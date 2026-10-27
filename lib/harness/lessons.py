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
_USERINFO = re.compile(r"://[^/\s:@]+:[^/\s@]+@")
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_HEX = re.compile(r"^[0-9a-f]{7,64}$")
_IDENT = re.compile(r"^[a-z][a-z0-9]*([_.-][a-z0-9]+)+$")
CLOSING_RE = re.compile(
    r"\b(close[sd]?|fix(e[sd])?|resolve[sd]?|implement(s|ed)?)\b\s*:?\s+"
    r"(#[0-9]+|[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#[0-9]+|https?://\S+/(issues|pull|merge_requests)/[0-9]+|[A-Z][A-Z0-9_]*-[0-9]+)",
    re.I)
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
        return "contains URL userinfo (a user name and password before @ in a URL); drop the credential part"
    for raw in (text or "").split():
        word = raw.strip("\"'`()[]{}<>,;")
        for part in [word] + word.split("=")[1:]:
            if not part:
                continue
            if not _TOKEN_PREFIX.match(part):
                if _UUID.match(part) or _HEX.match(part):
                    continue   # session ids and git object ids are not secrets
                if _IDENT.match(part) and max(len(s) for s in re.split(r"[_.-]", part)) <= 16:
                    continue   # snake/kebab identifiers (guard_section_core_20_credentials)
                if not looks_like_secret_value(part):
                    continue
            return "contains a token-shaped string (%s...); never record a secret" % part[:4]
    return None


def check_text(field: str, text: str, cap: int) -> str:
    text = one_line(text)
    if len(text) > cap:
        raise LessonError("%s is %d characters; the cap is %d: shorten it" % (field, len(text), cap))
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
    raw = cfg(hub, "lessons.dir") or ""
    return os.path.abspath(os.path.expanduser(raw)) if raw else os.path.join(state_dir(), "lessons")


def journal_dir() -> str:
    return os.environ.get("HARNESS_JOURNAL_DIR") or os.path.join(state_dir(), "journal")


def retro_dir() -> str:
    return os.environ.get("HARNESS_RETRO_DIR") or os.path.join(state_dir(), "retro")


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


def check_dir(path: str, home: str) -> None:
    """Refuse a lessons directory under the hub checkout or inside any git checkout."""
    real = os.path.realpath(path)
    hub = os.path.realpath(home)
    hint = ("lessons stay on this workstation and never enter a repository: set lessons.dir in "
            "harness.toml to a directory outside every git checkout, or leave it empty for the "
            "default %s" % os.path.join(state_dir(), "lessons"))
    if real == hub or real.startswith(hub.rstrip("/") + "/"):
        raise LessonError("lessons.dir %s is under the hub checkout %s; %s" % (path, home, hint))
    top = _git_checkout_of(path)
    if top:
        raise LessonError("lessons.dir %s is inside the git checkout %s; %s" % (path, top, hint))


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
    return parse(text, path)


def load_all(d: str) -> List[Lesson]:
    out = []
    for path in sorted(glob.glob(os.path.join(d, "*.md"))):
        if not ID_RE.match(os.path.basename(path)[:-3]):
            continue
        out.append(parse(read_text(path) or "", path))
    return out


def save(d: str, lesson: Lesson) -> str:
    validate_fm(lesson.fm, lesson.id)
    path = record_path(d, lesson.id)
    atomic_write(path, dump(lesson).encode("utf-8"), mode=0o600)
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

def diff_files(diff: str) -> List[Tuple[str, int, int]]:
    """(path, added, removed) per file of a unified diff; paths without a/ b/ prefixes."""
    files: List[List[Any]] = []
    cur: Optional[List[Any]] = None
    for ln in diff.splitlines():
        if ln.startswith("+++ "):
            p = ln[4:].split("\t")[0].strip()
            if p == "/dev/null":
                p = cur[0] if cur else p
            elif p.startswith("b/"):
                p = p[2:]
            cur = [p, 0, 0]
            files.append(cur)
        elif ln.startswith("--- "):
            continue
        elif cur is not None and ln.startswith("+"):
            cur[1] += 1
        elif cur is not None and ln.startswith("-"):
            cur[2] += 1
    return [(f[0], f[1], f[2]) for f in files]


