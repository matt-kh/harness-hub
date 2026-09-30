"""harness install: lock parsing, sha256 verification, extraction, refusal rules, mirror."""
from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import tarfile
import tempfile
import unittest
import zipfile

from helpers import REPO  # noqa: E402

from harness import tools as T
from harness.util import HarnessError


def make_tgz(member: str, data: bytes) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        info = tarfile.TarInfo(member)
        info.size = len(data)
        info.mode = 0o755
        tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class ToolsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="harness-tools-")
        self.payload = b"#!/bin/sh\necho fake-tool 1.2.3\n"
        self.archive = os.path.join(self.tmp, "tool.tgz")
        with open(self.archive, "wb") as fh:
            fh.write(make_tgz("tool_1.2.3/bin/tool", self.payload))
        with open(self.archive, "rb") as fh:
            self.sha = hashlib.sha256(fh.read()).hexdigest()
        self.lock = {"tool": "tool", "version": "1.2.3", "verified": True,
                     "assets": {"linux/amd64": {"url": "https://example.com/dl/tool.tgz", "sha256": self.sha,
                                                "archive": "tar.gz", "binary": "tool_1.2.3/bin/tool"}}}
        self.dest = os.path.join(self.tmp, "bin")
        os.makedirs(self.dest)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def install(self, lock=None, **kw):
        return T.install_from_lock(lock or self.lock, "tool", self.dest, key="linux/amd64", log=lambda *a: None, **kw)

    def test_install_from_file(self):
        info = self.install(from_file=self.archive)
        path = os.path.join(self.dest, "tool")
        with open(path, "rb") as fh:
            self.assertEqual(fh.read(), self.payload)
        self.assertTrue(os.access(path, os.X_OK))
        self.assertEqual(info["version"], "1.2.3")

    def test_sha_mismatch_refuses(self):
        lock = json.loads(json.dumps(self.lock))
        lock["assets"]["linux/amd64"]["sha256"] = "0" * 64
        with self.assertRaises(HarnessError) as cm:
            self.install(lock, from_file=self.archive)
        self.assertIn("sha256 mismatch", str(cm.exception))
        self.assertFalse(os.path.exists(os.path.join(self.dest, "tool")))

    def test_unverified_lock_needs_insecure(self):
        lock = json.loads(json.dumps(self.lock))
        lock["verified"] = False
        lock["assets"]["linux/amd64"]["sha256"] = ""
        with self.assertRaises(HarnessError):
            self.install(lock, from_file=self.archive)
        self.install(lock, from_file=self.archive, insecure=True)

    def test_version_pin_and_offline(self):
        with self.assertRaises(HarnessError):
            self.install(from_file=self.archive, want_version="9.9.9")
        with self.assertRaises(HarnessError) as cm:
            self.install(offline=True)
        self.assertIn("--from", str(cm.exception))

    def test_zip_and_missing_member(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("x/bin/tool", self.payload)
        self.assertEqual(T.extract(buf.getvalue(), "zip", "x/bin/tool"), self.payload)
        with self.assertRaises(HarnessError):
            T.extract(buf.getvalue(), "zip", "nope")

    def test_mirror_rewrite(self):
        self.assertEqual(T.mirror_url("https://github.com/cli/cli/releases/download/v1/x.tgz", "https://m.example.com/gh/"),
                         "https://m.example.com/gh/cli/cli/releases/download/v1/x.tgz")
        self.assertEqual(T.mirror_url("https://a/b", None), "https://a/b")

    def test_repo_locks_are_complete_and_verified(self):
        for tool in ("gh", "glab"):
            lock = T.load_lock(REPO, tool)
            self.assertTrue(lock["verified"], tool)
            self.assertEqual(sorted(lock["assets"]), ["darwin/amd64", "darwin/arm64", "linux/amd64", "linux/arm64"])
            for key, asset in lock["assets"].items():
                self.assertRegex(asset["sha256"], r"^[0-9a-f]{64}$", (tool, key))
                self.assertTrue(asset["url"].startswith("https://"))
                self.assertIn(lock["version"], asset["url"])


if __name__ == "__main__":
    unittest.main()
