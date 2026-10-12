#!/usr/bin/env python3
"""Stack sync for free tiers: keep stacked MRs/PRs retargeted, rebased and pushed — stdlib only.

Canonical invocation: `stk <verb>` (linked into ~/.local/bin by `harness apply`). It shells out
to `glab` (GitLab, CE included), `gh` (GitHub) and `git` only, and prints every native command
before it runs it, so everything it does is something you could have typed yourself. Merging
stays human: parts are merged bottom-up in the web UI in the order `stk plan` prints.

A stack is work-ticket's layout: a ticket branch BR with its main MR/PR (BR -> BASE) and parts
`BR-sub-NN-<task>`. A part targets BR (a fan-in leaf) or another part's branch (a chain).

Verbs (selection for all: `<refs...>` | `--stack BR [--with-main]` | `--label L`; nothing given
= `--label <stack.label>`; a ref or label selects the whole stack it belongs to):
  plan    Read-only. Topology (chains bottom-up, fan-in leaves, main MR), per-MR state (open,
          merged, draft, target ok or misfired, behind, conflicts, worktree), the MERGE ORDER
          for the human, and the exact native commands `stk sync` would run. Uses the
          remote-tracking refs as of the last `git fetch` (sync fetches first).
  status  Read-only. Live table of every member incl. merged parts and local worktrees; a
          merged part whose worktree still exists gets a `cleanup` line.
  check [--fix]
          Read-only. Repository readiness for stacks: GitLab merge method, squash option,
          delete-source-branch default, protected branches vs the ticket branch, your access;
          GitHub delete-branch-on-merge, merge strategies, "up to date" rules, your
          permission. --fix prints the settings commands; it never runs them.
  sync [--include-human] [--no-push] [--skip-ci]
          1 retarget open parts aimed at the default branch (misfire) or at a merged part's
            branch (`glab mr update N --target-branch T`, `gh pr edit N -B T`);
          2 cascade each chain locally: `git fetch origin`, then in the worktree that has the
            chain's top branch checked out `git rebase --update-refs --onto <new base>
            <old base> <top>` (clean worktrees only; `git rebase --abort` on a conflict
            leaves it exactly as found);
          3 push the rebased branches: `git push --force-with-lease origin <subs…>`;
          4 refresh at most one fan-in leaf server-side when the merge method needs an
            up-to-date source (`glab mr rebase`, `gh pr update-branch`);
          5 mark the main MR/PR ready once every part merged.
          Writes only to MRs/PRs carrying an agent-* label (WORK_TICKET_AGENT_LABEL_RE);
          unlabelled ones are listed with the command that labels them. --include-human lifts
          that (the guard asks); --no-push rebases locally and prints the push.

Common flags: -R/--repo owner/repo (default: the origin remote), --provider gitlab|github,
--json (the default when stdout is not a TTY) / --text.
Exit codes: 0 nothing to do or all done, 1 action needed by a human, 2 auth/access error.

Deliberately NOT implemented: merging (humans merge in the UI), `--force` (only
`--force-with-lease`, only sub branches), `reset --hard`, `rebase --continue` on your behalf,
approving, `glab stack`, local state files.

Env (each falls back to the harness config key in brackets, read from build/config.json via
HARNESS_CONFIG_JSON / HARNESS_HOME, then to the default):
  HARNESS_STACK_LABEL [stack.label]                 default label selection (stack)
  HARNESS_STACK_PUSH [stack.push]                   false: rebase locally, print the push (true)
  HARNESS_STACK_UPDATE_METHOD [stack.update_method] rebase|merge, GitHub leaf refresh (rebase)
  HARNESS_STACK_LEAF_REFRESH [stack.leaf_refresh]   auto|never (auto: only when the merge
                                                    method needs an up-to-date source)
  HARNESS_GITLAB_HOSTS_RE, HARNESS_GITLAB_HOST [gitlab.host]  GitLab host detection; any
                                                    other host is GitHub
  WORK_TICKET_AGENT_LABEL_RE (^agent-), WORK_TICKET_LABEL (agent-worked)  the label gate
  GLAB, GH, GIT                                     binary overrides (tests)
"""
import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import urllib.parse

# >>> harness_config
_HARNESS_CFG = None


def _harness_cfg_path():
    return os.environ.get("HARNESS_CONFIG_JSON") or os.path.join(
        os.environ.get("HARNESS_HOME") or os.path.expanduser("~/harness-hub"), "build", "config.json")


def cfg(key, default=None):
    """Dotted lookup in the compiled harness config, e.g. cfg("jira.url", "")."""
    global _HARNESS_CFG
    if _HARNESS_CFG is None:
        try:
            with open(_harness_cfg_path()) as fh:
                _HARNESS_CFG = json.load(fh)
        except (OSError, ValueError):
            _HARNESS_CFG = {}
        if not isinstance(_HARNESS_CFG, dict):
            _HARNESS_CFG = {}
    cur = _HARNESS_CFG
    for part in key.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur
# <<< harness_config


EXIT_OK, EXIT_ACTION, EXIT_ACCESS = 0, 1, 2
BINARIES = {"glab": os.environ.get("GLAB", "glab"), "gh": os.environ.get("GH", "gh"),
            "git": os.environ.get("GIT", "git")}
BIN_HINT = {"glab": "activate the gitlab bundle (hub.bundles) and run `harness apply`",
            "gh": "activate the github bundle (hub.bundles) and run `harness apply`",
            "git": "install git (2.38 or newer for rebase --update-refs)"}
CALL_TIMEOUT = 120
SUB_RE = re.compile(r"-sub-[0-9]+-")
REBASE_ENV = {"GIT_EDITOR": "true", "GIT_SEQUENCE_EDITOR": "true"}

DEFAULTS = {"label": "stack", "push": True, "update_method": "rebase", "leaf_refresh": "auto"}
CHOICES = {"update_method": ("rebase", "merge"), "leaf_refresh": ("auto", "never")}


# ------------------------------------------------------------------------------- settings
def setting(key):
    """HARNESS_STACK_<KEY> first, then cfg("stack.<key>"), then the default; typed like the default."""
    default = DEFAULTS[key]
    raw = os.environ.get("HARNESS_STACK_" + key.upper())
    if raw is None or raw == "":
        raw = cfg("stack." + key)
    if raw is None or raw == "":
        return default
    if isinstance(default, bool):
        if isinstance(raw, bool):
            return raw
        low = str(raw).strip().lower()
        if low in ("1", "true", "yes"):
            return True
        if low in ("0", "false", "no"):
            return False
        die("stack.%s = %r is not a boolean; set HARNESS_STACK_%s or stack.%s to true or false"
            % (key, raw, key.upper(), key), EXIT_ACTION)
    value = str(raw).strip()
    if key in CHOICES and value not in CHOICES[key]:
        die("stack.%s = %r; use one of: %s" % (key, value, ", ".join(CHOICES[key])), EXIT_ACTION)
    return value


def agent_label_re():
    pattern = os.environ.get("WORK_TICKET_AGENT_LABEL_RE") or "^agent-"
    try:
        return re.compile(pattern)
    except re.error:
        die("WORK_TICKET_AGENT_LABEL_RE %r is not a valid regex; fix it or unset it" % pattern, EXIT_ACTION)


def gov_label():
    return os.environ.get("WORK_TICKET_LABEL") or "agent-worked"


# ------------------------------------------------------------------------- small helpers
class AccessError(Exception):
    """Binary missing, not logged in, no access to the project -> exit 2."""


