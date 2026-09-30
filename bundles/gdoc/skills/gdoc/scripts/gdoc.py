#!/usr/bin/env python3
"""Google Workspace (Docs / Drive / Sheets / Gmail) client — stdlib only.

Canonical invocation: `gdoc <cmd>` (symlinked into ~/.local/bin, like `jira`).
One Google account (typically your Workspace account). Shared drives are supported
(every Drive call sends supportsAllDrives=true). The sign-in is restricted to the Workspace
domain in $GDOC_HD, else `google.domain` from the harness config (HARNESS_CONFIG_JSON /
HARNESS_HOME); with neither set any Google account may sign in.

Auth: installed-app OAuth (Desktop client + PKCE loopback). Two files, never
printed, mode 0600 in a 0700 directory:
  ~/.config/gdoc/client_secret.json   downloaded from the GCP console (one time)
  ~/.config/gdoc/token.json           written by `gdoc auth login`
See references/setup.md for the one-time human setup.

Provenance: files this tool creates carry public Drive `properties`
  agent_provenance=agent-created|agent-worked, agent_tool=claude-code,
  agent_created_at / agent_marked_at (ISO 8601).
The guard hook reads `gdoc meta <ID> | jq -r .properties.agent_provenance` to
decide whether a write runs promptless.

Exit codes: 0 ok, 2 auth/connection/scope/API-not-enabled (run `gdoc auth login`,
or enable the API — see references/setup.md), 1 everything else.

IDs: every <ID> argument accepts a bare Drive id or a docs/drive/sheets URL.

Commands (run with no args to print this list):

  whoami                      Verify the token; prints account email, granted scopes, expiry.
  auth login [--scopes a,b,..] [--no-browser] [--hint EMAIL]
                              Run the OAuth flow in a browser and cache the refresh token.
                              --scopes aliases: docs, drive, sheets, gmail (default:
                              drive + gmail.readonly + gmail.compose).
                              --no-browser: paste the redirect URL back (WSL2 fallback).
  auth status                 Offline: which credential files exist, their modes, scopes, expiry.

  search <QUERY> [max]        Search Drive (default max 25). A bare phrase is wrapped as
                              fullText contains '<QUERY>' and trashed=false; a query that
                              already uses Drive operators is passed through. e.g.:
                                search "release checklist"
                                search "name contains 'QBR' and mimeType='application/vnd.google-apps.document'"
  list [--folder ID] [max]    List a folder's contents (or recent files without --folder).
  meta <ID|URL>               Raw file metadata as JSON (id, name, mimeType, properties,
                              owners, parents, capabilities, webViewLink). Hook contract.
  get <ID|URL> [--json] [--tab TABID]
                              Outline a Google Doc: tabs, headings (H1..H6/TITLE) with their
                              UTF-16 index ranges, word count and endIndex per tab.
                              --json prints the raw documents.get response.
  export <ID|URL> [--md|--txt|--csv] [FILE]
                              Export a Doc (default Markdown) or Sheet (default CSV, first
                              sheet) to FILE, or to stdout when FILE is omitted.
  comments <ID|URL>           List comments: id | open/resolved | author | text (+ quoted text).
  sheet get <ID|URL> [RANGE]  No RANGE: list the sheets (title, sheetId, rows x cols).
                              With RANGE (e.g. 'Sheet1!A1:D20'): print the values as TSV.
  mail search <QUERY> [max]   Gmail search (default max 20): id | threadId | date | from | subject.
  mail get <MSGID>            Headers + plain-text body (HTML stripped as a fallback);
                              attachments are listed by name and size only.
  api <URL>                   GET-only escape hatch; prints raw JSON. https only, and the host
                              must be one of: www.googleapis.com, docs.googleapis.com,
                              sheets.googleapis.com, gmail.googleapis.com.

  create <TITLE> --from FILE.md [--folder ID] [--plain]
                              Create a new Google Doc from a local Markdown (or --plain text)
                              file, stamped agent_provenance=agent-created. Prints id + link.
  import <ID|URL> FILE.md [--force]
                              Replace the WHOLE document with the contents of FILE.md, keeping
                              the id, link and sharing. Comments, suggestions and extra tabs are
                              lost; refuses when the doc has unresolved comments unless --force.
                              (Drive revision history is kept.)
  append <ID|URL> <TEXT|--from FILE> [--heading H] [--tab TABID]
                              Append plain text (optionally under a new H2 heading) to the end
                              of a Doc, or of one tab. No Markdown is interpreted.
  replace <ID|URL> <FIND> <REPL> [--match-case] [--tab TABID]
                              replaceAllText across the doc (all tabs unless --tab); prints the
                              number of occurrences changed.
  mark <ID|URL> agent-created|agent-worked|none
                              Set (or with `none` clear) the Drive provenance properties. This is
                              the one-time handshake that adopts a human file; it always prompts.
  sheet append <ID|URL> <RANGE> <JSON-ROWS|@FILE>
                              Append rows, e.g. 'Sheet1!A:C' '[["a","b","c"]]'.
  sheet update <ID|URL> <RANGE> <JSON-ROWS|@FILE>
                              Overwrite a range with rows (USER_ENTERED).
  mail draft --to A [--cc B] --subject S (--body TEXT|--body-file F) [--reply-to MSGID]
                              Create a Gmail draft. --reply-to threads the draft onto an
                              existing message and then supplies the default recipient
                              (its Reply-To/From) and a `Re:` subject, so --to is only
                              required without it.

gdoc never SENDS mail — it only drafts. The draft waits in Gmail and the user sends it
themselves; there is no send verb to work around (and none via `api`, which is GET-only).

Deliberately NOT implemented (do not work around them with `api`): sending mail, sharing and
permissions, delete/trash, Calendar, writing document comments.

Env: GDOC_DRY_RUN=1 prints every non-GET request as `DRY-RUN <METHOD> <URL> <BODY>`
to stderr instead of sending it (and skips the read-back), GDOC_TIMEOUT (seconds,
default 30).
"""
import base64
import json
import os
import re
import secrets
import sys
import time
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


