"""sync: classify managed paths and adopt edits made through a provider back into the repo.

Per path (state vs live, plus the current render):

* ``clean``    live content equals what the last apply wrote
* ``drifted``  live content changed since the last apply (edited in the provider dir)

Merged targets compare only what the harness owns, never the whole file, because the
provider (or the user) rewrites the rest freely (Claude Code rewrites ``~/.claude.json``
on every session): ``json-merge`` is clean while merging the render into the live document
is a no-op without conflicts (unrelated keys never count), or, when the path is no longer
rendered, while every value recorded in the state ``owned`` list is still in place;
``managed-block`` and ``toml-block`` compare each recorded block body with its sha in the
state ``blocks`` map, ignoring text outside the blocks. ``file``/``dir`` keep the whole-file
sha and ``symlink`` the link target.
* ``missing``  recorded in state, gone from disk
* ``foreign``  rendered by the hub, present on disk, not in state (never adopted)

``--adopt [PATH…]`` copies a drifted rendered *file* back to its source in the bundle, but
only when the file is untemplated (rendered bytes == source bytes); managed blocks are
adopted the same way when the block body equals the untemplated rule file. Anything
templated (or JSON-merged) prints the diff and is refused: edit the bundle source or
``harness.toml`` instead. The state entry is refreshed so the next plan is clean.
"""
from __future__ import annotations

import difflib
import json
import os
from typing import Any, Dict, List, Optional, Sequence

from . import render as R
from . import state as S
from .util import HarnessError, atomic_write, canonical_json, expand, read_bytes, sha256_bytes, tilde


def classify(hub: Any, providers: Sequence[Any]) -> List[Dict[str, Any]]:
    targets = {t.path: t for t in R.Renderer(hub).render(providers, include_hub=True)}
    rows: List[Dict[str, Any]] = []
    names = [(p.name, p.home) for p in providers] + [("_hub", None)]
    seen = set()
    for name, home in names:
        st = S.load(name, home)
        for path in st.paths():
            entry = st.get(path) or {}
            seen.add(path)
            mode = entry.get("mode", "file")
            if mode == "symlink":
                if not os.path.islink(path):
                    status = "missing"
                elif os.readlink(path) != entry.get("target"):
                    status = "drifted"
                else:
                    status = "clean"
            else:
                live = read_bytes(path)
                if live is None:
                    status = "missing"
                elif sha256_bytes(live) == entry.get("sha256"):
                    status = "clean"
                else:
                    status = _merged_status(mode, live, entry, targets.get(path))
            rows.append({"path": path, "provider": name, "status": status, "mode": mode, "entry": entry,
                         "target": targets.get(path)})
    for path, t in sorted(targets.items()):
        if path in seen:
            continue
        if os.path.lexists(path):
            rows.append({"path": path, "provider": t.provider, "status": "foreign", "mode": t.mode,
                         "entry": None, "target": t})
    rows.sort(key=lambda r: (r["provider"], r["path"]))
    return rows


def _merged_status(mode: str, live: bytes, entry: Dict[str, Any], target: Any) -> str:
    """``clean``/``drifted`` for a path whose whole-file sha changed (see the module doc)."""
    try:
        text = live.decode("utf-8")
    except UnicodeDecodeError:
        return "drifted"
    if mode == "json-merge" and ("owned" in entry or target is not None):
        try:
            doc = json.loads(text) if text.strip() else {}
        except ValueError:
            return "drifted"
        if not isinstance(doc, dict):
            return "drifted"
        if target is not None and target.mode == "json-merge":
            merged, _owned, conflicts = R.merge_json(doc, target, entry.get("owned", []))
            return "clean" if not conflicts and canonical_json(merged) == canonical_json(doc) else "drifted"
        return "clean" if _owned_in_place(doc, entry.get("owned", [])) else "drifted"
    if mode == "managed-block" and "blocks" in entry:
        live_blocks = dict(v for k, v in R.parse_blocks(text) if k == "block")
        return "clean" if _blocks_match(entry["blocks"], live_blocks, R.body_sha) else "drifted"
    if mode == "toml-block" and "blocks" in entry:
        live_blocks = {m.group("id"): m.group("body") for m in R._TBLOCK_RE.finditer(text)}
        return "clean" if _blocks_match(entry["blocks"], live_blocks,
                                        lambda b: sha256_bytes(b.encode())) else "drifted"
    return "drifted"


def _owned_in_place(doc: Dict[str, Any], owned: Sequence[Dict[str, Any]]) -> bool:
    for rec in owned:
        cur = R._get(doc, tuple(rec["path"]))
        if cur is R._MISSING:
            return False
        if "items" in rec:
            if not isinstance(cur, list):
                return False
            have = {canonical_json(x) for x in cur}
            if any(canonical_json(i) not in have for i in rec["items"]):
                return False
        elif canonical_json(cur) != canonical_json(rec.get("value")):
            return False
    return True


