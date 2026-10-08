#!/usr/bin/env python3
"""Merge queue for free tiers: GitLab merge trains / GitHub merge queues, emulated — stdlib only.

Canonical invocation: `mq <verb>` (linked into ~/.local/bin by `harness apply`). It shells out
to `glab` (GitLab, CE included), `gh` (GitHub) and `git` only, and prints every native command
before it runs it, so everything it does is something you could have typed yourself.

Verbs (selection for all: `<refs...>` | `--stack BR [--with-main]` | `--label L`; nothing given
= `--label <mq.label>`):
  plan    Read-only. The ordered queue, each MR/PR's state and the exact native commands the
          train would run next. Run it before `mq run`.
  status  Read-only. Every member of the selection including merged parts: pipeline/checks,
          commits behind, next step; a merged part whose local worktree still exists shows a
          `cleanup` line (`git worktree remove …`).
  check [--fix]
          Read-only. Repository readiness: GitLab merge method, pipelines-must-succeed,
          skipped-pipeline policy, squash option, delete-source default, your access vs the
          protected default branch, merge trains, CI rules on the target branch; GitHub
          visibility, rulesets (merge queue), classic protection, auto-merge,
          delete-branch-on-merge, merge strategies, your permission, workflows. --fix prints
          the settings commands; it never runs them.
  sync [--include-human] [--skip-ci]
          Prepare; agent-runnable. Acts only on MRs/PRs carrying an agent-* label
          (WORK_TICKET_AGENT_LABEL_RE): retargets a -sub- part aimed at the default branch
          (stack mode), rebases ONLY the head of the queue server-side (`glab mr rebase`,
          `gh pr update-branch`), marks the main MR/PR ready once every part merged, and lists
          every unlabelled MR/PR with the command that labels it. Never merges, never
          force-pushes. --include-human lifts the label filter (the guard asks).
  run [--keep-branches] [--delete-blockers] [--allow-unstable]
          The train. Run it yourself in a terminal (the guard asks when an agent tries). One
          MR/PR at a time: retarget, server-side rebase, wait for the pipeline/checks on the
          new head, then arm the server's auto-merge (`glab mr merge --auto-merge --sha`,
          `gh pr merge --auto`) or merge pinned to the tested head (`--sha`,
          `--match-head-commit`). Idempotent: Ctrl-C and re-run resumes from live state, and an
          armed MR/PR merges even if mq dies. Source branches of parts without open dependents
          are deleted on merge (--keep-branches: never; --delete-blockers: chain blockers too).

Common flags: -R/--repo owner/repo (default: the origin remote), --provider gitlab|github,
--json (the default when stdout is not a TTY) / --text.
Exit codes: 0 all merged or mergeable, 1 action needed, 2 auth/access error, 3 the train stopped.

Deliberately NOT implemented: force-pushing (chained parts get the exact `git rebase --onto` +
`git push --force-with-lease` commands to run), approving, bypassing branch protection,
`glab stack`, local state files.

Env (each falls back to the harness config key in brackets, read from build/config.json via
HARNESS_CONFIG_JSON / HARNESS_HOME, then to the default):
  HARNESS_MQ_LABEL [mq.label]                     default label selection (merge-queue)
  HARNESS_MQ_POLL_SECONDS [mq.poll_seconds]       first poll interval, backs off to 60 (20)
  HARNESS_MQ_TIMEOUT_MINUTES [mq.timeout_minutes] per-MR deadline (90)
  HARNESS_MQ_ON_FAILURE [mq.on_failure]           stop|skip for label and ref selections; a
                                                  stack always stops (stop)
  HARNESS_MQ_UPDATE_METHOD [mq.update_method]     rebase|merge, GitHub update-branch (rebase)
  HARNESS_MQ_REQUIRE_CHECKS [mq.require_checks]   an MR/PR without pipeline/checks stops the
                                                  train (true; booleans: 1|true|yes)
  HARNESS_MQ_MAX_RETRIES [mq.max_retries]         rebases / re-arms per MR before it fails (3)
  HARNESS_GITLAB_HOSTS_RE, HARNESS_GITLAB_HOST [gitlab.host]  GitLab host detection; any
                                                  other host is GitHub
  WORK_TICKET_AGENT_LABEL_RE (^agent-), WORK_TICKET_LABEL (agent-worked)  sync's label gate
  GLAB, GH, GIT                                   binary overrides (tests)
  MQ_FAKE_CLOCK=1                                 virtual clock: waits advance time, no sleep (tests)
"""
import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
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


EXIT_OK, EXIT_ACTION, EXIT_ACCESS, EXIT_STOPPED = 0, 1, 2, 3
BINARIES = {"glab": os.environ.get("GLAB", "glab"), "gh": os.environ.get("GH", "gh"),
            "git": os.environ.get("GIT", "git")}
BIN_HINT = {"glab": "activate the gitlab bundle (hub.bundles) and run `harness apply`",
            "gh": "activate the github bundle (hub.bundles) and run `harness apply`",
            "git": "install git"}
CALL_TIMEOUT = 60
STUCK_REBASE_SECONDS = 600
NO_PIPELINE_POLLS = 3
MAX_BACKOFF = 60

DEFAULTS = {"label": "merge-queue", "poll_seconds": 20, "timeout_minutes": 90, "on_failure": "stop",
            "update_method": "rebase", "require_checks": True, "max_retries": 3}
CHOICES = {"on_failure": ("stop", "skip"), "update_method": ("rebase", "merge")}


# ------------------------------------------------------------------------------- settings
def setting(key):
    """HARNESS_MQ_<KEY> first, then cfg("mq.<key>"), then the default; typed like the default."""
    default = DEFAULTS[key]
    raw = os.environ.get("HARNESS_MQ_" + key.upper())
    if raw is None or raw == "":
        raw = cfg("mq." + key)
    if raw is None or raw == "":
        return default
    if isinstance(default, bool):
        return raw if isinstance(raw, bool) else str(raw).strip().lower() in ("1", "true", "yes")
    if isinstance(default, int):
        try:
            return int(raw)
        except (TypeError, ValueError):
            die("mq.%s = %r is not a whole number; set HARNESS_MQ_%s or mq.%s to one"
                % (key, raw, key.upper(), key), EXIT_ACTION)
    value = str(raw).strip()
    if key in CHOICES and value not in CHOICES[key]:
        die("mq.%s = %r; use one of: %s" % (key, value, ", ".join(CHOICES[key])), EXIT_ACTION)
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


ACCESS_RE = re.compile(r"\b401\b|unauthori[sz]ed|not logged in|authentication (failed|required)"
                       r"|auth login|bad credentials|could not resolve host|no such host"
                       r"|connection refused", re.I)


def call(argv, timeout=CALL_TIMEOUT):
    """Run a native command (argv[0] is the logical name glab|gh|git). -> (rc, stdout, stderr)."""
    real = [BINARIES.get(argv[0], argv[0])] + [str(a) for a in argv[1:]]
    try:
        p = subprocess.run(real, capture_output=True, text=True, timeout=timeout)
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


class Clock:
    """Monotonic clock; MQ_FAKE_CLOCK=1 makes sleep() advance virtual time instantly (tests)."""

    def __init__(self):
        self.fake = os.environ.get("MQ_FAKE_CLOCK") == "1"
        self.t = 0.0

    def now(self):
        return self.t if self.fake else time.monotonic()

    def sleep(self, seconds):
        if self.fake:
            self.t += seconds
        else:
            time.sleep(seconds)


CLOCK = Clock()


def stack_root(branch):
    """feat-x-sub-02-api -> feat-x ('' when the branch is not a sub branch)."""
    return branch.split("-sub-")[0] if "-sub-" in (branch or "") else ""


def sub_number(branch):
    m = re.search(r"-sub-(\d+)", branch or "")
    return int(m.group(1)) if m else 10 ** 6


def parse_ref(text):
    m = re.match(r"^[!#]?(\d+)$", text.strip())
    if not m:
        die("mq: %r is not an MR/PR number; pass numbers like 12, !12 or #12" % text, EXIT_ACTION)
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
            say("mq: HARNESS_GITLAB_HOSTS_RE %r is not a valid regex; ignored" % pattern)
    return "gitlab" if "gitlab" in host else "github"


