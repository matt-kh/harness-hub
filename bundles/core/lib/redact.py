#!/usr/bin/env python3
"""Redact secrets from JSON structures and free text / logs. Stdlib only, 3.9+.

One token-shape list for every CLI that prints cluster objects, pipeline logs or config
(principle 10): values under secret-looking keys (password, token, api_key, client_secret,
credential, auth, cert, jwt, dsn, connection_string, ...), Kubernetes Secret data (shown as
byte sizes), AWS access key ids, JWTs, PEM private-key blocks and URL userinfo.
A mid-line `key: <scheme> <token>` value whose first word is an HTTP auth scheme (Bearer,
Basic, Token, Digest, Negotiate, ApiKey, Api-Key, Key, SSWS, OAuth; any case) is masked as
one value, scheme word and token together.

Standalone CLIs are rendered without this directory next to them, so each carries an inlined
copy of the block between the `>>> redact` / `<<< redact` markers below;
bundles/core/tests/run.sh (sync_inline.py --check) fails when a copy drifts from this file.
The host script imports `base64` and `re` (the block itself imports nothing, like the other
core blocks).

API (inside the block):
    REDACTED                         the replacement string, "***REDACTED***"
    KEY_BODY, SECRET_KEY_RE          the secret-looking key-name regex (source, compiled)
    redact_obj(obj, extra_re=None)   JSON walk: secret keys -> REDACTED, Secret data -> sizes
    redact_text(text, extra_re=None) free text: key=value, AWS keys, JWTs, PEM, URL userinfo
`extra_re` is an optional compiled regex (callers read it from their own *_REDACT_EXTRA_RE
setting); its matches are replaced with REDACTED in text and in string values. None keeps
the built-in behaviour unchanged.

CLI:  redact.py [EXTRA_RE] < input     JSON in -> compact JSON out; anything else -> text
"""
import base64
import json
import re
import sys

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


def main(argv):
    extra = re.compile(argv[1]) if len(argv) > 1 and argv[1] else None
    raw = sys.stdin.read()
    try:
        obj = json.loads(raw)
    except ValueError:
        sys.stdout.write(redact_text(raw, extra))
        if raw and not raw.endswith("\n"):
            sys.stdout.write("\n")
        return 0
    sys.stdout.write(json.dumps(redact_obj(obj, extra), default=str) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
