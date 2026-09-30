#!/usr/bin/env python3
"""Thin Jira Server (8.x) REST v2 client — user-level generic edition.

Canonical invocation: `jira <cmd>` (symlinked into ~/.local/bin). A repo-level Jira
workflow skill with its own copy of a client stays authoritative in that repo.

Auth: Personal Access Token read from ~/.config/jira (plain token, one line),
or $JIRA_TOKEN. Sent as `Authorization: Bearer <token>`.
Base URL: $JIRA_URL, else `jira.url` from the harness config (build/config.json, see
HARNESS_CONFIG_JSON / HARNESS_HOME). There is no default: without one, every command that
talks to Jira exits 2 with a "not configured" message (running with no args still prints
this help).

TLS: verified by default. If the server certificate ever lapses, set JIRA_INSECURE=1 to
skip verification (mirrors `curl -k`).

Friendly field names (for `set`, `create --field`, and the extra keys `get` prints) come
from `jira.fields` in the harness config: `[jira.fields.PROJ] story_points = "customfield_…"`
(per project) or a top-level `[jira.fields] name = "customfield_…"` (all projects).
Names listed in `jira.get_exclude` (or $HARNESS_JIRA_GET_EXCLUDE, comma-separated) stay
write-only: they resolve for `set`/`create` but `get` does not surface them.
$HARNESS_JIRA_FIELDS_JSON (same shape, JSON) overrides the config. Nothing is built in:
discover ids at runtime with `fields <PROJECT>` and pass raw customfield_* ids.

Exit codes: 0 ok, 2 auth/connection problem (fall back to browser), 1 other error.

Commands (run with no args to print this list):
  whoami                    Verify the token works; prints the account name.
  get <KEY>                 Print the important fields of an issue as JSON.
  search <JQL> [max]        Run a JQL query; prints key | status | assignee | summary
                            (default max 25). e.g.:
                              search 'assignee=currentUser() AND resolution IS EMPTY'
  fields <KEY|PROJECT>      List editable custom field id -> name, so you can find
                            the exact id for Testing Solution / Epic Link etc.
  attachments <KEY>         List attachments (filename, type, size, id, url).
  download <KEY> <DIR>      Download all attachments of an issue into DIR.
  upload <KEY> <FILE>       Attach a local FILE to an issue.
  comment <KEY> <TEXT>      Add a comment (plain text — Jira Server has no ADF).
  label <KEY> add|remove <LABEL>
                            Add or remove ONE label atomically (Jira `update` verb —
                            never clobbers existing labels, unlike `set KEY labels`).
  links <KEY>               List issue links: id | type | direction phrase | other key | status | summary.
  link <FROM> <TYPE> <TO>   Create a native issue link (TYPE matched case-insensitively against
                            the server's link types, e.g. "Issue split", Relates, Blocks).
                            FROM is the inward issue, TO the outward one — for "Issue split":
                            FROM "split to" TO. Governed: the guard hook only permits links
                            between agent-worked tickets.
  api <path>                GET-only escape hatch; prints raw JSON. Path must start with /rest/.
  versions <PROJECT>        List the project's versions (for Affects Version).
  sprints <PROJECT>         List active+future sprints (id + name) for the project board.
                            Set one via: set <KEY> Sprint <sprintId>
  transitions <KEY>         List available status transitions (id + name).
  transition <KEY> <NAME>   Move the issue to a status by (case-insensitive) name.
  set <KEY> <field> <json-value>
                            Set one field. <field> is a field id OR a friendly name
                            configured in jira.fields (e.g. "Story Points", "Epic
                            Link"). Value is parsed as JSON,
                            falling back to a raw string. Examples:
                              set PROJ-123 versions '[{"name":"1.2.3"}]'
                              set PROJ-123 "Story Points" 3
  create <PROJECT> <TYPE> <SUMMARY> [--description TEXT] [--field name=json ...]
                            Create an issue with only the fields you pass.
                            Discover required fields first with `fields <PROJECT>`.
                            --field key is an id or friendly name; value parsed as
                            JSON, else raw string. e.g.:
                              create PROJ Task "Title" \
                                --field "Story Points"=3 \
                                --description "..."
                            Sprint/Affects/assignee: set afterward with `set`, or pass
                            --field assignee='{"name":"user"}' etc. at creation.
                            --link "TYPE:KEY" (repeatable) adds a native link in the SAME
                            request (new issue = outward side; e.g. --link "Issue split:PROJ-1"
                            makes PROJ-1 "split to" the new issue).

Env: JIRA_URL, JIRA_TOKEN, JIRA_INSECURE=1, JIRA_DRY_RUN=1 (print every non-GET request's
method, path and JSON body to stderr instead of sending it; returns a stub result),
HARNESS_JIRA_FIELDS_JSON, HARNESS_CONFIG_JSON / HARNESS_HOME (harness config location).

This script only READS and WRITES the fields/transitions you explicitly ask for.
It never transitions or edits on its own.
"""
import json
import os
import re
import ssl
import sys
import uuid
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