def local_repo():
    """(toplevel or '', host, owner/repo) of the current checkout's origin."""
    rc, out, _ = call(["git", "rev-parse", "--show-toplevel"])
    top = out.strip() if rc == 0 else ""
    rc, out, _ = call(["git", "remote", "get-url", "origin"])
    host, path = parse_remote(out) if rc == 0 else (None, None)
    return top, host, path


def worktrees():
    """{branch: path} from `git worktree list --porcelain`."""
    rc, out, _ = call(["git", "worktree", "list", "--porcelain"])
    found, path = {}, None
    for line in (out if rc == 0 else "").splitlines():
        if line.startswith("worktree "):
            path = line[len("worktree "):]
        elif line.startswith("branch refs/heads/") and path:
            found[line[len("branch refs/heads/"):]] = path
    return found


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
        self.squash = bool(kw.get("squash"))
        self.conflict = bool(kw.get("conflict"))
        self.status = kw.get("status") or ""            # detailed_merge_status | mergeStateStatus
        self.behind = kw.get("behind")                  # commits behind the target (None = unknown)
        self.rebasing = bool(kw.get("rebasing"))
        self.checks = kw.get("checks") or "none"        # none pending success failed canceled skipped manual
        self.checks_sha = kw.get("checks_sha")
        self.auto_merge = bool(kw.get("auto_merge"))
        self.cross = bool(kw.get("cross"))
        self.review = kw.get("review") or ""
        self.base_sha = kw.get("base_sha")
        self.url = kw.get("url") or ""

    def summary(self):
        return {"ref": self.ref, "title": self.title, "source": self.source, "target": self.target,
                "state": self.state, "draft": self.draft, "labels": self.labels, "sha": self.sha,
                "checks": self.checks, "behind": self.behind, "merge_status": self.status,
                "auto_merge": self.auto_merge}


class Decision:
    """The next step for one MR: done | wait | act (run cmd) | stop (human) | fail (on_failure)."""

    def __init__(self, kind, step, message, cmd=None, action=None, human=None):
        self.kind, self.step, self.message = kind, step, message
        self.cmd, self.action, self.human = cmd, action, human or []

    def as_dict(self, commands=None):
        return {"kind": self.kind, "step": self.step, "message": self.message,
                "commands": commands if commands is not None
                else ([fmt_cmd(self.cmd)] if self.cmd else []) + self.human}


class Ctx:
    """Per-MR loop state plus the train's options."""

    def __init__(self, opts, mode, stack, dry, known=None, merged_parts=None, is_main=False,
                 parts_merged=False):
        self.opts, self.mode, self.stack, self.dry = opts, mode, stack, dry
        self.known = known or []                 # MRs of the selection (blocker lookup)
        self.merged_parts = merged_parts or []   # merged parts of the stack (pre-squash check)
        self.is_main, self.parts_merged = is_main, parts_merged
        self.retries, self.armed, self.merging, self.uptodate = 0, False, False, False
        self.no_pipeline, self.rebase_since = 0, None
        self.acts = {}
        self.carries_cache = {}
        self.done = set()                        # refs merged earlier in this run


GL_PIPE = {"success": "success", "failed": "failed", "canceled": "canceled", "cancelled": "canceled",
           "skipped": "skipped", "manual": "manual"}
GL_WAIT = ("checking", "unchecked", "preparing", "approvals_syncing")
GL_STOP = {"draft_status": "is a draft", "discussions_not_resolved": "has unresolved threads; resolve them",
           "not_approved": "needs approval; ask a reviewer", "requested_changes": "has requested changes",
           "blocked_status": "is blocked by another MR", "external_status_checks": "waits on external status checks",
           "status_checks_must_pass": "needs its status checks to pass", "policies_denied": "is denied by a policy",
           "locked_paths": "touches locked paths", "jira_association_missing": "needs a Jira key in title or description"}
GL_FAIL = {"broken_status": "cannot be merged (broken: source or target missing)", "not_open": "is not open"}


