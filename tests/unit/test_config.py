"""Config layering, env overrides, secret rejection, explain, set and migrate."""
from __future__ import annotations

import os
import unittest

from helpers import HubTestCase  # noqa: E402  (sets sys.path)

from harness import config as C


class LayeringTest(HubTestCase):
    def test_precedence_defaults_org_config_user_env(self):
        # bundle defaults.toml sets core.default_branch_re; requires.config default sets ticket_example
        hub = self.hub()
        self.assertEqual(hub.config.get("core.ticket_example"), "PROJ-123")
        self.assertEqual(hub.config.get("core.default_branch_re"), "^(master|main)$")
        self.assertIn("defaults:core", hub.config.origin["core.default_branch_re"])
        # org overlay beats defaults
        self.write(os.path.join(self.cfg_dir, "harness.org.toml"), '[core]\nticket_example = "ORG-1"\n')
        self.assertEqual(self.hub().config.get("core.ticket_example"), "ORG-1")
        # the config file beats the org overlay
        self.write(self.cfg, self.read(self.cfg) + '\n[core]\nticket_example = "CFG-2"\n')
        self.assertEqual(self.hub().config.get("core.ticket_example"), "CFG-2")
        # the machine overlay beats the config file
        self.write(os.path.join(self.cfg_dir, "harness.user.toml"), '[core]\nticket_example = "USR-3"\n')
        hub = self.hub()
        self.assertEqual(hub.config.get("core.ticket_example"), "USR-3")
        self.assertTrue(hub.config.origin["core.ticket_example"].startswith("user"))
        # the environment beats everything
        os.environ["HARNESS_CORE_TICKET_EXAMPLE"] = "ENV-4"
        try:
            hub = self.hub()
            self.assertEqual(hub.config.get("core.ticket_example"), "ENV-4")
            self.assertEqual(hub.config.origin["core.ticket_example"], "env")
        finally:
            del os.environ["HARNESS_CORE_TICKET_EXAMPLE"]

    def test_tables_merge_arrays_replace(self):
        self.write(os.path.join(self.cfg_dir, "harness.org.toml"),
                   '[trust]\ndomains = ["a.example.com"]\nbuckets = ["b1"]\n')
        hub = self.hub()
        self.assertEqual(hub.config.get("trust.domains"), ["example.com"])  # config file array wins
        self.assertEqual(hub.config.get("trust.buckets"), ["b1"])           # sibling key kept

    def test_templated_default_is_resolved(self):
        self.assertEqual(self.hub().config.get("core.greeting"), "hello you@example.com")

    def test_env_coercion_by_schema_type(self):
        os.environ["HARNESS_ALPHA_MCP_ENABLED"] = "no"
        os.environ["HARNESS_TRUST_DOMAINS"] = "x.example.com, y.example.com"
        os.environ["HARNESS_HOME_UNRELATED"] = "ignored"
        try:
            hub = self.hub()
            self.assertIs(hub.config.get("alpha.mcp_enabled"), False)
            self.assertEqual(hub.config.get("trust.domains"), ["x.example.com", "y.example.com"])
        finally:
            for k in ("HARNESS_ALPHA_MCP_ENABLED", "HARNESS_TRUST_DOMAINS", "HARNESS_HOME_UNRELATED"):
                os.environ.pop(k, None)

    def test_env_bad_boolean_is_an_error(self):
        from harness.util import HarnessError

        os.environ["HARNESS_ALPHA_MCP_ENABLED"] = "maybe"
        try:
            with self.assertRaises(HarnessError):
                self.hub()
        finally:
            del os.environ["HARNESS_ALPHA_MCP_ENABLED"]

    def test_validation_errors_are_pathed(self):
        self.write(self.cfg, self.read(self.cfg).replace('host = "alpha.example.com"', 'host = "Bad Host"')
                   + '\n[jira]\nurl = "jira.example.com"\n')
        res = self.hub().config.validate()
        self.assertIn("alpha.host: does not match ^[a-z0-9.-]+$", res.errors)
        self.assertIn("jira.url: does not match ^https?://", res.errors)

    def test_required_key_of_active_bundle(self):
        self.write(self.cfg, self.read(self.cfg).replace('[alpha]\nhost = "alpha.example.com"\n', ""))
        res = self.hub().config.validate()
        self.assertIn("alpha.host: is required", res.errors)
        # not required when alpha is inactive
        res = self.hub(bundles=["core"]).config.validate()
        self.assertNotIn("alpha.host: is required", res.errors)

    def test_unknown_key_is_rejected(self):
        self.write(self.cfg, self.read(self.cfg) + '\n[github]\nlogn = "octocat"\n')
        self.assertIn("github.logn: unknown key", self.hub().config.validate().errors)