class CliError(Exception):
    """A native read failed for another reason."""

    def __init__(self, argv, rc, err):
        Exception.__init__(self, "%s exited %d: %s" % (fmt_cmd(argv), rc, first_line(err) or "no output"))
        self.rc, self.err = rc, err


def die(msg, code=EXIT_ACTION):
    print(msg, file=sys.stderr)
    sys.exit(code)


def say(msg):
    print(msg, file=sys.stderr, flush=True)


def fmt_cmd(argv):
    return " ".join(shlex.quote(str(a)) for a in argv)


def first_line(text):
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()
    return ""


def short(sha):
    return (sha or "")[:8] or "?"


ACCESS_RE = re.compile(r"\b401\b|unauthori[sz]ed|not logged in|authentication (failed|required)"
                       r"|auth login|bad credentials|could not resolve host|no such host"
                       r"|connection refused", re.I)


def call(argv, timeout=CALL_TIMEOUT, env=None):
    """Run a native command (argv[0] is the logical name glab|gh|git). -> (rc, stdout, stderr)."""
    real = [BINARIES.get(argv[0], argv[0])] + [str(a) for a in argv[1:]]
    full_env = None
    if env:
        full_env = dict(os.environ)
        full_env.update(env)
    try:
        p = subprocess.run(real, capture_output=True, text=True, timeout=timeout, env=full_env)
    except subprocess.TimeoutExpired:
        return 124, "", "timed out after %ds" % timeout
    except FileNotFoundError:
        raise AccessError("%s not found on PATH; %s" % (argv[0], BIN_HINT.get(argv[0], "install it")))
    return p.returncode, p.stdout, p.stderr.strip()


def read_json(argv):
    rc, out, err = call(argv)
    if rc != 0:
        if ACCESS_RE.search(err):
            raise AccessError("%s: %s — check `%s auth status`" % (fmt_cmd(argv[:3]), first_line(err), argv[0]))
        raise CliError(argv, rc, err)
    try:
        return json.loads(out) if out.strip() else None
    except ValueError:
        raise CliError(argv, rc, "unparseable JSON")


def http_status(err):
    m = re.search(r"\b(40[0-9]|42[0-9]|50[0-9])\b", err or "")
    return int(m.group(1)) if m else None


def is_sub(branch):
    return bool(SUB_RE.search(branch or ""))


def stack_root(branch):
    """feat-x-sub-02-api -> feat-x ('' when the branch is not a sub branch)."""
    m = re.match(r"^(.+?)-sub-[0-9]+-", branch or "")
    return m.group(1) if m else ""


def sub_number(branch):
    m = re.search(r"-sub-(\d+)-", branch or "")
    return int(m.group(1)) if m else 10 ** 6


def parse_ref(text):
    m = re.match(r"^[!#]?(\d+)$", text.strip())
    if not m:
        die("stk: %r is not an MR/PR number; pass numbers like 12, !12 or #12" % text, EXIT_ACTION)
    return int(m.group(1))


# --------------------------------------------------------------------------------- remote
def parse_remote(url):
    """(host, owner/repo) from an SSH, scp-like or HTTPS remote; credentials never kept."""
    u = (url or "").strip()
    m = re.match(r"^[a-z][a-z0-9+.-]*://(?:[^@/]*@)?([^/:]+)(?::\d+)?/(.+?)(?:\.git)?/?$", u, re.I)
    if not m:
        m = re.match(r"^(?:[^@/]+@)?([^:/]+):(.+?)(?:\.git)?/?$", u)
    if not m:
        return None, None
    return m.group(1).lower(), m.group(2)


def detect_provider(host):
    """Mirror of work-ticket's rf_provider: GitLab hosts by regex/host/'gitlab', else GitHub."""
    if host in ("github.com", "www.github.com", "ssh.github.com"):
        return "github"
    pattern = os.environ.get("HARNESS_GITLAB_HOSTS_RE") or ""
    if not pattern:
        gl = os.environ.get("HARNESS_GITLAB_HOST") or cfg("gitlab.host") or ""
        if gl:
            pattern = "^" + re.escape(str(gl).lower()) + "$"
    if pattern:
        try:
            if re.search(pattern, host, re.I):
                return "gitlab"
        except re.error:
            say("stk: HARNESS_GITLAB_HOSTS_RE %r is not a valid regex; ignored" % pattern)
    return "gitlab" if "gitlab" in host else "github"


# ------------------------------------------------------------------------------------ git
class Git:
    """Local git facts for the checkout stk runs in (top = '' outside a checkout)."""

    def __init__(self):
        rc, out, _ = call(["git", "rev-parse", "--show-toplevel"])
        self.top = out.strip() if rc == 0 else ""
        self._trees = None

    def run(self, args, wt=None, env=None):
        return call(["git"] + (["-C", wt] if wt else []) + list(args), env=env)

    def remote_url(self):
        if not self.top:
            return ""
        rc, out, _ = self.run(["config", "--get", "remote.origin.url"])
        if rc != 0:
            rc, out, _ = self.run(["remote", "get-url", "origin"])
        return out.strip() if rc == 0 else ""

    def rev(self, ref):
        if not self.top:
            return None
        rc, out, _ = self.run(["rev-parse", "--verify", "--quiet", ref + "^{commit}"])
        return out.strip() if rc == 0 and out.strip() else None

    def local(self, branch):
        return self.rev("refs/heads/" + branch)

    def remote(self, branch):
        return self.rev("refs/remotes/origin/" + branch)

    def ancestor(self, a, b):
        """True/False, or None when git cannot tell (a commit missing locally)."""
        if not (self.top and a and b):
            return None
        rc, _, _ = self.run(["merge-base", "--is-ancestor", a, b])
        return {0: True, 1: False}.get(rc)

    def merge_base(self, a, b):
        rc, out, _ = self.run(["merge-base", a, b])
        return out.strip() if rc == 0 else None

    def fork_point(self, upstream, branch):
        rc, out, _ = self.run(["merge-base", "--fork-point", upstream, branch])
        return out.strip() if rc == 0 and out.strip() else self.merge_base(upstream, branch)

    def worktrees(self, refresh=False):
        """{branch: path} from `git worktree list --porcelain`."""
        if self._trees is None or refresh:
            found, path = {}, None
            rc, out, _ = self.run(["worktree", "list", "--porcelain"]) if self.top else (1, "", "")
            for line in (out if rc == 0 else "").splitlines():
                if line.startswith("worktree "):
                    path = line[len("worktree "):]
                elif line.startswith("branch refs/heads/") and path:
                    found[line[len("branch refs/heads/"):]] = path
            self._trees = found
        return self._trees

    def unclean(self, wt):
        """'' when the worktree is clean and not mid-rebase/merge, else the reason."""
        for marker in ("rebase-merge", "rebase-apply", "MERGE_HEAD", "CHERRY_PICK_HEAD"):
            rc, out, _ = self.run(["rev-parse", "--git-path", marker], wt=wt)
            p = out.strip()
            if rc == 0 and p and os.path.exists(p if os.path.isabs(p) else os.path.join(wt, p)):
                return "a rebase or merge is in progress there; finish or abort it first"
        rc, out, err = self.run(["status", "--porcelain"], wt=wt)
        if rc != 0:
            return "git status failed there: %s" % (first_line(err) or "exit %d" % rc)
        if out.strip():
            return "it has uncommitted or untracked changes (%d path(s)); commit or stash them first" % len(out.splitlines())
        return ""