# ---------------------------------------------------------------------------- providers
class GitLab:
    """glab-backed provider (GitLab CE and above)."""

    name, sigil, kind = "gitlab", "!", "MR"

    def __init__(self, host, repo, explicit):
        self.host, self.repo = host, repo
        self.pid = urllib.parse.quote(repo, safe="") if explicit else ":id"
        self.rflag = ["-R", repo] if explicit else []
        self._project, self._branches = None, {}

    # --- reads
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
                "pipelines_must_succeed": bool(p.get("only_allow_merge_if_pipeline_succeeds")),
                "allow_skipped": bool(p.get("allow_merge_on_skipped_pipeline")),
                "merge_trains": bool(p.get("merge_trains_enabled")),
                "squash_option": p.get("squash_option") or "default_off",
                "remove_source_branch": bool(p.get("remove_source_branch_after_merge"))}

    def access_level(self):
        perms = self.project().get("permissions") or {}
        levels = [(perms.get(k) or {}).get("access_level") or 0 for k in ("project_access", "group_access")]
        return max(levels)

    @staticmethod
    def norm(j):
        hp = j.get("head_pipeline") or {}
        status = j.get("detailed_merge_status") or j.get("merge_status") or ""
        return MR(ref=j.get("iid"), title=j.get("title"),
                  state={"opened": "open", "locked": "open"}.get(j.get("state"), j.get("state")),
                  draft=j.get("draft") or j.get("work_in_progress"),
                  labels=[x if isinstance(x, str) else x.get("name") for x in j.get("labels") or []],
                  source=j.get("source_branch"), target=j.get("target_branch"), sha=j.get("sha"),
                  squash=j.get("squash"), conflict=j.get("has_conflicts") or status == "conflict",
                  status=status, behind=j.get("diverged_commits_count"),
                  rebasing=j.get("rebase_in_progress"),
                  checks=GL_PIPE.get(hp.get("status"), "pending") if hp else "none",
                  checks_sha=hp.get("sha"), auto_merge=j.get("merge_when_pipeline_succeeds"),
                  base_sha=(j.get("diff_refs") or {}).get("base_sha"), url=j.get("web_url"))

    def get(self, ref):
        return self.norm(self.api("projects/%s/merge_requests/%d?include_diverged_commits_count=true"
                                  "&include_rebase_in_progress=true" % (self.pid, ref)) or {})

    def _list(self, query):
        return [self.norm(j) for j in self.api("projects/%s/merge_requests?%s" % (self.pid, query)) or []]

    def list_all(self):
        return self._list("state=all&per_page=100")

    def list_label(self, label):
        return self._list("state=opened&labels=%s&per_page=100" % urllib.parse.quote(label, safe=""))

    def find_source(self, branch):
        return self._list("state=all&source_branch=%s&per_page=20" % urllib.parse.quote(branch, safe=""))

    def dependents(self, branch):
        return self._list("state=opened&target_branch=%s&per_page=100" % urllib.parse.quote(branch, safe=""))

    def branch(self, name):
        if name not in self._branches:
            try:
                self._branches[name] = self.api("projects/%s/repository/branches/%s"
                                                % (self.pid, urllib.parse.quote(name, safe=""))) or {}
            except CliError:
                self._branches[name] = {}
        return self._branches[name]

    def branch_head(self, name):
        self._branches.pop(name, None)   # always fresh: this is the target-moved check
        return (self.branch(name).get("commit") or {}).get("id")

    def carries(self, old, new):
        try:
            mb = self.api("projects/%s/repository/merge_base?refs[]=%s&refs[]=%s" % (self.pid, old, new)) or {}
        except CliError:
            return False
        return mb.get("id") == old

    # --- command builders (logical argv; printed before they run)
    def cmd_retarget(self, mr, branch):
        return ["glab", "mr", "update", str(mr.ref), "--target-branch", branch] + self.rflag

    def cmd_ready(self, mr):
        return ["glab", "mr", "update", str(mr.ref), "--ready"] + self.rflag

    def cmd_label(self, ref):
        return ["glab", "mr", "update", str(ref), "--label", gov_label()] + self.rflag

    def cmd_update(self, mr, skip_ci=False):
        return ["glab", "mr", "rebase", str(mr.ref)] + (["--skip-ci"] if skip_ci else []) + self.rflag

    def _merge_flags(self, mr, delete):
        return (["--squash"] if mr.squash else []) + (["--remove-source-branch"] if delete else [])

    def cmd_arm(self, mr, delete):
        return (["glab", "mr", "merge", str(mr.ref), "--auto-merge", "--sha", mr.sha, "--yes"]
                + self._merge_flags(mr, delete) + self.rflag)

    def cmd_merge(self, mr, delete):
        # glab >= 1.4x arms auto-merge by default; this fallback merges now, pinned to the tested head
        return (["glab", "mr", "merge", str(mr.ref), "--auto-merge=false", "--sha", mr.sha, "--yes"]
                + self._merge_flags(mr, delete) + self.rflag)

    def arms(self):
        f = self.facts()
        return f["merge_trains"] or (f["pipelines_must_succeed"] and f["merge_method"] != "merge")

    def final_cmd(self, mr, ctx, sha=None):
        probe = MR(ref=mr.ref, sha=sha or mr.sha, squash=mr.squash)
        delete = delete_branch(self, mr, ctx)
        return self.cmd_arm(probe, delete) if self.arms() else self.cmd_merge(probe, delete)

    def needs_update(self, mr):
        return not mr.conflict and not mr.rebasing and ((mr.behind or 0) > 0 or mr.status == "need_rebase")

    def notes(self):
        f = self.facts()
        out = []
        if f["merge_trains"]:
            out.append("native merge train available (merge_trains_enabled): `--auto-merge` adds each MR to it")
        if f["merge_method"] == "merge":
            out.append("merge_method = merge: a small race remains between the target-SHA check and the merge; "
                       "`mq check --fix` prints the switch to rebase_merge")
        return out

    # --- the state machine (skills/mq/references/state-machine.md, GitLab table)
    def step(self, mr, ctx):
        d = front(self, mr, ctx)
        if d:
            return d
        f, maxr = self.facts(), setting("max_retries")
        if mr.auto_merge and not (mr.status == "need_rebase" or (mr.behind or 0) > 0):
            return Decision("wait", "S5", "auto-merge armed; GitLab merges when the pipeline passes")
        if ctx.armed and not mr.auto_merge:
            ctx.armed = False
            ctx.retries += 1
            if ctx.retries > maxr:
                return Decision("fail", "S4", "auto-merge was cancelled %d times (pipeline failed or a new push); "
                                "see the pipeline, then re-run" % ctx.retries)
            say("[%s%s] S4: auto-merge was dropped (pipeline failed or a new push); re-evaluating" % (self.sigil, mr.ref))
        if ctx.merging:
            return Decision("wait", "S5", "merge requested; waiting for GitLab to finish it")
        # S2 — up to date with the target
        if mr.rebasing:
            if not ctx.dry:
                ctx.rebase_since = ctx.rebase_since if ctx.rebase_since is not None else CLOCK.now()
                if CLOCK.now() - ctx.rebase_since > STUCK_REBASE_SECONDS:
                    return Decision("stop", "S2", "server-side rebase stuck for more than 10 minutes",
                                    human=local_rebase_cmds(mr))
            return Decision("wait", "S2", "rebase in progress")
        ctx.rebase_since = None
        if mr.conflict:
            return Decision("fail", "S2", "merge conflict with %s; rebase locally and push" % mr.target,
                            human=local_rebase_cmds(mr))
        if (mr.behind or 0) > 0 or mr.status == "need_rebase":
            return self._rebase(mr, ctx, maxr, "%s commit(s) behind %s" % (mr.behind or "some", mr.target))
        if mr.status in GL_STOP:
            return Decision("stop", "S2", "%s%s %s" % (self.sigil, mr.ref, GL_STOP[mr.status]))
        if mr.status in GL_FAIL:
            return Decision("fail", "S2", "%s%s %s" % (self.sigil, mr.ref, GL_FAIL[mr.status]))
        # S3 — pipeline on this head
        arm = False
        if mr.checks == "none" or mr.checks_sha != mr.sha:
            d = no_checks(self, mr, ctx, "pipeline")
            if d:
                return d
            if f["pipelines_must_succeed"]:
                return Decision("stop", "S3", "the project requires a successful pipeline but none runs on this head "
                                "(CI rules filter on the target branch?)")
        elif mr.checks in ("failed", "canceled"):
            return Decision("fail", "S3", "pipeline %s on %s" % (mr.checks, short(mr.sha)),
                            human=["glab ci view %s" % mr.source])
        elif mr.checks == "manual":
            return Decision("stop", "S3", "pipeline waits on a manual job; run it in the GitLab UI, then re-run")
        elif mr.checks == "skipped" and not f["allow_skipped"]:
            return Decision("stop", "S3", "pipeline skipped and the project does not allow merging skipped pipelines")
        elif mr.checks == "pending":
            if not self.arms():
                return Decision("wait", "S3", "pipeline running on %s" % short(mr.sha))
            arm = True
        # S4 — arm (preferred) or merge pinned to the tested head
        delete = delete_branch(self, mr, ctx)
        if arm or f["merge_trains"]:
            return Decision("act", "S4", "arm auto-merge on %s%s" % (short(mr.sha), " (merge train)" if f["merge_trains"] else ""),
                            cmd=self.cmd_arm(mr, delete), action="arm")
        if mr.status in GL_WAIT:
            return Decision("wait", "S4", "GitLab is still checking mergeability (%s)" % mr.status)
        head = self.branch_head(mr.target)
        if head and mr.base_sha and head != mr.base_sha:
            return self._rebase(mr, ctx, maxr, "target %s moved to %s since the pipeline's base %s"
                                % (mr.target, short(head), short(mr.base_sha)))
        return Decision("act", "S4", "merge %s (pipeline %s)" % (short(mr.sha), mr.checks),
                        cmd=self.cmd_merge(mr, delete), action="merge")

    def _rebase(self, mr, ctx, maxr, why):
        if ctx.retries >= maxr:
            return Decision("fail", "S2", "%s after %d rebase(s); the target is busy — raise mq.max_retries or "
                            "re-run at a quieter time" % (why, ctx.retries))
        return Decision("act", "S2", why, cmd=self.cmd_update(mr), action="rebase")

    def on_error(self, d, mr, rc, err, ctx):
        """Map a failed write to a terminal Decision, or None to re-read and continue."""
        code = http_status(err)
        if d.action == "rebase" and (code == 403 or "forbidden" in err.lower()):
            return Decision("stop", "S2", "glab mr rebase was refused (403: no push access to %s?); rebase locally"
                            % mr.source, human=local_rebase_cmds(mr))
        if d.action in ("merge", "arm"):
            if code in (401, 403) or "forbidden" in err.lower():
                return Decision("fail", "S4", "needs Maintainer on protected %s; ask a maintainer to merge %s%s"
                                % (mr.target, self.sigil, mr.ref))
            if code in (405, 406, 409, 422) or "sha" in err.lower() or "not mergeable" in err.lower():
                return None
        return Decision("fail", d.step, "%s failed: %s" % (fmt_cmd(d.cmd[:4]), first_line(err) or "exit %d" % rc))


