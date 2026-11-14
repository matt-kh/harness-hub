#!/usr/bin/env python3
"""Software supply-chain client: detect, pins, ci, audit, sbom, verify, redact — stdlib only.

Canonical invocation: `supply <cmd>` (symlinked into ~/.local/bin by `harness apply`).
Read-only by construction: it scans a checkout offline, runs pinned scanners and verifiers
(osv-scanner, syft, cosign, `gh attestation verify`) or the ecosystem's own auditor when one is
already installed, and never installs, signs, attests, pushes or switches verification off.
The only local writes are `pins --apply FILE` (exact token rewrites a /pin-deps run prepared)
and `sbom --out FILE`. Every tool output passes through the core redactor. Nothing from the
scanned checkout is executed: fallback auditors run from an empty working directory where they
can (cargo-audit, pip-audit on fully hashed files only) and govulncheck with GOTOOLCHAIN=local.

Output is findings-first: JSON when stdout is not a TTY (or --json), Markdown on a TTY (or --md):
  {"command","dir","ecosystems","tools",
   "findings":[{"id","severity","file","line","message","fix"[,"ref"]}],"data":{...}}
Findings are sorted by (file, line, id, message); there is no timestamp. Pin findings carry
"ref": the exact token as written, so /pin-deps can build an apply file.
Exit codes: 0 clean, 1 a crit or warn finding (or a usage error), 2 access, tool or config error
(unreadable DIR, a needed tool missing, a tool failing or printing unexpected output, a bad
config regex, a refused or failed `--apply` write), 3 unsupported (no auditor for any detected
ecosystem, `ci` with no scannable file, `sbom lint` on a non-JSON file, `verify --offline`
without --trusted-root, or with --github and no --bundle). `detect` exits 0 on any readable DIR.
When JSON output exceeds --max-bytes, trailing items of the largest list are dropped until it
fits and the envelope carries "truncated": {"items_dropped": N, "max_bytes": M}.

Every command except `redact` and `sbom lint` prints a banner to STDERR first:
  supply: dir=<DIR as given> ecosystems=<list|none> tools=<installed tools|none>
(dir=- for an image or blob target and for `ci`).

Commands (run with no args to print this list):
  detect [DIR]          Ecosystems (pip, npm, go, cargo, docker, github-actions, gitlab-ci,
                        shell), their manifests and lockfiles. Never runs a tool.
  pins [DIR] [--apply FILE]
                        Unpinned actions, images, dependencies and downloads without a
                        checksum (GHA*, CI006, CI008, CI009, DKR*, PIP*, NPM*, GO*, CGO*,
                        SH001, SH002, REG001, SUP*). --apply FILE rewrites exact tokens from a
                        JSON list [{"file","line","old","new"}]: each old must be the ref of a
                        current finding on that line, occur there exactly once as a whole token,
                        and new must pin it (digest, 40-hex sha); no symlinks; all files or
                        none are written (exit 2), then it re-scans.
  ci FILE... [--ignore RULE,...]
                        Workflow hardening for GitHub Actions, GitLab CI, Dockerfiles and
                        shell files: CI*, GHA*, SH*. --ignore is a flag, never a comment.
  audit [DIR] [--lockfile F]... [--sbom F] [--offline]
                        Known vulnerabilities: osv-scanner (OSV001), else npm audit,
                        pip-audit (hashed requirements only), cargo-audit, govulncheck when
                        present (VUL001).
                        "unavailable" is never "clean": AUD001 per ecosystem with no auditor,
                        exit 3 when none could be audited.
  sbom DIR|IMAGE [--format spdx-json|cyclonedx-json] [--out F] [--force]
                        SBOM through syft (dir: or registry:, never the docker daemon); a
                        summary without --out; --out refuses an existing file unless --force.
  sbom lint FILE        SPDX / CycloneDX JSON shape check, offline (SBM*).
  verify TARGET [--identity NAME|RE [--issuer URL] | --key F | --github OWNER[/REPO]]
         [--attestation [--type T]] [--bundle F] [--trusted-root F] [--offline]
                        Signature or attestation of an image (oci://REF or a reference) or a
                        file (blob, needs --bundle with cosign) through cosign or
                        `gh attestation verify`. Never passes an --insecure-* flag.
  redact                stdin -> stdout filter (JSON or free text). No tool call.

Common flags: --json/--md, --max-bytes N (supply_chain.max_bytes, 65536), --timeout S (120).

Deliberately NOT implemented — do not work around these: signing, attesting, key generation,
publishing or pushing anything, `osv-scanner fix`, installing a scanner (`harness install
osv-scanner|cosign|syft` is the human's step), the docker daemon as an SBOM source, licence
policy, reachability analysis, editing a lockfile.

Config (harness config keys from build/config.json via HARNESS_CONFIG_JSON / HARNESS_HOME;
the environment wins where named):
  supply_chain.identities            [[supply_chain.identities]] name, identity_re, issuer,
                                     match_re (optional): signer identities for `verify`
  SUPPLY_REGISTRIES_RE [supply_chain.registries_re]   allowed registry hosts (REG001)
  SUPPLY_REDACT_EXTRA_RE [supply_chain.redact_extra_re] extra regex of token shapes to redact
  SUPPLY_EXCLUDE_RE [supply_chain.exclude_re]  python regex on relative paths to skip
  SUPPLY_OSV_OFFLINE_DB [supply_chain.osv_offline_db] local OSV database for `audit --offline`
  SUPPLY_TIMEOUT [supply_chain.timeout]        per-tool timeout seconds (120)
  SUPPLY_MAX_BYTES [supply_chain.max_bytes]    default --max-bytes (65536)
  supply_chain.pin_actions           false: GHA001 is not reported and `--apply` skips actions
Test hooks (never needed in normal use):
  SUPPLY_PATH=DIRS       look tools up only in DIRS (an empty directory = nothing installed)
  SUPPLY_DRY_RUN=1       append each tool argv to SUPPLY_DRY_RUN_LOG (stderr when unset);
                         the tool still runs
  SUPPLY_MAX_FILES=N     scan cap (20000; SUP001 when reached)
  SUPPLY_TEST_FAIL_AFTER=N  `pins --apply` fails after replacing N files (exercises the rollback)
"""
import argparse
import base64
import errno
import json
import os
import re
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tempfile

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


# --------------------------------------------------------------------------- redaction
# >>> redact
KEY_BODY = (r"(pass(word|wd)?|secret|token|api[-_]?key|private[-_]?key|access[-_]?key"
            r"|client[-_]?secret|credential|auth|cert(ificate)?|jwt|dsn"
            r"|connection[-_]?string)")
SECRET_KEY_RE = re.compile(r"(?i)" + KEY_BODY)
REDACTED = "***REDACTED***"
_TEXT_KEY_RE = re.compile(r"^(\s*[\w.-]*" + KEY_BODY + r"[\w.-]*\s*[:=]\s*)(.+)$", re.I)
# the anchored rule above only catches `key: value` lines; logs usually carry a timestamp
# and a level first, so the same key=value shape is redacted anywhere in the line too.
# An HTTP auth scheme word (`Authorization: Bearer X`) is consumed with the token after it,
# so the credential does not survive behind a masked scheme word. Accepted cost: a value
# that merely looks like a scheme word (`token=basic retry`) also masks the word after it.
_AUTH_SCHEME = r"(?:bearer|basic|token|digest|negotiate|api-?key|ssws|oauth)"
_TEXT_KEY_INLINE_RE = re.compile(
    r"(?P<key>[\w.-]*" + KEY_BODY + r"[\w.-]*)(?P<sep>\s*[:=]\s*)"
    r"(?P<val>\"[^\"]*\"|'[^']*'|" + _AUTH_SCHEME + r"\s+\S+|\S+)", re.I)
_AKIA_RE = re.compile(r"AKIA[0-9A-Z]{16}")
_JWT_RE = re.compile(r"eyJ[\w-]+\.[\w-]+\.[\w-]+")
_PEM_RE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
                     re.S)
_URLCRED_RE = re.compile(r"://[^/:@\s]+:[^@\s]+@")


def _secret_sizes(obj):
    """Replace a Secret's data/stringData values with '<N bytes>' (never the value)."""
    out = dict(obj)
    for field in ("data", "stringData"):
        blob = obj.get(field)
        if not isinstance(blob, dict):
            continue
        sized = {}
        for k, v in blob.items():
            if field == "data":
                try:
                    n = len(base64.b64decode(v or "", validate=False))
                except Exception:
                    n = len(v or "")
            else:
                n = len(v or "")
            sized[k] = "<%d bytes>" % n
        out[field] = sized
    return out


_EXTRA_WARNED = []


def _usable_extra(extra_re):
    """extra_re, or None when it is unset or matches the empty string (warned once)."""
    if extra_re is None or not extra_re.match(""):
        return extra_re
    if not _EXTRA_WARNED:
        _EXTRA_WARNED.append(True)
        sys.stderr.write("redact: extra pattern matches the empty string; ignored\n")
    return None


def redact_obj(obj, extra_re=None):
    """Walk a JSON structure: secret-ish keys -> ***REDACTED***, Secret data -> sizes.
    extra_re (compiled regex or None): its matches inside the remaining string values are
    redacted too, after key masking; Secret `<N bytes>` sizes are never passed to it."""
    return _redact_walk(obj, _usable_extra(extra_re))


def _redact_walk(obj, extra_re):
    if isinstance(obj, dict):
        sized = ()
        if obj.get("kind") == "Secret":
            obj = _secret_sizes(obj)
            sized = ("data", "stringData")
        out = {}
        for k, v in obj.items():
            if k in sized and isinstance(v, dict):
                out[k] = v  # byte sizes only: no value left to mask
            elif isinstance(v, (dict, list)):
                out[k] = _redact_walk(v, extra_re)
            elif SECRET_KEY_RE.search(str(k)) and v is not None and not (
                    isinstance(v, str) and v.startswith("<") and v.endswith("bytes>")):
                out[k] = REDACTED
            else:
                out[k] = _redact_walk(v, extra_re)
        return out
    if isinstance(obj, list):
        return [_redact_walk(x, extra_re) for x in obj]
    if extra_re is not None and isinstance(obj, str):
        return extra_re.sub(REDACTED, obj)
    return obj


def redact_text(text, extra_re=None):
    """Redact free text / logs: key=value lines, AWS keys, JWTs, PEM blocks, URL creds.
    extra_re (compiled regex or None): its matches are redacted too, after the built-in
    rules, so a pattern naming a key or scheme word cannot hide what they would catch."""
    if not text:
        return text
    extra_re = _usable_extra(extra_re)
    text = _PEM_RE.sub(REDACTED, text)
    lines = []
    for line in text.split("\n"):
        m = _TEXT_KEY_RE.match(line)
        if m:
            line = m.group(1) + REDACTED
        else:
            line = _TEXT_KEY_INLINE_RE.sub(
                lambda x: x.group("key") + x.group("sep") + REDACTED, line)
        line = _AKIA_RE.sub(REDACTED, line)
        line = _JWT_RE.sub(REDACTED, line)
        line = _URLCRED_RE.sub("://***:***@", line)
        lines.append(line)
    text = "\n".join(lines)
    if extra_re is not None:
        text = extra_re.sub(REDACTED, text)
    return text
# <<< redact


def die(msg, code=1):
    print(msg, file=sys.stderr)
    sys.exit(code)


class AccessError(Exception):
    """Unreadable input, a needed tool missing or failing, a bad config value -> exit 2."""


class Unsupported(Exception):
    """Nothing this CLI can do for the input -> exit 3."""


