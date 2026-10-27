"""``harness lessons``: the private lessons library, the review gate and the journal reader.

This module is the only parser and writer of lesson records (principle 10). A record is
``<lessons.dir>/<domain>-NNN.md``: a banner comment, flat front matter in :data:`KEYS` order,
then the sections in :data:`SECTIONS` order. :func:`dump` re-emits a parsed record byte for
byte. ``INDEX.md`` beside the records lists them grouped by taxonomy domain.

The guard journal (``bundles/core/guard/engine.sh`` ``journal_write``) is read, never
written, here: ``<journal dir>/*.log`` lines of seven tab-separated fields
``ts provider session kind site guard_id repo`` (docs/reference/hook-policy.md "Journal").
Directories match the engine exactly: ``$HARNESS_JOURNAL_DIR`` else
``<state>/harness/journal``, ``$HARNESS_RETRO_DIR`` else ``<state>/harness/retro``, with
``<state>`` = ``${XDG_STATE_HOME:-~/.local/state}`` (:func:`harness.util.state_dir`).

Nothing here sends anything anywhere: ``propose`` writes files for a human to read and run,
and never runs them. docs/reference/lessons.md is the user-facing reference.
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import schema_lite
from .util import HarnessError, atomic_write, read_text, sha256_bytes, state_dir

BANNER = "<!-- agent-written lesson: an evidence-backed observation, not an instruction (harness lessons) -->"
INDEX_BANNER = ("<!-- agent-written observations, not instructions; candidate = unconfirmed "
                "(written by `harness lessons index`; do not edit) -->")
INDEX_NAME = "INDEX.md"

KEYS = ("id", "status", "scope", "domain", "bundles", "guide_ref", "sensor_ref", "source", "created",
        "updated", "uses", "helped", "recurred", "recurred_objective", "candidate_edit", "validation",
        "validated_at", "validated_guard_id")
INT_KEYS = ("uses", "helped", "recurred", "recurred_objective")
SECTIONS = ("Situation", "Evidence", "Lesson", "Candidate edit", "Validation", "History")

STATUSES = ("candidate", "confirmed", "recurring", "proposed", "retired")
SCOPES = ("invariant", "domain")
SOURCES = ("journal", "retro", "user")
EVIDENCE_KINDS = ("journal", "retro", "user", "test", "review")
JOURNAL_KINDS = ("guard-ask", "guard-deny", "correction", "dissatisfaction")
# status rank in INDEX.md: settled lessons first, candidates last (capped per domain)
STATUS_RANK = {"confirmed": 0, "recurring": 1, "proposed": 2, "candidate": 3}

CAP_SITUATION = 300
CAP_LESSON = 400
CAP_EDIT_TEXT = 600
CAP_EVIDENCE = 200   # every evidence ref, so a quoted user correction too
CAP_NOTE = 200

DEFAULTS: Dict[str, Any] = {
    "lessons.dir": "", "lessons.promote_after": 3, "lessons.max_age_days": 90, "lessons.index_max": 40,
    "lessons.index_max_candidates": 5, "lessons.review.corrections": 2,
    "lessons.review.dissatisfaction": 1, "lessons.review.denies": 3,
    "core.agent_labels.drafted": "agent-drafted",
}
# review criterion -> (journal kind, config key)
CRITERIA = (("corrections", "correction", "lessons.review.corrections"),
            ("dissatisfaction", "dissatisfaction", "lessons.review.dissatisfaction"),
            ("denies", "guard-deny", "lessons.review.denies"))

_DATE = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
_TS = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
ID_RE = re.compile(r"^([a-z]+)-([0-9]{3,})$")
REF_KIND_DIRS = ("rules", "skills", "agents", "guard.d", "hooks", "permissions", "mcp", "bin", "install",
                 "doctor", "steps")
REF_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*/(%s)/[A-Za-z0-9._-]+$" % "|".join(re.escape(k) for k in REF_KIND_DIRS))
BUNDLE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

LESSON_SCHEMA: Dict[str, Any] = {
    "type": "object", "additionalProperties": False, "required": list(KEYS),
    "properties": {
        "id": {"type": "string", "pattern": ID_RE.pattern},
        "status": {"enum": list(STATUSES)},
        "scope": {"enum": list(SCOPES)},
        "domain": {"type": "string"},
        "bundles": {"type": "array", "items": {"type": "string", "pattern": BUNDLE_RE.pattern},
                    "uniqueItems": True},
        "guide_ref": {"type": "string", "pattern": REF_RE.pattern},
        "sensor_ref": {"type": "string", "pattern": REF_RE.pattern},
        "source": {"enum": list(SOURCES)},
        "created": {"type": "string", "pattern": _DATE},
        "updated": {"type": "string", "pattern": _DATE},
        "uses": {"type": "integer", "minimum": 0},
        "helped": {"type": "integer", "minimum": 0},
        "recurred": {"type": "integer", "minimum": 0},
        "recurred_objective": {"type": "integer", "minimum": 0},
        "candidate_edit": {"type": "string", "pattern": r"^(|patches/[a-z]+-[0-9]{3,}\.diff)$"},
        "validation": {"enum": ["none", "pass", "fail"]},
        "validated_at": {"type": "string", "pattern": r"^(|[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z)$"},
        "validated_guard_id": {"type": "string", "pattern": r"^(|[0-9a-f]{12})$"},
    },
}

# token shapes (config.looks_like_secret_value is the shared detector) and URL userinfo
_USERINFO = re.compile(r"://[^/\s@]+@")   # any userinfo: user:password@, token@, user@
_SUBPARTS = re.compile(r"://|[@:/=]")
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_HEX = re.compile(r"^[0-9a-f]{7,64}$")
_IDENT = re.compile(r"^[a-z][a-z0-9]*([_.-][a-z0-9]+)+$")
# keyword, optional markup (**Fixes**), optional colon, optional space, then an issue reference;
# a Jira key is matched case-sensitively so "fixes utf-8" is not one
CLOSING_RE = re.compile(
    r"\b(close[sd]?|fix(e[sd])?|resolve[sd]?|implement(s|ed)?)\b(\*\*|__)?\s*:?\s*"
    r"(#[0-9]+|[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#[0-9]+|https?://\S+/(issues|pull|merge_requests)/[0-9]+"
    r"|(?-i:[A-Z][A-Z0-9_]*-[0-9]+))",
    re.I)
HEADING_RE = re.compile(r"^#{1,6}(\s|$)")
ISSUE_REF_RE = re.compile(r"(^|[^&A-Za-z0-9])#[0-9]+")
OWNER_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class LessonError(HarnessError):
    """A refused lesson operation (rc 1) with the reason and what to do instead."""


# ================================================================= small helpers


def today() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def now_ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def norm_ts(value: Optional[str]) -> str:
    """``--now``/``--since``: a date or an ISO UTC timestamp -> ``YYYY-MM-DDTHH:MM:SSZ``."""
    if not value:
        return now_ts()
    if re.match(_DATE, value):
        return value + "T00:00:00Z"
    if re.match(_TS, value):
        return value
    raise HarnessError("%s: expected YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ (UTC)" % value, 2)


def norm_date(value: Optional[str]) -> str:
    if not value:
        return today()
    if not re.match(_DATE, value):
        raise HarnessError("--date %s: expected YYYY-MM-DD" % value, 2)
    return value


def days_between(a: str, b: str) -> int:
    """Whole days from date ``a`` to date ``b`` (both YYYY-MM-DD)."""
    import calendar

    ta = calendar.timegm(time.strptime(a[:10], "%Y-%m-%d"))
    tb = calendar.timegm(time.strptime(b[:10], "%Y-%m-%d"))
    return int((tb - ta) // 86400)


def one_line(text: Optional[str]) -> str:
    return " ".join((text or "").split())


def secret_reason(text: str) -> Optional[str]:
    """Why ``text`` may not be stored (token-shaped word, URL userinfo), else None."""
    from .config import _TOKEN_PREFIX, looks_like_secret_value

    if _USERINFO.search(text or ""):
        return ("contains URL userinfo (a user name, token or password before @ in a URL); "
                "drop the credential part")
    for raw in (text or "").split():
        word = raw.strip("\"'`()[]{}<>,;")
        if word and _TOKEN_PREFIX.match(word):
            return "contains a token-shaped string (%s...); never record a secret" % word[:4]
        # the parts of URLs, user@host, key=value and paths are tested on their own
        for part in _SUBPARTS.split(word):
            part = part.strip("\"'`()[]{}<>,;.")
            if not part:
                continue
            if not _TOKEN_PREFIX.match(part):
                if _UUID.match(part) or _HEX.match(part):
                    continue   # session ids and git object ids are not secrets
                if _IDENT.match(part) and max(len(x) for x in re.split(r"[_.-]", part)) <= 16:
                    continue   # snake/kebab identifiers (guard_section_core_20_credentials)
                if not looks_like_secret_value(part):
                    continue
            return "contains a token-shaped string (%s...); never record a secret" % part[:4]
    return None


def check_text(field: str, text: str, cap: int) -> str:
    text = one_line(text)
    if len(text) > cap:
        raise LessonError("%s is %d characters; the cap is %d: shorten it" % (field, len(text), cap))
    if HEADING_RE.match(text):
        raise LessonError("%s starts like a Markdown heading (%r); records use headings for their "
                          "sections: reword it" % (field, text[:20]))
    why = secret_reason(text)
    if why:
        raise LessonError("%s %s" % (field, why))
    return text


def cfg(hub: Any, key: str) -> Any:
    try:
        val = hub.config.get(key) if hub is not None else None
    except Exception:
        val = None
    return DEFAULTS.get(key) if val is None else val


# ================================================================= locations


def lessons_dir(hub: Any) -> str:
    raw = str(cfg(hub, "lessons.dir") or "")
    if not raw:
        return os.path.join(state_dir(), "lessons")
    full = os.path.expanduser(raw)
    if not os.path.isabs(full):
        raise LessonError("lessons.dir %r is relative: it would resolve against the current directory, "
                          "which is usually a checkout; use an absolute path or ~/... (or leave it empty "
                          "for %s)" % (raw, os.path.join(state_dir(), "lessons")))
    return os.path.normpath(full)


def _env_dir(name: str, leaf: str) -> str:
    """Same rule as engine.sh: $NAME, else <state>/harness/<leaf>; a relative result is '' (off)."""
    d = os.environ.get(name) or os.path.join(state_dir(), leaf)
    return d if os.path.isabs(d) else ""


def journal_dir() -> str:
    return _env_dir("HARNESS_JOURNAL_DIR", "journal")


def retro_dir() -> str:
    return _env_dir("HARNESS_RETRO_DIR", "retro")


def _git_checkout_of(path: str) -> Optional[str]:
    """The nearest ancestor of ``path`` (itself included) holding ``.git``, else None."""
    cur = os.path.realpath(path)
    while True:
        if os.path.exists(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def _under(path: str, base: str) -> bool:
    base = base.rstrip("/")
    return path == base or path.startswith(base + "/")


def dir_problem(path: str, home: str) -> Optional[str]:
    """Why ``path`` may not hold lessons or proposals (under the hub, inside a checkout), else None.

    ``$HOME``'s own ``.git`` (a dotfiles repository) is ignored for paths under the XDG state
    directory, which such repositories do not track."""
    real = os.path.realpath(path)
    hub = os.path.realpath(home)
    if _under(real, hub):
        return "is under the hub checkout %s" % home
    top = _git_checkout_of(path)
    if top:
        user = os.path.realpath(os.path.expanduser("~"))
        state = os.path.realpath(os.environ.get("XDG_STATE_HOME") or os.path.join(user, ".local", "state"))
        if top == user and _under(real, state):
            return None
        return "is inside the git checkout %s" % top
    return None


def _dir_hint(home: str) -> str:
    for cand in (os.path.join(state_dir(), "lessons"),
                 os.path.join(os.path.expanduser("~"), ".local", "state", "harness", "lessons")):
        if dir_problem(cand, home) is None:
            return "set lessons.dir to an absolute directory outside every git checkout, e.g. %s" % cand
    return ("set lessons.dir to an absolute directory outside the hub and every git checkout "
            "(the default %s is inside one here)" % os.path.join(state_dir(), "lessons"))


def check_dir(path: str, home: str, what: str = "lessons.dir") -> None:
    """Refuse a lessons directory under the hub checkout or inside any git checkout."""
    why = dir_problem(path, home)
    if why:
        raise LessonError("%s %s %s; lessons stay on this workstation and never enter a repository: %s"
                          % (what, path, why, _dir_hint(home) if what == "lessons.dir" else
                             "pass a directory outside the hub and every git checkout"))


# ================================================================= records


class Lesson:
    def __init__(self, fm: "OrderedDict[str, Any]", sections: "OrderedDict[str, List[str]]"):
        self.fm = fm
        self.sections = sections

    @property
    def id(self) -> str:
        return self.fm["id"]

    @property
    def status(self) -> str:
        return self.fm["status"]

    @property
    def situation(self) -> str:
        return " ".join(self.sections.get("Situation") or [])

    def history(self, date: str, text: str) -> None:
        self.sections["History"].append("- %s %s" % (date, text))
        self.fm["updated"] = date

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = OrderedDict(self.fm)
        out["situation"] = self.situation
        out["lesson"] = " ".join(self.sections.get("Lesson") or [])
        out["evidence"] = [ln[2:] for ln in self.sections.get("Evidence") or [] if ln.startswith("- ")]
        return out


def _fm_value(key: str, raw: str, where: str) -> Any:
    if key in INT_KEYS:
        if not re.match(r"^[0-9]+$", raw):
            raise LessonError("%s: %s must be a non-negative integer, got %r" % (where, key, raw))
        return int(raw)
    if key == "bundles":
        if not (raw.startswith("[") and raw.endswith("]")):
            raise LessonError("%s: bundles must be [a, b], got %r" % (where, raw))
        inner = raw[1:-1].strip()
        return [x.strip() for x in inner.split(",")] if inner else []
    return raw


def _fm_text(key: str, value: Any) -> str:
    if key == "bundles":
        return "%s: [%s]" % (key, ", ".join(value))
    text = str(value)
    return "%s: %s" % (key, text) if text != "" else "%s:" % key


def validate_fm(fm: Dict[str, Any], where: str) -> None:
    from . import taxonomy as T

    res = schema_lite.validate(LESSON_SCHEMA, dict(fm))
    if res.errors:
        raise LessonError("%s: %s" % (where, "; ".join(res.errors)))
    if fm["domain"] not in T.FACETS["domain"]:
        raise LessonError("%s: unknown domain %r; use one of %s" % (where, fm["domain"], ", ".join(T.FACETS["domain"])))
    if fm["scope"] == "invariant" and fm["domain"] != "base":
        raise LessonError("%s: scope invariant needs domain base (an invariant applies everywhere); "
                          "use --scope domain for a %s lesson" % (where, fm["domain"]))
    m = ID_RE.match(fm["id"])
    if not m or m.group(1) != fm["domain"]:
        raise LessonError("%s: id %s does not start with its domain %s" % (where, fm["id"], fm["domain"]))


def parse(text: str, where: str = "lesson") -> Lesson:
    lines = text.split("\n")
    if not text.endswith("\n"):
        raise LessonError("%s: no final newline; records are written by `harness lessons` only" % where)
    lines = lines[:-1]
    if len(lines) < 3 or lines[0] != BANNER or lines[1] != "---":
        raise LessonError("%s: not a lesson record (banner and --- expected); records are written by "
                          "`harness lessons new` only" % where)
    fm: "OrderedDict[str, Any]" = OrderedDict()
    i = 2
    while i < len(lines) and lines[i] != "---":
        m = re.match(r"^([a-z_]+):(?: (.*))?$", lines[i])
        if not m:
            raise LessonError("%s: line %d: expected `key: value`" % (where, i + 1))
        key = m.group(1)
        if key not in KEYS:
            raise LessonError("%s: line %d: unknown key %s" % (where, i + 1, key))
        if key in fm:
            raise LessonError("%s: line %d: duplicate key %s" % (where, i + 1, key))
        fm[key] = _fm_value(key, m.group(2) or "", where)
        i += 1
    if i >= len(lines):
        raise LessonError("%s: front matter is not closed with ---" % where)
    if list(fm) != list(KEYS):
        raise LessonError("%s: front matter keys must be, in order: %s" % (where, ", ".join(KEYS)))
    validate_fm(fm, where)
    i += 1
    sections: "OrderedDict[str, List[str]]" = OrderedDict()
    cur: Optional[str] = None
    for n in range(i, len(lines)):
        ln = lines[n]
        if ln.startswith("## ") and ln[3:] in SECTIONS:
            cur = ln[3:]
            if cur in sections:
                raise LessonError("%s: line %d: duplicate section %s" % (where, n + 1, cur))
            sections[cur] = []
            continue
        if cur is None:
            if ln.strip():
                raise LessonError("%s: line %d: text before the first section" % (where, n + 1))
            continue
        sections[cur].append(ln)
    if list(sections) != list(SECTIONS):
        raise LessonError("%s: sections must be, in order: %s" % (where, ", ".join(SECTIONS)))
    for k, body in sections.items():
        while body and not body[-1].strip():
            body.pop()
        while body and not body[0].strip():
            body.pop(0)
    return Lesson(fm, sections)


def dump(lesson: Lesson) -> str:
    out = [BANNER, "---"]
    out += [_fm_text(k, lesson.fm[k]) for k in KEYS]
    out.append("---")
    for n, name in enumerate(SECTIONS):
        out.append("## %s" % name)
        out += lesson.sections.get(name) or []
        if n < len(SECTIONS) - 1:
            out.append("")
    return "\n".join(out) + "\n"


def record_path(d: str, lid: str) -> str:
    if not ID_RE.match(lid or ""):
        raise HarnessError("%s: not a lesson id (<domain>-NNN, e.g. base-001)" % lid, 2)
    return os.path.join(d, "%s.md" % lid)


def load(d: str, lid: str) -> Lesson:
    path = record_path(d, lid)
    text = read_text(path)
    if text is None:
        raise LessonError("no lesson %s in %s (`harness lessons list` shows the ids)" % (lid, d))
    rec = parse(text, path)
    if rec.id != lid:
        raise LessonError("%s: front matter id %s differs from the file name %s; records are renamed by "
                          "nobody: restore the id or retire the record" % (path, rec.id, lid))
    return rec


def load_all(d: str, bad: Optional[List[Tuple[str, str]]] = None) -> List[Lesson]:
    """Every readable record. A record that does not parse is skipped, never fatal: it goes to
    ``bad`` as (id, reason) when a list is given, else one line on stderr."""
    import sys

    out = []
    for path in sorted(glob.glob(os.path.join(d, "*.md"))):
        lid = os.path.basename(path)[:-3]
        if not ID_RE.match(lid):
            continue
        try:
            out.append(load(d, lid))
        except LessonError as exc:
            if bad is not None:
                bad.append((lid, str(exc)))
            else:
                print("harness: skipping unreadable lesson %s: %s" % (path, exc), file=sys.stderr)
    return out


def _checked(lesson: Lesson) -> bytes:
    """dump() after the round-trip invariant: what is written parses back to the same bytes."""
    validate_fm(lesson.fm, lesson.id)
    text = dump(lesson)
    try:
        again = dump(parse(text, lesson.id))
    except LessonError as exc:
        raise LessonError("%s: refusing to write a record that would not parse back (%s)" % (lesson.id, exc))
    if again != text:
        raise LessonError("%s: refusing to write a record that would not round-trip; check the text "
                          "for heading-like or blank-padded lines" % lesson.id)
    return text.encode("utf-8")


def save(d: str, lesson: Lesson) -> str:
    data = _checked(lesson)
    path = record_path(d, lesson.id)
    atomic_write(path, data, mode=0o600)
    return path


def create(d: str, lesson: Lesson) -> str:
    """Write a new record; FileExistsError when the id is already taken (O_CREAT | O_EXCL)."""
    data = _checked(lesson)
    path = record_path(d, lesson.id)
    os.makedirs(d, mode=0o700, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    return path


def next_id(d: str, domain: str) -> str:
    high = 0
    for path in glob.glob(os.path.join(d, "%s-*.md" % domain)):
        m = ID_RE.match(os.path.basename(path)[:-3])
        if m and m.group(1) == domain:
            high = max(high, int(m.group(2)))
    return "%s-%03d" % (domain, high + 1)


def evidence_line(ref: str) -> str:
    """``kind:text`` -> ``kind: text`` after the shape, cap and secret checks."""
    m = re.match(r"^\s*([a-z]+)\s*:\s*(.*)$", ref or "", re.S)
    if not m or m.group(1) not in EVIDENCE_KINDS or not m.group(2).strip():
        raise LessonError("evidence %r: expected KIND:TEXT with KIND one of %s (e.g. "
                          "journal:<a journal line>, user:\"<quoted correction>\")" % (ref, ", ".join(EVIDENCE_KINDS)))
    text = check_text("evidence %s" % m.group(1), m.group(2), CAP_EVIDENCE)
    return "%s: %s" % (m.group(1), text)


# ----------------------------------------------------------------- candidate edits

_HUNK = re.compile(r"^@@ -[0-9]+(?:,([0-9]+))? \+[0-9]+(?:,([0-9]+))? @@")


def _strip_ab(p: str) -> str:
    p = p.split("\t")[0].strip()
    if p.startswith('"') and p.endswith('"'):
        p = p[1:-1]
    return p[2:] if p.startswith(("a/", "b/")) else p


def parse_diff(diff: str) -> Tuple[List[Tuple[str, int, int]], List[str]]:
    """(files, paths) of a git unified diff.

    ``files`` is (path, added, removed) per file; ``paths`` is every path any header names:
    ``diff --git a/X b/Y``, ``---``, ``+++``, ``rename|copy from|to`` and binary headers, so a
    deletion (``+++ /dev/null``), a rename or a copy cannot hide a path. Hunk bodies are
    consumed by their line counts, so a removed line that starts with ``--`` is never a header.
    """
    files: List[List[Any]] = []
    paths: List[str] = []
    cur: Optional[List[Any]] = None
    old = ""
    lines = diff.splitlines()
    i = 0

    def add(p: str) -> None:
        if p and p != "/dev/null" and p not in paths:
            paths.append(p)

    while i < len(lines):
        ln = lines[i]
        i += 1
        if ln.startswith("diff --git "):
            m = re.match(r"^diff --git (\S+) (\S+)$", ln)
            if not m:
                raise LessonError("--edit: unparsable header %r (paths with spaces are not supported)" % ln[:80])
            a, b = _strip_ab(m.group(1)), _strip_ab(m.group(2))
            add(a)
            add(b)
            cur = [b, 0, 0]
            files.append(cur)
            old = a
        elif ln.startswith("--- "):
            old = _strip_ab(ln[4:])
            add(old)
        elif ln.startswith("+++ "):
            p = _strip_ab(ln[4:])
            add(p)
            p = old if p == "/dev/null" else p
            if cur is None or cur[0] not in (p, old):
                cur = [p, 0, 0]
                files.append(cur)
            else:
                cur[0] = p
        elif re.match(r"^(rename|copy) (from|to) ", ln):
            add(ln.split(" ", 2)[2].strip())
        elif ln.startswith("Binary files "):
            m = re.match(r"^Binary files (\S+) and (\S+) differ$", ln)
            if m:
                add(_strip_ab(m.group(1)))
                add(_strip_ab(m.group(2)))
        elif ln.startswith("GIT binary patch"):
            raise LessonError("--edit: binary patches are not candidate edits; guides and sensors are text")
        elif ln.startswith("@@ "):
            m = _HUNK.match(ln)
            if not m:
                raise LessonError("--edit: unparsable hunk header %r" % ln[:80])
            n_old = int(m.group(1)) if m.group(1) is not None else 1
            n_new = int(m.group(2)) if m.group(2) is not None else 1
            if cur is None:
                cur = [old, 0, 0]
                files.append(cur)
            while (n_old > 0 or n_new > 0) and i < len(lines):
                body = lines[i]
                i += 1
                if body.startswith("\\"):
                    continue
                if body.startswith("+"):
                    cur[1] += 1
                    n_new -= 1
                elif body.startswith("-"):
                    cur[2] += 1
                    n_old -= 1
                else:
                    n_old -= 1
                    n_new -= 1
    return [(f[0], f[1], f[2]) for f in files if f[0]], paths


def diff_files(diff: str) -> List[Tuple[str, int, int]]:
    return parse_diff(diff)[0]


def path_problem(path: str) -> Optional[str]:
    parts = path.split("/")
    if path.startswith("/") or ".." in parts or not path.startswith("bundles/") or len(parts) < 3:
        return ("%s is outside bundles/; a candidate edit changes a guide and its sensor inside one or "
                "more bundles only" % path)
    return None


def check_diff(diff: str) -> List[Tuple[str, int, int]]:
    files, paths = parse_diff(diff)
    if not files or not paths or ("\n@@ " not in "\n" + diff and "\ndiff --git " not in "\n" + diff):
        raise LessonError("--edit: not a unified diff (git diff output against the hub root expected)")
    for path in paths:
        why = path_problem(path)
        if why:
            raise LessonError("--edit: %s" % why)
    why = secret_reason(diff)
    if why:
        raise LessonError("--edit %s" % why)
    return files


def _expand_rename(text: str) -> List[str]:
    """``pre/{a => b}/post`` or ``a => b`` (git's rename notation) -> both paths."""
    m = re.match(r"^(.*)\{(.*) => (.*)\}(.*)$", text)
    if m:
        return [re.sub("//+", "/", m.group(1) + x + m.group(4)) for x in (m.group(2), m.group(3))]
    return [x.strip() for x in text.split(" => ")]


def applied_paths(diff_path: str, cwd: str, env: Optional[Dict[str, str]] = None) -> List[str]:
    """Every path ``git apply --numstat --summary`` says the patch touches (nothing is applied)."""
    rc, out = _run_step(["git", "apply", "--numstat", "--summary", os.path.abspath(diff_path)], cwd, env, 120,
                        whole=True)
    if rc != 0:
        raise LessonError("validate: git apply --numstat refused the patch: %s" % one_line(out)[:200])
    paths: List[str] = []
    for ln in out.splitlines():
        if not ln.strip():
            continue
        if "\t" in ln:
            got = _expand_rename(ln.split("\t", 2)[2])
        else:
            t = ln.strip()
            m = re.match(r"^(create|delete) mode [0-7]+ (.+)$", t)
            m2 = re.match(r"^mode change [0-7]+ => [0-7]+ (.+)$", t)
            m3 = re.match(r"^(rename|copy) (.+?)(?: \([0-9]+%\))?$", t)
            if m:
                got = [m.group(2)]
            elif m2:
                got = [m2.group(1)]
            elif m3:
                got = _expand_rename(m3.group(2))
            else:
                got = [t]   # unknown summary line: checked as a path, so it fails closed
        for p in got:
            if p not in paths:
                paths.append(p)
    return paths


def edit_text(rel: str, files: Sequence[Tuple[str, int, int]]) -> List[str]:
    lines = ["%s:" % rel]
    for n, (path, add, rem) in enumerate(files):
        line = "- %s (+%d -%d)" % (path, add, rem)
        if len("\n".join(lines + [line])) > CAP_EDIT_TEXT - 40:
            lines.append("- ... %d more file(s)" % (len(files) - n))
            break
        lines.append(line)
    return lines


def touched_bundles(files: Sequence[Tuple[str, int, int]]) -> List[str]:
    return sorted({p.split("/")[1] for p, _a, _r in files if p.count("/") >= 2})


# ================================================================= operations


def new_lesson(d: str, domain: str, scope: str, situation: str, guide_ref: str, sensor_ref: str,
               evidence: Sequence[str], bundles: Sequence[str] = (), source: str = "retro",
               lesson: str = "", edit: Optional[str] = None, date: Optional[str] = None) -> Lesson:
    from . import taxonomy as T

    date = norm_date(date)
    if domain not in T.FACETS["domain"]:
        raise LessonError("unknown domain %r; use one of %s" % (domain, ", ".join(T.FACETS["domain"])))
    if scope == "invariant" and domain != "base":
        raise LessonError("scope invariant needs domain base (an invariant applies everywhere); "
                          "use --scope domain for a %s lesson" % domain)
    if not evidence:
        raise LessonError("no evidence, no record: pass at least one --evidence KIND:TEXT")
    for name, ref in (("--guide-ref", guide_ref), ("--sensor-ref", sensor_ref)):
        if not REF_RE.match(ref or ""):
            raise LessonError("%s %r: expected <bundle>/<kind>/<name> with kind one of %s (an id from "
                              "`harness catalog`, e.g. core/guard.d/20-credentials)" % (name, ref, ", ".join(REF_KIND_DIRS)))
    for b in bundles:
        if not BUNDLE_RE.match(b):
            raise LessonError("--bundles %r: not a bundle name" % b)
    situation = check_text("--situation", situation, CAP_SITUATION)
    if not situation:
        raise LessonError("--situation is empty: say in one line when the lesson applies")
    lesson = check_text("--lesson", lesson, CAP_LESSON)
    ev: List[str] = []
    for ref in evidence:
        line = "- " + evidence_line(ref)
        if line not in ev:
            ev.append(line)
    diff = None
    files: List[Tuple[str, int, int]] = []
    if edit:
        diff = read_text(edit)
        if diff is None:
            raise LessonError("--edit %s: no such file" % edit)
        files = check_diff(diff)
    for _attempt in range(100):
        rec = _new_record(next_id(d, domain), scope, domain, bundles, guide_ref, sensor_ref, source, date,
                          situation, ev, lesson, diff, files)
        try:
            create(d, rec)
        except FileExistsError:
            continue   # another writer took this id: take the next one
        if diff is not None:
            atomic_write(os.path.join(d, rec.fm["candidate_edit"]), diff.encode("utf-8"), mode=0o600)
        return rec
    raise LessonError("could not reserve a new id in %s after 100 attempts" % d)


def _new_record(lid: str, scope: str, domain: str, bundles: Sequence[str], guide_ref: str, sensor_ref: str,
                source: str, date: str, situation: str, ev: List[str], lesson: str, diff: Optional[str],
                files: Sequence[Tuple[str, int, int]]) -> Lesson:
    rel = "patches/%s.diff" % lid if diff is not None else ""
    fm: "OrderedDict[str, Any]" = OrderedDict([
        ("id", lid), ("status", "candidate"), ("scope", scope), ("domain", domain),
        ("bundles", list(OrderedDict.fromkeys(bundles))), ("guide_ref", guide_ref), ("sensor_ref", sensor_ref),
        ("source", source), ("created", date), ("updated", date), ("uses", 0), ("helped", 0),
        ("recurred", 0), ("recurred_objective", 0), ("candidate_edit", rel), ("validation", "none"),
        ("validated_at", ""), ("validated_guard_id", "")])
    sections: "OrderedDict[str, List[str]]" = OrderedDict([
        ("Situation", [situation]), ("Evidence", ev), ("Lesson", [lesson] if lesson else []),
        ("Candidate edit", edit_text(rel, files) if diff is not None else []), ("Validation", []),
        ("History", ["- %s created (source %s)" % (date, source)])])
    return Lesson(fm, sections)


def note(d: str, rec: Lesson, promote_after: int, used: bool = False, helped: bool = False,
         recurred: bool = False, evidence: Sequence[str] = (), text: str = "",
         date: Optional[str] = None) -> List[str]:
    """Bump counters; return the change words (for the History line and the output)."""
    date = norm_date(date)
    if rec.status in ("retired", "proposed"):
        raise LessonError("%s is %s; notes go to open lessons only (candidate, confirmed, recurring)"
                          % (rec.id, rec.status))
    if not (used or helped or recurred or evidence or text):
        raise HarnessError("nothing to note: pass --used, --helped, --recurred, --evidence or --note", 2)
    text = check_text("--note", text, CAP_NOTE)
    lines: List[str] = []
    for ref in evidence:
        ln = "- " + evidence_line(ref)
        if ln not in lines:
            lines.append(ln)
    added = [ln for ln in lines if ln not in rec.sections["Evidence"]]
    # only a journal line new to this record, of the journal's own shape and present in the
    # journal, makes a recurrence objective: a repeated or invented ref never promotes
    fresh = [ln for ln in added if ln.startswith("- journal: ")]
    objective = False
    if recurred and fresh:
        objective = bool(verified_journal_refs(fresh))
    words: List[str] = []
    if used:
        rec.fm["uses"] += 1
        words.append("used")
    if helped:
        rec.fm["helped"] += 1
        words.append("helped")
    if recurred:
        rec.fm["recurred"] += 1
        if objective:
            rec.fm["recurred_objective"] += 1
        words.append("recurred (objective)" if objective else "recurred")
    rec.sections["Evidence"].extend(added)
    if added:
        words.append("evidence +%d" % len(added))
    hist = "note: %s" % ", ".join(words) if words else "note"
    if text:
        hist += "; %s" % text
    rec.history(date, hist)
    if rec.status == "candidate" and rec.fm["recurred_objective"] >= promote_after:
        rec.fm["status"] = "recurring"
        rec.history(date, "status recurring (%d objective recurrences >= lessons.promote_after %d)"
                    % (rec.fm["recurred_objective"], promote_after))
        words.append("now recurring")
    save(d, rec)
    return words


def journal_ref_fields(line: str) -> Optional[Tuple[str, ...]]:
    """``- journal: ts provider session kind site guard_id repo`` -> the seven fields, else None."""
    fields = tuple(line[len("- journal: "):].split())
    if len(fields) != 7 or not re.match(_TS, fields[0]) or fields[3] not in JOURNAL_KINDS:
        return None
    return fields


def verified_journal_refs(lines: Sequence[str]) -> List[str]:
    """The journal evidence lines that name a line of the journal; refuses malformed ones."""
    jdir = journal_dir()
    for ln in lines:
        if journal_ref_fields(ln) is None:
            raise LessonError("--recurred evidence %r is not a journal line: an objective recurrence cites "
                              "one line of `harness lessons journal` as journal:<ts> <provider> <session> "
                              "<kind> <site> <guard_id> <repo>" % ln[2:])
    if not jdir or not journal_files(jdir):
        raise LessonError("--recurred with journal evidence needs the journal, but %s has no .log files; "
                          "note the recurrence without a journal: ref (it stays subjective)" % (jdir or "the journal dir"))
    have = {(j.ts, j.provider, j.session, j.kind, j.site, j.guard_id, j.repo) for j in journal_lines(jdir)}
    for ln in lines:
        if journal_ref_fields(ln) not in have:
            raise LessonError("--recurred evidence %r names no line of the journal in %s; copy the line "
                              "from <journal dir>/<date>.log (its tabs as spaces)" % (ln[2:], jdir))
    return list(lines)


def confirm(d: str, rec: Lesson, date: Optional[str] = None) -> None:
    if rec.status not in ("candidate", "recurring"):
        raise LessonError("%s is %s; only a candidate or recurring lesson can be confirmed" % (rec.id, rec.status))
    rec.fm["status"] = "confirmed"
    rec.history(norm_date(date), "confirmed")
    save(d, rec)


def retire(d: str, rec: Lesson, reason: str = "", date: Optional[str] = None) -> None:
    if rec.status == "retired":
        raise LessonError("%s is already retired" % rec.id)
    reason = check_text("--reason", reason, CAP_NOTE)
    rec.fm["status"] = "retired"
    rec.history(norm_date(date), "retired" + (": %s" % reason if reason else ""))
    save(d, rec)


def is_stale(rec: Lesson, now: str, max_age: int) -> bool:
    return days_between(rec.fm["updated"], now[:10]) > max_age


# ----------------------------------------------------------------- index

def index_text(lessons: Sequence[Lesson], now: str, max_age: int, index_max: int, max_candidates: int) -> str:
    from . import taxonomy as T

    live = [r for r in lessons if r.status != "retired"]
    counts = OrderedDict((s, 0) for s in STATUSES)
    for r in lessons:
        counts[r.status] += 1
    out = [INDEX_BANNER, "# Lessons index", "",
           "%d open lesson(s): %s; %d retired (not listed). Domain `base` applies everywhere." % (
               len(live), ", ".join("%d %s" % (counts[s], s) for s in STATUSES if s != "retired"), counts["retired"]),
           "Line: id · status · uses/helped/recurred · ready|stale (no update in %d days) · situation." % max_age]
    listed = 0
    unlisted = 0
    for domain in T.FACETS["domain"]:
        rows = [r for r in live if r.fm["domain"] == domain]
        if not rows:
            continue
        settled = sorted((r for r in rows if r.status != "candidate"), key=lambda r: (STATUS_RANK[r.status], r.id))
        cands = sorted((r for r in rows if r.status == "candidate"), key=lambda r: r.id)
        cands = sorted(cands, key=lambda r: r.fm["updated"], reverse=True)
        shown_c = cands[:max_candidates]
        more_c = len(cands) - len(shown_c)
        body: List[str] = []
        cut = 0
        for r in settled + shown_c:
            if listed >= index_max:
                unlisted += 1
                cut += 1
                continue
            listed += 1
            body.append("- %s · %s · %d/%d/%d · %s · %s" % (
                r.id, r.status, r.fm["uses"], r.fm["helped"], r.fm["recurred"],
                "stale" if is_stale(r, now, max_age) else "ready", r.situation))
        if not body and cut:
            unlisted += more_c   # the overall cap emptied the domain: its hidden candidates count too
            continue
        if more_c:
            body.append("- %d more candidate(s): `harness lessons list --domain %s --status candidate`" % (more_c, domain))
        out += ["", "### %s" % domain, ""] + body
    if unlisted:
        out += ["", "%d more lesson(s) not listed (lessons.index_max = %d): `harness lessons list`" % (unlisted, index_max)]
    return "\n".join(out) + "\n"


# ----------------------------------------------------------------- journal

class JLine:
    __slots__ = ("ts", "provider", "session", "kind", "site", "guard_id", "repo")

    def __init__(self, fields: Sequence[str]):
        (self.ts, self.provider, self.session, self.kind, self.site, self.guard_id, self.repo) = fields

    @property
    def citable(self) -> str:
        """The line as `note --evidence journal:<this>` accepts it: the seven fields, single spaces."""
        return " ".join((self.ts, self.provider, self.session, self.kind, self.site, self.guard_id, self.repo))

    @property
    def date(self) -> str:
        return self.ts[:10]

    @property
    def section(self) -> str:
        return self.site.split(":", 1)[0] if self.site != "-" else "-"


def journal_files(jdir: Optional[str] = None) -> List[str]:
    d = journal_dir() if jdir is None else jdir
    return sorted(glob.glob(os.path.join(d, "*.log"))) if d else []


def journal_lines(jdir: Optional[str] = None) -> List[JLine]:
    """Every well-formed line of every journal file, in file then line order (malformed lines skipped)."""
    out: List[JLine] = []
    for path in journal_files(jdir):
        for raw in (read_text(path) or "").splitlines():
            fields = raw.split("\t")
            if len(fields) != 7 or not re.match(_TS, fields[0]) or fields[3] not in JOURNAL_KINDS:
                continue
            out.append(JLine(fields))
    return out


def current_session() -> Optional[str]:
    text = (read_text(os.path.join(retro_dir(), "current")) or "").strip()
    return text if re.match(r"^[A-Za-z0-9._-]{1,64}$", text) else None


def review_state(lines: Sequence[JLine], session: str, thresholds: Dict[str, int]) -> Dict[str, Any]:
    mine = [ln for ln in lines if ln.session == session]
    counts = OrderedDict((k, 0) for k in JOURNAL_KINDS)
    for ln in mine:
        counts[ln.kind] += 1
    fired = []
    for name, kind, key in CRITERIA:
        t = int(thresholds.get(key, 0) or 0)
        if t > 0 and counts[kind] >= t:
            fired.append(OrderedDict([("criterion", name), ("kind", kind), ("count", counts[kind]),
                                      ("threshold", t), ("key", key)]))
    return OrderedDict([("due", bool(fired)), ("session", session), ("counts", counts), ("fired", fired),
                        ("lines", mine)])


# ----------------------------------------------------------------- guard sites

class GuardMap:
    """The current guard's id, sections and the taxonomy domain of each section function."""

    def __init__(self, hub: Any):
        from . import render as R
        from . import taxonomy as T

        self.guard_id: Optional[str] = None
        self.files: Dict[str, str] = {}    # section function -> section file (current guard)
        self.domains: Dict[str, str] = {}  # section function -> domain (every known bundle)
        if hub is None:
            return
        for b in sorted(hub.bundles.values(), key=lambda x: x.name):
            doms = {c.key: c.domain for c in T.components(b) if c.kind == "guard"}
            for rel in b.guard_rules():
                base = os.path.basename(rel)
                stem = base[:-3] if base.endswith(".sh") else base
                self.domains[R.section_function(base, b.name)] = doms.get("guard.d/%s" % stem) or ""
        active = list(hub.active_bundles)
        engine = R.find_guard_engine(active)
        if engine is None:
            return
        try:
            sections = R.guard_sections(active)
            self.guard_id = sha256_bytes(R.build_guard_from_sections(engine, sections))[:12]
        except Exception:
            return
        for base, bname, full in sections:
            self.files[R.section_function(base, bname)] = full

    def status(self, ln: JLine) -> str:
        if ln.site == "-":
            return "-"
        return "current" if self.guard_id and ln.guard_id == self.guard_id else "stale"

    def text(self, ln: JLine) -> str:
        """The static source line a current-guard site points at, else '' ."""
        if self.status(ln) != "current":
            return ""
        fn, _sep, num = ln.site.partition(":")
        path = self.files.get(fn)
        if not path or not num.isdigit():
            return ""
        src = (read_text(path) or "").split("\n")
        n = int(num)
        if n < 1 or n > len(src):
            return ""
        return one_line(src[n - 1])[:160]


def sensor_section(ref: str) -> Optional[str]:
    """``core/guard.d/30-git`` -> ``guard_section_core_30_git``; None for other kinds."""
    from . import render as R

    parts = ref.split("/")
    if len(parts) != 3 or parts[1] != "guard.d":
        return None
    return R.section_function(parts[2] + ".sh", parts[0])


# ----------------------------------------------------------------- stats

def _rate(n: int, sessions: int) -> str:
    return "%.2f" % (float(n) / sessions) if sessions else "-"


def stats_rows(lessons: Sequence[Lesson], lines: Sequence[JLine], gmap: GuardMap,
               since: Optional[str] = None) -> List["OrderedDict[str, Any]"]:
    """Per lesson, two windows (before / after its ``created`` date): sessions, then asks,
    denies and corrections per session in the lesson's scope (its guard section when the
    sensor is a guard section, else guard sections of its domain; corrections are never
    site-attributed, so they count every session of the window), plus its counters."""
    if since:
        lines = [ln for ln in lines if ln.date >= since[:10]]
    rows = []
    for r in sorted(lessons, key=lambda x: x.id):
        if r.status == "retired":
            continue
        sec = sensor_section(r.fm["sensor_ref"])
        scope = ("site %s" % sec) if sec else ("domain %s" % r.fm["domain"])

        def in_scope(ln: JLine) -> bool:
            if ln.section == "-":
                return False
            if sec:
                return ln.section == sec
            return gmap.domains.get(ln.section, "") == r.fm["domain"]

        for window in ("before", "after"):
            win = [ln for ln in lines if (ln.date < r.fm["created"]) == (window == "before")]
            sessions = len({ln.session for ln in win if ln.session != "-"})
            asks = sum(1 for ln in win if ln.kind == "guard-ask" and in_scope(ln))
            denies = sum(1 for ln in win if ln.kind == "guard-deny" and in_scope(ln))
            corr = sum(1 for ln in win if ln.kind == "correction")
            rows.append(OrderedDict([
                ("lesson", r.id), ("status", r.status), ("scope", scope), ("window", window),
                ("sessions", sessions), ("asks", asks), ("denies", denies), ("corrections", corr),
                ("asks_per_session", _rate(asks, sessions)), ("denies_per_session", _rate(denies, sessions)),
                ("corrections_per_session", _rate(corr, sessions)),
                ("uses", r.fm["uses"]), ("helped", r.fm["helped"]), ("recurred", r.fm["recurred"]),
                ("recurred_objective", r.fm["recurred_objective"])]))
    return rows


STATS_HEAD = ["lesson", "status", "scope", "window", "sessions", "asks/s", "denies/s", "corr/s",
              "uses", "helped", "recurred"]


def stats_table(rows: Sequence[Dict[str, Any]]) -> List[List[str]]:
    table = [list(STATS_HEAD)]
    for r in rows:
        table.append([r["lesson"], r["status"], r["scope"], r["window"], str(r["sessions"]),
                      r["asks_per_session"], r["denies_per_session"], r["corrections_per_session"],
                      str(r["uses"]), str(r["helped"]), "%d (%d obj)" % (r["recurred"], r["recurred_objective"])])
    return table


# ----------------------------------------------------------------- propose

def proposable(rec: Lesson, promote_after: int) -> Optional[str]:
    """None when ``propose`` accepts ``rec``, else the reason it refuses."""
    st = rec.status
    if st == "confirmed":
        return None
    if st == "recurring":
        if rec.fm["recurred_objective"] >= promote_after:
            return None
        return ("%s is recurring with %d objective recurrence(s) < lessons.promote_after %d; only "
                "journal-backed recurrences promote" % (rec.id, rec.fm["recurred_objective"], promote_after))
    if st == "candidate":
        return ("%s is a candidate (unconfirmed); a human confirms it first (`harness lessons confirm %s`), "
                "or it must recur %d time(s) with journal evidence" % (rec.id, rec.id, promote_after))
    if st == "proposed":
        return "%s is already proposed; the issue exists or was drafted" % rec.id
    return "%s is retired" % rec.id


def redact_repos(text: str, rec: Lesson) -> str:
    names = set()
    for ln in rec.sections["Evidence"]:
        if ln.startswith("- journal: "):
            fields = ln[len("- journal: "):].split()
            if len(fields) == 7 and fields[6] != "-":
                names.add(fields[6])
    for name in sorted(names, key=lambda n: (-len(n), n)):
        # never inside a path or id: a repository named core leaves core/guard.d/... alone
        text = re.sub(r"(?<![A-Za-z0-9._/-])%s(?![A-Za-z0-9_/-])" % re.escape(name), "<repo>", text)
    return text


def _sq(text: str) -> str:
    return "'" + text.replace("'", "'\\''") + "'"


def propose_files(rec: Lesson, tracker: str, repo: Optional[str], label: str, keep_repos: bool,
                  diff: Optional[str]) -> "OrderedDict[str, str]":
    title = "Lesson %s: %s" % (rec.id, rec.situation)
    if len(title) > 80:
        title = title[:77].rstrip() + "..."
    fm = rec.fm
    body = [
        "Lesson `%s` from a private lessons library, drafted by `harness lessons propose`. It is an "
        "agent-written observation backed by the evidence below; a human decides whether the guide "
        "and sensor change." % rec.id, "",
        "- scope: %s, domain: %s, status: %s" % (fm["scope"], fm["domain"], fm["status"]),
        "- guide: `%s`" % fm["guide_ref"], "- sensor: `%s`" % fm["sensor_ref"],
        "- bundles: %s" % (", ".join("`%s`" % b for b in fm["bundles"]) or "-"),
        "- counters: uses %d, helped %d, recurred %d (%d backed by the guard journal)" % (
            fm["uses"], fm["helped"], fm["recurred"], fm["recurred_objective"]),
        "", "## Situation", "", rec.situation, "", "## Lesson", "",
        " ".join(rec.sections["Lesson"]) or "(none recorded)", "", "## Evidence", ""]
    body += rec.sections["Evidence"]
    body += ["", "## Candidate edit", ""]
    if diff:
        fence = "`" * max(3, max([len(r) for r in re.findall(r"`+", diff)] or [0]) + 1)
        body += [fence + "diff", diff.rstrip("\n"), fence]
    else:
        body.append("(none: the issue asks for the guide and sensor change)")
    body += ["", "## Validation", ""]
    body += rec.sections["Validation"] or ["not validated (`harness lessons validate %s`)" % rec.id]
    body += ["", "Paired guide and sensor: the change lands as one PR with its guard rows or test, "
             "and a human merges it."]
    text = "\n".join(body) + "\n"
    if not keep_repos:
        text = redact_repos(text, rec)
        title = redact_repos(title, rec)
    for where, t in (("title", title), ("body", text)):
        m = CLOSING_RE.search(t)
        if m:
            raise LessonError("propose: the %s contains a closing keyword (%r): issue state is human-only; "
                              "reword the lesson so it mentions the issue without closing it" % (where, m.group(0)))
    if ISSUE_REF_RE.search(title):
        raise LessonError("propose: the title contains an issue reference (#N); mention issues in the body only")
    files: "OrderedDict[str, str]" = OrderedDict()
    files["body.md"] = text
    head = ["#!/bin/sh",
            "# Written by `harness lessons propose %s`; the harness never runs it." % rec.id,
            "# Read preview.md first, then run it yourself: sh create.sh"]
    if tracker == "github-issues":
        cmd = "gh issue create -R %s -t %s -F body.md -l %s" % (repo, _sq(title), _sq(label))
        script = head + ["set -eu", 'cd "$(dirname "$0")"', cmd]
        where = "GitHub Issues, %s" % repo
    else:
        cmd = "/create-ticket %s (description: body.md)" % title
        script = head + ["# Jira tracker: paste this line into an agent session; /create-ticket drafts the",
                         "# ticket with the agent-drafted label and stops.", "# " + cmd,
                         "echo 'Jira tracker: run the /create-ticket line in create.sh in an agent session.'"]
        where = "Jira (via /create-ticket)"
    files["create.sh"] = "\n".join(script) + "\n"
    files["preview.md"] = "\n".join([
        "# Proposal preview: %s" % rec.id, "",
        "- tracker: %s" % where, "- title: %s" % title, "- label: %s" % label,
        "- command (in create.sh, never run by the harness): `%s`" % cmd,
        "- repository names: %s" % ("kept (--keep-repos)" if keep_repos else "replaced by <repo>"),
        "", "---", "", text.rstrip("\n")]) + "\n"
    return files


def private_id_hits(home: str, paths: Sequence[str]) -> Optional[str]:
    """The private-identifier gate's findings for ``paths`` (``--ci`` form: private text is never
    echoed), or None when it is clean or the hub has no gate."""
    gate = os.path.join(home, "tools", "gate", "private-ids.sh")
    if not os.path.isfile(gate):
        return None
    env = dict(os.environ)
    env["HARNESS_HOME"] = home
    rc, out = _run_step(["bash", gate, "--ci", "--files"] + [os.path.abspath(p) for p in paths], home, env, 120,
                        whole=True)
    if rc == 0:
        return None
    return out.strip() or "gate exited %d" % rc


def hub_tracker(home: str) -> Tuple[Optional[str], Optional[str]]:
    """(tracker, owner/repo) of the hub checkout: ``.harness.toml [repo] tracker`` and the
    GitHub owner/repo parsed from ``origin`` (the URL itself is never printed)."""
    from . import repo as Rp
    from .util import run_argv

    tracker = None
    try:
        decl = Rp.load(home)
        tracker = (decl.data.get("repo") or {}).get("tracker")
    except Exception:
        tracker = None
    rc, out, _err = run_argv(["git", "-C", home, "remote", "get-url", "origin"], timeout=10)
    slug = None
    if rc == 0:
        m = re.search(r"github\.com[:/]([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(\.git)?/?$", out.strip())
        if m:
            slug = "%s/%s" % (m.group(1), m.group(2))
    return tracker, slug


# ----------------------------------------------------------------- validate

def _run_step(argv: Sequence[str], cwd: str, env: Optional[Dict[str, str]], timeout: int = 1800,
              whole: bool = False) -> Tuple[int, str]:
    """Run one step in its own process group (killed as a group on timeout); return (rc, last
    non-empty output line), or the whole output with ``whole``."""
    import signal

    try:
        proc = subprocess.Popen(list(argv), cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, start_new_session=True)
    except FileNotFoundError:
        return 127, "%s: not found" % argv[0]
    try:
        out, _err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            proc.kill()
        proc.communicate()
        return 124, "timed out after %ds" % timeout
    text = out.decode("utf-8", "replace")
    if whole:
        return proc.returncode, text
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return proc.returncode, (lines[-1].strip() if lines else "")


VALIDATE_ENV_KEEP = ("PATH", "LANG", "TMPDIR", "TERM")


def validate_env(tmp: str, hub: str, build: str, source: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """The environment of every validate step: an allow-list (PATH, LANG, LC_*, TMPDIR, TERM)
    plus isolation values pointing into ``tmp``. Tokens (GH_TOKEN, GITLAB_TOKEN, ...), every
    HARNESS_* and GIT_* variable and the user's git and XDG configuration are never inherited."""
    src = os.environ if source is None else source
    env = {k: v for k, v in src.items() if k in VALIDATE_ENV_KEEP or k.startswith("LC_")}
    env.update({
        "HOME": os.path.join(tmp, "home"), "XDG_STATE_HOME": os.path.join(tmp, "state"),
        "XDG_CACHE_HOME": os.path.join(tmp, "cache"), "XDG_DATA_HOME": os.path.join(tmp, "data"),
        "XDG_CONFIG_HOME": os.path.join(tmp, "config"),
        "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CEILING_DIRECTORIES": tmp,
        "HARNESS_HOME": hub, "HARNESS_BUILD_DIR": build,
        "HARNESS_CONFIG": os.path.join(hub, "tests", "fixtures", "harness.ci.toml"),
        "PYTHONPATH": os.path.join(hub, "lib")})
    return env


def validate_edit(home: str, diff_path: str, quick: bool = False, full: bool = False,
                  log: Any = print) -> Tuple[bool, List[Tuple[str, bool, str]], str]:
    """Copy ``git archive HEAD`` of the hub, apply the diff, run the hub's own sensors.

    Returns (passed, [(step, ok, summary)], guard id of the rendered copy or '').
    """
    import sys

    diff = read_text(diff_path)
    if diff is None:
        raise LessonError("validate: patch file not found: %s" % diff_path)
    files = check_diff(diff)
    tmp = tempfile.mkdtemp(prefix="harness-lessons-validate-")
    steps: List[Tuple[str, bool, str]] = []
    gid = ""
    try:
        hub = os.path.join(tmp, "hub")
        os.makedirs(hub)
        tar = os.path.join(tmp, "hub.tar")
        build = os.path.join(tmp, "build")
        for sub in ("build", "home", "state", "cache", "data", "config"):
            os.makedirs(os.path.join(tmp, sub))
        env = validate_env(tmp, hub, build)
        rc, _out = _run_step(["git", "-C", home, "archive", "--format=tar", "-o", tar, "HEAD"], tmp, env, 300)
        if rc != 0:
            raise LessonError("validate: `git archive HEAD` failed in %s (the hub must be a git checkout)" % home)
        with tarfile.open(tar) as tf:
            # our own HEAD, written by git archive; the data filter where python has it
            if hasattr(tarfile, "data_filter"):
                tf.extractall(hub, filter="data")
            else:
                tf.extractall(hub)
        # git's own reading of the patch: every path it would touch must be under bundles/
        for p in applied_paths(diff_path, hub, env):
            why = path_problem(p)
            if why:
                raise LessonError("validate: git apply --numstat --summary lists %s" % why)
        rc, out = _run_step(["git", "apply", "--whitespace=nowarn", os.path.abspath(diff_path)], hub, env, 120)
        steps.append(("apply", rc == 0, out or ("applied" if rc == 0 else "failed")))
        if rc != 0:
            return False, steps, gid
        py = sys.executable or "python3"
        plan: List[Tuple[str, List[str]]] = [("lint", [py, "-m", "harness", "lint"])]
        if full:
            plan.append(("test all", [py, "-m", "harness", "test", "all"]))
        else:
            plan.append(("test guard", [py, "-m", "harness", "test", "guard"]))
            if not quick:
                for b in touched_bundles(files):
                    if os.path.isdir(os.path.join(hub, "bundles", b)):
                        plan.append(("test %s" % b, [py, "-m", "harness", "test", b]))
        out_dir = os.path.join(tmp, "out")
        plan.append(("render", [py, "-m", "harness", "render", "--out", out_dir]))
        for name, argv in plan:
            log("validate: %s ..." % name)
            rc, summary = _run_step(argv, hub, env)
            steps.append((name, rc == 0, summary))
        # glob's * skips dot directories (.claude, .gemini): walk instead
        guards = sorted(os.path.join(dp, "guard-bash.sh") for dp, _dn, fns in os.walk(out_dir)
                        if "guard-bash.sh" in fns)
        if guards:
            with open(guards[0], "rb") as fh:
                gid = sha256_bytes(fh.read())[:12]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return all(ok for _n, ok, _s in steps), steps, gid


def validation_line(ts: str, passed: bool, steps: Sequence[Tuple[str, bool, str]], gid: str) -> str:
    parts = ["%s %s" % (n, "ok" if ok else "FAIL") for n, ok, _s in steps]
    return "- %s %s: %s; guard %s" % (ts, "pass" if passed else "fail", ", ".join(parts), gid or "-")


# ================================================================= CLI


def _hub(ctx: Any) -> Any:
    return ctx.hub(require_config=False)


def _dir(hub: Any, create: bool = False) -> str:
    d = lessons_dir(hub)
    check_dir(d, hub.home)
    if create:
        os.makedirs(d, mode=0o700, exist_ok=True)
    return d


def _print_table(rows: List[List[str]]) -> None:
    from .status import format_table

    print(format_table(rows), end="")


def run(ctx: Any, ns: Any) -> int:
    action = getattr(ns, "action", None)
    if not action:
        raise HarnessError("usage: harness lessons list|show|new|note|confirm|retire|review|stats|validate|"
                           "propose|index|journal (harness lessons --help)", 2)
    if action == "review":
        import sys

        try:
            hub = _hub(ctx)
        except HarnessError as exc:
            print("harness: lessons review: %s" % exc, file=sys.stderr)
            return 4
    else:
        hub = _hub(ctx)
    fn = globals()["cmd_" + action]
    return int(fn(ctx, ns, hub) or 0)


def cmd_list(ctx: Any, ns: Any, hub: Any) -> int:
    d = _dir(hub)
    want = ns.status or "open"
    now = norm_ts(None)
    max_age = int(cfg(hub, "lessons.max_age_days"))
    import sys

    rows = []
    bad: List[Tuple[str, str]] = []
    for r in load_all(d, bad):
        if want == "open" and r.status == "retired":
            continue
        if want not in ("open", "all") and r.status != want:
            continue
        if ns.domain and r.fm["domain"] != ns.domain:
            continue
        stale = is_stale(r, now, max_age)
        if ns.stale and not stale:
            continue
        rows.append((r, stale))
    for lid, why in bad:
        print("harness: unreadable lesson %s: %s" % (lid, why), file=sys.stderr)
    if ctx.json:
        out = []
        for r, stale in rows:
            item = r.to_dict()
            item["stale"] = stale
            out.append(item)
        out += [OrderedDict([("id", lid), ("status", "unreadable"), ("reason", why)]) for lid, why in bad]
        print(json.dumps(out, indent=2))
        return 0
    if not rows and not bad:
        print("no lessons (%s; status %s)" % (d, want))
        return 0
    table = [["id", "status", "scope", "uses/helped/recurred", "updated", "fresh", "situation"]]
    for r, stale in rows:
        sit = r.situation if len(r.situation) <= 60 else r.situation[:57] + "..."
        table.append([r.id, r.status, r.fm["scope"], "%d/%d/%d" % (r.fm["uses"], r.fm["helped"], r.fm["recurred"]),
                      r.fm["updated"], "stale" if stale else "ready", sit])
    for lid, _why in bad:
        table.append([lid, "unreadable", "-", "-", "-", "-", "(see stderr; fix or delete the file)"])
    _print_table(table)
    return 0


def cmd_show(ctx: Any, ns: Any, hub: Any) -> int:
    d = _dir(hub)
    rec = load(d, ns.id)
    if ctx.json:
        print(json.dumps(rec.to_dict(), indent=2))
    else:
        print(dump(rec), end="")
    return 0


def cmd_new(ctx: Any, ns: Any, hub: Any) -> int:
    d = _dir(hub, create=True)
    evidence = [e for group in (ns.evidence or []) for e in group]
    bundles: List[str] = []
    for v in ns.bundles or []:
        bundles += [x.strip() for x in v.split(",") if x.strip()]
    rec = new_lesson(d, ns.domain, ns.scope, ns.situation, ns.guide_ref, ns.sensor_ref, evidence,
                     bundles=bundles, source=ns.source, lesson=ns.lesson or "", edit=ns.edit, date=ns.date)
    print(rec.id)
    return 0


def cmd_note(ctx: Any, ns: Any, hub: Any) -> int:
    d = _dir(hub)
    rec = load(d, ns.id)
    words = note(d, rec, int(cfg(hub, "lessons.promote_after")), used=ns.used, helped=ns.helped,
                 recurred=ns.recurred, evidence=ns.evidence or [], text=ns.note or "", date=ns.date)
    print("%s: %s (status %s; uses %d, helped %d, recurred %d, objective %d)" % (
        rec.id, ", ".join(words) or "noted", rec.status, rec.fm["uses"], rec.fm["helped"],
        rec.fm["recurred"], rec.fm["recurred_objective"]))
    return 0


def cmd_confirm(ctx: Any, ns: Any, hub: Any) -> int:
    d = _dir(hub)
    rec = load(d, ns.id)
    confirm(d, rec, ns.date)
    print("%s: confirmed" % rec.id)
    return 0


def cmd_retire(ctx: Any, ns: Any, hub: Any) -> int:
    d = _dir(hub)
    rec = load(d, ns.id)
    retire(d, rec, ns.reason or "", ns.date)
    print("%s: retired" % rec.id)
    return 0


def cmd_review(ctx: Any, ns: Any, hub: Any) -> int:
    """rc 0 due, 1 not due, 3 nothing to judge, 4 an error (so 1 only ever means "not due")."""
    import sys

    try:
        return _review(ctx, ns, hub)
    except (HarnessError, OSError, ValueError) as exc:
        print("harness: lessons review: %s" % exc, file=sys.stderr)
        return 4


def _review(ctx: Any, ns: Any, hub: Any) -> int:
    jdir = journal_dir()
    session = ns.session or current_session()
    thresholds = {key: int(cfg(hub, key)) for _n, _k, key in CRITERIA}
    reason = None
    lines: List[JLine] = []
    if not jdir:
        reason = "no journal: the journal directory is relative or unset (HOME and XDG_STATE_HOME empty)"
    elif not journal_files(jdir):
        reason = "no journal: %s has no .log files (lessons.journal is off, or nothing was asked or denied yet)" % jdir
    elif not session:
        reason = "no session: pass --session S, or let a journal line write %s" % os.path.join(retro_dir(), "current")
    else:
        lines = journal_lines(jdir)
    state = review_state(lines, session or "-", thresholds)
    if reason is None and not state["lines"]:
        reason = "no signals: the journal has no line for session %s" % session
    if ctx.json:
        out = OrderedDict([("due", state["due"] if reason is None else False), ("session", session),
                           ("counts", state["counts"]), ("fired", [f["criterion"] for f in state["fired"]])])
        if reason:
            out["reason"] = reason
        if ns.explain:
            out["lines"] = [OrderedDict([("ts", ln.ts), ("kind", ln.kind), ("site", ln.site), ("line", ln.citable)])
                            for ln in state["lines"]]
        print(json.dumps(out, indent=2))
        return 3 if reason else (0 if state["due"] else 1)
    if reason:
        print("due: no (%s)" % reason)
        return 3
    print("due: %s" % ("yes" if state["due"] else "no"))
    print("session: %s" % session)
    print("counts: %s" % ", ".join("%s %d" % (k, v) for k, v in state["counts"].items()))
    if state["fired"]:
        for f in state["fired"]:
            print("fired: %s (%s %d >= %s %d)" % (f["criterion"], f["kind"], f["count"], f["key"], f["threshold"]))
    else:
        print("fired: none (thresholds: %s; 0 = off)" % ", ".join(
            "%s %d" % (key, thresholds[key]) for _n, _k, key in CRITERIA))
    if ns.explain:
        for ln in state["lines"]:
            print("  %s" % ln.citable)   # citable as --evidence journal:<line>
    return 0 if state["due"] else 1


def cmd_stats(ctx: Any, ns: Any, hub: Any) -> int:
    d = _dir(hub)
    lessons = [r for r in load_all(d) if not ns.domain or r.fm["domain"] == ns.domain]
    lines = journal_lines()
    since = norm_ts(ns.since) if ns.since else None
    rows = stats_rows(lessons, lines, GuardMap(hub), since)
    if ctx.json:
        print(json.dumps(rows, indent=2))
        return 0
    used = [ln for ln in lines if not since or ln.date >= since[:10]]
    print("journal: %d line(s), %d session(s)%s; lessons: %d" % (
        len(used), len({ln.session for ln in used if ln.session != "-"}),
        " since %s" % since[:10] if since else "", len({r["lesson"] for r in rows})))
    if rows:
        _print_table(stats_table(rows))
    return 0


def cmd_validate(ctx: Any, ns: Any, hub: Any) -> int:
    d = _dir(hub)
    recs = [load(d, ns.id)] if ns.id else [r for r in load_all(d) if r.fm["candidate_edit"] and r.status != "retired"]
    if not recs:
        print("validate: no lesson with a candidate edit")
        return 1
    ts = norm_ts(ns.now)
    rc = 0
    for rec in recs:
        if not rec.fm["candidate_edit"]:
            rec.fm["validation"] = "none"
            print("%s: validation none (no candidate edit; record one with `harness lessons new --edit FILE.diff`)" % rec.id)
            rc = 1
            continue
        passed, steps, gid = validate_edit(hub.home, os.path.join(d, rec.fm["candidate_edit"]),
                                           quick=ns.quick, full=ns.full)
        rec.fm["validation"] = "pass" if passed else "fail"
        rec.fm["validated_at"] = ts
        rec.fm["validated_guard_id"] = gid
        rec.sections["Validation"] = [validation_line(ts, passed, steps, gid)]
        rec.history(ts[:10], "validated: %s" % rec.fm["validation"])
        save(d, rec)
        for name, ok, summary in steps:
            print("%s  %-12s %s" % ("PASS" if ok else "FAIL", name, summary))
        print("%s: validation %s" % (rec.id, rec.fm["validation"]))
        if not passed:
            rc = 1
    return rc


def cmd_propose(ctx: Any, ns: Any, hub: Any) -> int:
    repo = ns.repo
    if repo and not OWNER_REPO_RE.match(repo):
        raise HarnessError("--repo %s: expected OWNER/REPO" % repo, 2)
    d = _dir(hub)
    rec = load(d, ns.id)
    why = proposable(rec, int(cfg(hub, "lessons.promote_after")))
    if why:
        raise LessonError("propose refuses: %s" % why)
    tracker, slug = hub_tracker(hub.home)
    if repo:
        tracker = "github-issues"
    elif tracker == "jira":
        repo = None
    else:
        if not slug:
            raise LessonError("propose: the hub's tracker repository is unknown; pass --repo OWNER/REPO")
        tracker, repo = "github-issues", slug
    diff = read_text(os.path.join(d, rec.fm["candidate_edit"])) if rec.fm["candidate_edit"] else None
    label = str(cfg(hub, "core.agent_labels.drafted"))
    files = propose_files(rec, tracker, repo, label, ns.keep_repos, diff)
    out = os.path.abspath(os.path.expanduser(ns.out))
    check_dir(out, hub.home, what="--out")
    written = []
    for name, text in files.items():
        path = os.path.join(out, name)
        atomic_write(path, text.encode("utf-8"), mode=0o644)
        written.append(path)
    hits = private_id_hits(hub.home, written)
    if hits is not None:
        for path in written:
            try:
                os.unlink(path)
            except OSError:
                pass
        raise LessonError("propose: tools/gate/private-ids.sh flags the draft (files removed); reword the "
                          "lesson or its evidence, or retire it:\n%s" % hits)
    print("wrote %s (%s); the harness never runs create.sh: read preview.md, then `sh %s`" % (
        ", ".join(files), out, os.path.join(out, "create.sh")))
    if ns.mark:
        rec.fm["status"] = "proposed"
        rec.history(norm_date(ns.date), "proposed")
        save(d, rec)
        print("%s: proposed" % rec.id)
    return 0


def cmd_index(ctx: Any, ns: Any, hub: Any) -> int:
    d = _dir(hub, create=True)
    now = norm_ts(ns.now)
    max_age = int(cfg(hub, "lessons.max_age_days"))
    lessons = load_all(d)
    if ns.prune:
        for r in lessons:
            if r.status == "candidate" and is_stale(r, now, max_age):
                r.fm["status"] = "retired"
                r.history(now[:10], "retired: stale (no update in %d days)" % max_age)
                save(d, r)
                print("%s: retired (stale)" % r.id)
    text = index_text(lessons, now, max_age, int(cfg(hub, "lessons.index_max")),
                      int(cfg(hub, "lessons.index_max_candidates")))
    path = os.path.join(d, INDEX_NAME)
    atomic_write(path, text.encode("utf-8"), mode=0o600)
    print("wrote %s (%d lesson(s))" % (path, len([r for r in lessons if r.status != "retired"])))
    return 0


def read_last(path: str) -> Optional[Tuple[str, int]]:
    """``retro/last``: ``TS<TAB>N`` = acknowledged through the first N lines stamped TS."""
    parts = (read_text(path) or "").strip().split("\t")
    if not parts or not re.match(_TS, parts[0]):
        return None
    n = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    return parts[0], n


def after_mark(lines: Sequence[JLine], since: Optional[str], skip: int = 0) -> List[JLine]:
    """Lines at or after ``since``, minus the first ``skip`` lines stamped exactly ``since``
    (already acknowledged): nothing in the same second is lost, nothing is shown twice."""
    if not since:
        return list(lines)
    out = []
    for ln in lines:
        if ln.ts < since:
            continue
        if ln.ts == since and skip > 0:
            skip -= 1
            continue
        out.append(ln)
    return out


def cmd_journal(ctx: Any, ns: Any, hub: Any) -> int:
    started = now_ts()   # taken before reading: an --ack with nothing shown loses no later line
    rdir = retro_dir()
    if not rdir:
        raise LessonError("the retro directory is relative or unset (HOME and XDG_STATE_HOME empty); "
                          "set HARNESS_RETRO_DIR to an absolute path")
    last_path = os.path.join(rdir, "last")
    since = None
    origin = "all"
    if ns.since:
        since, origin = norm_ts(ns.since), "--since"
    skip = 0
    if not ns.since and not ns.all:
        mark = read_last(last_path)
        if mark:
            (since, skip), origin = mark, "retro/last"
    every = journal_lines()
    lines = after_mark(every, since, skip)
    gmap = GuardMap(hub)
    groups: "OrderedDict[Tuple[str, str, str], Dict[str, Any]]" = OrderedDict()
    for ln in lines:
        key = (ln.kind, ln.site, gmap.status(ln))
        g = groups.get(key)
        if g is None:
            g = groups[key] = {"kind": ln.kind, "site": ln.site, "status": key[2], "count": 0,
                               "sessions": set(), "first": ln.ts, "last": ln.ts, "text": gmap.text(ln),
                               "example": ln.citable}
        g["count"] += 1
        g["sessions"].add(ln.session)
        g["first"] = min(g["first"], ln.ts)
        if ln.ts >= g["last"]:   # the newest line; on a tie the later one in file order
            g["example"] = ln.citable
        g["last"] = max(g["last"], ln.ts)
    ordered = sorted(groups.values(), key=lambda g: (JOURNAL_KINDS.index(g["kind"]), g["site"], g["status"]))
    if ctx.json:
        print(json.dumps(OrderedDict([
            ("since", since), ("from", origin), ("guard_id", gmap.guard_id), ("lines", len(lines)),
            ("groups", [OrderedDict([("kind", g["kind"]), ("site", g["site"]), ("status", g["status"]),
                                     ("count", g["count"]), ("sessions", len(g["sessions"])),
                                     ("first", g["first"]), ("last", g["last"]), ("text", g["text"]),
                                     ("example", g["example"])])
                        for g in ordered])]), indent=2))
    else:
        print("journal: %d line(s) since %s (%s); current guard %s" % (
            len(lines), since or "the start", origin, gmap.guard_id or "-"))
        if ordered:
            table = [["count", "sessions", "kind", "site", "status", "text"]]
            for g in ordered:
                table.append([str(g["count"]), str(len(g["sessions"])), g["kind"], g["site"], g["status"],
                              g["text"] or ("-" if g["status"] != "stale" else "(older guard; line not attributed)")])
            _print_table(table)
    if ns.ack:
        if lines:
            newest = max(ln.ts for ln in lines)
            ack(rdir, newest, sum(1 for ln in every if ln.ts == newest))
        else:
            ack(rdir, started, 0)
        print("acknowledged: %s" % last_path)
        marked = mark_session(rdir, current_session())
        if marked:
            print("session marked: %s" % marked)
    return 0


def mark_session(rdir: str, session: Optional[str]) -> Optional[str]:
    """Write the empty ``<retro dir>/sessions/<sid>`` marker that hooks/stop-retro-nudge.sh
    checks, so a session whose retro already ran is not nudged to run one again. ``-``, ``.``
    and ``..`` (no session) are skipped, as the hook skips them; returns the path or None."""
    if not session or session in ("-", ".", ".."):
        return None
    sdir = os.path.join(rdir, "sessions")
    path = os.path.join(sdir, session)
    try:
        os.makedirs(sdir, mode=0o700, exist_ok=True)
        if not os.path.exists(path):
            fd = os.open(path, os.O_WRONLY | os.O_CREAT, 0o600)
            os.close(fd)
    except OSError:
        return None
    return path


def ack(rdir: str, ts: str, count: int, keep_days: int = 7) -> None:
    os.makedirs(rdir, mode=0o700, exist_ok=True)
    atomic_write(os.path.join(rdir, "last"), ("%s\t%d\n" % (ts, count)).encode("utf-8"), mode=0o600)
    cutoff = time.time() - keep_days * 86400
    for path in glob.glob(os.path.join(rdir, "sessions", "*")):
        try:
            if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                os.unlink(path)
        except OSError:
            pass