class GitHub:
    """gh-backed provider (github.com and GitHub Enterprise)."""

    name, sigil, kind = "github", "#", "PR"
    PR_FIELDS = ("number,title,state,isDraft,isCrossRepository,mergeable,mergeStateStatus,headRefOid,"
                 "headRefName,baseRefName,autoMergeRequest,reviewDecision,labels,mergedAt,url")
    LIST_FIELDS = "number,title,state,isDraft,isCrossRepository,headRefOid,headRefName,baseRefName,labels,url"
    REPO_FIELDS = ("defaultBranchRef,deleteBranchOnMerge,squashMergeAllowed,rebaseMergeAllowed,"
                   "mergeCommitAllowed,isPrivate,visibility,viewerPermission")   # no auto-merge field: REST below

    def __init__(self, host, repo):
        self.host, self.repo = host or "github.com", repo
        self.spec = repo if self.host == "github.com" else "%s/%s" % (self.host, repo)
        self.rflag = ["-R", self.spec]
        self.hflag = [] if self.host == "github.com" else ["--hostname", self.host]
        self._repo, self._gates = None, {}

    # --- reads
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
            # `gh repo view --json` has no auto-merge field; the REST repository object does
            rest, _ = self.api_soft("")
            self._repo["autoMergeAllowed"] = bool((rest or {}).get("allow_auto_merge"))
        return self._repo

    def default_branch(self):
        return (self.repo_facts().get("defaultBranchRef") or {}).get("name") or "main"

    def gate(self, base):
        """How PRs into BASE merge: queue (merge_queue ruleset), arm (protection + auto-merge) or merge."""
        if base not in self._gates:
            rules, _ = self.api_soft("rules/branches/%s" % urllib.parse.quote(base, safe=""))
            types = set(r.get("type") for r in (rules or []) if isinstance(r, dict))
            prot, prot_code = self.api_soft("branches/%s/protection" % urllib.parse.quote(base, safe=""))
            protected = bool(prot) or bool(types & {"required_status_checks", "pull_request", "required_deployments"})
            required = "required_status_checks" in types or bool((prot or {}).get("required_status_checks"))
            if "merge_queue" in types:
                mode = "queue"
            elif protected and self.repo_facts().get("autoMergeAllowed"):
                mode = "arm"
            else:
                mode = "merge"
            self._gates[base] = {"mode": mode, "required": required, "protected": protected,
                                 "rule_types": sorted(t for t in types if t), "protection_status": prot_code}
        return self._gates[base]

    @staticmethod
    def norm(j):
        return MR(ref=j.get("number"), title=j.get("title"),
                  state={"OPEN": "open", "MERGED": "merged", "CLOSED": "closed"}.get(j.get("state"), "open"),
                  draft=j.get("isDraft"), labels=[x.get("name") for x in j.get("labels") or []],
                  source=j.get("headRefName"), target=j.get("baseRefName"), sha=j.get("headRefOid"),
                  conflict=j.get("mergeable") == "CONFLICTING" or j.get("mergeStateStatus") == "DIRTY",
                  status=j.get("mergeStateStatus") or "", auto_merge=j.get("autoMergeRequest") is not None,
                  cross=j.get("isCrossRepository"), review=j.get("reviewDecision"), url=j.get("url"))

    def get(self, ref):
        return self.norm(read_json(["gh", "pr", "view", str(ref)] + self.rflag + ["--json", self.PR_FIELDS]) or {})

    def _list(self, extra, fields=None):
        out = read_json(["gh", "pr", "list"] + self.rflag + extra + ["--limit", "100", "--json", fields or self.LIST_FIELDS])
        return [self.norm(j) for j in out or []]

    def list_all(self):
        return self._list(["--state", "all"])

    def list_label(self, label):
        return self._list(["--state", "open", "--label", label])

    def find_source(self, branch):
        return self._list(["--state", "all", "--head", branch])

    def dependents(self, branch):
        return self._list(["--state", "open", "--base", branch], "number,headRefName,baseRefName,state")

    def behind(self, mr):
        j = self.api("compare/%s...%s" % (urllib.parse.quote(mr.target, safe=""), mr.sha)) or {}
        return int(j.get("behind_by") or 0)

    def carries(self, old, new):
        try:
            j = self.api("compare/%s...%s" % (old, new)) or {}
        except CliError:
            return False
        return j.get("status") in ("ahead", "identical")

    def checks(self, mr, required):
        """none | pending | success | failed, from `gh pr checks --json` (exit 8 = pending)."""
        argv = ["gh", "pr", "checks", str(mr.ref)] + self.rflag + ["--json", "bucket,state,name"]
        rc, out, err = call(argv + (["--required"] if required else []))
        if rc != 0 and ACCESS_RE.search(err):
            raise AccessError("%s: %s — check `gh auth status`" % (fmt_cmd(argv[:3]), first_line(err)))
        try:
            rows = json.loads(out) if out.strip() else []
        except ValueError:
            rows = None
        if not rows:
            low = err.lower()
            if "no checks reported" in low or "no required checks" in low or (rc == 0 and rows == []):
                return "none"
            raise CliError(argv, rc, err)
        buckets = set(r.get("bucket") for r in rows)
        if buckets & {"fail", "cancel"}:
            return "failed"
        if "pending" in buckets or rc == 8:
            return "pending"
        return "success"

    # --- command builders
    def strategy(self):
        r = self.repo_facts()
        if r.get("squashMergeAllowed", True):
            return "--squash"
        return "--rebase" if r.get("rebaseMergeAllowed") else "--merge"

    def cmd_retarget(self, mr, branch):
        return ["gh", "pr", "edit", str(mr.ref)] + self.rflag + ["-B", branch]

    def cmd_ready(self, mr):
        return ["gh", "pr", "ready", str(mr.ref)] + self.rflag

    def cmd_label(self, ref):
        return ["gh", "pr", "edit", str(ref)] + self.rflag + ["--add-label", gov_label()]

    def cmd_update(self, mr, skip_ci=False):
        return (["gh", "pr", "update-branch", str(mr.ref)] + self.rflag
                + (["--rebase"] if setting("update_method") == "rebase" else []))

    def cmd_queue(self, mr):
        return ["gh", "pr", "merge", str(mr.ref)] + self.rflag + ["--auto"]

    def cmd_arm(self, mr):
        return ["gh", "pr", "merge", str(mr.ref)] + self.rflag + ["--auto", self.strategy(), "--match-head-commit", mr.sha]

    def cmd_merge(self, mr, delete):
        return (["gh", "pr", "merge", str(mr.ref)] + self.rflag + [self.strategy(), "--match-head-commit", mr.sha]
                + (["--delete-branch"] if delete else []))

    def final_cmd(self, mr, ctx, sha=None):
        probe = MR(ref=mr.ref, sha=sha or mr.sha)
        mode = self.gate(mr.target)["mode"]
        if mode == "queue":
            return self.cmd_queue(probe)
        if mode == "arm":
            return self.cmd_arm(probe)
        return self.cmd_merge(probe, delete_branch(self, mr, ctx))

    def needs_update(self, mr):
        return not mr.conflict and (self.behind(mr) > 0 or mr.status == "BEHIND")

    def notes(self):
        r = self.repo_facts()
        g = self.gate(self.default_branch())
        out = []
        if g["mode"] == "queue":
            out.append("native merge queue on %s: `gh pr merge --auto` enqueues; the queue does the rest" % self.default_branch())
        elif g["mode"] == "merge":
            out.append("no server-side gate on %s%s: mq run is the queue, and mq.require_checks is the only guard "
                       "against merging an unchecked PR" % (self.default_branch(), " (private repository)" if r.get("isPrivate") else ""))
        return out

    # --- the state machine (skills/mq/references/state-machine.md, GitHub table)
    def step(self, mr, ctx):
        d = front(self, mr, ctx)
        if d:
            return d
        maxr, g = setting("max_retries"), self.gate(mr.target)
        if mr.auto_merge and mr.status != "BEHIND":
            return Decision("wait", "S5", "auto-merge armed%s; GitHub merges when the checks pass"
                            % (" (in the merge queue)" if g["mode"] == "queue" else ""))
        if ctx.armed and not mr.auto_merge:
            ctx.armed = False
            ctx.retries += 1
            if ctx.retries > maxr:
                return Decision("fail", "S4", "auto-merge was removed %d times (checks failed or a new push); "
                                "see the checks, then re-run" % ctx.retries)
            say("[#%s] S4: auto-merge / queue entry was removed; re-evaluating" % mr.ref)
        if ctx.merging:
            return Decision("wait", "S5", "merge requested; waiting for GitHub to finish it")
        if mr.review in ("REVIEW_REQUIRED", "CHANGES_REQUESTED"):
            return Decision("stop", "S4", "review decision %s; ask a reviewer" % mr.review)
        # S2 — up to date with the base
        if mr.conflict:
            return Decision("fail", "S2", "merge conflict with %s; rebase locally and push" % mr.target,
                            human=local_rebase_cmds(mr))
        if mr.status == "UNKNOWN":
            return Decision("wait", "S2", "GitHub is computing mergeability")
        behind = self.behind(mr)
        mr.behind = behind
        if behind > 0 or (mr.status == "BEHIND" and not ctx.uptodate):
            if ctx.retries >= maxr:
                return Decision("fail", "S2", "still behind %s after %d update(s); the base is busy — raise "
                                "mq.max_retries or re-run at a quieter time" % (mr.target, ctx.retries))
            return Decision("act", "S2", "%s commit(s) behind %s" % (behind or "some", mr.target),
                            cmd=self.cmd_update(mr), action="update")
        # S3 — checks on this head
        checks = self.checks(mr, g["required"])
        mr.checks = checks
        if checks == "none":
            d = no_checks(self, mr, ctx, "checks")
            if d:
                return d
        elif checks == "failed":
            return Decision("fail", "S3", "checks failed on %s" % short(mr.sha),
                            human=[fmt_cmd(["gh", "pr", "checks", str(mr.ref)] + self.rflag)])
        elif checks == "pending" and g["mode"] == "merge":
            return Decision("wait", "S3", "checks running on %s" % short(mr.sha))
        # S4 — queue, arm, or merge pinned to the tested head
        if g["mode"] == "queue":
            return Decision("act", "S4", "enqueue in the native merge queue", cmd=self.cmd_queue(mr), action="arm")
        if g["mode"] == "arm":
            return Decision("act", "S4", "arm auto-merge on %s" % short(mr.sha), cmd=self.cmd_arm(mr), action="arm")
        if mr.status == "UNSTABLE" and not ctx.opts.get("allow_unstable"):
            return Decision("stop", "S4", "non-required checks are failing (UNSTABLE); fix them or re-run with --allow-unstable")
        if mr.status == "BLOCKED":
            return Decision("stop", "S4", "blocked by repository rules (BLOCKED); see the PR's merge box")
        return Decision("act", "S4", "merge %s (checks %s)" % (short(mr.sha), checks),
                        cmd=self.cmd_merge(mr, delete_branch(self, mr, ctx)), action="merge")

    def on_error(self, d, mr, rc, err, ctx):
        low = err.lower()
        if d.action == "update" and "already up to date" in low:
            ctx.uptodate = True
            return None
        if d.action in ("merge", "arm"):
            if http_status(err) in (401, 403) or "must have" in low or "permission" in low:
                return Decision("fail", "S4", "no permission to merge into %s; ask a maintainer to merge #%s" % (mr.target, mr.ref))
            if ("head branch was modified" in low or "does not match" in low or "not mergeable" in low
                    or http_status(err) in (405, 409)):
                return None
        return Decision("fail", d.step, "%s failed: %s" % (fmt_cmd(d.cmd[:4]), first_line(err) or "exit %d" % rc))


