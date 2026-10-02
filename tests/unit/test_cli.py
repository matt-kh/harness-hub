"""CLI parsing: every command exists, global flags work before and after the command."""
from __future__ import annotations

import io
import os
import unittest
from contextlib import redirect_stdout

from helpers import HubTestCase  # noqa: E402

from harness import cli


class ParserTest(unittest.TestCase):
    def test_every_command(self):
        p = cli.build_parser()
        for name, _h in cli.COMMANDS:
            argv = [name]
            if name == "render":
                argv += ["--out", "/tmp/x"]
            if name == "docs":
                argv += ["check"]
            if name == "verify":
                argv += ["x.bundle"]
            if name == "release":
                argv += ["check"]
            ns = p.parse_args(argv)
            self.assertEqual(ns.command, name)

    def test_global_flags_both_positions(self):
        p = cli.build_parser()
        a = cli.Ctx(p.parse_args(["--config", "/c.toml", "--offline", "plan"]))
        b = cli.Ctx(p.parse_args(["plan", "--config", "/c.toml", "--offline", "--yes"]))
        self.assertEqual((a.config, a.offline), ("/c.toml", True))
        self.assertEqual((b.config, b.offline, b.yes), ("/c.toml", True, True))
        self.assertEqual(cli._csv(["a,b", "c"]), ["a", "b", "c"])

    def test_bootstrap_from_flags(self):
        p = cli.build_parser()
        ns = p.parse_args(["bootstrap", "--from", "h.bundle", "--dest", "/d", "--origin", "u", "--yes"])
        self.assertEqual((ns.from_, ns.dest, ns.origin), ("h.bundle", "/d", "u"))
        ns = p.parse_args(["pack", "--out", "/o", "--tag", "v1", "--tools", "linux/amd64,darwin/arm64"])
        self.assertEqual((ns.out, ns.tag, cli._csv(ns.tools)), ("/o", "v1", ["linux/amd64", "darwin/arm64"]))

    def test_release_and_self_extract_flags(self):
        p = cli.build_parser()
        ns = p.parse_args(["release", "check", "v1.2.3", "--no-remote", "--branch", "trunk"])
        self.assertEqual((ns.action, ns.tag, ns.no_remote, ns.branch, ns.remote), ("check", "v1.2.3", True, "trunk", "origin"))
        ns = p.parse_args(["release", "notes", "v1.2.3", "--dir", "rel", "--out", "N.md"])
        self.assertEqual((ns.action, ns.tag, ns.dir, ns.out), ("notes", "v1.2.3", "rel", "N.md"))
        self.assertTrue(p.parse_args(["pack", "--self-extract"]).self_extract)
        self.assertEqual(p.parse_args(["upgrade"]).to, None)

    def _help(self, *argv):
        import contextlib

        buf = io.StringIO()
        with redirect_stdout(buf), self.assertRaises(SystemExit):
            with contextlib.redirect_stderr(io.StringIO()):
                cli.main(list(argv) + ["--help"])
        return buf.getvalue()

    def test_help_names_the_new_flags(self):
        self.assertIn("--no-remote", self._help("release", "check"))
        self.assertIn("--self-extract", self._help("pack"))
        self.assertIn(".run", self._help("pack"))
        self.assertIn("latest", self._help("upgrade"))
        self.assertIn("FILE.run", self._help("verify"))

    def test_release_without_action_is_a_usage_error(self):
        import contextlib

        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(["release"]), 2)

    def test_dest_without_from_is_a_usage_error(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            import contextlib

            with contextlib.redirect_stderr(io.StringIO()):
                rc = cli.main(["bootstrap", "--dest", "/tmp/x", "--dry-run"])
        self.assertEqual(rc, 2)


class CommandTest(HubTestCase):
    def run_cli(self, *argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli.main(list(argv) + ["--config", self.cfg])
        return rc, buf.getvalue()

    def test_plan_apply_plan(self):
        rc, out = self.run_cli("plan", "--providers", "claude")
        self.assertEqual(rc, 0)
        self.assertIn("create   ~/.claude/CLAUDE.md", out)
        rc, out = self.run_cli("apply", "--providers", "claude", "--yes")
        self.assertEqual(rc, 0)
        self.assertIn("Applied:", out)
        rc, out = self.run_cli("plan", "--providers", "claude")
        self.assertIn("Plan: 0 changes", out)

    def test_config_get_set_validate(self):
        rc, out = self.run_cli("config", "get", "alpha.host")
        self.assertEqual((rc, out.strip()), (0, "alpha.example.com"))
        rc, out = self.run_cli("config", "set", "alpha.host", "beta.example.com")
        self.assertEqual(rc, 0)
        self.assertIn('host = "beta.example.com"', self.read(self.cfg))
        rc, out = self.run_cli("config", "validate")
        self.assertEqual(rc, 0)
        rc, _out = self.run_cli("config", "set", "alpha.host", "Bad Host")
        self.assertEqual(rc, 1)

    def test_render_out(self):
        out_dir = os.path.join(self.tmp, "out")
        rc, out = self.run_cli("render", "--out", out_dir)
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.isfile(os.path.join(out_dir, ".claude", "settings.json")))
        self.assertFalse(os.path.exists(self.h(".claude")))  # render never touches live homes

    def test_bundles_list(self):
        rc, out = self.run_cli("bundles")
        self.assertEqual(rc, 0)
        self.assertIn("* core", out)

    def test_catalog(self):
        import json

        rc, out = self.run_cli("catalog")
        self.assertEqual(rc, 0)
        for cid in ("core/agents/planner", "core/skills/demo", "core/guard.d/20-core", "alpha/mcp/alpha",
                    "core/doctor/core-ok", "providers/claude", "profiles/minimal"):
            self.assertIn(cid, out)
        rc, out = self.run_cli("catalog", "--json")
        self.assertEqual(rc, 0)
        data = json.loads(out)
        planner = [e for e in data if e["id"] == "core/agents/planner"][0]
        self.assertEqual((planner["kind"], planner["function"], planner["posture"]), ("agent", "plan", "read-only"))
        rc, out = self.run_cli("catalog", "--kind", "agent", "--json")
        self.assertEqual([e["id"] for e in json.loads(out)], ["core/agents/planner"])
        rc, out = self.run_cli("catalog", "--bundle", "alpha", "--json")
        ids = [e["id"] for e in json.loads(out)]
        self.assertIn("alpha", ids)
        self.assertTrue(all(i == "alpha" or i.startswith("alpha/") for i in ids), ids)
        rc, out = self.run_cli("catalog", "--bundle", "nope")
        self.assertEqual(rc, 2)
        rc, out = self.run_cli("catalog", "--domain", "scm", "--json")
        self.assertEqual({e["id"] for e in json.loads(out) if e["kind"] == "bundle"}, {"beta"})


class UpgradeNotesTest(unittest.TestCase):
    def test_changelog_between(self):
        from harness.upgrade import changelog_between

        text = ("# Changelog\n\n## [Unreleased]\n\n## [0.3.0] - 2026-11-01\n### Migration\n- rename x\n\n"
                "## [0.2.0] - 2026-10-01\n- b\n\n## [0.1.0] - 2026-09-30\n- a\n")
        got = changelog_between(text, "0.1.0", "0.3.0")
        self.assertEqual([v for v, _b in got], ["0.3.0", "0.2.0"])
        self.assertIn("### Migration", got[0][1])
        self.assertEqual(changelog_between(text, "0.3.0", "0.3.0"), [])


if __name__ == "__main__":
    unittest.main()
