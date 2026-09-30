"""upgrade: move the hub checkout forward, print migration notes, re-validate, plan (and apply).

* ``--to TAG``: ``git fetch --tags`` then ``git checkout TAG`` (detached, pinned)
* default: ``git pull --ff-only`` on the current branch (refuses on local changes)
* prints every ``## [X.Y.Z]`` section of CHANGELOG.md between the old and new VERSION
* re-validates the config (deprecations warn) and shows the plan; applies unless
  ``--no-apply`` or ``--dry-run`` (``--yes`` skips the confirmation)
"""
from __future__ import annotations

import re
from typing import Any, List, Tuple

from .util import HarnessError, parse_version, read_text, run_argv


def changelog_between(text: str, old: str, new: str) -> List[Tuple[str, str]]:
    """Sections ``## [ver]`` with old < ver <= new, newest first."""
    out: List[Tuple[str, str]] = []
    parts = re.split(r"(?m)^## \[?v?([0-9][^\]\s]*)\]?.*$", text)
    # parts = [preamble, ver1, body1, ver2, body2, ...]
    lo, hi = parse_version(old), parse_version(new)
    for i in range(1, len(parts) - 1, 2):
        ver, body = parts[i], parts[i + 1]
        v = parse_version(ver)
        if v and lo < v <= hi:
            out.append((ver, body.strip()))
    return out


def run(ctx: Any, ns: Any) -> int:
    from .util import hub_home

    home = hub_home()
    old = (read_text(home + "/VERSION") or "0.0.0").strip()
    rc, out, err = run_argv(["git", "-C", home, "status", "--porcelain", "--untracked-files=no"], timeout=30)
    if rc != 0:
        raise HarnessError("%s is not a git checkout: %s" % (home, err.strip()))
    if out.strip() and not ctx.dry_run:
        raise HarnessError("the hub has local changes; commit or stash them first:\n" + out)
    if ctx.dry_run:
        print("dry run: would %s" % ("fetch and check out %s" % ns.to if ns.to else "git pull --ff-only"))
    elif ns.to:
        for argv in (["git", "-C", home, "fetch", "--tags", "--quiet"], ["git", "-C", home, "checkout", "--quiet", ns.to]):
            rc, _o, e = run_argv(argv, timeout=300)
            if rc != 0:
                raise HarnessError("%s failed: %s" % (" ".join(argv[3:]), e.strip()))
    else:
        rc, o, e = run_argv(["git", "-C", home, "pull", "--ff-only", "--quiet"], timeout=300)
        if rc != 0:
            raise HarnessError("git pull --ff-only failed: %s" % e.strip())
    new = (read_text(home + "/VERSION") or old).strip()
    print("hub %s -> %s" % (old, new))
    for ver, body in changelog_between(read_text(home + "/CHANGELOG.md") or "", old, new):
        print("\n## %s\n%s" % (ver, body))
    # re-exec so the new engine code is the one that plans
    argv = ["bash", home + "/bin/harness", "plan"]
    if ctx.config:
        argv += ["--config", ctx.config]
    import subprocess

    rc = subprocess.call(argv)
    if rc == 1:
        return 1
    if ns.no_apply or ctx.dry_run:
        return 0
    apply_argv = ["bash", home + "/bin/harness", "apply"] + (["--config", ctx.config] if ctx.config else [])
    if ctx.yes:
        apply_argv.append("--yes")
    return subprocess.call(apply_argv)
