"""Component taxonomy: vocabulary vs schema, ids, classification, the `taxonomy` lint rule and
the generated catalog (docs/reference/taxonomy.md)."""
from __future__ import annotations

import os

from helpers import REPO, HubTestCase  # noqa: E402

from harness import docsgen as D
from harness import lint as L
from harness import manifest as M
from harness import schema_lite as SL
from harness import taxonomy as T

HARNESS = """
[harness]
guides = [
  { kind = "rule", ref = "rules/10-core.md" },
  { kind = "skill", ref = "skills/demo" },
  { kind = "permission", ref = "permissions.toml" },
  { kind = "agent", ref = "agents/planner.md" },
]
sensors = [
  { kind = "guard", ref = "guard.d/20-core.sh" },
  { kind = "doctor", ref = "doctor_checks" },
  { kind = "review-agent", ref = "agents/planner.md" },
]
"""


class VocabularyTest(HubTestCase):
    def test_schema_enums_equal_facets(self):
        schema = M.load_schema("bundle.schema.json", REPO)
        for facet, values in T.FACETS.items():
            self.assertEqual(schema["$defs"][facet]["enum"], list(values), facet)

    def test_component_id(self):
        cases = {"agents/x.md": "agents/x", "guard.d/30-git.sh": "guard.d/30-git", "permissions.toml": "permissions",
                 "skills/k8s/": "skills/k8s", "install/gh.sh": "install/gh", "rules/00-conventions.md": "rules/00-conventions",
                 "./agents/y.md": "agents/y"}
        for ref, want in cases.items():
            self.assertEqual(T.component_id(ref), want, ref)
        self.assertEqual(T.kind_of_key("guard.d/30-git"), "guard")
        self.assertEqual(T.kind_of_key("permissions"), "permission")
        self.assertIsNone(T.kind_of_key("nope/x"))

    def test_posture_order(self):
        self.assertLess(T.posture_rank("read-only"), T.posture_rank("local"))
        self.assertLess(T.posture_rank("local"), T.posture_rank("label-gated"))