class SecretTest(unittest.TestCase):
    def test_secret_key_names(self):
        found = C.secret_findings({"jira": {"api_token": "abc"}, "x": {"password": "p"}})
        self.assertEqual(len(found), 2)
        self.assertTrue(found[0].startswith("jira.api_token: key name looks like a secret"))

    def test_path_suffixed_keys_are_allowed(self):
        self.assertEqual(C.secret_findings({"jira": {"token_file": "~/.config/jira"}}), [])
        self.assertEqual(len(C.secret_findings({"jira": {"token_file": "ghp_abcdefghijklmnopqrstu"}})), 1)

    def test_high_entropy_values(self):
        tok = "ghp_" + "aB3dE5fG7hJ9kL1mN3pQ5rS7tU9vW1xY3zA5"
        self.assertTrue(C.looks_like_secret_value(tok))
        self.assertTrue(C.looks_like_secret_value("Zx81Kq0Lm2Np4Rt6Vw8Yb1Dc3Fg5Hj7Kl9Mn"))
        for ok in ("(^|[-_./:])(prod|production)([-_./:]|$)", "https://jira.example.com/some/long/path/x1",
                   "~/dev/gitops-something-long-1", "customfield_20000",
                   "a-perfectly-ordinary-long-identifier-name", "local/bundles/acme/references/clusters.md"):
            self.assertFalse(C.looks_like_secret_value(ok), ok)
        found = C.secret_findings({"trust": {"notes": "Zx81Kq0Lm2Np4Rt6Vw8Yb1Dc3Fg5Hj7Kl9Mn"}})
        self.assertIn("trust.notes: value looks like a secret", found[0])


class EditTest(unittest.TestCase):
    TEXT = ('schema_version = 1\n\n[github]\nhost = "github.com"   # keep me\n\n[jira]\nurl = "https://a.example.com"\n'
            '[[jira.issue_types]]\nname = "Task"\n')

    def test_set_existing_key_keeps_comment(self):
        out = C.set_in_text(self.TEXT, "github.host", "ghe.example.com")
        self.assertIn('host = "ghe.example.com"   # keep me', out)

    def test_set_new_key_in_existing_section(self):
        out = C.set_in_text(self.TEXT, "github.login", "octocat")
        from harness import toml_compat

        data = toml_compat.loads(out)
        self.assertEqual(data["github"]["login"], "octocat")
        self.assertEqual(data["jira"]["issue_types"], [{"name": "Task"}])

    def test_set_new_section(self):
        from harness import toml_compat

        out = C.set_in_text(self.TEXT, "google.domain", "example.com")
        self.assertEqual(toml_compat.loads(out)["google"]["domain"], "example.com")

    def test_migrate_deprecated_key_and_section(self):
        from harness import toml_compat

        schema = C.load_base_schema(os.path.join(os.path.dirname(__file__), "..", ".."))
        text = 'schema_version = 1\n[k8s]\nknown_broken_contexts = ["a"]  # old\n'
        new, notes = C.migrate_text(text, schema)
        data = toml_compat.loads(new)
        self.assertEqual(data["k8s"]["broken_contexts"], ["a"])
        self.assertNotIn("known_broken_contexts", data["k8s"])
        new, notes = C.migrate_text('schema_version = 1\n[kubernetes]\nprod_re = "p"\n', schema)
        self.assertEqual(toml_compat.loads(new), {"schema_version": 1, "k8s": {"prod_re": "p"}})
        self.assertEqual(notes, ["renamed [kubernetes] -> [k8s]"])
        _new, notes = C.migrate_text('schema_version = 1\n[k8s]\nprod_re = "a"\n[kubernetes]\nprod_re = "p"\n', schema)
        self.assertIn("merge them by hand", notes[0])


if __name__ == "__main__":
    unittest.main()
