#!/usr/bin/env python3
"""Bootstrap git repositories to a standard — locally and on GitHub or GitLab — stdlib only.

Canonical invocation: `repoboot <verb>` (linked into ~/.local/bin by `harness apply`). It shells
out to `git`, `gh` (GitHub) and `glab` (GitLab) only, and prints every native command in its
plan before `apply` runs it, so everything it does is something you could have typed yourself.

The standard is three layers, later wins:
  1. the bundled baseline pack (hygiene files, MR/PR template, CI lint job, pre-commit);
  2. packs from repo_bootstrap.pack_dirs (org or personal architecture packs: files, fragments
     and their own questions), selected by the answers they `match`;
  3. the answers, kept in the repository's spec `.repo-standard.toml` (written by `answer`).

Verbs (DIR defaults to the current directory; the spec is DIR/.repo-standard.toml unless --spec):
  questions [--round N]
          Read-only. The open questions as JSON — the standard intake (scripts/questions.toml)
          plus the questions of every selected pack — with their resolved defaults and choices.
          Round 1 = identity, workflow, architecture, quality; round 2 = pack questions.
  answer KEY=VALUE... [--accept-defaults] [--infer]
          Writes answers into the spec (validated against the question's type and choices).
          --accept-defaults fills every open question that has a default; --infer fills what
          the checkout already says (name, host, owner, default branch, languages).
  plan    Read-only (GET probes only). Selected packs, uncovered architecture answers, every
          file (create / same / differs), the local git steps, the exact remote commands
          `apply` would run, and the .harness.toml draft for the human.
  render [--force]
          Writes the standard's files into DIR (missing ones; differing ones only with --force).
          In an existing repository it refuses on the default branch: render on a branch and
          deliver the change through an MR/PR.
  apply [--force]
          New repository: git init, render, initial commit, create the remote, push the default
          branch ONLY after `git ls-remote` shows the remote is empty, then settings, branch
          protection and agent-* labels. Existing repository: only the remote fix steps of
          `plan`. Never writes .harness.toml, never force-pushes, never deletes a repository.
  check [--fix]
          Read-only. Drift between DIR (files, and the remote's settings) and the standard;
          --fix adds the command that fixes each finding (it never runs them).

Common flags: --dir DIR, --spec FILE, --json (default when stdout is not a TTY) / --text.
Exit codes: 0 nothing to do or all done, 1 action needed by a human, 2 auth/access error.

Env (each falls back to the harness config key in brackets, read from build/config.json via
HARNESS_CONFIG_JSON / HARNESS_HOME, then to the default):
  HARNESS_REPO_BOOTSTRAP_PACK_DIRS [repo_bootstrap.pack_dirs]    extra pack directories (':')
  HARNESS_REPO_BOOTSTRAP_DEFAULT_VISIBILITY [.default_visibility] private|internal|public
  HARNESS_REPO_BOOTSTRAP_DEFAULT_MERGE_METHOD [.default_merge_method] squash|merge|rebase
  HARNESS_REPO_BOOTSTRAP_REQUIRED_APPROVALS [.required_approvals] default approvals (1)
  HARNESS_REPO_BOOTSTRAP_DEFAULT_LICENSE [.default_license]       none|MIT|proprietary
  HARNESS_REPO_BOOTSTRAP_GITHUB_OWNER, _GITLAB_NAMESPACE         default owner / namespace
  HARNESS_REPO_BOOTSTRAP_GITLAB_REMOVE_SOURCE_BRANCH            auto|true|false (auto: false
                                                                when the stack bundle is on)
  HARNESS_GITLAB_HOST [gitlab.host]                             the GitLab server
  WORK_TICKET_LABEL and core.agent_labels                       the agent-* labels to create
  GIT, GH, GLAB, HARNESS                                        binary overrides (tests)
  REPOBOOT_TODAY                                                YYYY-MM-DD override (tests)
"""
import argparse
import datetime
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

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
SPEC_NAME = ".repo-standard.toml"
INITIAL_SUBJECT = "Initial commit: repository standard"
CALL_TIMEOUT = 120
BINARIES = {"git": os.environ.get("GIT", "git"), "gh": os.environ.get("GH", "gh"),
            "glab": os.environ.get("GLAB", "glab"), "harness": os.environ.get("HARNESS", "harness")}
BIN_HINT = {"glab": "activate the gitlab bundle (hub.bundles) and run `harness apply`",
            "gh": "activate the github bundle (hub.bundles) and run `harness apply`",
            "git": "install git", "harness": "run the hub's bootstrap"}
DEFAULTS = {"pack_dirs": [], "default_visibility": "private", "default_merge_method": "squash",
            "required_approvals": "1", "default_license": "none", "github_owner": "",
            "gitlab_namespace": "", "gitlab_remove_source_branch": "auto"}
CHOICES = {"default_visibility": ("private", "internal", "public"),
           "default_merge_method": ("squash", "merge", "rebase"),
           "default_license": ("none", "MIT", "proprietary"),
           "gitlab_remove_source_branch": ("auto", "true", "false")}
LABEL_TEXT = {"worked": ("7057ff", "An agent may work this (harness governance: promptless writes)"),
              "created": ("0e8a16", "Created by an agent"),
              "drafted": ("fbca04", "Drafted by an agent; a human confirms it")}


# ------------------------------------------------------------------------------- errors
class AccessError(Exception):
    """Binary missing, not logged in, no access -> exit 2."""


class UserError(Exception):
    """Bad input, a refused action or a failed write -> exit 1."""


def die(msg, code=EXIT_ACTION):
    print(msg, file=sys.stderr)
    sys.exit(code)


def say(msg):
    print(msg, file=sys.stderr, flush=True)


def first_line(text):
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()
    return ""


ACCESS_RE = re.compile(r"\b401\b|unauthori[sz]ed|not logged in|authentication (failed|required)"
                       r"|auth login|bad credentials|could not resolve host|no such host"
                       r"|connection refused", re.I)


def http_status(err):
    m = re.search(r"\b(40[0-9]|42[0-9]|50[0-9])\b", err or "")
    return int(m.group(1)) if m else None


