"""Generated doc regions, docs check, template generation and init filling."""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from helpers import FIXTURES, REPO, HubTestCase  # noqa: E402

from harness import docsgen as G
from harness import init as I
from harness import manifest as M
from harness import toml_compat


class RegionTest(unittest.TestCase):
    def test_create_replace_append(self):
        created = G.replace_region(None, "a/b.toml", "body\n", "# Title")
        self.assertEqual(created, "# Title\n\n<!-- generated:begin source=a/b.toml -->\nbody\n<!-- generated:end -->\n")
        page = "# Hand\n\nprose\n\n<!-- generated:begin source=a/b.toml -->\nold\n<!-- generated:end -->\n\n## After\n"
        new = G.replace_region(page, "a/b.toml", "new\n", "# x")
        self.assertEqual(new, page.replace("old", "new"))
        self.assertEqual(G.replace_region(new, "a/b.toml", "new\n", "# x"), new)
        empty = "# Hand\n\n<!-- generated:begin source=a/b.toml -->\n<!-- generated:end -->\n"
        self.assertIn("\nnew\n<!-- generated:end -->", G.replace_region(empty, "a/b.toml", "new\n", "#"))
        appended = G.replace_region("# Hand\n", "c.toml", "x\n", "#")
        self.assertTrue(appended.startswith("# Hand\n"))
        self.assertIn("<!-- generated:begin source=c.toml -->\nx\n<!-- generated:end -->", appended)

    def test_bundle_body_has_anchors_and_tables(self):
        b = M.load_bundle(os.path.join(FIXTURES, "bundles", "alpha"))
        body = G.bundle_body(b)
        self.assertIn('<a id="alpha-auth"></a>\n', body)
        self.assertIn("### alpha-auth — Authenticate alpha", body)
        self.assertIn("**Verify:** `false` (exit 0)", body)
        self.assertIn("| `alpha-auth` | fail | runs | [alpha-auth](#alpha-auth) |", body)
        self.assertIn("{{ alpha.host }}", body)  # docs stay generic

    def test_hook_rules_parse(self):
        b = M.load_bundle(os.path.join(FIXTURES, "bundles", "core"))
        rows = G.hook_rules([b])
        self.assertEqual(rows[0], ("20-core.sh", "core", "fixture-deny ...", "deny", "fixture deny rule"))

    def test_cli_body_is_stable(self):
        self.assertEqual(G.cli_body(), G.cli_body())
        self.assertIn("### harness plan", G.cli_body())


class GenerateCheckTest(HubTestCase):
    def setUp(self):
        super().setUp()
        # a scratch hub: schema, providers, CLI source, docs from the repo; fixture bundles
        self.hubdir = os.path.join(self.tmp, "hub")
        for d in ("schema", "providers"):
            shutil.copytree(os.path.join(REPO, d), os.path.join(self.hubdir, d))
        os.makedirs(os.path.join(self.hubdir, "docs"))

    def test_generate_then_check_then_drift(self):
        import types

        os.environ["HARNESS_HOME"] = self.hubdir
        ctx = types.SimpleNamespace(dry_run=False)
        self.assertEqual(G.run(ctx, "check"), 1)          # nothing generated yet
        self.assertEqual(G.run(ctx, "generate"), 0)
        self.assertEqual(G.run(ctx, "check"), 0)
        page = os.path.join(self.hubdir, "docs", "bundles", "core.md")
        text = self.read(page)
        self.assertTrue(text.startswith("# Bundle: core\n"))
        self.write(page, "# My hand-written intro\n\n" + text.split("\n", 2)[2] + "\n## Troubleshooting\n\nhand\n")
        self.assertEqual(G.run(ctx, "check"), 0)          # hand-written text outside the region is fine
        src = os.path.join(self.bundles, "core", "bundle.toml")
        self.write(src, self.read(src).replace("Log in to demo", "Log in to the demo"))
        self.assertEqual(G.run(ctx, "check"), 1)
        G.run(ctx, "generate")
        final = self.read(page)
        self.assertIn("### demo-login — Log in to the demo", final)
        self.assertTrue(final.startswith("# My hand-written intro"))
        self.assertIn("## Troubleshooting\n\nhand\n", final)
        tmpl = self.read(os.path.join(self.hubdir, "templates", "harness.toml.tmpl"))
        self.assertIn("#@! alpha host = ", tmpl)


class TemplateFillTest(unittest.TestCase):
    def test_fill_selected_bundles(self):
        from harness import config as C

        bundles = [M.load_bundle(os.path.join(FIXTURES, "bundles", n)) for n in ("core", "alpha", "beta")]
        schema = C.compile_schema(C.load_base_schema(REPO), bundles, [])
        tmpl = G.template_text(schema, [b.name for b in bundles])
        text = I.fill_template(tmpl, ["core", "alpha"], ["claude"], "you@example.com")
        data = toml_compat.loads(text)
        self.assertEqual(data["hub"], {"bundles": ["core", "alpha"], "providers": ["claude"]})
        self.assertEqual(data["alpha"], {"host": "alpha.example.com"})  # required: uncommented; defaulted: commented
        self.assertNotIn("jira", data)                                   # unselected bundle stays commented
        self.assertIn('# url = "https://jira.example.com"', text)
        self.assertEqual(data["identity"]["email"], "you@example.com")
        text2 = I.fill_template(tmpl, ["core"], ["claude"], "you@example.com")
        self.assertNotIn("alpha", toml_compat.loads(text2))


if __name__ == "__main__":
    unittest.main()