class ClassifyTest(HubTestCase):
    def setUp(self):
        super().setUp()
        os.environ["HARNESS_LINT_SKIP_GATE"] = "1"
        self.core = os.path.join(self.bundles, "core")
        self.manifest = os.path.join(self.core, "bundle.toml")
        text = self.read(self.manifest)
        self.base = text[:text.index("[taxonomy]")]
        self.schema = M.load_schema("bundle.schema.json", REPO)

    def tearDown(self):
        os.environ.pop("HARNESS_LINT_SKIP_GATE", None)
        super().tearDown()

    def set_taxonomy(self, text, harness=HARNESS):
        self.write(self.manifest, self.base + text + harness)

    def bundle(self, origin="public"):
        return M.load_bundle(self.core, origin)

    def lint(self, origin="public"):
        rep = L.Report()
        L.lint_taxonomy(self.bundle(origin), rep)
        return rep

    def comps(self):
        return {c.key: c for c in T.components(self.bundle())}

    # ------------------------------------------------------------------ classification
    def test_every_kind_inheritance_and_override(self):
        os.makedirs(os.path.join(self.core, "install"))
        self.write(os.path.join(self.core, "install", "demo.sh"), "#!/usr/bin/env bash\n")
        self.write(os.path.join(self.core, "mcp.toml"), '[servers.demo-mcp]\ncommand = "uvx"\nargs = ["demo"]\n')
        self.set_taxonomy('[taxonomy]\ndomain = "base"\nposture = "local"\nfunction = "client"\n\n'
                          '[taxonomy.components]\n"agents/planner" = { function = "plan", posture = "read-only" }\n'
                          '"guard.d/20-core" = { domain = "scm" }\n')
        c = self.comps()
        kinds = {x.kind for x in c.values()}
        self.assertEqual(kinds, {"rule", "skill", "agent", "guard", "permission", "mcp", "bin", "installer", "doctor", "step"})
        self.assertEqual(sorted(c), sorted([
            "rules/10-core", "skills/demo", "agents/planner", "guard.d/20-core", "permissions", "mcp/demo-mcp",
            "bin/demo", "bin/core-tool", "install/demo", "doctor/core-ok", "doctor/core-online", "steps/demo-login"]))
        self.assertEqual(c["agents/planner"].id, "core/agents/planner")
        # inherited bundle defaults
        self.assertEqual((c["skills/demo"].domain, c["skills/demo"].function, c["skills/demo"].posture),
                         ("base", "client", "local"))
        # override
        self.assertEqual((c["agents/planner"].function, c["agents/planner"].posture), ("plan", "read-only"))
        self.assertEqual(c["guard.d/20-core"].domain, "scm")
        # fixed by kind
        self.assertEqual((c["guard.d/20-core"].function, c["guard.d/20-core"].posture), ("govern", None))
        self.assertEqual((c["bin/demo"].function, c["bin/demo"].posture), ("client", "local"))
        self.assertEqual((c["doctor/core-ok"].function, c["doctor/core-ok"].posture), ("setup", "read-only"))
        self.assertEqual((c["install/demo"].function, c["steps/demo-login"].function), ("setup", "setup"))
        self.assertEqual(c["mcp/demo-mcp"].summary, "runs `uvx demo`")
        # derived
        self.assertEqual(c["guard.d/20-core"].decisions, "deny 1 · ask 1 · allow 1")
        self.assertEqual(c["permissions"].decisions, "deny 1 · ask 1 · allow 2")
        self.assertEqual(c["agents/planner"].model, "{{ core.ticket_example }}")
        self.assertEqual(c["agents/planner"].summary, "Fixture planning agent")
        self.assertEqual(c["doctor/core-ok"].summary, "")
        self.assertEqual(c["steps/demo-login"].summary, "Log in to demo")
        self.assertEqual(c["rules/10-core"].control, "guide")
        self.assertEqual(c["guard.d/20-core"].control, "sensor")
        self.assertEqual(c["agents/planner"].control, "guide + sensor (inferential)")
        self.assertEqual(c["doctor/core-online"].control, "sensor")
        self.assertIsNone(c["bin/demo"].control)
        e = T.bundle_entry(self.bundle())
        self.assertEqual((e["domain"], e["posture"]), ("base", "local"))
        self.assertEqual(e["functions"], ["govern", "client", "plan", "setup"])

    def test_model_policy_and_folded_description(self):
        self.write(os.path.join(self.core, "agents", "planner.md"),
                   "---\nname: planner\ndescription: >-\n  Plans things. Second sentence.\n"
                   "model: {{ core.model_policy.plan }}\n---\nbody\n")
        self.set_taxonomy('[taxonomy]\ndomain = "base"\nposture = "local"\n')
        c = self.comps()["agents/planner"]
        self.assertEqual((c.model, c.summary), ("plan", "Plans things."))
        self.assertEqual(T.guard_decisions("# shellcheck shell=bash\n"), "helper (no rules)")

    def test_profile_and_provider_entries(self):
        bundles = M.discover_bundles([(os.path.join(REPO, "bundles"), "public")])
        e = T.profile_entry(REPO, "minimal", bundles)
        self.assertEqual((e["id"], e["domains"], e["posture"]), ("profiles/minimal", ["base"], "local"))
        e = T.profile_entry(REPO, "platform-engineer", bundles)
        self.assertEqual(e["posture"], "label-gated")
        provs = M.discover_providers([os.path.join(REPO, "providers")])
        tiers = {n: T.provider_entry(p)["tier"] for n, p in provs.items()}
        self.assertEqual(tiers, {"claude": "enforced", "gemini": "partial", "copilot": "partial",
                                 "codex": "advisory", "opencode": "advisory"})

    # ------------------------------------------------------------------ schema
    def test_schema(self):
        self.set_taxonomy('[taxonomy]\ndomain = "base"\nposture = "local"\n[taxonomy.components]\n'
                          '"agents/planner" = { function = "plan", note = "x" }\n')
        self.assertEqual(SL.validate(self.schema, self.bundle().data).errors, [])
        for bad in ('[taxonomy]\ndomain = "foo"\n',
                    '[taxonomy]\nposture = "writes"\n',
                    '[taxonomy]\nextra = 1\n',
                    '[taxonomy.components]\n"widgets/x" = {}\n',
                    '[taxonomy.components]\n"agents/planner" = { owner = "x" }\n'):
            self.set_taxonomy(bad)
            self.assertTrue(SL.validate(self.schema, self.bundle().data).errors, bad)
        self.set_taxonomy('[taxonomy]\ndomain = "foo"\n')
        self.assertIn("taxonomy.domain: must be one of", "\n".join(SL.validate(self.schema, self.bundle().data).errors))

    def test_tags_are_deprecated(self):
        self.write(self.manifest, self.base.replace('summary = ', 'tags = ["x"]\nsummary = ', 1))
        res = SL.validate(self.schema, self.bundle().data)
        self.assertEqual(res.errors, [])
        self.assertIn("bundle.tags: is deprecated; use taxonomy.domain", res.warnings)

    # ------------------------------------------------------------------ lint
    def test_clean(self):
        self.set_taxonomy('[taxonomy]\ndomain = "base"\nposture = "local"\nfunction = "client"\n\n'
                          '[taxonomy.components]\n"agents/planner" = { function = "plan", posture = "read-only" }\n')
        rep = self.lint()
        self.assertEqual((rep.errors, rep.warnings), ([], []))

    def test_missing_taxonomy_warns_public_only(self):
        self.write(self.manifest, self.base + HARNESS)
        rep = self.lint()
        self.assertTrue(any("no [taxonomy] section; add one with domain (one of: base," in w for w in rep.warnings),
                        rep.warnings)
        self.assertEqual(self.lint("private").warnings, [])

    def test_missing_function_and_posture_warn(self):
        self.set_taxonomy('[taxonomy]\ndomain = "base"\n')
        warns = "\n".join(self.lint().warnings)
        self.assertIn("core: taxonomy: core/skills/demo has no function; set it in [taxonomy] as the bundle default "
                      "or in components.'skills/demo' (one of: govern,", warns)
        self.assertIn("core/bin/demo has no posture", warns)
        self.assertIn("core/agents/planner has no posture", warns)
        self.assertNotIn("doctor/core-ok has no posture", warns)

    def test_unknown_component_key(self):
        self.set_taxonomy('[taxonomy]\ndomain = "base"\nposture = "local"\nfunction = "client"\n'
                          '[taxonomy.components]\n"agents/nope" = {}\n')
        errs = self.lint().errors
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("components.'agents/nope' names no component of the bundle; use an id printed by "
                      "`harness catalog --bundle core`", errs[0])

    def test_posture_on_kind_without_one(self):
        self.set_taxonomy('[taxonomy]\ndomain = "base"\nposture = "local"\nfunction = "client"\n'
                          '[taxonomy.components]\n"guard.d/20-core" = { posture = "read-only" }\n'
                          '"steps/demo-login" = { posture = "read-only" }\n')
        errs = self.lint().errors
        self.assertEqual(len(errs), 2, errs)
        self.assertIn("components.'guard.d/20-core' sets posture; remove it (its decisions are derived from its "
                      "# rule: comments)", errs[0])
        self.assertIn("a human performs the step", errs[1])

    def test_posture_on_doctor_check_is_an_error(self):
        self.set_taxonomy('[taxonomy]\ndomain = "base"\nposture = "local"\nfunction = "client"\n'
                          '[taxonomy.components]\n"doctor/core-ok" = { posture = "local" }\n')
        errs = self.lint().errors
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("components.'doctor/core-ok' sets posture; remove it", errs[0])

    def test_fixed_function_contradicted(self):
        self.set_taxonomy('[taxonomy]\ndomain = "base"\nposture = "local"\nfunction = "client"\n'
                          '[taxonomy.components]\n"rules/10-core" = { function = "client" }\n'
                          '"bin/demo" = { function = "client" }\n')
        errs = self.lint().errors
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("sets function = 'client' but a rule is always 'govern'; remove the function key", errs[0])

    def test_component_stronger_than_bundle(self):
        self.set_taxonomy('[taxonomy]\ndomain = "base"\nposture = "local"\nfunction = "client"\n'
                          '[taxonomy.components]\n"skills/demo" = { posture = "label-gated" }\n'
                          '"agents/planner" = { posture = "read-only" }\n')
        errs = self.lint().errors
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("posture 'label-gated' is stronger than the bundle posture 'local'; raise taxonomy.posture", errs[0])

    def test_read_only_agent_with_auto_mode(self):
        path = os.path.join(self.core, "agents", "planner.md")
        self.write(path, self.read(path).replace("model:", "permissionMode: auto\nmodel:", 1))
        self.set_taxonomy('[taxonomy]\ndomain = "base"\nposture = "local"\nfunction = "plan"\n'
                          '[taxonomy.components]\n"agents/planner" = { posture = "read-only" }\n')
        # the check lives in the agent-tools rule; the taxonomy rule no longer repeats it
        self.assertEqual(self.lint().warnings, [])
        rep = L.Report()
        L.lint_agent_tools(self.bundle(), rep)
        self.assertEqual(len(rep.warnings), 1, rep.warnings)
        self.assertIn('agent-tools: core/agents/planner has posture read-only but its front matter sets '
                      'permissionMode: auto; set posture = "local"', rep.warnings[0])
        self.set_taxonomy('[taxonomy]\ndomain = "base"\nposture = "local"\nfunction = "plan"\n')
        rep = L.Report()
        L.lint_agent_tools(self.bundle(), rep)
        self.assertEqual(rep.warnings, [])

    def test_unclassified_control_warns(self):
        self.set_taxonomy('[taxonomy]\ndomain = "base"\nposture = "local"\nfunction = "client"\n', harness="")
        warns = self.lint().warnings
        self.assertEqual(sorted(w.split(": taxonomy: ")[1].split()[0] for w in warns),
                         ["core/agents/planner", "core/guard.d/20-core", "core/permissions", "core/rules/10-core",
                          "core/skills/demo"])
        self.assertIn("declare it as a guide or sensor so its control facet is known", warns[0])
        # an empty permission list needs no control
        self.write(os.path.join(self.core, "permissions.toml"), "[permissions]\nallow = []\nask = []\ndeny = []\n")
        self.assertNotIn("core/permissions", "\n".join(self.lint().warnings))

    def test_reserved_bundle_name(self):
        b = self.bundle()
        b.name = "profiles"
        rep = L.Report()
        L.lint_taxonomy(b, rep)
        self.assertTrue(any("reserved by the component id scheme" in e for e in rep.errors), rep.errors)

    def test_lint_bundle_runs_taxonomy(self):
        self.set_taxonomy('[taxonomy]\ndomain = "base"\nposture = "local"\n[taxonomy.components]\n"agents/nope" = {}\n')
        hub = self.hub(require_config=False, select=False)
        rep = L.Report()
        L.lint_bundle(hub.bundles["core"], hub.bundles, hub.schema, self.schema, rep)
        self.assertTrue(any("names no component" in e for e in rep.errors), rep.errors)
        self.assertIn("taxonomy", L.LINT_RULES)

    # ------------------------------------------------------------------ the repo's own bundles
    def test_repo_bundles_are_classified_and_lint_clean(self):
        public = M.discover_bundles([(os.path.join(REPO, "bundles"), "public")])
        for name, b in sorted(public.items()):
            self.assertNotIn("tags", b.data.get("bundle", {}), name)
            rep = L.Report()
            L.lint_taxonomy(b, rep)
            self.assertEqual((rep.errors, rep.warnings), ([], []), name)
            for c in T.components(b):
                self.assertTrue(c.domain, c.id)
                if c.kind in ("skill", "agent", "bin", "mcp"):
                    self.assertTrue(c.function and c.posture, c.id)
        agents = {c.id: (c.function, c.posture, c.model, c.control)
                  for b in public.values() for c in T.components(b) if c.kind == "agent"}
        self.assertEqual(agents, {
            "core/agents/Plan": ("plan", "read-only", "plan", "guide"),
            "core/agents/Auto": ("execute", "local", "execute", "guide"),
            "core/agents/code-reviewer": ("review", "read-only", "execute", "sensor (inferential)"),
            "k8s/agents/k8s-triage": ("investigate", "read-only", "execute", "guide"),
            "k8s/agents/k8s-auditor": ("review", "read-only", "execute", "guide"),
            "k8s/agents/infra-architect": ("plan", "read-only", "plan", "guide"),
        })

    # ------------------------------------------------------------------ docs
    def test_docs(self):
        self.set_taxonomy('[taxonomy]\ndomain = "base"\nposture = "local"\nfunction = "client"\n'
                          '[taxonomy.components]\n"agents/planner" = { function = "plan", posture = "read-only" }\n')
        b = self.bundle()
        body = D.bundle_body(b)
        self.assertIn("- **Domain / posture:** base / local", body)
        self.assertIn("## Components\n", body)
        self.assertLess(body.index("## Components"), body.index("## Requirements"))
        self.assertIn("- `core/agents/planner` — control: guide + sensor (inferential) · function: plan · "
                      "posture: read-only · model: {{ core.ticket_example }}", body)
        self.assertIn("**Doctor checks** (function: setup · posture: read-only; table below): "
                      "`core/doctor/core-ok`, `core/doctor/core-online`", body)
        provs = M.discover_providers([os.path.join(REPO, "providers")])
        cat = D.catalog_body([b], [provs[n] for n in sorted(provs)], self.tmp)
        self.assertIn("## Agents\n", cat)
        self.assertIn("| `core/agents/planner` | guide + sensor (inferential) | base | plan | read-only |", cat)
        self.assertIn("[`core/steps/demo-login`](bundles/core.md#demo-login)", cat)
        self.assertIn("**Reach:** enforced on claude; partial on copilot, gemini; advisory on codex, opencode.", cat)
        self.assertIn("| base | `core/agents/planner` | `core/bin/core-tool`, `core/bin/demo`, `core/skills/demo` | — |",
                      D.posture_body([b]))
        voc = D.vocabulary_body([b], [provs[n] for n in sorted(provs)])
        self.assertIn("| `investigate` | diagnoses to a root cause, never applies the fix | 0 |", voc)
        self.assertIn("### Facets by kind", voc)

    def test_expected_pages(self):
        pages = D.expected(REPO)
        self.assertIn("docs/reference/taxonomy.md", pages)
        self.assertEqual([src for src, _b, _h in pages["docs/catalog.md"]],
                         ["bundles/*/bundle.toml#catalog", "bundles/*/bundle.toml#posture"])


