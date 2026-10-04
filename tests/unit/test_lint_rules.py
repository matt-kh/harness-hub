"""The lint rules env-provides, rule-guard-pairing, permissions-vs-guard, agent-tools,
skill-description, fragments-target, profile-sane, stability and the provider-feature sensor kind:
one passing and one failing fixture bundle each, plus the hub's own bundles staying clean."""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from helpers import REPO, HubTestCase  # noqa: E402

from harness import lint as L
from harness import manifest as M
from harness import render as R
from harness import schema_lite as SL

HAVE_JQ = shutil.which("jq") is not None


class LintRuleCase(HubTestCase):
    def setUp(self):
        super().setUp()
        os.environ["HARNESS_LINT_SKIP_GATE"] = "1"
        self.core = os.path.join(self.bundles, "core")

    def tearDown(self):
        os.environ.pop("HARNESS_LINT_SKIP_GATE", None)
        super().tearDown()

    def bundle(self, name="core", origin="public"):
        return M.load_bundle(os.path.join(self.bundles, name), origin)

    def edit(self, rel, old, new):
        path = os.path.join(self.bundles, rel)
        text = self.read(path)
        self.assertIn(old, text, rel)
        self.write(path, text.replace(old, new, 1))

    def run_rule(self, fn, *args):
        rep = L.Report()
        fn(*args, rep)
        return rep


class EnvProvidesTest(LintRuleCase):
    def test_prefixes_are_parsed_from_the_real_engine(self):
        got = L.guard_env_prefixes(os.path.join(REPO, "bundles", "core", "guard", "engine.sh"))
        self.assertEqual(got, list(L.GUARD_ENV_PREFIXES_FALLBACK))

    def test_passing_bundle(self):
        self.edit("core/bundle.toml", 'env = { FIX_TICKET = "{{ core.ticket_example }}", FIX_LABEL = "agent-worked" }',
                  'env = { HARNESS_FIX_TICKET = "{{ core.ticket_example }}", WORK_TICKET_LABEL = "agent-worked" }')
        rep = self.run_rule(L.lint_env_provides, self.bundle(), L.GUARD_ENV_PREFIXES_FALLBACK)
        self.assertEqual((rep.errors, rep.warnings), ([], []))

    def test_failing_bundle(self):
        rep = self.run_rule(L.lint_env_provides, self.bundle(), L.GUARD_ENV_PREFIXES_FALLBACK)
        self.assertEqual(len(rep.errors), 2, rep.errors)
        self.assertIn("core: env-provides: key FIX_LABEL in [provides.env] would be dropped by the guard; "
                      "prefix it with one of WORK_TICKET_, HARNESS_,", rep.errors[0])

    def test_unparsable_engine_falls_back_and_warns_once(self):
        hub = self.hub(require_config=False, select=False)  # the fixture engine has no prefix case line
        rep = L.Report()
        self.assertEqual(L.resolve_env_prefixes(hub, rep), list(L.GUARD_ENV_PREFIXES_FALLBACK))
        self.assertEqual(len(rep.warnings), 1, rep.warnings)
        self.assertIn("could not parse the guard.env prefix list", rep.warnings[0])


class RuleGuardPairingTest(LintRuleCase):
    def test_passing_bundle(self):
        rep = self.run_rule(L.lint_rule_guard_pairing, self.bundle("alpha"))  # rules/40-alpha + guard.d/40-alpha
        self.assertEqual(rep.warnings, [])

    def test_failing_bundle(self):
        rep = self.run_rule(L.lint_rule_guard_pairing, self.bundle("beta"))  # rules/05-beta, guard.d/15-beta
        self.assertEqual(len(rep.warnings), 2, rep.warnings)
        self.assertIn("beta: rule-guard-pairing: rules/05-beta.md has no guard.d/05-*.sh enforcing it; add that "
                      "guard section with test rows, or name 'beta' in [harness].coverage_note", rep.warnings[0])
        self.assertIn("guard.d/15-beta.sh has no rules/15-*.md", rep.warnings[1])
        self.assertEqual(self.run_rule(L.lint_rule_guard_pairing, self.bundle("beta", "private")).warnings, [])

    def test_coverage_note_naming_the_topic_silences_it(self):
        self.write(os.path.join(self.bundles, "beta", "bundle.toml"),
                   self.read(os.path.join(self.bundles, "beta", "bundle.toml"))
                   + '\n[harness]\ncoverage_note = "The Beta rule is guide-only."\n')
        self.assertEqual(self.run_rule(L.lint_rule_guard_pairing, self.bundle("beta")).warnings, [])

    def test_topic_matching(self):
        self.assertTrue(L.mentions_topic("the github closing section", "github-closing"))
        self.assertTrue(L.mentions_topic("see k8s-rules.", "k8s-rules"))
        self.assertFalse(L.mentions_topic("the github section", "git"))