# ------------------------------------------------------------------------------- settings
def setting(key):
    default = DEFAULTS[key]
    raw = os.environ.get("HARNESS_REPO_BOOTSTRAP_" + key.upper())
    if key == "pack_dirs":
        if raw:
            return [p for p in raw.split(":") if p]
        val = cfg("repo_bootstrap.pack_dirs")
        if isinstance(val, list):
            return [str(p) for p in val if p]
        return [p for p in str(val or "").split(":") if p]
    if raw is None or raw == "":
        raw = cfg("repo_bootstrap." + key)
    if raw is None or raw == "":
        return default
    value = str(raw).strip()
    if isinstance(raw, bool):
        value = "true" if raw else "false"
    if key in CHOICES and value not in CHOICES[key]:
        raise UserError("repo_bootstrap.%s = %r; use one of: %s (HARNESS_REPO_BOOTSTRAP_%s or repo_bootstrap.%s)"
                        % (key, value, ", ".join(CHOICES[key]), key.upper(), key))
    if key == "required_approvals" and not value.isdigit():
        raise UserError("repo_bootstrap.required_approvals = %r is not a whole number" % value)
    return value


def agent_labels():
    """[(role, name)] for worked / created / drafted, from core.agent_labels (WORK_TICKET_LABEL wins for worked)."""
    conf = cfg("core.agent_labels") or {}
    if not isinstance(conf, dict):
        conf = {}
    out = []
    for role in ("worked", "created", "drafted"):
        name = conf.get(role) or "agent-" + role
        if role == "worked" and os.environ.get("WORK_TICKET_LABEL"):
            name = os.environ["WORK_TICKET_LABEL"]
        out.append((role, name))
    return out


def gitlab_host():
    return os.environ.get("HARNESS_GITLAB_HOST") or cfg("gitlab.host") or ""


def stack_enabled():
    bundles = os.environ.get("HARNESS_BUNDLES")
    if bundles is None:
        bundles = cfg("hub.bundles") or []
    if isinstance(bundles, str):
        bundles = re.split(r"[,:\s]+", bundles)
    return "stack" in bundles


def today():
    raw = os.environ.get("REPOBOOT_TODAY")
    if raw:
        return datetime.date(*[int(x) for x in raw.split("-")])
    return datetime.date.today()


# ------------------------------------------------------------------------------- TOML
def toml_loads(text, where):
    try:
        import tomllib as toml  # python >= 3.11
    except ImportError:  # pragma: no cover - python 3.9/3.10: the hub's vendored tomli
        home = os.environ.get("HARNESS_HOME") or os.path.expanduser("~/harness-hub")
        sys.path.insert(0, os.path.join(home, "lib", "harness", "_vendor"))
        try:
            import tomli as toml  # type: ignore
        except ImportError:
            raise UserError("python < 3.11 needs the hub's vendored tomli (HARNESS_HOME=%s); set HARNESS_HOME" % home)
    try:
        return toml.loads(text)
    except Exception as exc:  # TOMLDecodeError
        raise UserError("%s: %s" % (where, exc))


def toml_load(path):
    with open(path, encoding="utf-8") as fh:
        return toml_loads(fh.read(), path)