def check_diff(diff: str) -> List[Tuple[str, int, int]]:
    files = diff_files(diff)
    if not files or "\n@@ " not in "\n" + diff:
        raise LessonError("--edit: not a unified diff (git diff output against the hub root expected)")
    for path, _a, _r in files:
        if not path.startswith("bundles/") or ".." in path.split("/"):
            raise LessonError("--edit: %s is outside bundles/; a candidate edit changes a guide and its "
                              "sensor inside one or more bundles only" % path)
    why = secret_reason(diff)
    if why:
        raise LessonError("--edit %s" % why)
    return files


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
    lid = next_id(d, domain)
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
    rec = Lesson(fm, sections)
    validate_fm(fm, lid)
    if diff is not None:
        atomic_write(os.path.join(d, rel), diff.encode("utf-8"), mode=0o600)
    save(d, rec)
    return rec


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
    lines = ["- " + evidence_line(ref) for ref in evidence]
    objective = recurred and any(ln.startswith("- journal: ") for ln in lines)
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
    added = [ln for ln in lines if ln not in rec.sections["Evidence"]]
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
        for r in settled + shown_c:
            if listed >= index_max:
                unlisted += 1
                continue
            listed += 1
            body.append("- %s · %s · %d/%d/%d · %s · %s" % (
                r.id, r.status, r.fm["uses"], r.fm["helped"], r.fm["recurred"],
                "stale" if is_stale(r, now, max_age) else "ready", r.situation))
        if not body:
            continue   # every lesson of the domain fell under the overall cap
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
    def date(self) -> str:
        return self.ts[:10]

    @property
    def section(self) -> str:
        return self.site.split(":", 1)[0] if self.site != "-" else "-"


def journal_files(jdir: Optional[str] = None) -> List[str]:
    return sorted(glob.glob(os.path.join(jdir or journal_dir(), "*.log")))


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
        text = re.sub(r"(?<![A-Za-z0-9._/-])%s(?![A-Za-z0-9_-])" % re.escape(name), "<repo>", text)
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
        body += ["```diff", diff.rstrip("\n"), "```"]
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