@unittest.skipUnless(HAVE_JQ, "the guard needs jq")
class PermissionsVsGuardTest(LintRuleCase):
    def lint(self):
        hub = self.hub(require_config=False, select=False)
        return self.run_rule(L.lint_permissions_vs_guard, hub)

    def test_passing_bundle(self):
        rep = self.lint()  # allow demo status / jq: the fixture guard passes both
        self.assertEqual((rep.errors, rep.warnings), ([], []))

    def test_failing_allow(self):
        self.edit("core/permissions.toml", 'allow = ["Bash(demo status:*)"', 'allow = ["Bash(fixture-deny:*)"')
        rep = self.lint()
        self.assertEqual(len(rep.errors), 1, rep.errors)
        self.assertIn("core: permissions-vs-guard: allow-listed command `fixture-deny x` (Bash(fixture-deny:*) in "
                      "permissions.toml) is denied by guard section 20-core.sh (bundle core): ", rep.errors[0])
        self.assertIn("fix one of them", rep.errors[0])

    def test_failing_deny(self):
        self.edit("core/permissions.toml", 'deny = ["Read(~/.config/demo/**)"]',
                  'deny = ["Read(~/.config/demo/**)", "Bash(fixture-allow:*)"]')
        rep = self.lint()
        self.assertEqual(len(rep.errors), 1, rep.errors)
        self.assertIn("deny-listed command `fixture-allow x` (Bash(fixture-allow:*) in permissions.toml) is allowed "
                      "by guard section 20-core.sh (bundle core)", rep.errors[0])

    def test_guard_is_built_from_core_and_the_bundle_only(self):
        # alpha's own section denies alpha-deny; beta's guard (core + beta) does not contain it
        self.write(os.path.join(self.bundles, "beta", "permissions.toml"),
                   '[permissions]\nallow = ["Bash(alpha-deny:*)"]\n')
        self.assertEqual(self.lint().errors, [])
        self.write(os.path.join(self.bundles, "alpha", "permissions.toml"),
                   '[permissions]\nallow = ["Bash(alpha-deny:*)"]\n')
        errs = self.lint().errors
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("section 40-alpha.sh (bundle alpha)", errs[0])


class AgentToolsTest(LintRuleCase):
    POLICY = "{{ core.model_policy.plan }}"

    def test_passing_bundle(self):
        self.edit("core/agents/planner.md", "model: {{ core.ticket_example }}",
                  "model: %s\ntools: Read, Grep, Bash" % self.POLICY)
        rep = self.run_rule(L.lint_agent_tools, self.bundle())
        self.assertEqual((rep.errors, rep.warnings), ([], []))

    def test_hard_coded_model_is_an_error(self):
        self.edit("core/agents/planner.md", "model: {{ core.ticket_example }}", "model: some-model-1")
        rep = self.run_rule(L.lint_agent_tools, self.bundle())
        self.assertEqual(len(rep.errors), 1, rep.errors)
        self.assertIn("core: agent-tools: core/agents/planner has a hard-coded model 'some-model-1'; use "
                      "{{ core.model_policy.plan|execute }}", rep.errors[0])
        self.assertEqual(self.run_rule(L.lint_agent_tools, self.bundle(origin="private")).errors, [])

    def test_read_only_agent_with_write_tools_warns(self):
        self.edit("core/agents/planner.md", "model: {{ core.ticket_example }}",
                  "model: %s\ntools: Read, Edit, Write" % self.POLICY)
        rep = self.run_rule(L.lint_agent_tools, self.bundle())  # agents/planner is read-only in the fixture
        self.assertEqual(len(rep.warnings), 1, rep.warnings)
        self.assertIn("core/agents/planner has posture read-only but its front matter tools: lists Edit, Write; "
                      "remove them", rep.warnings[0])