def _blocks_match(recorded: Dict[str, str], live_blocks: Dict[str, str], sha) -> bool:
    """Every block recorded at the last apply is present with the recorded body."""
    return all(k in live_blocks and sha(live_blocks[k]) == v for k, v in recorded.items())


def _adoptable_file(row: Dict[str, Any], home: str) -> Optional[str]:
    """Source path for an untemplated 1:1 file, else None."""
    entry = row["entry"] or {}
    t = row["target"]
    src = entry.get("source") or (t.source if t is not None else None)
    if not src or entry.get("templated") or (t is not None and t.templated):
        return None
    src = src if os.path.isabs(src) else os.path.join(home, src)
    if t is not None and t.source and read_bytes(t.source) != t.content:
        return None
    return src


def adopt_row(hub: Any, row: Dict[str, Any], log=print) -> bool:
    path = row["path"]
    live = read_bytes(path)
    if live is None:
        log("skip     %s  (missing)" % tilde(path))
        return False
    st = S.load(row["provider"], _home_of(hub, row["provider"]))
    if row["mode"] == "file":
        src = _adoptable_file(row, hub.home)
        if not src:
            t = row["target"]
            rendered = t.content if t is not None else b""
            log("refuse   %s  (templated or generated: edit the bundle source instead)" % tilde(path))
            _print_diff(rendered, live, path, log)
            return False
        atomic_write(src, live)
        entry = dict(row["entry"])
        entry["sha256"] = sha256_bytes(live)
        st.set(path, entry)
        st.save()
        log("adopted  %s -> %s" % (tilde(path), os.path.relpath(src, hub.home)))
        return True
    if row["mode"] == "managed-block":
        t = row["target"]
        if t is None:
            log("refuse   %s  (no longer rendered)" % tilde(path))
            return False
        text = live.decode("utf-8")
        live_blocks = dict(v for k, v in R.parse_blocks(text) if k == "block")
        changed = 0
        entry = dict(row["entry"])
        blocks = dict(entry.get("blocks", {}))
        for blk in t.blocks:
            body = live_blocks.get(blk.key)
            if body is None or R.body_sha(body) == R.body_sha(blk.body):
                continue
            b = hub.bundle(blk.bundle)
            src = b.rel(blk.file)
            raw = (read_bytes(src) or b"").decode("utf-8")
            if raw.rstrip("\n") != blk.body:
                log("refuse   %s [%s]  (templated block: edit %s)" % (tilde(path), blk.key, os.path.relpath(src, hub.home)))
                _print_diff(blk.body.encode(), body.encode(), path, log)
                continue
            atomic_write(src, (body.rstrip("\n") + "\n").encode("utf-8"))
            blocks[blk.key] = R.body_sha(body)
            changed += 1
            log("adopted  %s [%s] -> %s" % (tilde(path), blk.key, os.path.relpath(src, hub.home)))
        if changed:
            entry["blocks"] = blocks
            entry["sha256"] = sha256_bytes(live)
            st.set(path, entry)
            st.save()
        return changed > 0
    log("refuse   %s  (%s: edit permissions.toml / mcp.toml / harness.toml instead)" % (tilde(path), row["mode"]))
    return False


def _home_of(hub: Any, provider: str) -> Optional[str]:
    if provider == "_hub":
        return None
    return hub.provider(provider).home


def _print_diff(old: bytes, new: bytes, path: str, log) -> None:
    try:
        a = old.decode("utf-8").splitlines(True)
        b = new.decode("utf-8").splitlines(True)
    except UnicodeDecodeError:
        log("         (binary)")
        return
    for line in difflib.unified_diff(a, b, "rendered", "live " + tilde(path)):
        log("         " + line.rstrip("\n"))


def run(hub: Any, providers: Sequence[Any], adopt: Optional[List[str]] = None, as_json: bool = False) -> int:
    rows = classify(hub, providers)
    if adopt is not None:
        wanted = [expand(p) for p in adopt]
        n = 0
        for row in rows:
            if row["status"] != "drifted":
                continue
            if wanted and not any(row["path"] == w or row["path"].startswith(w.rstrip("/") + "/") for w in wanted):
                continue
            n += 1 if adopt_row(hub, row) else 0
        print("sync: adopted %d file(s); commit the bundle changes in %s" % (n, hub.home) if n else "sync: nothing adopted")
        return 0
    counts: Dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    if as_json:
        print(json.dumps({"counts": counts, "paths": [
            {"path": tilde(r["path"]), "provider": r["provider"], "status": r["status"], "mode": r["mode"]}
            for r in rows]}, indent=2))
    else:
        for r in rows:
            if r["status"] != "clean":
                print("%-8s %s" % (r["status"], tilde(r["path"])))
        print("sync: " + ", ".join("%d %s" % (counts.get(k, 0), k) for k in ("clean", "drifted", "missing", "foreign")))
    return 1 if counts.get("drifted") or counts.get("missing") else 0
