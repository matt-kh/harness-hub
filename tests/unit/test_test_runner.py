"""``harness test`` runner: each guard row runs once per run (HARNESS_TEST_GUARD_COVERED); several
suite names, ``--jobs`` (thread pool, discovery-order output) and guard shards."""
from __future__ import annotations

import io
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

from helpers import REPO  # noqa: E402,F401  (puts lib/ on sys.path)

from harness import test as T


class SuiteEnvScrubTest(unittest.TestCase):
    def test_inherited_row_knobs_are_dropped(self):
        with mock.patch.dict(os.environ, {"HARNESS_TEST_GUARD_COVERED": "1", "HARNESS_TEST_ROWS": "github",
                                          "HARNESS_TEST_BUNDLES": "jira", "HARNESS_TEST_KEEP_ME": "x"}):
            env = T.suite_env("/hub", "/build")
        self.assertNotIn("HARNESS_TEST_GUARD_COVERED", env)
        self.assertNotIn("HARNESS_TEST_ROWS", env)
        self.assertNotIn("HARNESS_TEST_BUNDLES", env)
        self.assertEqual(env["HARNESS_TEST_KEEP_ME"], "x")
        self.assertEqual(env["HARNESS_HOME"], "/hub")
        self.assertEqual(env["HARNESS_BUILD_DIR"], "/build")


class GuardCoveredTest(unittest.TestCase):
    """run() sets HARNESS_TEST_GUARD_COVERED=1 on non-guard suites only when `guard` runs too."""

    def _run(self, suites):
        envs = {}

        def call(argv, cwd=None, env=None, stdout=None, stderr=None):
            envs[argv[-1]] = dict(env)
            stdout.write(b"ok\n")
            return 0

        out = io.StringIO()
        with mock.patch.dict(os.environ, {"HARNESS_TEST_GUARD_COVERED": "1", "HARNESS_TEST_ROWS": "x"}), \
                mock.patch.object(T, "hub_home", return_value="/hub"), \
                mock.patch.object(T, "discover", return_value=suites), \
                mock.patch.object(T, "build_all_guard", return_value="/b/guard-bash.sh"), \
                mock.patch.object(T.subprocess, "call", side_effect=call), \
                mock.patch.object(sys, "stdout", out):
            rc = T.run(None, "all")
        self.assertEqual(rc, 0, out.getvalue())
        return envs

    def test_all_run_marks_non_guard_suites_covered(self):
        envs = self._run([("unit", ["python3", "unit"], {}),
                          ("guard", ["bash", "guard"], {"__guard__": "1"}),
                          ("bundles/core/tests/run.sh", ["bash", "core"], {})])
        self.assertEqual(envs["unit"].get("HARNESS_TEST_GUARD_COVERED"), "1")
        self.assertEqual(envs["core"].get("HARNESS_TEST_GUARD_COVERED"), "1")
        self.assertNotIn("HARNESS_TEST_GUARD_COVERED", envs["guard"])
        self.assertEqual(envs["guard"]["GUARD_BASH"], "/b/guard-bash.sh")
        for e in envs.values():
            self.assertNotIn("HARNESS_TEST_ROWS", e)

    def test_core_only_run_is_not_covered(self):
        envs = self._run([("bundles/core/tests/run.sh", ["bash", "core"], {})])
        self.assertNotIn("HARNESS_TEST_GUARD_COVERED", envs["core"])

    def test_bundles_only_run_is_not_covered(self):
        envs = self._run([("bundles/core/tests/run.sh", ["bash", "core"], {}),
                          ("bundles/github/tests/run.sh", ["bash", "github"], {})])
        for e in envs.values():
            self.assertNotIn("HARNESS_TEST_GUARD_COVERED", e)

    def test_guard_covered_helper(self):
        self.assertTrue(T.guard_covered([("guard", [], {})]))
        self.assertFalse(T.guard_covered([("unit", [], {}), ("bundles/core/tests/run.sh", [], {})]))
        self.assertFalse(T.guard_covered([]))
        self.assertTrue(T.guard_covered([("unit", [], {}), ("guard[github]", [], {})]))


class ParseJobsTest(unittest.TestCase):
    def test_values(self):
        self.assertEqual(T.parse_jobs("1"), 1)
        self.assertEqual(T.parse_jobs("4"), 4)
        self.assertEqual(T.parse_jobs(3), 3)
        self.assertEqual(T.parse_jobs(" 2 "), 2)
        with mock.patch.object(T.os, "cpu_count", return_value=6):
            self.assertEqual(T.parse_jobs("auto"), 6)
        with mock.patch.object(T.os, "cpu_count", return_value=None):
            self.assertEqual(T.parse_jobs("auto"), 1)

    def test_errors(self):
        for bad in ("0", "-1", "x", "", "1.5", 0, -2, None, True):
            with self.assertRaises(RuntimeError, msg=repr(bad)):
                T.parse_jobs(bad)