# ---------------------------------------------------------------------------- data model
class MR:
    """One merge request / pull request, normalised across providers."""

    def __init__(self, **kw):
        self.ref = kw.get("ref")
        self.title = kw.get("title") or ""
        self.state = kw.get("state") or "open"          # open | merged | closed
        self.draft = bool(kw.get("draft"))
        self.labels = kw.get("labels") or []
        self.source = kw.get("source") or ""
        self.target = kw.get("target") or ""
        self.sha = kw.get("sha") or ""
        self.conflict = bool(kw.get("conflict"))
        self.status = kw.get("status") or ""
        self.behind = kw.get("behind")                  # commits behind the target (None = unknown)
        self.cross = bool(kw.get("cross"))
        self.url = kw.get("url") or ""


class GitLab:
    """glab-backed provider (GitLab CE and above)."""

    name, sigil, kind = "gitlab", "!", "MR"

    def __init__(self, host, repo, explicit):
        self.host, self.repo = host, repo
        self.pid = urllib.parse.quote(repo, safe="") if explicit else ":id"
        self.rflag = ["-R", repo] if explicit else []
        self._project, self._branches = None, {}

    def api(self, path):
        return read_json(["glab", "api", path])

    def project(self):
        if self._project is None:
            try:
                self._project = self.api("projects/%s" % self.pid) or {}
            except CliError as e:
                if http_status(e.err) in (403, 404):
                    raise AccessError("project %s: %s — check the remote and your access"
                                      % (self.repo or "of this checkout", first_line(e.err)))
                raise
        return self._project

    def default_branch(self):
        return self.project().get("default_branch") or "main"

    def facts(self):
        p = self.project()
        return {"merge_method": p.get("merge_method") or "merge",
                "squash_option": p.get("squash_option") or "default_off",
                "remove_source_branch": bool(p.get("remove_source_branch_after_merge"))}

    def access_level(self):
        perms = self.project().get("permissions") or {}
        levels = [(perms.get(k) or {}).get("access_level") or 0 for k in ("project_access", "group_access")]
        return max(levels)

    def needs_uptodate(self, branch):
        """ff and semi-linear merges refuse a source that is behind its target."""
        return self.facts()["merge_method"] in ("ff", "rebase_merge")

    @staticmethod
    def norm(j):
        status = j.get("detailed_merge_status") or j.get("merge_status") or ""
        return MR(ref=j.get("iid"), title=j.get("title"),
                  state={"opened": "open", "locked": "open"}.get(j.get("state"), j.get("state")),
                  draft=j.get("draft") or j.get("work_in_progress"),
                  labels=[x if isinstance(x, str) else x.get("name") for x in j.get("labels") or []],
                  source=j.get("source_branch"), target=j.get("target_branch"), sha=j.get("sha"),
                  conflict=j.get("has_conflicts") or status == "conflict", status=status,
                  behind=j.get("diverged_commits_count"), url=j.get("web_url"))

    def get(self, ref):
        return self.norm(self.api("projects/%s/merge_requests/%d?include_diverged_commits_count=true"
                                  % (self.pid, ref)) or {})

    def _list(self, query):
        return [self.norm(j) for j in self.api("projects/%s/merge_requests?%s" % (self.pid, query)) or []]

    def list_all(self):
        return self._list("state=all&per_page=100")

    def list_label(self, label):
        return self._list("state=opened&labels=%s&per_page=100" % urllib.parse.quote(label, safe=""))

    def branch(self, name):
        if name not in self._branches:
            try:
                self._branches[name] = self.api("projects/%s/repository/branches/%s"
                                                % (self.pid, urllib.parse.quote(name, safe=""))) or {}
            except CliError:
                self._branches[name] = {}
        return self._branches[name]

    def refresh_behind(self, mr):
        return mr.behind

    def cmd_retarget(self, mr, branch):
        return ["glab", "mr", "update", str(mr.ref), "--target-branch", branch] + self.rflag

    def cmd_ready(self, mr):
        return ["glab", "mr", "update", str(mr.ref), "--ready"] + self.rflag

    def cmd_label(self, ref):
        return ["glab", "mr", "update", str(ref), "--label", gov_label()] + self.rflag

    def cmd_refresh(self, mr, skip_ci=False):
        return ["glab", "mr", "rebase", str(mr.ref)] + (["--skip-ci"] if skip_ci else []) + self.rflag


class GitHub:
    """gh-backed provider (github.com and GitHub Enterprise)."""

    name, sigil, kind = "github", "#", "PR"
    FIELDS = ("number,title,state,isDraft,isCrossRepository,mergeable,mergeStateStatus,headRefOid,"
              "headRefName,baseRefName,labels,url")
    REPO_FIELDS = ("defaultBranchRef,deleteBranchOnMerge,squashMergeAllowed,rebaseMergeAllowed,"
                   "mergeCommitAllowed,isPrivate,viewerPermission")

    def __init__(self, host, repo):
        self.host, self.repo = host or "github.com", repo
        self.spec = repo if self.host == "github.com" else "%s/%s" % (self.host, repo)
        self.rflag = ["-R", self.spec]
        self.hflag = [] if self.host == "github.com" else ["--hostname", self.host]
        self._repo, self._strict = None, {}

    def api(self, path):
        return read_json(["gh", "api"] + self.hflag + ["repos/%s%s" % (self.repo, "/" + path if path else "")])

    def api_soft(self, path):
        """(json|None, http status|None): 404 and 403 are answers here (no rules / not on this plan)."""
        try:
            return self.api(path), None
        except CliError as e:
            code = http_status(e.err)
            if code in (403, 404):
                return None, code
            raise

    def repo_facts(self):
        if self._repo is None:
            try:
                self._repo = read_json(["gh", "repo", "view", self.spec, "--json", self.REPO_FIELDS]) or {}
            except CliError as e:
                raise AccessError("gh repo view %s: %s — check the remote and your access" % (self.spec, first_line(e.err)))
        return self._repo

    def default_branch(self):
        return (self.repo_facts().get("defaultBranchRef") or {}).get("name") or "main"

    def strict(self, branch):
        """(strict, source) — does a ruleset or classic protection require an up-to-date branch?"""
        if branch not in self._strict:
            q = urllib.parse.quote(branch, safe="")
            rules, _ = self.api_soft("rules/branches/%s" % q)
            for r in rules or []:
                if isinstance(r, dict) and r.get("type") == "required_status_checks" and \
                        (r.get("parameters") or {}).get("strict_required_status_checks_policy"):
                    self._strict[branch] = (True, "ruleset")
                    break
            else:
                prot, code = self.api_soft("branches/%s/protection" % q)
                if ((prot or {}).get("required_status_checks") or {}).get("strict"):
                    self._strict[branch] = (True, "branch protection")
                else:
                    self._strict[branch] = (False, "private repository on GitHub Free" if code == 403 else "")
        return self._strict[branch]

    def needs_uptodate(self, branch):
        return self.strict(branch)[0]

    @staticmethod
    def norm(j):
        return MR(ref=j.get("number"), title=j.get("title"),
                  state={"OPEN": "open", "MERGED": "merged", "CLOSED": "closed"}.get(j.get("state"), "open"),
                  draft=j.get("isDraft"), labels=[x.get("name") for x in j.get("labels") or []],
                  source=j.get("headRefName"), target=j.get("baseRefName"), sha=j.get("headRefOid"),
                  conflict=j.get("mergeable") == "CONFLICTING" or j.get("mergeStateStatus") == "DIRTY",
                  status=j.get("mergeStateStatus") or "", cross=j.get("isCrossRepository"), url=j.get("url"))

    def get(self, ref):
        return self.norm(read_json(["gh", "pr", "view", str(ref)] + self.rflag + ["--json", self.FIELDS]) or {})

    def _list(self, extra):
        out = read_json(["gh", "pr", "list"] + self.rflag + extra + ["--limit", "100", "--json", self.FIELDS])
        return [self.norm(j) for j in out or []]

    def list_all(self):
        return self._list(["--state", "all"])

    def list_label(self, label):
        return self._list(["--state", "open", "--label", label])

    def refresh_behind(self, mr):
        if mr.behind is None and mr.sha and mr.target:
            j = self.api("compare/%s...%s" % (urllib.parse.quote(mr.target, safe=""), mr.sha)) or {}
            mr.behind = int(j.get("behind_by") or 0)
        return mr.behind

    def cmd_retarget(self, mr, branch):
        return ["gh", "pr", "edit", str(mr.ref)] + self.rflag + ["-B", branch]

    def cmd_ready(self, mr):
        return ["gh", "pr", "ready", str(mr.ref)] + self.rflag

    def cmd_label(self, ref):
        return ["gh", "pr", "edit", str(ref)] + self.rflag + ["--add-label", gov_label()]

    def cmd_refresh(self, mr, skip_ci=False):
        return (["gh", "pr", "update-branch", str(mr.ref)] + self.rflag
                + (["--rebase"] if setting("update_method") == "rebase" else []))


