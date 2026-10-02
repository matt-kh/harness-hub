"""Build-dir isolation: only the canonical <hub>/local/harness.toml writes <hub>/build."""
from __future__ import annotations

import hashlib
import os
import unittest

from helpers import REPO, HubTestCase  # noqa: E402

from harness.hub import resolve_build_dir


class BuildDirTest(HubTestCase):
    def test_canonical_config_uses_hub_build(self):
        hub_home = os.path.join(self.tmp, "hub")
        cfg = os.path.join(hub_home, "local", "harness.toml")
        self.write(cfg, "schema_version = 1\n")
        self.assertEqual(resolve_build_dir(hub_home, cfg), os.path.join(hub_home, "build"))

    def test_other_config_resolves_outside_the_hub(self):
        got = resolve_build_dir(REPO, self.cfg)
        digest = hashlib.sha1(os.path.realpath(self.cfg).encode()).hexdigest()[:12]
        self.assertEqual(got, os.path.join(self.home, ".cache", "harness", "build", digest))
        self.assertFalse(got.startswith(REPO + os.sep))
        os.environ["XDG_CACHE_HOME"] = os.path.join(self.tmp, "xdg")
        self.assertEqual(resolve_build_dir(REPO, self.cfg), os.path.join(self.tmp, "xdg", "harness", "build", digest))

    def test_env_override_wins(self):
        os.environ["HARNESS_BUILD_DIR"] = os.path.join(self.tmp, "b")
        try:
            hub_home = os.path.join(self.tmp, "hub")
            self.assertEqual(resolve_build_dir(hub_home, os.path.join(hub_home, "local", "harness.toml")),
                             os.path.join(self.tmp, "b"))
        finally:
            os.environ.pop("HARNESS_BUILD_DIR", None)

    def test_apply_writes_products_to_the_resolved_dir(self):
        live = os.path.join(REPO, "build", "config.json")
        before = self.read(live) if os.path.exists(live) else None
        hub = self.hub()
        self.apply(hub=hub, providers=["claude"])
        self.assertTrue(os.path.isfile(os.path.join(hub.build_dir, "config.json")))
        self.assertTrue(hub.build_dir.startswith(self.home + os.sep))
        self.assertEqual(self.read(live) if os.path.exists(live) else None, before)


if __name__ == "__main__":
    unittest.main()
