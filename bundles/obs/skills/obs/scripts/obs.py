#!/usr/bin/env python3
"""Read-only observability client (SigNoz, Prometheus, Grafana) — stdlib only.

Canonical invocation: `obs <cmd>` (symlinked into ~/.local/bin, like `k8s`/`gdoc`).
Every backend call is a bounded, read-only HTTP request through one helper that refuses
any method or endpoint outside its read allow-list; log lines, span attributes and label
values are redacted before they are printed, so raw backend dumps never land in a model
context. Alert rules, dashboards and silences are never changed here: they change as files
in the owning repository, through a merge request.

Output is findings-first: JSON when stdout is not a TTY (or --json), Markdown on a TTY
(or --md):
  {"backend","kind","prod","generated_at","command",
   "findings":[{"severity","kind","ns","name","message","evidence"}],"data":{...}}
Exit codes: 0 clean, 1 findings (or a usage / query error), 2 access error (401/403, 404
not found, a redirect — never followed, the key stays on the configured host —, a non-JSON
answer such as a login page, unreachable, timeout, key file missing), 3 the command does not
exist for this backend kind (a static decision, never an HTTP status).
When JSON output exceeds --max-bytes, trailing items of the largest list are dropped until it
fits and the envelope carries "truncated": {"items_dropped": N, "max_bytes": M}.

Every backend command prints a banner to STDERR first:
  backend=signoz-dev kind=signoz url=signoz.example.com [PROD]
[PROD] marks a backend whose name or host matches OBS_PROD_RE — reads stay free there, but
every remediation is a suggestion for the human to run.

Commands (run with no args to print this list):
  backends [--probe] [--names]
                        Configured backends: name, kind, host, key file (present 0600 /
                        bad mode / missing / none), default and prod flags. --probe adds
                        reachability, version and an authenticated read per backend.
                        --names prints only the names (offline; for doctor). Exit 2 when
                        a key file is missing (or, with --probe, a backend is unreachable
                        or refuses the key).
  query PROMQL [--range 1h] [--step 60s] [--datasource UID]
                        Metrics table: metric | labels | value [| samples]. signoz (PromQL
                        through the v5 query API), prometheus, grafana (--datasource: a
                        Prometheus datasource uid).
  logs FILTER [--service S] [--limit N] [--datasource UID]
                        Bounded, redacted log lines, newest first. signoz (FILTER is a
                        filter expression, e.g. "severity_text = 'ERROR'"), grafana (Loki
                        datasource; FILTER is LogQL or a line filter with --service).
                        prometheus: exit 3.
  traces --service S [--error] [--min-duration 500ms]
                        Root spans of recent traces: trace id, root span, duration, status
                        (signoz; others exit 3).
  trace ID [--depth 3]  Span tree of one trace, depth-limited, attributes redacted (signoz;
                        others exit 3).
  services              RED per service over --since: calls, rate, error %, p99 and average
                        latency (signoz; others exit 3). Error rate >= 5% is a finding.
  alerts [--firing] [--rules]
                        Firing alerts (default) and/or alert rule definitions. A firing
                        alert with severity critical|warning is a finding.
  dashboards [--export UID FILE.json [--force]]
                        List dashboards; --export writes one dashboard's JSON (sorted keys,
                        secret-looking keys redacted, at most --max-bytes) to FILE — the only
                        local write. It refuses an existing FILE unless --force, and an empty
                        answer. Edit the file in the owning repository and open an MR.
  lint FILE...          Alert rules and dashboards as code, offline: Prometheus rule files
                        (YAML through PyYAML when importable, else JSON), SigNoz alert JSON,
                        Grafana dashboard JSON. Findings carry file:line and the fix.
  redact                stdin -> stdout filter (JSON or free text). No backend call.

Common flags: --backend NAME (default obs.default, else the first configured backend),
--json/--md, --timeout S (20), --max-items N (50), --max-bytes N (obs.max_bytes, 65536),
--since DURATION (15m; s/m/h/d).

Deliberately NOT implemented — do not work around these with raw curl; the guard hook asks
on raw requests to a backend host and denies an API key on a command line, so tell the human
what to run instead: any write to a backend (alert rules, dashboards, silences, API keys,
channels), `--follow` / live tail, exports beyond --max-bytes, native Loki / Tempo adapters
(reach Loki through a grafana backend), Elastic / Datadog / New Relic, reading a kubeconfig
to find in-cluster services (in-cluster Prometheus without an ingress: `k8s promql`).

Config (harness config keys, read from build/config.json via HARNESS_CONFIG_JSON /
HARNESS_HOME; env first where named):
  obs.backends           array of tables {name, kind = signoz|prometheus|grafana, url,
                         auth_file = "~/.config/obs/<name>.key"}; prometheus may omit
                         auth_file (no auth). The key file holds one line: a Viewer-role API
                         key (SigNoz), a service-account token (Grafana) or a bearer token
                         (Prometheus behind a proxy). Mode 0600; never printed.
  OBS_DEFAULT [obs.default]          backend used without --backend
  OBS_PROD_RE [obs.prod_re]          default `(^|[-_./:])(prod|production)([-_./:]|$)`,
                                     matched case-insensitively on backend name and host
  OBS_HOSTS_RE [obs.hosts_re]        the guard's backend host regex, a POSIX ERE (grep -E):
                                     `backends` warns when it is empty, misses a configured
                                     host, uses Python-only syntax (\\d \\w \\s (?…) or when
                                     grep -E and Python disagree on a host
  OBS_LOG_TAIL [obs.log_tail]        default --limit for `logs` (200)
  OBS_MAX_BYTES [obs.max_bytes]      default --max-bytes (65536)
  OBS_REDACT_EXTRA_RE [obs.redact_extra_re]  extra regex (Python re) of token shapes to
                                     redact; compiled on its own, so a leading (?i) works
  OBS_TIMEOUT                        default --timeout seconds (20)
Test hooks (never needed in normal use):
  OBS_DRY_RUN=1          no request leaves the machine: each one is appended as
                         `METHOD URL` to the file OBS_DRY_RUN_LOG (stderr when unset) and
                         answered from OBS_HTTP_FIXTURES, else with an empty JSON object
  OBS_HTTP_FIXTURES=DIR  answer every request from DIR/*/routes.json (the route format of
                         tests/fakes/http_fixture.py); no network
"""
import argparse
import base64
import datetime
import glob
import json
import os
import re
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request

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
# so the credential does not survive behind a masked scheme word.
_AUTH_SCHEME = r"(?:bearer|basic|token|digest|negotiate|api-?key|key|ssws|oauth)"
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


def redact_obj(obj, extra_re=None):
    """Walk a JSON structure: secret-ish keys -> ***REDACTED***, Secret data -> sizes.
    extra_re (compiled regex or None): its matches inside string values are redacted too."""
    if isinstance(obj, dict):
        if obj.get("kind") == "Secret":
            obj = _secret_sizes(obj)
        out = {}
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                out[k] = redact_obj(v, extra_re)
            elif SECRET_KEY_RE.search(str(k)) and v is not None and not (
                    isinstance(v, str) and v.startswith("<") and v.endswith("bytes>")):
                out[k] = REDACTED
            else:
                out[k] = redact_obj(v, extra_re)
        return out
    if isinstance(obj, list):
        return [redact_obj(x, extra_re) for x in obj]
    if extra_re is not None and isinstance(obj, str):
        return extra_re.sub(REDACTED, obj)
    return obj


def redact_text(text, extra_re=None):
    """Redact free text / logs: key=value lines, AWS keys, JWTs, PEM blocks, URL creds.
    extra_re (compiled regex or None): its matches are redacted too, before the line rules."""
    if not text:
        return text
    text = _PEM_RE.sub(REDACTED, text)
    if extra_re is not None:
        text = extra_re.sub(REDACTED, text)
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
    return "\n".join(lines)
# <<< redact


def die(msg, code=1):
    print(msg, file=sys.stderr)
    sys.exit(code)


class AccessError(Exception):
    """401/403, unreachable, timeout, key file missing -> exit 2."""


class Unsupported(Exception):
    """The command does not exist for this backend kind -> exit 3."""


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


PROD_RE = re.compile(_env_or_cfg("OBS_PROD_RE", "obs.prod_re",
                                 r"(^|[-_./:])(prod|production)([-_./:]|$)"), re.I)