def _tq(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def _tkey(k):
    return k if re.match(r"^[A-Za-z0-9_-]+$", k) else _tq(k)


def _tval(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, list):
        return "[" + ", ".join(_tval(x) for x in v) + "]"
    return _tq(v)


def dump_spec(spec):
    lines = ["# Repository standard (repoboot). `repoboot check` measures drift against it; change it with",
             "# `repoboot answer KEY=VALUE`, then `repoboot plan` and `repoboot render` on a branch."]
    order = [s for s in SECTION_ORDER if s in spec] + sorted(s for s in spec if s not in SECTION_ORDER)
    for sec in order:
        body = spec[sec]
        if not body:
            continue
        lines.append("")
        lines.append("[%s]" % ".".join(_tkey(p) for p in sec.split(".")))
        for k in sorted(body):
            lines.append("%s = %s" % (_tkey(k), _tval(body[k])))
    return "\n".join(lines) + "\n"


SECTION_ORDER = ("repo", "workflow", "architecture", "quality")


def flatten_spec(raw):
    """TOML document -> {"section": {key: value}}; nested tables become dotted sections."""
    out = {}

    def walk(prefix, table):
        for k, v in table.items():
            if isinstance(v, dict):
                walk(prefix + [k], v)
            else:
                out.setdefault(".".join(prefix), {})[k] = v
    walk([], raw)
    out.pop("", None)
    return out


def split_id(qid):
    sec, _, key = qid.rpartition(".")
    return sec, key


def spec_get(spec, qid):
    sec, key = split_id(qid)
    return (spec.get(sec) or {}).get(key)


def spec_set(spec, qid, value):
    sec, key = split_id(qid)
    spec.setdefault(sec, {})[key] = value


# ------------------------------------------------------------------------------- native calls
def fmt_cmd(argv, env=None):
    pre = "".join("%s=%s " % (k, shlex.quote(v)) for k, v in sorted((env or {}).items()))
    return pre + " ".join(shlex.quote(str(a)) for a in argv)


def call(argv, cwd=None, env=None, timeout=CALL_TIMEOUT, stdin=None):
    real = [BINARIES.get(argv[0], argv[0])] + [str(a) for a in argv[1:]]
    full_env = None
    if env:
        full_env = dict(os.environ)
        full_env.update(env)
    try:
        p = subprocess.run(real, capture_output=True, text=True, timeout=timeout, env=full_env, cwd=cwd, input=stdin)
    except subprocess.TimeoutExpired:
        return 124, "", "timed out after %ds" % timeout
    except FileNotFoundError:
        raise AccessError("%s not found on PATH; %s" % (argv[0], BIN_HINT.get(argv[0], "install it")))
    return p.returncode, p.stdout, p.stderr.strip()


def read_json(argv, env=None, missing_ok=(404,)):
    """GET through gh/glab -> (status, data). status 200 on success, the HTTP status on a tolerated error."""
    rc, out, err = call(argv, env=env)
    if rc != 0:
        st = http_status(err)
        if st in missing_ok:
            return st, None
        if st == 401 or ACCESS_RE.search(err):
            raise AccessError("%s: %s — check `%s auth status`" % (fmt_cmd(argv[:3]), first_line(err), argv[0]))
        if st == 403:
            return 403, None
        raise UserError("%s exited %d: %s" % (fmt_cmd(argv), rc, first_line(err) or "no output"))
    try:
        return 200, (json.loads(out) if out.strip() else None)
    except ValueError:
        raise UserError("%s: unparseable JSON" % fmt_cmd(argv))


def git_out(d, *args):
    rc, out, _err = call(["git", "-C", d] + list(args))
    return out.strip() if rc == 0 else ""


# ------------------------------------------------------------------------------- facts
LANG_MARKERS = (("pyproject.toml", "python"), ("setup.py", "python"), ("requirements.txt", "python"),
                ("package.json", "node"), ("go.mod", "go"), ("Cargo.toml", "rust"), ("pom.xml", "java"),
                ("build.gradle", "java"), ("build.gradle.kts", "java"), ("Chart.yaml", "helm"),
                ("CMakeLists.txt", "cpp"))


def parse_remote(url):
    """git remote URL -> (host, path) for ssh, scp-like and https forms; ('', '') otherwise."""
    url = (url or "").strip()
    m = re.match(r"^(?:ssh://)?(?:[^@/]+@)?([^:/]+)(?::\d+)?[:/](.+?)(?:\.git)?/?$", url)
    if url.startswith(("http://", "https://")):
        m = re.match(r"^https?://(?:[^@/]+@)?([^/]+)/(.+?)(?:\.git)?/?$", url)
    if not m:
        return "", ""
    return m.group(1).lower(), m.group(2)


def facts(d):
    f = {"dir": d, "dir_name": os.path.basename(d.rstrip("/")) or "repo", "exists": os.path.isdir(d),
         "is_git": False, "has_commits": False, "branch": "", "origin": "", "origin_host": "",
         "origin_path": "", "fresh": False, "languages": [], "year": str(today().year), "today": today().isoformat()}
    if not f["exists"]:
        return f
    f["is_git"] = os.path.exists(os.path.join(d, ".git"))
    if f["is_git"]:
        f["has_commits"] = bool(git_out(d, "rev-parse", "--verify", "--quiet", "HEAD"))
        f["branch"] = git_out(d, "symbolic-ref", "--short", "-q", "HEAD")
        f["origin"] = git_out(d, "config", "--get", "remote.origin.url")   # as configured, before insteadOf
        if f["has_commits"]:
            subjects = git_out(d, "log", "--format=%s", "-n", "2").splitlines()
            pushed = git_out(d, "for-each-ref", "--count=1", "--format=%(refname)", "refs/remotes/origin")
            # only repoboot's own unpushed initial commit: an interrupted `apply`, still a new repository
            f["fresh"] = subjects == [INITIAL_SUBJECT] and not pushed
        f["origin_host"], f["origin_path"] = parse_remote(f["origin"])
    langs = []
    for marker, lang in LANG_MARKERS:
        if os.path.exists(os.path.join(d, marker)) and lang not in langs:
            langs.append(lang)
    f["languages"] = langs
    return f


def origin_provider(host):
    if not host:
        return ""
    if host == "github.com":
        return "github"
    gl = gitlab_host().lower()
    hosts_re = os.environ.get("HARNESS_GITLAB_HOSTS_RE") or cfg("gitlab.hosts_re") or ""
    if (gl and host == gl) or "gitlab" in host or (hosts_re and re.search(hosts_re, host)):
        return "gitlab"
    return ""


def inferred(f):
    """Answers the checkout already gives (for `answer --infer`)."""
    out = {"repo.name": f["dir_name"]}
    if f["languages"]:
        out["architecture.languages"] = list(f["languages"])
    prov = origin_provider(f["origin_host"])
    if prov:
        out["repo.host"] = prov
        owner, _, name = f["origin_path"].rpartition("/")
        out["repo.name"] = name or f["dir_name"]
        if owner:
            out["repo.owner"] = owner
        if prov == "gitlab":
            out["repo.server"] = f["origin_host"]
    elif f["is_git"] and not f["origin"]:
        out["repo.host"] = "local"
    if f["has_commits"]:
        head = git_out(f["dir"], "symbolic-ref", "--short", "-q", "refs/remotes/origin/HEAD")
        if head.startswith("origin/"):
            out["workflow.default_branch"] = head[len("origin/"):]
        elif f["branch"] and not f["origin"]:
            out["workflow.default_branch"] = f["branch"]
    return out


# ------------------------------------------------------------------------------- expressions
def ctx_get(ctx, path):
    """Dotted lookup: fact.x / config.x / label.x / slot... / spec sections (pack.<id>.<key>)."""
    if path in ("true", "false"):
        return path == "true"
    head, _, rest = path.partition(".")
    if head in ("fact", "config", "label", "derived"):
        return (ctx.get(head) or {}).get(rest)
    return spec_get(ctx["spec"], path)


def as_text(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, list):
        return ", ".join(as_text(x) for x in v)
    return str(v)


def as_list(v):
    if v is None or v == "":
        return []
    return [as_text(x) for x in v] if isinstance(v, list) else [as_text(v)]


def truthy(v):
    if isinstance(v, list):
        return bool(v)
    return as_text(v) not in ("", "false", "0", "none", "no")


COND_RE = re.compile(r"^\s*(not\s+)?([A-Za-z0-9_.-]+)\s*(?:(==|!=|\bin\b|\bhas\b)\s*(.+?))?\s*$")


def evaluate(expr, ctx):
    """`A == v`, `A != v`, `A in a|b`, `A has v` (list contains), `A`, `not A`; joined by ` and ` / ` or `."""
    expr = (expr or "").strip()
    if not expr:
        return True
    if " or " in expr:
        return any(evaluate(p, ctx) for p in expr.split(" or "))
    if " and " in expr:
        return all(evaluate(p, ctx) for p in expr.split(" and "))
    m = COND_RE.match(expr)
    if not m:
        raise UserError("bad condition %r: use `A == v`, `A != v`, `A in a|b`, `A has v`, `A` or `not A`" % expr)
    neg, path, op, rhs = m.groups()
    val = ctx_get(ctx, path)
    if not op:
        res = truthy(val)
    else:
        rhs = rhs.strip().strip('"').strip("'")
        if op == "==":
            res = as_text(val) == rhs
        elif op == "!=":
            res = as_text(val) != rhs
        elif op == "in":
            res = as_text(val) in [x.strip() for x in rhs.split("|")]
        else:
            res = rhs in as_list(val)
    return (not res) if neg else res


# ------------------------------------------------------------------------------- templates
TOKEN_RE = re.compile(r"\{\{\s*(#if|#each|else|/if|/each|slot)?\s*([^}]*?)\s*\}\}")


def _parse(tokens, i, stop):
    nodes = []
    while i < len(tokens):
        kind, val = tokens[i]
        if kind == "tag" and val[0] in stop:
            return nodes, i
        if kind == "text":
            nodes.append(("text", val))
            i += 1
            continue
        tag, arg = val
        if tag == "#if":
            body, i = _parse(tokens, i + 1, ("else", "/if"))
            other = []
            if tokens[i][1][0] == "else":
                other, i = _parse(tokens, i + 1, ("/if",))
            nodes.append(("if", arg, body, other))
            i += 1
        elif tag == "#each":
            body, i = _parse(tokens, i + 1, ("/each",))
            nodes.append(("each", arg, body))
            i += 1
        elif tag == "slot":
            nodes.append(("slot", arg))
            i += 1
        elif tag in ("else", "/if", "/each"):
            raise UserError("template: unexpected {{%s}}" % tag)
        else:
            nodes.append(("var", arg))
            i += 1
    if stop:
        raise UserError("template: missing {{%s}}" % stop[-1])
    return nodes, i


def tokenize(text):
    tokens, pos = [], 0
    for m in TOKEN_RE.finditer(text):
        start, end = m.start(), m.end()
        tag = m.group(1) or ""
        # a block tag alone on its line takes the line (and its newline) with it
        if tag:
            ls = text.rfind("\n", 0, start) + 1
            le = text.find("\n", end)
            le = len(text) if le < 0 else le
            if text[ls:start].strip() == "" and text[end:le].strip() == "" and tag != "slot":
                start, end = ls, min(le + 1, len(text))
        if start > pos:
            tokens.append(("text", text[pos:start]))
        tokens.append(("tag", (tag, m.group(2))))
        pos = max(pos, end)
    if pos < len(text):
        tokens.append(("text", text[pos:]))
    return tokens


def render_nodes(nodes, ctx, item=None):
    out = []
    for n in nodes:
        if n[0] == "text":
            out.append(n[1])
        elif n[0] == "var":
            out.append(as_text(item) if n[1] == "." else as_text(ctx_get(ctx, n[1])))
        elif n[0] == "slot":
            out.append("".join(ctx["slots"].get(n[1], [])))
        elif n[0] == "if":
            out.append(render_nodes(n[2] if evaluate(n[1], ctx) else n[3], ctx, item))
        elif n[0] == "each":
            for x in as_list(ctx_get(ctx, n[1])):
                out.append(render_nodes(n[2], ctx, x))
    return "".join(out)


def render_text(text, ctx):
    nodes, _ = _parse(tokenize(text), 0, ())
    return render_nodes(nodes, ctx)


# ------------------------------------------------------------------------------- questions
def load_questions(path, prefix="", pack=""):
    data = toml_load(path)
    out = []
    for q in data.get("question") or []:
        q = dict(q)
        if prefix:
            q["id"] = prefix + q["id"]
        q.setdefault("type", "string")
        q.setdefault("round", 2 if pack else 1)
        q["pack"] = pack
        if q["type"] not in ("string", "choice", "multi", "list", "bool", "int"):
            raise UserError("%s: question %s has unknown type %r" % (path, q["id"], q["type"]))
        out.append(q)
    return out


def coerce(q, raw):
    """A string from the command line (or a TOML value) -> the question's typed value."""
    t = q["type"]
    if t in ("multi", "list"):
        items = raw if isinstance(raw, list) else [x.strip() for x in str(raw).split(",")]
        items = [str(x) for x in items if str(x) != ""]
        if t == "multi" and q.get("choices"):
            bad = [x for x in items if x not in q["choices"]]
            if bad:
                raise UserError("%s: %s not in %s" % (q["id"], ", ".join(bad), "|".join(q["choices"])))
        return items
    if t == "bool":
        if isinstance(raw, bool):
            return raw
        low = str(raw).strip().lower()
        if low in ("true", "yes", "y", "1"):
            return True
        if low in ("false", "no", "n", "0"):
            return False
        raise UserError("%s: %r is not yes/no" % (q["id"], raw))
    if t == "int":
        if isinstance(raw, bool) or not re.match(r"^\d+$", str(raw).strip()):
            raise UserError("%s: %r is not a whole number" % (q["id"], raw))
        return int(str(raw).strip())
    val = str(raw).strip()
    if t == "choice" and q.get("choices") and val not in q["choices"]:
        raise UserError("%s: %r not in %s" % (q["id"], val, "|".join(q["choices"])))
    if q.get("pattern") and val and not re.match(q["pattern"], val):
        raise UserError("%s: %r does not match %s" % (q["id"], val, q["pattern"]))
    return val


def resolve_default(q, ctx):
    d = q.get("default")
    if d is None:
        return None
    if isinstance(d, list):
        vals = []
        for x in d:
            vals.extend(v.strip() for v in render_text(str(x), ctx).split(","))
        return coerce(q, [v for v in vals if v])
    if isinstance(d, (bool, int)):
        return coerce(q, d)
    text = render_text(str(d), ctx)
    if text == "" and q["type"] not in ("multi", "list"):
        return "" if not q.get("required", True) else None
    return coerce(q, text)


# ------------------------------------------------------------------------------- packs
class Pack(object):
    def __init__(self, path, data):
        meta = data.get("pack") or {}
        self.dir = path
        self.id = meta.get("id") or os.path.basename(path)
        self.summary = meta.get("summary", "")
        self.order = int(meta.get("order", 50))
        self.always = bool(meta.get("always", False))
        self.match = meta.get("match") or {}
        self.covers = meta.get("covers") or {}
        self.files = data.get("file") or []
        self.fragments = data.get("fragment") or []
        if not re.match(r"^[a-z0-9][a-z0-9-]*$", self.id):
            raise UserError("%s: pack id %r must be lower-case letters, digits and dashes" % (path, self.id))

    def questions(self):
        return load_questions(os.path.join(self.dir, "pack.toml"), "pack.%s." % self.id, self.id)

    def matches(self, spec):
        if self.always:
            return True
        if not self.match:
            return False
        for key, want in self.match.items():
            have = as_list(spec_get(spec, key))
            if not set(as_list(want)) & set(have):
                return False
        return True

    def read(self, rel):
        path = os.path.normpath(os.path.join(self.dir, rel))
        if not path.startswith(os.path.normpath(self.dir) + os.sep):
            raise UserError("pack %s: template %r leaves the pack directory" % (self.id, rel))
        with open(path, encoding="utf-8") as fh:
            return fh.read()


def pack_dirs():
    dirs = [os.path.join(HERE, "packs")]
    for d in setting("pack_dirs"):
        d = os.path.expanduser(d)
        if not os.path.isdir(d):
            raise UserError("repo_bootstrap.pack_dirs: %s is not a directory; fix the config or create it" % d)
        dirs.append(d)
    return dirs


def load_packs():
    packs = {}
    for root in pack_dirs():
        for name in sorted(os.listdir(root)):
            path = os.path.join(root, name)
            if os.path.isfile(os.path.join(path, "pack.toml")):
                p = Pack(path, toml_load(os.path.join(path, "pack.toml")))
                packs[p.id] = p   # a later directory replaces a pack of the same id
    if "baseline" not in packs:
        raise UserError("the baseline pack is missing from %s; reinstall the bundle (harness apply)" % HERE)
    return packs


def selected_packs(packs, spec):
    return sorted([p for p in packs.values() if p.matches(spec)], key=lambda p: (p.order, p.id))


def uncovered(sel, spec):
    """Architecture answers no selected pack matches or covers -> the skill offers to write a pack."""
    covered = set()
    for p in sel:
        for table in (p.match, p.covers):
            for k, v in table.items():
                for x in as_list(v):
                    covered.add((k, x))
    out = []
    for key in ("architecture.kind", "architecture.languages", "architecture.toolchain", "architecture.deploy"):
        for v in as_list(spec_get(spec, key)):
            if v in ("", "none", "other") or (key, v) in covered:
                continue
            out.append("%s = %s" % (key, v))
    return out


# ------------------------------------------------------------------------------- engine
class Engine(object):
    def __init__(self, d, spec_path):
        self.dir = os.path.abspath(os.path.expanduser(d))
        self.spec_path = os.path.abspath(spec_path) if spec_path else os.path.join(self.dir, SPEC_NAME)
        self.facts = facts(self.dir)
        self.spec = flatten_spec(toml_load(self.spec_path)) if os.path.isfile(self.spec_path) else {}
        self.packs = load_packs()
        self.base_questions = load_questions(os.path.join(HERE, "questions.toml"))

    # context for conditions and templates
    def ctx(self):
        conf = dict((k, setting(k)) for k in DEFAULTS)
        conf["gitlab_host"] = gitlab_host()
        conf["gitlab_remove_source_branch_effective"] = self.remove_source_branch()
        labels = dict(agent_labels())
        return {"spec": self.spec, "fact": self.facts, "config": conf, "label": labels,
                "derived": self.derived(), "slots": {}}

    def remove_source_branch(self):
        v = setting("gitlab_remove_source_branch")
        if v == "auto":
            return "false" if stack_enabled() else "true"
        return v

    def derived(self):
        host = spec_get(self.spec, "repo.host") or ""
        owner = spec_get(self.spec, "repo.owner") or ""
        name = spec_get(self.spec, "repo.name") or ""
        server = "github.com" if host == "github" else (spec_get(self.spec, "repo.server") or gitlab_host())
        slug = "%s/%s" % (owner, name) if owner else name
        d = {"slug": slug, "server": server if host in ("github", "gitlab") else "",
             "ssh_url": "git@%s:%s.git" % (server, slug) if host in ("github", "gitlab") else "",
             "web_url": "https://%s/%s" % (server, slug) if host in ("github", "gitlab") else "",
             "ci": host if host in ("github", "gitlab") else "none",
             "codeowners": " ".join(as_list(spec_get(self.spec, "workflow.codeowners")))}
        return d

    def all_questions(self, sel=None):
        qs = list(self.base_questions)
        for p in (sel if sel is not None else selected_packs(self.packs, self.spec)):
            qs.extend(p.questions())
        return qs

    def open_questions(self, rnd=None):
        sel = selected_packs(self.packs, self.spec)
        ctx = self.ctx()
        out = []
        for q in self.all_questions(sel):
            if spec_get(self.spec, q["id"]) is not None:
                continue
            if not evaluate(q.get("when", ""), ctx):
                continue
            if rnd and q["round"] != rnd:
                continue
            row = {"id": q["id"], "round": q["round"], "group": q.get("group", q["pack"] and "pack:" + q["pack"]),
                   "prompt": render_text(q["prompt"], ctx), "type": q["type"], "required": bool(q.get("required", True))}
            for k in ("choices", "help", "pattern"):
                if q.get(k):
                    row[k] = q[k]
            dv = resolve_default(q, ctx)
            if dv is not None and (dv not in ([], "") or not row["required"]):
                row["default"] = dv
            if q["pack"]:
                row["pack"] = q["pack"]
            out.append(row)
        return out, sel

    def question(self, qid):
        for q in self.all_questions(None):
            if q["id"] == qid:
                return q
        # a pack question whose pack is not selected yet: search every pack
        for p in self.packs.values():
            for q in p.questions():
                if q["id"] == qid:
                    return q
        return None

    def write_spec(self):
        parent = os.path.dirname(self.spec_path)
        if not os.path.isdir(parent):
            os.makedirs(parent)
        atomic_write(self.spec_path, dump_spec(self.spec))

    # ---- files
    def files(self):
        """[(path, content, pack id)] in path order; a later pack replaces an earlier pack's file."""
        sel = selected_packs(self.packs, self.spec)
        ctx = self.ctx()
        for p in sel:
            for fr in p.fragments:
                if evaluate(fr.get("when", ""), ctx):
                    text = fr.get("text") if "text" in fr else p.read(fr["template"])
                    ctx["slots"].setdefault(fr["slot"], []).append(render_text(text, ctx))
        out = {}
        for p in sel:
            for fd in p.files:
                if not evaluate(fd.get("when", ""), ctx):
                    continue
                path = render_text(fd["path"], ctx).strip()
                if not path or path.startswith("/") or ".." in path.split("/"):
                    raise UserError("pack %s: file path %r must stay inside the repository" % (p.id, fd["path"]))
                if path in (SPEC_NAME, ".harness.toml") or path.startswith(".git/"):
                    raise UserError("pack %s: %s is not a pack file" % (p.id, path))
                content = render_text(p.read(fd["template"]), ctx)
                content = re.sub(r"\n{3,}", "\n\n", content).strip("\n")
                content = content + "\n" if content else ""
                out[path] = (content, p.id)
        return [(k, out[k][0], out[k][1]) for k in sorted(out)], sel

    def file_rows(self):
        rows = []
        files, sel = self.files()
        for path, content, pack in files:
            full = os.path.join(self.dir, path)
            if not os.path.exists(full):
                status = "create"
            else:
                try:
                    with open(full, encoding="utf-8") as fh:
                        status = "same" if fh.read() == content else "differs"
                except (OSError, UnicodeDecodeError):
                    status = "differs"
            rows.append({"path": path, "pack": pack, "status": status})
        return rows, files, sel

    # ---- validation
    def require_complete(self):
        missing, _ = self.open_questions()
        req = [q["id"] for q in missing if q["required"] and "default" not in q]
        if req:
            raise UserError("the spec %s leaves required questions open: %s — run `repoboot questions` and "
                            "`repoboot answer KEY=VALUE`" % (self.spec_path, ", ".join(req)))
        if missing:
            raise UserError("the spec %s leaves questions open (%s) — answer them or run `repoboot answer "
                            "--accept-defaults`" % (self.spec_path, ", ".join(q["id"] for q in missing)))
        if not self.spec:
            raise UserError("no spec at %s — run `repoboot questions` and `repoboot answer` first" % self.spec_path)

    def mode(self):
        return "existing" if self.facts["has_commits"] and not self.facts["fresh"] else "new"

    def host(self):
        return spec_get(self.spec, "repo.host") or "local"

    def provider(self):
        h = self.host()
        if h == "github":
            import repoboot_github
            return repoboot_github.Provider(self, sys.modules[__name__])
        if h == "gitlab":
            import repoboot_gitlab
            return repoboot_gitlab.Provider(self, sys.modules[__name__])
        return None

    def default_branch(self):
        return spec_get(self.spec, "workflow.default_branch") or "main"


def atomic_write(path, text):
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(prefix=".repoboot-", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


# ------------------------------------------------------------------------------- steps
def step(sid, argv, note, env=None, body=None, tolerate=None, kind="write"):
    """One native command `apply` runs. body = JSON written to a temp file passed as `@BODY`."""
    s = {"id": sid, "kind": kind, "argv": [str(a) for a in argv], "note": note}
    if env:
        s["env"] = env
    if body is not None:
        s["body"] = body
    if tolerate:
        s["tolerate"] = tolerate   # {"403": "why this is only a warning"}
    s["command"] = fmt_cmd(s["argv"], env)
    return s


def finding(severity, key, message, fix=None):
    f = {"severity": severity, "key": key, "message": message}
    if fix:
        f["fix"] = fix
    return f


def local_steps(e, rows):
    """git steps of a new repository (no remote)."""
    out = []
    branch = e.default_branch()
    if e.facts["fresh"]:
        return out   # an interrupted apply already committed; it resumes at the remote steps
    if not e.facts["is_git"]:
        out.append(step("git-init", ["git", "-C", e.dir, "init", "-b", branch], "create the repository"))
    elif e.facts["branch"] and e.facts["branch"] != branch:
        out.append(step("git-branch", ["git", "-C", e.dir, "symbolic-ref", "HEAD", "refs/heads/" + branch],
                        "name the unborn branch %s" % branch))
    paths = [SPEC_NAME if e.spec_path == os.path.join(e.dir, SPEC_NAME) else None] + [r["path"] for r in rows]
    paths = [p for p in paths if p]
    out.append(step("git-add", ["git", "-C", e.dir, "add", "--"] + paths, "stage the standard's files only"))
    out.append(step("git-commit", ["git", "-C", e.dir, "commit", "-m", INITIAL_SUBJECT,
                                   "-m", "Generated by repoboot from %s." % SPEC_NAME],
                    "the initial commit (your git identity)"))
    return out


def harness_draft(e):
    """`harness repo init` with [repo] filled from the spec; None when harness is not on PATH."""
    try:
        rc, out, _err = call(["harness", "repo", "init"])
    except AccessError:
        return None
    if rc != 0 or not out.strip():
        return None
    name = spec_get(e.spec, "repo.name") or ""
    tracker = spec_get(e.spec, "workflow.tracker") or ""
    project = spec_get(e.spec, "workflow.tracker_project") or ""
    text = out
    if name:
        text = re.sub(r'(?m)^# name = "[^"]*"$', 'name = "%s"' % name, text, count=1)
    if tracker in ("github-issues", "jira"):
        text = re.sub(r'(?m)^# tracker = "[^"]*"$', 'tracker = "%s"' % tracker, text, count=1)
        if tracker == "jira" and project:
            text = re.sub(r'(?m)^# project = "[^"]*"(.*)$', 'project = "%s"' % project, text, count=1)
    return text


# ------------------------------------------------------------------------------- verbs
def cmd_questions(e, a):
    qs, sel = e.open_questions(a.round)
    return {"verb": "questions", "spec": e.spec_path, "spec_exists": os.path.isfile(e.spec_path),
            "packs": [p.id for p in sel], "open": qs,
            "next": "ask round 1, then `repoboot answer KEY=VALUE…`; pack questions appear in round 2 once "
                    "the architecture answers select packs" if qs else "every question is answered: run `repoboot plan`",
            "exit": EXIT_OK}


def cmd_answer(e, a):
    changed = {}
    if a.infer:
        for qid, val in inferred(e.facts).items():
            if spec_get(e.spec, qid) is None:
                q = e.question(qid)
                if q:
                    spec_set(e.spec, qid, coerce(q, val))
                    changed[qid] = spec_get(e.spec, qid)
    for pair in a.pairs:
        if "=" not in pair:
            raise UserError("answer %r: use KEY=VALUE (lists: a,b; an empty value removes the answer)" % pair)
        qid, raw = pair.split("=", 1)
        qid = qid.strip()
        q = e.question(qid)
        if not q:
            raise UserError("%s is not a question of the intake or of any pack; `repoboot questions` lists them" % qid)
        if raw == "":
            sec, key = split_id(qid)
            (e.spec.get(sec) or {}).pop(key, None)
            changed[qid] = None
            continue
        spec_set(e.spec, qid, coerce(q, raw))
        changed[qid] = spec_get(e.spec, qid)
    if a.accept_defaults:
        for _ in range(4):   # defaults can open new questions (when) and select packs
            qs, _sel = e.open_questions()
            todo = [q for q in qs if "default" in q]
            if not todo:
                break
            for q in todo:
                spec_set(e.spec, q["id"], q["default"])
                changed[q["id"]] = q["default"]
    e.write_spec()
    qs, sel = e.open_questions()
    return {"verb": "answer", "spec": e.spec_path, "changed": changed, "packs": [p.id for p in sel],
            "open": [q["id"] for q in qs], "exit": EXIT_OK}


def build_plan(e, probe=True):
    e.require_complete()
    rows, _files, sel = e.file_rows()
    gaps = uncovered(sel, e.spec)
    mode = e.mode()
    plan = {"verb": "plan", "dir": e.dir, "spec": e.spec_path, "mode": mode, "host": e.host(),
            "packs": [{"id": p.id, "summary": p.summary, "dir": p.dir} for p in sel],
            "uncovered": gaps, "files": rows, "local": [], "remote": [], "findings": [], "notes": []}
    if gaps:
        plan["notes"].append("no pack covers %s: the baseline is used for them; offer the user a pack in "
                             "repo_bootstrap.pack_dirs (references/packs.md)" % "; ".join(gaps))
    if mode == "new":
        plan["local"] = local_steps(e, rows)
    else:
        if e.facts["branch"] == e.default_branch() and any(r["status"] != "same" for r in rows):
            plan["notes"].append("existing repository on its default branch: render on a branch "
                                 "(git switch -c repo-standard) and open an MR/PR for the file changes")
    prov = e.provider()
    if prov is not None:
        if probe:
            remote = prov.probe()
            plan["remote_state"] = remote.get("summary")
            if mode == "new":
                plan["remote"], notes = prov.new_steps(remote)
                if prov.blocked:
                    plan["blocked"] = prov.blocked
            else:
                plan["findings"], plan["remote"] = prov.drift(remote)
                notes = []
                ci = [r["path"] for r in rows if r["path"] in (".gitlab-ci.yml", ".github/workflows/ci.yml")
                      and r["status"] != "same"]
                if ci and plan["remote"]:
                    notes.append("%s is not on the default branch yet: merge the MR/PR with the files first, then "
                                 "apply the remote settings (pipelines must succeed / required checks)" % ci[0])
            plan["notes"].extend(notes)
        else:
            plan["notes"].append("remote not probed")
    draft = harness_draft(e)
    if draft is not None and not os.path.exists(os.path.join(e.dir, ".harness.toml")):
        plan["harness_toml_draft"] = draft
        plan["notes"].append(".harness.toml is drafted for the human to review and commit; repoboot never writes it")
    plan["exit"] = EXIT_ACTION if plan.get("blocked") else EXIT_OK
    return plan


def cmd_plan(e, a):
    return build_plan(e)


def write_files(e, rows, files, force):
    want = dict((p, c) for p, c, _k in files)
    written, skipped = [], []
    for r in rows:
        if r["status"] == "same":
            continue
        if r["status"] == "differs" and not force:
            skipped.append(r["path"])
            continue
        full = os.path.join(e.dir, r["path"])
        parent = os.path.dirname(full)
        if not os.path.isdir(parent):
            os.makedirs(parent)
        atomic_write(full, want[r["path"]])
        written.append(r["path"])
    return written, skipped


def cmd_render(e, a):
    e.require_complete()
    if e.mode() == "existing" and e.facts["branch"] == e.default_branch():
        raise UserError("%s is on its default branch %s: switch to a branch first (git -C %s switch -c "
                        "repo-standard), render there and open an MR/PR" % (e.dir, e.default_branch(), e.dir))
    rows, files, _sel = e.file_rows()
    if not os.path.isdir(e.dir):
        os.makedirs(e.dir)
    written, skipped = write_files(e, rows, files, a.force)
    out = {"verb": "render", "dir": e.dir, "written": written, "skipped_differs": skipped, "exit": EXIT_OK}
    if skipped:
        out["notes"] = ["%d file(s) differ from the standard and were kept; review `repoboot plan`, then "
                        "`repoboot render --force` to replace them" % len(skipped)]
        out["exit"] = EXIT_ACTION
    return out


def run_step(s, results):
    body_file = None
    argv = list(s["argv"])
    if "body" in s:
        fd, body_file = tempfile.mkstemp(prefix="repoboot-body-", suffix=".json")
        with os.fdopen(fd, "w") as fh:
            json.dump(s["body"], fh, indent=2, sort_keys=True)
        argv = [body_file if x == "@BODY" else x for x in argv]
    try:
        rc, out, err = call(argv, env=s.get("env"))
    finally:
        if body_file:
            os.unlink(body_file)
    res = {"id": s["id"], "command": s["command"]}
    if rc == 0:
        res["status"] = "done"
    else:
        st = http_status(err)
        why = (s.get("tolerate") or {}).get(str(st)) if st else None
        if why:
            res["status"] = "warn"
            res["message"] = why
        else:
            res["status"] = "failed"
            res["message"] = first_line(err) or first_line(out) or "exit %d" % rc
    results.append(res)
    return res["status"] != "failed"


def cmd_apply(e, a):
    plan = build_plan(e)
    results = []
    out = {"verb": "apply", "dir": e.dir, "mode": plan["mode"], "host": plan["host"], "results": results,
           "notes": list(plan["notes"])}
    if plan.get("blocked"):
        raise UserError(plan["blocked"])
    prov = e.provider()
    if plan["mode"] == "new":
        if not os.path.isdir(e.dir):
            os.makedirs(e.dir)
        rows, files, _sel = e.file_rows()
        written, skipped = write_files(e, rows, files, a.force)
        if skipped:
            raise UserError("files differ from the standard (%s): review `repoboot plan`, then `repoboot apply "
                            "--force` to replace them" % ", ".join(skipped))
        results.append({"id": "render", "status": "done", "command": "render %d file(s)" % len(written)})
        if not os.path.isfile(e.spec_path):
            e.write_spec()
        for s in plan["local"]:
            if not run_step(s, results):
                return finish(out, EXIT_ACTION)
        if prov is not None:
            ok = prov.apply_new(plan["remote"], results, run_step)
            if not ok:
                return finish(out, EXIT_ACTION)
    else:
        for s in plan["remote"]:
            if not run_step(s, results):
                return finish(out, EXIT_ACTION)
    if plan.get("harness_toml_draft"):
        out["harness_toml_draft"] = plan["harness_toml_draft"]
    warn = any(r["status"] == "warn" for r in results)
    return finish(out, EXIT_ACTION if warn else EXIT_OK)


def finish(out, code):
    out["exit"] = code
    return out


def cmd_check(e, a):
    if not os.path.isfile(e.spec_path):
        out = {"verb": "check", "dir": e.dir, "findings": [finding(
            "fail", "spec", "no %s: there is no standard to compare against" % e.spec_path,
            "repoboot answer --infer --dir %s && repoboot questions --dir %s" % (shlex.quote(e.dir), shlex.quote(e.dir)))],
            "exit": EXIT_ACTION}
        return out
    findings = []
    qs, _sel = e.open_questions()
    if qs:
        findings.append(finding("warn", "spec", "open questions: %s" % ", ".join(q["id"] for q in qs),
                                "repoboot answer KEY=VALUE … (or --accept-defaults)"))
        return {"verb": "check", "dir": e.dir, "findings": findings, "exit": EXIT_ACTION}
    rows, _files, sel = e.file_rows()
    for r in rows:
        if r["status"] == "same":
            findings.append(finding("ok", "file:" + r["path"], "as the standard (%s)" % r["pack"]))
        else:
            findings.append(finding("warn", "file:" + r["path"], "%s (%s)" % (
                "missing" if r["status"] == "create" else "differs from the standard", r["pack"]),
                "git switch -c repo-standard && repoboot render%s, then open an MR/PR" % (
                    " --force" if r["status"] == "differs" else "")))
    gaps = uncovered(sel, e.spec)
    for g in gaps:
        findings.append(finding("info", "architecture", "no pack covers %s (baseline only)" % g))
    if not os.path.exists(os.path.join(e.dir, ".harness.toml")):
        findings.append(finding("info", "harness", "no .harness.toml: the user-level harness applies unchanged",
                                "harness repo init (prints a draft for you to review and commit)"))
    prov = e.provider()
    if prov is not None:
        remote = prov.probe()
        if not remote.get("exists"):
            findings.append(finding("fail", "remote", "%s does not exist" % e.derived()["web_url"],
                                    "repoboot apply (creates it; the guard asks)"))
        else:
            fs, _steps = prov.drift(remote)
            findings.extend(fs)
    if not a.fix:
        for f in findings:
            f.pop("fix", None)
    bad = any(f["severity"] in ("warn", "fail") for f in findings)
    return {"verb": "check", "dir": e.dir, "packs": [p.id for p in sel], "findings": findings,
            "exit": EXIT_ACTION if bad else EXIT_OK}


# ------------------------------------------------------------------------------- output
def emit_text(rep):
    lines = ["repoboot %s — %s" % (rep["verb"], rep.get("dir") or rep.get("spec") or "")]
    if rep["verb"] == "questions":
        for q in rep["open"]:
            extra = " [%s]" % "|".join(q["choices"]) if q.get("choices") else ""
            dflt = " (default: %s)" % as_text(q["default"]) if "default" in q else ""
            lines.append("  r%d %-34s %s%s%s" % (q["round"], q["id"], q["prompt"], extra, dflt))
        lines.append("next: " + rep["next"])
    if rep["verb"] == "answer":
        for k in sorted(rep["changed"]):
            lines.append("  %s = %s" % (k, as_text(rep["changed"][k])))
        lines.append("open: %s" % (", ".join(rep["open"]) or "none"))
    if rep.get("mode"):
        lines.append("mode %s, host %s" % (rep["mode"], rep.get("host")))
    for p in rep.get("packs") or []:
        lines.append("pack  %s" % (p["id"] if isinstance(p, dict) else p))
    for f in rep.get("files") or []:
        lines.append("file  %-8s %s (%s)" % (f["status"], f["path"], f["pack"]))
    for s in (rep.get("local") or []) + (rep.get("remote") or []):
        lines.append("step  %s: %s" % (s["id"], s["note"]))
        lines.append("      " + s["command"])
    for r in rep.get("results") or []:
        lines.append("%-7s %s%s" % (r["status"], r["command"], ": " + r["message"] if r.get("message") else ""))
    for k in ("written", "skipped_differs"):
        for p in rep.get(k) or []:
            lines.append("%s %s" % ("wrote" if k == "written" else "kept ", p))
    for f in rep.get("findings") or []:
        lines.append("%-5s %s: %s" % (f["severity"], f["key"], f["message"]))
        if f.get("fix"):
            lines.append("      fix: " + f["fix"])
    for n in rep.get("notes") or []:
        lines.append("note: " + n)
    if rep.get("blocked"):
        lines.append("BLOCKED: " + rep["blocked"])
    if rep.get("harness_toml_draft"):
        lines.append("--- .harness.toml draft (for the human to review and commit) ---")
        lines.append(rep["harness_toml_draft"].rstrip("\n"))
    print("\n".join(lines))


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        die("repoboot %s: %s\n\nRun `repoboot` with no arguments for the usage." % (self.prog.split()[-1], message))


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--dir", default=".", help="the repository directory (default: .)")
    common.add_argument("--spec", help="the spec file (default: DIR/%s)" % SPEC_NAME)
    common.add_argument("--json", action="store_true", help="JSON output (default when stdout is not a TTY)")
    common.add_argument("--text", action="store_true", help="text output (default on a TTY)")
    top = _Parser(prog="repoboot", add_help=False)
    subs = top.add_subparsers(dest="verb")

    def sub(name, text):
        return subs.add_parser(name, parents=[common], help=text, description=text)

    q = sub("questions", "read-only: the open questions of the intake and the selected packs")
    q.add_argument("--round", type=int, choices=(1, 2))
    an = sub("answer", "write answers into the spec")
    an.add_argument("pairs", nargs="*", metavar="KEY=VALUE")
    an.add_argument("--accept-defaults", action="store_true", dest="accept_defaults")
    an.add_argument("--infer", action="store_true", help="fill what the checkout already says")
    sub("plan", "read-only: packs, files, local steps and remote commands apply would run")
    r = sub("render", "write the standard's files (missing ones; differing ones with --force)")
    r.add_argument("--force", action="store_true")
    ap = sub("apply", "new repository: init, commit, create, push, configure; existing: remote fixes")
    ap.add_argument("--force", action="store_true", help="replace files that differ from the standard")
    c = sub("check", "read-only: drift between the repository and its standard")
    c.add_argument("--fix", action="store_true", help="print the command that fixes each finding")
    return top, list(subs.choices)


VERBS = {"questions": cmd_questions, "answer": cmd_answer, "plan": cmd_plan, "render": cmd_render,
         "apply": cmd_apply, "check": cmd_check}


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
        die("Unknown verb %r. Verbs: %s\n\nRun `repoboot` with no arguments for the usage." % (argv[0], ", ".join(names)))
    a = top.parse_args(argv)
    try:
        for key in DEFAULTS:
            setting(key)
        e = Engine(a.dir, a.spec)
        rep = VERBS[a.verb](e, a)
    except AccessError as exc:
        die("repoboot: %s" % exc, EXIT_ACCESS)
    except UserError as exc:
        die("repoboot: %s" % exc, EXIT_ACTION)
    except KeyboardInterrupt:
        die("repoboot: interrupted", EXIT_ACTION)
    except BrokenPipeError:
        sys.exit(EXIT_OK)
    if a.json or not (a.text or sys.stdout.isatty()):
        print(json.dumps(rep, indent=2, sort_keys=False))
    else:
        emit_text(rep)
    sys.exit(rep["exit"])


if __name__ == "__main__":
    main()
