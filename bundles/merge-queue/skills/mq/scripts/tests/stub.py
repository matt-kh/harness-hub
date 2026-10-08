#!/usr/bin/env python3
"""Scenario-routed stub for glab, gh and git (mq tests). No network, no real CLI.

    stub.py glab|gh|git ARGS...

MQ_SCENARIO names fixtures/<scenario>.json, deep-merged over fixtures/_gitlab.json or
_github.json (by its `gl-` / `gh-` prefix). Every invocation is appended to $STUB_LOG as
`<tool> <args>`. Reads of the same resource are sequenced: the k-th `glab api …/merge_requests/12`
(or `gh pr view 12`, `gh pr checks 12`, a branch, a compare) answers the k-th entry of its list
in the fixture, each entry a delta merged over the previous one; the last entry repeats.
Counters live in $STUB_STATE. Writes (glab mr rebase|merge|update, gh pr update-branch|merge|
edit|ready) answer `writes["<verb>-<N>"][k]` = {rc, out, err} (default: rc 0) so a test can
inject 403 / 405 / `422 … already up to date`.
"""
import copy
import json
import os
import re
import sys
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "fixtures")


def merge(base, delta):
    out = copy.deepcopy(base)
    for k, v in (delta or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load():
    scen = os.environ.get("MQ_SCENARIO", "gl-default")
    base = "_gitlab.json" if scen.startswith("gl-") else "_github.json"
    data = json.load(open(os.path.join(FIX, base)))
    path = os.path.join(FIX, scen + ".json")
    if os.path.exists(path):
        data = merge(data, json.load(open(path)))
    return data


def bump(key):
    """1-based count of calls for KEY in this test case."""
    d = os.environ.get("STUB_STATE") or "/tmp"
    f = os.path.join(d, re.sub(r"[^A-Za-z0-9_.-]", "_", key) + ".n")
    n = int(open(f).read()) + 1 if os.path.exists(f) else 1
    with open(f, "w") as fh:
        fh.write(str(n))
    return n


def pick(seq, k):
    return seq[min(k, len(seq)) - 1] if seq else {}


def cumulative(template, seq, k, fill):
    """State after the k-th read: template + deltas[0..k-1]; fill(state, delta) fixes derived fields."""
    state = template
    for delta in (seq or [{}])[:max(1, min(k, len(seq or [{}])))]:
        state = merge(state, delta)
        fill(state, delta)
    return state


def out(obj=None, text=None, rc=0, err=""):
    if text is not None:
        sys.stdout.write(text)
    elif obj is not None:
        sys.stdout.write(json.dumps(obj))
    if err:
        sys.stderr.write(err + "\n")
    sys.exit(rc)


def write(data, key):
    k = bump("write-" + key)
    w = pick((data.get("writes") or {}).get(key) or [], k)
    out(text=w.get("out", ""), rc=w.get("rc", 0), err=w.get("err", ""))


# ------------------------------------------------------------------------------- gitlab
def gl_mr(data, n, k):
    heads = data.get("heads") or {}
    seq = (data.get("mrs") or {}).get(str(n))
    if seq is None:
        out(rc=1, err="glab: 404 Not Found")
    tmpl = {"iid": n, "title": "PROJ-123 part %d" % n, "state": "opened", "draft": False,
            "labels": ["agent-worked"], "source_branch": "feat-x", "target_branch": "main",
            "sha": "head%d-1" % n, "squash": True, "has_conflicts": False,
            "detailed_merge_status": "mergeable", "merge_when_pipeline_succeeds": False,
            "head_pipeline": {"status": "success"}, "diverged_commits_count": 0,
            "rebase_in_progress": False, "merge_error": None,
            "web_url": "https://gitlab.example.com/o/r/-/merge_requests/%d" % n}

    def fill(st, delta):
        hp = st.get("head_pipeline")
        if isinstance(hp, dict) and ("sha" not in hp or ("head_pipeline" in delta
                                                         and "sha" not in (delta["head_pipeline"] or {}))):
            hp["sha"] = st["sha"]   # a pipeline named in a delta runs on that delta's head
        if "diff_refs" not in delta and ("target_branch" in delta or "diff_refs" not in st):
            st["diff_refs"] = {"base_sha": heads.get(st["target_branch"], "base-" + st["target_branch"])}
    return cumulative(tmpl, seq, k, fill)


def glab(data, args):
    if args[:2] == ["auth", "status"]:
        out(text="Logged in to gitlab.example.com\n")
    if args and args[0] == "mr" and len(args) >= 3 and args[1] in ("rebase", "merge", "update"):
        write(data, "%s-%s" % (args[1], args[2]))
    if not args or args[0] != "api":
        out(rc=1, err="stub: no route for glab %s" % " ".join(args))
    path = args[1]
    m = re.match(r"^projects/[^/?]+(.*)$", path)
    rest = m.group(1) if m else path
    if rest == "":
        out(data.get("project"))
    m = re.match(r"^/merge_requests/(\d+)\?", rest)
    if m:
        n = int(m.group(1))
        out(gl_mr(data, n, bump("mr-%d" % n)))
    if rest.startswith("/merge_requests?"):
        q = dict(urllib.parse.parse_qsl(rest.split("?", 1)[1]))
        rows = []
        for n in sorted(int(x) for x in (data.get("mrs") or {})):
            mr = gl_mr(data, n, 1)
            st = q.get("state", "all")
            if st != "all" and mr["state"] != st:
                continue
            if "labels" in q and q["labels"] not in mr["labels"]:
                continue
            if "source_branch" in q and mr["source_branch"] != q["source_branch"]:
                continue
            if "target_branch" in q and mr["target_branch"] != q["target_branch"]:
                continue
            rows.append({k: mr[k] for k in ("iid", "title", "state", "draft", "labels", "source_branch",
                                            "target_branch", "sha", "web_url")})
        out(rows)
    m = re.match(r"^/repository/branches/(.+)$", rest)
    if m:
        name = urllib.parse.unquote(m.group(1))
        k = bump("branch-" + name)
        heads = data.get("heads") or {}
        tmpl = {"name": name, "commit": {"id": heads.get(name, "base-" + name)},
                "protected": name == data["project"].get("default_branch"), "developers_can_merge": False}
        out(cumulative(tmpl, (data.get("branches") or {}).get(name), k, lambda s, d: None))
    m = re.match(r"^/repository/merge_base\?(.*)$", rest)
    if m:
        refs = [v for _k, v in urllib.parse.parse_qsl(m.group(1))]
        key = "...".join(refs)
        out((data.get("merge_base") or {}).get(key, {"id": "base-unrelated"}))
    out(rc=1, err="stub: no route for glab api %s" % path)


# ------------------------------------------------------------------------------- github
def gh_pr(data, n, k):
    seq = (data.get("prs") or {}).get(str(n))
    if seq is None:
        out(rc=1, err="GraphQL: Could not resolve to a PullRequest with the number of %d." % n)
    tmpl = {"number": n, "title": "part %d" % n, "state": "OPEN", "isDraft": False,
            "isCrossRepository": False, "mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN",
            "headRefOid": "head%d-1" % n, "headRefName": "feat-x", "baseRefName": "main",
            "autoMergeRequest": None, "reviewDecision": "", "labels": ["agent-worked"],
            "mergedAt": None, "url": "https://github.com/o/r/pull/%d" % n}
    st = cumulative(tmpl, seq, k, lambda s, d: None)
    st["labels"] = [{"name": x} for x in st["labels"]]
    return st


def flag(args, name):
    return args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else None


def gh(data, args):
    if args[:2] == ["auth", "status"]:
        out(text="Logged in to github.com\n")
    if args[:2] == ["repo", "view"]:
        fields = (flag(args, "--json") or "").split(",")
        repo = data.get("repo") or {}
        bad = [f for f in fields if f not in repo or f == "autoMergeAllowed"]
        if bad:   # like gh: an unknown --json field is an error (gh has no autoMergeAllowed)
            out(rc=1, err='Unknown JSON field: "%s"' % bad[0])
        out({f: repo[f] for f in fields})
    if args and args[0] == "pr" and len(args) >= 3 and args[1] in ("update-branch", "merge", "edit", "ready"):
        write(data, "%s-%s" % (args[1], args[2]))
    if args[:2] == ["pr", "view"]:
        n = int(args[2])
        out(gh_pr(data, n, bump("pr-%d" % n)))
    if args[:2] == ["pr", "checks"]:
        n = int(args[2])
        c = pick((data.get("checks") or {}).get(str(n)) or [{}], bump("checks-%d" % n))
        rows = c.get("rows", [{"bucket": "pass", "state": "SUCCESS", "name": "test"}])
        out(rows if rows else None, rc=c.get("rc", 0), err=c.get("err", ""))
    if args[:2] == ["pr", "list"]:
        st = (flag(args, "--state") or "open").upper()
        rows = []
        for n in sorted(int(x) for x in (data.get("prs") or {})):
            pr = gh_pr(data, n, 1)
            if st != "ALL" and pr["state"] != st:
                continue
            if flag(args, "--label") and flag(args, "--label") not in [x["name"] for x in pr["labels"]]:
                continue
            if flag(args, "--head") and pr["headRefName"] != flag(args, "--head"):
                continue
            if flag(args, "--base") and pr["baseRefName"] != flag(args, "--base"):
                continue
            rows.append(pr)
        out(rows)
    if args and args[0] == "api":
        rest = [a for a in args[1:] if a != "--hostname"]
        path = rest[-1]
        m = re.match(r"^repos/[^/]+/[^/]+/(.*)$", path)
        sub = m.group(1) if m else path
        if re.match(r"^repos/[^/]+/[^/]+$", path):   # the REST repository object
            out({"allow_auto_merge": bool((data.get("repo") or {}).get("autoMergeAllowed"))})
        if sub.startswith("rules/branches/"):
            out((data.get("rules") or {}).get(urllib.parse.unquote(sub[len("rules/branches/"):]), []))
        m = re.match(r"^branches/(.+)/protection$", sub)
        if m:
            p = (data.get("protection") or {}).get(urllib.parse.unquote(m.group(1)))
            if p == 403:
                out(rc=1, err="gh: Upgrade to GitHub Pro or make this repository public to enable this feature. (HTTP 403)")
            if p is None:
                out(rc=1, err="gh: Branch not protected (HTTP 404)")
            out(p)
        if sub.startswith("compare/"):
            key = urllib.parse.unquote(sub[len("compare/"):])
            seq = (data.get("compare") or {}).get(key)
            k = bump("compare-" + key)
            out(cumulative({"behind_by": 0, "status": "diverged"}, seq, k, lambda s, d: None))
        if sub == "actions/workflows":
            out(data.get("workflows", {"total_count": 1}))
    out(rc=1, err="stub: no route for gh %s" % " ".join(args))


# ---------------------------------------------------------------------------------- git
def git(data, args):
    if args == ["rev-parse", "--show-toplevel"]:
        out(text="/home/u/dev/r\n")
    if args == ["remote", "get-url", "origin"]:
        out(text=data["remote"] + "\n")
    if args == ["worktree", "list", "--porcelain"]:
        out(text=data.get("worktrees", ""))
    if args == ["show", "HEAD:.gitlab-ci.yml"]:
        if data.get("ci") is None:
            out(rc=128, err="fatal: path '.gitlab-ci.yml' does not exist in 'HEAD'")
        out(text=data["ci"])
    out(rc=1, err="stub: no route for git %s" % " ".join(args))


def main():
    tool, args = sys.argv[1], sys.argv[2:]
    log = os.environ.get("STUB_LOG")
    if log:
        with open(log, "a") as fh:
            fh.write("%s %s\n" % (tool, " ".join(args)))
    data = load()
    {"glab": glab, "gh": gh, "git": git}[tool](data, args)


if __name__ == "__main__":
    main()