def workspace_domain():
    """Workspace domain for the OAuth `hd` hint: $GDOC_HD, else google.domain; '' = any account."""
    return (os.environ.get("GDOC_HD") or cfg("google.domain") or "").strip()
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from html.parser import HTMLParser

CONF_DIR = os.path.expanduser("~/.config/gdoc")
CLIENT_FILE = os.path.join(CONF_DIR, "client_secret.json")
TOKEN_FILE = os.path.join(CONF_DIR, "token.json")

DRIVE = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3"
DOCS = "https://docs.googleapis.com/v1"
SHEETS = "https://sheets.googleapis.com/v4"
GMAIL = "https://gmail.googleapis.com/gmail/v1"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"

API_HOSTS = {"www.googleapis.com", "docs.googleapis.com",
             "sheets.googleapis.com", "gmail.googleapis.com"}

DOC_MIME = "application/vnd.google-apps.document"
SHEET_MIME = "application/vnd.google-apps.spreadsheet"
FOLDER_MIME = "application/vnd.google-apps.folder"

PROV_KEYS = ("agent_provenance", "agent_tool", "agent_created_at", "agent_marked_at")

SCOPE_ALIASES = {
    "drive": ["https://www.googleapis.com/auth/drive"],
    "docs": ["https://www.googleapis.com/auth/documents"],
    "sheets": ["https://www.googleapis.com/auth/spreadsheets"],
    # gmail.readonly reads; gmail.compose creates drafts. Neither can send on its own,
    # and gdoc has no send verb.
    "gmail": ["https://www.googleapis.com/auth/gmail.readonly",
              "https://www.googleapis.com/auth/gmail.compose"],
    "gmail.readonly": ["https://www.googleapis.com/auth/gmail.readonly"],
    "gmail.compose": ["https://www.googleapis.com/auth/gmail.compose"],
}
# The drive scope covers the Docs and Sheets APIs too, so it is the only file scope
# requested by default.
DEFAULT_SCOPES = SCOPE_ALIASES["drive"] + SCOPE_ALIASES["gmail"]

ID_RE = re.compile(r"^[A-Za-z0-9_-]{20,}$")
URL_RES = (
    re.compile(r"(?:docs|drive|sheets)\.google\.com/"
               r"(?:document|spreadsheets|presentations|file)/d/([A-Za-z0-9_-]{20,})"),
    re.compile(r"drive\.google\.com/drive/(?:u/\d+/)?folders/([A-Za-z0-9_-]{20,})"),
    re.compile(r"[?&]id=([A-Za-z0-9_-]{20,})"),
)
# A Drive query that already uses the query language is passed through untouched.
DRIVE_OP_RE = re.compile(
    r"\b(contains|in parents|in owners|in writers|in readers|mimeType|trashed|fullText|"
    r"modifiedTime|createdTime|starred|sharedWithMe|owners|writers|readers|"
    r"properties|appProperties|visibility|parents|name\s*=|name\s*!=)\b")

HEADING_STYLES = {"TITLE": "TITLE", "SUBTITLE": "SUBTITLE",
                  "HEADING_1": "H1", "HEADING_2": "H2", "HEADING_3": "H3",
                  "HEADING_4": "H4", "HEADING_5": "H5", "HEADING_6": "H6"}


# ---------------------------------------------------------------- core helpers

def die(msg, code=1):
    sys.stdout.flush()  # keep already-printed output ahead of the error when piped
    print(msg, file=sys.stderr)
    sys.exit(code)


def dry_run():
    return os.environ.get("GDOC_DRY_RUN") == "1"


def timeout():
    try:
        return int(os.environ.get("GDOC_TIMEOUT", "30"))
    except ValueError:
        return 30


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def file_id(arg):
    """Accept a bare Drive id or a docs/drive/sheets URL; die otherwise."""
    tok = (arg or "").strip().strip("\"'")
    if ID_RE.match(tok):
        return tok
    for rx in URL_RES:
        m = rx.search(tok)
        if m:
            return m.group(1)
    die(f"'{arg}' is not a Drive file id or a docs/drive/sheets URL. "
        f"Find one with `gdoc search <query>` or paste the document URL.")


def utf16len(s):
    """Docs API indexes count UTF-16 code units, not Python characters."""
    return len(s.encode("utf-16-le")) // 2


def _write_secret(path, data):
    """Atomic 0600 write inside a 0700 directory (never printed anywhere)."""
    os.makedirs(CONF_DIR, mode=0o700, exist_ok=True)
    try:
        os.chmod(CONF_DIR, 0o700)
    except OSError:
        pass
    tmp = f"{path}.tmp.{os.getpid()}"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data if isinstance(data, bytes) else data.encode())
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def load_client():
    if not os.path.exists(CLIENT_FILE):
        die(f"No OAuth client at {CLIENT_FILE}. Do the one-time setup in the gdoc skill's "
            f"references/setup.md (GCP console -> Credentials -> OAuth client ID -> Desktop "
            f"app -> download JSON), then run `gdoc auth login`.", 2)
    try:
        with open(CLIENT_FILE) as f:
            blob = json.load(f)
    except (OSError, ValueError) as e:
        die(f"Cannot read {CLIENT_FILE}: {e.__class__.__name__}. Re-download the Desktop "
            f"OAuth client JSON (see references/setup.md).", 2)
    if "web" in blob and "installed" not in blob:
        die(f"{CLIENT_FILE} is a 'web' OAuth client; gdoc needs a **Desktop app** client "
            f"(loopback redirect). Create one and download it again.", 2)
    conf = blob.get("installed") or blob
    if not conf.get("client_id") or not conf.get("client_secret"):
        die(f"{CLIENT_FILE} has no client_id/client_secret. Re-download the Desktop OAuth "
            f"client JSON (see references/setup.md).", 2)
    return conf


