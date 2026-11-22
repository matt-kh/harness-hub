"""``harness test [suite ...] [--jobs N|auto]``: discover and run every test suite, one PASS/FAIL line each.

Suites (in order):

* ``unit``       ``python3 -m unittest discover -s tests/unit``
* ``guard``      ``bundles/core/guard/tests/run.sh`` with ``GUARD_BASH`` pointing at a guard
                 concatenated from **all** bundles (built once per run into a run-level temp dir)
* ``bundles``    every ``bundles/*/tests/run.sh``
* ``skills``     every ``bundles/*/skills/*/scripts/tests/run.sh``
* ``providers``  every ``providers/*/tests/run.sh``
* ``smoke``      every ``tests/smoke/*.sh``

``harness test <bundle>`` runs that bundle's own suites only. Several names may be given
(``harness test unit skills github``); each resolves on its own, ``all`` anywhere means all,
and an entry selected twice runs once. The last non-empty output line of each suite is shown
as its summary; failures print their FAIL lines. Exit status is non-zero when any suite fails.

``--jobs N`` (``auto`` = the CPU count; default 1) runs the suites on N worker threads, each
suite in its own subprocess, and prints the results in discovery order. With N > 1 the guard
suite is sharded: one ``guard[<bundle>]`` entry per bundle with ``guard.d/tests.sh``, each
running only that bundle's rows (``HARNESS_TEST_ROWS``) against the same all-bundles guard.
The longest suites are submitted first (guard shards by the size of their rows file, then
``HEAVY``); entries in ``SERIAL`` run alone after the pool drains. With N = 1 the output is the
same as a serial run without the flag.

Every child suite gets ``HARNESS_BUILD_DIR`` set to its own fresh temporary directory, so no
suite (the bootstrap smoke applies a fixture config) can overwrite the live
``<hub>/build/config.json`` that rendered skills read.

Git's repository-discovery variables (``GIT_DIR``, ``GIT_WORK_TREE``, ``GIT_INDEX_FILE``, …)
are dropped from every child environment: git exports them to hooks, and a suite run from the
pre-push hook would otherwise point its throw-away fixture repositories at the real checkout
(``git add -A`` in a fixture then stages the deletion of the whole hub).

Each guard row runs once per run: when the run includes the ``guard`` suite (or its shards),
every other suite gets ``HARNESS_TEST_GUARD_COVERED=1`` (the core bundle suite then skips its
full guard-rows pass), and the bundle isolation suites run only their own rows
(``HARNESS_TEST_ROWS``). Both variables are dropped from the inherited environment, so a shell
export cannot skip rows.
"""
from __future__ import annotations

import concurrent.futures
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from .util import atomic_write, hub_home

SUITES = ("unit", "guard", "bundles", "skills", "providers", "smoke")

# Submitted to the pool right after the guard shards: the slowest suites besides the guard.
HEAVY = ("bundles/stack/tests/run.sh", "bundles/stack/skills/stk/scripts/tests/run.sh", "bundles/supply-chain/tests/run.sh",
         "bundles/core/tests/run.sh", "unit")

# Escape hatch: entries that must not run next to others (shared state). Run alone, after the pool.
SERIAL: frozenset = frozenset()

# Marks an entry that runs guard rows; run() gives it the shared GUARD_BASH.
GUARD_MARK = "__guard__"

# Exported by git to hook processes; a fixture ``git init`` under them re-targets the checkout.
GIT_DISCOVERY_ENV = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY",
                     "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_PREFIX", "GIT_NAMESPACE", "GIT_IMPLICIT_WORK_TREE")

# Row-selection knobs only ``run`` may set: inherited from the user's shell they would skip rows.
ROW_SKIP_ENV = ("HARNESS_TEST_GUARD_COVERED", "HARNESS_TEST_ROWS", "HARNESS_TEST_BUNDLES")

Entry = Tuple[str, List[str], dict]


def suite_env(home: str, build_dir: str) -> dict:
    """The environment every child suite runs with: hub + fresh build dir, no git discovery vars
    and no inherited row-selection knobs."""
    env = {k: v for k, v in os.environ.items() if k not in GIT_DISCOVERY_ENV and k not in ROW_SKIP_ENV}
    env["HARNESS_HOME"] = home
    env["HARNESS_BUILD_DIR"] = build_dir
    return env


def bundles_root(home: str) -> str:
    return os.environ.get("HARNESS_BUNDLES_ROOT") or os.path.join(home, "bundles")


def build_all_guard(home: str, build_dir: str) -> str:
    """Concatenate engine + every bundle's sections into <build_dir>/guard/guard-bash.sh."""
    from . import manifest as M
    from . import render as R

    bundles = M.discover_bundles([(bundles_root(home), "public")])
    ordered = [bundles[n] for n in sorted(bundles)]
    engine = R.find_guard_engine(ordered)
    if engine is None:
        raise RuntimeError("no guard engine (bundles/core/guard/engine.sh) found")
    out = os.path.join(build_dir, "guard", "guard-bash.sh")
    atomic_write(out, R.build_guard(engine, ordered), mode=0o755)
    return out


