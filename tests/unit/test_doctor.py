"""doctor: bundle checks, fix linking to manual steps, warn_only, offline, built-ins; steps."""
from __future__ import annotations

import io
import os
import unittest
from contextlib import redirect_stdout

from helpers import HubTestCase  # noqa: E402

from harness import doctor as D
from harness import steps as ST


class DoctorTest(HubTestCase):
    def results(self, **kw):
        hub = self.hub()
        return {r.id: r for r in D.Doctor(hub, **kw).run()}, hub

    def test_failure_links_manual_step(self):
        res, hub = self.results(offline=True)
        r = res["alpha-auth"]
        self.assertEqual(r.status, "FAIL")
        self.assertEqual(r.fix_line, "→ manual step alpha#alpha-auth: Authenticate alpha (docs/bundles/alpha.md#alpha-auth)")
        self.assertEqual(res["core-ok"].status, "PASS")
        self.assertEqual(res["core-online"].status, "SKIP")

    def test_literal_fix_command(self):
        core = self.hub().bundle("core")
        self.assertEqual(D.fix_line(core, "echo run a literal command"), "→ fix: echo run a literal command")

    def test_warn_only_and_online(self):
        self.write(self.cfg, self.read(self.cfg) + '\n[doctor]\nwarn_only = ["alpha-auth"]\n')
        res, _ = self.results(offline=False)
        self.assertEqual(res["alpha-auth"].status, "WARN")
        self.assertEqual(res["core-online"].status, "PASS")

    def test_exit_code_and_output(self):
        self.apply(providers=["claude"])
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = D.run(self.hub(), offline=True, providers=["claude"])
        out = buf.getvalue()
        self.assertEqual(rc, 1)
        self.assertIn("→ manual step alpha#alpha-auth", out)
        self.assertRegex(out, r"doctor: 1 fail, \d+ warn, \d+ pass, 1 skipped")

    def test_hook_checks_after_apply(self):
        res, _ = self.results(offline=True, providers=["claude"])
        self.assertEqual(res["hook-claude"].status, "FAIL")  # not applied yet
        self.apply(providers=["claude"])
        res, _ = self.results(offline=True, providers=["claude"])
        self.assertEqual(res["hook-claude"].status, "PASS")
        self.assertEqual(res["hook-entry-claude"].status, "PASS")
        self.assertEqual(res["link-demo"].status, "PASS")
        self.write(self.h(".claude", "hooks", "guard-bash.sh"), "#!/bin/sh\n")
        os.chmod(self.h(".claude", "hooks", "guard-bash.sh"), 0o755)
        res, _ = self.results(offline=True, providers=["claude"])
        self.assertEqual(res["hook-claude"].status, "WARN")

    def test_script_check_exit_mapping(self):
        d = os.path.join(self.bundles, "core", "doctor")
        self.write(os.path.join(d, "warn.sh"), "echo meh; exit 1\n")
        self.write(os.path.join(self.bundles, "core", "bundle.toml"),
                   self.read(os.path.join(self.bundles, "core", "bundle.toml"))
                   + '\n[[doctor_checks]]\nid = "core-script"\nseverity = "fail"\nscript = "doctor/warn.sh"\n')
        res, _ = self.results(offline=True)
        self.assertEqual(res["core-script"].status, "WARN")


class StepsTest(HubTestCase):
    def test_grouping_and_pending(self):
        rows = ST.collect(self.hub())
        self.assertEqual([(r["bundle"], r["id"], r["group"]) for r in rows],
                         [("core", "demo-login", "browser"), ("alpha", "alpha-auth", "none")])
        self.assertEqual(rows[0]["how"], "Run `demo login --host PROJ-123` in a terminal.")
        pending = ST.collect(self.hub(), pending=True)
        self.assertEqual([r["id"] for r in pending], ["alpha-auth"])   # core's verify is `true`
        text = ST.render_text(pending, "Pending manual steps")
        self.assertIn("== No browser needed ==", text)
        self.assertIn("docs/bundles/alpha.md#alpha-auth", text)


if __name__ == "__main__":
    unittest.main()