# ------------------------------------------------------------------- shared state machine
def short(sha):
    return (sha or "")[:8] or "?"


def local_rebase_cmds(mr):
    return ["git fetch origin && git rebase origin/%s %s && git push --force-with-lease origin %s"
            % (mr.target, mr.source, mr.source)]


def rebase_onto_cmds(p, mr, blocker, branch):
    cmds = ["git fetch origin && git rebase --onto origin/%s %s %s && git push --force-with-lease origin %s"
            % (branch, blocker.sha, mr.source, mr.source)]
    if mr.target != branch:
        cmds.append(fmt_cmd(p.cmd_retarget(mr, branch)))
    return cmds


def find_blocker(p, mr, ctx):
    """The MR whose source branch this one targets (a chain), or None."""
    if "-sub-" not in mr.target:
        return None
    for m in ctx.known:
        if m.source == mr.target and m.ref != mr.ref:
            return MR(ref=m.ref, source=m.source, target=m.target, sha=m.sha, state="merged") if m.ref in ctx.done else m
    for m in p.find_source(mr.target):
        if m.state != "closed":
            return m
    return None


def front(p, mr, ctx):
    """S0 (load) and S1 (target/base) — identical on both providers."""
    if mr.state == "merged":
        return Decision("done", "S0", "merged")
    if mr.state == "closed":
        return Decision("fail", "S0", "closed without merging")
    if mr.cross:
        return Decision("stop", "S0", "cross-repository (fork) %s: fork PRs are never stacked; merge it in the web UI" % p.kind)
    if mr.draft:
        if ctx.is_main and ctx.parts_merged:
            return Decision("stop", "S0", "every part merged: mark the main %s ready (`mq sync` does it for an "
                            "agent-labelled %s)" % (p.kind, p.kind), human=[fmt_cmd(p.cmd_ready(mr))])
        if ctx.is_main:
            return Decision("wait", "S0", "the main %s stays a draft until every part merged; then `mq sync` "
                            "marks it ready" % p.kind)
        return Decision("stop", "S0", "draft; finish it, then mark it ready", human=[fmt_cmd(p.cmd_ready(mr))])
    branch = ctx.stack or stack_root(mr.source)
    default = p.default_branch()
    if "-sub-" in mr.source and mr.target == default and branch and branch != default:
        cmd = p.cmd_retarget(mr, branch)
        if ctx.mode == "stack":
            return Decision("act", "S1", "sub part targets the default branch %s (auto-retarget misfire after a "
                            "branch delete?); retarget to %s" % (default, branch), cmd=cmd, action="retarget")
        return Decision("stop", "S1", "sub part targets the default branch %s instead of %s" % (default, branch),
                        human=[fmt_cmd(cmd)])
    blocker = find_blocker(p, mr, ctx)
    if blocker is not None:
        if blocker.state == "open":
            return Decision("stop", "S1", "chained on %s%s (%s), which is still open; it merges first, then this part "
                            "needs a rebase onto %s" % (p.sigil, blocker.ref, blocker.source, branch or blocker.target))
        return Decision("stop", "S1", "chained on %s%s, which merged: drop its pre-squash commits and retarget"
                        % (p.sigil, blocker.ref), human=rebase_onto_cmds(p, mr, blocker, branch or default))
    for y in ctx.merged_parts:
        if y.ref == mr.ref or not y.sha or not mr.sha:
            continue
        key = (y.sha, mr.sha)
        if key not in ctx.carries_cache:
            ctx.carries_cache[key] = p.carries(y.sha, mr.sha)
        if ctx.carries_cache[key]:
            return Decision("stop", "S1", "carries the pre-squash commits of merged %s%s; rebase them away"
                            % (p.sigil, y.ref), human=rebase_onto_cmds(p, mr, y, branch or mr.target))
    return None


def no_checks(p, mr, ctx, what):
    """S3 without a pipeline/checks on this head: wait a few polls, then stop if required."""
    if not ctx.dry:
        ctx.no_pipeline += 1
        if ctx.no_pipeline <= NO_PIPELINE_POLLS:
            return Decision("wait", "S3", "no %s on %s yet" % (what, short(mr.sha)))
    elif setting("require_checks"):
        return Decision("wait", "S3", "no %s on %s yet; the train waits %d polls, then stops (mq.require_checks)"
                        % (what, short(mr.sha), NO_PIPELINE_POLLS))
    if setting("require_checks"):
        hint = " (CI rules filter on the target branch?)" if p.name == "gitlab" else ""
        return Decision("stop", "S3", "no %s on this head%s; mq.require_checks is on — fix CI or set "
                        "HARNESS_MQ_REQUIRE_CHECKS=false" % (what, hint))
    return None


def delete_branch(p, mr, ctx):
    """Delete the source on merge: parts without open dependents; blockers only with --delete-blockers."""
    if ctx.opts.get("keep_branches"):
        return False
    if any(m.ref != mr.ref for m in p.dependents(mr.source)):
        return bool(ctx.opts.get("delete_blockers"))
    return True


# ----------------------------------------------------------------------------- selection
class Selection:
    def __init__(self, mode, queue, stack=None, label=None, main=None, merged_parts=None, members=None):
        self.mode, self.queue, self.stack, self.label = mode, queue, stack, label
        self.main, self.merged_parts = main, merged_parts or []
        self.members = members or list(queue)

    def describe(self):
        return {"mode": self.mode, "stack": self.stack, "label": self.label,
                "refs": [m.ref for m in self.queue] if self.mode == "refs" else []}


def select(p, a):
    """Queue order: explicit refs as given; a stack by -sub-NN (main last with --with-main); a label by number."""
    if a.refs:
        if a.stack or a.label:
            die("mq: pass refs, --stack or --label, not several", EXIT_ACTION)
        return Selection("refs", [MR(ref=parse_ref(r)) for r in a.refs])
    if a.stack:
        if a.label:
            die("mq: pass --stack or --label, not both", EXIT_ACTION)
        br = a.stack
        members = [m for m in p.list_all() if (m.source == br or m.source.startswith(br + "-sub-")) and m.state != "closed"]
        parts = sorted([m for m in members if m.source != br], key=lambda m: (sub_number(m.source), m.ref))
        mains = sorted([m for m in members if m.source == br], key=lambda m: (m.state != "open", -m.ref))
        main = mains[0] if mains else None
        queue = [m for m in parts if m.state == "open"]
        if a.with_main and main is not None and main.state == "open":
            queue.append(main)
        return Selection("stack", queue, stack=br, main=main, members=parts + ([main] if main else []),
                         merged_parts=[m for m in parts if m.state == "merged"])
    label = a.label or setting("label")
    return Selection("label", sorted(p.list_label(label), key=lambda m: m.ref), label=label)