def load_token(required=True):
    if not os.path.exists(TOKEN_FILE):
        if not required:
            return {}
        die("Not signed in (no ~/.config/gdoc/token.json). Run `gdoc auth login` yourself "
            "in a terminal — it opens a browser.", 2)
    try:
        with open(TOKEN_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        if not required:
            return {}
        die("~/.config/gdoc/token.json is unreadable or corrupt. Run `gdoc auth login`.", 2)


def save_token(tok):
    _write_secret(TOKEN_FILE, json.dumps(tok, indent=2) + "\n")


def _token_post(form):
    """POST to the OAuth token endpoint. Deliberately bypasses req()/GDOC_DRY_RUN:
    token exchange and refresh are never dry-run and never carry a bearer token."""
    data = urllib.parse.urlencode(form).encode()
    r = urllib.request.Request(TOKEN_URL, data=data, method="POST")
    r.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(r, timeout=timeout()) as resp:
            return json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:600]
        if "invalid_grant" in detail:
            die("Refresh token rejected (invalid_grant): revoked, expired, or the account "
                "password changed. Run `gdoc auth login` yourself in a terminal.", 2)
        die(f"OAuth token endpoint returned HTTP {e.code}: {detail}", 2)
    except urllib.error.URLError as e:
        die(f"Cannot reach {TOKEN_URL}: {e.reason}. Check the network/proxy.", 2)


def access_token():
    tok = load_token()
    if tok.get("access_token") and float(tok.get("expires_at", 0)) - 60 > time.time():
        return tok["access_token"]
    refresh = tok.get("refresh_token")
    if not refresh:
        die("No refresh token cached. Run `gdoc auth login` yourself in a terminal.", 2)
    conf = load_client()
    res = _token_post({
        "grant_type": "refresh_token",
        "refresh_token": refresh,
        "client_id": conf["client_id"],
        "client_secret": conf["client_secret"],
    })
    if not res.get("access_token"):
        die("Token refresh returned no access_token. Run `gdoc auth login`.", 2)
    tok["access_token"] = res["access_token"]
    tok["expires_at"] = time.time() + float(res.get("expires_in", 3600))
    if res.get("scope"):
        tok["scopes"] = res["scope"].split()
    save_token(tok)
    return tok["access_token"]


def req(method, url, body=None, *, raw=None, ctype="application/json",
        accept_bytes=False, _retried=False):
    """One HTTP call against a Google API. Non-GET is short-circuited by GDOC_DRY_RUN=1
    BEFORE any credential is touched, so dry runs work without ~/.config/gdoc."""
    if method != "GET" and dry_run():
        print(f"DRY-RUN {method} {url} "
              f"{json.dumps(body, ensure_ascii=False) if body is not None else ''}".rstrip(),
              file=sys.stderr)
        return {"id": "DRY-0", "dryRun": True}
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Authorization", f"Bearer {access_token()}")
    r.add_header("Accept", "*/*" if accept_bytes else "application/json")
    if data is not None:
        r.add_header("Content-Type", ctype)
    try:
        with urllib.request.urlopen(r, timeout=timeout()) as resp:
            payload = resp.read()
            if accept_bytes:
                return payload
            text = payload.decode("utf-8", "replace")
            return json.loads(text) if text.strip() else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:800]
        low = detail.lower()
        if e.code == 401:
            die(f"Auth failed (401): the token is invalid or revoked. Run `gdoc auth login` "
                f"yourself in a terminal. {detail}", 2)
        if e.code == 403:
            if any(k in low for k in ("insufficientpermissions", "access_token_scope_insufficient",
                                      "accessnotconfigured", "has not been used in project",
                                      "api has not been used")):
                die(f"403 scope/API problem on {method} {url}: re-login with more scopes "
                    f"(`gdoc auth login --scopes drive,gmail`) or enable the API in the GCP "
                    f"project (see references/setup.md). {detail}", 2)
            die(f"403 on {method} {url}: no access to this file, or it lives on a shared drive "
                f"you cannot write to. {detail}", 1)
        if e.code == 404:
            die(f"404 on {method} {url}: no such file/message, or you have no access to it "
                f"(shared-drive files need supportsAllDrives, which gdoc always sends). "
                f"{detail}", 1)
        if e.code in (429, 503) and method == "GET" and not _retried:
            time.sleep(2)
            return req(method, url, body, raw=raw, ctype=ctype,
                       accept_bytes=accept_bytes, _retried=True)
        die(f"HTTP {e.code} on {method} {url}: {detail}", 1)
    except urllib.error.URLError as e:
        die(f"Cannot reach {urllib.parse.urlsplit(url).netloc}: {e.reason}. "
            f"Check the network/proxy, then retry.", 2)


def drive_url(path, **params):
    """Drive v3 URL with supportsAllDrives=true always on."""
    params.setdefault("supportsAllDrives", "true")
    clean = {k: v for k, v in params.items() if v is not None}
    return f"{DRIVE}{path}?{urllib.parse.urlencode(clean)}"


def parse_flags(args, bools=(), valued=()):
    """Split argv into (positionals, flags). Flag keys lose the leading dashes and
    turn inner dashes into underscores: --match-case -> flags['match_case']."""
    def key(a):
        return a.lstrip("-").replace("-", "_")

    pos, flags, i = [], {}, 0
    while i < len(args):
        a = args[i]
        if a in bools:
            flags[key(a)] = True
            i += 1
        elif a in valued:
            if i + 1 >= len(args):
                die(f"{a} needs a value.")
            flags[key(a)] = args[i + 1]
            i += 2
        elif "=" in a and a.split("=", 1)[0] in valued:
            k, v = a.split("=", 1)
            flags[key(k)] = v
            i += 1
        elif a.startswith("--"):
            die(f"Unknown flag '{a}'. Run `gdoc` for usage.")
        else:
            pos.append(a)
            i += 1
    return pos, flags