# ----------------------------------------------------------------------------- the stack
class Stack:
    """One ticket branch BR: its main MR/PR, its parts and their topology."""

    def __init__(self, p, br, members):
        self.p, self.br = p, br
        default = p.default_branch()
        mains = sorted([m for m in members if m.source == br and m.state != "closed"],
                       key=lambda m: (m.state != "open", -(m.ref or 0)))
        self.main = mains[0] if mains else None
        self.base = self.main.target if self.main else default
        self.default = default
        self.parts = sorted([m for m in members if m.source != br and m.state != "closed"],
                            key=lambda m: (sub_number(m.source), m.ref))
        self.closed = [m for m in members if m.state == "closed" and m.source != br]
        self.by_source = dict((m.source, m) for m in self.parts)
        self.open = [m for m in self.parts if m.state == "open" and not m.cross]
        self.forks = [m for m in self.parts if m.state == "open" and m.cross]
        self.merged = [m for m in self.parts if m.state == "merged"]
        self.want = {}      # ref -> resolved target
        self.why = {}       # ref -> why the target changes
        for m in self.open:
            self.want[m.ref], self.why[m.ref] = self.resolve(m)

    def resolve(self, m):
        """(the target this part should have, reason or '')."""
        t = m.target
        if t == self.default and self.br != self.default and is_sub(m.source):
            return self.br, "targets the default branch %s (auto-retarget misfire after a branch delete?)" % t
        seen, first = set(), None
        while t in self.by_source and self.by_source[t].state == "merged" and t not in seen:
            seen.add(t)
            first = first or self.by_source[t]
            t = self.by_source[t].target
            if t == self.default and self.br != self.default:
                t = self.br
        if first is not None:
            return t, "its blocker %s%s (%s) merged" % (self.p.sigil, first.ref, first.source)
        return m.target, ""

    def children(self, branch):
        return [m for m in self.open if self.want[m.ref] == branch]

    def paths(self):
        """Every path BR -> ... -> top through open parts, bottom-up, by the top's sub number."""
        out = []

        def walk(m, acc):
            kids = self.children(m.source)
            if not kids:
                out.append(acc + [m])
            for k in kids:
                walk(k, acc + [m])
        for root in [m for m in self.open if self.want[m.ref] not in self.by_source or
                     self.by_source[self.want[m.ref]].state != "open"]:
            walk(root, [])
        return sorted(out, key=lambda path: (sub_number(path[-1].source), path[-1].ref))

    def chains(self):
        return [path for path in self.paths() if len(path) > 1 or self.children(path[0].source)]

    def leaves(self):
        return [path[0] for path in self.paths() if len(path) == 1 and not self.children(path[0].source)]

    def merge_order(self):
        """Bottom-up: a part after its blocker, otherwise by sub number; the main MR last."""
        order, done = [], set()
        pending = list(self.open)
        while pending:
            ready = [m for m in pending if self.want[m.ref] not in self.by_source
                     or self.by_source[self.want[m.ref]].state != "open"
                     or self.want[m.ref] in done]
            nxt = sorted(ready or pending, key=lambda m: (sub_number(m.source), m.ref))[0]
            order.append(nxt)
            done.add(nxt.source)
            pending.remove(nxt)
        return order


def load(p, a):
    """-> list of Stack, plus MRs/PRs that are not part of any stack."""
    everything = p.list_all()
    if a.refs:
        if a.stack or a.label:
            die("stk: pass refs, --stack or --label, not several", EXIT_ACTION)
        picked = []
        for r in a.refs:
            n = parse_ref(r)
            hit = [m for m in everything if m.ref == n]
            picked.append(hit[0] if hit else p.get(n))
        roots = [stack_root(m.source) or m.source for m in picked]
    elif a.stack:
        if a.label:
            die("stk: pass --stack or --label, not both", EXIT_ACTION)
        roots = [a.stack]
    else:
        label = a.label or setting("label")
        roots = [stack_root(m.source) or m.source for m in p.list_label(label)]
    seen, stacks, loose = set(), [], []
    for br in roots:
        if br in seen:
            continue
        seen.add(br)
        members = [m for m in everything if m.source == br or (m.source.startswith(br + "-sub-") and is_sub(m.source))]
        if not any(m.source != br for m in members):
            loose.extend(m for m in members if m.state == "open")
            continue
        for m in members:   # live details for open members (behind, conflicts, draft)
            if m.state == "open":
                live = p.get(m.ref)
                live.cross = live.cross or m.cross
                m.__dict__.update(live.__dict__)
        stacks.append(Stack(p, br, members))
    return stacks, loose


def make_provider(a, git):
    host, path = parse_remote(git.remote_url())
    repo = a.repo or path
    if not repo:
        die("stk: no origin remote here and no -R owner/repo; run it inside a checkout or pass -R", EXIT_ACCESS)
    provider = a.provider or detect_provider(host or "github.com")
    if provider == "gitlab":
        return GitLab(host, repo, explicit=bool(a.repo))
    return GitHub(host if host and detect_provider(host) == "github" and not a.repo else "github.com", repo)


# --------------------------------------------------------------------------------- report
class Report:
    def __init__(self, verb, p, a):
        self.data = {"verb": verb, "provider": p.name, "repo": p.repo, "selection": describe_selection(a)}
        self.steps = []

    def step(self, kind, status, message, ref=None, commands=None, ran=None):
        """status: ran | planned | skipped | failed | conflict | todo | info."""
        s = {"ref": ref, "kind": kind, "status": status, "message": message,
             "commands": [c if isinstance(c, str) else fmt_cmd(c) for c in commands or []]}
        if ran is not None:
            s["ran"] = [c if isinstance(c, str) else fmt_cmd(c) for c in ran]
        self.steps.append(s)
        return s

    def exit_code(self):
        return EXIT_ACTION if any(s["status"] in ("skipped", "failed", "conflict", "todo") for s in self.steps) else EXIT_OK


def describe_selection(a):
    if a.refs:
        return {"mode": "refs", "refs": [parse_ref(r) for r in a.refs]}
    if a.stack:
        return {"mode": "stack", "stack": a.stack, "with_main": bool(a.with_main)}
    return {"mode": "label", "label": a.label or setting("label")}


def labelled(mr, opts):
    return opts.get("include_human") or any(agent_label_re().search(x or "") for x in mr.labels)


