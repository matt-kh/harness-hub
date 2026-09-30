"""Plan: compare rendered targets with live files and state; classify every path.

Actions (ARCHITECTURE §6): ``create | update | skip | conflict | orphan``.

* ``create``   path absent (or recorded but deleted by hand)
* ``update``   path ours and unchanged since the last apply, content differs from the render
* ``skip``     live content already equals the render (an identical foreign file is silently
               taken into the state)
* ``conflict`` the user wins: a foreign file/skill dir, a hand-edited managed file, a JSON
               value the user changed, an invalid merge. Merge targets may still be written
               for their non-conflicting parts (``write`` is then true).
* ``orphan``   recorded in state but no longer rendered: removed (with a backup) if unchanged

``--adopt PATH`` turns conflicts at or below PATH into updates (the live file is backed up).
Only paths in the plan are ever read or written; provider runtime state is never listed.
"""
from __future__ import annotations

import difflib
import json
import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import render as R
from . import state as S
from .util import expand, read_bytes, sha256_bytes, tilde


class Item:
    def __init__(self, target: Optional[R.Target], path: str, provider: str, action: str, reason: str = ""):
        self.target = target
        self.path = path
        self.provider = provider
        self.action = action
        self.reason = reason
        self.old: Optional[bytes] = None
        self.new: Optional[bytes] = None   # None + write => delete
        self.write = False
        self.entry: Optional[Dict[str, Any]] = None  # new state entry (None => drop)
        self.details: List[str] = []
        self.link: Optional[str] = None
        self.executable = False
        self.view: Optional[Tuple[str, str]] = None  # (old, new) text for diffs

    @property
    def mode(self) -> str:
        if self.target is not None:
            return self.target.mode
        return (self.entry or {}).get("mode", "file")

    def diff(self) -> str:
        if self.view is not None:
            old, new = self.view
        else:
            try:
                old = (self.old or b"").decode("utf-8")
                new = (self.new or b"").decode("utf-8") if self.new is not None else ""
            except UnicodeDecodeError:
                return "  (binary content differs)\n"
        name = tilde(self.path)
        lines = difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                     "a/" + name.lstrip("~/"), "b/" + name.lstrip("~/"))
        return "".join(line if line.endswith("\n") else line + "\n" for line in lines)


class Plan:
    def __init__(self) -> None:
        self.items: List[Item] = []
        self.states: Dict[str, S.State] = {}
        self.notes: List[str] = []

    def counts(self) -> Dict[str, int]:
        out = {"create": 0, "update": 0, "skip": 0, "conflict": 0, "orphan": 0}
        for it in self.items:
            out[it.action] += 1
        return out

    @property
    def changes(self) -> int:
        return sum(1 for it in self.items if it.write)

    def summary(self) -> str:
        c = self.counts()
        parts = ["%d %s" % (c[k], k) for k in ("create", "update", "orphan") if c[k]]
        text = "Plan: %d change%s" % (self.changes, "" if self.changes == 1 else "s")
        if parts:
            text += " (%s)" % ", ".join(parts)
        text += ", %d conflict%s, %d unchanged" % (c["conflict"], "" if c["conflict"] == 1 else "s", c["skip"])
        return text

    def to_json(self) -> Dict[str, Any]:
        return {
            "summary": self.summary(),
            "changes": self.changes,
            "counts": self.counts(),
            "items": [{"path": tilde(i.path), "provider": i.provider, "action": i.action,
                       "reason": i.reason, "details": i.details, "write": i.write} for i in self.items],
            "notes": self.notes,
        }


def _adopted(path: str, adopt: Sequence[str]) -> bool:
    for a in adopt:
        a = expand(a).rstrip("/")
        if path == a or path.startswith(a + "/"):
            return True
    return False


def _source_ref(src: Optional[str], home: str) -> Optional[str]:
    if not src:
        return None
    rel = os.path.relpath(src, home)
    return src if rel.startswith("..") else rel


def build(hub: Any, providers: Sequence[Any], adopt: Sequence[str] = (), include_hub: bool = True,
          targets: Optional[List[R.Target]] = None) -> Plan:
    plan = Plan()
    renderer = R.Renderer(hub)
    if targets is None:
        targets = renderer.render(providers, include_hub=include_hub)
    plan.notes.extend(renderer.notes)
    homes = {p.name: p.home for p in providers}
    names = [p.name for p in providers] + (["_hub"] if include_hub else [])
    for n in names:
        plan.states[n] = S.load(n, homes.get(n))
    rendered = set()
    # foreign skill directories: exist, non-empty, nothing of ours inside
    units: Dict[str, bool] = {}
    for t in targets:
        if t.unit and t.unit not in units:
            st = plan.states[t.provider]
            ours = any(p == t.unit or p.startswith(t.unit + "/") for p in st.paths())
            units[t.unit] = (not ours) and os.path.isdir(t.unit) and bool(os.listdir(t.unit))
    for t in targets:
        rendered.add(t.path)
        st = plan.states[t.provider]
        prev = st.get(t.path)
        adopt_this = _adopted(t.path, adopt)
        item = _classify(t, prev, adopt_this, units.get(t.unit or "", False), hub.home)
        plan.items.append(item)
    # orphans
    for n in names:
        st = plan.states[n]
        for path in st.paths():
            if path in rendered:
                continue
            plan.items.append(_orphan(path, n, st.get(path) or {}, _adopted(path, adopt)))
    plan.items.sort(key=lambda i: (i.provider, i.path))
    return plan


