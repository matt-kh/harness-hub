"""bootstrap step 5: missing tools with a lock are installed, optional ones never are."""
from __future__ import annotations

import hashlib
import json
import os
import types
import unittest

from helpers import HubTestCase

from harness import bootstrap as B


class InstallMissingToolsTest(HubTestCase):
    def setUp(self):
        super().setUp()
        self.hub = os.path.join(self.tmp, "hub")
        os.makedirs(os.path.join(self.hub, "tools"))
        self.dest = os.path.join(self.tmp, "bin")
        os.makedirs(self.dest)
        payload = b"#!/bin/sh\necho fake 1.0\n"
        src = os.path.join(self.tmp, "fake-bin")
        with open(src, "wb") as fh:
            fh.write(payload)
        asset = {"url": "file://" + src, "sha256": hashlib.sha256(payload).hexdigest(),
                 "archive": "none", "binary": "fake-bin"}
        from harness import tools as T

        for tool in ("fake", "opt"):
            lock = {"tool": tool, "version": "1.0", "verified": True,
                    "assets": {T.platform_key(): asset}}
            with open(os.path.join(self.hub, "tools", "%s.lock.json" % tool), "w") as fh:
                json.dump(lock, fh)
        self.logs = []

    def bundle(self, name, binaries):
        return types.SimpleNamespace(name=name, requires_binaries=binaries)

    def run_it(self, bundles):
        return B.install_missing_tools(bundles, self.hub, dest=self.dest, log=self.logs.append,
                                       has=lambda _n: None)

    def test_optional_binary_is_not_installed(self):
        got = self.run_it([self.bundle("b", {"opt": {"install": "opt", "optional": True}})])
        self.assertEqual(got, [])
        self.assertFalse(os.path.exists(os.path.join(self.dest, "opt")))
        self.assertTrue(any("harness install opt" in ln and "optional" in ln for ln in self.logs), self.logs)

    def test_required_binary_is_installed_once(self):
        got = self.run_it([self.bundle("a", {"fake": {"install": "fake"}}),
                           self.bundle("b", {"fake": {"install": "fake", "optional": True}})])
        self.assertEqual(got, ["fake"])
        self.assertTrue(os.access(os.path.join(self.dest, "fake"), os.X_OK))

    def test_present_or_lockless_binaries_are_skipped(self):
        got = B.install_missing_tools([self.bundle("a", {"fake": {"install": "fake"}})], self.hub,
                                      dest=self.dest, log=self.logs.append, has=lambda _n: "/usr/bin/fake")
        self.assertEqual(got, [])
        got = self.run_it([self.bundle("a", {"nolock": {"install": "nolock"}, "plain": {}})])
        self.assertEqual(got, [])
        self.assertEqual(self.logs, [])


if __name__ == "__main__":
    unittest.main()