def topology(st, git, with_main):
    trees = git.worktrees()
    sg = st.p.sigil

    def row(m):
        r = {"ref": m.ref, "source": m.source, "target": m.target, "state": "draft" if (m.state == "open" and m.draft) else m.state,
             "labelled": any(agent_label_re().search(x or "") for x in m.labels), "worktree": trees.get(m.source)}
        if m.state == "open":
            want = st.want.get(m.ref, m.target)
            r.update({"target_ok": want == m.target, "behind": m.behind, "conflicts": m.conflict})
            if want != m.target:
                r["retarget"] = {"to": want, "why": st.why.get(m.ref, "")}
        if m.cross:
            r["fork"] = True
        return r
    out = {"branch": st.br, "base": st.base,
           "main": ({"ref": st.main.ref, "state": "draft" if (st.main.state == "open" and st.main.draft) else st.main.state}
                    if st.main else None),
           "chains": [[m.ref for m in path] for path in st.chains()],
           "leaves": [m.ref for m in st.leaves()],
           "merged": [m.ref for m in st.merged],
           "parts": [row(m) for m in st.parts]}
    if with_main and st.main is not None:
        out["main_row"] = row(st.main)
    order = ["%s%s" % (sg, m.ref) for m in st.merge_order()]
    if st.main is not None and st.main.state == "open":
        order.append("%s%s (main, last)" % (sg, st.main.ref))
    out["merge_order"] = order
    return out