def multipart_related(meta, media, media_type):
    """Drive multipart/related upload body -> (bytes, content-type)."""
    boundary = "----gdoc" + uuid.uuid4().hex
    body = b"".join([
        f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode(),
        json.dumps(meta).encode(),
        f"\r\n--{boundary}\r\nContent-Type: {media_type}\r\n\r\n".encode(),
        media if isinstance(media, bytes) else media.encode(),
        f"\r\n--{boundary}--\r\n".encode(),
    ])
    return body, f"multipart/related; boundary={boundary}"


def read_local(path):
    if not os.path.isfile(path):
        die(f"No such file: {path}")
    with open(path, "rb") as f:
        return f.read()


def rows_arg(value):
    """JSON rows, or @file holding JSON rows."""
    text = read_local(value[1:]).decode() if value.startswith("@") else value
    try:
        rows = json.loads(text)
    except ValueError as e:
        die(f"Rows must be JSON, e.g. '[[\"a\",\"b\"]]' (got: {e}).")
    if not isinstance(rows, list) or not all(isinstance(r, list) for r in rows):
        die("Rows must be a JSON array of arrays, e.g. '[[\"a\",\"b\"],[\"c\",\"d\"]]'.")
    return rows


# --------------------------------------------------------------- auth commands

def _scope_list(spec):
    out = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if part.startswith("https://"):
            out.append(part)
        elif part in SCOPE_ALIASES:
            out.extend(SCOPE_ALIASES[part])
        else:
            die(f"Unknown scope alias '{part}'. Known: {', '.join(sorted(SCOPE_ALIASES))} "
                f"(or a full https://www.googleapis.com/auth/... URL).")
    seen, uniq = set(), []
    for s in out:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq


def _pkce():
    verifier = secrets.token_urlsafe(64)
    import hashlib
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return verifier, challenge


