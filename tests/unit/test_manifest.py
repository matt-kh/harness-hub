"""Bundle discovery, provides fallbacks and dependency resolution."""
from __future__ import annotations

import os
import unittest

from helpers import HubTestCase  # noqa: E402

from harness import manifest as M
from harness.util import HarnessError


def fake(name, depends=(), conflicts=(), any_of=(), recommends=()):
    return M.Bundle("/nonexistent/" + name, {"bundle": {
        "name": name, "summary": name, "depends_on": list(depends), "conflicts_with": list(conflicts),
        "any_of": [list(g) for g in any_of], "recommends": list(recommends)}})


class ResolveTest(unittest.TestCase):
    def setUp(self):
        self.b = {n.name: n for n in (
            fake("core"), fake("scm", ["core"]), fake("tracker", ["core"]),
            fake("flow", ["core"], any_of=[["scm", "tracker"]], recommends=["tracker"]),
            fake("x", ["core"], conflicts=["scm"]), fake("zeta", ["core"]), fake("alpha2", ["zeta"]))}

    def test_depends_on_closure_and_order(self):
        r = M.resolve(["alpha2"], self.b)
        self.assertEqual(r.order, ["core", "zeta", "alpha2"])
        self.assertEqual(r.added, {"zeta": "alpha2", "core": "zeta"})

    def test_deterministic_regardless_of_request_order(self):
        a = M.resolve(["scm", "flow", "tracker"], self.b).order
        b = M.resolve(["tracker", "scm", "flow"], self.b).order
        self.assertEqual(a, b)
        self.assertEqual(a, ["core", "flow", "scm", "tracker"])

    def test_any_of(self):
        with self.assertRaises(HarnessError) as cm:
            M.resolve(["flow"], self.b)
        self.assertIn("needs at least one of: scm, tracker", str(cm.exception))
        self.assertEqual(M.resolve(["flow", "scm"], self.b).recommended, {"tracker": ["flow"]})

    def test_conflicts(self):
        with self.assertRaises(HarnessError) as cm:
            M.resolve(["x", "scm"], self.b)
        self.assertIn("conflict", str(cm.exception))

    def test_unknown_and_cycle(self):
        with self.assertRaises(HarnessError):
            M.resolve(["nope"], self.b)
        b = {"p": fake("p", ["q"]), "q": fake("q", ["p"])}
        with self.assertRaises(HarnessError) as cm:
            M.resolve(["p"], b)
        self.assertIn("cycle", str(cm.exception))


class FixtureBundlesTest(HubTestCase):
    def test_discovery_and_provides(self):
        hub = self.hub()
        self.assertEqual(hub.active_names, ["core", "alpha", "beta"])
        core = hub.bundle("core")
        self.assertEqual(core.rules(), ["rules/10-core.md"])
        self.assertEqual(core.skills(), ["skills/demo"])
        self.assertEqual(core.bins(), [("demo", "skills/demo/scripts/demo.sh"), ("core-tool", "bin/core-tool.sh")])
        self.assertEqual(hub.bundle("beta").guard_rules(), ["guard.d/15-beta.sh"])  # deprecated hook_rules alias
        self.assertEqual(hub.bundle("alpha").skill_fragment_files(),
                         [("demo", "references/alpha.md", "skill-fragments/demo/references/alpha.md")])
        self.assertEqual(hub.bundle("beta").any_of, [["alpha", "delta"]])

    def test_convention_fallback_when_provides_key_absent(self):
        hub = self.hub()
        alpha = hub.bundle("alpha")
        self.assertEqual(alpha.agents(), [])     # no agents/ dir
        self.assertEqual(alpha.skills(), [])

    def test_duplicate_bundle_names(self):
        extra = os.path.join(self.tmp, "extra")
        os.makedirs(os.path.join(extra, "core"))
        self.write(os.path.join(extra, "core", "bundle.toml"), '[bundle]\nname = "core"\nsummary = "dup"\n')
        os.environ["HARNESS_BUNDLE_PATH"] = extra
        with self.assertRaises(HarnessError):
            self.hub()

    def test_private_bundles_next_to_the_config(self):
        d = os.path.join(self.cfg_dir, "bundles", "acme")
        self.write(os.path.join(d, "bundle.toml"), '[bundle]\nname = "acme"\nsummary = "org"\ndepends_on = ["core"]\n')
        self.write(os.path.join(d, "rules", "90-org.md"), "Org rule.\n")
        self.write(self.cfg, self.read(self.cfg).replace('bundles = ["core", "alpha", "beta"]',
                                                         'bundles = ["core", "alpha", "beta", "acme"]'))
        hub = self.hub()
        self.assertEqual(hub.bundle("acme").origin, "private")
        self.assertTrue(hub.bundle("acme").private)
        self.assertIn("acme", hub.active_names)

    def test_profile_selection_and_explicit_list_wins(self):
        self.write(self.cfg, 'schema_version = 1\n[hub]\nprofile = "minimal"\n')
        hub = self.hub()
        self.assertEqual(hub.active_names, ["core"])
        self.assertEqual([p.name for p in hub.active_providers], ["claude"])
        hub = self.hub(bundles=["core", "beta", "alpha"])
        self.assertEqual(hub.active_names, ["core", "alpha", "beta"])


if __name__ == "__main__":
    unittest.main()