# ---------------------------------------------------------------------------- the sync core
class Sync:
    """retarget -> cascade -> push -> leaf refresh -> ready. dry=True plans without writing."""

    def __init__(self, p, git, rep, opts, dry):
        self.p, self.git, self.rep, self.opts, self.dry = p, git, rep, opts, dry
        self.fetched = False
        self.refreshed = 0
        self.moved = {}     # branch -> its sha before this run's cascade (planned or done)

    def run_cmd(self, kind, ref, message, cmd):
        """Run (or plan) one server-side write; -> True when it ran (or would run) cleanly."""
        if self.dry:
            self.rep.step(kind, "planned", message, ref=ref, commands=[cmd])
            return True
        say("[%s%s] %s" % (self.p.sigil, ref, message))
        say("+ " + fmt_cmd(cmd))
        rc, _out, err = call(cmd)
        if rc != 0 and kind == "refresh" and "already up to date" in (err or "").lower():
            rc = 0
        if rc != 0:
            self.rep.step(kind, "failed", "%s: %s" % (message, first_line(err) or "exit %d" % rc), ref=ref, commands=[cmd])
            return False
        self.rep.step(kind, "ran", message, ref=ref, ran=[cmd])
        return True

    # 1 -- retarget
    def retarget(self, st):
        for m in st.open:
            want = st.want[m.ref]
            if want == m.target:
                continue
            cmd = self.p.cmd_retarget(m, want)
            msg = "%s; retarget %s -> %s" % (st.why[m.ref], m.target, want)
            if not labelled(m, self.opts):
                self.rep.step("retarget", "skipped", "not agent-labelled; " + msg, ref=m.ref,
                              commands=[self.p.cmd_label(m.ref), cmd])
                continue
            if self.run_cmd("retarget", m.ref, msg, cmd) and not self.dry:
                m.target = want

    # 2+3 -- cascade and push
    def tip(self, branch):
        """(ref name, sha) of the base a part should sit on."""
        if branch in self.moved:
            return branch, self.git.local(branch)
        return "origin/" + branch, self.git.remote(branch)

    def head(self, branch):
        return self.git.local(branch) or self.git.remote(branch)

    def stale(self, st, m, target):
        """(reason, old base sha) when part m must move onto `target`, else None."""
        if m.source in self.moved:
            return None
        if target in self.moved:
            return "its base %s is rebased in this run" % target, self.moved[target]
        _ref, tip = self.tip(target)
        head = self.head(m.source)
        if not tip or not head:
            return None
        carried = [y for y in st.merged if y.sha and self.git.ancestor(y.sha, head)
                   and self.git.ancestor(y.sha, tip) is False]
        if carried:
            top = [y for y in carried if all(self.git.ancestor(z.sha, y.sha) for z in carried)] or carried[-1:]
            y = top[0]
            return ("carries the pre-squash commits of merged %s%s (%s)" % (self.p.sigil, y.ref, y.source)), y.sha
        if self.git.ancestor(tip, head) is not False:
            return None
        if target in st.by_source and st.by_source[target].state == "open":
            ref = m.source if self.git.local(m.source) else "origin/" + m.source
            return ("its base %s moved (amended or rebased)" % target), self.git.fork_point("origin/" + target, ref)
        if target == st.br and st.children(m.source) and self.p.needs_uptodate(st.br):
            return ("%s advanced and the merge method needs an up-to-date source" % st.br), self.git.merge_base(tip, head)
        return None

    def fetch(self, wt):
        if self.fetched:
            return True
        cmd = ["git", "-C", wt, "fetch", "origin"]
        if self.dry:
            self.rep.step("fetch", "planned", "refresh the remote-tracking refs first", commands=[cmd])
            self.fetched = True
            return True
        say("+ " + fmt_cmd(cmd))
        rc, _o, err = call(cmd)
        if rc != 0:
            self.rep.step("fetch", "failed", "git fetch failed: %s" % (first_line(err) or "exit %d" % rc), commands=[cmd])
            return False
        self.fetched = True
        self.git.worktrees(refresh=True)
        return True

    def cascade(self, st):
        if not self.git.top:
            if st.open:
                self.rep.step("cascade", "skipped", "not inside a checkout of %s: the cascade needs the local "
                              "worktrees; run stk sync from the main checkout" % self.p.repo)
            return
        if st.open and not self.fetch(self.git.top):
            return
        for path in st.paths():
            self.cascade_path(st, path)

    def manual(self, st, wt, newbase, old, top, branches):
        where = wt or "../%s_%s" % (os.path.basename(self.git.top.rstrip("/")), top)
        cmds = []
        if not wt:
            cmds.append("git worktree add %s %s" % (shlex.quote(where), top))
        cmds.append("git -C %s fetch origin" % shlex.quote(where))
        cmds.append("git -C %s rebase --update-refs --onto %s %s %s" % (shlex.quote(where), newbase, old, top))
        cmds.append("git -C %s push --force-with-lease origin %s" % (shlex.quote(where), " ".join(branches)))
        return cmds

    def cascade_path(self, st, path):
        low = None
        for i, m in enumerate(path):
            target = st.want[m.ref] if i == 0 else path[i - 1].source
            hit = self.stale(st, m, target)
            if hit:
                low = (i, target, hit[0], hit[1])
                break
        if low is None:
            return
        i, target, why, old = low
        rng = path[i:]
        top = rng[-1]
        names = [m.source for m in rng]
        newbase = self.tip(target)[0]
        refs = " ".join("%s%s" % (self.p.sigil, m.ref) for m in rng)
        msg = "%s%s: %s; rebase %s onto %s" % (self.p.sigil, rng[0].ref, why, refs, newbase)
        trees = self.git.worktrees()
        wt = trees.get(top.source)
        if not old:
            self.rep.step("cascade", "skipped", msg + ": the old base is unknown locally; run git fetch origin "
                          "and rebase by hand", ref=top.ref, commands=self.manual(st, wt, newbase, "<old-base>", top.source, names))
            return
        cmds = self.manual(st, wt, newbase, old, top.source, names)
        human = [m for m in rng if not labelled(m, self.opts)]
        if human:
            self.rep.step("cascade", "skipped", msg + ": %s not agent-labelled; label them (or run the commands "
                          "yourself)" % ", ".join("%s%s" % (self.p.sigil, m.ref) for m in human), ref=top.ref,
                          commands=[fmt_cmd(self.p.cmd_label(m.ref)) for m in human] + cmds)
            return
        missing = [b for b in names if not self.git.local(b)]
        if missing:
            self.rep.step("cascade", "skipped", msg + ": no local branch %s; create it from origin first"
                          % ", ".join(missing), ref=top.ref,
                          commands=["git branch %s origin/%s" % (b, b) for b in missing] + cmds)
            return
        drift = [b for b in names if self.git.remote(b) and self.git.local(b) != self.git.remote(b)]
        if drift:
            self.rep.step("cascade", "skipped", msg + ": local %s differs from origin; push or pull it first, "
                          "then re-run" % ", ".join(drift), ref=top.ref, commands=cmds)
            return
        if not wt:
            self.rep.step("cascade", "skipped", msg + ": no worktree has %s checked out; add one and run the "
                          "commands, or re-run stk sync" % top.source, ref=top.ref, commands=cmds)
            return
        dirty = self.git.unclean(wt)
        if dirty:
            self.rep.step("cascade", "skipped", msg + ": worktree %s is not clean: %s" % (wt, dirty),
                          ref=top.ref, commands=cmds)
            return
        others = [(b, trees[b]) for b in names[:-1] if trees.get(b) and trees[b] != wt]
        for b, owt in others:
            reason = self.git.unclean(owt)
            if reason:
                self.rep.step("cascade", "skipped", msg + ": %s is checked out in %s, which is not clean: %s"
                              % (b, owt, reason), ref=top.ref, commands=cmds)
                return
        before = dict((b, self.git.local(b)) for b in names)
        detach = [["git", "-C", owt, "switch", "--detach"] for _b, owt in others]
        attach = [["git", "-C", owt, "switch", b] for b, owt in others]
        rebase = ["git", "-C", wt, "rebase", "--update-refs", "--onto", newbase, old, top.source]
        if self.dry:
            self.rep.step("cascade", "planned", msg, ref=top.ref,
                          commands=detach + [rebase] + attach)
            for b in names:
                self.moved[b] = before[b]
            self.push(st, rng, wt, names)
            return
        ran = []
        say("[%s%s] %s" % (self.p.sigil, top.ref, msg))
        for cmd in detach:
            say("+ " + fmt_cmd(cmd))
            rc, _o, err = call(cmd)
            ran.append(cmd)
            if rc != 0:
                self.reattach(attach, ran)
                self.rep.step("cascade", "failed", msg + ": %s failed: %s" % (fmt_cmd(cmd), first_line(err)),
                              ref=top.ref, commands=cmds, ran=ran)
                return
        say("+ " + fmt_cmd(rebase))
        rc, rout, err = call(rebase, env=REBASE_ENV)
        ran.append(rebase)
        if rc != 0:
            why_c = [x.strip() for x in (rout + "\n" + err).splitlines() if x.startswith("CONFLICT") or "could not apply" in x]
            abort = ["git", "-C", wt, "rebase", "--abort"]
            say("+ " + fmt_cmd(abort))
            call(abort)
            ran.append(abort)
            self.reattach(attach, ran)
            self.rep.step("cascade", "conflict", msg + ": %s; aborted, every worktree is as it was. Run the "
                          "commands below by hand, resolve, `git rebase --continue`, then push (or ask the author)"
                          % ("; ".join(why_c) or first_line(err) or "exit %d" % rc), ref=top.ref, commands=cmds, ran=ran)
            return
        self.reattach(attach, ran)
        after = dict((b, self.git.local(b)) for b in names)
        stuck = [b for b in names if after[b] == before[b]]
        for b in names:
            if after[b] != before[b]:
                self.moved[b] = before[b]
        if stuck:
            self.rep.step("cascade", "failed", msg + ": %s did not move (git left it out of --update-refs); "
                          "nothing was pushed, rebase it by hand" % ", ".join(stuck), ref=top.ref, commands=cmds, ran=ran)
            return
        self.rep.step("cascade", "ran", msg, ref=top.ref, ran=ran)
        self.push(st, rng, wt, names)

    def reattach(self, attach, ran):
        for cmd in attach:
            say("+ " + fmt_cmd(cmd))
            rc, _o, err = call(cmd)
            ran.append(cmd)
            if rc != 0:
                self.rep.step("cascade", "failed", "%s failed: %s; re-attach that worktree by hand"
                              % (fmt_cmd(cmd), first_line(err)), commands=[cmd])

    def push(self, st, rng, wt, names):
        branches = [m.source for m in rng if m.source in self.moved and labelled(m, self.opts)]
        if not branches:
            return
        cmd = ["git", "-C", wt, "push", "--force-with-lease", "origin"] + branches
        refs = ", ".join("%s%s" % (self.p.sigil, m.ref) for m in rng)
        if self.opts.get("no_push") or not setting("push"):
            self.rep.step("push", "todo", "rebased locally, not pushed (%s); push them when ready"
                          % ("--no-push" if self.opts.get("no_push") else "stack.push = false"), ref=rng[-1].ref,
                          commands=[cmd])
            return
        if self.dry:
            self.rep.step("push", "planned", "push the rebased %s" % refs, ref=rng[-1].ref, commands=[cmd])
            return
        say("+ " + fmt_cmd(cmd))
        rc, _o, err = call(cmd)
        if rc != 0:
            self.rep.step("push", "failed", "the lease was rejected or the push failed (%s): someone pushed one of "
                          "these branches; git fetch origin, look at the new commits, then re-run"
                          % (first_line(err) or "exit %d" % rc), ref=rng[-1].ref, commands=[cmd])
            return
        self.rep.step("push", "ran", "pushed the rebased %s" % refs, ref=rng[-1].ref, ran=[cmd])

    # 4 -- leaf refresh
    def leaves(self, st):
        repo_dir = os.path.basename((self.git.top or self.p.repo).rstrip("/"))
        trees = self.git.worktrees()
        need = self.p.needs_uptodate(st.br)
        for m in st.leaves():
            if m.source in self.moved:
                continue
            m.target = st.want[m.ref]
            where = trees.get(m.source) or "../%s_%s" % (repo_dir, m.source)
            local = ["git -C %s fetch origin" % shlex.quote(where),
                     "git -C %s rebase origin/%s" % (shlex.quote(where), m.target),
                     "git -C %s push --force-with-lease origin %s" % (shlex.quote(where), m.source)]
            if m.conflict:
                self.rep.step("refresh", "conflict", "conflicts with %s; parts that conflict share files: chain them "
                              "(rebase this part onto the other one and retarget it), or rebase locally"
                              % m.target, ref=m.ref, commands=local)
                continue
            behind = self.p.refresh_behind(m)
            if not behind and m.status not in ("need_rebase", "BEHIND"):
                continue
            if not need:
                self.rep.step("refresh", "info", "%s commit(s) behind %s; the merge method does not need an "
                              "up-to-date source, nothing to do" % (behind or "some", m.target), ref=m.ref)
                continue
            if setting("leaf_refresh") == "never":
                self.rep.step("refresh", "todo", "%s commit(s) behind %s and the merge needs an up-to-date source "
                              "(stack.leaf_refresh = never): refresh it yourself" % (behind or "some", m.target),
                              ref=m.ref, commands=[self.p.cmd_refresh(m, self.opts.get("skip_ci"))])
                continue
            cmd = self.p.cmd_refresh(m, self.opts.get("skip_ci"))
            if not labelled(m, self.opts):
                self.rep.step("refresh", "skipped", "not agent-labelled; %s commit(s) behind %s" % (behind or "some", m.target),
                              ref=m.ref, commands=[self.p.cmd_label(m.ref), cmd])
                continue
            if self.refreshed >= 1:
                self.rep.step("refresh", "todo", "%s commit(s) behind %s; one leaf refresh per run (CI cost): "
                              "re-run stk sync after the previous one's pipeline" % (behind or "some", m.target), ref=m.ref,
                              commands=[cmd])
                continue
            self.refreshed += 1
            ok = self.run_cmd("refresh", m.ref, "%s commit(s) behind %s; server-side rebase" % (behind or "some", m.target), cmd)
            if ok and not self.dry:
                self.rep.step("refresh", "todo", "rebased server-side; refresh the local worktree (never reset --hard)",
                              ref=m.ref, commands=["git -C %s pull --rebase origin %s" % (shlex.quote(where), m.source)])

    # 5 -- main ready
    def ready(self, st):
        main = st.main
        if main is None or main.state != "open" or not main.draft:
            return
        if st.open or st.forks or not st.merged:
            return
        if not labelled(main, self.opts):
            self.rep.step("ready", "skipped", "every part merged, but the main %s is not agent-labelled" % self.p.kind,
                          ref=main.ref, commands=[self.p.cmd_label(main.ref), self.p.cmd_ready(main)])
            return
        self.run_cmd("ready", main.ref, "every part merged: mark the main %s ready" % self.p.kind, self.p.cmd_ready(main))

    def all(self, st):
        for m in st.forks:
            self.rep.step("fork", "skipped", "cross-repository (fork) %s: fork %ss are never stacked; handle it in the "
                          "web UI" % (self.p.kind, self.p.kind), ref=m.ref)
        self.retarget(st)
        self.cascade(st)
        self.leaves(st)
        self.ready(st)