def _classify(t: R.Target, prev: Optional[Dict[str, Any]], adopt: bool, foreign_unit: bool, home: str) -> Item:
    it = Item(t, t.path, t.provider, "skip")
    if t.mode == "symlink":
        return _classify_link(t, prev, adopt, it)
    live = read_bytes(t.path) if not os.path.islink(t.path) or t.mode != "file" else read_bytes(t.path)
    if os.path.isdir(t.path):
        it.action, it.reason = "conflict", "a directory exists at this path"
        return it
    it.old = live
    bundle = t.bundle_label
    if t.mode == "file":
        new = t.content
        it.new = new
        it.executable = t.executable
        entry = {"sha256": sha256_bytes(new), "bundle": bundle, "mode": "file", "exec": t.executable}
        src = _source_ref(t.source, home)
        if src:
            entry["source"] = src
            entry["templated"] = bool(t.templated)
        it.entry = entry
        if live is None:
            it.action, it.write = "create", True
            if prev:
                it.reason = "was deleted outside the harness"
            if foreign_unit and not adopt:
                it.action, it.write = "conflict", False
                it.reason = "inside a foreign directory %s (kept; use --adopt %s)" % (tilde(t.unit or ""), tilde(t.unit or ""))
                it.entry = None
            return it
        live_sha = sha256_bytes(live)
        if prev is None:
            if live == new:
                it.action, it.reason = "skip", "identical foreign file taken into state"
                return it
            if adopt:
                it.action, it.write, it.reason = "update", True, "adopted (foreign file backed up)"
                return it
            it.action, it.reason, it.entry = "conflict", "foreign: exists and is not managed (kept; use --adopt)", None
            return it
        if live == new:
            it.action = "skip"
            if prev.get("sha256") != entry["sha256"] or prev.get("exec") != t.executable:
                it.reason = "state refreshed"
            _fix_exec(it, t)
            return it
        if live_sha == prev.get("sha256") or adopt:
            it.action, it.write = "update", True
            it.reason = "adopted (edited file backed up)" if live_sha != prev.get("sha256") else ""
            return it
        it.action = "conflict"
        it.reason = "edited outside the harness (kept; `harness sync` to adopt it into the bundle, or --adopt)"
        it.entry = dict(prev)
        return it

    if t.mode == "managed-block":
        live_text = live.decode("utf-8") if live is not None else None
        new_text, blocks, conflicts = R.merge_managed_blocks(live_text, t.blocks, (prev or {}).get("blocks", {}), adopt)
        new = new_text.encode("utf-8")
        created = live is None or bool((prev or {}).get("created"))
        it.entry = {"sha256": sha256_bytes(new), "bundle": bundle, "mode": t.mode, "blocks": blocks, "created": created}
        return _finish_merge(it, live, new, conflicts)

    if t.mode == "json-merge":
        live_doc: Any = {}
        if live is not None:
            try:
                live_doc = json.loads(live.decode("utf-8")) if live.strip() else {}
            except ValueError as exc:
                it.action, it.reason = "conflict", "not valid JSON (%s); kept untouched" % exc
                return it
            if not isinstance(live_doc, dict):
                it.action, it.reason = "conflict", "top level is not a JSON object; kept untouched"
                return it
        doc, owned, conflicts = R.merge_json(live_doc, t, (prev or {}).get("owned", []), adopt)
        new = R.dump_json(doc) if doc else (b"{}\n" if live is not None else b"")
        if live is None and not doc:
            it.action = "skip"
            return it
        created = live is None or bool((prev or {}).get("created"))
        it.entry = {"sha256": sha256_bytes(new), "bundle": bundle, "mode": t.mode, "owned": owned, "created": created}
        it.view = (_pretty(R.owner_view(live_doc, t)), _pretty(R.owner_view(doc, t)))
        if live is not None and json.loads(new.decode()) == live_doc:
            new = live  # semantically equal: never reformat the user's file
            it.entry["sha256"] = sha256_bytes(live)
        return _finish_merge(it, live, new, conflicts)

    if t.mode == "toml-block":
        live_text = live.decode("utf-8") if live is not None else None
        new_text, blocks, conflicts = R.merge_toml_blocks(live_text, t.tblocks, (prev or {}).get("blocks", {}), adopt)
        new = new_text.encode("utf-8")
        created = live is None or bool((prev or {}).get("created"))
        it.entry = {"sha256": sha256_bytes(new), "bundle": bundle, "mode": t.mode, "blocks": blocks, "created": created}
        return _finish_merge(it, live, new, conflicts)
    raise R.RenderError("unknown target mode %s" % t.mode)


