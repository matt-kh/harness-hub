"""status: what is active, where the config comes from, drift, and the capability matrix."""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from . import state as S
from .util import run_argv, tilde

MATRIX_ROWS = [
    ("guard hook", lambda c: "enforced" if c.get("hook_enforced") else "advisory"),
    ("ask decision", lambda c: "native" if c.get("ask") else "mapped (ask_as)" if c.get("hook_enforced") else "-"),
    ("permission lists", lambda c: c.get("permissions", "none")),
    ("instructions", lambda c: c.get("instructions", "native")),
    ("skills", lambda c: c.get("skills", "none")),
    ("agents", lambda c: c.get("agents", "none")),
    ("mcp", lambda c: c.get("mcp", "none")),
]


def matrix_rows(providers: List[Any]) -> List[List[str]]:
    rows = [["capability"] + [p.name for p in providers]]
    for label, fn in MATRIX_ROWS:
        rows.append([label] + [str(fn(p.capabilities)) for p in providers])
    return rows


def format_table(rows: List[List[str]]) -> str:
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    return "\n".join("  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip() for r in rows) + "\n"


def run(ctx: Any, matrix: bool = False) -> int:
    from .hub import Hub

    if matrix:
        hub = Hub(home=ctx.home, config_path=ctx.config, require_config=False)
        provs = [hub.providers[n] for n in sorted(hub.providers)]
        rows = matrix_rows(provs)
        if ctx.json:
            print(json.dumps({r[0]: dict(zip(rows[0][1:], r[1:])) for r in rows[1:]}, indent=2))
        else:
            print(format_table(rows), end="")
            print("\nenforced = the guard blocks commands; advisory = instructions only (no hook).")
        return 0
    hub = ctx.hub()
    from . import sync

    rows = sync.classify(hub, hub.active_providers)
    counts: Dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    rc, rev, _ = run_argv(["git", "-C", hub.home, "rev-parse", "--short", "HEAD"], timeout=5)
    info = {
        "hub": hub.home, "version": hub.version, "git": rev.strip() if rc == 0 else "",
        "config": hub.config_path, "build": hub.build_dir, "profile": hub.profile,
        "bundles": hub.active_names, "providers": [p.name for p in hub.active_providers],
        "auto_added": hub.resolution.added, "recommended": hub.resolution.recommended,
        "drift": counts,
        "applied": {p.name: S.load(p.name, p.home).applied_at for p in hub.active_providers},
    }
    if ctx.json:
        print(json.dumps(info, indent=2, sort_keys=True))
        return 0
    print("hub        %s (v%s%s)" % (tilde(hub.home), hub.version, ", " + info["git"] if info["git"] else ""))
    print("config     %s" % tilde(hub.config_path))
    print("build      %s" % tilde(hub.build_dir))
    print("bundles    %s" % " ".join(hub.active_names))
    for dep, by in sorted(hub.resolution.added.items()):
        print("           + %s (required by %s)" % (dep, by))
    for rec, by in sorted(hub.resolution.recommended.items()):
        print("           ? %s recommended by %s" % (rec, ", ".join(by)))
    print("providers  %s" % " ".join(p.name for p in hub.active_providers))
    for p in hub.active_providers:
        print("applied    %-9s %s" % (p.name, info["applied"][p.name] or "never"))
    print("drift      " + ", ".join("%d %s" % (counts.get(k, 0), k) for k in ("clean", "drifted", "missing", "foreign")))
    for r in rows:
        if r["status"] in ("drifted", "missing"):
            print("           %s %s" % (r["status"], tilde(r["path"])))
    return 0