TOKEN_FILE = os.path.expanduser("~/.config/jira")
_BASE = None


def base_url():
    """Jira base URL: $JIRA_URL, else jira.url from the harness config; exit 2 when unset."""
    global _BASE
    if _BASE is None:
        u = (os.environ.get("JIRA_URL") or cfg("jira.url") or "").strip().rstrip("/")
        if not u:
            die("Jira is not configured: set jira.url in local/harness.toml "
                "(harness config set jira.url https://jira.example.com) or export JIRA_URL.", code=2)
        _BASE = u
    return _BASE


def die(msg, code=1):
    print(msg, file=sys.stderr)
    sys.exit(code)


def get_token():
    tok = os.environ.get("JIRA_TOKEN")
    if tok:
        return tok.strip()
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE) as f:
            tok = f.read().strip()
            if tok:
                return tok
    die(
        "No Jira token. Create a Personal Access Token at "
        f"{base_url()}/secure/ViewProfile.jspa -> Personal Access Tokens, then save it "
        f"(plain, one line) to {TOKEN_FILE}. Without it, fall back to the browser.",
        code=2,
    )


def _ctx():
    """Verified TLS by default; JIRA_INSECURE=1 mirrors `curl -k` for cert lapses."""
    ctx = ssl.create_default_context()
    if os.environ.get("JIRA_INSECURE") == "1":
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def req(method, path, body=None):
    url = path if path.startswith("http") else f"{base_url()}{path}"
    if method != "GET" and os.environ.get("JIRA_DRY_RUN") == "1":
        print(f"DRY-RUN {method} {path} {json.dumps(body) if body is not None else ''}", file=sys.stderr)
        return {"key": "DRY-0", "id": "0", "dryRun": True}
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Authorization", f"Bearer {get_token()}")
    r.add_header("Content-Type", "application/json")
    r.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(r, context=_ctx(), timeout=30) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:800]
        if e.code == 401:
            die(f"Auth failed (401). Token invalid/expired. {detail}", code=2)
        if e.code == 403:
            die(f"Permission denied (403) on {method} {path}. If `jira whoami` succeeds, the "
                f"token is valid but lacks browse/edit permission for this project/issue. {detail}", code=2)
        die(f"HTTP {e.code} on {method} {path}: {detail}", code=1)
    except urllib.error.URLError as e:
        die(f"Cannot reach {base_url()}: {e}. Fall back to the browser.", code=2)


def cmd_whoami():
    me = req("GET", "/rest/api/2/myself")
    print(json.dumps({"name": me.get("name"), "displayName": me.get("displayName"),
                      "email": me.get("emailAddress")}, indent=2))


# Friendly field names come from the harness config (jira.fields); nothing is built in.
# Each row: friendly name -> id, plus the camelCase key `get` shows it under (None = don't
# surface in `get`). The same rows feed the write path (resolve_field, for set/create) and
# the read path (cmd_get). Project tables (upper-case keys) apply to that project only;
# lower-case keys at the top level of jira.fields apply to every project.
_PROJECT_KEY = re.compile(r"^[A-Z][A-Z0-9_]*$")


def _fields_config():
    raw = os.environ.get("HARNESS_JIRA_FIELDS_JSON")
    if raw:
        try:
            val = json.loads(raw)
        except ValueError:
            die("HARNESS_JIRA_FIELDS_JSON is not valid JSON.")
    else:
        val = cfg("jira.fields", {})
    return val if isinstance(val, dict) else {}