# ---------------------------------------------------------------------------------- verbs
def cmd_plan(p, a, opts, git):
    stacks, loose = load(p, a)
    rep = Report("plan", p, a)
    rep.data["stacks"] = [topology(st, git, a.with_main) for st in stacks]
    sync = Sync(p, git, rep, opts, dry=True)
    for st in stacks:
        sync.all(st)
    rep.data["other"] = [{"ref": m.ref, "source": m.source, "target": m.target,
                          "note": "not a stack (no <branch>-sub-NN- parts)"} for m in loose]
    if not stacks and not loose:
        rep.data["notes"] = ["nothing selected"]
    rep.data["sync_would_run"] = rep.steps
    rep.data["exit"] = rep.exit_code()
    return rep.data


def cmd_status(p, a, opts, git):
    stacks, loose = load(p, a)
    rep = Report("status", p, a)
    rows, cleanup = [], []
    for st in stacks:
        topo = topology(st, git, True)
        for r in topo["parts"] + ([topo["main_row"]] if topo.get("main_row") else []):
            r["stack"] = st.br
            if r["state"] in ("open", "draft"):
                local, remote = git.local(r["source"]), git.remote(r["source"])
                r["local"] = ("same as origin" if local and local == remote else
                              "differs from origin" if local and remote else "no local branch" if not local else "not on origin")
            rows.append(r)
            path = r.get("worktree")
            if r["state"] == "merged" and path and path != git.top:
                cleanup.append({"ref": r["ref"], "branch": r["source"], "path": path,
                                "command": "git worktree remove %s" % shlex.quote(path)})
    rep.data["rows"] = rows
    rep.data["cleanup"] = cleanup
    rep.data["other"] = [{"ref": m.ref, "source": m.source, "target": m.target} for m in loose]
    bad = cleanup or any(r.get("conflicts") for r in rows)
    rep.data["exit"] = EXIT_ACTION if bad else EXIT_OK
    return rep.data


def finding(severity, key, message, fix=None):
    f = {"severity": severity, "key": key, "message": message}
    if fix:
        f["fix"] = fix
    return f


def gitlab_check(p, a):
    f, out = p.facts(), []
    api = "glab api -X PUT projects/%s" % p.pid
    if f["merge_method"] == "merge":
        out.append(finding("ok", "merge_method", "merge: chains need no rebase after a merge and fan-in leaves need "
                           "no refresh; stk sync only retargets (plus the squash cascade below)"))
    else:
        out.append(finding("info", "merge_method", "%s: the source must be up to date, so after every merge stk sync "
                           "rebases the chains and refreshes one fan-in leaf per run" % f["merge_method"]))
    if f["squash_option"] in ("always", "default_on"):
        out.append(finding("info", "squash_option", "%s: a squashed part leaves its pre-squash commits in its "
                           "dependents; stk sync cascades them away after each merge" % f["squash_option"]))
    else:
        out.append(finding("ok", "squash_option", "%s: parts merge with their commits; dependents need only a retarget "
                           "unless the merge method rebases" % f["squash_option"]))
    if f["remove_source_branch"]:
        out.append(finding("warn", "remove_source_branch_after_merge", "on: new MRs default to deleting their source "
                           "branch, and GitLab CE then retargets the dependents of a merged part to the default "
                           "branch (stk sync repairs it, but turn the default off)",
                           "%s -f remove_source_branch_after_merge=false" % api))
    else:
        out.append(finding("ok", "remove_source_branch_after_merge", "off"))
    level = p.access_level()
    if level < 30:
        out.append(finding("fail", "access", "access level %d: Developer (30) or more is needed to push sub branches "
                           "and retarget MRs" % level))
    else:
        out.append(finding("ok", "access", "access level %d" % level))
    if a.stack:
        sb = p.branch(a.stack)
        if sb.get("protected") and not sb.get("developers_can_merge") and level < 40:
            out.append(finding("warn", "protected", "ticket branch %s is protected: merging parts into it needs a "
                               "Maintainer" % a.stack))
        elif sb.get("protected"):
            out.append(finding("info", "protected", "ticket branch %s is protected; you can merge into it" % a.stack))
        else:
            out.append(finding("ok", "protected", "ticket branch %s is not protected" % a.stack))
    return out


def github_check(p, a):
    r, out = p.repo_facts(), []
    patch = "gh api -X PATCH repos/%s" % p.repo
    perm = r.get("viewerPermission") or ""
    if perm in ("WRITE", "MAINTAIN", "ADMIN"):
        out.append(finding("ok", "permission", perm))
    else:
        out.append(finding("fail", "permission", "%s: WRITE or more is needed to push sub branches and edit PRs" % (perm or "unknown")))
    if r.get("deleteBranchOnMerge"):
        out.append(finding("ok", "delete_branch_on_merge", "on: GitHub retargets a merged part's dependents onto its base"))
    else:
        out.append(finding("info", "delete_branch_on_merge", "off: dependents keep targeting a merged part's branch; "
                           "stk sync retargets them (gh pr edit -B)", "%s -F delete_branch_on_merge=true" % patch))
    allowed = [s for s, k in (("squash", "squashMergeAllowed"), ("rebase", "rebaseMergeAllowed"),
                              ("merge", "mergeCommitAllowed")) if r.get(k)]
    out.append(finding("info", "strategies", "allowed: %s%s" % (", ".join(allowed) or "none",
                       "; squash and rebase merges leave pre-merge commits in dependents, stk sync cascades them away"
                       if set(allowed) & {"squash", "rebase"} else "")))
    for branch in [p.default_branch()] + ([a.stack] if a.stack else []):
        strict, src = p.strict(branch)
        if strict:
            out.append(finding("info", "up_to_date", "%s requires up-to-date branches (%s): stk sync refreshes one "
                               "fan-in leaf per run (gh pr update-branch)" % (branch, src)))
        else:
            out.append(finding("ok", "up_to_date", "%s does not require up-to-date branches%s" % (branch, " (%s)" % src if src else "")))
    return out


