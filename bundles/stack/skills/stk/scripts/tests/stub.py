#!/usr/bin/env python3
"""Fixture-driven stub for glab and gh (stk tests). No network, no real CLI.

    stub.py glab|gh ARGS...

The scenario fixture ($STK_FIXTURE, written by run.sh for each sandbox) is deep-merged over
fixtures/_gitlab.json or fixtures/_github.json (by the scenario's `gl-` / `gh-` prefix in
$STK_SCENARIO). Every invocation is appended to $STUB_LOG as `<tool> <args>`.

Git facts come from the sandbox's real bare origin ($STK_ORIGIN): an open MR/PR without a
`sha` answers its source branch's head there, and `diverged_commits_count` (GitLab) or
`behind_by` (GitHub compare) is `git rev-list --count <sha>..<target>`. Merged MRs/PRs carry
their head sha at merge in the fixture. Writes (glab mr update|rebase, gh pr edit|ready|
update-branch) answer `writes["<verb>-<N>"]` = {rc, out, err} (default: rc 0).
"""
import copy
import json
import os
import re
import subprocess
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
    scen = os.environ.get("STK_SCENARIO", "gl-default")
    base = "_gitlab.json" if scen.startswith("gl-") else "_github.json"
    with open(os.path.join(FIX, base)) as fh:
        data = json.load(fh)
    path = os.environ.get("STK_FIXTURE")
    if path and os.path.exists(path):
        with open(path) as fh:
            data = merge(data, json.load(fh))
    return data


def git(*args):
    origin = os.environ.get("STK_ORIGIN")
    if not origin:
        return ""
    p = subprocess.run(["git", "--git-dir", origin] + list(args), capture_output=True, text=True)
    return p.stdout.strip() if p.returncode == 0 else ""


def head(branch):
    return git("rev-parse", "--verify", "--quiet", "refs/heads/%s^{commit}" % branch)


def behind(sha, target):
    tip = head(target)
    if not (sha and tip):
        return 0
    n = git("rev-list", "--count", "%s..%s" % (sha, tip))
    return int(n or 0)


def out(obj=None, text=None, rc=0, err=""):
    if text is not None:
        sys.stdout.write(text)
    elif obj is not None:
        sys.stdout.write(json.dumps(obj))
    if err:
        sys.stderr.write(err + "\n")
    sys.exit(rc)


def write(data, key):
    w = (data.get("writes") or {}).get(key) or {}
    out(text=w.get("out", ""), rc=w.get("rc", 0), err=w.get("err", ""))


# ------------------------------------------------------------------------------- gitlab
def gl_mr(data, n):
    raw = (data.get("mrs") or {}).get(str(n))
    if raw is None:
        out(rc=1, err="glab: 404 Not Found")
    mr = {"iid": n, "title": "PROJ-123 part %d" % n, "state": "opened", "draft": False,
          "labels": ["agent-worked"], "source_branch": "feat-x", "target_branch": "main",
          "squash": True, "has_conflicts": False, "detailed_merge_status": "mergeable",
          "web_url": "https://gitlab.example.com/o/r/-/merge_requests/%d" % n}
    mr.update(raw)
    if not mr.get("sha"):
        mr["sha"] = head(mr["source_branch"]) or "0" * 40
    if mr["state"] == "opened" and "diverged_commits_count" not in raw:
        mr["diverged_commits_count"] = behind(mr["sha"], mr["target_branch"])
    return mr


