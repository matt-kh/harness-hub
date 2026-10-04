"""SemVer 2.0.0 helpers (util), changelog ordering and upgrade target resolution."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest

from helpers import REPO  # noqa: E402,F401  (puts lib/ on sys.path)

from harness import upgrade as U
from harness.util import is_prerelease, parse_semver, version_key

GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0",
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
}


class SemverTest(unittest.TestCase):
    def test_spec_precedence_example(self):
        # SemVer 2.0.0 §11, the example chain
        seq = ["1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta", "1.0.0-beta", "1.0.0-beta.2",
               "1.0.0-beta.11", "1.0.0-rc.1", "1.0.0"]
        self.assertEqual(sorted(reversed(seq), key=version_key), seq)
        for lo, hi in zip(seq, seq[1:]):
            self.assertLess(version_key(lo), version_key(hi))
        self.assertLess(version_key("1.9.0"), version_key("1.10.0"))
        self.assertLess(version_key("v1.0.0"), version_key("2.0.0-rc.1"))

    def test_build_metadata_is_ignored(self):
        self.assertEqual(version_key("1.0.0+a.1"), version_key("1.0.0+b"))
        self.assertEqual(parse_semver("v1.2.3-rc.1+exp.sha.5114f85"), (1, 2, 3, ("rc", "1"), "exp.sha.5114f85"))

    def test_strictness(self):
        for bad in ("1.2", "v1", "01.2.3", "1.2.3-01", "1.2.3-", "1.2.3+", "vnext", "1.2.3.4", ""):  # gate-allow: version string, not an IP
            self.assertIsNone(parse_semver(bad), bad)
        self.assertTrue(is_prerelease("v1.3.0-rc.1"))
        self.assertFalse(is_prerelease("v1.3.0"))
        self.assertFalse(is_prerelease("garbage"))

    def test_loose_fallback(self):
        self.assertEqual(version_key("1.2"), version_key("1.2.0"))
        self.assertLess(version_key("0.1"), version_key("0.1.1"))
        self.assertLess(version_key(""), version_key("0.0.1"))
        # dev pack names sort as their core release
        self.assertEqual(version_key("v1.2.3-g0abc123")[:3], (1, 2, 3))

    def test_changelog_with_prereleases(self):
        text = ("# Changelog\n\n## [Unreleased]\n\n## [1.3.0] - 2026-11-02\n- final\n\n"
                "## [1.3.0-rc.1] - 2026-11-01\n- rc\n\n## [1.2.4] - 2026-10-01\n- b\n\n"
                "## [1.2.3] - 2026-09-30\n- a\n\n[1.3.0]: https://example.com/c\n")
        got = U.changelog_between(text, "1.2.3", "1.3.0")
        self.assertEqual([v for v, _b in got], ["1.3.0", "1.3.0-rc.1", "1.2.4"])
        self.assertEqual([v for v, _b in U.changelog_between(text, "1.2.4", "1.3.0-rc.1")], ["1.3.0-rc.1"])
        self.assertEqual(U.changelog_section(text, "v1.3.0-rc.1"), "- rc")
        self.assertEqual(U.changelog_section(text, "1.2.3"), "- a")
        self.assertIsNone(U.changelog_section(text, "9.9.9"))


class WorkflowGateTest(unittest.TestCase):
    """release.yml's gate inlines SEMVER_RE as POSIX ERE; both must accept the same tag names."""

    def test_gate_regex_matches_util(self):
        import re

        from harness.util import SEMVER_RE

        with open(os.path.join(REPO, ".github", "workflows", "release.yml"), encoding="utf-8") as fh:
            m = re.search(r"SEMVER_ERE='([^']+)'", fh.read())
        self.assertIsNotNone(m, "release.yml lost its SEMVER_ERE line")
        ere = re.compile(m.group(1))
        samples = ["v1.2.3", "v0.0.0", "v1.2.3-rc.1", "v1.0.0-alpha.beta.1", "v1.0.0-0.3.7", "v1.0.0-x-y.7z.92",
                   "v1.2.3+build.5", "v1.2.3-rc.1+exp.sha.5114f85", "v10.20.30",
                   "1.2.3", "v1", "v1.2", "vnext", "v01.2.3", "v1.02.3", "v1.2.3-01", "v1.2.3-", "v1.2.3+",
                   "v1.2.3.4", "v1.2.3-rc..1", "V1.2.3", "v1.2.3 ", "v\u0661.2.3", ""]  # gate-allow: version string, not an IP
        for tag in samples:
            want = bool(SEMVER_RE.match(tag)) and tag.startswith("v")
            self.assertEqual(bool(ere.search(tag)), want, tag)

    def test_util_regex_is_ascii_and_anchored_at_the_very_end(self):
        from harness.util import SEMVER_RE

        self.assertTrue(SEMVER_RE.match("v1.2.3"))
        for tag in ("v1.2.3\n", "v\u0661.2.3", "v1.\u0662.3", "v1.2.3-rc.\u0663", "1.2.3\n"):
            self.assertIsNone(SEMVER_RE.match(tag), repr(tag))