def _loopback_code(port_holder, state):
    """Serve exactly one request on 127.0.0.1:<random port> and return ?code=."""
    from http.server import BaseHTTPRequestHandler, HTTPServer
    got = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            got.update({k: v[0] for k, v in q.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            ok = got.get("code") and got.get("state") == state
            self.wfile.write(b"gdoc: signed in - close this tab.\n" if ok
                             else b"gdoc: sign-in failed - check the terminal.\n")

        def log_message(self, *a):  # keep the console clean
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    server.timeout = 300
    port_holder.append(server.server_address[1])
    return server, got


def cmd_auth_login(args):
    _, flags = parse_flags(args, bools=("--no-browser",), valued=("--scopes", "--hint"))
    conf = load_client()
    scopes = _scope_list(flags["scopes"]) if flags.get("scopes") else list(DEFAULT_SCOPES)
    verifier, challenge = _pkce()
    state = secrets.token_urlsafe(16)

    server, got = None, {}
    if flags.get("no_browser"):
        redirect = "http://127.0.0.1:8765/"
    else:
        holder = []
        server, got = _loopback_code(holder, state)
        redirect = f"http://127.0.0.1:{holder[0]}/"

    params = {
        "client_id": conf["client_id"], "redirect_uri": redirect, "response_type": "code",
        "scope": " ".join(scopes), "access_type": "offline", "prompt": "consent",
        "state": state, "code_challenge": challenge, "code_challenge_method": "S256",
    }
    if workspace_domain():
        params["hd"] = workspace_domain()
    if flags.get("hint"):
        params["login_hint"] = flags["hint"]
    url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"
    print("Open this URL in your browser (it may not open by itself under WSL2):\n",
          file=sys.stderr)
    print(url, file=sys.stderr)
    print("", file=sys.stderr)
    try:
        import webbrowser
        webbrowser.open(url)
    except Exception:
        pass

    if server is None:
        print("After approving, the browser will fail to load http://127.0.0.1:8765/... — that "
              "is expected.", file=sys.stderr)
        pasted = input("Paste the full redirect URL (or just the code): ").strip()
        if "code=" in pasted:
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(pasted).query)
            code = (q.get("code") or [""])[0]
            if (q.get("state") or [state])[0] != state:
                die("OAuth state mismatch — start `gdoc auth login` again.")
        else:
            code = pasted
        if not code:
            die("No authorization code given.")
    else:
        try:
            server.handle_request()
        finally:
            server.server_close()
        if not got.get("code"):
            die(f"No authorization code received ({got.get('error', 'timeout after 300s')}). "
                f"Retry, or use `gdoc auth login --no-browser`.")
        if got.get("state") != state:
            die("OAuth state mismatch — start `gdoc auth login` again.")
        code = got["code"]

    res = _token_post({
        "grant_type": "authorization_code", "code": code, "redirect_uri": redirect,
        "client_id": conf["client_id"], "client_secret": conf["client_secret"],
        "code_verifier": verifier,
    })
    if not res.get("refresh_token"):
        die("Google returned no refresh_token. Revoke gdoc's access at "
            "https://myaccount.google.com/permissions and run `gdoc auth login` again "
            "(the flow already asks for prompt=consent&access_type=offline).")
    save_token({
        "client_id": conf["client_id"],          # never the client_secret
        "refresh_token": res["refresh_token"],
        "access_token": res.get("access_token"),
        "expires_at": time.time() + float(res.get("expires_in", 3600)),
        "scopes": (res.get("scope") or " ".join(scopes)).split(),
        "obtained_at": now_iso(),
    })
    print(f"OK: signed in; credentials cached in {TOKEN_FILE} (mode 0600).")
    cmd_whoami()


def cmd_auth_status():
    """Offline. Prints only whether the files exist, their modes, scopes and expiry."""
    missing = False
    for label, path in (("client_secret", CLIENT_FILE), ("token", TOKEN_FILE)):
        if os.path.exists(path):
            mode = oct(os.stat(path).st_mode & 0o777)[2:]
            warn = "  <-- should be 600" if mode != "600" else ""
            print(f"{label:<14} present  {path}  mode {mode}{warn}")
        else:
            print(f"{label:<14} MISSING  {path}")
            missing = True
    if os.path.isdir(CONF_DIR):
        dmode = oct(os.stat(CONF_DIR).st_mode & 0o777)[2:]
        print(f"{'config dir':<14} {CONF_DIR}  mode {dmode}"
              f"{'  <-- should be 700' if dmode != '700' else ''}")
    tok = load_token(required=False)
    if tok:
        exp = tok.get("expires_at")
        when = (datetime.fromtimestamp(float(exp), timezone.utc).isoformat()
                if exp else "unknown")
        fresh = "valid" if exp and float(exp) - 60 > time.time() else "expired (auto-refreshes)"
        print(f"{'refresh token':<14} {'present' if tok.get('refresh_token') else 'ABSENT'}")
        print(f"{'access token':<14} {fresh}, expires {when}")
        print(f"{'obtained':<14} {tok.get('obtained_at', 'unknown')}")
        print(f"{'scopes':<14} {' '.join(tok.get('scopes') or []) or '(unknown)'}")
    if missing:
        die("Not ready. See the gdoc skill's references/setup.md, then run `gdoc auth login`.", 2)


def cmd_whoami():
    about = req("GET", f"{DRIVE}/about?fields=user(emailAddress,displayName)")
    user = about.get("user", {})
    tok = load_token(required=False)
    exp = tok.get("expires_at")
    print(f"{user.get('emailAddress', '?')}  ({user.get('displayName', '?')})")
    print(f"scopes: {' '.join(tok.get('scopes') or []) or '(unknown)'}")
    if exp:
        print(f"access token expires: "
              f"{datetime.fromtimestamp(float(exp), timezone.utc).isoformat()}")


# --------------------------------------------------------------- read commands

FILE_FIELDS = ("files(id,name,mimeType,modifiedTime,owners(emailAddress),webViewLink),"
               "nextPageToken")


def _print_files(res):
    files = res.get("files", [])
    for f in files:
        kind = (f.get("mimeType") or "").replace("application/vnd.google-apps.", "g-")
        owner = ((f.get("owners") or [{}])[0]).get("emailAddress", "-")
        print(f"{f.get('id'):<46} | {kind:<28} | {(f.get('modifiedTime') or '')[:10]} | "
              f"{owner:<28} | {f.get('name')}")
    print(f"({len(files)} shown)")


def cmd_search(query, max_results="25"):
    q = query if DRIVE_OP_RE.search(query) else (
        "fullText contains '%s' and trashed=false"
        % query.replace("\\", "\\\\").replace("'", "\\'"))
    res = req("GET", drive_url("/files", q=q, pageSize=max_results,
                               orderBy="modifiedTime desc", fields=FILE_FIELDS,
                               includeItemsFromAllDrives="true", corpora="allDrives"))
    _print_files(res)


def cmd_list(args):
    pos, flags = parse_flags(args, valued=("--folder",))
    max_results = pos[0] if pos else "25"
    if flags.get("folder"):
        q = f"'{file_id(flags['folder'])}' in parents and trashed=false"
    else:
        q = "trashed=false"
    res = req("GET", drive_url("/files", q=q, pageSize=max_results,
                               orderBy="modifiedTime desc", fields=FILE_FIELDS,
                               includeItemsFromAllDrives="true", corpora="allDrives"))
    _print_files(res)


META_FIELDS = ("id,name,mimeType,properties,modifiedTime,owners(emailAddress,displayName),"
               "lastModifyingUser(emailAddress),webViewLink,parents,driveId,"
               "capabilities(canEdit,canComment)")


def _meta(fid):
    return req("GET", drive_url(f"/files/{fid}", fields=META_FIELDS))


def cmd_meta(ref):
    # Hook contract: top-level `id` plus `properties`. Keep this raw.
    print(json.dumps(_meta(file_id(ref)), indent=2, ensure_ascii=False))


def _tabs(doc):
    """Flatten the tab tree (childTabs included); pre-tabs responses get one pseudo-tab."""
    out = []

    def walk(tabs):
        for t in tabs or []:
            props = t.get("tabProperties", {})
            out.append((props.get("tabId", ""), props.get("title", ""),
                        (t.get("documentTab") or {}).get("body", {})))
            walk(t.get("childTabs"))

    walk(doc.get("tabs"))
    if not out:
        out.append(("", doc.get("title", ""), doc.get("body", {})))
    return out


def _para_text(el):
    return "".join((r.get("textRun") or {}).get("content", "")
                   for r in (el.get("paragraph") or {}).get("elements", []))


def cmd_get(args):
    pos, flags = parse_flags(args, bools=("--json",), valued=("--tab",))
    if not pos:
        die("get needs a document id or URL.")
    fid = file_id(pos[0])
    meta = _meta(fid)
    if meta.get("mimeType") != DOC_MIME:
        die(f"'{meta.get('name')}' is {meta.get('mimeType')}, not a Google Doc. "
            f"Use `gdoc sheet get {fid}` for a spreadsheet, or `gdoc export {fid}` "
            f"for anything else.")
    doc = req("GET", f"{DOCS}/documents/{fid}?includeTabsContent=true")
    if flags.get("json"):
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        return
    print(f"{doc.get('title')}   [{fid}]")
    print(meta.get("webViewLink", ""))
    for tab_id, title, body in _tabs(doc):
        if flags.get("tab") and tab_id != flags["tab"]:
            continue
        content = body.get("content", [])
        end = content[-1].get("endIndex", 0) if content else 0
        words = sum(len(_para_text(el).split()) for el in content)
        print(f"\n== tab {tab_id or '(single)'} \"{title}\"  words {words}  endIndex {end}")
        for el in content:
            style = ((el.get("paragraph") or {}).get("paragraphStyle") or {}).get(
                "namedStyleType", "")
            if style in HEADING_STYLES:
                text = _para_text(el).strip()
                if text:
                    print(f"{HEADING_STYLES[style]:<8} @{el.get('startIndex', 0)}-"
                          f"{el.get('endIndex', 0)}  \"{text}\"")
    if flags.get("tab"):
        return
    print("\n(headings only — `gdoc export <ID> --md` for the full text)")


EXPORT_MIMES = {"md": "text/markdown", "txt": "text/plain", "csv": "text/csv"}


def cmd_export(args):
    pos, flags = parse_flags(args, bools=("--md", "--txt", "--csv"))
    if not pos:
        die("export needs a file id or URL.")
    fid = file_id(pos[0])
    dest = pos[1] if len(pos) > 1 else None
    chosen = [k for k in EXPORT_MIMES if flags.get(k)]
    if len(chosen) > 1:
        die("Pick one of --md / --txt / --csv.")
    if chosen:
        mime = EXPORT_MIMES[chosen[0]]
    else:
        kind = _meta(fid).get("mimeType")
        if kind == DOC_MIME:
            mime = "text/markdown"
        elif kind == SHEET_MIME:
            mime = "text/csv"
        else:
            die(f"Cannot export {kind}: export only works for Google Docs and Sheets. "
                f"(Pass --md/--txt/--csv to force a format.)")
    data = req("GET", drive_url(f"/files/{fid}/export", mimeType=mime), accept_bytes=True)
    if dest:
        with open(dest, "wb") as f:
            f.write(data)
        print(f"OK: exported {len(data)} bytes ({mime}) to {dest}")
    else:
        sys.stdout.buffer.write(data)


def _comments(fid):
    fields = ("comments(id,resolved,author/displayName,content,"
              "quotedFileContent/value),nextPageToken")
    out, page = [], None
    while True:
        res = req("GET", drive_url(f"/files/{fid}/comments", fields=fields,
                                   pageSize="100", pageToken=page))
        out.extend(res.get("comments", []))
        page = res.get("nextPageToken")
        if not page:
            return out


def cmd_comments(ref):
    rows = _comments(file_id(ref))
    if not rows:
        print("(no comments)")
        return
    for c in rows:
        state = "resolved" if c.get("resolved") else "OPEN"
        author = (c.get("author") or {}).get("displayName", "?")
        print(f"{c.get('id'):<24} | {state:<8} | {author:<22} | "
              f"{(c.get('content') or '').strip()}")
        quoted = (c.get("quotedFileContent") or {}).get("value")
        if quoted:
            print(f"{'':>24}   > {quoted.strip()[:200]}")
    print(f"({len(rows)} comments, {sum(1 for c in rows if not c.get('resolved'))} open)")


def cmd_sheet_get(ref, rng=None):
    fid = file_id(ref)
    if not rng:
        res = req("GET", f"{SHEETS}/spreadsheets/{fid}"
                         "?fields=properties.title,sheets.properties"
                         "(sheetId,title,gridProperties)")
        print(f"{(res.get('properties') or {}).get('title', '')}   [{fid}]")
        for sh in res.get("sheets", []):
            p = sh.get("properties", {})
            g = p.get("gridProperties", {})
            print(f"{p.get('sheetId'):<14} | {p.get('title'):<32} | "
                  f"{g.get('rowCount', '?')} rows x {g.get('columnCount', '?')} cols")
        return
    res = req("GET", f"{SHEETS}/spreadsheets/{fid}/values/"
                     f"{urllib.parse.quote(rng, safe='')}")
    for row in res.get("values", []):
        print("\t".join(str(c) for c in row))


def cmd_mail_search(query, max_results="20"):
    res = req("GET", f"{GMAIL}/users/me/messages?"
                     f"{urllib.parse.urlencode({'q': query, 'maxResults': max_results})}")
    msgs = res.get("messages", [])
    for m in msgs:
        full = req("GET", f"{GMAIL}/users/me/messages/{m['id']}?format=metadata"
                          "&metadataHeaders=From&metadataHeaders=Subject&metadataHeaders=Date")
        h = {x["name"].lower(): x["value"] for x in (full.get("payload") or {}).get("headers", [])}
        print(f"{m['id']:<18} | {m.get('threadId', ''):<18} | {h.get('date', '')[:25]:<25} | "
              f"{h.get('from', '')[:34]:<34} | {h.get('subject', '')}")
    print(f"({len(msgs)} shown)")


class _Untag(HTMLParser):
    BREAKS = {"p", "br", "div", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self):
        super().__init__()
        self.out, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag in self.BREAKS:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)

    def text(self):
        return re.sub(r"\n{3,}", "\n\n", "".join(self.out)).strip()


