"""Manual steps: the human-only actions each bundle needs (logins, consoles, admin grants).

``harness steps`` lists the steps of the active bundles grouped by what they need:
``no browser``, ``browser`` and ``admin`` (a step needing both lands in ``admin``).
``--pending`` runs each step's templated ``verify.cmd`` and keeps only the failing ones
(steps without a verify command always count as pending). The same text is used by the
generated ``docs/bundles/<b>.md`` pages and by bootstrap's final hand-off.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import render as R
from .util import first_line, run_shell

GROUPS = [("none", "No browser needed"), ("browser", "Needs a browser"), ("admin", "Needs an administrator")]


def group_of(step: Dict[str, Any]) -> str:
    needs = step.get("needs") or []
    if "admin" in needs:
        return "admin"
    if "browser" in needs:
        return "browser"
    return "none"


def verify(hub: Any, bundle: Any, step: Dict[str, Any], tpl: Optional[R.Templater] = None) -> Tuple[Optional[bool], str]:
    """(True=done | False=pending | None=cannot verify, detail)."""
    v = step.get("verify") or {}
    if not v.get("cmd"):
        return None, "no verify command"
    tpl = tpl or R.Templater(hub.template_context())
    cmd = tpl.expand(v["cmd"], "%s manual_steps.%s" % (bundle.name, step.get("id")))
    if tpl.missing:
        key = tpl.missing[-1][1]
        tpl.missing = []
        return False, "template key missing: %s" % key
    env = dict(os.environ)
    env.setdefault("HARNESS_HOME", hub.home)
    rc, out, err = run_shell(cmd, timeout=float(v.get("timeout", 15)), env=env)
    expect = v.get("expect") or {}
    ok = rc == int(expect.get("exit", 0))
    rx = expect.get("stdout_regex")
    if ok and rx and not re.search(rx, out + err):
        ok = False
    return ok, first_line(out) or first_line(err) or "rc=%d" % rc


def collect(hub: Any, bundles: Optional[Sequence[str]] = None, pending: bool = False
            ) -> List[Dict[str, Any]]:
    tpl = R.Templater(hub.template_context())
    active = [p.name for p in hub.active_providers]
    rows: List[Dict[str, Any]] = []
    for b in hub.active_bundles:
        if bundles and b.name not in bundles:
            continue
        for step in b.manual_steps:
            provs = step.get("providers") or []
            if provs and not any(p in provs for p in active):
                continue
            done: Optional[bool] = None
            detail = ""
            if pending:
                done, detail = verify(hub, b, step, tpl)
                if done:
                    continue
            how = tpl.expand(step.get("how", ""), "%s manual_steps.%s.how" % (b.name, step.get("id")))
            vcmd = (step.get("verify") or {}).get("cmd", "")
            rows.append({
                "bundle": b.name, "id": step.get("id"), "title": tpl.expand(step.get("title", ""), b.name),
                "group": group_of(step), "minutes": step.get("minutes"), "once_per": step.get("once_per", ""),
                "why": tpl.expand(step.get("why", ""), b.name), "how": how.strip(),
                "verify": tpl.expand(vcmd, b.name) if vcmd else "", "docs": "%s#%s" % (b.docs_path(), step.get("id")),
                "status": "pending" if done is False else ("unverifiable" if pending else ""), "detail": detail,
            })
            tpl.missing = []
    return rows


def render_text(rows: List[Dict[str, Any]], header: str = "") -> str:
    if not rows:
        return (header + "\n" if header else "") + "No manual steps.\n"
    total = sum(int(r["minutes"] or 0) for r in rows)
    out = []
    if header:
        out.append("%s (%d, ~%d min):" % (header, len(rows), total))
    for gid, title in GROUPS:
        grp = [r for r in rows if r["group"] == gid]
        if not grp:
            continue
        out.append("")
        out.append("== %s ==" % title)
        for r in grp:
            meta = []
            if r["minutes"]:
                meta.append("~%s min" % r["minutes"])
            if r["once_per"]:
                meta.append("once per %s" % r["once_per"])
            out.append("")
            out.append("[%s#%s] %s%s" % (r["bundle"], r["id"], r["title"], " (%s)" % ", ".join(meta) if meta else ""))
            if r["why"]:
                out.append("  why:    %s" % " ".join(r["why"].split()))
            for i, line in enumerate(r["how"].splitlines()):
                out.append("  %s %s" % ("how:   " if i == 0 else "       ", line))
            if r["verify"]:
                out.append("  verify: %s" % r["verify"])
            out.append("  docs:   %s" % r["docs"])
    out.append("")
    out.append("Re-run `harness doctor` (or `harness steps --pending`) after each step.")
    return "\n".join(out) + "\n"


def run(hub: Any, bundles: Optional[Sequence[str]] = None, pending: bool = False, as_json: bool = False) -> int:
    rows = collect(hub, bundles, pending)
    if as_json:
        print(json.dumps(rows, indent=2))
        return 0
    header = "Pending manual steps" if pending else "Manual steps"
    print(render_text(rows, header), end="")
    return 0