def _run_step(argv: Sequence[str], cwd: str, env: Dict[str, str], timeout: int = 1800) -> Tuple[int, str]:
    try:
        proc = subprocess.run(list(argv), cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              stdin=subprocess.DEVNULL, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, "timed out after %ds" % timeout
    lines = [ln for ln in proc.stdout.decode("utf-8", "replace").splitlines() if ln.strip()]
    return proc.returncode, (lines[-1].strip() if lines else "")


def validate_edit(home: str, diff_path: str, quick: bool = False, full: bool = False,
                  log: Any = print) -> Tuple[bool, List[Tuple[str, bool, str]], str]:
    """Copy ``git archive HEAD`` of the hub, apply the diff, run the hub's own sensors.

    Returns (passed, [(step, ok, summary)], guard id of the rendered copy or '').
    """
    import sys

    from .test import suite_env

    diff = read_text(diff_path) or ""
    files = check_diff(diff)
    tmp = tempfile.mkdtemp(prefix="harness-lessons-validate-")
    steps: List[Tuple[str, bool, str]] = []
    gid = ""
    try:
        hub = os.path.join(tmp, "hub")
        os.makedirs(hub)
        tar = os.path.join(tmp, "hub.tar")
        env0 = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        rc = subprocess.call(["git", "-C", home, "archive", "--format=tar", "-o", tar, "HEAD"],
                             env=env0, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if rc != 0:
            raise LessonError("validate: `git archive HEAD` failed in %s (the hub must be a git checkout)" % home)
        with tarfile.open(tar) as tf:
            # our own HEAD, written by git archive; the data filter where python has it
            if hasattr(tarfile, "data_filter"):
                tf.extractall(hub, filter="data")
            else:
                tf.extractall(hub)
        env0["GIT_CEILING_DIRECTORIES"] = tmp
        rc, out = _run_step(["git", "apply", "--whitespace=nowarn", os.path.abspath(diff_path)], hub, env0, 120)
        steps.append(("apply", rc == 0, out or ("applied" if rc == 0 else "failed")))
        if rc != 0:
            return False, steps, gid
        build = os.path.join(tmp, "build")
        fake_home = os.path.join(tmp, "home")
        os.makedirs(build)
        os.makedirs(fake_home)
        env = suite_env(hub, build)
        env.update({"HOME": fake_home, "XDG_STATE_HOME": os.path.join(tmp, "state"),
                    "XDG_CACHE_HOME": os.path.join(tmp, "cache"), "XDG_DATA_HOME": os.path.join(tmp, "data"),
                    "HARNESS_CONFIG": os.path.join(hub, "tests", "fixtures", "harness.ci.toml"),
                    "PYTHONPATH": os.path.join(hub, "lib"), "GIT_CEILING_DIRECTORIES": tmp})
        for k in ("HARNESS_BUNDLES_ROOT", "HARNESS_BUNDLE_PATH", "HARNESS_PROVIDER_PATH",
                  "HARNESS_JOURNAL_DIR", "HARNESS_RETRO_DIR"):
            env.pop(k, None)
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
    hub = _hub(ctx)
    fn = globals()["cmd_" + action]
    return int(fn(ctx, ns, hub) or 0)


def cmd_list(ctx: Any, ns: Any, hub: Any) -> int:
    d = _dir(hub)
    want = ns.status or "open"
    now = norm_ts(None)
    max_age = int(cfg(hub, "lessons.max_age_days"))
    rows = []
    for r in load_all(d):
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
    if ctx.json:
        out = []
        for r, stale in rows:
            item = r.to_dict()
            item["stale"] = stale
            out.append(item)
        print(json.dumps(out, indent=2))
        return 0
    if not rows:
        print("no lessons (%s; status %s)" % (d, want))
        return 0
    table = [["id", "status", "scope", "uses/helped/recurred", "updated", "fresh", "situation"]]
    for r, stale in rows:
        sit = r.situation if len(r.situation) <= 60 else r.situation[:57] + "..."
        table.append([r.id, r.status, r.fm["scope"], "%d/%d/%d" % (r.fm["uses"], r.fm["helped"], r.fm["recurred"]),
                      r.fm["updated"], "stale" if stale else "ready", sit])
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
    jdir = journal_dir()
    session = ns.session or current_session()
    thresholds = {key: int(cfg(hub, key)) for _n, _k, key in CRITERIA}
    reason = None
    lines: List[JLine] = []
    if not journal_files(jdir):
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
            out["lines"] = [OrderedDict([("ts", ln.ts), ("kind", ln.kind), ("site", ln.site)]) for ln in state["lines"]]
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
            print("  %s  %s  %s" % (ln.ts, ln.kind, ln.site))
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
    out = os.path.abspath(ns.out)
    for name, text in files.items():
        atomic_write(os.path.join(out, name), text.encode("utf-8"), mode=0o644)
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


def cmd_journal(ctx: Any, ns: Any, hub: Any) -> int:
    rdir = retro_dir()
    last_path = os.path.join(rdir, "last")
    since = None
    origin = "all"
    if ns.since:
        since, origin = norm_ts(ns.since), "--since"
    elif not ns.all:
        last = (read_text(last_path) or "").strip()
        if re.match(_TS, last):
            since, origin = last, "retro/last"
    lines = [ln for ln in journal_lines() if not since or ln.ts > since]
    gmap = GuardMap(hub)
    groups: "OrderedDict[Tuple[str, str, str], Dict[str, Any]]" = OrderedDict()
    for ln in lines:
        key = (ln.kind, ln.site, gmap.status(ln))
        g = groups.get(key)
        if g is None:
            g = groups[key] = {"kind": ln.kind, "site": ln.site, "status": key[2], "count": 0,
                               "sessions": set(), "first": ln.ts, "last": ln.ts, "text": gmap.text(ln)}
        g["count"] += 1
        g["sessions"].add(ln.session)
        g["first"] = min(g["first"], ln.ts)
        g["last"] = max(g["last"], ln.ts)
    ordered = sorted(groups.values(), key=lambda g: (JOURNAL_KINDS.index(g["kind"]), g["site"], g["status"]))
    if ctx.json:
        print(json.dumps(OrderedDict([
            ("since", since), ("from", origin), ("guard_id", gmap.guard_id), ("lines", len(lines)),
            ("groups", [OrderedDict([("kind", g["kind"]), ("site", g["site"]), ("status", g["status"]),
                                     ("count", g["count"]), ("sessions", len(g["sessions"])),
                                     ("first", g["first"]), ("last", g["last"]), ("text", g["text"])])
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
        ack(rdir)
        print("acknowledged: %s" % last_path)
    return 0


def ack(rdir: str, keep_days: int = 7) -> None:
    os.makedirs(rdir, mode=0o700, exist_ok=True)
    atomic_write(os.path.join(rdir, "last"), (now_ts() + "\n").encode("utf-8"), mode=0o600)
    cutoff = time.time() - keep_days * 86400
    for path in glob.glob(os.path.join(rdir, "sessions", "*")):
        try:
            if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                os.unlink(path)
        except OSError:
            pass