def _b64(data):
    return base64.urlsafe_b64decode(data + "==").decode("utf-8", "replace")


def _walk_parts(part, plain, html, atts):
    mime = part.get("mimeType", "")
    body = part.get("body", {})
    if part.get("filename"):
        atts.append((part["filename"], body.get("size", 0)))
    elif mime == "text/plain" and body.get("data"):
        plain.append(_b64(body["data"]))
    elif mime == "text/html" and body.get("data"):
        html.append(_b64(body["data"]))
    for sub in part.get("parts", []):
        _walk_parts(sub, plain, html, atts)


def cmd_mail_get(msgid):
    msg = req("GET", f"{GMAIL}/users/me/messages/{msgid}?format=full")
    payload = msg.get("payload", {})
    headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
    for name in ("date", "from", "to", "cc", "subject", "message-id"):
        if headers.get(name):
            print(f"{name.title():<12} {headers[name]}")
    print(f"{'Thread':<12} {msg.get('threadId')}")
    plain, html, atts = [], [], []
    _walk_parts(payload, plain, html, atts)
    print()
    if plain:
        print("\n".join(plain).strip())
    elif html:
        p = _Untag()
        p.feed("\n".join(html))
        print(p.text())
    else:
        print(msg.get("snippet", "(no body)"))
    for name, size in atts:
        print(f"\n[attachment] {name}  ({size} bytes)")


def cmd_api(url):
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or parts.netloc not in API_HOSTS:
        die(f"api: only https URLs on {', '.join(sorted(API_HOSTS))} are allowed "
            f"(got '{url}'). GET only — there is no write escape hatch on purpose.")
    print(json.dumps(req("GET", url), indent=2, ensure_ascii=False))


# -------------------------------------------------------------- write commands