def cmd_check(p, a, opts, git):
    rep = Report("check", p, a)
    findings = gitlab_check(p, a) if p.name == "gitlab" else github_check(p, a)
    if not a.fix:
        for f in findings:
            f.pop("fix", None)
    rep.data["findings"] = findings
    rep.data["exit"] = EXIT_ACTION if any(f["severity"] in ("warn", "fail") for f in findings) else EXIT_OK
    return rep.data


def cmd_sync(p, a, opts, git):
    stacks, loose = load(p, a)
    rep = Report("sync", p, a)
    sync = Sync(p, git, rep, opts, dry=False)
    for st in stacks:
        sync.all(st)
    if not stacks:
        rep.data["notes"] = ["nothing selected" if not loose else "no stack in the selection (no <branch>-sub-NN- parts)"]
    rep.data["steps"] = rep.steps
    rep.data["exit"] = rep.exit_code()
    return rep.data


# ---------------------------------------------------------------------------------- output
def emit_text(rep):
    sel = rep.get("selection") or {}
    what = {"stack": "stack %s" % sel.get("stack"), "label": "label %s" % sel.get("label"),
            "refs": "refs %s" % " ".join(str(r) for r in sel.get("refs") or [])}.get(sel.get("mode"), "")
    lines = ["stk %s — %s %s — %s" % (rep["verb"], rep["provider"], rep["repo"], what)]
    sig = "!" if rep["provider"] == "gitlab" else "#"
    for note in rep.get("notes") or []:
        lines.append("note: " + note)
    for st in rep.get("stacks") or []:
        lines.append("stack %s -> %s  main %s" % (st["branch"], st["base"],
                     "%s%s (%s)" % (sig, st["main"]["ref"], st["main"]["state"]) if st["main"] else "none"))
        for ch in st["chains"]:
            lines.append("  chain  " + " <- ".join("%s%s" % (sig, r) for r in ch))
        if st["leaves"]:
            lines.append("  leaves " + ", ".join("%s%s" % (sig, r) for r in st["leaves"]))
        for r in st["parts"]:
            extra = ""
            if r["state"] in ("open", "draft"):
                extra = "  behind %s%s%s" % ("?" if r.get("behind") is None else r["behind"],
                                             ", CONFLICTS" if r.get("conflicts") else "",
                                             ", retarget -> %s" % r["retarget"]["to"] if r.get("retarget") else "")
            lines.append("  %s%-5s %-8s %s -> %s%s%s" % (sig, r["ref"], r["state"], r["source"], r["target"], extra,
                                                       "  [%s]" % r["worktree"] if r.get("worktree") else ""))
        lines.append("  merge order: " + ", ".join(st["merge_order"]) + "; run `stk sync --stack %s` after each merge" % st["branch"])
    for r in rep.get("rows") or []:
        lines.append("%s%-5s %-8s %s -> %s%s" % (sig, r["ref"], r["state"], r["source"], r["target"],
                                                "  [%s]" % r["worktree"] if r.get("worktree") else ""))
    for c in rep.get("cleanup") or []:
        lines.append("cleanup %s%s: %s" % (sig, c["ref"], c["command"]))
    for f in rep.get("findings") or []:
        lines.append("%-5s %s: %s" % (f["severity"], f["key"], f["message"]))
        if f.get("fix"):
            lines.append("      fix: " + f["fix"])
    for s in rep.get("sync_would_run") or rep.get("steps") or []:
        who = "%s%s " % (sig, s["ref"]) if s["ref"] is not None else ""
        lines.append("%-8s %s%s: %s" % (s["status"], who, s["kind"], s["message"]))
        lines.extend("      " + c for c in s.get("commands") or [])
        lines.extend("      ran: " + c for c in s.get("ran") or [])
    print("\n".join(lines))


# ------------------------------------------------------------------------------------ main
class _Parser(argparse.ArgumentParser):
    def error(self, message):
        die("stk %s: %s\n\nRun `stk` with no arguments for the usage." % (self.prog.split()[-1], message), EXIT_ACTION)


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("refs", nargs="*", metavar="REF", help="MR/PR numbers; selects the stacks they belong to")
    common.add_argument("--stack", metavar="BR", help="ticket branch BR: its parts BR-sub-NN-* and its main MR/PR")
    common.add_argument("--with-main", action="store_true", dest="with_main", help="also list BR's own MR/PR as a row")
    common.add_argument("--label", metavar="L", help="the stacks of open MRs/PRs carrying label L (default stack.label)")
    common.add_argument("-R", "--repo", metavar="OWNER/REPO", help="default: the origin remote of this checkout")
    common.add_argument("--provider", choices=("gitlab", "github"), help="default: detected from the remote host")
    common.add_argument("--json", action="store_true", help="JSON output (default when stdout is not a TTY)")
    common.add_argument("--text", action="store_true", help="text output (default on a TTY)")
    top = _Parser(prog="stk", add_help=False)
    subs = top.add_subparsers(dest="verb")

    def sub(name, text):
        return subs.add_parser(name, parents=[common], help=text, description=text)

    common.add_argument("--include-human", action="store_true", dest="include_human",
                        help="sync: also act on MRs/PRs without an agent-* label (the guard asks); plan: preview it")
    common.add_argument("--no-push", action="store_true", dest="no_push", help="rebase locally, print the push commands")
    common.add_argument("--skip-ci", action="store_true", dest="skip_ci", help="glab mr rebase --skip-ci (GitLab leaf refresh)")
    sub("plan", "read-only: topology, merge order and the native commands stk sync would run")
    sub("status", "read-only: every member's state, worktree and cleanup lines")
    c = sub("check", "read-only: repository readiness for stacked MRs/PRs")
    c.add_argument("--fix", action="store_true", help="print the settings commands (never runs them)")
    sub("sync", "retarget, cascade-rebase and lease-push agent-labelled parts; refresh one leaf; ready the main")
    return top, list(subs.choices)


def main():
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        sys.exit(EXIT_ACTION)
    if argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        sys.exit(EXIT_OK)
    top, names = build_parser()
    if argv[0] not in names:
        die("Unknown verb %r. Verbs: %s\n\nRun `stk` with no arguments for the usage." % (argv[0], ", ".join(names)), EXIT_ACTION)
    a = top.parse_args(argv)
    opts = {k: getattr(a, k, False) for k in ("include_human", "no_push", "skip_ci")}
    if a.with_main and not a.stack:
        die("stk: --with-main needs --stack BR", EXIT_ACTION)
    for key in DEFAULTS:
        setting(key)   # fail fast on a malformed HARNESS_STACK_* / stack.* value
    git = Git()
    try:
        p = make_provider(a, git)
        verb = {"plan": cmd_plan, "status": cmd_status, "check": cmd_check, "sync": cmd_sync}[a.verb]
        rep = verb(p, a, opts, git)
    except AccessError as e:
        die("stk: %s" % e, EXIT_ACCESS)
    except CliError as e:
        die("stk: %s" % e, EXIT_ACTION)
    except KeyboardInterrupt:
        die("stk: interrupted; if a rebase was running, `git -C <worktree> rebase --abort` restores it", EXIT_ACTION)
    except BrokenPipeError:
        sys.exit(EXIT_OK)
    if a.json or not (a.text or sys.stdout.isatty()):
        print(json.dumps(rep, indent=2))
    else:
        emit_text(rep)
    sys.exit(rep["exit"])


if __name__ == "__main__":
    main()