def glab(data, args):
    if args[:2] == ["auth", "status"]:
        out(text="Logged in to gitlab.example.com\n")
    if args and args[0] == "mr" and len(args) >= 3 and args[1] in ("rebase", "update"):
        write(data, "%s-%s" % (args[1], args[2]))
    if not args or args[0] != "api":
        out(rc=1, err="stub: no route for glab %s" % " ".join(args))
    path = args[1]
    m = re.match(r"^projects/[^/?]+(.*)$", path)
    rest = m.group(1) if m else path
    if rest == "":
        out(data.get("project"))
    m = re.match(r"^/merge_requests/(\d+)(\?.*)?$", rest)
    if m:
        out(gl_mr(data, int(m.group(1))))
    if rest.startswith("/merge_requests?"):
        q = dict(urllib.parse.parse_qsl(rest.split("?", 1)[1]))
        rows = []
        for n in sorted(int(x) for x in (data.get("mrs") or {})):
            mr = gl_mr(data, n)
            st = q.get("state", "all")
            if st != "all" and mr["state"] != st:
                continue
            if "labels" in q and q["labels"] not in mr["labels"]:
                continue
            rows.append({k: mr[k] for k in ("iid", "title", "state", "draft", "labels", "source_branch",
                                            "target_branch", "sha", "web_url")})
        out(rows)
    m = re.match(r"^/repository/branches/(.+)$", rest)
    if m:
        name = urllib.parse.unquote(m.group(1))
        b = {"name": name, "commit": {"id": head(name)}, "protected": name == data["project"].get("default_branch"),
             "developers_can_merge": False}
        b.update((data.get("branches") or {}).get(name) or {})
        out(b)
    out(rc=1, err="stub: no route for glab api %s" % path)


# ------------------------------------------------------------------------------- github
def gh_pr(data, n):
    raw = (data.get("prs") or {}).get(str(n))
    if raw is None:
        out(rc=1, err="GraphQL: Could not resolve to a PullRequest with the number of %d." % n)
    pr = {"number": n, "title": "part %d" % n, "state": "OPEN", "isDraft": False,
          "isCrossRepository": False, "mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN",
          "headRefName": "feat-x", "baseRefName": "main", "labels": ["agent-worked"],
          "url": "https://github.com/o/r/pull/%d" % n}
    pr.update(raw)
    if not pr.get("headRefOid"):
        pr["headRefOid"] = head(pr["headRefName"]) or "0" * 40
    pr["labels"] = [{"name": x} for x in pr["labels"]]
    return pr


def flag(args, name):
    return args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else None


def gh(data, args):
    if args[:2] == ["auth", "status"]:
        out(text="Logged in to github.com\n")
    if args[:2] == ["repo", "view"]:
        fields = (flag(args, "--json") or "").split(",")
        repo = data.get("repo") or {}
        bad = [f for f in fields if f not in repo]
        if bad:   # like gh: an unknown --json field is an error
            out(rc=1, err='Unknown JSON field: "%s"' % bad[0])
        out({f: repo[f] for f in fields})
    if args and args[0] == "pr" and len(args) >= 3 and args[1] in ("update-branch", "edit", "ready"):
        write(data, "%s-%s" % (args[1], args[2]))
    if args[:2] == ["pr", "view"]:
        out(gh_pr(data, int(args[2])))
    if args[:2] == ["pr", "list"]:
        st = (flag(args, "--state") or "open").upper()
        rows = []
        for n in sorted(int(x) for x in (data.get("prs") or {})):
            pr = gh_pr(data, n)
            if st != "ALL" and pr["state"] != st:
                continue
            if flag(args, "--label") and flag(args, "--label") not in [x["name"] for x in pr["labels"]]:
                continue
            rows.append(pr)
        out(rows)
    if args and args[0] == "api":
        path = [a for a in args[1:] if not a.startswith("-")][-1]
        m = re.match(r"^repos/[^/]+/[^/]+/(.*)$", path)
        sub = m.group(1) if m else path
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
            base, _, sha = urllib.parse.unquote(sub[len("compare/"):]).partition("...")
            out({"behind_by": behind(sha, base), "status": "diverged"})
    out(rc=1, err="stub: no route for gh %s" % " ".join(args))


def main():
    tool, args = sys.argv[1], sys.argv[2:]
    log = os.environ.get("STUB_LOG")
    if log:
        with open(log, "a") as fh:
            fh.write("%s %s\n" % (tool, " ".join(args)))
    data = load()
    {"glab": glab, "gh": gh}[tool](data, args)


if __name__ == "__main__":
    main()
