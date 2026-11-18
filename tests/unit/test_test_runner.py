"""``harness test`` runner: each guard row runs once per run (HARNESS_TEST_GUARD_COVERED)."""
from __future__ import annotations

import io
import os
import sys
import unittest
from unittest import mock

from helpers import REPO  # noqa: E402,F401  (puts lib/ on sys.path)

from harness import test as T


class SuiteEnvScrubTest(unittest.TestCase):
    def test_inherited_row_knobs_are_dropped(self):
        with mock.patch.dict(os.environ, {"HARNESS_TEST_GUARD_COVERED": "1", "HARNESS_TEST_ROWS": "github",
                                          "HARNESS_TEST_KEEP_ME": "x"}):
            env = T.suite_env("/hub", "/build")
        self.assertNotIn("HARNESS_TEST_GUARD_COVERED", env)
        self.assertNotIn("HARNESS_TEST_ROWS", env)
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
                          ("guard", ["bash", "guard"], {"__build_guard__": "1"}),
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


if __name__ == "__main__":
    unittest.main()