class SkillDescriptionTest(LintRuleCase):
    TPL = R.Templater({"core": {"ticket_example": "PROJ-123"}})
    GOOD = ("Run the demo tool against {{ core.ticket_example }}. Use when the user asks for a demo run or "
            "mentions the demo tool.")

    def set_description(self, desc, extra=""):
        self.write(os.path.join(self.core, "skills", "demo", "SKILL.md"),
                   "---\nname: demo\ndescription: %s%s\n---\n# demo\n" % (desc, extra))

    def test_passing_bundle(self):
        self.set_description(self.GOOD)
        rep = self.run_rule(L.lint_skill_description, self.bundle(), self.TPL)
        self.assertEqual(rep.warnings, [])

    def test_failing_bundle(self):
        rep = self.run_rule(L.lint_skill_description, self.bundle(), self.TPL)
        self.assertEqual(len(rep.warnings), 2, rep.warnings)
        self.assertIn("core: skill-description: skill demo: description is 24 chars, under the 60-char minimum",
                      rep.warnings[0])
        self.assertIn("description has no trigger phrase; add a sentence starting \"Use when ...\"", rep.warnings[1])

    def test_too_long_after_expansion(self):
        self.set_description(self.GOOD + " {{ core.ticket_example }}" * 120)
        rep = self.run_rule(L.lint_skill_description, self.bundle(), self.TPL)
        self.assertEqual(len(rep.warnings), 1, rep.warnings)
        self.assertIn("after template expansion, over the 1024-char limit", rep.warnings[0])

    def test_workflow_skill_needs_scope_and_argument_hint(self):
        self.edit("core/bundle.toml", '[taxonomy.components]\n', '[taxonomy.components]\n"skills/demo" = { function = "workflow" }\n')
        self.set_description(self.GOOD)
        rep = self.run_rule(L.lint_skill_description, self.bundle(), self.TPL)
        self.assertEqual(len(rep.warnings), 2, rep.warnings)
        self.assertIn("workflow skill description has no negative scope; add \"NOT for ...\"", rep.warnings[0])
        self.assertIn("workflow skill has no argument-hint", rep.warnings[1])
        self.set_description(self.GOOD + " NOT for real runs.", "\nargument-hint: <ticket>")
        self.assertEqual(self.run_rule(L.lint_skill_description, self.bundle(), self.TPL).warnings, [])

    def test_ci_templater_expands_with_the_ci_config(self):
        tpl = L.ci_templater(self.hub(require_config=False, select=False))
        self.assertEqual(tpl.expand("{{ core.ticket_example }}", "x"), "PROJ-123")


class FragmentsTargetTest(LintRuleCase):
    def test_passing_bundle(self):
        hub = self.hub(require_config=False, select=False)
        rep = self.run_rule(L.lint_fragments_target, self.bundle("alpha", "private"), hub.bundles)
        self.assertEqual((rep.errors, rep.warnings), ([], []))

    def test_public_fragments_warn(self):
        hub = self.hub(require_config=False, select=False)
        rep = self.run_rule(L.lint_fragments_target, hub.bundles["alpha"], hub.bundles)
        self.assertEqual(rep.errors, [])
        self.assertEqual(len(rep.warnings), 1, rep.warnings)
        self.assertIn("alpha: fragments-target: public bundle ships skill fragments (skill-fragments/demo/); prefer "
                      "references inside the owning skill; fragments are for org overlays", rep.warnings[0])

    def test_failing_bundle(self):
        self.edit("alpha/bundle.toml", 'depends_on = ["core"]', "depends_on = []")
        hub = self.hub(require_config=False, select=False)
        rep = self.run_rule(L.lint_fragments_target, hub.bundles["alpha"], hub.bundles)
        self.assertEqual(len(rep.errors), 1, rep.errors)
        self.assertIn("alpha: fragments-target: skill-fragments/demo/ targets skill 'demo', which no bundle in "
                      "depends_on, recommends or any_of provides", rep.errors[0])


class ProfileSaneTest(LintRuleCase):
    def lint(self, profiles):
        home = tempfile.mkdtemp(prefix="harness-profiles-")
        self.addCleanup(shutil.rmtree, home, True)
        for name, text in profiles.items():
            self.write(os.path.join(home, "profiles", name + ".toml"), text)
        hub = self.hub(require_config=False, select=False)
        rep = L.Report()
        L.lint_profiles(hub, rep, home)
        return rep

    def test_passing_profile(self):
        rep = self.lint({"ok": '[profile]\nbundles = ["core", "alpha", "beta"]\nproviders = ["claude"]\n'})
        self.assertEqual(rep.errors, [])

    def test_failing_profiles(self):
        rep = self.lint({
            "anyof": '[profile]\nbundles = ["beta"]\n',                       # beta needs alpha or delta
            "unknown": '[profile]\nbundles = ["core", "nope"]\nproviders = ["nobody"]\n',
        })
        errs = "\n".join(rep.errors)
        self.assertIn("profiles/anyof.toml: profile-sane: bundle beta needs at least one of: alpha, delta", errs)
        self.assertIn("profiles/unknown.toml: profile-sane: unknown bundle nope; use one of: alpha, beta, core", errs)
        self.assertIn("profiles/unknown.toml: profile-sane: unknown provider nobody; use one of:", errs)

    def test_private_bundle_in_a_profile(self):
        self.write(os.path.join(self.cfg_dir, "bundles", "acme", "bundle.toml"),
                   '[bundle]\nname = "acme"\nsummary = "org"\n')
        rep = self.lint({"org": '[profile]\nbundles = ["core", "acme"]\n'})
        self.assertIn("bundle acme is not public", "\n".join(rep.errors))


