"""harness pack / verify / bootstrap --from against a throw-away fixture repository."""
from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import unittest

from helpers import REPO  # noqa: E402,F401  (puts lib/ on sys.path)

from harness import bootstrap as B
from harness import pack as P
from harness import upgrade as U
from harness.util import HarnessError

GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0",
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
}


def sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


class PackTest(unittest.TestCase):
    def setUp(self):
        self._env = {k: os.environ.get(k) for k in list(GIT_ENV) + ["HARNESS_TOOLS_MIRROR"]}
        os.environ.update(GIT_ENV)
        os.environ.pop("HARNESS_TOOLS_MIRROR", None)
        self.tmp = tempfile.mkdtemp(prefix="harness-pack-")
        self.repo = os.path.join(self.tmp, "hub")
        self.out = os.path.join(self.tmp, "rel")
        os.makedirs(os.path.join(self.repo, "tools"))
        self.write("VERSION", "1.2.3\n")
        self.write(".gitignore", "/local/\n/build/\n")
        self.write("bootstrap", "#!/usr/bin/env bash\necho fixture\n")
        self.write("local/harness.toml", "secret = 'never packed'\n")  # ignored  # pragma: allowlist secret
        self.git("init", "-q", "-b", "main")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "fixture")
        self.logs = []

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, rel, text, root=None):
        path = os.path.join(root or self.repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def git(self, *args, cwd=None):
        return subprocess.run(["git"] + list(args), cwd=cwd or self.repo, check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode()

    def pack(self, **kw):
        return P.pack(self.repo, self.out, log=self.logs.append, **kw)

    # ------------------------------------------------------------------ pack
    def test_pack_writes_bundle_sums_and_install(self):
        res = self.pack()
        head = self.git("rev-parse", "--short=7", "HEAD").strip()
        name = "harness-hub-v1.2.3-g%s.bundle" % head
        self.assertEqual(os.path.basename(res["bundle"]), name)
        self.assertEqual(sorted(os.listdir(self.out)), sorted([name, "INSTALL.txt", "SHA256SUMS"]))
        sums = P.read_sums(os.path.join(self.out, "SHA256SUMS"))
        self.assertEqual(sorted(sums), sorted([name, "INSTALL.txt"]))
        for rel, want in sums.items():
            self.assertEqual(sha(os.path.join(self.out, rel)), want)
        self.assertIn("git clone %s ~/harness-hub" % name, self.read(os.path.join(self.out, "INSTALL.txt")))
        self.assertIn("refs/heads/main", res["heads"])
        self.assertIn("HEAD", res["heads"])

    def test_exact_tag_names_the_bundle(self):
        self.git("tag", "-a", "v1.2.3", "-m", "r")
        res = self.pack()
        self.assertTrue(res["bundle"].endswith("harness-hub-v1.2.3.bundle"))

    def test_tag_mode(self):
        self.git("tag", "-a", "v1.2.3", "-m", "r")
        res = self.pack(tag="v1.2.3")
        self.assertEqual(res["heads"], ["refs/tags/v1.2.3"])
        self.assertIn("git clone -b v1.2.3 ", self.read(os.path.join(self.out, "INSTALL.txt")))
        with self.assertRaises(HarnessError):
            self.pack(tag="v9.9.9")

    def test_verify_ok(self):
        res = self.pack()
        rep = P.verify(res["bundle"])
        self.assertTrue(rep["ok"], rep)
        self.assertTrue(rep["sha256sums"])
        self.assertIn(os.path.basename(res["bundle"]), rep["checked"])
        self.assertIn("refs/heads/main", rep["heads"])

    def test_verify_detects_tampering(self):
        res = self.pack()
        with open(os.path.join(self.out, "INSTALL.txt"), "a", encoding="utf-8") as fh:
            fh.write("tampered\n")
        rep = P.verify(res["bundle"])
        self.assertFalse(rep["ok"])
        self.assertIn("sha256 mismatch: INSTALL.txt", rep["problems"])

    def test_verify_rejects_garbage(self):
        bad = self.write("x.bundle", "not a bundle\n", root=self.tmp)
        self.assertFalse(P.verify(bad)["ok"])

    def test_verify_without_sums(self):
        res = self.pack()
        os.unlink(os.path.join(self.out, "SHA256SUMS"))
        rep = P.verify(res["bundle"])
        self.assertTrue(rep["ok"])
        self.assertFalse(rep["sha256sums"])

    def test_dirty_tree_refused(self):
        self.write("new.txt", "untracked\n")
        with self.assertRaises(HarnessError) as cm:
            self.pack()
        self.assertIn("dirty", str(cm.exception))
        os.unlink(os.path.join(self.repo, "new.txt"))
        self.write("VERSION", "1.2.4\n")  # modified tracked file
        with self.assertRaises(HarnessError):
            self.pack()
        self.assertFalse(os.path.exists(self.out))

    def test_local_excluded(self):
        res = self.pack()
        clone = os.path.join(self.tmp, "clone")
        self.git("clone", "-q", res["bundle"], clone, cwd=self.tmp)
        self.assertTrue(os.path.isfile(os.path.join(clone, "VERSION")))
        self.assertFalse(os.path.exists(os.path.join(clone, "local")))
        self.assertEqual(self.git("ls-tree", "-r", "--name-only", "HEAD", "--", "local", cwd=clone), "")

    def test_tracked_local_refused(self):
        self.git("add", "-f", "local/harness.toml")
        self.git("commit", "-q", "-m", "oops")
        with self.assertRaises(HarnessError) as cm:
            self.pack()
        self.assertIn("local/", str(cm.exception))
        # removing it at the tip is not enough: history still carries it
        self.git("rm", "-q", "--cached", "local/harness.toml")
        self.git("commit", "-q", "-m", "remove")
        with self.assertRaises(HarnessError) as cm:
            self.pack()
        self.assertIn("history:local/harness.toml", str(cm.exception))

    # ------------------------------------------------------------------ tools
    def _lock(self, data, verified=True, digest=None):
        asset = os.path.join(self.tmp, "fake_1.0_linux_amd64.tar.gz")
        with open(asset, "wb") as fh:
            fh.write(data)
        lock = {"tool": "fake", "version": "1.0", "verified": verified,
                "assets": {"linux/amd64": {"url": "file://" + asset, "archive": "tar.gz", "binary": "fake",
                                           "sha256": digest if digest is not None else hashlib.sha256(data).hexdigest()}}}
        self.write("tools/fake.lock.json", json.dumps(lock))
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "lock")

    def _targz(self):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tf:
            info = tarfile.TarInfo("fake")
            info.size = 3
            tf.addfile(info, io.BytesIO(b"hi\n"))
        return buf.getvalue()

    def test_tools_downloaded_and_summed(self):
        self._lock(self._targz())
        res = self.pack(platforms=["linux/amd64", "darwin/arm64"])
        self.assertEqual(res["problems"], [])
        self.assertIn("tools/fake_1.0_linux_amd64.tar.gz", res["files"])
        sums = P.read_sums(os.path.join(self.out, "SHA256SUMS"))
        self.assertIn("tools/fake_1.0_linux_amd64.tar.gz", sums)
        self.assertTrue(P.verify(res["bundle"])["ok"])
        self.assertTrue(any("no darwin/arm64 asset" in ln for ln in self.logs))

    def test_tools_bad_sha_not_shipped(self):
        self._lock(self._targz(), digest="0" * 64)
        res = self.pack(platforms=["linux/amd64"])
        self.assertEqual(len(res["problems"]), 1)
        self.assertIn("mismatch", res["problems"][0])
        self.assertFalse(os.path.exists(os.path.join(self.out, "tools")))

    def test_tools_offline_and_unverified(self):
        self._lock(self._targz())
        res = self.pack(platforms=["linux/amd64"], offline=True)
        self.assertIn("offline", res["problems"][0])
        self.assertTrue(os.path.isfile(res["bundle"]))  # the bundle is still written
        self._lock(self._targz(), verified=False)
        res = self.pack(platforms=["linux/amd64"])
        self.assertIn("not verified", res["problems"][0])

    def test_bad_platform(self):
        with self.assertRaises(HarnessError):
            self.pack(platforms=["windows/amd64"])

    # ------------------------------------------------------------------ bootstrap --from
    def test_passthrough_args(self):
        self.assertEqual(
            B.passthrough_args(["--home", "/h", "bootstrap", "--from", "x.bundle", "--dest=/d", "--origin", "u",
                                "--yes", "--bundles", "core", "--config", "c.toml"]),
            ["--yes", "--bundles", "core", "--config", "c.toml"])

    def test_from_bundle_refuses_non_empty_dest(self):
        res = self.pack()

        class NS:
            from_ = res["bundle"]
            dest = self.repo
            origin = None

        class Ctx:
            dry_run = False
            argv = []

        with self.assertRaises(HarnessError) as cm:
            B.from_bundle(Ctx(), NS())
        self.assertIn("not empty", str(cm.exception))

    # ------------------------------------------------------------------ upgrade --to offline
    def test_upgrade_uses_local_tag_when_fetch_fails(self):
        self.git("tag", "-a", "v1.2.3", "-m", "r")
        self.git("commit", "-q", "--allow-empty", "-m", "after")
        self.git("remote", "add", "origin", os.path.join(self.tmp, "nowhere.bundle"))
        logs = []
        U.checkout_tag(self.repo, "v1.2.3", log=logs.append)
        self.assertEqual(logs, ["note: fetch failed; using local tag v1.2.3"])
        self.assertEqual(self.git("rev-parse", "HEAD").strip(), self.git("rev-parse", "v1.2.3^{commit}").strip())

    def test_upgrade_missing_tag_names_the_bundle_flow(self):
        self.git("remote", "add", "origin", os.path.join(self.tmp, "nowhere.bundle"))
        with self.assertRaises(HarnessError) as cm:
            U.checkout_tag(self.repo, "v9.9.9", log=lambda *a: None)
        self.assertIn("remote set-url origin /path/NEW.bundle", str(cm.exception))
        self.assertIn("refs/tags/*:refs/tags/*", str(cm.exception))

    def test_upgrade_from_a_newer_bundle(self):
        self.git("tag", "-a", "v1.2.3", "-m", "r")
        first = self.pack(tag="v1.2.3")["bundle"]
        clone = os.path.join(self.tmp, "clone")
        self.git("clone", "-q", "-b", "v1.2.3", first, clone, cwd=self.tmp)
        self.write("VERSION", "1.2.4\n")
        self.git("commit", "-q", "-am", "next")
        self.git("tag", "-a", "v1.2.4", "-m", "r")
        self.out = os.path.join(self.tmp, "rel2")
        newer = self.pack(tag="v1.2.4")["bundle"]
        self.git("remote", "set-url", "origin", newer, cwd=clone)
        logs = []
        U.checkout_tag(clone, "v1.2.4", log=logs.append)
        self.assertEqual(logs, [])
        self.assertEqual(self.read(os.path.join(clone, "VERSION")), "1.2.4\n")
        self.assertIn("remote set-url origin /path/NEW.bundle", self.read(os.path.join(self.out, "INSTALL.txt")))

    @staticmethod
    def read(path):
        with open(path, encoding="utf-8") as fh:
            return fh.read()


if __name__ == "__main__":
    unittest.main()