def ctx_for(p, sel, opts, mr, dry, done_refs=()):
    is_main = sel.main is not None and mr.ref == sel.main.ref
    parts = [m for m in sel.members if sel.main is None or m.ref != sel.main.ref]
    parts_merged = bool(parts) and all(m.state == "merged" or m.ref in done_refs for m in parts)
    ctx = Ctx(opts, sel.mode, sel.stack, dry, known=sel.members, merged_parts=sel.merged_parts,
              is_main=is_main, parts_merged=parts_merged)
    ctx.done = set(done_refs)
    return ctx


def make_provider(a):
    top, host, path = local_repo()
    repo = a.repo or path
    if not repo:
        die("mq: no origin remote here and no -R owner/repo; run it inside a checkout or pass -R", EXIT_ACCESS)
    provider = a.provider or detect_provider(host or "github.com")
    if provider == "gitlab":
        return GitLab(host, repo, explicit=bool(a.repo)), top
    return GitHub(host if host and detect_provider(host) == "github" and not a.repo else "github.com", repo), top


# ---------------------------------------------------------------------------------- verbs
def base_report(verb, p, sel=None):
    rep = {"verb": verb, "provider": p.name, "repo": p.repo}
    if sel is not None:
        rep["selection"] = sel.describe()
    return rep


def preview(p, mr, ctx):
    """Next decision plus the commands the train would run from here (plan/status)."""
    d = p.step(mr, ctx)
    if d.kind == "done" or (d.kind == "wait" and d.step == "S5"):
        return d.as_dict([])
    if d.kind in ("stop", "fail"):
        return d.as_dict()
    cmds = [fmt_cmd(d.cmd)] if d.kind == "act" else []
    if d.action not in ("arm", "merge"):
        sha = "<new-head>" if d.action in ("rebase", "update") else None
        cmds.append(fmt_cmd(p.final_cmd(mr, ctx, sha)))
    return d.as_dict(cmds)


def cmd_plan(p, a, opts):
    sel = select(p, a)
    rep = base_report("plan", p, sel)
    rep["notes"] = p.notes()
    rows, worst = [], EXIT_OK
    for i, ref in enumerate(m.ref for m in sel.queue):
        mr = p.get(ref)
        nxt = preview(p, mr, ctx_for(p, sel, opts, mr, dry=True, done_refs=[m.ref for m in sel.queue[:i]]))
        if i > 0 and nxt["kind"] not in ("stop", "fail", "done"):
            nxt["message"] += " (re-evaluated when it reaches the head of the queue)"
        if nxt["kind"] in ("stop", "fail"):
            worst = EXIT_ACTION
        row = mr.summary()
        row["next"] = nxt
        rows.append(row)
    rep["queue"] = rows
    if not rows:
        rep["notes"].append("nothing selected (%s)" % describe_selection(sel))
    rep["exit"] = worst
    return rep


def describe_selection(sel):
    if sel.mode == "stack":
        return "stack %s" % sel.stack
    if sel.mode == "label":
        return "label %s" % sel.label
    return "refs " + " ".join(str(m.ref) for m in sel.queue)


def cmd_status(p, a, opts, top):
    sel = select(p, a)
    rep = base_report("status", p, sel)
    trees = worktrees()
    rows, cleanup, worst = [], [], EXIT_OK
    members = sel.members if sel.mode == "stack" else sel.queue
    for m in members:
        mr = p.get(m.ref) if m.state == "open" else m
        if mr.state == "open":
            nxt = preview(p, mr, ctx_for(p, sel, opts, mr, dry=True))
            if nxt["kind"] in ("stop", "fail"):
                worst = EXIT_ACTION
        else:
            nxt = {"kind": "done" if mr.state == "merged" else "fail", "step": "S0", "message": mr.state, "commands": []}
        row = mr.summary()
        row["next"] = nxt
        rows.append(row)
        path = trees.get(mr.source)
        if mr.state in ("merged", "closed") and path and path != top:
            cleanup.append({"ref": mr.ref, "branch": mr.source, "path": path,
                            "command": "git worktree remove %s" % shlex.quote(path)})
    rep["rows"] = rows
    rep["cleanup"] = cleanup
    if cleanup:
        worst = EXIT_ACTION
    rep["exit"] = worst
    return rep


def cmd_check(p, a, opts):
    rep = base_report("check", p)
    findings = gitlab_check(p, a) if p.name == "gitlab" else github_check(p, a)
    if not a.fix:
        for f in findings:
            f.pop("fix", None)
    rep["findings"] = findings
    rep["exit"] = EXIT_ACTION if any(f["severity"] in ("warn", "fail") for f in findings) else EXIT_OK
    return rep


def finding(severity, key, message, fix=None):
    f = {"severity": severity, "key": key, "message": message}
    if fix:
        f["fix"] = fix
    return f


def gitlab_check(p, a):
    f, out = p.facts(), []
    api = "glab api -X PUT projects/%s" % p.pid
    if f["merge_method"] in ("ff", "rebase_merge"):
        out.append(finding("ok", "merge_method", "%s: GitLab itself refuses a stale source (need_rebase)" % f["merge_method"]))
    else:
        out.append(finding("warn", "merge_method", "merge: a small race remains between the target-SHA check and "
                           "the merge; semi-linear (rebase_merge) or ff closes it", "%s -f merge_method=rebase_merge" % api))
    if f["pipelines_must_succeed"]:
        out.append(finding("ok", "pipelines_must_succeed", "on: auto-merge waits for the pipeline server-side"))
    else:
        out.append(finding("warn", "pipelines_must_succeed", "off: mq waits client-side and merges itself; turn it on "
                           "so a killed mq run loses nothing", "%s -f only_allow_merge_if_pipeline_succeeds=true" % api))
    out.append(finding("info", "allow_merge_on_skipped_pipeline", "%s: a skipped pipeline %s"
                       % ("on" if f["allow_skipped"] else "off", "counts as passed" if f["allow_skipped"] else "stops the train")))
    if f["squash_option"] == "never":
        out.append(finding("warn", "squash_option", "never: stacked parts are squash-merged by convention",
                           "%s -f squash_option=default_on" % api))
    else:
        out.append(finding("ok", "squash_option", f["squash_option"]))
    if f["remove_source_branch"]:
        out.append(finding("warn", "remove_source_branch_after_merge", "on: new MRs default to deleting their source, which "
                           "makes GitLab CE retarget chained parts to the default branch; mq deletes branches itself",
                           "%s -f remove_source_branch_after_merge=false" % api))
    else:
        out.append(finding("ok", "remove_source_branch_after_merge", "off"))
    level = p.access_level()
    default = p.default_branch()
    br = p.branch(default)
    if level < 30:
        out.append(finding("fail", "access", "access level %d: Developer (30) or more is needed to rebase and merge parts" % level))
    elif br.get("protected") and not br.get("developers_can_merge") and level < 40:
        out.append(finding("warn", "access", "Developer: parts into an unprotected ticket branch merge; the main MR into "
                           "protected %s needs a Maintainer" % default))
    else:
        out.append(finding("ok", "access", "access level %d" % level))
    if a.stack:
        sb = p.branch(a.stack)
        if sb.get("protected") and not sb.get("developers_can_merge") and level < 40:
            out.append(finding("warn", "access", "ticket branch %s is protected: parts need a Maintainer" % a.stack))
    if f["merge_trains"]:
        out.append(finding("info", "merge_trains", "native merge train available: --auto-merge adds each MR to it"))
    rc, ci, _ = call(["git", "show", "HEAD:.gitlab-ci.yml"])
    if rc != 0:
        out.append(finding("warn", "ci", "no .gitlab-ci.yml at HEAD: parts get no pipeline; add CI or set mq.require_checks = false"))
    elif "merge_request_event" not in ci:
        out.append(finding("warn", "ci", "CI has no merge_request_event rule: MR pipelines may not run on rebased heads"))
    elif re.search(r"CI_MERGE_REQUEST_TARGET_BRANCH_NAME|CI_COMMIT_BRANCH\s*==\s*\$CI_DEFAULT_BRANCH", ci):
        out.append(finding("info", "ci", "CI rules filter on the target branch: parts target the ticket branch; check they still get a pipeline"))
    else:
        out.append(finding("ok", "ci", "MR pipelines configured"))
    return out