def _camel(name):
    parts = [w for w in re.split(r"[\s_]+", name.strip()) if w]
    return (parts[0].lower() + "".join(w[:1].upper() + w[1:].lower() for w in parts[1:])) if parts else name


def _norm_name(name):
    return re.sub(r"[\s_]+", " ", str(name).strip()).lower()


def _get_exclude():
    raw = os.environ.get("HARNESS_JIRA_GET_EXCLUDE")
    val = raw.split(",") if raw is not None else cfg("jira.get_exclude", [])
    return {_norm_name(n) for n in (val if isinstance(val, list) else []) if str(n).strip()}


def field_rows(project=None):
    """[(friendly name, id, get key or None)] for PROJECT (all projects when None)."""
    conf, rows, excl = _fields_config(), {}, _get_exclude()

    def add(name, spec):
        if not isinstance(spec, str):
            return
        fid = spec
        gk = None if _norm_name(name) in excl else _camel(name)
        friendly = name.replace("_", " ")
        rows[friendly.lower()] = (friendly, fid, gk)

    for k, v in conf.items():
        if not _PROJECT_KEY.match(k):
            add(k, v)
    for k, v in conf.items():
        if _PROJECT_KEY.match(k) and isinstance(v, dict) and (project is None or k == project):
            for name, spec in v.items():
                add(name, spec)
    return list(rows.values())


def get_extra(project):
    """id -> get key, for the configured fields `get` should surface beyond the built-ins."""
    return {fid: gk for _, fid, gk in field_rows(project) if gk}


def cmd_get(key):
    builtins = ("summary,issuetype,status,priority,description,assignee,reporter,"
                "components,versions,fixVersions,labels,parent,project,issuelinks")
    extra = get_extra(key.split("-", 1)[0])
    issue = req("GET", f"/rest/api/2/issue/{key}?fields={builtins}" + "".join("," + f for f in extra))
    fl = issue.get("fields", {})
    out = {
        "key": issue.get("key"),
        "summary": fl.get("summary"),
        "type": (fl.get("issuetype") or {}).get("name"),
        "status": (fl.get("status") or {}).get("name"),
        "priority": (fl.get("priority") or {}).get("name"),
        "project": (fl.get("project") or {}).get("key"),
        "assignee": (fl.get("assignee") or {}).get("displayName"),
        "reporter": (fl.get("reporter") or {}).get("displayName"),
        "parent": (fl.get("parent") or {}).get("key"),
        "components": [c.get("name") for c in fl.get("components") or []],
        "affectsVersions": [v.get("name") for v in fl.get("versions") or []],
        "fixVersions": [v.get("name") for v in fl.get("fixVersions") or []],
        "labels": fl.get("labels"),
        "description": fl.get("description"),
        "url": f"{base_url()}/browse/{issue.get('key')}",
    }
    # Surface the extra fields under readable keys, skipping blanks and the literal "0"
    # placeholder some templates pre-fill. Sprint on Jira Server arrives as opaque
    # "...Sprint@xxx[id=2049,...,name=Sprint 32,...]" strings -> parse id + name.
    for fid, out_key in extra.items():
        val = fl.get(fid)
        if val is None:
            continue
        if out_key == "sprint":
            sprints = []
            for item in (val if isinstance(val, list) else [val]):
                text = item if isinstance(item, str) else json.dumps(item)
                m_id = re.search(r"\bid=(\d+)", text)
                m_name = re.search(r"\bname=([^,\]]+)", text)
                if isinstance(item, dict):
                    sprints.append({"id": item.get("id"), "name": item.get("name")})
                elif m_id or m_name:
                    sprints.append({"id": int(m_id.group(1)) if m_id else None,
                                    "name": m_name.group(1) if m_name else None})
            if sprints:
                out[out_key] = sprints[-1] if len(sprints) == 1 else sprints
        elif isinstance(val, str):
            if val.strip() and val.strip() != "0":
                out[out_key] = val
        else:
            out[out_key] = val
    out["links"] = _link_rows(fl.get("issuelinks") or [])
    print(json.dumps(out, indent=2, ensure_ascii=False))