class ReviewRegressionTest(HubTestCase):
    """Edge cases found in review: pass/defer-only guards, doctor posture, README drift."""

    def test_pass_defer_only_guard_keeps_a_badge(self):
        self.assertEqual(T.guard_decisions("# rule: x -> pass : see y\n# rule: z -> defer : run w\n"),
                         "pass/defer only (2 rules)")
        self.assertEqual(T.guard_decisions("# rule: x -> deny : use y\n"), "deny 1")
        self.assertEqual(T.guard_decisions("echo no rules\n"), "helper (no rules)")

    def test_first_sentence_keeps_abbreviations(self):
        self.assertEqual(T.first_sentence("Use e.g. the CLI. Then stop."), "Use e.g. the CLI.")
        self.assertEqual(T.first_sentence("One line only"), "One line only")

    def test_readme_bundle_table_matches_manifests(self):
        """The hand-written README column repeats [taxonomy]; keep it honest."""
        import re
        text = open(os.path.join(REPO, "README.md"), encoding="utf-8").read()
        rows = dict(re.findall(r"^\| \[([a-z0-9-]+)\]\(docs/bundles/[a-z0-9-]+\.md\) \| ([^|]+?) \|", text, re.M))
        self.assertTrue(rows, "README bundle table not found")
        found = M.discover_bundles([(os.path.join(REPO, "bundles"), "public")])
        for b in (found[n] for n in sorted(found) if not found[n].private):
            tax = b.taxonomy
            self.assertEqual(rows.get(b.name), "%s / %s" % (tax.get("domain"), tax.get("posture")),
                             "README row for %s differs from its [taxonomy]; update README.md" % b.name)