def github_check(p, a):
    r, out = p.repo_facts(), []
    default = p.default_branch()
    g = p.gate(default)
    patch = "gh api -X PATCH repos/%s" % p.repo
    perm = r.get("viewerPermission") or ""
    if perm in ("WRITE", "MAINTAIN", "ADMIN"):
        out.append(finding("ok", "permission", perm))
    else:
        out.append(finding("fail", "permission", "%s: WRITE or more is needed to update and merge PRs" % (perm or "unknown")))
    vis = (r.get("visibility") or ("PRIVATE" if r.get("isPrivate") else "PUBLIC")).lower()
    if g["mode"] == "queue":
        out.append(finding("ok", "merge_queue", "ruleset on %s requires a merge queue: mq enqueues with gh pr merge --auto" % default))
    elif g["protected"]:
        out.append(finding("ok", "protection", "%s is protected (%s)" % (default, ", ".join(g["rule_types"]) or "classic protection")))
    elif r.get("isPrivate") and g["protection_status"] == 403:
        out.append(finding("info", "protection", "private repository on a Free plan: no rulesets, protection, auto-merge "
                           "or merge queue; mq run is the queue and mq.require_checks the only guard"))
    else:
        out.append(finding("warn", "protection", "%s (%s) has no ruleset or protection: nothing server-side stops an "
                           "unchecked merge; add a ruleset with required checks" % (default, vis)))
    if g["protected"] and not r.get("autoMergeAllowed"):
        out.append(finding("warn", "auto_merge", "Allow auto-merge is off: mq waits client-side instead of arming",
                           "%s -F allow_auto_merge=true" % patch))
    elif g["protected"]:
        out.append(finding("ok", "auto_merge", "allowed"))
    if r.get("deleteBranchOnMerge"):
        out.append(finding("ok", "delete_branch_on_merge", "on: dependents retarget when a part merges"))
    else:
        out.append(finding("warn", "delete_branch_on_merge", "off: armed or queued parts keep their head branch, so "
                           "dependents keep a stale base", "%s -F delete_branch_on_merge=true" % patch))
    allowed = [s for s, k in (("squash", "squashMergeAllowed"), ("rebase", "rebaseMergeAllowed"),
                              ("merge", "mergeCommitAllowed")) if r.get(k)]
    out.append(finding("ok" if "squash" in allowed else "info", "strategies",
                       "allowed: %s; mq uses %s" % (", ".join(allowed) or "none", p.strategy()[2:])))
    wf, _ = p.api_soft("actions/workflows")
    if not (wf or {}).get("total_count"):
        out.append(finding("warn", "workflows", "no GitHub Actions workflows: PRs get no checks; add one or set mq.require_checks = false"))
    else:
        out.append(finding("ok", "workflows", "%d workflow(s)" % wf["total_count"]))
    return out


def cmd_sync(p, a, opts, top):
    sel = select(p, a)
    rep = base_report("sync", p, sel)
    agent = agent_label_re()
    trees = worktrees()
    repo_dir = os.path.basename(top.rstrip("/")) if top else os.path.basename(p.repo)
    actions, skipped, hints, live = [], [], [], {}
    head_taken = False
    for m in sel.queue:
        mr = p.get(m.ref)
        live[mr.ref] = mr.state
        if mr.state != "open":
            continue
        if sel.main is not None and mr.ref == sel.main.ref and mr.draft:
            continue   # the main MR/PR: handled after the loop (ready once every part merged)
        labelled = any(agent.search(x) for x in mr.labels)
        if not labelled and not opts.get("include_human"):
            skipped.append({"ref": mr.ref, "reason": "not agent-labelled", "command": fmt_cmd(p.cmd_label(mr.ref))})
            head_taken = True
            continue
        ctx = ctx_for(p, sel, opts, mr, dry=True, done_refs=[])
        d = front(p, mr, ctx)
        if d is not None and d.kind == "act" and d.action == "retarget":
            run_write(p, mr, d, actions)
            mr = p.get(mr.ref)
            d = front(p, mr, ctx)
        if d is not None and d.kind in ("stop", "fail"):
            hints.append({"ref": mr.ref, "message": d.message, "commands": d.human})
            head_taken = True
            continue
        if head_taken:
            continue
        head_taken = True
        if p.needs_update(mr):
            d = Decision("act", "S2", "head of the queue is behind %s" % mr.target,
                         cmd=p.cmd_update(mr, opts.get("skip_ci")), action="rebase")
            rc = run_write(p, mr, d, actions)
            if rc == 0:
                path = trees.get(mr.source) or "../%s_%s" % (repo_dir, mr.source)
                hints.append({"ref": mr.ref, "message": "rebased server-side; refresh the local worktree (never reset --hard)",
                              "commands": ["git -C %s pull --rebase origin %s" % (shlex.quote(path), mr.source)]})
        else:
            d = p.step(mr, ctx)   # dry: why the head of the queue cannot move (reads only)
            if d.kind in ("stop", "fail"):
                hints.append({"ref": mr.ref, "message": d.message, "commands": d.human})
    main = sel.main
    if main is not None and main.state == "open":
        parts = [x for x in sel.members if x.ref != main.ref]
        if parts and all(live.get(x.ref, x.state) == "merged" for x in parts):
            mm = p.get(main.ref)
            if mm.draft:
                if any(agent.search(x) for x in mm.labels) or opts.get("include_human"):
                    run_write(p, mm, Decision("act", "S0", "every part merged: main ready",
                                              cmd=p.cmd_ready(mm), action="ready"), actions)
                else:
                    skipped.append({"ref": mm.ref, "reason": "not agent-labelled", "command": fmt_cmd(p.cmd_label(mm.ref))})
    rep["actions"], rep["skipped"], rep["hints"] = actions, skipped, hints
    failed = any(x["rc"] != 0 for x in actions)
    rep["exit"] = EXIT_ACTION if (skipped or hints or failed) else EXIT_OK
    return rep


def run_write(p, mr, d, actions):
    say("[%s%s] %s: %s" % (p.sigil, mr.ref, d.step, d.message))
    say("+ " + fmt_cmd(d.cmd))
    rc, _out, err = call(d.cmd)
    if rc != 0 and isinstance(p, GitHub) and d.action in ("rebase", "update") and "already up to date" in err.lower():
        rc = 0
    actions.append({"ref": mr.ref, "command": fmt_cmd(d.cmd), "rc": rc, "error": first_line(err) if rc else ""})
    if rc != 0:
        say("  failed: %s" % (first_line(err) or "exit %d" % rc))
    return rc


def drive(p, ref, ctx, resume):
    """Run one MR through the state machine until it is merged, stops or fails."""
    deadline = CLOCK.now() + setting("timeout_minutes") * 60
    poll = max(1, setting("poll_seconds"))
    waits, last_wait, done_cmds = 0, None, []
    while True:
        mr = p.get(ref)
        d = p.step(mr, ctx)
        if d.kind in ("done", "stop", "fail"):
            return mr, d, done_cmds
        if d.kind == "act":
            n = ctx.acts.get(d.action, 0) + 1
            ctx.acts[d.action] = n
            limit = 2 if d.action == "retarget" else setting("max_retries") + 1
            if d.action in ("rebase", "update"):
                ctx.retries += 1
            elif n > limit:
                return mr, Decision("fail", d.step, "%s did not take effect after %d attempts; see the %s in the "
                                    "web UI, then re-run" % (d.action, limit, p.kind)), done_cmds
            say("[%s%s] %s: %s" % (p.sigil, ref, d.step, d.message))
            say("+ " + fmt_cmd(d.cmd))
            rc, _out, err = call(d.cmd)
            done_cmds.append(fmt_cmd(d.cmd))
            if rc != 0:
                say("  -> %s" % (first_line(err) or "exit %d" % rc))
                term = p.on_error(d, mr, rc, err, ctx)
                if term is not None:
                    return mr, term, done_cmds
            elif d.action == "arm":
                ctx.armed = True
            elif d.action == "merge":
                ctx.merging = True
            waits, last_wait = 0, None
            continue
        if CLOCK.now() >= deadline:
            return mr, Decision("fail", d.step, "timed out after %d min (%s); re-run `%s` to resume from live state"
                                % (setting("timeout_minutes"), d.message, resume)), done_cmds
        if d.message != last_wait:
            say("[%s%s] %s: %s — waiting" % (p.sigil, ref, d.step, d.message))
            last_wait = d.message
        CLOCK.sleep(min(MAX_BACKOFF, poll * (1.5 ** waits)))
        waits += 1