def _link_rows(issuelinks):
    rows = []
    for l in issuelinks:
        t = l.get("type", {})
        if "outwardIssue" in l:
            other, phrase = l["outwardIssue"], t.get("outward")
        else:
            other, phrase = l.get("inwardIssue", {}), t.get("inward")
        rows.append({
            "id": l.get("id"), "type": t.get("name"), "direction": phrase,
            "key": other.get("key"),
            "status": ((other.get("fields") or {}).get("status") or {}).get("name"),
            "summary": (other.get("fields") or {}).get("summary"),
        })
    return rows


def cmd_links(key):
    issue = req("GET", f"/rest/api/2/issue/{key}?fields=issuelinks")
    rows = _link_rows(issue.get("fields", {}).get("issuelinks") or [])
    if not rows:
        print("(no links)")
        return
    for r in rows:
        print(f"{r['id']:<8} | {r['type']:<14} | {r['direction']:<14} | {r['key']:<12} | "
              f"{(r['status'] or ''):<18} | {r['summary'] or ''}")


def _resolve_link_type(name):
    types = req("GET", "/rest/api/2/issueLinkType").get("issueLinkTypes", [])
    for t in types:
        if t.get("name", "").lower() == name.lower():
            return t["name"]
    avail = ", ".join(sorted(t.get("name", "") for t in types))
    die(f"Unknown link type '{name}'. Available: {avail}")


def cmd_link(src, ltype, dst):
    if src.upper() == dst.upper():
        die("link needs two different issues.")
    name = _resolve_link_type(ltype)
    req("POST", "/rest/api/2/issueLink",
        {"type": {"name": name}, "inwardIssue": {"key": src}, "outwardIssue": {"key": dst}})
    print(f"OK: linked {src} -[{name}]-> {dst}")
    cmd_links(dst)


def cmd_api(path):
    if not path.startswith("/rest/"):
        die("api path must start with /rest/ (GET only).")
    print(json.dumps(req("GET", path), indent=2, ensure_ascii=False))


def cmd_search(jql, max_results="25"):
    params = urllib.parse.urlencode({
        "jql": jql, "maxResults": max_results,
        "fields": "key,status,summary,assignee,issuetype",
    })
    res = req("GET", f"/rest/api/2/search?{params}")
    issues = res.get("issues", [])
    total = res.get("total", len(issues))
    for it in issues:
        fl = it.get("fields", {})
        status = (fl.get("status") or {}).get("name", "")
        assignee = (fl.get("assignee") or {}).get("displayName") or "-"
        print(f"{it['key']:<12} | {status:<18} | {assignee:<20} | {fl.get('summary', '')}")
    print(f"({len(issues)} of {total} shown)")


def cmd_fields(target):
    """Discover field ids via editmeta (issue key) or createmeta (project key)."""
    if "-" in target:  # looks like an issue key, e.g. PROJ-123
        meta = req("GET", f"/rest/api/2/issue/{target}/editmeta")
        fields = meta.get("fields", {})
    else:  # project key, e.g. PROJ
        meta = req(
            "GET",
            f"/rest/api/2/issue/createmeta?projectKeys={target}"
            "&expand=projects.issuetypes.fields",
        )
        fields = {}
        for p in meta.get("projects", []):
            for it in p.get("issuetypes", []):
                fields.update(it.get("fields", {}))
    rows = sorted(((fid, f.get("name", "")) for fid, f in fields.items()),
                  key=lambda x: x[1].lower())
    for fid, name in rows:
        print(f"{fid:<22} | {name}")


def cmd_attachments(key):
    issue = req("GET", f"/rest/api/2/issue/{key}?fields=attachment")
    atts = issue.get("fields", {}).get("attachment") or []
    if not atts:
        print("(no attachments)")
        return
    for a in atts:
        kb = round(a.get("size", 0) / 1024)
        print(f"{a['id']:<8} | {a['filename']}  | {a.get('mimeType')}  | {kb} KB")
        print(f"         {a['content']}")


def cmd_download(key, dest_dir):
    import os.path
    os.makedirs(dest_dir, exist_ok=True)
    issue = req("GET", f"/rest/api/2/issue/{key}?fields=attachment")
    atts = issue.get("fields", {}).get("attachment") or []
    if not atts:
        print("(no attachments)")
        return
    for a in atts:
        r = urllib.request.Request(a["content"])
        r.add_header("Authorization", f"Bearer {get_token()}")
        out = os.path.join(dest_dir, a["filename"])
        with urllib.request.urlopen(r, context=_ctx(), timeout=120) as resp, open(out, "wb") as f:
            f.write(resp.read())
        print(f"saved {out}")


