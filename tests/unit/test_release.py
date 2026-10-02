"""harness release check | notes against a throw-away fixture repository."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest

from helpers import REPO  # noqa: E402,F401  (puts lib/ on sys.path)

from harness import pack as P
from harness import release as R
from harness.util import HarnessError

GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0",
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
}

CHANGELOG = """# Changelog

## [Unreleased]

## [{v}] - 2026-09-30

### Added

- the first thing

[Unreleased]: https://example.com/compare/v{v}...HEAD
[{v}]: https://example.com/releases/tag/v{v}
"""


class ReleaseCheckTest(unittest.TestCase):
    def setUp(self):
        self._env = {k: os.environ.get(k) for k in list(GIT_ENV) + ["GITHUB_REPOSITORY"]}
        os.environ.update(GIT_ENV)
        os.environ["GITHUB_REPOSITORY"] = "owner/repo"
        self.tmp = tempfile.mkdtemp(prefix="harness-release-")
        self.repo = os.path.join(self.tmp, "hub")
        os.makedirs(self.repo)
        self.git("init", "-q", "-b", "main")
        self.release("1.2.3")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")

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

    def write(self, rel, text):
        path = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def release(self, version, changelog=None, tag=True, annotated=True):
        self.write("VERSION", version + "\n")
        self.write("CHANGELOG.md", changelog if changelog is not None else CHANGELOG.format(v=version))
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "release %s" % version)
        if tag:
            if annotated:
                self.git("tag", "-a", "v" + version, "-m", "harness-hub v" + version)
            else:
                self.git("tag", "v" + version)

    def check(self, tag, **kw):
        kw.setdefault("remote", "origin")
        return R.check(self.repo, tag, **kw)

    def assertProblem(self, res, needle):
        self.assertFalse(res["ok"], res)
        self.assertTrue(any(needle in p for p in res["problems"]), res["problems"])

    def test_ok(self):
        res = self.check("v1.2.3")
        self.assertTrue(res["ok"], res)
        self.assertEqual((res["version"], res["prerelease"]), ("1.2.3", False))
        self.assertEqual(res["commit"], self.git("rev-parse", "HEAD").strip())
        self.assertTrue(any("annotated" in i for i in res["info"]))
        # no origin remote is configured: the fetch only warns, the local ref decides
        self.assertTrue(any("git fetch origin main failed" in w for w in res["warnings"]), res["warnings"])
        json.dumps(res)
        self.assertTrue(R.check(self.repo, None, fetch=False)["ok"])  # the tag on HEAD

    def test_lightweight_tag(self):
        self.git("tag", "-d", "v1.2.3")
        self.git("tag", "v1.2.3")
        self.assertProblem(self.check("v1.2.3"), "lightweight")

    def test_missing_tag(self):
        self.assertProblem(self.check("v9.9.9"), "does not exist")

    def test_version_mismatch(self):
        self.release("1.2.4", changelog=CHANGELOG.format(v="1.2.5"), tag=False)
        self.git("tag", "-a", "v1.2.5", "-m", "r")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.assertProblem(self.check("v1.2.5"), "VERSION at v1.2.5 is '1.2.4'")

    def test_missing_section(self):
        self.release("1.2.4", changelog="# Changelog\n\n## [Unreleased]\n\n## [1.2.3] - 2026-09-30\n- a\n")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        res = self.check("v1.2.4")
        self.assertProblem(res, "no '## [1.2.4] - YYYY-MM-DD' heading")
        self.assertTrue(any("link line" in w for w in res["warnings"]))

    def test_bad_date(self):
        self.release("1.2.4", changelog=CHANGELOG.format(v="1.2.4").replace("2026-09-30", "2026-13-40"))
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.assertProblem(self.check("v1.2.4"), "YYYY-MM-DD")

    def test_leftover_unreleased(self):
        text = CHANGELOG.format(v="1.2.4").replace("## [Unreleased]\n", "## [Unreleased]\n\n### Fixed\n\n- stray\n")
        self.release("1.2.4", changelog=text)
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.assertProblem(self.check("v1.2.4"), "[Unreleased] still holds")

    def test_non_semver_and_build_tags(self):
        for bad in ("v1.2", "1.2.3", "vnext", "v01.2.3"):
            self.assertProblem(self.check(bad), "not SemVer 2.0.0")
        self.git("tag", "-a", "v1.2.3+build.7", "-m", "r")
        self.assertProblem(self.check("v1.2.3+build.7"), "+build")

    def test_not_on_main(self):
        self.git("checkout", "-q", "-b", "side")
        self.release("1.2.4")
        res = self.check("v1.2.4")
        self.assertProblem(res, "is not on origin/main")
        self.assertTrue(self.check("v1.2.4", fetch=False)["ok"])  # --no-remote rehearsal

    def test_dirty_tree_and_head_elsewhere(self):
        self.write("new.txt", "x\n")
        self.assertProblem(self.check("v1.2.3"), "dirty")
        os.unlink(os.path.join(self.repo, "new.txt"))
        self.git("commit", "-q", "--allow-empty", "-m", "after")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        res = self.check("v1.2.3")
        self.assertTrue(res["ok"], res)
        self.assertTrue(any("not the tag commit" in w for w in res["warnings"]))

    def test_tracked_local(self):
        self.write("local/harness.toml", "x = 1\n")
        self.git("add", "-f", "local/harness.toml")
        self.git("commit", "-q", "-m", "oops")
        self.git("rm", "-q", "--cached", "local/harness.toml")
        os.unlink(os.path.join(self.repo, "local/harness.toml"))
        self.release("1.2.4")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.assertProblem(self.check("v1.2.4"), "local/")

    def test_tool_asset_clash(self):
        lock = {"tool": "a", "version": "1", "verified": True,
                "assets": {"linux/amd64": {"url": "https://example.com/x/same.tar.gz", "sha256": "0" * 64}}}
        self.write("tools/a.lock.json", json.dumps(lock))
        lock["tool"] = "b"
        self.write("tools/b.lock.json", json.dumps(lock))
        self.release("1.2.4")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.assertProblem(self.check("v1.2.4"), "unique basenames")

    def test_prerelease(self):
        self.release("1.3.0-rc.1")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        res = self.check("v1.3.0-rc.1")
        self.assertTrue(res["ok"], res)
        self.assertTrue(res["prerelease"])

    # ------------------------------------------------------------------ notes
    def test_notes(self):
        rel = os.path.join(self.tmp, "rel")
        P.pack(self.repo, rel, tag="v1.2.3", self_extract=True, log=lambda *a: None)
        text = R.notes(self.repo, "v1.2.3", rel_dir=rel)
        self.assertTrue(text.startswith("# harness-hub v1.2.3\n"))
        self.assertIn("### Added\n\n- the first thing", text)
        self.assertNotIn("[1.2.3]: https://", text)
        self.assertIn("sh harness-hub-v1.2.3.run --check", text)
        self.assertIn("git clone -b v1.2.3 harness-hub-v1.2.3.bundle ~/harness-hub", text)
        self.assertIn("gh attestation verify harness-hub-v1.2.3.bundle -R owner/repo", text)
        self.assertIn("## SHA256SUMS\n\n```\n", text)
        with open(os.path.join(rel, "SHA256SUMS"), encoding="utf-8") as fh:
            self.assertIn(fh.read().rstrip("\n"), text)
        self.assertNotIn("Pre-release", text)

    def test_notes_prerelease_and_missing_section(self):
        self.release("1.3.0-rc.1")
        text = R.notes(self.repo, "v1.3.0-rc.1")
        self.assertIn("Pre-release", text)
        self.assertIn("--to v1.3.0-rc.1", text)
        with self.assertRaises(HarnessError):
            R.notes(self.repo, "v9.9.9")


if __name__ == "__main__":
    unittest.main()
