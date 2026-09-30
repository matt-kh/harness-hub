"""uninstall: remove only what the state files list, honouring every bundle's ``[uninstall].keeps``.

* file / symlink entries: removed (backed up first) when unchanged since the last apply;
  edited ones are kept and reported
* managed blocks, JSON contributions and TOML blocks: only the harness's parts are removed;
  a file the harness created and that is now empty is deleted
* ``--bundle X``: only entries owned by X (files shared by several bundles are left alone)
* ``--purge-tools``: also tools written by ``harness install``
"""
from __future__ import annotations

import fnmatch
import os
from typing import Any, List

from . import apply as A
from . import plan as P
from . import state as S
from .util import HarnessError, expand, tilde


def _kept(path: str, keeps: List[str]) -> bool:
    for pat in keeps:
        p = expand(pat)
        if fnmatch.fnmatch(path, p) or (pat.endswith("/**") and path.startswith(expand(pat[:-3]) + "/")):
            return True
    return False


def run(ctx: Any, ns: Any) -> int:
    from .hub import Hub

    hub = Hub(home=ctx.home, config_path=ctx.config, require_config=False)
    names: List[str] = []
    if ns.all:
        names = sorted(hub.providers)
    elif ns.provider:
        names = [n for v in ns.provider for n in v.split(",")]
    else:
        names = [p.name for p in hub.active_providers]
    names.append("_hub")
    keeps: List[str] = []
    for b in hub.bundles.values():
        keeps.extend(b.uninstall.get("keeps", []) or [])
    only = set(n for v in (ns.bundle or []) for n in v.split(","))
    plan = P.Plan()
    homes = {}
    for name in names:
        home = hub.provider(name).home if name != "_hub" else None
        homes[name] = home
        st = S.load(name, home)
        plan.states[name] = st
        for path in st.paths():
            entry = st.get(path) or {}
            owners = set((entry.get("bundle") or "").split(","))
            if only and not owners <= only:
                continue
            if _kept(path, keeps):
                print("keep     %s  (uninstall.keeps)" % tilde(path))
                continue
            plan.items.append(P._orphan(path, name, entry, adopt=False))
        if ns.purge_tools and name == "_hub":
            for tool, info in sorted(st.tools.items()):
                path = info.get("path", "")
                if path and os.path.exists(path):
                    it = P.Item(None, path, "_hub", "orphan", "tool %s" % tool)
                    it.write, it.new = True, None
                    plan.items.append(it)
    if not plan.items:
        print("uninstall: nothing recorded for %s" % ", ".join(names))
        return 0
    P.print_plan(plan)
    if ctx.dry_run:
        return 0
    if not ctx.yes:
        import sys

        if not sys.stdin.isatty():
            raise HarnessError("uninstall needs --yes when not interactive")
        if input("Remove %d path(s)? [y/N] " % plan.changes).strip().lower() not in ("y", "yes"):
            print("aborted")
            return 1
    report = A.execute(plan, hub, {k: v for k, v in homes.items() if v})
    if ns.purge_tools:
        st = plan.states["_hub"]
        st.tools = {}
        if st.files:
            st.save()
        else:
            st.remove_file()
    print(A.summary_line(report).replace("Applied", "Uninstalled"))
    return 0
