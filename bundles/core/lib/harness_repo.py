#!/usr/bin/env python3
"""Read a repository's `.harness.toml` (principle 8). Stdlib only, python 3.9+.

Shell twin: harness_repo.sh (same subset, same answers; bundles/core/tests checks parity).
The guard parses the file in bash 3.2, so every reader accepts only this TOML subset — one
statement per line:

    [section]
    key = "string"          (no escapes: a backslash or double quote inside is refused)
    key = 'string'          (literal: anything but a single quote)
    key = ["a", 'b']        (one line; items are strings)
    # whole-line comments

No inline comments, multi-line arrays, inline tables or dotted keys: such a line is reported
as a problem and ignored (fail open); so is a repeated key (the first one counts) and a plain
string in [owns] (arrays only). A file larger than 16 KiB or longer than 400 lines is ignored as
a whole.

Python skill scripts carry an inlined copy of the block between the `>>> harness_repo` /
`<<< harness_repo` markers; `harness repo` (lib/harness/repo.py) loads this file by path.

CLI:  harness_repo.py root [DIR]              the repository root (rc 1 outside a checkout)
      harness_repo.py file [DIR]              the .harness.toml path (rc 1 when absent)
      harness_repo.py get SECTION KEY [DIR]   value(s), one per line (rc 1 when absent)
      harness_repo.py owns ID DOMAIN [DIR]    rc 0 when the repository owns ID or DOMAIN
"""
import os
import re
import sys

# >>> harness_repo
_HREPO_MAX = 16384
_HREPO_MAX_LINES = 400
_HREPO_KEY = re.compile(r"^[A-Za-z0-9_]+$")
_HREPO_NEVER = ("core/guard.d/20-credentials", "core/permissions")


def repo_root(start=None):
    """First ancestor of ``start`` (default: cwd) holding ``.git`` (dir or worktree file), else None."""
    d = start or os.getcwd()
    if not d.startswith("/"):
        return None
    d = d.rstrip("/") or "/"
    for _ in range(64):
        if d in ("", "/"):
            return None
        if os.path.exists(os.path.join(d, ".git")):
            return d
        d = d.rsplit("/", 1)[0]
    return None


def repo_file(start=None):
    root = repo_root(start)
    if not root:
        return None
    path = os.path.join(root, ".harness.toml")
    return path if os.path.isfile(path) and os.access(path, os.R_OK) else None


def _hrepo_unquote(v):
    if len(v) >= 2 and v[0] == v[-1] == '"':
        inner = v[1:-1]
        return None if ('"' in inner or "\\" in inner) else inner
    if len(v) >= 2 and v[0] == v[-1] == "'":
        inner = v[1:-1]
        return None if "'" in inner else inner
    return None


def _hrepo_lines(text):
    """Lines as bash ``read`` sees them: split on newline only; a final newline ends the last line."""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def parse_subset(text):
    """Parse the subset -> (data, problems); data = {section: {key: str | [str]}}, problems = [(line, why)]."""
    data, problems, sec = {}, [], ""
    if len(text.encode("utf-8", "replace")) > _HREPO_MAX:
        return {}, [(0, "larger than 16 KiB")]
    lines = _hrepo_lines(text)
    if len(lines) > _HREPO_MAX_LINES:
        return {}, [(0, "more than %d lines" % _HREPO_MAX_LINES)]
    for n, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            sec = line[1:-1].strip()
            continue
        if line.startswith("["):
            problems.append((n, "unterminated section header"))
            sec = ""
            continue
        if "=" not in line:
            problems.append((n, "not key = value"))
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip()
        if not k or not _HREPO_KEY.match(k):
            problems.append((n, "bad key %r" % k))
            continue
        if v.startswith("[") and v.endswith("]"):
            items, bad = [], False
            for item in v[1:-1].split(","):
                item = item.strip()
                if not item:
                    continue
                u = _hrepo_unquote(item)
                if u is None:
                    bad = True
                    continue
                items.append(u)
            if bad:
                problems.append((n, "unquoted or escaped array item"))
            value = items
        elif sec == "owns":
            problems.append((n, "%s must be a one-line array of strings (no inline comments)" % k))
            continue
        else:
            value = _hrepo_unquote(v)
            if value is None:
                problems.append((n, "%s must be a quoted string or a one-line array (no inline comments or escapes)" % k))
                continue
        if k in data.get(sec, {}):
            problems.append((n, "duplicate key %s in [%s]; the guard uses the first" % (k, sec)))
            continue
        data.setdefault(sec, {})[k] = value
    return data, problems


def repo_declaration(start=None):
    """(path, data, problems) of the repository's .harness.toml; (None, {}, []) when there is none."""
    path = repo_file(start)
    if not path:
        return None, {}, []
    try:
        with open(path, "rb") as fh:
            raw = fh.read(_HREPO_MAX + 1)
    except OSError as exc:
        return path, {}, [(0, "unreadable: %s" % exc)]
    if len(raw) > _HREPO_MAX:
        return path, {}, [(0, "larger than 16 KiB")]
    return (path,) + parse_subset(raw.decode("utf-8", "replace"))


def _hrepo_list(v):
    return v if isinstance(v, list) else []


def repo_owns(cid, domain, start=None):
    """True when the repository declares the component id or its domain in [owns] (never credentials)."""
    if cid in _HREPO_NEVER:
        return False
    _path, data, _problems = repo_declaration(start)
    owns = data.get("owns") or {}
    if cid in _hrepo_list(owns.get("components")):
        return True
    return bool(domain) and domain in _hrepo_list(owns.get("domains"))
# <<< harness_repo


def main(argv):
    args = argv[1:]
    if not args:
        print(__doc__.strip().splitlines()[-4].strip(), file=sys.stderr)
        return 2
    cmd, rest = args[0], args[1:]
    if cmd == "root" and len(rest) <= 1:
        r = repo_root(rest[0] if rest else None)
        if r:
            print(r)
        return 0 if r else 1
    if cmd == "file" and len(rest) <= 1:
        f = repo_file(rest[0] if rest else None)
        if f:
            print(f)
        return 0 if f else 1
    if cmd == "get" and len(rest) in (2, 3):
        _p, data, _pr = repo_declaration(rest[2] if len(rest) == 3 else None)
        v = (data.get(rest[0]) or {}).get(rest[1])
        if v is None:
            return 1
        for item in (v if isinstance(v, list) else [v]):
            print(item)
        return 0
    if cmd == "owns" and len(rest) in (2, 3):
        return 0 if repo_owns(rest[0], rest[1], rest[2] if len(rest) == 3 else None) else 1
    print("usage: harness_repo.py root|file [DIR] | get SECTION KEY [DIR] | owns ID DOMAIN [DIR]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