def is_guard(name: str) -> bool:
    """The ``guard`` suite or one of its ``guard[<bundle>]`` shards."""
    return name == "guard" or (name.startswith("guard[") and name.endswith("]"))


def guard_covered(suites: Sequence[Entry]) -> bool:
    """True when the discovered suites include the ``guard`` suite or a shard of it (every guard
    row runs there)."""
    return any(is_guard(name) for name, _a, _e in suites)


def parse_jobs(value: Union[str, int]) -> int:
    """``auto`` -> the CPU count; an integer >= 1 as is; anything else raises RuntimeError."""
    if isinstance(value, str) and value.strip().lower() == "auto":
        return os.cpu_count() or 1
    if isinstance(value, bool):
        n = None
    elif isinstance(value, int):
        n = value
    else:
        try:
            n = int(str(value).strip())
        except ValueError:
            n = None
    if n is None or n < 1:
        raise RuntimeError("--jobs: expected a positive integer or 'auto', got %r" % (value,))
    return n


def _guard_entries(root: str, shard: bool) -> List[Entry]:
    runner = os.path.join(root, "core", "guard", "tests", "run.sh")
    if not os.path.isfile(runner):
        return []
    if not shard:
        return [("guard", ["bash", runner], {GUARD_MARK: "1"})]
    out: List[Entry] = []
    for rows in sorted(glob.glob(os.path.join(root, "*", "guard.d", "tests.sh"))):
        b = os.path.basename(os.path.dirname(os.path.dirname(rows)))
        out.append(("guard[%s]" % b, ["bash", runner], {GUARD_MARK: "1", "HARNESS_TEST_ROWS": b}))
    return out


def _discover_one(home: str, root: str, name: str, shard: bool) -> List[Entry]:
    """Entries for one suite or bundle name; an unknown name raises RuntimeError."""
    out: List[Entry] = []
    if name not in SUITES:
        base = os.path.join(root, name)
        if not name or not os.path.isdir(base):
            raise RuntimeError("unknown suite or bundle %r (suites: all, %s)" % (name, ", ".join(SUITES)))
        for p in [os.path.join(base, "tests", "run.sh")] + sorted(glob.glob(os.path.join(base, "skills", "*", "scripts", "tests", "run.sh"))):
            if os.path.isfile(p):
                out.append((os.path.relpath(p, home), ["bash", p], {}))
        return out
    if name == "unit":
        if os.path.isdir(os.path.join(home, "tests", "unit")):
            py = sys.executable or "python3"
            out.append(("unit", [py, "-m", "unittest", "discover", "-s", os.path.join(home, "tests", "unit")],
                        {"PYTHONPATH": os.path.join(home, "lib")}))
        return out
    if name == "guard":
        return _guard_entries(root, shard)
    pattern = {
        "bundles": os.path.join(root, "*", "tests", "run.sh"),
        "skills": os.path.join(root, "*", "skills", "*", "scripts", "tests", "run.sh"),
        "providers": os.path.join(home, "providers", "*", "tests", "run.sh"),
        "smoke": os.path.join(home, "tests", "smoke", "*.sh"),
    }[name]
    for p in sorted(glob.glob(pattern)):
        out.append((os.path.relpath(p, home), ["bash", p], {}))
    return out


def discover(home: str, suites: Union[str, Sequence[str]] = "all", shard: bool = False) -> List[Entry]:
    """(name, argv, extra env) for the selected suite(s) and bundle(s), de-duplicated by name in
    first-seen order. ``all`` anywhere means every suite; ``shard`` splits ``guard`` per bundle."""
    names = [suites] if isinstance(suites, str) else list(suites)
    if not names or "all" in names:
        names = list(SUITES)
    root = bundles_root(home)
    out: List[Entry] = []
    seen = set()
    for name in names:
        for entry in _discover_one(home, root, name, shard):
            if entry[0] not in seen:
                seen.add(entry[0])
                out.append(entry)
    return out


def _run_one(home: str, argv: List[str], extra: dict, covered: bool, guard_bash: Optional[str]) -> Tuple[int, str, float]:
    """Run one suite in its own fresh build dir; (rc, combined output, seconds)."""
    build_dir = tempfile.mkdtemp(prefix="harness-test-build-")
    try:
        env = suite_env(home, build_dir)
        if GUARD_MARK in extra:
            if guard_bash:
                env["GUARD_BASH"] = guard_bash
        elif covered:
            env["HARNESS_TEST_GUARD_COVERED"] = "1"
        env.update({k: v for k, v in extra.items() if not k.startswith("__")})
        start = time.time()
        with tempfile.TemporaryFile() as log:
            rc = subprocess.call(argv, cwd=home, env=env, stdout=log, stderr=subprocess.STDOUT)
            log.seek(0)
            text = log.read().decode("utf-8", "replace")
        return rc, text, time.time() - start
    finally:
        shutil.rmtree(build_dir, ignore_errors=True)