def cmd_upload(key, path):
    import mimetypes
    if not os.path.isfile(path):
        die(f"No such file: {path}")
    fname = os.path.basename(path)
    with open(path, "rb") as f:
        content = f.read()
    mime = mimetypes.guess_type(fname)[0] or "application/octet-stream"

    # Build a minimal multipart/form-data body (stdlib has no helper). The field
    # name MUST be "file" for the Jira attachment endpoint.
    boundary = "----jirapyboundary" + uuid.uuid4().hex
    pre = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{fname}"\r\n'
        f"Content-Type: {mime}\r\n\r\n"
    ).encode()
    post = f"\r\n--{boundary}--\r\n".encode()
    data = pre + content + post

    url = f"{base_url()}/rest/api/2/issue/{key}/attachments"
    r = urllib.request.Request(url, data=data, method="POST")
    r.add_header("Authorization", f"Bearer {get_token()}")
    r.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    # Jira blocks attachment uploads without this XSRF opt-out header.
    r.add_header("X-Atlassian-Token", "no-check")
    try:
        with urllib.request.urlopen(r, context=_ctx(), timeout=120) as resp:
            res = json.loads(resp.read().decode() or "[]")
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:800]
        if e.code in (401, 403):
            die(f"Auth/XSRF failed ({e.code}). {detail}", code=2)
        die(f"HTTP {e.code} uploading to {key}: {detail}", code=1)
    except urllib.error.URLError as e:
        die(f"Cannot reach {base_url()}: {e}. Fall back to the browser.", code=2)
    for a in (res or []):
        print(f"OK: attached {a.get('filename')} to {key} (id {a.get('id')})")


def cmd_comment(key, text):
    res = req("POST", f"/rest/api/2/issue/{key}/comment", {"body": text})
    print(f"OK: comment {res.get('id')} added to {key}")


def cmd_label(key, op, label):
    if op not in ("add", "remove"):
        die("label needs add|remove.")
    req("PUT", f"/rest/api/2/issue/{key}", {"update": {"labels": [{op: label}]}})
    print(f"OK: {op} label '{label}' on {key}")


def cmd_versions(project):
    vs = req("GET", f"/rest/api/2/project/{project}/versions")
    for v in vs:
        flag = " (released)" if v.get("released") else ""
        archived = " [archived]" if v.get("archived") else ""
        print(f"{v.get('name')}{flag}{archived}")


def cmd_sprints(project):
    boards = req("GET", f"/rest/agile/1.0/board?projectKeyOrId={project}")
    vals = boards.get("values", [])
    if not vals:
        die(f"No agile board for project {project}.")
    for b in vals:
        s = req("GET", f"/rest/agile/1.0/board/{b['id']}/sprint?state=active,future")
        for sp in s.get("values", []):
            print(f"{sp['id']:<6} | {sp['name']}  ({sp['state']})  board={b['id']}")


def cmd_transitions(key):
    t = req("GET", f"/rest/api/2/issue/{key}/transitions")
    for tr in t.get("transitions", []):
        print(f"{tr['id']:<6} | {tr['name']}  -> {tr.get('to', {}).get('name', '')}")


def cmd_transition(key, name):
    t = req("GET", f"/rest/api/2/issue/{key}/transitions")
    match = [tr for tr in t.get("transitions", []) if tr["name"].lower() == name.lower()]
    if not match:
        avail = ", ".join(tr["name"] for tr in t.get("transitions", []))
        die(f"No transition named '{name}'. Available: {avail or '(none)'}")
    req("POST", f"/rest/api/2/issue/{key}/transitions",
        {"transition": {"id": match[0]["id"]}})
    print(f"OK: {key} -> {match[0]['name']}")


def resolve_field(field, project=None):
    """Map a friendly field name (jira.fields) to its id — the project's own table first,
    then any project's; pass anything else through as a literal id, so built-ins
    (`summary`, `versions`) and any raw `customfield_*` work."""
    for rows in (field_rows(project), field_rows(None)) if project else (field_rows(None),):
        for friendly, fid, _ in rows:
            if friendly.lower() == field.lower().replace("_", " "):
                return fid
    return field