class StabilityTest(LintRuleCase):
    def test_failing_bundle(self):
        rep = self.run_rule(L.lint_stability, self.bundle())  # stable; skills/demo and bin/core-tool lack suites
        self.assertEqual(len(rep.warnings), 2, rep.warnings)
        self.assertIn("core: stability: skill skills/demo has no scripts/tests/run.sh; stable requires a test suite "
                      "per skill/CLI; move to beta or add the suite", rep.warnings[0])
        self.assertIn("CLI core-tool (bin/core-tool.sh) has no tests/run.sh", rep.warnings[1])

    def test_passing_bundle(self):
        self.write(os.path.join(self.core, "skills", "demo", "scripts", "tests", "run.sh"), "#!/usr/bin/env bash\n")
        self.write(os.path.join(self.core, "tests", "run.sh"), "#!/usr/bin/env bash\n")
        self.assertEqual(self.run_rule(L.lint_stability, self.bundle()).warnings, [])
        # a coverage note admitting a missing suite still warns
        self.write(os.path.join(self.core, "bundle.toml"), self.read(os.path.join(self.core, "bundle.toml"))
                   + '\n[harness]\ncoverage_note = "The demo CLI has no unit suite."\n')
        warns = self.run_rule(L.lint_stability, self.bundle()).warnings
        self.assertEqual(len(warns), 1, warns)
        self.assertIn("coverage_note admits a missing suite ('no unit suite')", warns[0])

    def test_beta_is_exempt(self):
        self.edit("core/bundle.toml", 'stability = "stable"', 'stability = "beta"')
        self.assertEqual(self.run_rule(L.lint_stability, self.bundle()).warnings, [])


class ProviderFeatureTest(LintRuleCase):
    SENSOR = '\n[harness]\nguides = [{ kind = "rule", ref = "rules/10-core.md" }]\nsensors = [{ kind = "provider-feature", ref = "%s" }]\n'

    def lint(self, ref):
        self.write(os.path.join(self.core, "bundle.toml"), self.read(os.path.join(self.core, "bundle.toml")) + self.SENSOR % ref)
        hub = self.hub(require_config=False, select=False)
        rep = L.Report()
        L.lint_harness(self.bundle(), rep, hub.providers)
        return rep

    def test_schema_accepts_the_kind(self):
        self.lint("claude:auto-mode-classifier")
        res = SL.validate(M.load_schema("bundle.schema.json", REPO), self.bundle().data)
        self.assertEqual(res.errors, [])

    def test_passing_ref(self):
        self.assertEqual(self.lint("claude:auto-mode-classifier").errors, [])

    def test_failing_refs(self):
        self.assertIn("provider claude declares no feature 'nope'", self.lint("claude:nope").errors[0])

    def test_failing_format_and_provider(self):
        self.assertIn("must be <provider>:<feature>", self.lint("auto-mode-classifier").errors[0])

    def test_unknown_provider(self):
        self.assertIn("names unknown provider nobody", self.lint("nobody:x").errors[0])

    def test_providers_declare_features(self):
        providers = M.discover_providers([os.path.join(REPO, "providers")])
        self.assertIn("auto-mode-classifier", providers["claude"].features)
        for name, p in providers.items():
            self.assertIsInstance(p.features, list, name)


class RepoBundlesTest(LintRuleCase):
    """The hub's own bundles and profiles pass every new rule without a warning."""

    def test_repo_is_clean(self):
        os.environ["HARNESS_BUNDLES_ROOT"] = os.path.join(REPO, "bundles")
        hub = self.hub(require_config=False, select=False)
        rep = L.Report()
        prefixes = L.resolve_env_prefixes(hub, rep)
        tpl = L.ci_templater(hub)
        for b in hub.bundles.values():
            L.lint_harness(b, rep, hub.providers)
            L.lint_env_provides(b, prefixes, rep)
            L.lint_rule_guard_pairing(b, rep)
            L.lint_agent_tools(b, rep)
            L.lint_skill_description(b, tpl, rep)
            L.lint_fragments_target(b, hub.bundles, rep)
            L.lint_stability(b, rep)
        L.lint_profiles(hub, rep)
        if HAVE_JQ:
            L.lint_permissions_vs_guard(hub, rep)
        self.assertEqual((rep.errors, rep.warnings), ([], []))

    def test_rules_are_known_and_skippable(self):
        for rule in ("env-provides", "rule-guard-pairing", "permissions-vs-guard", "agent-tools", "skill-description",
                     "fragments-target", "profile-sane", "stability"):
            self.assertIn(rule, L.LINT_RULES)
            self.assertIn(rule, L.SKIPPABLE_RULES)
        self.assertTrue(set(L.SKIPPABLE_RULES) <= L.LINT_RULES)


if __name__ == "__main__":
    unittest.main()