def _prime_cfg():
    """Load the compiled config as UTF-8 before the inlined cfg() opens it with the locale's
    encoding (the inlined block is shared with other CLIs and stays byte-identical)."""
    global _HARNESS_CFG
    try:
        with open(_harness_cfg_path(), encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        doc = {}
    _HARNESS_CFG = doc if isinstance(doc, dict) else {}


_prime_cfg()


def _env_or_cfg(env, key, default):
    v = os.environ.get(env)
    if v not in (None, ""):
        return v
    v = cfg(key)
    return default if v in (None, "") else v


def _int(v, default):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


TIMEOUT = _int(_env_or_cfg("SUPPLY_TIMEOUT", "supply_chain.timeout", 120), 120)
MAX_BYTES = _int(_env_or_cfg("SUPPLY_MAX_BYTES", "supply_chain.max_bytes", 65536), 65536)
TOOLS = ("cargo-audit", "cosign", "gh", "govulncheck", "npm", "osv-scanner", "pip-audit", "syft")
SKIP_DIRS = {".git", "node_modules", "vendor", ".venv", "venv", "target", "dist", "build",
             "__pycache__", ".tox"}
MAX_FILE_BYTES = 2 * 1024 * 1024
DEP_ECOSYSTEMS = ("cargo", "go", "npm", "pip")
HEX40 = re.compile(r"^[0-9a-f]{40}$")

_AUTH_SCHEME_RE = re.compile(r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{6,}")


class _ExtraRedactors(object):
    """The built-in scheme regex and the user's supply_chain.redact_extra_re, each compiled on its
    own (a user pattern may start with a global flag such as `(?i)`) and applied in turn."""

    def __init__(self, *rxs):
        self.rxs = [r for r in rxs if r is not None]

    def match(self, s):
        for r in self.rxs:
            m = r.match(s)
            if m is not None:
                return m
        return None

    def sub(self, repl, s):
        for r in self.rxs:
            s = r.sub(repl, s)
        return s


_REDACTORS = None


def _compile_cfg_re(env, key, what):
    pat = _env_or_cfg(env, key, "")
    if not pat:
        return None
    try:
        return re.compile(pat)
    except re.error as e:
        raise AccessError("%s / %s is not a valid Python regex (%s); fix or unset it (%s)"
                          % (env, key, e, what))


def extra_redactors():
    """Compiled lazily on the first redacting use: a bad pattern fails that command with exit 2."""
    global _REDACTORS
    if _REDACTORS is None:
        try:
            user = _compile_cfg_re("SUPPLY_REDACT_EXTRA_RE", "supply_chain.redact_extra_re",
                                   "a global flag such as (?i) must come first")
        except AccessError:
            _REDACTORS = _ExtraRedactors(_AUTH_SCHEME_RE)  # the error message is still redacted
            raise
        _REDACTORS = _ExtraRedactors(_AUTH_SCHEME_RE, _usable_extra(user))
    return _REDACTORS


def red_text(s):
    if s is None:
        return ""
    return redact_text(str(s), extra_redactors()) if s != "" else ""


def red_obj(o):
    return redact_obj(o, extra_redactors())


def red_deep(o):
    """redact_obj (secret-looking keys) and then the free-text rules on every string value."""
    o = red_obj(o)

    def walk(x):
        if isinstance(x, dict):
            return {k: walk(v) for k, v in x.items()}
        if isinstance(x, list):
            return [walk(v) for v in x]
        if isinstance(x, str):
            return red_text(x)
        return x
    return walk(o)


_EXCLUDE = []
_REGISTRIES = []


def exclude_re():
    if not _EXCLUDE:
        _EXCLUDE.append(_compile_cfg_re("SUPPLY_EXCLUDE_RE", "supply_chain.exclude_re",
                                        "it is matched against paths relative to DIR"))
    return _EXCLUDE[0]


def registries_re():
    if not _REGISTRIES:
        _REGISTRIES.append(_compile_cfg_re("SUPPLY_REGISTRIES_RE", "supply_chain.registries_re",
                                           "it is matched against registry host names"))
    return _REGISTRIES[0]


def pin_actions():
    v = cfg("supply_chain.pin_actions", True)
    return not (v is False or str(v).lower() in ("false", "0", "no"))


# --------------------------------------------------------------------------------- tools
def _abs_dirs(path):
    """PATH without empty or relative entries: those resolve against the working directory,
    which may be the scanned checkout."""
    return os.pathsep.join(d for d in (path or "").split(os.pathsep) if d and os.path.isabs(d))


def tool_path(name):
    """The tool's absolute path: from SUPPLY_PATH only when it is set (test hook), else from PATH;
    empty and relative entries are ignored."""
    sp = os.environ.get("SUPPLY_PATH")
    dirs = _abs_dirs(sp if sp is not None else os.environ.get("PATH", os.defpath))
    if not dirs:
        return None
    exe = shutil.which(name, path=dirs)
    return exe if exe and os.path.isabs(exe) else None


def installed_tools():
    return [t for t in TOOLS if tool_path(t)]


def _dry_log(line):
    path = os.environ.get("SUPPLY_DRY_RUN_LOG")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    else:
        sys.stderr.write("dry-run: %s\n" % line)


NEUTRAL = object()  # _run(cwd=NEUTRAL): a fresh empty directory, never the checkout


def _run(name, args, cwd=None, timeout=None, env_extra=None):
    """Run tool NAME with ARGS; -> (rc, stdout, stderr). Never merges stderr into stdout.
    The tool runs in its own process group, killed whole when it outlives the timeout."""
    exe = tool_path(name)
    if not exe:
        raise AccessError("%s is not installed" % name)
    t = timeout or TIMEOUT
    neutral = None
    if cwd is NEUTRAL:
        neutral = cwd = tempfile.mkdtemp(prefix="supply-")
    try:
        if os.environ.get("SUPPLY_DRY_RUN") == "1":
            pre = "".join("%s=%s " % (k, shlex.quote(v)) for k, v in sorted((env_extra or {}).items()))
            if cwd:
                pre = "cd %s && %s" % ("<empty-dir>" if neutral else shlex.quote(cwd), pre)
            _dry_log(pre + " ".join([name] + [shlex.quote(str(a)) for a in args]))
        env = dict(os.environ)
        env.update(env_extra or {})
        try:
            p = subprocess.Popen([exe] + [str(a) for a in args], cwd=cwd or None, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, env=env,
                                 universal_newlines=True, errors="replace", start_new_session=True)
        except OSError as e:
            raise AccessError("%s could not be started (%s); check the installation" % (name, e.strerror or e))
        try:
            out, err = p.communicate(timeout=t)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except OSError:
                p.kill()
            p.communicate()
            raise AccessError("%s timed out after %ds; raise --timeout (or SUPPLY_TIMEOUT / "
                              "supply_chain.timeout), or narrow the target" % (name, t))
        return p.returncode, out, err
    finally:
        if neutral:
            shutil.rmtree(neutral, ignore_errors=True)


class tool_output(object):
    """`with tool_output("npm audit", hint):` turns a malformed but parseable tool answer (a list
    where an object was expected, ...) into an AccessError instead of a traceback."""

    def __init__(self, tool, hint=""):
        self.tool, self.hint = tool, hint

    def __enter__(self):
        return self

    def __exit__(self, et, ev, tb):
        if et is not None and issubclass(et, (AttributeError, TypeError, KeyError, IndexError, ValueError)):
            raise AccessError("%s printed unexpected output (%s: %s); %s" % (
                self.tool, et.__name__, snippet(ev, 80),
                self.hint or "check the tool version against the pinned one (harness install)"))
        return False


def error_line(text, n=300):
    """The tool's error line: the last `Error: ...` line (cosign and syft print the cause there and
    a `main.go:NN: error during command execution` trailer after it), else the last line that reads
    like an error (tools log progress first), else the first line."""
    lines = [ln.strip() for ln in (text or "").splitlines()]
    hits = [ln for ln in lines if ln.startswith("Error:")] or \
           [ln for ln in lines if re.search(r"(?i)\b(error|unable|could not|cannot|failed|fatal)\b", ln)]
    return red_text(hits[-1])[:n] if hits else first_line(text, n)


def first_line(text, n=300):
    for line in (text or "").splitlines():
        s = line.strip()
        if s:
            return red_text(s)[:n]
    return ""


# -------------------------------------------------------------------------------- rules
# id -> (default severity, fix). Severities and fixes are documented once in
# references/pinning.md and references/ci-hardening.md; keep the three in step.
RULES = {
    "GHA001": ("warn", "pin the full 40-character commit sha and keep the tag as a comment: "
                       "`uses: OWNER/REPO@<sha> # vX.Y.Z` (/pin-deps resolves it)"),
    "GHA002": ("crit", "pin the full 40-character commit sha of a released tag: "
                       "`uses: OWNER/REPO@<sha> # vX.Y.Z`"),
    "GHA003": ("warn", "pin the image digest: `docker://IMAGE@sha256:<digest>` (keep the tag in a "
                       "comment)"),
    "CI000": ("info", "the file was not scanned: indent with spaces, or check it with its own "
                      "tool (actionlint, the GitLab CI lint)"),
    "CI001": ("warn", "add a top-level `permissions: contents: read` and widen per job only "
                      "where needed"),
    "CI002": ("crit", "grant only the scopes a job needs, at job level (`permissions: contents: "
                      "read` at the top)"),
    "CI003": ("crit", "never check out the pull request head in a pull_request_target "
                      "workflow; use pull_request, or a two-workflow split with workflow_run "
                      "and no secrets in the untrusted half"),
    "CI004": ("crit", "pass the value through env: (`env: TITLE: ${{ ... }}`) and use "
                      "\"$TITLE\" in the script; never expand it into the script text"),
    "CI005": ("warn", "never print secrets or dump the environment; pass secrets as env "
                      "variables to the step that needs them"),
    "CI006": ("warn", "pin the image digest: `IMAGE:TAG@sha256:<digest>` (resolve with "
                      "`docker buildx imagetools inspect` or `crane digest`)"),
    "CI007": ("warn", "let the security job fail the pipeline; triage findings instead of "
                      "`allow_failure`/`continue-on-error`"),
    "CI008": ("warn", "pin the include to a full 40-character commit sha (`ref: <sha>`) or a "
                      "released component version (`@1.2.3`)"),
    "CI009": ("warn", "vendor the remote file into the repository, or include it from a project "
                      "pinned to a commit sha"),
    "DKR001": ("warn", "pin the base image digest: `FROM IMAGE:TAG@sha256:<digest>`"),
    "DKR002": ("crit", "name a released tag and pin its digest: `FROM IMAGE:TAG@sha256:<digest>`"),
    "DKR003": ("warn", "pin the image digest: `image: IMAGE:TAG@sha256:<digest>`"),
    "PIP001": ("warn", "pin an exact version (`name==X.Y.Z`), or generate the file from a "
                       "lockfile (`uv pip compile --generate-hashes`)"),
    "PIP002": ("crit", "pin the commit (`git+https://HOST/OWNER/REPO@<sha>`), or depend on a "
                       "released version from the index; URL archives need `--hash`"),
    "PIP003": ("info", "add `--hash=sha256:...` to every line (`uv pip compile "
                       "--generate-hashes`, `pip-compile --generate-hashes`)"),
    "PIP004": ("info", "commit a lockfile (`uv lock`, `poetry lock`, `pdm lock`) so installs "
                       "resolve the same versions"),
    "NPM001": ("warn", "commit a lockfile (`npm install` writes package-lock.json) and install "
                       "with `npm ci`; exact versions for applications"),
    "NPM002": ("crit", "depend on a released version from the registry, or pin the commit: "
                       "`github:OWNER/REPO#<sha>`"),
    "GO001": ("warn", "run `go mod tidy` and commit go.sum"),
    "GO002": ("warn", "install a released version: `go install MODULE@vX.Y.Z`"),
    "GO003": ("info", "replace with a released version, or keep the local path out of release "
                      "builds"),
    "CGO001": ("crit", "pin the commit: `{ git = \"URL\", rev = \"<sha>\" }`, or use a "
                       "released crate"),
    "CGO002": ("info", "install a released version reproducibly: `cargo install NAME --version "
                       "X.Y.Z --locked`"),
    "SH001": ("crit", "download to a file, check its sha256 (`sha256sum -c`) or signature, read "
                      "it, then run it"),
    "SH002": ("warn", "verify the download before use: `sha256sum -c`, `cosign verify-blob`, "
                      "`gh attestation verify`, or `ADD --checksum=sha256:...`"),
    "REG001": ("warn", "pull from an allowed registry (supply_chain.registries_re), or add the "
                       "host to the allow-list after review"),
    "SUP001": ("warn", "narrow DIR or exclude generated trees with supply_chain.exclude_re; "
                       "files after the cap were not scanned"),
    "SUP002": ("warn", "make the path readable and rerun, or exclude it with supply_chain.exclude_re; "
                       "it was not scanned, so the result is not clean"),
    "OSV001": ("warn", "upgrade to the fixed version (see the message); /audit-deps applies "
                       "patch and minor upgrades"),
    "VUL001": ("warn", "upgrade to the fixed version (see the message); /audit-deps applies "
                       "patch and minor upgrades"),
    "AUD001": ("info", "`harness install osv-scanner` (covers every ecosystem), or install the "
                       "ecosystem's own auditor"),
    "AUD002": ("info", "nothing to audit: no lockfile or manifest osv-scanner understands"),
    "AUD003": ("warn", "run the auditor by hand to see its error; an errored audit is not clean"),
    "SBM001": ("crit", "generate the SBOM with a real tool (`supply sbom DIR --out F`)"),
    "SBM002": ("warn", "regenerate the SBOM; the format's required fields are missing"),
    "SBM003": ("info", "regenerate with SPDX 2.3 or CycloneDX 1.5-1.7"),
    "SBM004": ("warn", "regenerate the SBOM; consumers need the creation time"),
    "SBM005": ("warn", "regenerate the SBOM with a tool that records itself"),
    "SBM006": ("warn", "check the scan target; an SBOM without packages describes nothing"),
    "SBM007": ("info", "regenerate from a lockfile or the built artefact so versions resolve"),
    "SBM008": ("info", "regenerate with purls so scanners can match the packages"),
    "SBM009": ("info", "record what the SBOM describes (SPDX DESCRIBES relationship, CycloneDX "
                       "metadata.component)"),
    "VER000": ("info", "none: verified"),
    "VER001": ("warn", "the signature belongs to another reference; verify the image you will "
                       "run, by digest"),
}
PIN_RULES = {"GHA001", "GHA002", "GHA003", "CI000", "CI006", "CI008", "CI009", "DKR001",
             "DKR002", "DKR003", "PIP001", "PIP002", "PIP003", "PIP004", "NPM001", "NPM002",
             "GO001", "GO002", "GO003", "CGO001", "CGO002", "SH001", "SH002", "REG001", "SUP001",
             "SUP002"}
CI_RULES = {r for r in RULES if r.startswith(("CI", "GHA", "SH"))} | {"REG001"}


# -------------------------------------------------------------------------------- report
class Report(object):
    def __init__(self, command, dir_="-", ecosystems=(), tools=()):
        self.command = command
        self.dir = dir_
        self.ecosystems = list(ecosystems)
        self.tools = list(tools)
        self.findings = []
        self.data = {}
        self.forced_exit = None

    def add(self, rid, file, line, message, severity=None, fix=None, ref=None):
        sev = severity or RULES[rid][0]
        f = {"id": rid, "severity": sev, "file": file or "", "line": int(line or 0),
             "message": red_text(message), "fix": red_text(fix) if fix else RULES[rid][1]}
        if ref:
            r = red_text(ref)
            if r == ref:  # a ref the redactor changed carries a credential: never echo it
                f["ref"] = ref
        self.findings.append(f)

    def keep(self, allowed):
        self.findings = [f for f in self.findings if f["id"] in allowed]

    def sorted_findings(self):
        seen, out = set(), []
        for f in sorted(self.findings, key=lambda f: (f["file"], f["line"], f["id"], f["message"])):
            k = json.dumps(f, sort_keys=True)
            if k not in seen:
                seen.add(k)
                out.append(f)
        return out

    def exit_code(self):
        if self.forced_exit is not None:
            return self.forced_exit
        return 1 if any(f["severity"] in ("crit", "warn") for f in self.findings) else 0

    def envelope(self):
        return {"command": self.command, "dir": self.dir, "ecosystems": self.ecosystems,
                "tools": self.tools, "findings": self.sorted_findings(), "data": self.data}

    def markdown(self):
        out = ["# supply %s — %s" % (self.command, self.dir), "",
               "ecosystems: %s · tools: %s" % (", ".join(self.ecosystems) or "none",
                                                ", ".join(self.tools) or "none"), ""]
        fs = self.sorted_findings()
        out += ["## Findings (%d)" % len(fs), ""]
        if fs:
            out += ["| sev | id | where | message | fix |", "|---|---|---|---|---|"]
            for f in fs:
                where = f["file"] + (":%d" % f["line"] if f["line"] else "")
                out.append("| %s | %s | %s | %s | %s |" % (f["severity"], f["id"], md_cell(where or "-"),
                                                          md_cell(f["message"]), md_cell(f["fix"])))
        else:
            out.append("none")
        out.append("")
        for name in sorted(self.data):
            out += ["## %s" % name, ""]
            out.extend(md_value(self.data[name]))
            out.append("")
        return "\n".join(out)

    def fitted_envelope(self, max_bytes):
        env = self.envelope()

        def dump(e):
            return json.dumps(e, indent=2, sort_keys=True, default=str)

        txt = dump(env)
        if not max_bytes or len(txt.encode("utf-8")) <= max_bytes:
            return txt
        data = env["data"] = dict(env["data"])
        lists = {k: list(v) for k, v in data.items() if isinstance(v, list)}
        data.update(lists)
        env["findings"] = list(env["findings"])
        dropped = 0
        env["truncated"] = {"items_dropped": 0, "max_bytes": max_bytes}
        while len(txt.encode("utf-8")) > max_bytes:
            pool = [lists[k] for k in sorted(lists) if lists[k]] or (
                [env["findings"]] if env["findings"] else [])
            if not pool:
                break
            biggest = max(pool, key=lambda v: len(json.dumps(v, sort_keys=True, default=str)))
            biggest.pop()
            dropped += 1
            env["truncated"]["items_dropped"] = dropped
            txt = dump(env)
        return txt

    def emit(self, fmt, max_bytes):
        if fmt == "json":
            sys.stdout.write(self.fitted_envelope(max_bytes) + "\n")
            return
        txt = self.markdown()
        raw = txt.encode("utf-8")
        if max_bytes and len(raw) > max_bytes:
            txt = raw[:max_bytes].decode("utf-8", "ignore")
            txt += "\n\n…[truncated %d bytes — narrow DIR or rerun with --json and a larger --max-bytes]" % (
                len(raw) - max_bytes)
        sys.stdout.write(txt if txt.endswith("\n") else txt + "\n")


def md_cell(v):
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        v = json.dumps(v, default=str, sort_keys=True)
    return str(v).replace("|", "\\|").replace("\n", " ⏎ ")


def md_value(val):
    if isinstance(val, list):
        if not val:
            return ["_none_"]
        if all(isinstance(x, dict) for x in val):
            cols = []
            for row in val:
                for k in sorted(row):
                    if k not in cols:
                        cols.append(k)
            lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
            for row in val:
                lines.append("| " + " | ".join(md_cell(row.get(c)) for c in cols) + " |")
            return lines
        return ["- " + md_cell(x) for x in val]
    if isinstance(val, dict):
        if not val:
            return ["_none_"]
        return ["| key | value |", "|---|---|"] + ["| %s | %s |" % (md_cell(k), md_cell(val[k]))
                                                    for k in sorted(val)]
    return [md_cell(val)]


def banner(dir_, ecosystems, tools):
    sys.stderr.write("supply: dir=%s ecosystems=%s tools=%s\n"
                     % (dir_, ",".join(ecosystems) or "none", ",".join(tools) or "none"))


def snippet(text, n=100):
    s = " ".join(str(text).split())
    return s if len(s) <= n else s[:n - 1] + "…"


# ------------------------------------------------------------------------------- walking
class Tree(object):
    """Every file under DIR (relative POSIX paths, sorted walk), classified."""

    def __init__(self, root):
        self.root = root
        self.files = []
        self.large = []
        self.truncated = False
        self.cap = _int(os.environ.get("SUPPLY_MAX_FILES"), 20000)
        self.roles = {}       # rel -> [(ecosystem, role)]
        self.gitlab = []      # .gitlab-ci.yml and its local includes
        self.unreadable = []  # [(rel, reason)]: directories os.walk could not list
        self.outside = []     # symlinks whose target leaves DIR (never read)
        self.realroot = os.path.realpath(root)
        self._walk()
        self._classify()

    def _walk(self):
        if not os.path.isdir(self.root):
            raise AccessError("%s: not a directory (pass a checkout directory)" % self.root)
        try:
            os.listdir(self.root)
        except OSError as e:
            raise AccessError("%s: not readable (%s)" % (self.root, e.strerror or e))
        excl = exclude_re()

        def onerror(e):
            p = getattr(e, "filename", None) or ""
            rel = os.path.relpath(p, self.root).replace(os.sep, "/") if p else "?"
            self.unreadable.append((rel + "/", e.strerror or str(e)))

        for dp, dns, fns in os.walk(self.root, onerror=onerror):
            reld = os.path.relpath(dp, self.root).replace(os.sep, "/")
            reld = "" if reld == "." else reld + "/"
            dns[:] = sorted(d for d in dns if d not in SKIP_DIRS
                            and not (excl and excl.search(reld + d + "/")))
            for fn in sorted(fns):
                rel = reld + fn
                if excl and excl.search(rel):
                    continue
                full = os.path.join(dp, fn)
                try:
                    if os.path.islink(full) and not self.inside(os.path.realpath(full)):
                        self.outside.append(rel)
                        continue
                    if not os.path.isfile(full):
                        continue
                    size = os.path.getsize(full)
                except (OSError, ValueError):
                    continue
                if size > MAX_FILE_BYTES:
                    self.large.append(rel)
                    continue
                if len(self.files) >= self.cap:
                    self.truncated = True
                    return
                self.files.append(rel)

    def inside(self, real):
        try:
            return os.path.commonpath([real, self.realroot]) == self.realroot
        except ValueError:
            return False

    def path(self, rel):
        return os.path.join(self.root, *rel.split("/"))

    def read(self, rel):
        try:
            with open(self.path(rel), "rb") as fh:
                return fh.read().decode("utf-8", "replace")
        except OSError:
            return None

    def _classify(self):
        for rel in self.files:
            r = classify(rel)
            if r:
                self.roles[rel] = r
        if ".gitlab-ci.yml" in self.roles:
            todo, seen = [".gitlab-ci.yml"], set()
            while todo:
                rel = todo.pop(0)
                if rel in seen:
                    continue
                seen.add(rel)
                self.gitlab.append(rel)
                try:
                    doc = parse_yaml(self.read(rel) or "")
                except YamlError:
                    continue
                for inc in gitlab_local_includes(doc):
                    inc = inc.lstrip("/")
                    if inc in self.files and inc not in seen:
                        self.roles.setdefault(inc, []).append(("gitlab-ci", "ci"))
                        todo.append(inc)
        for rel in self.files:
            if os.path.basename(rel).startswith("requirements") and rel.endswith(".txt"):
                if "--hash" in (self.read(rel) or ""):
                    self.roles.setdefault(rel, []).append(("pip", "lockfile"))

    def of(self, role, ecosystem=None):
        return [rel for rel in self.files for (e, r) in self.roles.get(rel, ())
                if r == role and (ecosystem is None or e == ecosystem)]

    def ecosystems(self):
        return sorted({e for rs in self.roles.values() for (e, _r) in rs})

    def summary(self):
        out = []
        for e in self.ecosystems():
            files = sorted({rel for rel, rs in self.roles.items() for (x, r) in rs
                            if x == e and r != "lockfile"})
            locks = sorted({rel for rel, rs in self.roles.items() for (x, r) in rs
                            if x == e and r == "lockfile"})
            out.append({"ecosystem": e, "files": files, "lockfiles": locks})
        return out


_SHELL_NAMES = {"makefile", "gnumakefile", "justfile"}


def classify(rel):
    base = rel.rsplit("/", 1)[-1]
    low = base.lower()
    out = []
    if re.search(r"(^|/)\.github/workflows/[^/]+\.ya?ml$", rel):
        # first: a workflow may be named compose.yml, dockerfile.yml or requirements.yml
        out.append(("github-actions", "workflow"))
    elif re.match(r"^requirements.*\.txt$", low) or (rel.startswith("requirements/") or "/requirements/" in rel) and low.endswith(".txt"):
        out.append(("pip", "manifest"))
    elif low in ("pyproject.toml", "setup.py", "setup.cfg", "pipfile"):
        out.append(("pip", "manifest"))
    elif low in ("uv.lock", "poetry.lock", "pdm.lock", "pipfile.lock"):
        out.append(("pip", "lockfile"))
    elif low == "package.json":
        out.append(("npm", "manifest"))
    elif low in ("package-lock.json", "npm-shrinkwrap.json", "pnpm-lock.yaml", "yarn.lock", "bun.lock",
                 "bun.lockb"):
        out.append(("npm", "lockfile"))
    elif low == ".npmrc":
        out.append(("npm", "config"))
    elif base == "go.mod":
        out.append(("go", "manifest"))
    elif base == "go.sum":
        out.append(("go", "lockfile"))
    elif base == "Cargo.toml":
        out.append(("cargo", "manifest"))
    elif base == "Cargo.lock":
        out.append(("cargo", "lockfile"))
    elif is_dockerfile(base):
        out.append(("docker", "dockerfile"))
    elif re.match(r"^(docker-)?compose([.-][\w.-]+)?\.ya?ml$", low):
        out.append(("docker", "compose"))
    elif low in ("action.yml", "action.yaml"):
        out.append(("github-actions", "action"))
    elif rel == ".gitlab-ci.yml":
        out.append(("gitlab-ci", "ci"))
    elif low.endswith((".sh", ".bash", ".mk")) or low in _SHELL_NAMES:
        out.append(("shell", "script"))
    return out


def is_dockerfile(base):
    low = base.lower()
    return bool(re.match(r"^(dockerfile|containerfile)([.-][\w.-]+)?$", low) or low.endswith(".dockerfile"))


# ---------------------------------------------------------------------- YAML (line model)
class YNode(object):
    """One YAML line: a key (with an inline scalar, a block scalar or children) or a list item."""
    __slots__ = ("key", "val", "line", "indent", "children", "block", "item", "raw")

    def __init__(self, key, val, line, indent, item=False):
        self.key, self.val, self.line, self.indent, self.item = key, val, line, indent, item
        self.children, self.block, self.raw = [], [], None

    def get(self, key):
        for c in self.children:
            if not c.item and c.key == key:
                return c
        return None

    def keys(self):
        return [c for c in self.children if not c.item]

    def items(self):
        return [c for c in self.children if c.item]

    def sval(self, key):
        c = self.get(key)
        return c.val if c is not None and c.val is not None else None


_YKEY = re.compile(r"""^(?P<key>"[^"]*"|'[^']*'|[^\s"'#{\[|>&*!%@`,?:-][^:#]*?|-[^\s:#][^:#]*?)\s*:(?:\s+(?P<val>.*))?$""")
_BLOCK_IND = re.compile(r"^[|>][0-9+-]*$")


def strip_comment(s):
    q = None
    for i, ch in enumerate(s):
        if q:
            if ch == q:
                q = None
        elif ch in ("'", '"') and (i == 0 or s[i - 1] in " \t:[{,-"):
            q = ch
        elif ch == "#" and (i == 0 or s[i - 1] in " \t"):
            return s[:i].rstrip()
    return s.rstrip()


def unquote(v):
    if v is None:
        return None
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
        inner = v[1:-1]
        return inner.replace("''", "'") if v[0] == "'" else inner
    return v


def flow_list(v):
    v = (v or "").strip()
    if v.startswith("[") and v.endswith("]"):
        return [unquote(x) for x in v[1:-1].split(",") if x.strip()]
    return None


class YamlError(Exception):
    pass


def parse_yaml(text):
    """-> root YNode, or raise YamlError for what this model refuses (tab indentation)."""
    lines = text.split("\n")
    root = YNode(None, None, 0, -1)
    stack = [root]
    last = None
    i = 0

    def attach(node):
        while len(stack) > 1:
            top = stack[-1]
            if top.indent > node.indent:
                stack.pop()
            elif top.indent == node.indent and not (node.item and not top.item and top.val is None):
                stack.pop()
            else:
                break
        stack[-1].children.append(node)
        stack.append(node)

    def read_block(node, start, base_indent):
        j, block = start, []
        while j < len(lines):
            raw = lines[j].rstrip("\r")
            if raw.strip() and len(raw) - len(raw.lstrip(" ")) <= base_indent:
                break
            block.append((j + 1, raw))
            j += 1
        while block and not block[-1][1].strip():
            block.pop()
        ind = min([len(t) - len(t.lstrip(" ")) for _l, t in block if t.strip()] or [0])
        node.block = [(ln, t[ind:]) for ln, t in block]
        node.val = "\n".join(t for _l, t in node.block)
        return j

    while i < len(lines):
        raw = lines[i].rstrip("\r")
        ln = i + 1
        i += 1
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lead = raw[:len(raw) - len(raw.lstrip(" \t"))]
        if "\t" in lead:
            raise YamlError("line %d: tab indentation" % ln)
        if stripped in ("---", "...") or stripped.startswith(("--- ", "%")):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        content = strip_comment(raw[indent:])
        if not content:
            continue
        if last is not None and indent > last.indent:
            last.block.append((ln, content))
            last.val = (last.val or "") + " " + content
            continue
        last = None
        col = indent
        node = None
        while content == "-" or content.startswith("- "):
            item = YNode(None, None, ln, col, item=True)
            attach(item)
            rest = content[1:]
            col += 1 + len(rest) - len(rest.lstrip(" "))
            content = rest.lstrip(" ")
            item.raw = unquote(content)
            node = item
        if not content:
            continue
        m = _YKEY.match(content)
        if m:
            key = unquote(m.group("key"))
            val = m.group("val")
            val = re.sub(r"^&\S+\s*", "", val) if val else val
            kn = YNode(key, None, ln, col)
            attach(kn)
            if val and _BLOCK_IND.match(val):
                i = read_block(kn, i, col)
            elif val:
                kn.val = unquote(val)
                kn.block = [(ln, kn.val)]
                last = kn
            continue
        target = node if node is not None else None
        if target is None:
            continue  # a bare scalar outside a list: nothing this model needs
        if _BLOCK_IND.match(content):
            i = read_block(target, i, target.indent)
        else:
            target.val = unquote(content)
            target.block = [(ln, target.val)]
            last = target
    return root


def yaml_lines(node):
    """(line, text) pairs of a scalar node, or of a list of scalars (GitLab script)."""
    if node is None:
        return []
    if node.block:
        return list(node.block)
    out = []
    for it in node.items():
        # an item the model read as a mapping (`- echo a: b`) still contributes its line
        out.extend(it.block or ([(it.line, it.raw)] if it.raw else []))
    return out


# ------------------------------------------------------------------------------- shell
_SEC_WORDS = (r"(?i)(?:^|[\s:/_.-])(audit|osv[\w-]*|vuln\w*|scan\w*|snyk|trivy|grype|codeql|semgrep|"
              r"gitleaks|trufflehog|zizmor|scorecard|dependency[-_ ]review|dependency[-_ ]scanning|"
              r"sast|dast|secret[-_ ]detection|container[-_ ]scanning|pip-audit|govulncheck|bandit|"
              r"sbom|cosign|attest\w*)(?:$|[\s:/_.@-])")
SEC_RE = re.compile(_SEC_WORDS)
_INTERP_RE = re.compile(r"^(?:sh|bash|zsh|ksh|dash|fish|python[0-9.]*|perl|node|ruby|php)$")
_SHELLS = {"sh", "bash", "zsh", "ksh", "dash", "fish"}
_FETCH = {"curl", "wget", "fetch"}
_CURL_FILE = re.compile(r"\bcurl\b(?=[^|;]*(?:\s-[A-Za-z]*[oO](?:\s|\S)|\s--output\b|\s--remote-name|\s>\s*[^\s&]))")
_WGET_STDOUT = re.compile(r"\s-[A-Za-z]*O\s*-(?:\s|$)|--output-document[= ]-(?:\s|$)|-O\s*/dev/stdout")
_DEVNULL = re.compile(r"(?:-o|--output)\s*/dev/null|>\s*/dev/null")
SH002_OK = re.compile(r"sha256sum|sha512sum|shasum\s+-a\s*(?:256|512)|hn_sha256|sha256:|--checksum|"
                      r"cosign\s+verify|gh\s+attestation\s+verify|\.sig\b|\.sigstore|gpg\s+--verify|"
                      r"minisign\s+-V")
GO002_RE = re.compile(r"\bgo\s+(?:install|run|get)\s+(?:-\S+\s+)*(?P<ref>\S+@(?:latest|master|main|HEAD))(?![\w.-])")
CGO002_RE = re.compile(r"\bcargo\s+install\s+(?P<rest>.*)$")


def logical_lines(pairs, docker=False):
    """Join backslash continuations: [(first line number, joined text)]. Comment lines are
    dropped; inside a continuation a Dockerfile skips them (BuildKit strips them first) while a
    shell ends the command there (the comment itself is never part of the text)."""
    out, buf, start = [], [], None
    for ln, text in pairs:
        t = text.rstrip()
        if start is None:
            if not t.strip() or t.strip().startswith("#"):
                continue
            start = ln
        elif t.strip().startswith("#") or (docker and not t.strip()):
            if docker:
                continue
            out.append((start, " ".join(x.strip() for x in buf)))
            buf, start = [], None
            continue
        if t.endswith("\\"):
            buf.append(t[:-1])
            continue
        buf.append(t)
        out.append((start, " ".join(x.strip() for x in buf)))
        buf, start = [], None
    if buf:
        out.append((start, " ".join(x.strip() for x in buf)))
    return out


# ------------------------------------------------------------------ shell lexer (one line)
_SH_OPS = ("&&", "||", ";;", "|&", "<(", ">(", "|", ";", "&", "(", ")")
_SH_REDIR = re.compile(r"&>>?|[<>]{1,3}[&|]?(?:\d+-?|-)?")


def _sub_end(text, j):
    """Index just past the `)` that closes a `$(` whose body starts at J."""
    depth, n = 1, len(text)
    while j < n:
        c = text[j]
        if c == "\\":
            j += 2
            continue
        if c == "'":
            k = text.find("'", j + 1)
            j = n if k < 0 else k + 1
            continue
        if c == '"':
            k = j + 1
            while k < n and text[k] != '"':
                k += 2 if text[k] == "\\" else 1
            j = k + 1
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    return n


def sh_tokens(text):
    """Quote-aware split of one logical shell line: [(kind, value)] with kind 'w' (a word, quotes
    removed, `$(...)` kept whole), 'r' (a redirection) or 'op'. An unquoted `#` starting a word
    ends the line."""
    toks, cur, have, i, n = [], [], False, 0, len(text)

    def flush():
        if have:
            toks.append(("w", "".join(cur)))
        return [], False

    while i < n:
        c = text[i]
        if c in " \t\r\n":
            cur, have = flush()
            i += 1
        elif c == "#" and not have:
            break
        elif c == "\\":
            cur.append(text[i + 1:i + 2])
            have, i = True, i + 2
        elif c == "'":
            j = text.find("'", i + 1)
            j = n if j < 0 else j
            cur.append(text[i + 1:j])
            have, i = True, j + 1
        elif c == '"':
            j = i + 1
            while j < n and text[j] != '"':
                if text[j] == "\\":
                    j += 2
                elif text.startswith("$(", j):
                    j = _sub_end(text, j + 2)
                else:
                    j += 1
            cur.append(text[i + 1:j])
            have, i = True, j + 1
        elif text.startswith("$(", i):
            j = _sub_end(text, i + 2)
            cur.append(text[i:j])
            have, i = True, j
        elif c == "`":
            j = text.find("`", i + 1)
            j = n if j < 0 else j
            cur.append(text[i:j + 1])
            have, i = True, j + 1
        elif text.startswith(("<(", ">("), i):
            cur, have = flush()
            toks.append(("op", text[i:i + 2]))
            i += 2
        elif c in "<>" or text.startswith("&>", i):
            fd = "".join(cur) if have and "".join(cur).isdigit() else ""
            if fd:
                cur, have = [], False
            else:
                cur, have = flush()
            m = _SH_REDIR.match(text, i)
            toks.append(("r", fd + m.group(0)))
            i = m.end()
        else:
            op = next((o for o in _SH_OPS if text.startswith(o, i)), None)
            if op:
                cur, have = flush()
                toks.append(("op", op))
                i += len(op)
            else:
                cur.append(c)
                have, i = True, i + 1
    flush()
    return toks


class ShCmd(object):
    """One simple command of a logical line: its words (redirections and their targets
    excluded), its text with redirections, and the operators around it."""
    __slots__ = ("words", "text", "before", "after")

    def __init__(self, words, text, before, after):
        self.words, self.text, self.before, self.after = words, text, before, after


def sh_commands(text):
    toks = sh_tokens(text)
    ops = [v for k, v in toks if k == "op" and v in ("(", ")", "<(", ">(")]
    if ops and ops[0] == ")":  # a case pattern (`curl|wget) ...`): drop it
        k = next(i for i, t in enumerate(toks) if t == ("op", ")"))
        toks = toks[k + 1:]
    cmds, words, parts, before, redir = [], [], [], None, False
    for kind, v in toks:
        if kind == "op":
            if words or parts:
                cmds.append(ShCmd(words, " ".join(parts), before, v))
            words, parts, before, redir = [], [], v, False
            continue
        parts.append(v)
        if kind == "r":
            redir = not re.search(r"&(?:\d+-?|-)$", v)  # `2>&1` carries its target
            continue
        if redir:
            redir = False
            continue
        words.append(v)
    if words or parts:
        cmds.append(ShCmd(words, " ".join(parts), before, None))
    return cmds


_WRAPPERS = {"command", "exec", "time", "nohup", "builtin", "then", "do", "else", "if", "elif", "while",
             "until", "!", "{", "xargs"}


def sh_head(words):
    """-> (index, basename) of the command word after assignments, sudo, env and keywords."""
    i = 0
    while i < len(words):
        w = words[i]
        b = w.rsplit("/", 1)[-1]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", w):
            i += 1
        elif b in ("sudo", "doas", "env"):
            i += 1
            while i < len(words) and (words[i].startswith("-") or (b == "env" and "=" in words[i])):
                if words[i] in ("-u", "-g", "-C", "-h", "-p", "-r", "-t", "-U", "-D", "-S"):
                    i += 1
                i += 1
        elif b in _WRAPPERS:
            i += 1
            while i < len(words) and words[i].startswith("-"):
                i += 1
        else:
            return i, b
    return None, ""


def reads_stdin(interp, args):
    """True when INTERP with ARGS takes its program from stdin (`sh`, `sh -s`, `bash -`,
    `python3 -`), False when the program comes from -c/-e/-m or a script file."""
    shell = interp in _SHELLS
    bad = set("cn") if shell else set("cmeEnpr")
    i = 0
    while i < len(args):
        w = args[i]
        if w == "-":
            return True
        if w == "--":
            return i + 1 == len(args)
        if w.startswith("--"):
            if re.match(r"^--(?:command|eval|print|module|exec|check|syntax-check|version|help)\b", w):
                return False
            i += 1
            continue
        if w.startswith("-") or (shell and w.startswith("+")):
            letters = set(w[1:])
            if letters & bad:
                return False
            if shell and "s" in letters:
                return True
            i += 2 if (shell and letters & set("oO")) or (not shell and letters & set("WXQ")) else 1
            continue
        return False  # a script file (or a module path): stdin is its data
    return True


def _substitutions(word):
    """The bodies of the `$(...)` substitutions inside WORD."""
    out, i = [], 0
    while True:
        i = word.find("$(", i)
        if i < 0:
            return out
        j = _sub_end(word, i + 2)
        out.append(word[i + 2:j - 1] if word[j - 1:j] == ")" else word[i + 2:j])
        i = j


def _fetch_sub(word):
    """True when WORD is (or starts with) `$(curl|wget|fetch ...)`."""
    w = word.lstrip()
    if not w.startswith("$("):
        return False
    subs = _substitutions(w)
    if not subs:
        return False
    cmds = sh_commands(subs[0])
    return bool(cmds) and sh_head(cmds[0].words)[1] in _FETCH


def sh001(text, depth=0):
    """True when the logical line runs downloaded code unreviewed (quote-aware: a pipe inside a
    quoted string, an `echo` of install instructions, `| python -c`, `| python -m json.tool` or a
    pipe into a script file are not findings)."""
    cmds = sh_commands(text)
    for k, c in enumerate(cmds):
        if depth < 3:  # `x=$(curl … | sh)`, `echo "$(curl … | sh)"`
            for w in c.words:
                for body in _substitutions(w):
                    if sh001(body, depth + 1):
                        return True
        hi, head = sh_head(c.words)
        if hi is None:
            continue
        args = c.words[hi + 1:]
        if head in _FETCH and c.after in ("|", "|&") and k + 1 < len(cmds):
            nxt = cmds[k + 1]
            ni, nhead = sh_head(nxt.words)
            if ni is not None and _INTERP_RE.match(nhead) and reads_stdin(nhead, nxt.words[ni + 1:]):
                return True
        if (head in _SHELLS or head in ("source", ".")) and c.after == "<(" and k + 1 < len(cmds) \
                and sh_head(cmds[k + 1].words)[1] in _FETCH:
            return True
        if head in _SHELLS and "-c" in args:
            j = args.index("-c")
            if j + 1 < len(args) and _fetch_sub(args[j + 1]):
                return True
        if head == "eval" and any(_fetch_sub(a) for a in args):
            return True
    return False


def scan_shell(rep, rel, pairs, docker=False):
    """SH001, SH002, GO002, CGO002 over (line, text) pairs of one script or script block."""
    logical = logical_lines(pairs, docker=docker)
    for idx, (ln, text) in enumerate(logical):
        text = mask_gha_expr(text)
        if sh001(text):
            rep.add("SH001", rel, ln, "downloaded code runs unreviewed: `%s`" % snippet(text))
            continue
        for c in sh_commands(text):
            hi, head = sh_head(c.words)
            if head == "curl":
                hit = _CURL_FILE.search(c.text) and not _DEVNULL.search(c.text)
            elif head == "wget":
                hit = not _WGET_STDOUT.search(c.text) and c.after not in ("|", "|&")
            else:
                continue
            if hit:
                window = " ".join(t for _l, t in logical[idx:idx + 9])
                if not SH002_OK.search(window):
                    rep.add("SH002", rel, ln, "download written to a file with no checksum or signature "
                            "check within the next 8 lines: `%s`" % snippet(text))
                break
        m = GO002_RE.search(text)
        if m:
            rep.add("GO002", rel, ln, "`go %s` installs whatever the ref points at today"
                    % m.group(0).split(None, 1)[1], ref=m.group("ref"))
        m = CGO002_RE.search(text)
        if m and "--path" not in m.group("rest"):
            rest = m.group("rest")
            versioned = re.search(r"--vers(?:ion)?[ =]\S+|@\d", rest)
            if not ("--locked" in rest and versioned):
                rep.add("CGO002", rel, ln, "`cargo install %s` without both --version and --locked "
                        "resolves fresh dependency versions" % snippet(rest, 60))


_GHA_EXPR = re.compile(r"\$\{\{(.*?)\}\}")


def mask_gha_expr(text):
    """`${{ a || b }}` -> `${{a__b}}`: an expression is one word to the shell lexer (GitHub
    substitutes it before the shell runs), so its spaces and operators must not split commands."""
    if "${{" not in text:
        return text
    return _GHA_EXPR.sub(lambda m: "${{" + re.sub(r"[\s|&;()<>'\"`]+", "_", m.group(1)).strip("_") + "}}", text)


# ------------------------------------------------------------------------------- images
def image_parts(ref):
    """-> (host, repository, tag, digest) of an image reference."""
    digest = None
    if "@" in ref:
        ref, digest = ref.split("@", 1)
    tag = None
    if ":" in ref.rsplit("/", 1)[-1]:
        ref, tag = ref.rsplit(":", 1)
    first = ref.split("/", 1)[0]
    host = first if "/" in ref and ("." in first or ":" in first or first == "localhost") else "docker.io"
    return host, ref, tag, digest


def image_pin(ref):
    """None when pinned by digest (or not checkable), else 'crit' (no tag / latest) or 'warn'."""
    if not ref or "$" in ref or "{{" in ref:
        return None
    _h, _r, tag, digest = image_parts(ref)
    if digest and digest.startswith("sha256:"):
        return None
    if not tag or tag == "latest":
        return "crit"
    return "warn"


def check_registry(rep, rel, ln, host, what):
    rx = registries_re()
    if rx is not None and host and not rx.search(host):
        rep.add("REG001", rel, ln, "%s comes from %s, which supply_chain.registries_re does not allow"
                % (what, host))


def check_image(rep, rid, rel, ln, ref, where):
    if not ref or "$" in ref or "{{" in ref:
        return
    sev = image_pin(ref)
    if sev == "crit":
        rep.add(rid, rel, ln, "%s `%s` has no tag or uses :latest" % (where, ref), severity="crit", ref=ref)
    elif sev == "warn":
        rep.add(rid, rel, ln, "%s `%s` is pinned to a tag, not a digest" % (where, ref), severity="warn", ref=ref)
    check_registry(rep, rel, ln, image_parts(ref)[0], "%s `%s`" % (where, ref))


# ------------------------------------------------------------------------ GitHub Actions
UNTRUSTED = (r"(?:github\.head_ref|github\.event\.(?:"
             r"(?:issue|pull_request|discussion)\.(?:title|body)"
             r"|(?:comment|review|review_comment|discussion_comment)\.body"
             r"|pull_request\.head\.(?:ref|label|repo\.default_branch)"
             r"|(?:head_commit|workflow_run\.head_commit)\.(?:message|author\.(?:email|name))"
             r"|commits(?:\[\d+\]|\.\*)\.(?:message|author\.(?:email|name))"
             r"|workflow_run\.head_branch"
             r"|pages(?:\[\d+\]|\.\*)\.page_name))")
CI004_RE = re.compile(r"\$\{\{[^}]*?(?<![\w.])(" + UNTRUSTED + r")(?![\w-])[^}]*\}\}")
INPUT_RE = re.compile(r"\$\{\{[^}]*?(?<![\w.])((?:github\.event\.)?inputs\.([A-Za-z0-9_-]+))(?![\w-])[^}]*\}\}")
HEADREF_RE = re.compile(r"github\.event\.pull_request\.head\.(?:sha|ref)|github\.head_ref|refs/pull/|"
                        r"github\.event\.pull_request\.merge_commit_sha|github\.event\.pull_request\.number")
PR_HEAD_ARG_RE = re.compile(r"pull/|github\.event\.pull_request\.head|github\.head_ref|"
                            r"github\.event\.pull_request\.merge_commit_sha")
GH_SECRET_ECHO = re.compile(r"\b(?:echo|printf|print|cat|tee)\b.*\$\{\{\s*(?:secrets\.|toJSON\(\s*secrets)"
                            r"|\$\{\{\s*toJSON\(\s*secrets\s*\)")
ENV_DUMP = re.compile(r"^(?:sudo\s+)?(?:env|printenv|export\s+-p|set)\s*(?:\||>|$)")
BRANCH_NAMES = {"main", "master", "develop", "dev", "trunk", "head", "latest", "stable", "next",
                "nightly", "edge"}
TAG_RE = re.compile(r"^v?\d+(?:\.\d+)*(?:[-+.][0-9A-Za-z.-]+)?$")


def gha_triggers(doc):
    on = doc.get("on") or doc.get("true") or doc.get('"on"')
    if on is None:
        return None
    if on.val:
        fl = flow_list(on.val)
        return fl if fl is not None else [on.val]
    return [c.key for c in on.keys()] + [c.val for c in on.items() if c.val]


def string_inputs(doc, action=False):
    """Names of the free-text inputs: `type: string` under on.workflow_call / on.workflow_dispatch
    (a dispatch input without a type is a string), or every input of an action."""
    out = set()
    if action:
        ins = doc.get("inputs")
        return {i.key for i in ins.keys()} if ins is not None else out
    on = doc.get("on") or doc.get("true") or doc.get('"on"')
    if on is None or on.val:
        return out
    for trig in ("workflow_dispatch", "workflow_call"):
        t = on.get(trig)
        ins = t.get("inputs") if t is not None else None
        for i in (ins.keys() if ins is not None else []):
            typ = (i.sval("type") or "").strip()
            if typ == "string" or (not typ and trig == "workflow_dispatch"):
                out.add(i.key)
    return out


def branchy(ref):
    """A ref that names a branch for certain: a well-known branch name, or one with a `/`."""
    return ref.lower() in BRANCH_NAMES or "/" in ref


def ref_kind(ref):
    """Classify a git ref: 'sha' (40 hex), 'short' (7-39 hex), 'tag', 'branch'."""
    if HEX40.match(ref):
        return "sha"
    if re.match(r"^[0-9a-f]{7,39}$", ref):
        return "short"
    if ref.lower() in BRANCH_NAMES or not TAG_RE.match(ref):
        return "branch"
    return "tag"


def check_uses(rep, rel, node):
    v = (node.val or "").strip()
    ln = node.line
    if not v or v.startswith("./") or "${{" in v:
        return
    if v.startswith("docker://"):
        sev = image_pin(v[len("docker://"):])
        if sev:
            rep.add("GHA003", rel, ln, "action image `%s` has no digest" % v, ref=v)
        check_registry(rep, rel, ln, image_parts(v[len("docker://"):])[0], "action image `%s`" % v)
        return
    if "@" not in v:
        return
    name, ref = v.rsplit("@", 1)
    k = ref_kind(ref)
    if k == "sha":
        return
    if branchy(ref):
        rep.add("GHA002", rel, ln, "action `%s` follows the branch `%s`" % (name, ref), ref=v)
    elif pin_actions():
        what = {"short": "a short commit", "tag": "the tag `%s`, which can be moved" % ref}.get(
            k, "`%s`, a tag or branch that can be moved" % ref)
        rep.add("GHA001", rel, ln, "action `%s` is pinned to %s" % (name, what), ref=v)


def check_gha_perms(rep, rel, node, top):
    if node is None:
        return
    if node.val is not None:
        if node.val.strip() == "write-all":
            rep.add("CI002", rel, node.line, "%spermissions: write-all grants every scope"
                    % ("top-level " if top else "job "), severity="crit")
        return
    if top:
        writes = sorted(c.key for c in node.keys() if (c.val or "").strip() == "write")
        if writes:
            rep.add("CI002", rel, node.line, "top-level permissions grant write to %s for every job"
                    % ", ".join(writes), severity="warn")


def check_inputs(rep, rel, ln, t, strs, where):
    """CI004 warn: a free-text input expanded into script text (choice, boolean, number: none)."""
    for m in INPUT_RE.finditer(t):
        if m.group(2) in strs:
            rep.add("CI004", rel, ln, "free-text input `%s` is expanded into the %s" % (m.group(1), where),
                    severity="warn")
            return


def check_run_lines(rep, rel, pairs, gitlab=False, strs=()):
    for ln, text in pairs:
        t = text.strip()
        if not t or t.startswith("#"):
            continue
        if not gitlab:
            m = CI004_RE.search(t)
            if m:
                rep.add("CI004", rel, ln, "untrusted `%s` is expanded into the script text"
                        % m.group(1), severity="crit")
            else:
                check_inputs(rep, rel, ln, t, strs, "script text")
            if "::add-mask::" not in t and GH_SECRET_ECHO.search(t):
                rep.add("CI005", rel, ln, "a secret is printed to the job log: `%s`" % snippet(t))
        else:
            m = GL_INJECT_RE.search(t)
            if m:
                rep.add("CI004", rel, ln, "commit or merge request text `$%s` runs through %s"
                        % (m.group(2), m.group(1)), severity="warn")
            if GL_SECRET_ECHO.search(t):
                rep.add("CI005", rel, ln, "a secret variable is printed to the job log: `%s`" % snippet(t))
        if ENV_DUMP.match(t):
            rep.add("CI005", rel, ln, "`%s` dumps every variable, secrets included, to the job log" % snippet(t, 40))


def scan_github(rep, rel, text, action=False):
    try:
        doc = parse_yaml(text)
    except YamlError as e:
        rep.add("CI000", rel, 0, "not scanned: %s" % e)
        return
    if action:
        runs = doc.get("runs")
        steps = runs.get("steps") if runs is not None else None
        strs = string_inputs(doc, action=True)
        for st in (steps.items() if steps is not None else []):
            scan_gha_step(rep, rel, st, False, strs)
        return
    jobs = doc.get("jobs")
    triggers = gha_triggers(doc)
    if jobs is None or triggers is None:
        rep.add("CI000", rel, 0, "not a GitHub Actions workflow (no on: and jobs:)")
        return
    perms = doc.get("permissions")
    if perms is None:
        loose = [j.key for j in jobs.keys() if j.get("permissions") is None]
        if loose:
            rep.add("CI001", rel, jobs.line, "no top-level permissions: the token gets the repository "
                    "default for job(s) %s" % ", ".join(loose))
    check_gha_perms(rep, rel, perms, True)
    prt = "pull_request_target" in triggers
    strs = string_inputs(doc)
    for job in jobs.keys():
        check_gha_perms(rep, rel, job.get("permissions"), False)
        cont = job.get("container")
        if cont is not None:
            img = cont.val if cont.val is not None else cont.sval("image")
            line = cont.line if cont.val is not None else (cont.get("image").line if cont.get("image") else cont.line)
            check_image(rep, "CI006", rel, line, img, "job container")
        svcs = job.get("services")
        for s in (svcs.keys() if svcs is not None else []):
            img = s.val if s.val is not None else s.sval("image")
            line = s.line if s.val is not None else (s.get("image").line if s.get("image") else s.line)
            check_image(rep, "CI006", rel, line, img, "service `%s` image" % s.key)
        coe = (job.sval("continue-on-error") or "").strip()
        if coe == "true" and SEC_RE.search(" %s %s " % (job.key, job.sval("name") or "")):
            rep.add("CI007", rel, job.get("continue-on-error").line,
                    "security job `%s` cannot fail the workflow (continue-on-error: true)" % job.key)
        steps = job.get("steps")
        for st in (steps.items() if steps is not None else []):
            scan_gha_step(rep, rel, st, prt, strs)


def pr_checkout(text):
    """True when a command of the line checks out the pull request head: `gh pr checkout X`, or
    `git fetch|checkout|pull|switch` with the head ref among that command's own arguments."""
    for c in sh_commands(mask_gha_expr(text)):
        hi, head = sh_head(c.words)
        if hi is None:
            continue
        args = c.words[hi + 1:]
        if head == "gh" and args[:2] == ["pr", "checkout"] and any(not a.startswith("-") for a in args[2:]):
            return True
        if head == "git":
            sub = next((a for a in args if not a.startswith("-")), "")
            if sub in ("fetch", "checkout", "pull", "switch") and any(PR_HEAD_ARG_RE.search(a) for a in args):
                return True
    return False


def scan_gha_step(rep, rel, st, prt, strs=()):
    uses = st.get("uses")
    run = st.get("run")
    if uses is not None:
        check_uses(rep, rel, uses)
    pairs = yaml_lines(run)
    with_ = st.get("with")
    if run is not None:
        check_run_lines(rep, rel, pairs, strs=strs)
        scan_shell(rep, rel, pairs)
    if with_ is not None and uses is not None and (uses.val or "").startswith("actions/github-script@"):
        script = with_.get("script")
        for ln, t in yaml_lines(script):
            m = CI004_RE.search(t)
            if m:
                rep.add("CI004", rel, ln, "untrusted `%s` is expanded into the github-script code"
                        % m.group(1), severity="crit")
            else:
                check_inputs(rep, rel, ln, t, strs, "github-script code")
    if prt:
        if uses is not None and (uses.val or "").startswith("actions/checkout@") and with_ is not None:
            ref = with_.get("ref")
            if ref is not None and HEADREF_RE.search(ref.val or ""):
                rep.add("CI003", rel, ref.line, "pull_request_target checks out the pull request head "
                        "(`ref: %s`) with the base repository's token and secrets" % snippet(ref.val, 80))
        for ln, t in logical_lines(pairs):
            if pr_checkout(t):
                rep.add("CI003", rel, ln, "pull_request_target checks out the pull request head: `%s`"
                        % snippet(t))
    coe = (st.sval("continue-on-error") or "").strip()
    if coe == "true":
        what = " ".join([st.sval("name") or "", st.sval("id") or "", (uses.val if uses is not None else "") or "",
                         (pairs[0][1] if pairs else "")])
        if SEC_RE.search(" %s " % what):
            rep.add("CI007", rel, st.get("continue-on-error").line,
                    "security step `%s` cannot fail the job (continue-on-error: true)"
                    % snippet(st.sval("name") or st.sval("id") or what.strip(), 60))


# ----------------------------------------------------------------------------- GitLab CI
GL_RESERVED = {"stages", "variables", "default", "include", "workflow", "image", "services",
               "before_script", "after_script", "cache", "spec"}
_GL_VARS = (r"CI_COMMIT_MESSAGE|CI_COMMIT_TITLE|CI_COMMIT_DESCRIPTION|CI_COMMIT_BRANCH|"
            r"CI_COMMIT_REF_NAME|CI_COMMIT_AUTHOR|CI_MERGE_REQUEST_TITLE|CI_MERGE_REQUEST_DESCRIPTION|"
            r"CI_MERGE_REQUEST_SOURCE_BRANCH_NAME")
GL_INJECT_RE = re.compile(r"\b(eval|sh\s+-c|bash\s+-c)\b.*\$\{?(" + _GL_VARS + r")\b")
GL_SECRET_ECHO = re.compile(r"\b(?:echo|printf)\b.*\$\{?(?:CI_JOB_TOKEN|CI_REGISTRY_PASSWORD|"
                            r"CI_DEPLOY_PASSWORD|[A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|"
                            r"PRIVATE_KEY)[A-Z0-9_]*)\b")
COMPONENT_VER = re.compile(r"^\d+(?:\.\d+){0,2}$")


def gitlab_include_entries(doc):
    """[(line, kind, value, node)] for every include entry: kind local|remote|project|component|template."""
    inc = doc.get("include") if doc is not None else None
    if inc is None:
        return []
    out = []

    def scalar(ln, v):
        v = (v or "").strip()
        if v.startswith(("http://", "https://")):
            out.append((ln, "remote", v, None))
        elif v:
            out.append((ln, "local", v, None))

    def mapping(n):
        for kind in ("local", "remote", "project", "component", "template"):
            c = n.get(kind)
            if c is not None:
                out.append((c.line, kind, c.val or "", n))
                return

    if inc.val is not None:
        fl = flow_list(inc.val)
        for v in (fl if fl is not None else [inc.val]):
            scalar(inc.line, v)
    elif inc.items():
        for it in inc.items():
            if it.val is not None:
                scalar(it.line, it.val)
            else:
                mapping(it)
    else:
        mapping(inc)
    return out


def gitlab_local_includes(doc):
    return [v for (_l, k, v, _n) in gitlab_include_entries(doc) if k == "local" and "*" not in v]


def scan_gitlab(rep, rel, text):
    try:
        doc = parse_yaml(text)
    except YamlError as e:
        rep.add("CI000", rel, 0, "not scanned: %s" % e)
        return
    if not doc.children:
        rep.add("CI000", rel, 0, "empty or not a YAML mapping")
        return
    for ln, kind, val, node in gitlab_include_entries(doc):
        if kind == "remote":
            rep.add("CI009", rel, ln, "remote include `%s` runs whatever that URL serves" % val)
            check_registry(rep, rel, ln, re.sub(r"^https?://([^/:]+).*$", r"\1", val), "remote include")
        elif kind == "project":
            ref = node.get("ref") if node is not None else None
            r = (ref.val or "").strip() if ref is not None else ""
            if not r:
                rep.add("CI008", rel, ln, "include of project `%s` has no ref: it follows the default "
                        "branch" % val, severity="crit")
            elif branchy(r):
                rep.add("CI008", rel, ref.line, "include of project `%s` follows the branch `%s`"
                        % (val, r), severity="crit", ref=r)
            elif not HEX40.match(r):
                rep.add("CI008", rel, ref.line, "include of project `%s` follows `%s`, a tag or branch, "
                        "not a commit sha" % (val, r), severity="warn", ref=r)
        elif kind == "component":
            ver = val.rsplit("@", 1)[1] if "@" in val else ""
            if not ver or ver.startswith("~") or not (COMPONENT_VER.match(ver) or HEX40.match(ver)):
                rep.add("CI008", rel, ln, "component `%s` is not pinned to a released version or a "
                        "commit sha" % val, severity="crit" if ver and branchy(ver) else "warn", ref=val)
    blocks = [("", doc)] + [("default", doc.get("default"))] + \
             [(j.key, j) for j in doc.keys() if j.key not in GL_RESERVED and not j.val]
    for name, node in blocks:
        if node is None:
            continue
        img = node.get("image")
        if img is not None:
            ref = img.val if img.val is not None else img.sval("name")
            line = img.line if img.val is not None else (img.get("name").line if img.get("name") else img.line)
            check_image(rep, "CI006", rel, line, ref, "%simage" % ("job `%s` " % name if name and name != "default" else ""))
        svcs = node.get("services")
        for it in (svcs.items() if svcs is not None else []):
            ref = it.val if it.val is not None else it.sval("name")
            line = it.line if it.val is not None else (it.get("name").line if it.get("name") else it.line)
            check_image(rep, "CI006", rel, line, ref, "service")
        pairs = []
        for k in ("before_script", "script", "after_script"):
            pairs.extend(yaml_lines(node.get(k)))
        if pairs:
            check_run_lines(rep, rel, pairs, gitlab=True)
            scan_shell(rep, rel, pairs)
        af = node.get("allow_failure")
        if name and af is not None and (af.val or "").strip() == "true":
            ext = node.get("extends")
            words = " ".join([name, (ext.val or "") if ext is not None else ""] +
                             [t for _l, t in pairs[:1]])
            if SEC_RE.search(" %s " % words):
                rep.add("CI007", rel, af.line, "security job `%s` cannot fail the pipeline "
                        "(allow_failure: true)" % name)


# ---------------------------------------------------------------------- Docker / compose
FROM_RE = re.compile(r"^\s*FROM\s+(?:--\S+\s+)*(?P<img>\S+)(?:\s+AS\s+(?P<name>\S+))?", re.I)
RUN_RE = re.compile(r"^\s*RUN\s+(?P<cmd>.*)$", re.I)
ADD_RE = re.compile(r"^\s*ADD\s+(?P<rest>.*)$", re.I)


def scan_dockerfile(rep, rel, text):
    stages = set()
    pairs = [(i + 1, t.rstrip("\r")) for i, t in enumerate(text.split("\n"))]
    for ln, line in logical_lines(pairs, docker=True):
        m = FROM_RE.match(line)
        if m:
            img = m.group("img")
            if m.group("name"):
                stages.add(m.group("name").lower())
            if img.lower() == "scratch" or img.lower() in stages or "$" in img:
                continue
            sev = image_pin(img)
            if sev == "crit":
                rep.add("DKR002", rel, ln, "base image `%s` has no tag or uses :latest" % img, ref=img)
            elif sev == "warn":
                rep.add("DKR001", rel, ln, "base image `%s` is pinned to a tag, not a digest" % img, ref=img)
            check_registry(rep, rel, ln, image_parts(img)[0], "base image `%s`" % img)
            continue
        m = RUN_RE.match(line)
        if m:
            scan_shell(rep, rel, [(ln, m.group("cmd"))])
            continue
        m = ADD_RE.match(line)
        if m and re.search(r"(?:^|\s)https?://", m.group("rest")) and "--checksum=" not in m.group("rest"):
            rep.add("SH002", rel, ln, "ADD of a URL without --checksum: `%s`" % snippet(line))


def scan_compose(rep, rel, text):
    try:
        doc = parse_yaml(text)
    except YamlError as e:
        rep.add("CI000", rel, 0, "not scanned: %s" % e)
        return
    svcs = doc.get("services")
    for s in (svcs.keys() if svcs is not None else []):
        img = s.get("image")
        if img is None or not img.val:
            continue
        # with `build:` the image is the name compose tags the local build with, pulled only
        # when pull_policy says so
        if s.get("build") is not None and (s.sval("pull_policy") or "").strip() not in ("always", "missing"):
            continue
        check_image(rep, "DKR003", rel, img.line, img.val, "service `%s` image" % s.key)


# ---------------------------------------------------------------------------- python
REQ_RE = re.compile(r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?\s*(?P<spec>[^;]*)")
VCS_RE = re.compile(r"(?:git|hg|svn|bzr)\+[a-z]+://\S+")
ARCHIVE_RE = re.compile(r"https?://\S+\.(?:whl|tar\.gz|tgz|zip)\b\S*")
PINNED_RE = re.compile(r"^\s*===?\s*[^\s,*;]+\s*$")


def vcs_split(token):
    """-> (url without the ref, ref, #fragment or None) of a pip VCS URL; the ref follows the
    last `@` of the path (after the host, so `ssh://git@host/` is not a ref)."""
    t, frag = (token.split("#", 1) + [None])[:2]
    m = re.match(r"^([a-z]+\+[a-z]+://[^/]*)(.*)$", t)
    head, path = (m.group(1), m.group(2)) if m else ("", t)
    if "@" not in path:
        return t, "", frag
    base, ref = path.rsplit("@", 1)
    return head + base, ref, frag


def vcs_ref(token):
    """-> (kind, ref) of a pip VCS URL: kind sha|short|tag|branch|none."""
    _base, ref, _frag = vcs_split(token)
    if not ref:
        return "none", ""
    if ref.startswith("refs/tags/"):
        return "tag", ref
    if ref.startswith("refs/heads/"):
        return "branch", ref
    return ref_kind(ref), ref


def check_vcs(rep, rid, rel, ln, token, where):
    kind, ref = vcs_ref(token)
    if kind == "sha":
        return
    if kind in ("none", "branch"):
        rep.add(rid, rel, ln, "%s `%s` follows %s" % (where, token, "the default branch" if kind == "none"
                                                     else "the branch `%s`" % ref), severity="crit", ref=token)
    else:
        rep.add(rid, rel, ln, "%s `%s` is pinned to `%s`, not a commit sha" % (where, token, ref),
                severity="warn", ref=token)


def scan_requirements(rep, rel, text):
    pairs = [(i + 1, t.rstrip("\r")) for i, t in enumerate(text.split("\n"))]
    unhashed = []
    for ln, line in logical_lines(pairs):
        line = strip_comment(line).strip()
        if not line:
            continue
        hashed = "--hash" in line
        m = re.match(r"^(?:-i|--index-url|--extra-index-url)[\s=]+(\S+)", line)
        if m:
            host = re.sub(r"^[a-z+]+://(?:[^@/]*@)?([^/:]+).*$", r"\1", m.group(1))
            check_registry(rep, rel, ln, host, "package index")
            continue
        v = VCS_RE.search(line)
        if v:
            check_vcs(rep, "PIP002", rel, ln, v.group(0), "requirement")
            continue
        if line.startswith("-"):
            continue
        a = ARCHIVE_RE.search(line)
        if a:
            if not hashed:
                rep.add("PIP002", rel, ln, "URL requirement `%s` has no --hash" % a.group(0),
                        severity="warn", ref=a.group(0))
            continue
        if line.startswith((".", "/")) or line.startswith("file:"):
            continue
        m = REQ_RE.match(line)
        if not m:
            continue
        spec = re.split(r"\s--", m.group("spec"))[0]
        if not PINNED_RE.match(spec):
            rep.add("PIP001", rel, ln, "`%s` is not pinned to an exact version" % snippet(line.split(" --")[0], 80))
        elif not hashed:
            unhashed.append(ln)
    if unhashed:
        rep.add("PIP003", rel, unhashed[0], "%d pinned requirement(s) have no --hash" % len(unhashed))


def toml_sections(text):
    """[(line, section, key_line, raw)] — every non-blank line with its current [section]."""
    sec, out = "", []
    for i, raw in enumerate(text.split("\n"), 1):
        s = raw.strip()
        m = re.match(r"^\[\[?\s*([^\]]+?)\s*\]\]?\s*(?:#.*)?$", s)
        if m:
            sec = re.sub(r"\s+", "", m.group(1)).replace('"', "").replace("'", "")
            continue
        if s and not s.startswith("#"):
            out.append((i, sec, raw))
    return out


def toml_strings(s):
    return re.findall(r'"((?:[^"\\]|\\.)*)"|\'([^\']*)\'', s)


def _strings_removed(s):
    return re.sub(r'"(?:[^"\\]|\\.)*"|\'[^\']*\'', "", s)


def scan_pyproject(rep, rel, text, locked):
    loose = []
    in_arr = False
    for ln, sec, raw in toml_sections(text):
        s = strip_comment(raw).strip()
        body = None
        if in_arr:
            body = s
        elif (sec == "project" and re.match(r"^dependencies\s*=", s)) or (
                sec == "project.optional-dependencies" and re.match(r"^[\w.-]+\s*=\s*\[", s)):
            body = s.split("=", 1)[1]
        if body is not None:
            for dq, sq in toml_strings(body):
                req = dq or sq
                v = VCS_RE.search(req)
                if v:
                    check_vcs(rep, "PIP002", rel, ln, v.group(0), "dependency")
                    continue
                m = REQ_RE.match(req)
                if m and "@" not in req and not PINNED_RE.match(m.group("spec")):
                    loose.append((ln, m.group("name")))
            bare = _strings_removed(body)
            in_arr = (in_arr or "[" in bare) and "]" not in bare
            continue
        if sec in ("tool.poetry.dependencies", "tool.poetry.dev-dependencies") or \
                re.match(r"^tool\.poetry\.group\.[\w-]+\.dependencies$", sec):
            m = re.match(r"^([\w.-]+)\s*=\s*(.*)$", s)
            if not m or m.group(1) == "python":
                continue
            val = m.group(2)
            if val.startswith("{"):
                g = re.search(r'\bgit\s*=\s*"([^"]+)"', val)
                if g and not re.search(r"\brev\s*=", val):
                    tag = re.search(r"\btag\s*=", val)
                    rep.add("PIP002", rel, ln, "git dependency `%s` has no rev" % m.group(1),
                            severity="warn" if tag else "crit", ref=g.group(1))
                    continue
                vm = re.search(r'\bversion\s*=\s*"([^"]+)"', val)
                spec = vm.group(1) if vm else ""
            else:
                spec = unquote(val)
            if spec and not re.match(r"^=?=?\s*\d[\w.]*$", spec):
                loose.append((ln, m.group(1)))
    if loose and not locked:
        rep.add("PIP004", rel, loose[0][0], "%d dependency range(s) (%s) and no lockfile next to it"
                % (len(loose), ", ".join(n for _l, n in loose[:3])))


# ---------------------------------------------------------------------------------- npm
NPM_EXACT = re.compile(r"^v?\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")


def npm_line(lines, name, spec):
    pat = re.compile(r'"%s"\s*:\s*"%s"' % (re.escape(name), re.escape(spec)))
    for i, t in enumerate(lines, 1):
        if pat.search(t):
            return i
    return 0


NPM_LOCKS = ("package-lock.json", "npm-shrinkwrap.json", "pnpm-lock.yaml", "yarn.lock", "bun.lock", "bun.lockb")


def scan_package_json(rep, rel, text, locked):
    try:
        doc = json.loads(text)
    except ValueError:
        return
    if not isinstance(doc, dict):
        return
    lines = text.split("\n")
    ranges = []
    for sec in ("dependencies", "devDependencies", "optionalDependencies"):
        deps = doc.get(sec)
        if not isinstance(deps, dict):
            continue
        for name in sorted(deps):
            spec = deps[name]
            if not isinstance(spec, str):
                continue
            s = spec.strip()
            ln = npm_line(lines, name, spec)
            if s.startswith(("file:", "link:", "workspace:", "portal:", "patch:")):
                continue
            if s.startswith("npm:"):  # an alias (`npm:@scope/pkg@^1`) comes from the registry
                body = s[4:]
                at = body.find("@", 1)
                ver = body[at + 1:] if at > 0 else ""
                if not NPM_EXACT.match(ver):
                    ranges.append((ln, "%s %s" % (name, spec)))
                continue
            if s.startswith(("git+", "git://", "github:", "gitlab:", "bitbucket:", "gist:")) or \
                    re.match(r"^[\w.-]+/[\w.-]+(?:#.*)?$", s):
                ref = s.split("#", 1)[1] if "#" in s else ""
                if ref.startswith("semver:"):
                    kind = "tag"
                else:
                    kind = ref_kind(ref) if ref else "none"
                if kind == "sha":
                    continue
                sev = "crit" if kind in ("none", "branch") and not locked else "warn"
                rep.add("NPM002", rel, ln, "`%s` comes from git (`%s`) without a commit sha%s"
                        % (name, spec, "; the lockfile pins the commit it resolved" if locked else ""),
                        severity=sev, ref=spec)
                continue
            if s.startswith(("http://", "https://")):
                rep.add("NPM002", rel, ln, "`%s` comes from a URL (`%s`)" % (name, spec), severity="warn", ref=spec)
                continue
            if not NPM_EXACT.match(s):
                ranges.append((ln, "%s %s" % (name, spec)))
    if ranges:
        ranges.sort()
        rep.add("NPM001", rel, ranges[0][0], "%d dependency range(s) (%s)%s"
                % (len(ranges), ", ".join(r for _l, r in ranges[:3]),
                   "" if locked else " and no lockfile"), severity="info" if locked else "warn")


def scan_npmrc(rep, rel, text):
    for i, raw in enumerate(text.split("\n"), 1):
        m = re.match(r"^\s*(?:@[\w.-]+:)?registry\s*=\s*(\S+)", raw)
        if m:
            host = re.sub(r"^[a-z]+://([^/:]+).*$", r"\1", m.group(1))
            check_registry(rep, rel, i, host, "npm registry")


# ----------------------------------------------------------------------------- go, cargo
def scan_gomod(rep, rel, text, has_sum):
    lines = text.split("\n")
    requires = False
    block = None
    for i, raw in enumerate(lines, 1):
        s = raw.split("//", 1)[0].strip()
        if not s:
            continue
        m = re.match(r"^(require|replace)\s*\($", s)
        if m:
            block = m.group(1)
            continue
        if s == ")":
            block = None
            continue
        kind, body = block, s
        m = re.match(r"^(require|replace)\s+(.*)$", s)
        if m:
            kind, body = m.group(1), m.group(2)
        if kind == "require":
            requires = True
        elif kind == "replace" and "=>" in body:
            target = body.split("=>", 1)[1].strip()
            if target.startswith((".", "/")):
                rep.add("GO003", rel, i, "replace points at the local path `%s`" % target.split()[0])
    if requires and not has_sum:
        rep.add("GO001", rel, 1, "go.mod requires modules but there is no go.sum next to it")


CARGO_DEP_SEC = re.compile(r"^(?:workspace\.)?(?:target\..+\.)?(?:dev-|build-)?dependencies$")
CARGO_DEP_TABLE = re.compile(r"^(?:workspace\.)?(?:target\..+\.)?(?:dev-|build-)?dependencies\.([\w-]+)$")


def scan_cargo(rep, rel, text, locked=False):
    tables = {}
    for ln, sec, raw in toml_sections(text):
        s = strip_comment(raw).strip()
        if CARGO_DEP_SEC.match(sec):
            m = re.match(r"^([\w-]+)\s*=\s*\{(.*)\}\s*$", s)
            if m:
                cargo_git(rep, rel, m.group(1), {k: (ln, v) for k, v in
                                                 re.findall(r'\b(git|rev|tag|branch)\s*=\s*"([^"]*)"', m.group(2))},
                          locked)
            continue
        m = CARGO_DEP_TABLE.match(sec)
        if m:
            km = re.match(r'^(git|rev|tag|branch)\s*=\s*"([^"]*)"', s)
            if km:
                tables.setdefault((sec, m.group(1)), {})[km.group(1)] = (ln, km.group(2))
    for (_sec, name), keys in sorted(tables.items()):
        cargo_git(rep, rel, name, keys, locked)


def cargo_git(rep, rel, name, keys, locked=False):
    if "git" not in keys or "rev" in keys:
        return
    ln, url = keys["git"]
    if "tag" in keys:
        rep.add("CGO001", rel, ln, "git dependency `%s` is pinned to the tag `%s`, not a rev"
                % (name, keys["tag"][1]), severity="warn", ref=url)
    else:
        what = "the branch `%s`" % keys["branch"][1] if "branch" in keys else "the default branch"
        rep.add("CGO001", rel, ln, "git dependency `%s` follows %s%s"
                % (name, what, "; Cargo.lock pins the commit it resolved" if locked else ""),
                severity="warn" if locked else "crit", ref=url)


# ------------------------------------------------------------------------------- detect
def start_dir(a, command):
    d = a.dir
    tree = Tree(d)
    tools = installed_tools()
    banner(d, tree.ecosystems(), tools)
    rep = Report(command, d, tree.ecosystems(), tools)
    if tree.truncated:
        rep.add("SUP001", "", 0, "scan stopped at %d files; the rest of %s was not scanned" % (tree.cap, d))
    for rel, why in tree.unreadable:
        rep.add("SUP002", rel, 0, "directory not readable (%s): nothing below it was scanned" % why)
    return tree, rep


def cmd_detect(a):
    tree, rep = start_dir(a, "detect")
    rep.data["ecosystems"] = tree.summary()
    rep.data["files_scanned"] = len(tree.files)
    rep.data["skipped_large"] = tree.large
    if tree.outside:
        rep.data["skipped_symlinks_outside"] = tree.outside
    rep.forced_exit = 0
    return rep


def pdir(rel):
    return rel.rsplit("/", 1)[0] if "/" in rel else ""


def has_lock(tree, rel, names):
    """A lockfile with one of NAMES next to REL or in any parent directory up to DIR."""
    d = rel.rsplit("/", 1)[0] if "/" in rel else ""
    while True:
        for n in names:
            if (d + "/" + n if d else n) in tree.files:
                return True
        if not d:
            return False
        d = d.rsplit("/", 1)[0] if "/" in d else ""


def scan_tree(tree, rep):
    for rel in tree.files:
        roles = tree.roles.get(rel, ())
        text = None
        if roles:
            text = tree.read(rel)
            if text is None:
                rep.add("SUP002", rel, 0, "file not readable: not scanned")
                continue
        for eco, role in roles:
            base = rel.rsplit("/", 1)[-1]
            if eco == "github-actions":
                scan_github(rep, rel, text, action=(role == "action"))
            elif eco == "gitlab-ci":
                scan_gitlab(rep, rel, text)
            elif role == "dockerfile":
                scan_dockerfile(rep, rel, text)
            elif role == "compose":
                scan_compose(rep, rel, text)
            elif eco == "pip" and role == "manifest" and base.endswith(".txt"):
                scan_requirements(rep, rel, text)
            elif eco == "pip" and base == "pyproject.toml":
                locked = any(pdir(r) == pdir(rel) for r in tree.of("lockfile", "pip"))
                scan_pyproject(rep, rel, text, locked)
            elif eco == "npm" and role == "manifest":
                scan_package_json(rep, rel, text, has_lock(tree, rel, NPM_LOCKS))
            elif eco == "npm" and role == "config":
                scan_npmrc(rep, rel, text)
            elif eco == "go" and role == "manifest":
                d = rel.rsplit("/", 1)[0] + "/" if "/" in rel else ""
                scan_gomod(rep, rel, text, (d + "go.sum") in tree.files)
            elif eco == "cargo" and role == "manifest":
                scan_cargo(rep, rel, text, has_lock(tree, rel, ("Cargo.lock",)))
            elif eco == "shell":
                scan_shell(rep, rel, [(i + 1, t.rstrip("\r")) for i, t in enumerate(text.split("\n"))])


# --------------------------------------------------------------------------------- pins
def cmd_pins(a):
    if a.apply:
        return apply_pins(a)
    tree, rep = start_dir(a, "pins")
    scan_tree(tree, rep)
    rep.keep(PIN_RULES)
    rep.data["files_scanned"] = len(tree.files)
    return rep


def _load_apply(path):
    try:
        with open(path, encoding="utf-8") as fh:
            entries = json.load(fh)
    except OSError as e:
        raise AccessError("%s: cannot read the apply file (%s)" % (path, e.strerror or e))
    except ValueError as e:
        raise AccessError("%s: not UTF-8 JSON (%s); expected [{\"file\", \"line\", \"old\", \"new\"}]" % (path, e))
    if not isinstance(entries, list):
        raise AccessError("%s: expected a JSON list of {\"file\", \"line\", \"old\", \"new\"}" % path)
    return entries


IMAGE_PIN_RULES = {"DKR001", "DKR002", "DKR003", "CI006", "GHA003"}
_SHA40 = r"[0-9a-f]{40}"
_TOKEN_CH = re.compile(rb"[\w.:@/-]")


def pin_problem(rid, old, new):
    """None when NEW pins OLD (the ref of a RID finding) without renaming it, else what NEW must be."""
    if rid in IMAGE_PIN_RULES:
        pre = "docker://" if old.startswith("docker://") else ""
        repo = image_parts(old[len(pre):])[1]
        if re.match(r"^%s(?::\w[\w.-]{0,127})?@sha256:[0-9a-f]{64}$" % re.escape(pre + repo), new):
            return None
        return "new must be %s[:TAG]@sha256:<64 hex>" % (pre + repo)
    if rid in ("GHA001", "GHA002"):
        name = old.rsplit("@", 1)[0]
        return None if re.match(r"^%s@%s$" % (re.escape(name), _SHA40), new) else \
            "new must be %s@<40-hex sha>" % name
    if rid == "PIP002" and VCS_RE.match(old):
        base, _ref, frag = vcs_split(old)
        tail = "#" + frag if frag is not None else ""
        return None if re.match(r"^%s@%s%s$" % (re.escape(base), _SHA40, re.escape(tail)), new) else \
            "new must be %s@<40-hex sha>%s" % (base, tail)
    if rid == "NPM002" and not old.startswith(("http://", "https://")):
        base = old.split("#", 1)[0]
        return None if re.match(r"^%s#%s$" % (re.escape(base), _SHA40), new) else \
            "new must be %s#<40-hex sha>" % base
    if rid == "CI008":
        if "@" in old:  # a component
            name = old.rsplit("@", 1)[0]
            v = new[len(name) + 1:] if new.startswith(name + "@") else ""
            return None if HEX40.match(v) or COMPONENT_VER.match(v) else \
                "new must be %s@<40-hex sha> or %s@X.Y.Z" % (name, name)
        return None if HEX40.match(new) else "new must be a 40-hex commit sha"
    if rid == "GO002":
        name = old.rsplit("@", 1)[0]
        return None if re.match(r"^%s@(?:%s|v\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)$" % (re.escape(name), _SHA40), new) \
            else "new must be %s@vX.Y.Z or %s@<40-hex sha>" % (name, name)
    return "%s findings are not rewritten by --apply; edit the file by hand (see the finding's fix)" % rid


def token_spans(line, ob):
    """Start offsets of OB in LINE where it stands as a whole token (no [\\w.:@/-] neighbour)."""
    out, i = [], line.find(ob)
    while i >= 0:
        before = line[i - 1:i]
        after = line[i + len(ob):i + len(ob) + 1]
        if not (before and _TOKEN_CH.match(before)) and not (after and _TOKEN_CH.match(after)):
            out.append(i)
        i = line.find(ob, i + 1)
    return out


def symlink_in_path(root, rel):
    """The first component of REL under ROOT that is a symlink, or None."""
    cur = root
    for part in rel.split("/"):
        cur = os.path.join(cur, part)
        if os.path.islink(cur):
            return cur
    return None


def _umask():
    m = os.umask(0)
    os.umask(m)
    return m


def atomic_write(path, data, mode=None):
    """Write DATA to a temp file beside PATH and rename it over PATH (mode kept or MODE)."""
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix="." + os.path.basename(path) + ".", suffix=".supply-tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.chmod(tmp, mode if mode is not None else 0o666 & ~_umask())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_all(changes):
    """All-or-nothing: CHANGES [(rel, full, original bytes, new bytes)]. Every file is checked
    writable and staged first; each is re-read and compared just before its rename; a failure
    part-way restores the files already replaced. -> nothing, or AccessError."""
    temps, done = {}, []
    try:
        for rel, full, _o, _n in changes:
            if not os.access(full, os.W_OK) or not os.access(os.path.dirname(full) or ".", os.W_OK | os.X_OK):
                raise AccessError("%s is not writable (or its directory is not)" % rel)
        for rel, full, _o, new in changes:
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(full), prefix="." + os.path.basename(full) + ".",
                                       suffix=".supply-tmp")
            temps[rel] = tmp
            with os.fdopen(fd, "wb") as fh:
                fh.write(new)
            shutil.copymode(full, tmp)
        fail_after = _int(os.environ.get("SUPPLY_TEST_FAIL_AFTER"), -1)
        for rel, full, orig, _n in changes:
            if len(done) == fail_after:
                raise OSError(errno.EIO, "injected failure (SUPPLY_TEST_FAIL_AFTER=%d)" % fail_after, rel)
            with open(full, "rb") as fh:
                if fh.read() != orig:
                    raise AccessError("%s changed while --apply ran" % rel)
            os.replace(temps.pop(rel), full)
            done.append((rel, full, orig))
    except (OSError, AccessError) as e:
        why = str(e) if isinstance(e, AccessError) else "%s: %s" % (getattr(e, "filename", "") or "write",
                                                                   e.strerror or e)
        lost = []
        for rel, full, orig in reversed(done):
            try:
                atomic_write(full, orig, stat.S_IMODE(os.stat(full).st_mode))
            except OSError:
                lost.append(rel)
        for tmp in temps.values():
            try:
                os.unlink(tmp)
            except OSError:
                pass
        if lost:
            raise AccessError("pins --apply: %s; rolling back failed for %s — restore them with `git checkout -- "
                              "FILE` and rerun" % (why, ", ".join(lost)))
        raise AccessError("pins --apply: %s; nothing written (%d file(s) rolled back) — fix the cause "
                          "and rerun" % (why, len(done)))


def apply_pins(a):
    root = a.dir
    entries = _load_apply(a.apply)
    tree = Tree(root)
    tools = installed_tools()
    banner(root, tree.ecosystems(), tools)
    current = Report("pins", root)
    scan_tree(tree, current)
    refs = {}
    for f in current.findings:
        if f.get("ref"):
            refs.setdefault((f["file"], f["line"]), {})[f["ref"]] = f["id"]
    errors, skipped, applied = [], [], []
    files = {}  # rel -> (full, original bytes, [lines])
    for n, e in enumerate(entries):
        where = "entry %d" % n
        if not isinstance(e, dict):
            errors.append("%s: not an object" % where)
            continue
        f, line, old, new = e.get("file"), e.get("line"), e.get("old"), e.get("new")
        if not isinstance(f, str) or not f or "\x00" in f or f.startswith("/") or ".." in f.split("/") \
                or "\\" in f or "" in f.split("/"):
            errors.append("%s: file must be a relative path inside DIR, without `..` or NUL" % where)
            continue
        if not isinstance(line, int) or isinstance(line, bool) or line < 1:
            errors.append("%s (%s): line must be a positive integer" % (where, f))
            continue
        if not isinstance(old, str) or not old or not isinstance(new, str) or not new:
            errors.append("%s (%s:%d): old and new must be non-empty strings" % (where, f, line))
            continue
        if any(ch in x for x in (old, new) for ch in ("\n", "\r", "\x00")):
            errors.append("%s (%s:%d): old and new must be single-line, without NUL" % (where, f, line))
            continue
        if old == new:
            errors.append("%s (%s:%d): old and new are identical" % (where, f, line))
            continue
        link = symlink_in_path(root, f)
        if link:
            errors.append("%s: %s goes through the symlink %s; --apply writes regular files inside DIR only"
                          % (where, f, os.path.relpath(link, root).replace(os.sep, "/")))
            continue
        if f not in tree.roles:
            errors.append("%s: %s is not a file `supply pins` scans (workflows, CI files, Dockerfiles, "
                          "compose, manifests, scripts; never .git); nothing to pin there" % (where, f))
            continue
        if f not in files:
            full = tree.path(f)
            if not tree.inside(os.path.realpath(full)):
                errors.append("%s: %s resolves outside DIR" % (where, f))
                continue
            try:
                with open(full, "rb") as fh:
                    raw = fh.read()
            except OSError as ex:
                errors.append("%s: %s: cannot read (%s)" % (where, f, ex.strerror or ex))
                continue
            files[f] = (full, raw, raw.split(b"\n"))
        lines = files[f][2]
        if line > len(lines):
            errors.append("%s: %s has no line %d" % (where, f, line))
            continue
        cur = lines[line - 1]
        if not pin_actions() and re.search(rb"^\s*-?\s*uses\s*:", cur):
            skipped.append({"file": f, "line": line, "old": red_text(old),
                            "reason": "supply_chain.pin_actions is false"})
            continue
        rid = refs.get((f, line), {}).get(old)
        if rid is None:
            errors.append("%s: `%s` is not the ref of a current finding on %s:%d (copy `ref` from "
                          "`supply pins DIR --json`)" % (where, old, f, line))
            continue
        why = pin_problem(rid, old, new)
        if why:
            errors.append("%s (%s:%d, %s): %s" % (where, f, line, rid, why))
            continue
        ob = old.encode("utf-8")
        spans = token_spans(cur, ob)
        if len(spans) != 1:
            errors.append("%s: `%s` occurs %d times as a whole token on %s:%d (must be exactly once)"
                          % (where, old, len(spans), f, line))
            continue
        lines[line - 1] = cur[:spans[0]] + new.encode("utf-8") + cur[spans[0] + len(ob):]
        applied.append({"file": f, "line": line, "old": red_text(old), "new": red_text(new)})
    if errors:
        raise AccessError("pins --apply: nothing written —\n  " + "\n  ".join(red_text(x) for x in errors))
    changes = [(rel, files[rel][0], files[rel][1], b"\n".join(files[rel][2]))
               for rel in sorted({x["file"] for x in applied})]
    write_all([c for c in changes if c[2] != c[3]])
    tree = Tree(root)
    rep = Report("pins", root, tree.ecosystems(), tools)
    for rel, why in tree.unreadable:
        rep.add("SUP002", rel, 0, "directory not readable (%s): nothing below it was scanned" % why)
    if tree.truncated:
        rep.add("SUP001", "", 0, "scan stopped at %d files; the rest of %s was not scanned" % (tree.cap, root))
    scan_tree(tree, rep)
    rep.keep(PIN_RULES)
    rep.data["applied"] = applied
    if skipped:
        rep.data["skipped"] = skipped
    rep.data["files_scanned"] = len(tree.files)
    return rep


# ----------------------------------------------------------------------------------- ci
def file_kind(path, text):
    rel = path.replace(os.sep, "/")
    base = rel.rsplit("/", 1)[-1]
    low = base.lower()
    if re.search(r"(^|/)\.github/workflows/[^/]+\.ya?ml$", rel):
        return "github-workflow"
    if low in ("action.yml", "action.yaml"):
        return "github-action"
    if low.endswith(".gitlab-ci.yml"):
        return "gitlab-ci"
    if is_dockerfile(base):
        return "dockerfile"
    if re.match(r"^(docker-)?compose([.-][\w.-]+)?\.ya?ml$", low):
        return "compose"
    if low.endswith((".sh", ".bash", ".mk")) or low in _SHELL_NAMES:
        return "shell"
    if low.endswith((".yml", ".yaml")):
        if re.search(r"(?m)^jobs:", text) and re.search(r"(?m)^(on|\"on\"|'on'|true):", text):
            return "github-workflow"
        if re.search(r"(?m)^(stages|include):", text) or re.search(r"(?m)^\s+script:", text):
            return "gitlab-ci"
    return "unknown"


def cmd_ci(a):
    ignore = set()
    for part in (a.ignore or "").split(","):
        part = part.strip().upper()
        if part:
            if part not in RULES:
                die("supply ci: unknown rule id %r in --ignore; pass ids from this list, comma-separated: %s"
                    % (part, ", ".join(sorted(RULES))), 1)
            ignore.add(part)
    texts, kinds = {}, []
    for p in a.files:
        try:
            with open(p, "rb") as fh:
                texts[p] = fh.read().decode("utf-8", "replace")
        except OSError as e:
            raise AccessError("%s: not readable (%s)" % (p, e.strerror or e))
    ecos = set()
    for p in a.files:
        k = file_kind(p, texts[p])
        kinds.append({"file": p, "kind": k})
        ecos.add({"github-workflow": "github-actions", "github-action": "github-actions",
                  "gitlab-ci": "gitlab-ci", "dockerfile": "docker", "compose": "docker",
                  "shell": "shell"}.get(k, ""))
    ecos.discard("")
    tools = installed_tools()
    banner("-", sorted(ecos), tools)
    rep = Report("ci", "-", sorted(ecos), tools)
    for row in kinds:
        p, k, text = row["file"], row["kind"], texts[row["file"]]
        if k == "github-workflow":
            scan_github(rep, p, text)
        elif k == "github-action":
            scan_github(rep, p, text, action=True)
        elif k == "gitlab-ci":
            scan_gitlab(rep, p, text)
        elif k == "dockerfile":
            scan_dockerfile(rep, p, text)
        elif k == "compose":
            scan_compose(rep, p, text)
        elif k == "shell":
            scan_shell(rep, p, [(i + 1, t.rstrip("\r")) for i, t in enumerate(text.split("\n"))])
        else:
            rep.add("CI000", p, 0, "not a recognised CI file", fix="pass a GitHub workflow or action, a "
                    ".gitlab-ci.yml (or a file it includes), a Dockerfile, a compose file or a shell script")
    unscanned = {f["file"] for f in rep.findings if f["id"] == "CI000"}
    if all(p in unscanned for p in a.files):
        rep.forced_exit = 3
        sys.stderr.write("supply ci: no file could be scanned (every one is CI000); pass a workflow, "
                         ".gitlab-ci.yml, Dockerfile, compose file or shell script, or check it with its "
                         "own linter\n")
    rep.keep(CI_RULES - ignore)
    rep.data["files"] = kinds
    if ignore:
        rep.data["ignored_rules"] = sorted(ignore)
    return rep


# -------------------------------------------------------------------------------- audit
OSV_ECO = {"pypi": "pip", "npm": "npm", "go": "go", "crates.io": "cargo"}
SBOM_NAME_RE = re.compile(r"(?:\.spdx\.json|\.cdx\.json|(?:^|/)bom\.json)$")


def _vkey(v):
    return [(0, int(p), "") if p.isdigit() else (1, 0, p) for p in re.split(r"[.+-]", str(v).lstrip("v=<>~^ "))]


def rel_to(path, root):
    if not path:
        return ""
    if os.path.isabs(path):
        try:
            r = os.path.relpath(path, os.path.abspath(root))
        except ValueError:
            return os.path.basename(path)
        return os.path.basename(path) if r.startswith("..") else r.replace(os.sep, "/")
    return path.replace(os.sep, "/")


def line_of(tree, rel, name):
    if not rel or not name or tree is None:
        return 0
    text = tree.read(rel) or ""
    pat = re.compile(r"(?i)(?:^|[^A-Za-z0-9_.-])%s(?:[^A-Za-z0-9_.-]|$)" % re.escape(name))
    for i, t in enumerate(text.split("\n"), 1):
        if pat.search(t):
            return i
    return 0


def sev_word(s):
    s = (s or "").strip().upper()
    if s in ("CRITICAL", "HIGH"):
        return "crit"
    if s in ("MODERATE", "MEDIUM"):
        return "warn"
    if s in ("LOW", "INFO", "NONE"):
        return "info"
    return None


SEV_RANK = {"crit": 0, "warn": 1, "info": 2}


def osv_group_severity(group, vulns):
    try:
        f = float(group.get("max_severity"))
        return "crit" if f >= 7 else ("warn" if f >= 4 else "info")
    except (TypeError, ValueError):
        pass
    best = None
    for vid in group.get("ids") or []:
        w = sev_word(((vulns.get(vid) or {}).get("database_specific") or {}).get("severity"))
        if w and (best is None or SEV_RANK[w] < SEV_RANK[best]):
            best = w
    return best or "warn"


def osv_fixed(ids, vulns, pkg):
    fixed = set()
    for vid in ids:
        for aff in (vulns.get(vid) or {}).get("affected") or []:
            pn = (aff.get("package") or {}).get("name")
            if pn and pkg and pn.lower() != pkg.lower():
                continue
            for rng in aff.get("ranges") or []:
                for ev in rng.get("events") or []:
                    if isinstance(ev, dict) and ev.get("fixed"):
                        fixed.add(str(ev["fixed"]))
    return sorted(fixed, key=_vkey)


def vuln_message(eco, name, ver, primary, aliases, summary, fixed):
    al = " (%s)" % ", ".join(aliases) if aliases else ""
    fx = "fixed in %s" % ", ".join(fixed) if fixed else "no fixed version published"
    return "%s %s %s: %s%s — %s; %s" % (eco, name, ver or "?", primary, al, snippet(summary or "no summary", 120), fx)


def vuln_fix(name, fixed):
    if fixed:
        return ("upgrade %s to %s (/audit-deps applies patch and minor upgrades; a major upgrade is a "
                "human decision)" % (name, fixed[0]))
    return "no fix published: remove or replace the dependency, mitigate, or accept it with a reason " \
           "(references/vuln-triage.md)"


def parse_osv(rep, out, root, tree):
    try:
        doc = json.loads(out)
    except ValueError:
        raise AccessError("osv-scanner printed no JSON; the supported version is 2.7.0 "
                          "(harness install osv-scanner)")
    with tool_output("osv-scanner", "the supported version is 2.7.0 (harness install osv-scanner)"):
        return _parse_osv(rep, doc, root, tree)


def _parse_osv(rep, doc, root, tree):
    counts = {}
    if not isinstance(doc, dict):
        raise TypeError("the top level is not an object")
    for r in doc.get("results") or []:
        rel = rel_to((r.get("source") or {}).get("path", ""), root)
        for p in r.get("packages") or []:
            pk = p.get("package") or {}
            name, ver = pk.get("name", ""), pk.get("version", "")
            eco = OSV_ECO.get(str(pk.get("ecosystem", "")).lower(), str(pk.get("ecosystem", "")).lower())
            counts[eco] = counts.get(eco, 0) + 1
            vulns = {v.get("id"): v for v in p.get("vulnerabilities") or [] if isinstance(v, dict) and v.get("id")}
            groups = p.get("groups") or [{"ids": [vid], "aliases": (v.get("aliases") or []), "max_severity": ""}
                                         for vid, v in sorted(vulns.items())]
            for g in groups:
                ids = sorted(g.get("ids") or [])
                if not ids:
                    continue
                primary = ids[0]
                aliases = sorted((set(g.get("aliases") or []) | set(ids)) - {primary})
                summary = (vulns.get(primary) or {}).get("summary") or next(
                    ((vulns.get(i) or {}).get("summary") for i in ids if (vulns.get(i) or {}).get("summary")), "")
                fixed = osv_fixed(ids, vulns, name)
                rep.add("OSV001", rel, line_of(tree, rel, name),
                        vuln_message(eco, name, ver, primary, aliases, summary, fixed),
                        severity=osv_group_severity(g, vulns), fix=vuln_fix(name, fixed))
    return counts


def fb_npm(rep, tree, root, dirs, offline):
    rows = []
    for d, lock in dirs:
        if offline:
            rows.append(("offline", 0))
            continue
        rc, out, err = _run("npm", ["audit", "--json", "--audit-level=none"], cwd=os.path.join(root, *d.split("/")) if d else root)
        try:
            doc = json.loads(out)
        except ValueError:
            doc = None
        if rc not in (0, 1) or not isinstance(doc, dict) or "error" in doc:
            rep.add("AUD003", lock, 0, "npm audit failed (exit %d): %s" % (rc, first_line(err) or "no JSON"))
            rows.append(("error", 0))
            continue
        with tool_output("npm audit"):
            rows.append(_npm_findings(rep, tree, lock, doc))
    return rows


def _npm_findings(rep, tree, lock, doc):
    vulns = doc.get("vulnerabilities") or {}
    n = 0
    for name in sorted(vulns):
        v = vulns[name] or {}
        advs = [x for x in v.get("via") or [] if isinstance(x, dict)]
        if not advs:
            continue
        n += 1
        ids = sorted({re.sub(r"^.*/", "", a.get("url") or "") or str(a.get("source", "")) for a in advs})
        sev = min((sev_word(a.get("severity")) or "warn" for a in advs), key=lambda s: SEV_RANK[s])
        title = sorted(a.get("title") or "" for a in advs)[0]
        fa = v.get("fixAvailable")
        fixed = [str(fa["version"])] if isinstance(fa, dict) and fa.get("version") else []
        msg = vuln_message("npm", name, v.get("range", ""), ids[0], ids[1:], title, fixed)
        fix = vuln_fix(name, fixed)
        if fa is True:
            msg = msg.replace("no fixed version published", "npm reports a fix within the declared ranges")
            fix = ("update %s within its declared range (`npm update %s`; /audit-deps applies patch and "
                   "minor upgrades)" % (name, name))
        rep.add("VUL001", lock, line_of(tree, lock, name), msg, severity=sev, fix=fix)
    return ("ok", n)


def fully_hashed(text):
    """True when every requirement of a requirements file is `name==X.Y.Z ... --hash=...` and
    nothing else (no -e, -r, -c, index options, local paths, URLs or VCS): pip-audit can then
    audit it with --require-hashes --no-deps --disable-pip, without resolving or building."""
    pairs = [(i + 1, t.rstrip("\r")) for i, t in enumerate(text.split("\n"))]
    seen = False
    for _ln, line in logical_lines(pairs):
        line = strip_comment(line).strip()
        if not line:
            continue
        if line.startswith("-"):
            if line.split()[0] == "--require-hashes":
                continue
            return False
        if "://" in line or VCS_RE.search(line) or line.startswith((".", "/", "file:")) or " @ " in line:
            return False
        m = REQ_RE.match(line)
        if not m or "--hash" not in line or not PINNED_RE.match(re.split(r"\s--", m.group("spec"))[0]):
            return False
        seen = True
    return seen


def fb_pip(rep, tree, root, files, offline):
    rows = []
    for rel in files:
        if offline:
            rows.append(("offline", 0))
            continue
        if not fully_hashed(tree.read(rel) or ""):
            rep.add("AUD001", rel, 0, "pip-audit would resolve and build packages from %s (not every line "
                    "is pinned with --hash); pip unaudited, not clean" % rel,
                    fix="`harness install osv-scanner` (reads requirements files without building), or "
                        "audit a hashed requirements file (`uv pip compile --generate-hashes`)")
            rows.append(("unavailable", 0))
            continue
        rc, out, err = _run("pip-audit", ["-f", "json", "--require-hashes", "--no-deps", "--disable-pip",
                                          "-r", os.path.abspath(tree.path(rel))], cwd=NEUTRAL)
        try:
            doc = json.loads(out)
        except ValueError:
            doc = None
        deps = doc.get("dependencies") if isinstance(doc, dict) else doc
        if rc not in (0, 1) or not isinstance(deps, list):
            rep.add("AUD003", rel, 0, "pip-audit failed (exit %d): %s" % (rc, first_line(err) or "no JSON"))
            rows.append(("error", 0))
            continue
        with tool_output("pip-audit"):
            for d in deps:
                for v in d.get("vulns") or []:
                    fixed = sorted((str(x) for x in v.get("fix_versions") or []), key=_vkey)
                    rep.add("VUL001", rel, line_of(tree, rel, d.get("name", "")),
                            vuln_message("pip", d.get("name", ""), d.get("version", ""), v.get("id", ""),
                                         sorted(v.get("aliases") or []), (v.get("description") or "").split(". ")[0],
                                         fixed),
                            severity="warn", fix=vuln_fix(d.get("name", ""), fixed))
            rows.append(("ok", len([d for d in deps if d.get("vulns")])))
    return rows


def fb_cargo(rep, tree, root, locks, offline):
    """cargo-audit, called directly (never `cargo audit`: cargo honours the checkout's
    .cargo/config.toml aliases and rust-toolchain.toml) from an empty working directory."""
    rows = []
    for lock in locks:
        if offline:
            rows.append(("offline", 0))
            continue
        rc, out, err = _run("cargo-audit", ["audit", "--json", "--file", os.path.abspath(tree.path(lock))],
                            cwd=NEUTRAL)
        try:
            doc = json.loads(out)
        except ValueError:
            doc = None
        if rc not in (0, 1) or not isinstance(doc, dict):
            rep.add("AUD003", lock, 0, "cargo-audit failed (exit %d): %s" % (rc, first_line(err) or "no JSON"))
            rows.append(("error", 0))
            continue
        with tool_output("cargo-audit"):
            vl = (doc.get("vulnerabilities") or {}).get("list") or []
            for v in vl:
                adv, pk = v.get("advisory") or {}, v.get("package") or {}
                fixed = [str(x) for x in (v.get("versions") or {}).get("patched") or []]
                rep.add("VUL001", lock, line_of(tree, lock, pk.get("name", "")),
                        vuln_message("cargo", pk.get("name", ""), pk.get("version", ""), adv.get("id", ""),
                                     sorted(adv.get("aliases") or []), adv.get("title", ""), fixed),
                        severity="warn", fix=vuln_fix(pk.get("name", ""), fixed))
            rows.append(("ok", len({((v.get("package") or {}).get("name")) for v in vl})))
    return rows


def json_stream(text):
    dec, i, out = json.JSONDecoder(), 0, []
    text = text or ""
    while i < len(text):
        while i < len(text) and text[i] in " \t\r\n":
            i += 1
        if i >= len(text):
            break
        try:
            obj, i = dec.raw_decode(text, i)
        except ValueError:
            break
        out.append(obj)
    return out


def fb_go(rep, tree, root, mods, offline):
    """govulncheck in the module directory (it needs `go list`), with GOTOOLCHAIN=local (a go.mod
    `toolchain` line never downloads a toolchain) and GOFLAGS=-mod=readonly."""
    rows = []
    for mod in mods:
        if offline:
            rows.append(("offline", 0))
            continue
        d = mod.rsplit("/", 1)[0] if "/" in mod else ""
        rc, out, err = _run("govulncheck", ["-json", "./..."], cwd=os.path.join(root, *d.split("/")) if d else root,
                            env_extra={"GOTOOLCHAIN": "local", "GOFLAGS": "-mod=readonly"})
        objs = json_stream(out)
        if rc not in (0, 3) or not objs:
            rep.add("AUD003", mod, 0, "govulncheck failed (exit %d): %s" % (rc, first_line(err) or "no JSON"))
            rows.append(("error", 0))
            continue
        with tool_output("govulncheck"):
            rows.append(_go_findings(rep, mod, objs))
    return rows


def _go_findings(rep, mod, objs):
    osvs, found = {}, {}
    for o in objs:
        if isinstance(o.get("osv"), dict):
            osvs[o["osv"].get("id")] = o["osv"]
        f = o.get("finding")
        if isinstance(f, dict) and f.get("osv"):
            tr = (f.get("trace") or [{}])[0] or {}
            cur = found.setdefault(f["osv"], {"module": tr.get("module", ""), "version": tr.get("version", ""),
                                              "fixed": f.get("fixed_version", ""), "called": False})
            if tr.get("function"):
                cur["called"] = True
    for vid in sorted(found):
        f, o = found[vid], osvs.get(vid) or {}
        fixed = [f["fixed"]] if f["fixed"] else []
        rep.add("VUL001", mod, 0,
                vuln_message("go", f["module"], f["version"], vid, sorted(o.get("aliases") or []),
                             o.get("summary", ""), fixed) + ("; called" if f["called"] else "; imported, not called"),
                severity="warn" if f["called"] else "info", fix=vuln_fix(f["module"], fixed))
    return ("ok", len({f["module"] for f in found.values()}))


OSV_NEEDS = {"pip": "requirements*.txt, uv.lock, poetry.lock, pdm.lock or Pipfile.lock",
             "npm": "package-lock.json, npm-shrinkwrap.json, yarn.lock, pnpm-lock.yaml or bun.lock",
             "go": "go.mod", "cargo": "Cargo.lock"}


def osv_reads(eco, rel):
    """True when osv-scanner extracts packages of ECO from the file REL (a manifest with ranges
    only, such as package.json, Cargo.toml or pyproject.toml, is not enough)."""
    low = rel.rsplit("/", 1)[-1].lower()
    if eco == "pip":
        return bool(re.match(r"^requirements.*\.txt$", low)) or low in ("uv.lock", "poetry.lock", "pdm.lock",
                                                                        "pipfile.lock")
    if eco == "npm":
        return low in ("package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml", "bun.lock")
    if eco == "go":
        return low == "go.mod"
    if eco == "cargo":
        return low == "cargo.lock"
    return False


OSV_NO_OFFLINE_DB = "no offline version of the OSV database is available"  # osv-scanner 2.7.0


def cmd_audit(a):
    tree, rep = start_dir(a, "audit")
    root = a.dir
    for f in (a.lockfile or []) + ([a.sbom] if a.sbom else []):
        if not os.path.isfile(f):
            raise AccessError("%s: no such file" % f)
    if a.sbom and not SBOM_NAME_RE.search(a.sbom):
        die("supply audit: --sbom %s must be named *.spdx.json, *.cdx.json or bom.json (osv-scanner "
            "picks the parser from the name)" % a.sbom, 1)
    detected = [e for e in tree.ecosystems() if e in DEP_ECOSYSTEMS]
    auditors = []
    if tool_path("osv-scanner"):
        # --all-packages: without it the JSON lists only vulnerable packages, so a lockfile read
        # clean would count 0 packages (checked against osv-scanner 2.7.0)
        args = ["scan", "source", "--format", "json", "--all-packages"]
        targets = []
        for f in (a.lockfile or []) + ([a.sbom] if a.sbom else []):
            targets += ["-L", os.path.abspath(f)]
        args += targets or ["-r", os.path.abspath(root)]
        env = {}
        if a.offline:
            args.append("--offline-vulnerabilities")
            db = _env_or_cfg("SUPPLY_OSV_OFFLINE_DB", "supply_chain.osv_offline_db", "")
            if db:
                # osv-scanner 2.7.0 has no flag for it: the variable names the directory under which
                # it reads osv-scalibr/<Ecosystem>/all.zip (default: the user cache directory).
                env["OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY"] = os.path.expanduser(db)
        rc, out, err = _run("osv-scanner", args, env_extra=env)
        empty = rc == 128
        if empty:
            rep.add("AUD002", "", 0, "osv-scanner found no packages to scan in %s" % root)
            counts = {}
        elif rc in (0, 1):
            counts = parse_osv(rep, out, root, tree)
        else:
            why = error_line(err) or first_line(out) or "no output"
            # only osv-scanner's own "no offline database" error gets the download hint (an older
            # osv-scanner rejecting --offline-vulnerabilities also says "offline")
            if a.offline and OSV_NO_OFFLINE_DB in (err or ""):
                why += ("; the offline database is missing: a human downloads it once (osv-scanner scan "
                        "source --offline-vulnerabilities --download-offline-databases -r DIR, with "
                        "OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY set to supply_chain.osv_offline_db), or "
                        "drop --offline")
            raise AccessError("osv-scanner failed (exit %d): %s" % (rc, why))
        scope = set(detected)
        if targets:  # --lockfile / --sbom: only what was named, plus what osv-scanner reported
            scope = {e for t in (a.lockfile or []) for (e, _r) in classify(os.path.basename(t))}
        for eco in sorted(scope | set(counts)):
            read = eco in counts or (not empty and (targets or any(osv_reads(eco, r) for r in tree.files)))
            if not read:
                rep.add("AUD001", "", 0, "%s: osv-scanner read no %s here (%s); %s is unaudited, not clean"
                        % (eco, "packages" if empty else "file it understands", OSV_NEEDS.get(eco, "a lockfile"), eco),
                        fix="commit the lockfile (or pass it with --lockfile) so osv-scanner can read it")
            auditors.append({"ecosystem": eco, "tool": "osv-scanner",
                             "status": ("offline" if a.offline else "ok") if read else "unavailable",
                             "packages": counts.get(eco, 0)})
        rep.data["auditors"] = auditors
        return rep
    if a.sbom:
        raise Unsupported("only osv-scanner audits an SBOM and it is not installed: harness install osv-scanner")
    given = [rel_to(os.path.abspath(g), root) for g in (a.lockfile or [])]
    plan = {
        "npm": ("npm", fb_npm, [(pdir(r), r) for r in tree.of("lockfile", "npm")
                                if r.endswith(("package-lock.json", "npm-shrinkwrap.json"))],
                "npm audit needs package-lock.json or npm-shrinkwrap.json"),
        "pip": ("pip-audit", fb_pip, [r for r in tree.of("manifest", "pip") if r.endswith(".txt")],
                "pip-audit reads requirements files; osv-scanner also reads uv.lock, poetry.lock and pdm.lock"),
        "cargo": ("cargo-audit", fb_cargo, tree.of("lockfile", "cargo"), "cargo-audit needs Cargo.lock"),
        "go": ("govulncheck", fb_go, tree.of("manifest", "go"), "govulncheck needs go.mod"),
    }
    audited = 0
    for eco in detected:
        tool, fn, targets, need = plan[eco]
        if not tool_path(tool):
            rep.add("AUD001", "", 0, "%s: no auditor (osv-scanner and %s are not installed); %s is "
                    "unaudited, not clean" % (eco, tool, eco))
            auditors.append({"ecosystem": eco, "tool": "", "status": "unavailable", "packages": 0})
            continue
        sel = [t for t in targets if not given or (t[1] if isinstance(t, tuple) else t) in given]
        if not sel:
            rep.add("AUD001", "", 0, "%s: %s; %s is unaudited, not clean" % (eco, need, eco))
            auditors.append({"ecosystem": eco, "tool": tool, "status": "unavailable", "packages": 0})
            continue
        rows = fn(rep, tree, root, sel, a.offline)
        kinds = {s for s, _n in rows}
        status = "error" if "error" in kinds else (
            "offline" if kinds == {"offline"} else (
                "unavailable" if kinds == {"unavailable"} else ("partial" if "unavailable" in kinds else "ok")))
        if status == "offline":
            rep.add("AUD001", "", 0, "%s: %s needs the network; `--offline` works with osv-scanner "
                    "and a local database" % (eco, tool))
        elif status in ("ok", "error", "partial"):
            audited += 1
        auditors.append({"ecosystem": eco, "tool": tool, "status": status,
                         "packages": sum(n for _s, n in rows)})
    rep.data["auditors"] = auditors
    if detected and not audited:
        rep.forced_exit = 3
        sys.stderr.write("supply audit: no auditor for %s — harness install osv-scanner (or the "
                         "ecosystem's own auditor); unaudited is not clean\n" % ", ".join(detected))
    elif not detected:
        rep.add("AUD002", "", 0, "no pip, npm, go or cargo manifest in %s" % root)
    return rep


# --------------------------------------------------------------------------------- sbom
SPDX_REQUIRED = ("spdxVersion", "dataLicense", "SPDXID", "name", "documentNamespace", "creationInfo", "packages")
CDX_REQUIRED = ("bomFormat", "specVersion", "version", "metadata", "components")


def key_line(text, key):
    pat = re.compile(r'"%s"\s*:' % re.escape(key))
    for i, t in enumerate(text.split("\n"), 1):
        if pat.search(t):
            return i
    return 1


def sbom_packages(doc, fmt, syft=False):
    """The package entries of an SBOM: SPDX packages without the document root (syft's
    SPDXRef-DocumentRoot-*, the scanned directory or image). For syft's own output (``syft``,
    `supply sbom` only) also CycloneDX components without "type": "file" (the manifests syft read,
    by absolute path); `sbom lint` of any other SBOM counts every component."""
    if fmt == "spdx-json":
        pkgs = doc.get("packages") if isinstance(doc.get("packages"), list) else []
        return [p for p in pkgs if not (isinstance(p, dict)
                                        and str(p.get("SPDXID", "")).startswith("SPDXRef-DocumentRoot-"))]
    pkgs = doc.get("components") if isinstance(doc.get("components"), list) else []
    if not syft:
        return pkgs
    return [p for p in pkgs if not (isinstance(p, dict) and p.get("type") == "file")]


def lint_sbom(rep, rel, text, doc, syft=False):
    """SBM001-SBM009 on a parsed document; -> (format, spec_version, package count). ``syft``: the
    document is syft's output from `supply sbom` (its file components are not packages)."""
    if not isinstance(doc, dict) or not ("spdxVersion" in doc or doc.get("bomFormat") == "CycloneDX"):
        rep.add("SBM001", rel, 1, "not an SPDX or CycloneDX JSON document (no spdxVersion, no "
                "bomFormat: CycloneDX)")
        return "unknown", "", 0
    if "spdxVersion" in doc:
        fmt, ver = "spdx-json", str(doc.get("spdxVersion", ""))
        missing = [k for k in SPDX_REQUIRED if k not in doc]
        ci = doc.get("creationInfo") if isinstance(doc.get("creationInfo"), dict) else {}
        pkgs = sbom_packages(doc, "spdx-json")
        if ver not in ("SPDX-2.2", "SPDX-2.3"):
            rep.add("SBM003", rel, key_line(text, "spdxVersion"), "spec version %s is not SPDX-2.2 or SPDX-2.3" % ver)
        created = ci.get("created")
        tools = [c for c in ci.get("creators") or [] if str(c).startswith("Tool:")]
        no_ver = [p for p in pkgs if isinstance(p, dict) and not p.get("versionInfo")]
        no_purl = [p for p in pkgs if isinstance(p, dict) and not any(
            (r or {}).get("referenceType") == "purl" for r in p.get("externalRefs") or [])]
        describes = bool(doc.get("documentDescribes")) or any(
            (r or {}).get("relationshipType") == "DESCRIBES" for r in doc.get("relationships") or [])
        what_line = key_line(text, "relationships")
    else:
        fmt, ver = "cyclonedx-json", str(doc.get("specVersion", ""))
        missing = [k for k in CDX_REQUIRED if k not in doc]
        md = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
        pkgs = sbom_packages(doc, "cyclonedx-json", syft)
        if not re.match(r"^1\.[4-7]$", ver):
            rep.add("SBM003", rel, key_line(text, "specVersion"), "spec version %s is not CycloneDX 1.4-1.7" % ver)
        created = md.get("timestamp")
        t = md.get("tools")
        tools = (t.get("components") or t.get("services") or []) if isinstance(t, dict) else (t or [])
        no_ver = [p for p in pkgs if isinstance(p, dict) and not p.get("version")]
        no_purl = [p for p in pkgs if isinstance(p, dict) and not p.get("purl")]
        describes = isinstance(md.get("component"), dict)
        what_line = key_line(text, "metadata")
    if missing:
        rep.add("SBM002", rel, 1, "missing required top-level field(s): %s" % ", ".join(missing))
    if not created:
        rep.add("SBM004", rel, key_line(text, "creationInfo" if fmt == "spdx-json" else "metadata"),
                "no creation timestamp")
    if not tools:
        rep.add("SBM005", rel, key_line(text, "creationInfo" if fmt == "spdx-json" else "metadata"),
                "no generating tool recorded")
    if not pkgs:
        rep.add("SBM006", rel, key_line(text, "packages" if fmt == "spdx-json" else "components"),
                "zero packages")
    if no_ver:
        rep.add("SBM007", rel, 1, "%d of %d package(s) have no version" % (len(no_ver), len(pkgs)))
    if no_purl:
        rep.add("SBM008", rel, 1, "%d of %d package(s) have no purl" % (len(no_purl), len(pkgs)))
    if not describes:
        rep.add("SBM009", rel, what_line, "the document does not say what it describes")
    return fmt, ver, len(pkgs)


def cmd_sbom_lint(a, path):
    try:
        with open(path, "rb") as fh:
            text = fh.read().decode("utf-8", "replace")
    except OSError as e:
        raise AccessError("%s: not readable (%s)" % (path, e.strerror or e))
    try:
        doc = json.loads(text)
    except ValueError:
        raise Unsupported("%s is not JSON: `supply sbom lint` checks SPDX JSON and CycloneDX JSON only "
                          "(convert tag-value or XML with the generating tool)" % path)
    rep = Report("sbom lint", "-", [], [])
    fmt, ver, n = lint_sbom(rep, path, text, doc)
    rep.data["sbom"] = {"file": path, "format": fmt, "spec_version": ver, "packages": n}
    return rep


def looks_like_image(t):
    return bool(re.match(r"^[a-z0-9][a-z0-9._-]*(?::[0-9]+)?/[a-z0-9._/-]+(?::[\w.-]+)?(?:@sha256:[0-9a-f]{64})?$", t)
                or re.match(r"^[a-z0-9][a-z0-9._-]*(?::[\w.-]+)?(?:@sha256:[0-9a-f]{64})?$", t) and (":" in t or "@" in t))


def red_tokens(o):
    """Token-shape redaction for an artefact written to disk: AWS keys, JWTs, PEM private keys, URL
    credentials and supply_chain.redact_extra_re in every string value. Unlike red_deep it never
    masks by key name or `key=value` text, so CPEs, authors and licence texts stay intact."""
    user = [r for r in extra_redactors().rxs if r is not _AUTH_SCHEME_RE]

    def s(x):
        x = _PEM_RE.sub(REDACTED, x)
        x = _AKIA_RE.sub(REDACTED, x)
        x = _JWT_RE.sub(REDACTED, x)
        x = _URLCRED_RE.sub("://***:***@", x)
        for r in user:
            x = r.sub(REDACTED, x)
        return x

    def walk(x):
        if isinstance(x, dict):
            return {k: walk(v) for k, v in x.items()}
        if isinstance(x, list):
            return [walk(v) for v in x]
        return s(x) if isinstance(x, str) else x
    return walk(o)


def write_new(path, data, force):
    """Create PATH exclusively (O_EXCL: never through an existing file or symlink), or with FORCE
    replace it atomically (temp file + rename; the old file's mode is kept)."""
    try:
        if not force:
            try:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
            except FileExistsError:
                die("supply sbom: %s already exists — nothing written; pass --force to overwrite it" % path, 1)
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            return
        mode = None
        if os.path.isfile(path) and not os.path.islink(path):
            mode = stat.S_IMODE(os.stat(path).st_mode)
        atomic_write(path, data, mode)
    except OSError as e:
        raise AccessError("--out %s: cannot write (%s); pick a writable path" % (path, e.strerror or e))


def cmd_sbom(a):
    if a.args[0] == "lint":
        if len(a.args) != 2:
            die("supply sbom lint: exactly one FILE (a directory named lint: pass ./lint)", 1)
        return cmd_sbom_lint(a, a.args[1])
    if len(a.args) != 1:
        die("supply sbom: one DIR or IMAGE (or `sbom lint FILE`)", 1)
    target = a.args[0]
    tools = installed_tools()
    if target.startswith("oci://") or (not os.path.exists(target) and looks_like_image(target)):
        image = target[len("oci://"):] if target.startswith("oci://") else target
        src, dir_, ecos = "registry:" + image, "-", []
    elif os.path.isdir(target):
        tree = Tree(target)
        src, dir_, ecos = "dir:" + target, target, tree.ecosystems()
    elif os.path.exists(target):
        raise Unsupported("%s is a file: `supply sbom` scans a directory or an image; lint an SBOM with "
                          "`supply sbom lint %s`" % (target, target))
    else:
        raise AccessError("%s: no such directory, and not an image reference" % target)
    banner(dir_, ecos, tools)
    rep = Report("sbom", dir_, ecos, tools)
    if a.out:
        if "\x00" in a.out:
            raise AccessError("--out contains a NUL byte; pass a plain file path")
        parent = os.path.dirname(os.path.abspath(a.out))
        if not os.path.isdir(parent):
            raise AccessError("--out %s: the directory %s does not exist — nothing scanned or written; create "
                              "it first or write somewhere else" % (a.out, parent))
        if os.path.lexists(a.out) and not a.force:
            die("supply sbom: %s already exists — nothing scanned or written; pass --force to overwrite it, or "
                "write to a new file and diff the two" % a.out, 1)
        if os.path.isdir(a.out):
            raise AccessError("--out %s is a directory; name a file" % a.out)
    if not tool_path("syft"):
        raise AccessError("syft is not installed: harness install syft (the SBOM is unavailable, not empty)")
    # SYFT_CHECK_FOR_APP_UPDATE=false: syft 1.55.0 otherwise calls home for a version check
    rc, out, err = _run("syft", ["scan", src, "-o", a.format, "-q"],
                        env_extra={"SYFT_CHECK_FOR_APP_UPDATE": "false"})
    if rc != 0:
        raise AccessError("syft failed (exit %d): %s" % (rc, error_line(err) or "no output"))
    try:
        doc = json.loads(out)
    except ValueError:
        raise AccessError("syft printed no JSON; the supported version is 1.55.0 (harness install syft)")
    written = red_tokens(doc)
    txt = json.dumps(written, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    with tool_output("syft", "the supported version is 1.55.0 (harness install syft)"):
        fmt, ver, n = lint_sbom(rep, a.out or "-", txt, written, syft=True)
    rep.data["sbom"] = {"source": src, "format": fmt, "spec_version": ver, "packages": n,
                        "bytes": len(txt.encode("utf-8")), "file": a.out or ""}
    if a.out:
        write_new(a.out, txt.encode("utf-8"), a.force)
    else:
        clean = red_deep(doc)
        clean = clean if isinstance(clean, dict) else {}
        names = sorted({"%s %s" % (p.get("name", ""), p.get("versionInfo") or p.get("version") or "")
                        for p in sbom_packages(clean, fmt, syft=True) if isinstance(p, dict)})
        rep.data["packages"] = [x.strip() for x in names]
        rep.data["note"] = "summary only: pass --out FILE to write the SBOM"
    return rep


# ------------------------------------------------------------------------------- verify
def load_identities():
    raw = cfg("supply_chain.identities", []) or []
    if not isinstance(raw, list):
        raise AccessError("supply_chain.identities must be an array of tables ([[supply_chain.identities]] "
                          "name, identity_re, issuer, match_re)")
    out = []
    for i, e in enumerate(raw):
        if not isinstance(e, dict) or not e.get("name") or not e.get("identity_re") or not e.get("issuer"):
            raise AccessError("supply_chain.identities[%d]: needs name, identity_re and issuer "
                              "(manual step configure-identities)" % i)
        for k in ("identity_re", "match_re"):
            if e.get(k):
                try:
                    re.compile(e[k])
                except re.error as ex:
                    raise AccessError("supply_chain.identities[%d] (%s): %s is not a valid regex (%s)"
                                      % (i, e["name"], k, ex))
        check_identity_re(e["identity_re"], "supply_chain.identities[%d] (%s) identity_re" % (i, e["name"]))
        out.append(e)
    return out


def check_identity_re(rx, where):
    """A signer identity regexp must be anchored at both ends and must not match the empty string:
    an unanchored one accepts any certificate whose identity merely contains it."""
    try:
        c = re.compile(rx)
    except re.error as ex:
        raise AccessError("%s: %r is not a valid regex (%s)" % (where, rx, ex))
    if not (rx.startswith("^") and rx.endswith("$") and not rx.endswith("\\$")) or c.match("") is not None:
        raise AccessError("%s: %r must be anchored as ^...$ and must not match the empty string (e.g. "
                          "^https://github\\.com/OWNER/REPO/\\.github/workflows/release\\.yml@refs/tags/v.*$)"
                          % (where, rx))


def resolve_identity(a, target):
    ids = load_identities()
    names = ", ".join(e["name"] for e in ids) or "none configured"
    if a.identity:
        for e in ids:
            if e["name"] == a.identity:
                return e["identity_re"], e["issuer"], e["name"]
        if not a.issuer:
            raise AccessError("--identity %s is not a configured identity (configured: %s); as a certificate "
                              "identity regexp it needs --issuer URL" % (a.identity, names))
        check_identity_re(a.identity, "--identity")
        return a.identity, a.issuer, ""
    for e in ids:
        if e.get("match_re") and re.search(e["match_re"], target):
            return e["identity_re"], e["issuer"], e["name"]
    raise AccessError("no signer identity for %s: pass --identity NAME (configured: %s) or --identity RE "
                      "--issuer URL, --key FILE, or --github OWNER/REPO; or add a [[supply_chain.identities]] "
                      "entry whose match_re matches the target" % (target, names))


def norm_repo(ref):
    _h, repo, _t, _d = image_parts(ref)
    repo = re.sub(r"^(?:index\.)?docker\.io/", "", repo)
    return re.sub(r"^library/", "", repo)


def cmd_verify(a):
    target = a.target
    if target.startswith("-") or "\x00" in target:
        die("supply verify: TARGET %r starts with `-` (or holds a NUL), which a verifier would read as an "
            "option; for a file of that name pass ./%s" % (target, target.replace("\x00", "")), 1)
    if target.startswith("oci://"):
        kind, subject = "image", target[len("oci://"):]
    elif os.path.isfile(target):
        kind, subject = "blob", target
    else:
        kind, subject = "image", target
    if a.key and a.github:
        die("supply verify: --key and --github are alternatives; pass one", 1)
    if (a.key or a.github) and a.identity:
        die("supply verify: --identity is for keyless cosign verification; drop it with --key or --github", 1)
    if a.type and not a.attestation and not a.github:
        die("supply verify: --type needs --attestation", 1)
    tools = installed_tools()
    banner("-", [], tools)
    rep = Report("verify", "-", [], tools)
    if a.offline and not a.trusted_root:
        raise Unsupported("--offline needs --trusted-root FILE (a Sigstore trusted_root.json): without the "
                          "network there is nothing else to verify against")
    if a.offline and a.github and not a.bundle:
        raise Unsupported("--github --offline needs --bundle FILE (the attestation, from `gh attestation "
                          "download`) and --trusted-root FILE (`gh attestation trusted-root`): gh cannot "
                          "fetch either without the network")
    if a.trusted_root and not os.path.isfile(a.trusted_root):
        raise AccessError("%s: no such file (--trusted-root)" % a.trusted_root)
    if a.github:
        return verify_github(a, rep, kind, subject)
    if kind == "image" and a.offline:
        raise Unsupported("--offline cannot verify an image with cosign: cosign 3.1.4 deprecated --offline, and "
                          "verify / verify-attestation read the image's signatures and the transparency log "
                          "over the network. Offline, verify a downloaded file with its Sigstore bundle "
                          "(supply verify FILE --bundle F --trusted-root F --offline), or an attestation "
                          "with gh (supply verify TARGET --github OWNER/REPO --bundle F --trusted-root F "
                          "--offline); else drop --offline")
    if kind == "image" and a.bundle:
        die("supply verify: --bundle is for a file with cosign (cosign verify and verify-attestation read "
            "an image's signatures from its registry); drop --bundle, or use --github OWNER/REPO --bundle F", 1)
    if kind == "blob" and not a.bundle:
        die("supply verify: a file needs --bundle F (cosign v3 verifies blobs from a Sigstore bundle), or "
            "use --github OWNER/REPO", 1)
    if not tool_path("cosign"):
        raise AccessError("cosign is not installed: harness install cosign (the signature is unverified, "
                          "not failed)")
    args = []
    who = {}
    if a.key:
        args += ["--key", a.key]
        who = {"key": a.key}
    else:
        rx, issuer, name = resolve_identity(a, subject)
        args += ["--certificate-identity-regexp", rx, "--certificate-oidc-issuer", issuer]
        who = {"identity_re": rx, "issuer": issuer, "identity": name}
    if a.trusted_root:
        args += ["--trusted-root", a.trusted_root]
    # no cosign --offline: cosign 3.1.4 deprecates it ("provide a --bundle ... and a --trusted-root");
    # offline here means a file, its --bundle and a --trusted-root (images are refused above)
    if kind == "blob":
        verb = "verify-blob-attestation" if a.attestation else "verify-blob"
        cmd = [verb, "--bundle", a.bundle] + (["--type", a.type] if a.type else []) + args + ["--", subject]
    elif a.attestation:
        cmd = ["verify-attestation", "--output", "json"] + (["--type", a.type] if a.type else []) + args + \
              ["--", subject]
    else:
        cmd = ["verify", "--output", "json"] + args + ["--", subject]
    rc, out, err = _run("cosign", cmd)
    if rc != 0:
        raise AccessError("unverifiable: %s" % (error_line(err) or "cosign exited %d" % rc))
    rep.data["verifier"] = dict(who, tool="cosign", command=cmd[0])
    if kind == "blob":
        rep.data["signatures"] = [{"file": subject, "bundle": a.bundle}]
        rep.add("VER000", subject, 0, "%s verified for %s" % ("attestation" if a.attestation else "signature", subject))
        return rep
    if a.attestation:
        with tool_output("cosign", "the supported version is 3.1.4 (harness install cosign)"):
            atts = _cosign_attestations(out)
        if not atts:
            raise AccessError("cosign verify-attestation exited 0 but printed no attestation; treat %s as "
                              "unverified and rerun cosign by hand to see why" % subject)
        rep.data["attestations"] = red_deep(sorted(atts, key=lambda x: json.dumps(x, sort_keys=True)))
        rep.add("VER000", subject, 0, "%d attestation(s) verified for %s" % (len(atts), subject))
        for x in atts:
            if x["subject"] and norm_repo(x["subject"]) != norm_repo(subject):
                rep.add("VER001", subject, 0, "attestation subject %s is not %s" % (x["subject"], norm_repo(subject)))
        return rep
    try:
        doc = json.loads(out)
    except ValueError:
        raise AccessError("cosign printed no JSON; the supported version is 3.1.4 (harness install cosign)")
    if not isinstance(doc, list) or not doc:
        raise AccessError("cosign verify exited 0 but printed no signature list; treat %s as unverified and "
                          "rerun cosign by hand to see why" % subject)
    with tool_output("cosign", "the supported version is 3.1.4 (harness install cosign)"):
        sigs = _cosign_signatures(doc)
    rep.data["signatures"] = red_deep(sorted(sigs, key=lambda x: json.dumps(x, sort_keys=True)))
    rep.add("VER000", subject, 0, "%d signature(s) verified for %s" % (len(sigs), subject))
    for x in sigs:
        if x["reference"] and norm_repo(x["reference"]) != norm_repo(subject):
            rep.add("VER001", subject, 0, "signature was made for %s, not %s" % (x["reference"], norm_repo(subject)))
    return rep


def _cosign_signatures(doc):
    sigs = []
    for s in doc:
        crit, opt = s.get("critical") or {}, s.get("optional") or {}
        sigs.append({"reference": (crit.get("identity") or {}).get("docker-reference", ""),
                     "digest": (crit.get("image") or {}).get("docker-manifest-digest", ""),
                     "type": crit.get("type", ""), "issuer": opt.get("Issuer", ""), "subject": opt.get("Subject", "")})
    return sigs


def _cosign_attestations(out):
    atts = []
    for o in json_stream(out):
        st = {}
        try:
            st = json.loads(base64.b64decode(o.get("payload") or "").decode("utf-8", "replace"))
        except (ValueError, TypeError):
            pass
        st = st if isinstance(st, dict) else {}
        pred = st.get("predicate") or {}
        builder = ((pred.get("builder") or {}).get("id") or
                   (((pred.get("runDetails") or {}).get("builder") or {}).get("id")) or "")
        for s in st.get("subject") or [{}]:
            atts.append({"subject": s.get("name", ""), "digest": "sha256:" + ((s.get("digest") or {}).get("sha256") or ""),
                         "predicateType": st.get("predicateType", ""), "builder": builder})
    return atts


def verify_github(a, rep, kind, subject):
    if not tool_path("gh"):
        raise AccessError("gh is not installed: enable the github bundle (harness install gh); the "
                          "attestation is unverified, not failed")
    owner = a.github.strip("/")
    if not re.match(r"^[\w.-]+(?:/[\w.-]+)?$", owner):
        die("supply verify: --github takes OWNER or OWNER/REPO", 1)
    cmd = ["attestation", "verify"]
    cmd += ["-R", owner] if "/" in owner else ["-o", owner]
    cmd += ["--format", "json"]
    if a.type:
        cmd += ["--predicate-type", a.type]
    if a.bundle:
        cmd += ["--bundle", a.bundle]
    if a.trusted_root:
        cmd += ["--custom-trusted-root", a.trusted_root]
    cmd += ["--", subject if kind == "blob" else "oci://" + subject]
    rc, out, err = _run("gh", cmd)
    if rc != 0:
        raise AccessError("unverifiable: %s" % (first_line(err) or "gh attestation verify exited %d" % rc))
    try:
        doc = json.loads(out)
    except ValueError:
        raise AccessError("gh attestation verify printed no JSON; gh 2.49 or later is required")
    if not isinstance(doc, list) or not doc:
        raise AccessError("gh attestation verify exited 0 but printed no attestation list; treat %s as "
                          "unverified and rerun gh by hand to see why" % subject)
    atts = []
    with tool_output("gh attestation verify", "gh 2.49 or later is required"):
        for r in doc:
            vr = r.get("verificationResult") or {}
            st = vr.get("statement") or {}
            cert = (vr.get("signature") or {}).get("certificate") or {}
            for s in st.get("subject") or [{}]:
                atts.append({"subject": s.get("name", ""),
                             "digest": "sha256:" + ((s.get("digest") or {}).get("sha256") or ""),
                             "predicateType": st.get("predicateType", ""), "issuer": cert.get("issuer", ""),
                             "identity": cert.get("subjectAlternativeName", ""),
                             "builder": cert.get("buildSignerURI", "")})
    rep.data["verifier"] = {"tool": "gh", "command": "attestation verify", "owner": owner}
    rep.data["attestations"] = red_deep(sorted(atts, key=lambda x: json.dumps(x, sort_keys=True)))
    rep.add("VER000", subject, 0, "%d attestation(s) verified for %s" % (len(atts), subject))
    return rep


# ------------------------------------------------------------------------------- redact
def cmd_redact(a):
    raw = sys.stdin.read()
    try:
        obj = json.loads(raw)
    except ValueError:
        sys.stdout.write(red_text(raw))
        if raw and not raw.endswith("\n"):
            sys.stdout.write("\n")
        sys.exit(0)
    indent = 2 if (sys.stdout.isatty() or a.md) else None
    sys.stdout.write(json.dumps(red_deep(obj), indent=indent, default=str) + "\n")
    sys.exit(0)


# ------------------------------------------------------------------------------- parser
class _Parser(argparse.ArgumentParser):
    def error(self, message):
        who = "supply %s" % self.prog.split()[-1] if " " in self.prog else "supply"
        die("%s: %s\n\nRun `supply` with no arguments for the command list." % (who, message), 1)


def common_parser():
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--json", action="store_true", help="force JSON output")
    p.add_argument("--md", action="store_true", help="force Markdown output")
    p.add_argument("--max-bytes", type=int, default=MAX_BYTES, dest="max_bytes")
    p.add_argument("--timeout", type=int, default=TIMEOUT, help="per-tool timeout seconds")
    return p


def build_parser():
    common = common_parser()
    top = _Parser(prog="supply", description="Software supply-chain client", add_help=False)
    subs = top.add_subparsers(dest="cmd", parser_class=_Parser)

    def sub(name, **kw):
        return subs.add_parser(name, parents=[common], **kw)

    s = sub("detect", help="ecosystems, manifests and lockfiles")
    s.add_argument("dir", metavar="DIR", nargs="?", default=".")
    s.set_defaults(fn=cmd_detect)

    s = sub("pins", help="unpinned actions, images, dependencies and downloads")
    s.add_argument("dir", metavar="DIR", nargs="?", default=".")
    s.add_argument("--apply", metavar="FILE", help="JSON list of {file, line, old, new} rewrites")
    s.set_defaults(fn=cmd_pins)

    s = sub("ci", help="workflow hardening")
    s.add_argument("files", metavar="FILE", nargs="+")
    s.add_argument("--ignore", metavar="RULE,...", default="")
    s.set_defaults(fn=cmd_ci)

    s = sub("audit", help="known vulnerabilities")
    s.add_argument("dir", metavar="DIR", nargs="?", default=".")
    s.add_argument("--lockfile", metavar="F", action="append", default=[])
    s.add_argument("--sbom", metavar="F")
    s.add_argument("--offline", action="store_true")
    s.set_defaults(fn=cmd_audit)

    s = sub("sbom", help="SBOM of a directory or image; `sbom lint FILE`")
    s.add_argument("args", metavar="DIR|IMAGE|lint FILE", nargs="+")
    s.add_argument("--format", choices=("spdx-json", "cyclonedx-json"), default="spdx-json")
    s.add_argument("--out", metavar="F")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_sbom)

    s = sub("verify", help="signature or attestation of an image or file")
    s.add_argument("target", metavar="TARGET")
    s.add_argument("--identity", metavar="NAME|RE")
    s.add_argument("--issuer", metavar="URL")
    s.add_argument("--key", metavar="F")
    s.add_argument("--github", metavar="OWNER[/REPO]")
    s.add_argument("--attestation", action="store_true")
    s.add_argument("--type", metavar="T")
    s.add_argument("--bundle", metavar="F")
    s.add_argument("--trusted-root", metavar="F", dest="trusted_root")
    s.add_argument("--offline", action="store_true")
    s.set_defaults(fn=cmd_verify)

    s = sub("redact", help="stdin -> redacted stdout")
    s.set_defaults(fn=cmd_redact)
    return top, list(subs.choices)


def main():
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        sys.exit(1)
    if argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        sys.exit(0)
    top, names = build_parser()
    if argv[0] not in names:
        die("Unknown command %r. Commands: %s\n\nRun `supply` with no arguments for the full usage."
            % (argv[0], ", ".join(names)), 1)
    a = top.parse_args(argv)
    global TIMEOUT
    if getattr(a, "timeout", None) is not None:
        if a.timeout < 1:
            die("supply %s: --timeout must be a positive number of seconds" % a.cmd, 1)
        TIMEOUT = a.timeout
    if getattr(a, "max_bytes", 0) < 0:
        die("supply %s: --max-bytes must be 0 (no cap) or a positive number" % a.cmd, 1)
    try:
        rep = a.fn(a)
        fmt = "json" if a.json else ("md" if a.md else ("md" if sys.stdout.isatty() else "json"))
        rep.emit(fmt, a.max_bytes)
    except AccessError as e:
        die("supply %s: %s" % (a.cmd, red_text(str(e))), 2)
    except Unsupported as e:
        die("supply %s: %s" % (a.cmd, red_text(str(e))), 3)
    except BrokenPipeError:
        sys.exit(0)
    except KeyboardInterrupt:
        die("supply %s: interrupted" % a.cmd, 130)
    except (OSError, ValueError) as e:
        die("supply %s: %s (%s) — check the paths and permissions given and rerun"
            % (a.cmd, red_text(str(e)), type(e).__name__), 2)
    except Exception as e:  # never a traceback: a bug is reported as an error, exit 2
        die("supply %s: internal error (%s: %s) — please report it with the "
            "command line" % (a.cmd, type(e).__name__, red_text(str(e))), 2)
    sys.exit(rep.exit_code())


if __name__ == "__main__":
    main()
