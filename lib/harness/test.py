"""``harness test [suite]``: discover and run every test suite, one PASS/FAIL line each.

Suites (in order):

* ``unit``       ``python3 -m unittest discover -s tests/unit``
* ``guard``      ``bundles/core/guard/tests/run.sh`` with ``GUARD_BASH`` pointing at a guard
                 concatenated from **all** bundles into ``build/guard/guard-bash.sh``
* ``bundles``    every ``bundles/*/tests/run.sh``
* ``skills``     every ``bundles/*/skills/*/scripts/tests/run.sh``
* ``providers``  every ``providers/*/tests/run.sh``
* ``smoke``      every ``tests/smoke/*.sh``

``harness test <bundle>`` runs that bundle's own suites only. The last non-empty output
line of each suite is shown as its summary; failures print their FAIL lines. Exit status
is non-zero when any suite fails.
"""
from __future__ import annotations

import glob
import os
import re
import subprocess
import sys
import tempfile
import time
from typing import Any, List, Tuple

from .util import atomic_write, hub_home

SUITES = ("unit", "guard", "bundles", "skills", "providers", "smoke")


def build_all_guard(home: str) -> str:
    """Concatenate engine + every bundle's sections into build/guard/guard-bash.sh."""
    from . import manifest as M
    from . import render as R

    root = os.environ.get("HARNESS_BUNDLES_ROOT") or os.path.join(home, "bundles")
    bundles = M.discover_bundles([(root, "public")])
    ordered = [bundles[n] for n in sorted(bundles)]
    engine = R.find_guard_engine(ordered)
    if engine is None:
        raise RuntimeError("no guard engine (bundles/core/guard/engine.sh) found")
    out = os.path.join(home, "build", "guard", "guard-bash.sh")
    atomic_write(out, R.build_guard(engine, ordered), mode=0o755)
    return out


def discover(home: str, suite: str) -> List[Tuple[str, List[str], dict]]:
    """(name, argv, extra env) for the selected suite(s)."""
    out: List[Tuple[str, List[str], dict]] = []
    py = sys.executable or "python3"
    want = SUITES if suite == "all" else (suite,)
    bundle_only = suite not in SUITES and suite != "all"
    root = os.environ.get("HARNESS_BUNDLES_ROOT") or os.path.join(home, "bundles")
    if bundle_only:
        base = os.path.join(root, suite)
        if not os.path.isdir(base):
            raise RuntimeError("unknown suite or bundle %r (suites: all, %s)" % (suite, ", ".join(SUITES)))
        for p in [os.path.join(base, "tests", "run.sh")] + sorted(glob.glob(os.path.join(base, "skills", "*", "scripts", "tests", "run.sh"))):
            if os.path.isfile(p):
                out.append((os.path.relpath(p, home), ["bash", p], {}))
        return out
    for s in want:
        if s == "unit":
            if os.path.isdir(os.path.join(home, "tests", "unit")):
                out.append(("unit", [py, "-m", "unittest", "discover", "-s", os.path.join(home, "tests", "unit")],
                            {"PYTHONPATH": os.path.join(home, "lib")}))
        elif s == "guard":
            runner = os.path.join(root, "core", "guard", "tests", "run.sh")
            if os.path.isfile(runner):
                out.append(("guard", ["bash", runner], {"__build_guard__": "1"}))
        elif s == "bundles":
            for p in sorted(glob.glob(os.path.join(root, "*", "tests", "run.sh"))):
                out.append((os.path.relpath(p, home), ["bash", p], {}))
        elif s == "skills":
            for p in sorted(glob.glob(os.path.join(root, "*", "skills", "*", "scripts", "tests", "run.sh"))):
                out.append((os.path.relpath(p, home), ["bash", p], {}))
        elif s == "providers":
            for p in sorted(glob.glob(os.path.join(home, "providers", "*", "tests", "run.sh"))):
                out.append((os.path.relpath(p, home), ["bash", p], {}))
        elif s == "smoke":
            for p in sorted(glob.glob(os.path.join(home, "tests", "smoke", "*.sh"))):
                out.append((os.path.relpath(p, home), ["bash", p], {}))
    return out


def run(ctx: Any, suite: str = "all", verbose: bool = False) -> int:
    home = hub_home()
    try:
        suites = discover(home, suite)
    except RuntimeError as exc:
        print("harness: %s" % exc, file=sys.stderr)
        return 2
    if not suites:
        print("no test suites found for %r" % suite)
        return 1
    failed = 0
    width = max(len(n) for n, _a, _e in suites)
    for name, argv, extra in suites:
        env = dict(os.environ)
        env["HARNESS_HOME"] = home
        if extra.pop("__build_guard__", None):
            try:
                env["GUARD_BASH"] = build_all_guard(home)
            except Exception as exc:
                print("FAIL  %-*s could not build the guard: %s" % (width, name, exc))
                failed += 1
                continue
        env.update(extra)
        start = time.time()
        with tempfile.TemporaryFile() as log:
            rc = subprocess.call(argv, cwd=home, env=env, stdout=log, stderr=subprocess.STDOUT)
            log.seek(0)
            text = log.read().decode("utf-8", "replace")
        lines = [ln for ln in text.splitlines() if ln.strip()]
        summary = lines[-1].strip() if lines else ""
        took = time.time() - start
        if rc == 0:
            print("PASS  %-*s %s (%.1fs)" % (width, name, summary, took))
        else:
            failed += 1
            print("FAIL  %-*s rc=%d %s" % (width, name, rc, summary))
            shown = [ln for ln in lines if re.search(r"FAIL|not ok|Error|Traceback", ln)][:20]
            for ln in shown:
                print("      %s" % ln)
        if verbose:
            for ln in text.splitlines():
                print("      %s" % ln)
        sys.stdout.flush()
    print("test: %d suite(s), %d failed" % (len(suites), failed))
    return 1 if failed else 0