def cmd_set(key, field, raw_value):
    field_id = resolve_field(field, key.split("-", 1)[0])
    try:
        value = json.loads(raw_value)
    except json.JSONDecodeError:
        value = raw_value
    req("PUT", f"/rest/api/2/issue/{key}", {"fields": {field_id: value}})
    print(f"OK: set {field_id} on {key}")


def cmd_create(args):
    """create <PROJECT> <TYPE> <SUMMARY> [--description TEXT] [--field id=json ...]

    Creates an issue with only the fields you pass. Discover required fields
    first with `fields <PROJECT>` (some types need custom fields). Each --field
    key is a field id OR a friendly name (jira.fields); the value is parsed as
    JSON, falling back to a raw string (same rule as `set`). Prints key + URL.
    """
    positional, description, extra_fields, links = [], None, {}, []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--link":
            if i + 1 >= len(args) or ":" not in args[i + 1]:
                die('--link needs "TYPE:KEY" (e.g. --link "Issue split:PROJ-1234").')
            ltype, lkey = args[i + 1].rsplit(":", 1)
            links.append((ltype.strip(), lkey.strip()))
            i += 2
        elif a == "--description":
            if i + 1 >= len(args):
                die("--description needs a value.")
            description = args[i + 1]
            i += 2
        elif a == "--field":
            if i + 1 >= len(args):
                die("--field needs an id=value argument.")
            pair = args[i + 1]
            if "=" not in pair:
                die(f"--field must be id=value, got '{pair}'.")
            name, raw = pair.split("=", 1)
            try:
                extra_fields[name] = json.loads(raw)
            except json.JSONDecodeError:
                extra_fields[name] = raw
            i += 2
        else:
            positional.append(a)
            i += 1
    if len(positional) < 3:
        die("create needs <PROJECT> <TYPE> <SUMMARY>. See the header for usage.")
    project, issuetype, summary = positional[0], positional[1], " ".join(positional[2:])
    extra_fields = {resolve_field(n, project): v for n, v in extra_fields.items()}
    fields = {
        "project": {"key": project},
        "issuetype": {"name": issuetype},
        "summary": summary,
    }
    if description is not None:
        fields["description"] = description
    fields.update(extra_fields)
    body = {"fields": fields}
    if links:
        # New issue is the OUTWARD side of each link: for "Issue split", PARENT "split to" NEW.
        body["update"] = {"issuelinks": [
            {"add": {"type": {"name": _resolve_link_type(t)}, "inwardIssue": {"key": k}}}
            for t, k in links]}
    res = req("POST", "/rest/api/2/issue", body)
    key = res.get("key")
    if not key:
        die(f"Create returned no key: {res}")
    print(f"OK: created {key}")
    print(f"{base_url()}/browse/{key}")
    if links and not res.get("dryRun"):
        cmd_links(key)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "create":  # variadic flags — handled outside the fixed-arity table
        cmd_create(args)
        return
    table = {
        "whoami": (cmd_whoami, 0),
        "get": (cmd_get, 1),
        "search": (cmd_search, 1),
        "fields": (cmd_fields, 1),
        "attachments": (cmd_attachments, 1),
        "download": (cmd_download, 2),
        "upload": (cmd_upload, 2),
        "comment": (cmd_comment, 2),
        "label": (cmd_label, 3),
        "links": (cmd_links, 1),
        "link": (cmd_link, 3),
        "api": (cmd_api, 1),
        "versions": (cmd_versions, 1),
        "sprints": (cmd_sprints, 1),
        "transitions": (cmd_transitions, 1),
        "transition": (cmd_transition, 2),
        "set": (cmd_set, 3),
    }
    if cmd not in table:
        die(f"Unknown command '{cmd}'.\n{__doc__}")
    fn, n = table[cmd]
    if len(args) < n:
        die(f"'{cmd}' needs {n} argument(s). See the header for usage.")
    # search takes an optional 2nd arg (maxResults)
    fn(*args[: n + 1] if cmd == "search" else args[:n])


if __name__ == "__main__":
    main()