def cmd_run(p, a, opts):
    sel = select(p, a)
    rep = base_report("run", p, sel)
    rep["notes"] = p.notes()
    for note in rep["notes"]:
        say("note: " + note)
    on_failure = "stop" if sel.mode == "stack" else setting("on_failure")
    resume = "mq run " + resume_args(a)
    results, merged, halted, skipped_any = [], [], False, False
    for m in sel.queue:
        if halted:
            results.append({"ref": m.ref, "outcome": "not reached", "step": "", "message": "", "commands": [], "ran": []})
            continue
        ctx = ctx_for(p, sel, opts, m, dry=False, done_refs=merged)
        mr, d, ran = drive(p, m.ref, ctx, resume)
        outcome = {"done": "merged", "stop": "stopped", "fail": "failed"}[d.kind]
        if outcome == "merged":
            merged.append(m.ref)
            say("[%s%s] merged" % (p.sigil, m.ref))
        elif outcome == "stopped" or on_failure == "stop":
            halted = True
            say("[%s%s] %s at %s: %s — the train stops here" % (p.sigil, m.ref, outcome, d.step, d.message))
        else:
            outcome, skipped_any = "skipped", True
            say("[%s%s] failed at %s: %s — skipped (mq.on_failure = skip)" % (p.sigil, m.ref, d.step, d.message))
        results.append({"ref": m.ref, "source": mr.source, "target": mr.target, "outcome": outcome,
                        "step": d.step, "message": d.message, "commands": d.human, "ran": ran})
    rep["queue"] = results
    rep["exit"] = EXIT_STOPPED if halted else (EXIT_ACTION if skipped_any else EXIT_OK)
    return rep


def resume_args(a):
    if a.refs:
        return " ".join(a.refs)
    if a.stack:
        return "--stack %s%s" % (a.stack, " --with-main" if a.with_main else "")
    return "--label %s" % (a.label or setting("label"))


# ---------------------------------------------------------------------------------- output
def emit_text(rep):
    lines = ["mq %s — %s %s%s" % (rep["verb"], rep["provider"], rep["repo"],
                                  (" — " + describe_sel(rep["selection"])) if rep.get("selection") else "")]
    sig = "!" if rep["provider"] == "gitlab" else "#"
    for note in rep.get("notes") or []:
        lines.append("note: " + note)
    for row in rep.get("queue") or rep.get("rows") or []:
        if "next" in row:
            n = row["next"]
            lines.append("%s%-5s %s -> %s  [%s, checks %s, behind %s]  %s %s: %s" % (
                sig, row["ref"], row["source"], row["target"], "draft" if row["draft"] else row["state"],
                row["checks"], "?" if row["behind"] is None else row["behind"], n["kind"], n["step"], n["message"]))
            lines.extend("      " + c for c in n["commands"])
        else:
            lines.append("%s%-5s %s  %s %s" % (sig, row["ref"], row["outcome"], row["step"], row["message"]))
            lines.extend("      " + c for c in row["commands"])
    for c in rep.get("cleanup") or []:
        lines.append("cleanup %s%s: %s" % (sig, c["ref"], c["command"]))
    for f in rep.get("findings") or []:
        lines.append("%-5s %s: %s" % (f["severity"], f["key"], f["message"]))
        if f.get("fix"):
            lines.append("      fix: " + f["fix"])
    for x in rep.get("actions") or []:
        lines.append("ran   %s%s: %s%s" % (sig, x["ref"], x["command"], "" if x["rc"] == 0 else "  (failed: %s)" % x["error"]))
    for x in rep.get("skipped") or []:
        lines.append("skipped %s%s: %s — %s" % (sig, x["ref"], x["reason"], x["command"]))
    for x in rep.get("hints") or []:
        lines.append("next  %s%s: %s" % (sig, x["ref"], x["message"]))
        lines.extend("      " + c for c in x["commands"])
    print("\n".join(lines))


def describe_sel(s):
    if s["mode"] == "stack":
        return "stack " + s["stack"]
    if s["mode"] == "label":
        return "label " + s["label"]
    return "refs " + " ".join(str(r) for r in s["refs"])


# ------------------------------------------------------------------------------------ main
class _Parser(argparse.ArgumentParser):
    def error(self, message):
        die("mq %s: %s\n\nRun `mq` with no arguments for the usage." % (self.prog.split()[-1], message), EXIT_ACTION)


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("refs", nargs="*", metavar="REF", help="MR/PR numbers, in queue order")
    common.add_argument("--stack", metavar="BR", help="the parts of ticket branch BR (BR-sub-NN-*), by NN")
    common.add_argument("--with-main", action="store_true", dest="with_main", help="append BR's own MR/PR (stack mode)")
    common.add_argument("--label", metavar="L", help="open MRs/PRs carrying label L, by number (default mq.label)")
    common.add_argument("-R", "--repo", metavar="OWNER/REPO", help="default: the origin remote of this checkout")
    common.add_argument("--provider", choices=("gitlab", "github"), help="default: detected from the remote host")
    common.add_argument("--json", action="store_true", help="JSON output (default when stdout is not a TTY)")
    common.add_argument("--text", action="store_true", help="text output (default on a TTY)")
    top = _Parser(prog="mq", add_help=False)
    subs = top.add_subparsers(dest="verb")

    def sub(name, text):
        return subs.add_parser(name, parents=[common], help=text, description=text)

    sub("plan", "read-only: the ordered queue and the native commands the train would run")
    sub("status", "read-only: every member's state, next step and worktree cleanup")
    c = sub("check", "read-only: repository readiness for the train")
    c.add_argument("--fix", action="store_true", help="print the settings commands (never runs them)")
    s = sub("sync", "prepare agent-labelled MRs/PRs: retarget misfires, rebase the queue head, ready the main")
    s.add_argument("--include-human", action="store_true", dest="include_human",
                   help="also act on MRs/PRs without an agent-* label (the guard asks)")
    s.add_argument("--skip-ci", action="store_true", dest="skip_ci", help="glab mr rebase --skip-ci (GitLab only)")
    r = sub("run", "the train: run it yourself in a terminal")
    r.add_argument("--keep-branches", action="store_true", dest="keep_branches", help="never delete source branches")
    r.add_argument("--delete-blockers", action="store_true", dest="delete_blockers",
                   help="also delete the branch of a part that others are chained on")
    r.add_argument("--allow-unstable", action="store_true", dest="allow_unstable",
                   help="GitHub: merge although non-required checks fail (UNSTABLE)")
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
        die("Unknown verb %r. Verbs: %s\n\nRun `mq` with no arguments for the usage." % (argv[0], ", ".join(names)), EXIT_ACTION)
    a = top.parse_args(argv)
    opts = {k: getattr(a, k, False) for k in ("keep_branches", "delete_blockers", "allow_unstable",
                                               "include_human", "skip_ci")}
    if a.with_main and not a.stack:
        die("mq: --with-main needs --stack BR", EXIT_ACTION)
    for key in DEFAULTS:
        setting(key)   # fail fast on a malformed HARNESS_MQ_* / mq.* value
    try:
        p, top_dir = make_provider(a)
        if a.verb == "plan":
            rep = cmd_plan(p, a, opts)
        elif a.verb == "status":
            rep = cmd_status(p, a, opts, top_dir)
        elif a.verb == "check":
            rep = cmd_check(p, a, opts)
        elif a.verb == "sync":
            rep = cmd_sync(p, a, opts, top_dir)
        else:
            rep = cmd_run(p, a, opts)
    except AccessError as e:
        die("mq: %s" % e, EXIT_ACCESS)
    except CliError as e:
        die("mq: %s" % e, EXIT_ACTION)
    except KeyboardInterrupt:
        die("mq: interrupted; armed MRs/PRs still merge server-side — re-run to resume from live state", EXIT_STOPPED)
    except BrokenPipeError:
        sys.exit(EXIT_OK)
    if a.json or not (a.text or sys.stdout.isatty()):
        print(json.dumps(rep, indent=2))
    else:
        emit_text(rep)
    sys.exit(rep["exit"])


if __name__ == "__main__":
    main()