def _fix_exec(it: Item, t: R.Target) -> None:
    """Content equal but the executable bit is wrong: a (cheap) update."""
    try:
        is_exec = os.access(t.path, os.X_OK)
    except OSError:
        return
    if is_exec != t.executable:
        it.action, it.write, it.reason = "update", True, "file mode"


def _finish_merge(it: Item, live: Optional[bytes], new: bytes, conflicts: List[str]) -> Item:
    it.new = new
    it.details = conflicts
    changed = live != new
    if live is None:
        it.action, it.write = "create", True
    elif changed:
        it.action, it.write = "update", True
    else:
        it.action = "skip"
    if conflicts:
        it.action = "conflict"
        it.reason = "%d value(s) kept as the user set them" % len(conflicts)
    if live is not None and not new.strip() and it.entry and it.entry.get("created"):
        it.new = None  # everything ours was removed from a file we created: delete it
    return it


def _classify_link(t: R.Target, prev: Optional[Dict[str, Any]], adopt: bool, it: Item) -> Item:
    it.link = t.link
    it.entry = {"sha256": sha256_bytes(t.link.encode("utf-8")), "bundle": t.bundle_label, "mode": "symlink",
                "target": t.link}
    if os.path.islink(t.path):
        cur = os.readlink(t.path)
        if cur == t.link:
            it.action = "skip"
            return it
        if prev is None and not adopt:
            it.action, it.reason, it.entry = "conflict", "foreign symlink -> %s (kept; use --adopt)" % cur, None
            return it
        if prev is not None and prev.get("target") != cur and not adopt:
            it.action, it.reason, it.entry = "conflict", "re-pointed outside the harness -> %s (kept)" % cur, dict(prev)
            return it
        it.action, it.write, it.reason = "update", True, "was -> %s" % cur
        it.view = ("-> %s\n" % cur, "-> %s\n" % t.link)
        return it
    if os.path.lexists(t.path):
        if not adopt:
            it.action, it.reason, it.entry = "conflict", "a regular file exists (kept; use --adopt)", None
            return it
        it.action, it.write, it.reason = "update", True, "adopted (file backed up)"
        it.old = read_bytes(t.path)
        return it
    it.action, it.write = "create", True
    it.view = ("", "-> %s\n" % t.link)
    return it


def _orphan(path: str, provider: str, prev: Dict[str, Any], adopt: bool) -> Item:
    it = Item(None, path, provider, "orphan", "no longer rendered")
    it.entry = None
    mode = prev.get("mode", "file")
    if mode == "symlink":
        if os.path.islink(path):
            if os.readlink(path) == prev.get("target") or adopt:
                it.write, it.new = True, None
            else:
                it.action, it.reason, it.entry = "conflict", "orphaned link re-pointed by hand (kept)", prev
        else:
            it.reason = "already gone"
        return it
    live = read_bytes(path)
    it.old = live
    if live is None:
        it.reason = "already gone"
        return it
    if mode in ("managed-block", "json-merge", "toml-block"):
        # remove only our contributions, keep the file
        t = R.Target(path, provider, mode)
        fake_prev = prev
        if mode == "managed-block":
            text, blocks, conflicts = R.merge_managed_blocks(live.decode("utf-8"), [], prev.get("blocks", {}), adopt)
            new = text.encode("utf-8")
        elif mode == "json-merge":
            try:
                doc = json.loads(live.decode("utf-8"))
            except ValueError:
                it.action, it.reason, it.entry = "conflict", "orphan is not valid JSON (kept)", prev
                return it
            R.unapply_owned(doc, fake_prev.get("owned", []))
            new = R.dump_json(doc) if doc else b""
            conflicts = []
        else:
            text, _b, conflicts = R.merge_toml_blocks(live.decode("utf-8"), {}, prev.get("blocks", {}), adopt)
            new = text.encode("utf-8")
        it.details = conflicts
        if new != live:
            it.write = True
            it.new = new if (new.strip() or not prev.get("created")) else None
        if conflicts:
            it.action = "conflict"
            it.entry = prev
        return it
    if sha256_bytes(live) == prev.get("sha256") or adopt:
        it.write, it.new = True, None
    else:
        it.action, it.reason, it.entry = "conflict", "orphaned file was edited (kept; delete it by hand or --adopt)", prev
    return it


def _pretty(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n" if obj else ""


def print_plan(plan: Plan, show_diff: bool = False, verbose: bool = False, out=None) -> None:
    import sys

    from .util import paint

    out = out or sys.stdout
    for it in plan.items:
        if it.action == "skip" and not verbose:
            continue
        line = "%s %s" % (paint(it.action, "%-8s" % it.action), tilde(it.path))
        if it.reason:
            line += "  (%s)" % it.reason
        print(line, file=out)
        for d in it.details:
            print("           ! %s" % d, file=out)
        if show_diff and it.write:
            text = it.diff()
            if text:
                out.write("".join("           " + ln for ln in text.splitlines(True)))
    for n in plan.notes:
        print("note     %s" % n, file=out)
    print(plan.summary(), file=out)