def _report(name: str, width: int, rc: int, text: str, took: float, verbose: bool) -> str:
    """The PASS/FAIL line (+ failure excerpt, + full output with -v) for one finished suite."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    summary = lines[-1].strip() if lines else ""
    out: List[str] = []
    if rc == 0:
        out.append("PASS  %-*s %s (%.1fs)" % (width, name, summary, took))
    else:
        out.append("FAIL  %-*s rc=%d %s" % (width, name, rc, summary))
        shown = [ln for ln in lines if re.search(r"FAIL|not ok|Error|Traceback", ln)][:20]
        out.extend("      %s" % ln for ln in shown)
    if verbose:
        out.extend("      %s" % ln for ln in text.splitlines())
    return "\n".join(out)


def _submit_order(entries: Sequence[Entry], root: str) -> List[int]:
    """Indices of ``entries`` longest-first: guard (shards by rows-file size, descending), then
    ``HEAVY``, then the rest in discovery order."""
    def rows_size(extra: dict) -> int:
        b = extra.get("HARNESS_TEST_ROWS")
        if not b:
            return 1 << 62  # the unsharded guard runs every row
        try:
            return os.path.getsize(os.path.join(root, b, "guard.d", "tests.sh"))
        except OSError:
            return 0

    guard = sorted((i for i, (n, _a, _e) in enumerate(entries) if is_guard(n)),
                   key=lambda i: (-rows_size(entries[i][2]), i))
    names = {n: i for i, (n, _a, _e) in enumerate(entries)}
    heavy = [names[h] for h in HEAVY if h in names and names[h] not in guard]
    taken = set(guard) | set(heavy)
    rest = [i for i in range(len(entries)) if i not in taken]
    return guard + heavy + rest


def _label(suite: Union[str, Sequence[str]]) -> str:
    return suite if isinstance(suite, str) else " ".join(suite)


def run(ctx: Any, suite: Union[str, Sequence[str]] = "all", verbose: bool = False, jobs: Union[str, int] = 1) -> int:
    home = hub_home()
    try:
        n_jobs = parse_jobs(jobs)
        entries = discover(home, suite, shard=n_jobs > 1)
    except RuntimeError as exc:
        print("harness: %s" % exc, file=sys.stderr)
        return 2
    if not entries:
        print("no test suites found for %r" % _label(suite))
        return 1
    covered = guard_covered(entries)
    width = max(len(n) for n, _a, _e in entries)
    failed = 0
    guard_dir: Optional[str] = None
    guard_bash: Optional[str] = None
    guard_err: Optional[BaseException] = None
    try:
        if any(GUARD_MARK in e for _n, _a, e in entries):
            guard_dir = tempfile.mkdtemp(prefix="harness-test-guard-")
            try:
                guard_bash = build_all_guard(home, guard_dir)
            except Exception as exc:  # reported once per guard entry below
                guard_err = exc

        def blocked(extra: dict) -> bool:
            return GUARD_MARK in extra and guard_err is not None

        def emit(name: str, result: Tuple[int, str, float]) -> None:
            nonlocal failed
            rc, text, took = result
            if rc != 0:
                failed += 1
            print(_report(name, width, rc, text, took, verbose))
            sys.stdout.flush()

        def emit_blocked(name: str) -> None:
            nonlocal failed
            failed += 1
            print("FAIL  %-*s could not build the guard: %s" % (width, name, guard_err))
            sys.stdout.flush()

        if n_jobs == 1:
            for name, argv, extra in entries:
                if blocked(extra):
                    emit_blocked(name)
                else:
                    emit(name, _run_one(home, argv, extra, covered, guard_bash))
        else:
            futures: Dict[int, "concurrent.futures.Future"] = {}
            pool = concurrent.futures.ThreadPoolExecutor(max_workers=n_jobs)
            try:
                for i in _submit_order(entries, bundles_root(home)):
                    name, argv, extra = entries[i]
                    if name in SERIAL or blocked(extra):
                        continue
                    futures[i] = pool.submit(_run_one, home, argv, extra, covered, guard_bash)
                for i, (name, argv, extra) in enumerate(entries):
                    if blocked(extra):
                        emit_blocked(name)
                    elif i in futures:
                        emit(name, futures[i].result())
                    else:  # SERIAL: alone, once everything submitted has finished
                        pool.shutdown(wait=True)
                        emit(name, _run_one(home, argv, extra, covered, guard_bash))
            except BaseException:  # Ctrl-C or an error: start no queued suite, wait for the running ones
                pool.shutdown(wait=True, cancel_futures=True)
                raise
            finally:
                pool.shutdown(wait=True)
    finally:
        if guard_dir:
            shutil.rmtree(guard_dir, ignore_errors=True)
    print("test: %d suite(s), %d failed" % (len(entries), failed))
    return 1 if failed else 0