def _script(path, body):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write("#!/usr/bin/env bash\n" + body + "\n")


class FakeHubTest(unittest.TestCase):
    """A throw-away hub with fake suites; run() and discover() against it for real (subprocesses)."""

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="harness-test-hub-")
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)
        b = os.path.join(self.home, "bundles")
        # the guard runner reports its row selection and the guard it got
        _script(os.path.join(b, "core", "guard", "tests", "run.sh"),
                'echo "rows=${HARNESS_TEST_ROWS:-all} guard=${GUARD_BASH:-none}"; echo "passed=1 failed=0"')
        for name, size in (("core", 10), ("github", 300), ("jira", 100)):
            _script(os.path.join(b, name, "guard.d", "tests.sh"), "#" * size)
        _script(os.path.join(b, "core", "tests", "run.sh"),
                'echo "covered=${HARNESS_TEST_GUARD_COVERED:-0} build=$HARNESS_BUILD_DIR"')
        _script(os.path.join(b, "github", "tests", "run.sh"), 'echo "github ok"')
        _script(os.path.join(b, "github", "skills", "s1", "scripts", "tests", "run.sh"), 'echo "s1 ok"')
        self.env = mock.patch.dict(os.environ, {"HARNESS_BUNDLES_ROOT": b})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.builds = []

    def build(self, home, build_dir):
        self.builds.append(build_dir)
        out = os.path.join(build_dir, "guard", "guard-bash.sh")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        open(out, "w").close()
        return out

    def run_test(self, suite, jobs=1, verbose=False):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(T, "hub_home", return_value=self.home), \
                mock.patch.object(T, "build_all_guard", side_effect=self.build), \
                mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", err):
            rc = T.run(None, suite, verbose=verbose, jobs=jobs)
        return rc, out.getvalue(), err.getvalue()

    # discover ---------------------------------------------------------------------------------
    def test_shard_names_and_env(self):
        entries = T.discover(self.home, ["guard"], shard=True)
        self.assertEqual([n for n, _a, _e in entries], ["guard[core]", "guard[github]", "guard[jira]"])
        for name, argv, extra in entries:
            self.assertEqual(extra, {"__guard__": "1", "HARNESS_TEST_ROWS": name[6:-1]})
            self.assertTrue(argv[-1].endswith(os.path.join("core", "guard", "tests", "run.sh")))
        self.assertEqual([n for n, _a, _e in T.discover(self.home, "guard")], ["guard"])

    def test_several_names_dedupe_in_first_seen_order(self):
        names = [n for n, _a, _e in T.discover(self.home, ["github", "skills", "bundles"])]
        self.assertEqual(names, ["bundles/github/tests/run.sh",
                                 "bundles/github/skills/s1/scripts/tests/run.sh",
                                 "bundles/core/tests/run.sh"])

    def test_all_anywhere_means_all(self):
        self.assertEqual(T.discover(self.home, ["github", "all"]), T.discover(self.home, "all"))
        self.assertEqual(T.discover(self.home, []), T.discover(self.home, "all"))

    def test_unknown_name_raises_and_run_rc_2(self):
        with self.assertRaises(RuntimeError):
            T.discover(self.home, ["github", "nosuch"])
        rc, out, err = self.run_test(["github", "nosuch"])
        self.assertEqual(rc, 2)
        self.assertIn("harness: unknown suite or bundle 'nosuch'", err)
        rc, _out, err = self.run_test("github", jobs="0")
        self.assertEqual(rc, 2)
        self.assertIn("harness: --jobs", err)

    def test_submit_order_longest_first(self):
        entries = T.discover(self.home, ["bundles", "guard"], shard=True)
        order = [entries[i][0] for i in T._submit_order(entries, os.path.join(self.home, "bundles"))]
        self.assertEqual(order, ["guard[github]", "guard[jira]", "guard[core]",
                                 "bundles/core/tests/run.sh", "bundles/github/tests/run.sh"])

    # run --------------------------------------------------------------------------------------
    def test_jobs_1_has_no_shard_names(self):
        rc, out, _err = self.run_test(["guard", "bundles"])
        self.assertEqual(rc, 0, out)
        self.assertNotIn("guard[", out)
        self.assertRegex(out, r"(?m)^PASS  guard +passed=1 failed=0")
        self.assertIn("test: 3 suite(s), 0 failed", out)

    def test_one_guard_build_shared_across_shards(self):
        rc, out, _err = self.run_test(["guard"], jobs=3, verbose=True)
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(self.builds), 1)
        guard = os.path.join(self.builds[0], "guard", "guard-bash.sh")
        for b in ("core", "github", "jira"):
            self.assertRegex(out, r"(?m)^PASS  guard\[%s\] " % b)
            self.assertIn("rows=%s guard=%s" % (b, guard), out)
        self.assertFalse(os.path.exists(self.builds[0]), "run-level guard dir is removed")

    def test_covered_propagates_under_shards(self):
        rc, out, _err = self.run_test(["guard", "core"], jobs=2, verbose=True)
        self.assertEqual(rc, 0, out)
        self.assertIn("covered=1", out)
        rc, out, _err = self.run_test(["core"], jobs=2, verbose=True)
        self.assertIn("covered=0", out)

    def test_guard_build_failure_fails_each_guard_entry(self):
        out = io.StringIO()
        with mock.patch.object(T, "hub_home", return_value=self.home), \
                mock.patch.object(T, "build_all_guard", side_effect=RuntimeError("boom")), \
                mock.patch.object(sys, "stdout", out):
            rc = T.run(None, ["guard", "github"], jobs=2)
        self.assertEqual(rc, 1)
        self.assertEqual(out.getvalue().count("could not build the guard: boom"), 3)
        self.assertIn("test: 5 suite(s), 3 failed", out.getvalue())

    def test_output_in_discovery_order_when_first_is_slowest(self):
        b = os.path.join(self.home, "bundles")
        _script(os.path.join(b, "core", "tests", "run.sh"), 'sleep 1; echo "core done"')
        rc, out, _err = self.run_test(["bundles", "skills"], jobs=3)
        self.assertEqual(rc, 0, out)
        names = [ln.split()[1] for ln in out.splitlines() if ln.startswith("PASS")]
        self.assertEqual(names, ["bundles/core/tests/run.sh", "bundles/github/tests/run.sh",
                                 "bundles/github/skills/s1/scripts/tests/run.sh"])

    def test_suites_overlap_under_jobs(self):
        b = os.path.join(self.home, "bundles")
        marks = os.path.join(self.home, "marks")
        os.makedirs(marks)
        # each waits until the other has started: only finishes when both run at once
        body = 'touch "%s/$1"; for i in $(seq 50); do [ -e "%s/$2" ] && { echo ok; exit 0; }; sleep 0.1; done; exit 1'
        _script(os.path.join(b, "core", "tests", "run.sh"), 'set -- core github\n' + body % (marks, marks))
        _script(os.path.join(b, "github", "tests", "run.sh"), 'set -- github core\n' + body % (marks, marks))
        rc, out, _err = self.run_test(["bundles"], jobs=2)
        self.assertEqual(rc, 0, out)

    def test_failing_suite_rc_1_with_excerpt(self):
        b = os.path.join(self.home, "bundles")
        _script(os.path.join(b, "github", "tests", "run.sh"),
                'echo "FAIL row one"; echo "ok row"; echo "passed=1 failed=1"; exit 1')
        rc, out, _err = self.run_test(["bundles"], jobs=2)
        self.assertEqual(rc, 1)
        self.assertRegex(out, r"(?m)^FAIL  bundles/github/tests/run.sh rc=1 passed=1 failed=1$")
        self.assertIn("      FAIL row one", out)
        self.assertNotIn("ok row", out)
        self.assertIn("test: 2 suite(s), 1 failed", out)

    def test_serial_entries_run_alone(self):
        b = os.path.join(self.home, "bundles")
        running = os.path.join(self.home, "running")
        body = 'f="%s"; [ -e "$f" ] && { echo "FAIL overlap"; exit 1; }; touch "$f"; sleep 0.3; rm -f "$f"; echo ok'
        _script(os.path.join(b, "core", "tests", "run.sh"), body % running)
        _script(os.path.join(b, "github", "tests", "run.sh"), body % running)
        with mock.patch.object(T, "SERIAL", frozenset({"bundles/core/tests/run.sh"})):
            rc, out, _err = self.run_test(["bundles"], jobs=2)
        self.assertEqual(rc, 0, out)
        names = [ln.split()[1] for ln in out.splitlines() if ln.startswith("PASS")]
        self.assertEqual(names, ["bundles/core/tests/run.sh", "bundles/github/tests/run.sh"])


if __name__ == "__main__":
    unittest.main()