def cmd_create(args):
    pos, flags = parse_flags(args, bools=("--plain",), valued=("--from", "--folder"))
    if not pos:
        die('create needs a TITLE, e.g. gdoc create "Design notes" --from notes.md')
    if not flags.get("from"):
        die("create needs --from FILE.md (the document body).")
    title = " ".join(pos)
    media = read_local(flags["from"])
    meta = {
        "name": title,
        "mimeType": DOC_MIME,
        "properties": {
            "agent_provenance": "agent-created",
            "agent_tool": "claude-code",
            "agent_created_at": now_iso(),
        },
    }
    if flags.get("folder"):
        meta["parents"] = [file_id(flags["folder"])]
    ctype = "text/plain; charset=UTF-8" if flags.get("plain") else "text/markdown; charset=UTF-8"
    body, boundary_ctype = multipart_related(meta, media, ctype)
    url = (f"{UPLOAD}/files?uploadType=multipart&supportsAllDrives=true"
           f"&fields=id,name,webViewLink,properties")
    res = req("POST", url, meta, raw=body, ctype=boundary_ctype)
    if res.get("dryRun"):
        return
    print(f"OK: created {res.get('id')}  \"{res.get('name')}\"")
    print(res.get("webViewLink", ""))
    cmd_meta(res["id"])


def cmd_import(args):
    pos, flags = parse_flags(args, bools=("--force",))
    if len(pos) < 2:
        die("import needs <ID|URL> FILE.md")
    fid = file_id(pos[0])
    media = read_local(pos[1])
    meta = _meta(fid)
    if meta.get("mimeType") != DOC_MIME:
        die(f"'{meta.get('name')}' is {meta.get('mimeType')}, not a Google Doc — "
            f"import replaces a Doc's whole body.")
    if not flags.get("force"):
        open_comments = [c for c in _comments(fid) if not c.get("resolved")]
        if open_comments:
            die(f"{len(open_comments)} unresolved comment(s) on '{meta.get('name')}'. A whole-doc "
                f"import drops every comment and suggestion. Resolve them, use `append`/"
                f"`replace` for a surgical edit, or re-run with --force.")
    url = (f"{UPLOAD}/files/{fid}?uploadType=multipart&supportsAllDrives=true"
           f"&fields=id,name,modifiedTime")
    payload = {"mimeType": DOC_MIME}
    body, ctype = multipart_related(payload, media, "text/markdown; charset=UTF-8")
    res = req("PATCH", url, payload, raw=body, ctype=ctype)
    if res.get("dryRun"):
        return
    print(f"OK: replaced the body of {res.get('id')} \"{res.get('name')}\" "
          f"({res.get('modifiedTime')})")
    print(meta.get("webViewLink", ""))


def cmd_append(args):
    pos, flags = parse_flags(args, valued=("--from", "--heading", "--tab"))
    if not pos:
        die("append needs <ID|URL> and TEXT (or --from FILE).")
    fid = file_id(pos[0])
    if flags.get("from"):
        text = read_local(flags["from"]).decode()
    elif len(pos) > 1:
        text = " ".join(pos[1:])
    else:
        die("append needs TEXT or --from FILE.")
    text = text.rstrip("\n")
    heading = flags.get("heading")

    doc = req("GET", f"{DOCS}/documents/{fid}?includeTabsContent=true")
    tabs = _tabs(doc)
    if flags.get("tab"):
        tabs = [t for t in tabs if t[0] == flags["tab"]]
        if not tabs:
            die(f"No tab '{flags['tab']}' in this document. Run `gdoc get {fid}` for the tab ids.")
    tab_id, _, body = tabs[0]
    content = body.get("content", [])
    if not content:
        die("Document body is empty in the API response — cannot find the insertion point.")
    at = content[-1]["endIndex"] - 1  # before the body's final newline

    payload = "\n" + (heading + "\n" if heading else "") + text
    loc = {"index": at}
    if tab_id:
        loc["tabId"] = tab_id
    requests = [{"insertText": {"location": loc, "text": payload}}]

    def style_range(start, end, named):
        rng = {"startIndex": start, "endIndex": end}
        if tab_id:
            rng["tabId"] = tab_id
        return {"updateParagraphStyle": {"range": rng,
                                         "paragraphStyle": {"namedStyleType": named},
                                         "fields": "namedStyleType"}}

    cursor = at + 1  # past the leading newline
    if heading:
        h_end = cursor + utf16len(heading) + 1
        requests.append(style_range(cursor, h_end, "HEADING_2"))
        cursor = h_end
    if text:
        requests.append(style_range(cursor, cursor + utf16len(text), "NORMAL_TEXT"))

    req("POST", f"{DOCS}/documents/{fid}:batchUpdate", {"requests": requests})
    print(f"OK: appended {len(payload)} chars to tab {tab_id or '(single)'} of {fid}")


def cmd_replace(args):
    pos, flags = parse_flags(args, bools=("--match-case",), valued=("--tab",))
    if len(pos) < 3:
        die("replace needs <ID|URL> <FIND> <REPL>.")
    fid = file_id(pos[0])
    rep = {"containsText": {"text": pos[1], "matchCase": bool(flags.get("match_case"))},
           "replaceText": pos[2]}
    if flags.get("tab"):
        rep["tabsCriteria"] = {"tabIds": [flags["tab"]]}
    res = req("POST", f"{DOCS}/documents/{fid}:batchUpdate",
              {"requests": [{"replaceAllText": rep}]})
    if res.get("dryRun"):
        return
    changed = sum((r.get("replaceAllText") or {}).get("occurrencesChanged", 0)
                  for r in res.get("replies", []))
    print(f"OK: occurrencesChanged: {changed}")


def cmd_mark(ref, value):
    fid = file_id(ref)
    if value not in ("agent-created", "agent-worked", "none"):
        die("mark needs agent-created, agent-worked or none.")
    if value == "none":
        props = {k: None for k in PROV_KEYS}
    else:
        props = {"agent_provenance": value, "agent_tool": "claude-code",
                 "agent_marked_at": now_iso()}
    res = req("PATCH", drive_url(f"/files/{fid}", fields="id,properties"),
              {"properties": props})
    if res.get("dryRun"):
        return
    print(f"OK: {fid} provenance -> {value}")
    cmd_meta(fid)