TIMEOUT = _int(os.environ.get("OBS_TIMEOUT"), 20)
LOG_TAIL = _int(_env_or_cfg("OBS_LOG_TAIL", "obs.log_tail", 200), 200)
MAX_BYTES = _int(_env_or_cfg("OBS_MAX_BYTES", "obs.max_bytes", 65536), 65536)
KINDS = ("signoz", "prometheus", "grafana")

# Bearer / Basic credentials anywhere in a line. The shared block now masks the scheme word
# and its token after a secret-looking key (`Authorization: Bearer X`); this stays as belt
# and braces for a scheme with no such key in front, and for JSON string values, which
# redact_obj passes through extra_re only.
_AUTH_SCHEME_RE = re.compile(r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{6,}")


class _ExtraRedactors(object):
    """The built-in scheme regex and the user's obs.redact_extra_re, each compiled on its own
    (a user pattern may start with a global flag such as `(?i)`, which is an error anywhere but
    at the start of a pattern) and applied in turn. Duck-types the `.sub` the redact block calls."""

    def __init__(self, *rxs):
        self.rxs = [r for r in rxs if r is not None]

    def sub(self, repl, s):
        for r in self.rxs:
            s = r.sub(repl, s)
        return s


_REDACTORS = None


def extra_redactors():
    """Compiled lazily, on the first redacting use: a bad user pattern fails that command with a
    clean message, never a traceback, and never commands that do not redact."""
    global _REDACTORS
    if _REDACTORS is None:
        user = _env_or_cfg("OBS_REDACT_EXTRA_RE", "obs.redact_extra_re", "")
        try:
            user_rx = re.compile(user) if user else None
        except re.error as e:
            die("OBS_REDACT_EXTRA_RE / obs.redact_extra_re is not a valid Python regex (%s); fix or "
                "unset it (a global flag such as (?i) must come first)" % e)
        _REDACTORS = _ExtraRedactors(_AUTH_SCHEME_RE, user_rx)
    return _REDACTORS


def red_text(s):
    return redact_text(str(s), extra_redactors()) if s not in (None, "") else ("" if s is None else s)


def red_obj(o):
    return redact_obj(o, extra_redactors())


# ------------------------------------------------------------------------------ backends
def is_prod(*parts):
    return any(PROD_RE.search(p) for p in parts if p)


def host_of(url):
    """host[:port] of a URL — never its userinfo (load_backends rejects one; defence in depth)."""
    parts = urllib.parse.urlsplit(url or "")
    if not parts.netloc:
        return (url or "").rsplit("@", 1)[-1]
    host = parts.hostname or ""
    if ":" in host:
        host = "[%s]" % host
    try:
        port = parts.port
    except ValueError:
        port = None
    return host + (":%d" % port if port else "")


def load_backends():
    raw = cfg("obs.backends", []) or []
    out = []
    if not isinstance(raw, list):
        die("obs.backends must be an array of tables ([[obs.backends]] name, kind, url, auth_file)")
    for i, b in enumerate(raw):
        if not isinstance(b, dict):
            die("obs.backends[%d] is not a table; see the manual step configure-backends" % i)
        name, kind, url = b.get("name"), b.get("kind"), b.get("url")
        if not name or kind not in KINDS or not url:
            die("obs.backends[%d]: needs name, kind (%s) and url; see the manual step "
                "configure-backends" % (i, "|".join(KINDS)))
        if not re.match(r"^https?://[^/\s]+", url):
            die("obs.backends[%d] (%s): url must start with https:// (or http://)" % (i, name))
        if "@" in urllib.parse.urlsplit(url).netloc:
            die("backend %s: url must not carry credentials; put them in auth_file (a key file under "
                "~/.config/obs, mode 0600) and remove the user:password@ part from the url" % name, 2)
        out.append({"name": name, "kind": kind, "url": url.rstrip("/"),
                    "auth_file": b.get("auth_file") or ""})
    return out


def pick_backend(name):
    backends = load_backends()
    if not backends:
        die("no observability backends configured — add [[obs.backends]] to local/harness.toml "
            "(manual step configure-backends), run `harness apply`, then `obs backends`", 2)
    want = name or _env_or_cfg("OBS_DEFAULT", "obs.default", "")
    if not want:
        return backends[0]
    for b in backends:
        if b["name"] == want:
            return b
    die("unknown backend %r — configured: %s (see `obs backends`)"
        % (want, ", ".join(b["name"] for b in backends)), 1)


def key_status(b):
    """-> (status, path): none | missing | ok | mode-0644 (never reads the content)."""
    if not b["auth_file"]:
        return "none", ""
    path = os.path.expanduser(b["auth_file"])
    try:
        st = os.stat(path)
    except OSError:
        return "missing", path
    mode = stat.S_IMODE(st.st_mode)
    return ("ok" if not mode & 0o077 else "mode-%04o" % mode), path


def read_key(b):
    status, path = key_status(b)
    if status == "none":
        if b["kind"] == "prometheus":
            return ""
        raise AccessError("backend %s (%s) has no auth_file — set auth_file in [[obs.backends]] "
                          "(manual step obs-api-key)" % (b["name"], b["kind"]))
    if status == "missing":
        raise AccessError("key file missing for backend %s: %s — create it with `install -m 600` "
                          "(manual step obs-api-key); `obs backends` shows every backend's key "
                          "status" % (b["name"], b["auth_file"]))
    if status != "ok":
        print("warning: key file %s has %s; run `chmod 600 %s`" % (b["auth_file"], status, b["auth_file"]),
              file=sys.stderr)
    try:
        with open(path) as fh:
            key = fh.read().strip()
    except OSError as e:
        raise AccessError("cannot read key file %s (%s); check its owner and mode"
                          % (b["auth_file"], e.strerror))
    if not key:
        raise AccessError("key file %s is empty — paste the API key into it (manual step obs-api-key)"
                          % b["auth_file"])
    return key


def banner(b):
    parts = ["backend=%s" % b["name"], "kind=%s" % b["kind"], "url=%s" % host_of(b["url"])]
    if is_prod(b["name"], host_of(b["url"])):
        parts.append("[PROD]")
    print(" ".join(parts), file=sys.stderr)


# ----------------------------------------------------------------------------------- http
# The read allow-list: every request the CLI can make. POST is a read only on these paths
# (query APIs take their query as a body); PUT/PATCH/DELETE are never sent.
READ_ENDPOINTS = {
    "signoz": [("GET", r"^/api/v1/version$"), ("GET", r"^/api/v1/health$"),
               ("POST", r"^/api/v5/query_range$"), ("POST", r"^/api/v1/services$"),
               ("GET", r"^/api/v1/rules$"), ("GET", r"^/api/v1/alerts$"),
               ("GET", r"^/api/v1/dashboards(/[A-Za-z0-9-]+)?$")],
    "prometheus": [("GET", r"^/api/v1/(query|query_range|rules|alerts|status/buildinfo)$")],
    "grafana": [("GET", r"^/api/health$"), ("GET", r"^/api/search$"),
                ("GET", r"^/api/dashboards/uid/[A-Za-z0-9._-]+$"), ("POST", r"^/api/ds/query$"),
                ("GET", r"^/api/alertmanager/grafana/api/v2/alerts$"),
                ("GET", r"^/api/prometheus/grafana/api/v1/rules$")],
}
_FIXTURES = None


def _fixture_routes():
    global _FIXTURES
    if _FIXTURES is None:
        _FIXTURES = []
        d = os.environ.get("OBS_HTTP_FIXTURES") or ""
        for p in sorted(glob.glob(os.path.join(d, "*", "routes.json"))) if d else []:
            with open(p) as fh:
                r = json.load(fh)
            _FIXTURES.extend(r.get("routes", []) if isinstance(r, dict) else r)
    return _FIXTURES


def _fixture_answer(method, url):
    for r in _fixture_routes():
        if r.get("method") and r["method"].upper() != method:
            continue
        if not re.search(r.get("url", ""), url):
            continue
        if r.get("error"):
            raise AccessError("%s unreachable: %s — check the url in [[obs.backends]] and the "
                              "network (`obs backends --probe`)" % (host_of(url), r["error"]))
        status, body = int(r.get("status", 200)), r.get("body", "")
        return status, (body if isinstance(body, str) else json.dumps(body)), r.get("headers") or {}
    raise AccessError("no fixture route for %s %s (OBS_HTTP_FIXTURES)" % (method, url))


class NotFound(AccessError):
    """HTTP 404: the endpoint is not served by this backend version, or the resource is missing.
    An access error (exit 2), not "unsupported" (exit 3 is only for a verb this backend kind
    lacks by design)."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never follow a redirect: urllib would resend the API key header to the new host. The 3xx
    surfaces as an HTTPError and _http reports it (exit 2) with the target host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


urllib.request.install_opener(urllib.request.build_opener(_NoRedirect))


def _header(headers, name):
    if not headers:
        return ""
    for k, v in (headers.items() if hasattr(headers, "items") else []):
        if str(k).lower() == name.lower():
            return v or ""
    return ""


def _snippet(text, n=60):
    return red_text(" ".join(str(text).split()))[:n]


def _http(b, method, path, query=None, body=None, key=None, timeout=TIMEOUT):
    """The only network path. Returns parsed JSON. Raises AccessError (incl. NotFound) — a
    redirect, a 404 and a non-JSON 2xx body are access errors; nothing is followed."""
    if not any(m == method and re.match(rx, path) for m, rx in READ_ENDPOINTS[b["kind"]]):
        die("obs: refusing %s %s on a %s backend — not a read endpoint this CLI allows"
            % (method, path, b["kind"]), 1)
    url = b["url"] + path + ("?" + urllib.parse.urlencode(query) if query else "")
    data = json.dumps(body).encode() if body is not None else None
    if os.environ.get("OBS_DRY_RUN") == "1":
        line = "%s %s\n" % (method, url)
        log = os.environ.get("OBS_DRY_RUN_LOG")
        if log:
            with open(log, "a") as fh:
                fh.write(line)
        else:
            sys.stderr.write("dry-run: " + line)
        if not os.environ.get("OBS_HTTP_FIXTURES"):
            return {}
    resp_headers = {}
    if os.environ.get("OBS_HTTP_FIXTURES"):
        status, text, resp_headers = _fixture_answer(method, url)
    else:
        headers = {"Accept": "application/json", "User-Agent": "harness-obs/1"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if key:
            if b["kind"] == "signoz":
                headers["SIGNOZ-API-KEY"] = key
            else:
                headers["Authorization"] = "Bearer " + key
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status, text = resp.status, resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            status, text, resp_headers = e.code, (e.read() or b"").decode("utf-8", "replace"), e.headers
        except urllib.error.URLError as e:
            raise AccessError("%s unreachable: %s — check the url in [[obs.backends]] and the "
                              "network (`obs backends --probe`)" % (host_of(url), e.reason))
        except OSError as e:
            raise AccessError("%s unreachable: %s — check the url and the network"
                              % (host_of(url), e))
    if status in (401, 403):
        raise AccessError("%s answered %d for %s %s — the key in %s is invalid, expired or lacks "
                          "the Viewer role; replace it (docs/runbooks/rotate-obs-key.md)"
                          % (b["name"], status, method, path, b["auth_file"] or "(no auth_file)"))
    if 300 <= status < 400:
        loc = _header(resp_headers, "Location")
        target = host_of(urllib.parse.urljoin(url, loc)) if loc else "(no Location header)"
        raise AccessError("%s answered %d for %s %s: redirected to %s; refusing to follow with "
                          "credentials — set url in [[obs.backends]] to the address that serves the "
                          "API directly (scheme, host and path prefix)"
                          % (b["name"], status, method, path, target))
    if status == 404:
        raise NotFound("%s answered 404 for %s %s%s: not found: endpoint unsupported by this version "
                       "or resource missing — check the name or id you passed, and `obs backends "
                       "--probe` for the version"
                       % (b["name"], method, b["url"], path))
    if status >= 500:
        raise AccessError("%s answered %d for %s %s — the backend is failing; retry later or "
                          "check its own health" % (b["name"], status, method, path))
    try:
        parsed = json.loads(text) if text else {}
    except ValueError:
        if status < 400:
            raise AccessError("%s returned non-JSON for %s %s (%s) — a login page or proxy answered "
                              "instead of the API; check the url in [[obs.backends]]"
                              % (b["name"], method, path, _snippet(text)))
        parsed = text
    if status >= 400:
        msg = parsed.get("error") if isinstance(parsed, dict) else parsed
        if isinstance(msg, dict):
            msg = msg.get("message") or json.dumps(msg)
        die("%s rejected the request (%d): %s — fix the query and rerun"
            % (b["name"], status, red_text(str(msg))[:300]), 1)
    return parsed


def as_dict(b, body, path):
    """A JSON object, or AccessError (exit 2): a list or a bare string where the API answers an
    object means something else answered (a proxy, a login page, another product)."""
    if body is None or body == "":
        return {}
    if not isinstance(body, dict):
        raise AccessError("%s returned non-JSON for %s (%s) — expected a JSON object; check the url "
                          "in [[obs.backends]]" % (b["name"], path, _snippet(json.dumps(body, default=str))))
    return body


def unwrap(body):
    """SigNoz/Prometheus envelope {"status":"success","data":X} -> X (else the body)."""
    if isinstance(body, dict) and "data" in body and body.get("status") in ("success", None):
        return body["data"]
    return body


# --------------------------------------------------------------------------------- time
def parse_duration(s, unit_default="s"):
    """'15m' / '1h' / '2d' / '500ms' / '30s' -> seconds (float)."""
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*(ms|us|s|m|h|d)?\s*$", str(s or ""))
    if not m:
        die("bad duration %r — use e.g. 500ms, 30s, 15m, 6h, 2d" % s)
    n = float(m.group(1))
    return n * {"us": 1e-6, "ms": 1e-3, "s": 1, "m": 60, "h": 3600, "d": 86400}[m.group(2) or unit_default]


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def window(a, rng=None):
    end = now_utc()
    start = end - datetime.timedelta(seconds=parse_duration(rng or a.since))
    return start, end


def ms(t):
    return int(t.timestamp() * 1000)


def iso_ms(v):
    """Epoch milliseconds -> ISO-8601 UTC; anything else unchanged."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return datetime.datetime.fromtimestamp(v / 1000.0, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return v


# ------------------------------------------------------------------------------- report
SEV_ORDER = {"crit": 0, "warn": 1, "info": 2}


class Report(object):
    def __init__(self, command, backend=None):
        self.command = command
        self.backend = backend
        self.prod = bool(backend and is_prod(backend["name"], host_of(backend["url"])))
        self.findings = []
        self.data = {}

    def add(self, severity, kind, name, message, evidence=None, ns=""):
        if severity not in SEV_ORDER:
            severity = "info"
        self.findings.append({"severity": severity, "kind": kind, "ns": ns or "",
                              "name": name or "", "message": message, "evidence": evidence})

    def section(self, name, items, max_items=None):
        if max_items and isinstance(items, list) and len(items) > max_items:
            self.data[name] = items[:max_items]
            self.data[name + "_truncated"] = True
            self.data[name + "_total"] = len(items)
        else:
            self.data[name] = items

    def exit_code(self):
        return 1 if any(f["severity"] in ("crit", "warn") for f in self.findings) else 0

    def sorted_findings(self):
        return sorted(self.findings, key=lambda f: (SEV_ORDER[f["severity"]], f["kind"],
                                                    f["ns"], f["name"]))

    def envelope(self):
        b = self.backend or {}
        return {"backend": b.get("name", ""), "kind": b.get("kind", ""), "prod": self.prod,
                "generated_at": now_utc().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "command": self.command, "findings": self.sorted_findings(), "data": self.data}

    def markdown(self):
        b = self.backend
        title = "# obs %s" % self.command
        if b:
            title += " — %s (%s)%s" % (b["name"], b["kind"], " [PROD]" if self.prod else "")
        out = [title, ""]
        fs = self.sorted_findings()
        out += ["## Findings (%d)" % len(fs), ""]
        if fs:
            out += ["| sev | kind | name | message |", "|---|---|---|---|"]
            for f in fs:
                out.append("| %s | %s | %s | %s |" % (f["severity"], f["kind"], md_cell(f["name"] or "-"),
                                                      md_cell(f["message"])))
        else:
            out.append("none")
        out.append("")
        for name, val in self.data.items():
            if name.endswith("_truncated") or name.endswith("_total"):
                continue
            out += ["## %s" % name, ""]
            out.extend(md_value(val))
            if self.data.get(name + "_truncated"):
                out += ["", "_showing %d of %d — rerun with --max-items N or narrow the query_"
                        % (len(val), self.data.get(name + "_total", len(val)))]
            out.append("")
        return "\n".join(out)

    def fitted_envelope(self, max_bytes):
        """The envelope, always a whole JSON document: over max_bytes, trailing items of the
        largest list (data lists first, then findings) are dropped until it fits, and
        "truncated" says how many. Still over with every list empty: emitted as is."""
        env = self.envelope()

        def dump(e):
            return json.dumps(e, indent=2, default=str)

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
            pool = [v for v in lists.values() if v] or ([env["findings"]] if env["findings"] else [])
            if not pool:
                break
            biggest = max(pool, key=lambda v: len(json.dumps(v, default=str)))
            biggest.pop()
            dropped += 1
            env["truncated"]["items_dropped"] = dropped
            txt = dump(env)
        return txt

    def emit(self, fmt, max_bytes):
        if fmt == "json":
            txt = self.fitted_envelope(max_bytes)
            sys.stdout.write(txt + "\n")
            return
        txt = self.markdown()
        raw = txt.encode("utf-8")
        if max_bytes and len(raw) > max_bytes:
            txt = raw[:max_bytes].decode("utf-8", "ignore")
            txt += "\n\n…[truncated %d bytes — narrow the query or rerun with --max-items N]" % (
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
                for k in row:
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
        return ["| key | value |", "|---|---|"] + ["| %s | %s |" % (md_cell(k), md_cell(v))
                                                    for k, v in val.items()]
    return [md_cell(val)]


def fmt_labels(labels, skip=("__name__",)):
    return ", ".join("%s=%s" % (k, red_text(v)) for k, v in sorted((labels or {}).items())
                     if k not in skip)[:200]


def num(v, nd=3):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return v
    return int(f) if f == int(f) else round(f, nd)


def unsupported(b, what, alt):
    raise Unsupported("%s is not available on a %s backend (%s) — %s"
                      % (what, b["kind"], b["name"], alt))


def start(a, command):
    b = pick_backend(a.backend)
    banner(b)
    return b, read_key(b), Report(command, b)


# ------------------------------------------------------------------------------ signoz
def signoz_range(b, key, a, rtype, queries, rng=None):
    st, en = window(a, rng)
    body = {"schemaVersion": "v1", "start": ms(st), "end": ms(en), "requestType": rtype,
            "compositeQuery": {"queries": queries}}
    data = unwrap(as_dict(b, _http(b, "POST", "/api/v5/query_range", body=body, key=key, timeout=a.timeout),
                          "/api/v5/query_range"))
    return ((data or {}).get("data") or {}).get("results") or [] if isinstance(data, dict) else []


def signoz_raw(b, key, a, signal, expr, limit, fields=None):
    spec = {"name": "A", "signal": signal, "filter": {"expression": expr},
            "order": [{"key": {"name": "timestamp"}, "direction": "desc"}], "limit": limit}
    if fields:
        spec["selectFields"] = fields
    rows = []
    for res in signoz_range(b, key, a, "raw", [{"type": "builder_query", "spec": spec}]):
        rows.extend(res.get("rows") or [])
    return rows


def sq(v):
    return "'%s'" % str(v).replace("\\", "\\\\").replace("'", "\\'")


# ------------------------------------------------------------------------------- query
def cmd_query(a):
    b, key, rep = start(a, "query")
    rep.data["query"] = a.query
    rows = []
    if b["kind"] == "prometheus":
        rows = prom_query(b, key, a)
    elif b["kind"] == "signoz":
        step = int(parse_duration(a.step))
        results = signoz_range(b, key, a, "time_series",
                               [{"type": "promql", "spec": {"name": "A", "query": a.query, "step": step}}],
                               rng=a.range)
        for res in results:
            for agg in res.get("aggregations") or []:
                for s in agg.get("series") or []:
                    labels = {}
                    for lab in s.get("labels") or []:
                        labels[(lab.get("key") or {}).get("name", "")] = lab.get("value")
                    vals = s.get("values") or []
                    row = {"metric": labels.get("__name__") or res.get("queryName", "A"),
                           "labels": fmt_labels(labels), "value": num(vals[-1].get("value")) if vals else ""}
                    if a.range:
                        row["samples"] = len(vals)
                    rows.append(row)
    else:
        if not a.datasource:
            die("a grafana backend needs --datasource UID (a Prometheus datasource; the Grafana UI "
                "shows the uid under Connections → Data sources)", 1)
        rows = grafana_metrics(b, key, a)
    rep.section("result", rows, a.max_items)
    return rep


def prom_query(b, key, a):
    if a.range:
        st, en = window(a, a.range)
        body = _http(b, "GET", "/api/v1/query_range", {"query": a.query, "start": int(st.timestamp()),
                                                       "end": int(en.timestamp()), "step": a.step},
                     key=key, timeout=a.timeout)
    else:
        body = _http(b, "GET", "/api/v1/query", {"query": a.query}, key=key, timeout=a.timeout)
    body = as_dict(b, body, "/api/v1/query")
    if body.get("status") != "success":
        die("prometheus: %s %s" % (body.get("errorType", ""), red_text(body.get("error", ""))[:300]), 1)
    data = body.get("data") or {}
    rows = []
    for item in data.get("result") or []:
        metric = item.get("metric") or {}
        if data.get("resultType") == "matrix":
            vals = item.get("values") or []
            row = {"metric": metric.get("__name__") or "{}", "labels": fmt_labels(metric),
                   "value": num(vals[-1][1]) if vals else "", "samples": len(vals)}
        else:
            row = {"metric": metric.get("__name__") or "{}", "labels": fmt_labels(metric),
                   "value": num((item.get("value") or ["", ""])[1])}
        rows.append(row)
    return rows


def grafana_ds(b, key, a, query, rng=None):
    st, en = window(a, rng)
    body = {"queries": [dict(query, refId="A", datasource={"uid": a.datasource})],
            "from": str(ms(st)), "to": str(ms(en))}
    resp = as_dict(b, _http(b, "POST", "/api/ds/query", body=body, key=key, timeout=a.timeout), "/api/ds/query")
    res = ((resp or {}).get("results") or {}).get("A") or {} if isinstance(resp, dict) else {}
    if res.get("error"):
        die("grafana datasource %s: %s" % (a.datasource, red_text(res["error"])[:300]), 1)
    return res.get("frames") or []


def grafana_metrics(b, key, a):
    q = {"expr": a.query, "instant": not a.range, "range": bool(a.range),
         "intervalMs": int(parse_duration(a.step) * 1000), "maxDataPoints": 1000}
    rows = []
    for fr in grafana_ds(b, key, a, q, rng=a.range):
        fields = (fr.get("schema") or {}).get("fields") or []
        values = (fr.get("data") or {}).get("values") or []
        for i, f in enumerate(fields):
            if f.get("type") != "number":
                continue
            vals = values[i] if i < len(values) else []
            labels = f.get("labels") or {}
            row = {"metric": labels.get("__name__") or f.get("name") or "{}",
                   "labels": fmt_labels(labels), "value": num(vals[-1]) if vals else ""}
            if a.range:
                row["samples"] = len(vals)
            rows.append(row)
    return rows


# -------------------------------------------------------------------------------- logs
def cmd_logs(a):
    b, key, rep = start(a, "logs")
    limit = a.limit or LOG_TAIL
    rows = []
    if b["kind"] == "prometheus":
        unsupported(b, "logs", "use a grafana backend with a Loki datasource, or `k8s pod NS POD` "
                    "for container logs")
    elif b["kind"] == "signoz":
        expr = a.filter or ""
        if a.service:
            expr = ("service.name = %s" % sq(a.service)) + (" AND (%s)" % expr if expr else "")
        for r in signoz_raw(b, key, a, "logs", expr, limit):
            d = r.get("data") or {}
            res = d.get("resources_string") or d.get("resource") or {}
            rows.append({"time": r.get("timestamp") or d.get("timestamp", ""),
                         "service": d.get("service.name") or res.get("service.name", ""),
                         "severity": d.get("severity_text", ""),
                         "body": red_text(d.get("body", ""))[:500]})
    else:
        if not a.datasource:
            die("a grafana backend needs --datasource UID (a Loki datasource)", 1)
        expr = a.filter or ""
        if not expr.lstrip().startswith("{"):
            sel = '{service_name=%s}' % json.dumps(a.service) if a.service else '{job=~".+"}'
            expr = sel + (" |= %s" % json.dumps(expr) if expr else "")
        for fr in grafana_ds(b, key, a, {"expr": expr, "queryType": "range", "maxLines": limit}):
            fields = (fr.get("schema") or {}).get("fields") or []
            values = (fr.get("data") or {}).get("values") or []
            col = {f.get("name"): (values[i] if i < len(values) else []) for i, f in enumerate(fields)}
            lines, times = col.get("Line") or col.get("line") or [], col.get("Time") or col.get("time") or []
            labels = col.get("labels") or []
            for i, line in enumerate(lines):
                lab = labels[i] if i < len(labels) and isinstance(labels[i], dict) else {}
                rows.append({"time": iso_ms(times[i]) if i < len(times) else "",
                             "service": lab.get("service_name") or lab.get("app") or a.service or "",
                             "severity": lab.get("level") or lab.get("detected_level", ""),
                             "body": red_text(line)[:500]})
    rep.data["filter"] = a.filter or ""
    rep.data["limit"] = limit
    rep.section("lines", rows[:limit])
    return rep


# ------------------------------------------------------------------------------ traces
TRACE_FIELDS = [{"name": "trace_id", "fieldContext": "span"}, {"name": "span_id", "fieldContext": "span"},
                {"name": "parent_span_id", "fieldContext": "span"}, {"name": "name", "fieldContext": "span"},
                {"name": "duration_nano", "fieldContext": "span"}, {"name": "has_error", "fieldContext": "span"},
                {"name": "service.name", "fieldContext": "resource"}]


def _dur_ms(d):
    try:
        return round(float(d.get("duration_nano") or 0) / 1e6, 1)
    except (TypeError, ValueError):
        return ""


def cmd_traces(a):
    b, key, rep = start(a, "traces")
    if b["kind"] != "signoz":
        unsupported(b, "traces", "use a signoz backend (Tempo is not supported in v1)")
    expr = "service.name = %s AND parent_span_id = ''" % sq(a.service)
    if a.error:
        expr += " AND has_error = true"
    if a.min_duration:
        expr += " AND duration_nano >= %d" % int(parse_duration(a.min_duration, "ms") * 1e9)
    rows = []
    for r in signoz_raw(b, key, a, "traces", expr, a.max_items, TRACE_FIELDS):
        d = r.get("data") or {}
        rows.append({"trace_id": d.get("trace_id", ""), "root_span": red_text(d.get("name", "")),
                     "duration_ms": _dur_ms(d), "status": "error" if d.get("has_error") else "ok",
                     "time": r.get("timestamp", "")})
    rep.data["filter"] = expr
    rep.section("traces", rows, a.max_items)
    return rep


def cmd_trace(a):
    b, key, rep = start(a, "trace")
    if b["kind"] != "signoz":
        unsupported(b, "trace", "use a signoz backend (Tempo is not supported in v1)")
    if not re.match(r"^[0-9a-fA-F]{16,32}$", a.trace_id):
        die("trace id must be 16 or 32 hex characters", 1)
    spans = []
    for r in signoz_raw(b, key, a, "traces", "trace_id = %s" % sq(a.trace_id), 1000):
        d = r.get("data") or {}
        attrs = {k: v for k, v in d.items() if isinstance(v, dict) and v}
        spans.append({"id": d.get("span_id", ""), "parent": d.get("parent_span_id", ""),
                      "name": red_text(d.get("name", "")), "service": d.get("service.name", ""),
                      "duration_ms": _dur_ms(d), "error": bool(d.get("has_error")),
                      "attributes": red_obj(attrs), "time": r.get("timestamp", "")})
    if not spans:
        rep.add("warn", "trace", a.trace_id, "no spans found in the last %s — widen --since" % a.since)
    ids = {s["id"] for s in spans}
    kids = {}
    for s in sorted(spans, key=lambda s: (s["time"], s["id"])):
        kids.setdefault(s["parent"] if s["parent"] in ids else "", []).append(s)
    rows, hidden = [], [0]

    def walk(parent, depth):
        for s in kids.get(parent, []):
            if depth >= a.depth:
                hidden[0] += 1 + count(s["id"])
                continue
            attrs = json.dumps(s["attributes"], sort_keys=True, default=str) if s["attributes"] else ""
            rows.append({"span": ("│ " * (depth - 1) + "└ " if depth else "") + s["name"], "service": s["service"],
                         "duration_ms": s["duration_ms"], "error": "yes" if s["error"] else "",
                         "attributes": attrs[:200]})
            walk(s["id"], depth + 1)

    def count(sid):
        return sum(1 + count(k["id"]) for k in kids.get(sid, []))

    walk("", 0)
    for s in spans:
        if s["error"]:
            rep.add("warn", "span-error", s["name"], "span %s (%s) has an error status" % (s["name"], s["service"]))
    rep.data["trace_id"] = a.trace_id
    rep.data["spans_total"] = len(spans)
    if hidden[0]:
        rep.data["spans_below_depth"] = "%d spans below --depth %d (rerun with a larger --depth)" % (hidden[0], a.depth)
    rep.section("tree", rows, a.max_items)
    return rep


# ---------------------------------------------------------------------------- services
def cmd_services(a):
    b, key, rep = start(a, "services")
    if b["kind"] != "signoz":
        unsupported(b, "services (RED per service)", "use `obs query` with your RED metrics, e.g. "
                    "sum by (service) (rate(http_server_requests_total[5m]))")
    st, en = window(a)
    body = {"start": str(ms(st) * 1000000), "end": str(ms(en) * 1000000), "tags": []}
    items = unwrap(_http(b, "POST", "/api/v1/services", body=body, key=key, timeout=a.timeout)) or []
    rows = []
    for it in items if isinstance(items, list) else []:
        er = float(it.get("errorRate") or 0)
        rows.append({"service": it.get("serviceName", ""), "calls": it.get("numCalls", 0),
                     "rate_per_s": num(it.get("callRate"), 2), "error_pct": num(er, 2),
                     "p99_ms": num(float(it.get("p99") or 0) / 1e6, 1),
                     "avg_ms": num(float(it.get("avgDuration") or 0) / 1e6, 1)})
        if er >= 5:
            rep.add("warn", "error-rate", it.get("serviceName", ""),
                    "error rate %.1f%% over %s — inspect with `obs traces --service %s --error`"
                    % (er, a.since, it.get("serviceName", "")))
    rows.sort(key=lambda r: (-float(r["error_pct"] or 0), r["service"]))
    rep.data["since"] = a.since
    rep.section("services", rows, a.max_items)
    return rep


# ------------------------------------------------------------------------------ alerts
SEV_MAP = {"critical": "crit", "page": "crit", "error": "crit", "warning": "warn", "warn": "warn"}


def cmd_alerts(a):
    b, key, rep = start(a, "alerts")
    want_rules = a.rules
    want_firing = a.firing or not a.rules
    if want_firing:
        if b["kind"] == "prometheus":
            raw = as_dict(b, unwrap(_http(b, "GET", "/api/v1/alerts", key=key, timeout=a.timeout)),
                          "/api/v1/alerts").get("alerts") or []
        elif b["kind"] == "signoz":
            raw = unwrap(_http(b, "GET", "/api/v1/alerts", key=key, timeout=a.timeout)) or []
        else:
            raw = _http(b, "GET", "/api/alertmanager/grafana/api/v2/alerts", {"active": "true"},
                        key=key, timeout=a.timeout) or []
        rows = []
        for al in raw if isinstance(raw, list) else []:
            labels, ann = al.get("labels") or {}, al.get("annotations") or {}
            state = al.get("state") or (al.get("status") or {}).get("state", "")
            if state not in ("firing", "active"):
                continue
            name = labels.get("alertname", "")
            sev = labels.get("severity", "")
            rows.append({"alert": name, "severity": sev, "since": al.get("activeAt") or al.get("startsAt", ""),
                         "labels": fmt_labels(labels, ("alertname", "severity")),
                         "summary": red_text(ann.get("summary") or ann.get("description") or "")[:200]})
            if SEV_MAP.get(sev.lower()):
                rep.add(SEV_MAP[sev.lower()], "firing", name, "%s firing (%s)%s" % (
                    name, sev, " — runbook: %s" % ann["runbook_url"] if ann.get("runbook_url") else ""))
        rows.sort(key=lambda r: (SEV_ORDER.get(SEV_MAP.get(r["severity"].lower(), "info"), 2), r["alert"]))
        rep.section("firing", rows, a.max_items)
    if want_rules:
        rows = []
        if b["kind"] == "signoz":
            body = unwrap(_http(b, "GET", "/api/v1/rules", key=key, timeout=a.timeout)) or {}
            for r in (body.get("rules") or []) if isinstance(body, dict) else []:
                rows.append({"rule": r.get("alert", ""), "type": r.get("ruleType", ""),
                             "state": "disabled" if r.get("disabled") else r.get("state", ""),
                             "severity": (r.get("labels") or {}).get("severity", ""),
                             "eval": r.get("evalWindow", ""), "id": r.get("id", "")})
        else:
            path = "/api/v1/rules" if b["kind"] == "prometheus" else "/api/prometheus/grafana/api/v1/rules"
            body = unwrap(_http(b, "GET", path, key=key, timeout=a.timeout)) or {}
            for g in (body.get("groups") or []) if isinstance(body, dict) else []:
                for r in g.get("rules") or []:
                    if r.get("type") not in ("alerting", None):
                        continue
                    dur = r.get("duration", "")
                    rows.append({"rule": r.get("name", ""), "group": g.get("name", ""),
                                 "state": r.get("state", ""),
                                 "for": "%ss" % num(dur) if isinstance(dur, (int, float)) else dur,
                                 "severity": (r.get("labels") or {}).get("severity", ""),
                                 "expr": red_text(r.get("query", ""))[:160]})
        rows.sort(key=lambda r: r["rule"])
        rep.section("rules", rows, a.max_items)
    return rep


# --------------------------------------------------------------------------- dashboards
def cmd_dashboards(a):
    b, key, rep = start(a, "dashboards")
    if b["kind"] == "prometheus":
        unsupported(b, "dashboards", "use a grafana or signoz backend")
    if a.export:
        uid, path = a.export
        if os.path.lexists(path) and not a.force:
            die("%s already exists — nothing fetched or written; pass --force to overwrite it, or "
                "export to a new file and diff the two" % path, 1)
        if b["kind"] == "signoz":
            if not re.match(r"^[A-Za-z0-9-]+$", uid):
                die("dashboard id must be letters, digits and dashes", 1)
            dash = (unwrap(_http(b, "GET", "/api/v1/dashboards/" + uid, key=key, timeout=a.timeout)) or {})
            dash = dash.get("data", dash) if isinstance(dash, dict) else dash
        else:
            if not re.match(r"^[A-Za-z0-9._-]+$", uid):
                die("dashboard uid must be letters, digits, dot, dash or underscore", 1)
            dash = (_http(b, "GET", "/api/dashboards/uid/" + uid, key=key, timeout=a.timeout) or {})
            dash = dash.get("dashboard", dash) if isinstance(dash, dict) else dash
        if not dash:
            die("dashboard %s: the backend answered an empty body — nothing written%s"
                % (uid, " (OBS_DRY_RUN=1 without OBS_HTTP_FIXTURES answers every request with {})"
                   if os.environ.get("OBS_DRY_RUN") == "1" else "; check the uid with `obs dashboards`"), 1)
        clean = red_obj(dash)
        n_red = json.dumps(clean).count(REDACTED)
        txt = json.dumps(clean, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        if len(txt.encode("utf-8")) > a.max_bytes:
            die("dashboard %s is %d bytes, over --max-bytes %d — nothing written; raise --max-bytes "
                "if the file is meant to be that large" % (uid, len(txt.encode("utf-8")), a.max_bytes), 1)
        with open(path, "w") as fh:
            fh.write(txt)
        rep.data["exported"] = {"uid": uid, "file": path, "bytes": len(txt.encode("utf-8")),
                                "title": (dash or {}).get("title", "") if isinstance(dash, dict) else ""}
        if n_red:
            rep.add("warn", "redacted", uid, "%d secret-looking value(s) replaced by %s in %s — review "
                    "them before committing" % (n_red, REDACTED, path))
        rep.add("info", "next", uid, "edit %s in the owning repository and open an MR; never write "
                "the dashboard back through the API" % path)
        return rep
    rows = []
    if b["kind"] == "signoz":
        items = unwrap(_http(b, "GET", "/api/v1/dashboards", key=key, timeout=a.timeout)) or []
        for d in items if isinstance(items, list) else []:
            data = d.get("data") or {}
            rows.append({"id": d.get("id", ""), "title": data.get("title", ""),
                         "tags": ", ".join(data.get("tags") or []), "updated": d.get("updatedAt", ""),
                         "locked": bool(d.get("locked"))})
    else:
        items = _http(b, "GET", "/api/search", {"type": "dash-db", "limit": max(a.max_items, 1)},
                      key=key, timeout=a.timeout) or []
        for d in items if isinstance(items, list) else []:
            rows.append({"uid": d.get("uid", ""), "title": d.get("title", ""),
                         "folder": d.get("folderTitle", ""), "tags": ", ".join(d.get("tags") or [])})
    rows.sort(key=lambda r: (r["title"], r.get("id") or r.get("uid")))
    rep.section("dashboards", rows, a.max_items)
    return rep


# ----------------------------------------------------------------------------- backends
HOSTS_RE_DIALECT_MSG = ("hosts_re is a POSIX ERE used by the guard; use [0-9], [A-Za-z0-9_], "
                        "[[:space:]]")
_PY_ONLY_RE = re.compile(r"\\[dwsDWS]|\(\?")


class HostsEre(object):
    """obs.hosts_re as the guard applies it: `grep -E` (POSIX ERE), pattern passed via argv.
    Python-only syntax is a finding; so is any host where Python re and grep -E disagree."""

    def __init__(self, pattern, rep):
        self.pattern, self.rep, self.grep_ok, self.py = pattern, rep, True, None
        if _PY_ONLY_RE.search(pattern):
            rep.add("warn", "hosts_re", "obs.hosts_re", "%s (found %s)"
                    % (HOSTS_RE_DIALECT_MSG, _PY_ONLY_RE.search(pattern).group(0)))
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                self.py = re.compile(pattern)
            except re.error:
                self.py = None
        rc = self._grep("")
        if rc == 2:
            self.grep_ok = False
            rep.add("warn", "hosts_re", "obs.hosts_re", "not a valid POSIX ERE (grep -E rejects it): the guard's "
                    "host rows never match; fix obs.hosts_re and run `harness apply`")

    def _grep(self, host):
        """0 match, 1 no match, 2 invalid pattern, None when grep is not on PATH."""
        import subprocess
        try:
            return subprocess.run(["grep", "-qE", "-e", self.pattern], input=host.encode(),
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
        except OSError:
            return None

    def covers(self, name, host):
        py = bool(self.py.search(host)) if self.py is not None else None
        if not self.grep_ok:
            return False
        rc = self._grep(host)
        if rc is None:
            return bool(py)
        grep = rc == 0
        if py is not None and py != grep:
            self.rep.add("warn", "hosts_re", name, "Python re and grep -E disagree on host %s (grep -E: %s, "
                         "Python: %s); the guard uses grep -E — %s"
                         % (host, "match" if grep else "no match", "match" if py else "no match",
                            HOSTS_RE_DIALECT_MSG))
        return grep


def cmd_backends(a):
    backends = load_backends()
    if a.names:
        for b in backends:
            print(b["name"])
        sys.exit(0)
    rep = Report("backends")
    default = _env_or_cfg("OBS_DEFAULT", "obs.default", "") or (backends[0]["name"] if backends else "")
    hosts_re = _env_or_cfg("OBS_HOSTS_RE", "obs.hosts_re", "")
    ere = HostsEre(hosts_re, rep) if hosts_re else None
    worst = 0
    rows = []
    if not backends:
        rep.add("info", "config", "obs.backends", "no backends configured — add [[obs.backends]] to "
                "local/harness.toml (manual step configure-backends)")
    elif not hosts_re:
        rep.add("warn", "hosts_re", "obs.hosts_re", "empty while backends are configured: raw curl to "
                "them is not guarded; set obs.hosts_re to a regex of their hosts and run `harness apply`")
    for b in backends:
        status, path = key_status(b)
        host = host_of(b["url"])
        row = {"name": b["name"], "kind": b["kind"], "host": host, "key": status,
               "default": b["name"] == default, "prod": bool(is_prod(b["name"], host))}
        if status == "missing":
            worst = 2
            rep.add("crit", "key", b["name"], "key file %s is missing — create it with `install -m 600` "
                    "(manual step obs-api-key)" % b["auth_file"])
        elif status.startswith("mode-"):
            rep.add("warn", "key", b["name"], "key file %s has %s; run `chmod 600 %s`"
                    % (b["auth_file"], status, b["auth_file"]))
        elif status == "none" and b["kind"] != "prometheus":
            worst = 2
            rep.add("crit", "key", b["name"], "no auth_file set; a %s backend needs one (manual step "
                    "obs-api-key)" % b["kind"])
        hostname = urllib.parse.urlsplit(b["url"]).hostname or host
        if ere is not None and not ere.covers(b["name"], hostname):
            rep.add("warn", "hosts_re", b["name"], "host %s does not match obs.hosts_re under grep -E (matched "
                    "against the host name, no scheme or port): raw curl to it is not guarded; extend "
                    "obs.hosts_re" % hostname)
        if a.probe:
            row.update(probe(b, a, status, rep))
            if row.get("reachable") is False or row.get("auth") == "refused":
                worst = 2
        rows.append(row)
    rep.data["default"] = default
    rep.data["hosts_re"] = hosts_re
    rep.section("backends", rows, a.max_items)
    rep.forced_exit = worst
    return rep


def probe(b, a, status, rep):
    out = {"reachable": None, "version": "", "auth": ""}
    if status == "missing" or (status == "none" and b["kind"] != "prometheus"):
        out["auth"] = "no key"
        return out
    print("probe: backend=%s kind=%s url=%s%s" % (b["name"], b["kind"], host_of(b["url"]),
                                                  " [PROD]" if is_prod(b["name"], host_of(b["url"])) else ""),
          file=sys.stderr)
    # step 1: the version/health endpoint proves the url reaches this kind of backend; a 404
    # there means the url points somewhere else (wrong host or path prefix): unreachable.
    # step 2: an authenticated read proves the key.
    first = {"signoz": "/api/v1/version", "prometheus": "/api/v1/status/buildinfo",
             "grafana": "/api/health"}[b["kind"]]
    step = 1
    try:
        key = read_key(b)
        v = unwrap(_http(b, "GET", first, key=key, timeout=a.timeout))
        out["version"] = v.get("version", "") if isinstance(v, dict) else ""
        step = 2
        if b["kind"] == "signoz":
            _http(b, "GET", "/api/v1/rules", key=key, timeout=a.timeout)
        elif b["kind"] == "grafana":
            _http(b, "GET", "/api/search", {"limit": 1}, key=key, timeout=a.timeout)
        out["reachable"], out["auth"] = True, "ok"
    except NotFound as e:
        if step == 1:
            out["reachable"] = False
            out["note"] = "%s answered 404 — not a %s API at this url" % (first, b["kind"])
            rep.add("crit", "probe", b["name"], "%s answered 404 for GET %s%s: not a %s API at this url — "
                    "check the url (host and path prefix) in [[obs.backends]]"
                    % (b["name"], b["url"], first, b["kind"]))
        else:
            out["reachable"], out["auth"] = True, "?"
            out["note"] = "authenticated read answered 404"
            rep.add("warn", "probe", b["name"], str(e))
    except AccessError as e:
        msg = str(e)
        refused = re.search(r"answered (401|403)", msg)
        out["reachable"], out["auth"] = (True, "refused") if refused else (False, "")
        rep.add("crit", "probe", b["name"], msg)
    return out


# --------------------------------------------------------------------------------- lint
_HARDCODED_RE = re.compile(r"\b(namespace|instance|pod|node)\s*(=|=~)\s*\"(?!\$)[^\"]+\"")


def _key_lines(text, key, value):
    """1-based lines where `key: value` / "key": "value" appears with value as a whole token —
    `alert: HighLatency` never matches `alert: HighLatencyCritical`."""
    rx = re.compile(r"""(?m)(?<![\w-])["']?%s["']?\s*:\s*(["']?)%s\1(?![\w.:-])"""
                    % (re.escape(key), re.escape(value)))
    return [text.count("\n", 0, m.start()) + 1 for m in rx.finditer(text)]


class _Lines(object):
    """Per-file line lookup: the n-th call for the same (key, value) returns its n-th
    occurrence, so duplicates point at their own lines. No state outlives one file."""

    def __init__(self, text):
        self.text, self.seen = text, {}

    def of(self, value, *keys):
        found = sorted(set(n for k in keys for n in _key_lines(self.text, k, value)))
        n = self.seen.get((keys, value), 0)
        self.seen[(keys, value)] = n + 1
        return found[n] if n < len(found) else (found[-1] if found else 1)


def _load(path, rep):
    try:
        with open(path) as fh:
            text = fh.read()
    except OSError as e:
        rep.add("crit", "file", path, "cannot read: %s" % e.strerror)
        return None, ""
    if path.endswith((".yaml", ".yml")):
        try:
            import yaml  # optional: PyYAML when importable, else JSON only
        except ImportError:
            rep.add("warn", "parse", "%s:1" % path, "PyYAML is not importable; convert the file to JSON "
                    "(`yq -o json`) or run `promtool check rules` instead")
            return None, text
        try:
            return yaml.safe_load(text), text
        except yaml.YAMLError as e:
            mark = getattr(e, "problem_mark", None)
            rep.add("crit", "parse", "%s:%d" % (path, (mark.line + 1) if mark else 1), "invalid YAML: %s" % e)
            return None, text
    try:
        return json.loads(text), text
    except ValueError as e:
        rep.add("crit", "parse", "%s:%d" % (path, getattr(e, "lineno", 1)), "invalid JSON: %s" % e)
        return None, text


def lint_prom(path, doc, text, rep, seen):
    lines = _Lines(text)
    for g in doc.get("groups") or []:
        for r in g.get("rules") or []:
            name = r.get("alert")
            if not name:
                continue
            at = "%s:%d" % (path, lines.of(name, "alert"))
            if name in seen:
                rep.add("warn", "duplicate", at, "alert %s is also defined at %s — give each alert a unique "
                        "name" % (name, seen[name]))
            else:
                seen[name] = at
            if not r.get("for"):
                rep.add("warn", "for", at, "alert %s has no `for:` — add `for: 5m` (or longer) so one bad "
                        "scrape does not page" % name)
            if not (r.get("labels") or {}).get("severity"):
                rep.add("warn", "severity", at, "alert %s has no severity label — add `labels: {severity: "
                        "warning|critical}` so routing works" % name)
            ann = r.get("annotations") or {}
            if not ann.get("runbook_url"):
                rep.add("warn", "runbook", at, "alert %s has no runbook_url annotation — link the runbook "
                        "the responder should open" % name)
            if not (ann.get("description") or ann.get("summary")):
                rep.add("warn", "description", at, "alert %s has no description/summary annotation — say "
                        "what is wrong and for whom" % name)
            m = _HARDCODED_RE.search(str(r.get("expr", "")))
            if m:
                rep.add("warn", "hardcoded", at, "alert %s pins %s=\"…\" in its expression — aggregate "
                        "`by (%s)` instead so the rule covers every %s" % (name, m.group(1), m.group(1), m.group(1)))


def lint_signoz(path, doc, text, rep, seen):
    name = doc.get("alert", "")
    at = "%s:%d" % (path, _Lines(text).of(name, "alert") if isinstance(name, str) and name else 1)
    if name in seen:
        rep.add("warn", "duplicate", at, "alert %s is also defined at %s — give each alert a unique name"
                % (name, seen[name]))
    else:
        seen[name] = at
    if not doc.get("ruleType"):
        rep.add("warn", "ruleType", at, "SigNoz alert %s has no ruleType — set \"threshold_rule\" or "
                "\"promql_rule\"" % name)
    cond = doc.get("condition") or {}
    if cond.get("target") is None and not cond.get("thresholds"):
        rep.add("warn", "threshold", at, "SigNoz alert %s has no threshold (condition.target or "
                "condition.thresholds) — set one, or the rule never fires" % name)
    if not (doc.get("labels") or {}).get("severity"):
        rep.add("warn", "severity", at, "SigNoz alert %s has no severity label — add labels.severity" % name)
    ann = doc.get("annotations") or {}
    if not (ann.get("description") or ann.get("summary")):
        rep.add("warn", "description", at, "SigNoz alert %s has no description/summary annotation — say "
                "what is wrong and for whom" % name)


def _panels(doc):
    for p in doc.get("panels") or []:
        yield p
        for sub in p.get("panels") or []:
            yield sub
    for row in doc.get("rows") or []:
        for p in row.get("panels") or []:
            yield p


def lint_grafana(path, doc, text, rep, seen):
    doc = doc.get("dashboard", doc)
    title = doc.get("title", "")
    lines = _Lines(text)
    if not doc.get("uid"):
        rep.add("warn", "uid", "%s:1" % path, "dashboard %r has no uid — set a stable uid so links and "
                "provisioning survive re-imports" % title)
    if not title:
        rep.add("warn", "title", "%s:1" % path, "dashboard has no title — set one")
    for p in _panels(doc):
        for ds in [p.get("datasource")] + [t.get("datasource") for t in p.get("targets") or []]:
            uid = ds.get("uid") if isinstance(ds, dict) else ds
            if isinstance(uid, str) and uid and not uid.startswith("$") and uid not in ("-- Grafana --", "-- Mixed --", "-- Dashboard --"):
                rep.add("warn", "datasource", "%s:%d" % (path, lines.of(uid, "uid", "datasource")),
                        "panel %r pins datasource uid %r — use a datasource template variable "
                        "(${datasource}) so the dashboard works in every environment"
                        % (p.get("title", ""), uid))
                break


def cmd_lint(a):
    rep = Report("lint")
    seen, checked = {}, []
    for path in a.files:
        doc, text = _load(path, rep)
        if doc is None:
            continue
        if isinstance(doc, dict) and "groups" in doc:
            lint_prom(path, doc, text, rep, seen)
            kind = "prometheus-rules"
        elif isinstance(doc, dict) and "alert" in doc and ("condition" in doc or "ruleType" in doc or "alertType" in doc):
            lint_signoz(path, doc, text, rep, seen)
            kind = "signoz-alert"
        elif isinstance(doc, dict) and ("panels" in doc or "rows" in doc or "dashboard" in doc):
            lint_grafana(path, doc, text, rep, seen)
            kind = "grafana-dashboard"
        else:
            rep.add("warn", "unknown", "%s:1" % path, "not a Prometheus rule file, SigNoz alert or Grafana "
                    "dashboard — check the file, or lint it with its own tool")
            kind = "unknown"
        checked.append({"file": path, "kind": kind})
    rep.data["files"] = checked
    return rep


# -------------------------------------------------------------------------------- redact
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
    sys.stdout.write(json.dumps(red_obj(obj), indent=indent, default=str) + "\n")
    sys.exit(0)


# -------------------------------------------------------------------------------- parser
class _Parser(argparse.ArgumentParser):
    def error(self, message):
        die("obs %s: %s\n\nRun `obs` with no arguments for the command list."
            % (self.prog.split()[-1] if " " in self.prog else "", message), 1)


def common_parser():
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--backend", help="backend name (default obs.default, else the first configured)")
    p.add_argument("--json", action="store_true", help="force JSON output")
    p.add_argument("--md", action="store_true", help="force Markdown output")
    p.add_argument("--timeout", type=int, default=TIMEOUT, help="per-request timeout seconds")
    p.add_argument("--max-items", type=int, default=50, dest="max_items")
    p.add_argument("--max-bytes", type=int, default=MAX_BYTES, dest="max_bytes")
    p.add_argument("--since", default="15m", help="look-back window (default 15m)")
    return p


def build_parser():
    common = common_parser()
    top = _Parser(prog="obs", description="Read-only observability client", add_help=False)
    subs = top.add_subparsers(dest="cmd")

    def sub(name, **kw):
        return subs.add_parser(name, parents=[common], **kw)

    s = sub("backends", help="configured backends and key status")
    s.add_argument("--probe", action="store_true", help="reachability, version and an authenticated read")
    s.add_argument("--names", action="store_true", help="print backend names only (offline)")
    s.set_defaults(fn=cmd_backends)

    s = sub("query", help="PromQL query")
    s.add_argument("query", metavar="PROMQL")
    s.add_argument("--range", help="range query window, e.g. 1h")
    s.add_argument("--step", default="60s")
    s.add_argument("--datasource", metavar="UID", help="grafana: Prometheus datasource uid")
    s.set_defaults(fn=cmd_query)

    s = sub("logs", help="bounded, redacted log lines")
    s.add_argument("filter", metavar="FILTER", nargs="?", default="")
    s.add_argument("--service")
    s.add_argument("--limit", type=int, default=0, help="lines (default obs.log_tail)")
    s.add_argument("--datasource", metavar="UID", help="grafana: Loki datasource uid")
    s.set_defaults(fn=cmd_logs)

    s = sub("traces", help="recent root spans of a service")
    s.add_argument("--service", required=True)
    s.add_argument("--error", action="store_true")
    s.add_argument("--min-duration", dest="min_duration")
    s.set_defaults(fn=cmd_traces)

    s = sub("trace", help="span tree of one trace")
    s.add_argument("trace_id", metavar="ID")
    s.add_argument("--depth", type=int, default=3)
    s.set_defaults(fn=cmd_trace)

    s = sub("services", help="RED per service")
    s.set_defaults(fn=cmd_services)

    s = sub("alerts", help="firing alerts and/or rules")
    s.add_argument("--firing", action="store_true")
    s.add_argument("--rules", action="store_true")
    s.set_defaults(fn=cmd_alerts)

    s = sub("dashboards", help="list or export dashboards")
    s.add_argument("--export", nargs=2, metavar=("UID", "FILE"))
    s.add_argument("--force", action="store_true", help="--export: overwrite an existing FILE")
    s.set_defaults(fn=cmd_dashboards)

    s = sub("lint", help="alert rules and dashboards as code")
    s.add_argument("files", metavar="FILE", nargs="+")
    s.set_defaults(fn=cmd_lint)

    s = sub("redact", help="stdin -> redacted stdout")
    s.set_defaults(fn=cmd_redact)
    return top, list(subs.choices)


GLOBAL_VALUE_FLAGS = ("--backend", "--timeout", "--max-items", "--max-bytes", "--since")


def hoist_globals(argv):
    """`obs --backend X query …` == `obs query … --backend X`: global flags may precede the command."""
    lead = []
    while argv and argv[0].startswith("--") and argv[0] not in ("--help",):
        flag = argv.pop(0)
        lead.append(flag)
        if flag in GLOBAL_VALUE_FLAGS and argv:
            lead.append(argv.pop(0))
    return argv[:1] + lead + argv[1:] if argv else lead


def main():
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        sys.exit(1)
    if argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        sys.exit(0)
    argv = hoist_globals(argv)
    top, names = build_parser()
    if argv[0] not in names:
        die("Unknown command %r. Commands: %s\n\nRun `obs` with no arguments for the full usage."
            % (argv[0], ", ".join(names)), 1)
    a = top.parse_args(argv)
    try:
        rep = a.fn(a)
    except AccessError as e:
        die(red_text(str(e)), 2)
    except Unsupported as e:
        die(str(e), 3)
    except BrokenPipeError:
        sys.exit(0)
    fmt = "json" if a.json else ("md" if a.md else ("md" if sys.stdout.isatty() else "json"))
    rep.emit(fmt, a.max_bytes)
    forced = getattr(rep, "forced_exit", 0)
    sys.exit(forced if forced else rep.exit_code())


if __name__ == "__main__":
    main()