class TargetTest(unittest.TestCase):
    def setUp(self):
        self._env = {k: os.environ.get(k) for k in GIT_ENV}
        os.environ.update(GIT_ENV)
        self.tmp = tempfile.mkdtemp(prefix="harness-semver-")
        self.repo = os.path.join(self.tmp, "hub")
        os.makedirs(self.repo)
        self.git("init", "-q", "-b", "main")
        self.git("commit", "-q", "--allow-empty", "-m", "one")

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def git(self, *args, cwd=None):
        return subprocess.run(["git"] + list(args), cwd=cwd or self.repo, check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode()

    def test_latest_release_tag_skips_prereleases(self):
        self.assertIsNone(U.latest_release_tag(self.repo))
        for t in ("v1.2.3", "v1.2.4", "v1.3.0-rc.1", "v1.10.0-beta", "nightly", "1.9.9"):
            self.git("tag", "-a", t, "-m", t)
        self.assertEqual(U.latest_release_tag(self.repo), "v1.2.4")
        self.assertEqual(U.resolve_target(self.repo, None, offline=True), ("tag", "v1.2.4"))
        self.assertEqual(U.resolve_target(self.repo, "latest", offline=True), ("tag", "v1.2.4"))

    def test_resolve_branch_and_tag(self):
        self.assertEqual(U.resolve_target(self.repo, "main", offline=True), ("branch", "main"))
        self.assertTrue(U.is_branch(self.repo, "main"))
        self.assertEqual(U.resolve_target(self.repo, "v1.0.0", offline=True), ("tag", "v1.0.0"))

    def test_no_release_tag_names_the_alternatives(self):
        with self.assertRaises(Exception) as cm:
            U.resolve_target(self.repo, None, offline=True)
        msg = str(cm.exception)
        self.assertIn("--to main", msg)
        self.assertIn("NEW.bundle", msg)

    def test_main_in_a_tag_only_clone(self):
        self.git("tag", "-a", "v1.0.0", "-m", "r")
        clone = os.path.join(self.tmp, "clone")
        bundle = os.path.join(self.tmp, "t.bundle")
        self.git("bundle", "create", "-q", bundle, "--tags")
        self.git("clone", "-q", "-b", "v1.0.0", bundle, clone, cwd=self.tmp)
        kind, target = U.resolve_target(clone, "main", offline=True)
        self.assertEqual((kind, target), ("tag", "main"))
        with self.assertRaises(Exception) as cm:
            U.checkout_tag(clone, "main", log=lambda *a: None)
        self.assertIn("tag-only bundle", str(cm.exception))
        self.assertIn("--to TAG", str(cm.exception))



class UpgradeLatestTest(unittest.TestCase):
    """``harness upgrade`` (default --to latest) never moves a checkout backwards; --to TAG pins."""

    def setUp(self):
        keys = list(GIT_ENV) + ["HARNESS_HOME"]
        self._env = {k: os.environ.get(k) for k in keys}
        os.environ.update(GIT_ENV)
        self.tmp = tempfile.mkdtemp(prefix="harness-upgrade-")
        self.repo = os.path.join(self.tmp, "hub")
        os.makedirs(self.repo)
        os.environ["HARNESS_HOME"] = self.repo
        self.git("init", "-q", "-b", "main")
        self.commit("1.2.3")
        self.git("tag", "-a", "v1.2.3", "-m", "r")

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def git(self, *args):
        return subprocess.run(["git"] + list(args), cwd=self.repo, check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode()

    def commit(self, version):
        with open(os.path.join(self.repo, "VERSION"), "w", encoding="utf-8") as fh:
            fh.write(version + "\n")
        self.git("add", "VERSION")
        self.git("commit", "-q", "-m", version)

    def upgrade(self, to=None):
        import contextlib
        import io
        from unittest import mock

        class Ctx:
            dry_run = False
            offline = True
            config = None
            yes = True

        class NS:
            no_apply = True

        NS.to = to
        out = io.StringIO()
        with mock.patch("subprocess.call", return_value=0) as call, contextlib.redirect_stdout(out):
            rc = U.run(Ctx(), NS())
        return rc, out.getvalue(), call

    def head(self):
        return self.git("rev-parse", "HEAD").strip()

    def test_latest_does_not_move_a_checkout_ahead_of_the_newest_tag(self):
        self.commit("1.3.0")  # main ahead of v1.2.3
        before = self.head()
        rc, out, call = self.upgrade()
        self.assertEqual(rc, 0)
        self.assertIn("hub 1.3.0 is at or ahead of the newest release v1.2.3; nothing to upgrade", out)
        self.assertIn("--to TAG", out)
        self.assertIn("--to BRANCH", out)
        self.assertEqual(self.head(), before)
        call.assert_not_called()

    def test_latest_at_the_newest_tag_is_a_no_op(self):
        rc, out, call = self.upgrade("latest")
        self.assertEqual(rc, 0)
        self.assertIn("nothing to upgrade", out)
        call.assert_not_called()

    def test_latest_moves_forward_to_a_newer_tag(self):
        self.commit("1.2.4")
        self.git("tag", "-a", "v1.2.4", "-m", "r")
        self.git("checkout", "-q", "v1.2.3")
        rc, out, call = self.upgrade()
        self.assertEqual(rc, 0)
        self.assertIn("hub 1.2.3 -> 1.2.4", out)
        self.assertEqual(self.head(), self.git("rev-parse", "v1.2.4^{commit}").strip())
        self.assertTrue(call.called)  # plan ran

    def test_explicit_tag_still_pins_backwards(self):
        self.commit("1.3.0")
        rc, out, _call = self.upgrade("v1.2.3")
        self.assertEqual(rc, 0)
        self.assertIn("hub 1.3.0 -> 1.2.3", out)
        self.assertEqual(self.head(), self.git("rev-parse", "v1.2.3^{commit}").strip())

    def test_tag_version_falls_back_to_the_tag_name(self):
        self.git("rm", "-q", "VERSION")
        self.git("commit", "-q", "-m", "no version")
        self.git("tag", "-a", "v2.0.0", "-m", "r")
        self.assertEqual(U.tag_version(self.repo, "v2.0.0"), "2.0.0")
        self.assertEqual(U.tag_version(self.repo, "v1.2.3"), "1.2.3")
        self.assertTrue(U.newer_release(self.repo, "v2.0.0", "1.9.9"))
        self.assertFalse(U.newer_release(self.repo, "v1.2.3", "1.2.3"))


if __name__ == "__main__":
    unittest.main()