def cmd_sheet_append(ref, rng, rows):
    fid = file_id(ref)
    url = (f"{SHEETS}/spreadsheets/{fid}/values/{urllib.parse.quote(rng, safe='')}:append"
           f"?valueInputOption=USER_ENTERED&insertDataOption=INSERT_ROWS")
    res = req("POST", url, {"values": rows_arg(rows)})
    if res.get("dryRun"):
        return
    print(f"OK: appended to {(res.get('updates') or {}).get('updatedRange')} "
          f"({(res.get('updates') or {}).get('updatedCells')} cells)")


def cmd_sheet_update(ref, rng, rows):
    fid = file_id(ref)
    url = (f"{SHEETS}/spreadsheets/{fid}/values/{urllib.parse.quote(rng, safe='')}"
           f"?valueInputOption=USER_ENTERED")
    res = req("PUT", url, {"range": rng, "majorDimension": "ROWS", "values": rows_arg(rows)})
    if res.get("dryRun"):
        return
    print(f"OK: updated {res.get('updatedRange')} ({res.get('updatedCells')} cells)")


def cmd_mail_draft(args):
    _, flags = parse_flags(args, valued=("--to", "--cc", "--subject", "--body",
                                         "--body-file", "--reply-to"))
    if flags.get("body") and flags.get("body_file"):
        die("Pass either --body or --body-file, not both.")
    if not flags.get("body") and not flags.get("body_file"):
        die("mail draft needs --body TEXT or --body-file FILE.")
    text = flags["body"] if flags.get("body") else read_local(flags["body_file"]).decode()
    if not flags.get("to") and not flags.get("reply_to"):
        die("mail draft needs --to ADDRESS (or --reply-to MSGID, which supplies the recipient).")

    # No pre-GET unless --reply-to is used, so a plain dry run needs no credentials.
    thread_id, headers = None, {}
    if flags.get("reply_to"):
        src = req("GET", f"{GMAIL}/users/me/messages/{flags['reply_to']}?format=metadata"
                         "&metadataHeaders=Message-ID&metadataHeaders=From"
                         "&metadataHeaders=Reply-To&metadataHeaders=Subject"
                         "&metadataHeaders=References")
        headers = {h["name"].lower(): h["value"]
                   for h in (src.get("payload") or {}).get("headers", [])}
        thread_id = src.get("threadId")

    to = flags.get("to") or headers.get("reply-to") or headers.get("from")
    if not to:
        die("mail draft needs --to (the --reply-to message has no Reply-To/From header).")

    msg = EmailMessage()
    msg["To"] = to
    if flags.get("cc"):
        msg["Cc"] = flags["cc"]
    subject = flags.get("subject")
    if not subject:
        base = headers.get("subject", "")
        if not base:
            die("mail draft needs --subject.")
        subject = base if base.lower().startswith("re:") else f"Re: {base}"
    msg["Subject"] = subject
    if headers.get("message-id"):
        msg["In-Reply-To"] = headers["message-id"]
        msg["References"] = (headers.get("references", "") + " " +
                             headers["message-id"]).strip()
    msg.set_content(text)

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    message = {"raw": raw}
    if thread_id:
        message["threadId"] = thread_id
    res = req("POST", f"{GMAIL}/users/me/drafts", {"message": message})
    if res.get("dryRun"):
        return
    inner = res.get("message") or {}
    print(f"OK: draft {res.get('id')} to {to} (thread {inner.get('threadId')}) — nothing is "
          f"sent; it is waiting in Gmail for you to review and send.")


# ------------------------------------------------------------------- dispatch

# name -> (fn, min positional args, max positional args; -1 = variadic list)
TABLE = {
    "whoami": (cmd_whoami, 0, 0),
    "auth login": (cmd_auth_login, 0, -1),
    "auth status": (cmd_auth_status, 0, 0),
    "search": (cmd_search, 1, 2),
    "list": (cmd_list, 0, -1),
    "meta": (cmd_meta, 1, 1),
    "get": (cmd_get, 1, -1),
    "export": (cmd_export, 1, -1),
    "comments": (cmd_comments, 1, 1),
    "sheet get": (cmd_sheet_get, 1, 2),
    "mail search": (cmd_mail_search, 1, 2),
    "mail get": (cmd_mail_get, 1, 1),
    "api": (cmd_api, 1, 1),
    "create": (cmd_create, 1, -1),
    "import": (cmd_import, 2, -1),
    "append": (cmd_append, 1, -1),
    "replace": (cmd_replace, 3, -1),
    "mark": (cmd_mark, 2, 2),
    "sheet append": (cmd_sheet_append, 3, 3),
    "sheet update": (cmd_sheet_update, 3, 3),
    "mail draft": (cmd_mail_draft, 0, -1),
}
TWO_WORD = ("auth", "sheet", "mail")


def main():
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        sys.exit(1)
    cmd, args = argv[0], argv[1:]
    if cmd in TWO_WORD:
        if not args:
            die(f"'{cmd}' needs a sub-command "
                f"({', '.join(k.split()[1] for k in TABLE if k.startswith(cmd + ' '))}).")
        cmd, args = f"{cmd} {args[0]}", args[1:]
    if cmd not in TABLE:
        die(f"Unknown command '{cmd}'.\n{__doc__}")
    fn, mn, mx = TABLE[cmd]
    positional = [a for a in args if not a.startswith("--")]
    if len(positional) < mn:
        die(f"'{cmd}' needs at least {mn} argument(s). See the header for usage.")
    if mx == -1:
        fn(args)
    elif len(args) > mx:
        die(f"'{cmd}' takes at most {mx} argument(s), got {len(args)}.")
    else:
        fn(*args)


if __name__ == "__main__":
    main()
