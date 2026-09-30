"""Apply a plan: back up, write atomically, record state.

Backups: every existing file that is modified or removed is copied first to
``$XDG_STATE_HOME/harness/backups/<UTC timestamp>/<path relative to $HOME>`` (mode 0700
directories), so nothing is ever lost. Writes go through a temp file + rename in the same
directory. State files are saved last, and only for providers whose state changed.
"""
from __future__ import annotations

import os
import shutil
import time
from typing import Any, Dict, List, Optional

from . import build_products
from .plan import Item, Plan
from .util import atomic_symlink, atomic_write, state_dir, tilde, user_home


def backup_root(ts: Optional[str] = None) -> str:
    ts = ts or time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return os.path.join(state_dir(), "backups", ts)


def backup(path: str, root: str) -> Optional[str]:
    if not os.path.lexists(path):
        return None
    home = user_home().rstrip("/")
    rel = path[len(home) + 1:] if path.startswith(home + "/") else os.path.join("_abs", path.lstrip("/"))
    dest = os.path.join(root, rel)
    os.makedirs(os.path.dirname(dest), mode=0o700, exist_ok=True)
    try:
        os.chmod(root, 0o700)
    except OSError:
        pass
    if os.path.islink(path):
        if os.path.lexists(dest):
            os.unlink(dest)
        os.symlink(os.readlink(path), dest)
    else:
        shutil.copy2(path, dest)
    return dest


def _remove(path: str, stop_at: List[str]) -> None:
    try:
        os.unlink(path)
    except FileNotFoundError:
        return
    # prune now-empty parents we may have created, never above a provider home
    d = os.path.dirname(path)
    stops = set(os.path.abspath(s) for s in stop_at) | {user_home()}
    while d and d not in stops and d != "/":
        try:
            os.rmdir(d)
        except OSError:
            break
        d = os.path.dirname(d)


def execute(plan: Plan, hub: Any, homes: Dict[str, str], dry_run: bool = False,
            log=print) -> Dict[str, Any]:
    """Write every item with ``write``; update the state of every item. Returns a report."""
    root = backup_root()
    report = {"written": 0, "removed": 0, "backups": 0, "backup_dir": None}
    if dry_run:
        return report
    stop_at = [os.path.expanduser(h) for h in homes.values() if h]
    for it in plan.items:
        st = plan.states[it.provider]
        if it.write:
            if it.old is not None or os.path.lexists(it.path):
                if backup(it.path, root):
                    report["backups"] += 1
                    report["backup_dir"] = root
            if it.link is not None and it.new is None and it.target is not None:
                atomic_symlink(it.link, it.path)
                report["written"] += 1
            elif it.new is None:
                _remove(it.path, stop_at)
                report["removed"] += 1
            else:
                mode = None
                if it.mode == "file":
                    mode = 0o755 if it.executable else 0o644
                elif not os.path.exists(it.path):
                    mode = 0o644
                atomic_write(it.path, it.new, mode=mode)
                report["written"] += 1
        if it.entry is None:
            st.drop(it.path)
        else:
            st.set(it.path, it.entry)
    # conflicts are remembered so doctor can warn about them
    for name, st in plan.states.items():
        st.conflicts = sorted(
            "%s: %s" % (tilde(i.path), d or i.reason)
            for i in plan.items if i.provider == name and i.action == "conflict"
            for d in (i.details or [""]))
    for name, st in sorted(plan.states.items()):
        before = st.exists
        if not st.files and not before:
            continue
        if not st.files and before and not st.tools:
            st.remove_file()
            continue
        if st.dirty():
            st.save()
    build_products.write(hub)
    return report


def summary_line(report: Dict[str, Any]) -> str:
    text = "Applied: %d written, %d removed" % (report["written"], report["removed"])
    if report["backups"]:
        text += ", %d backed up to %s" % (report["backups"], tilde(report["backup_dir"]))
    return text
