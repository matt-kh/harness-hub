"""[harness] guides and sensors: schema, lint pairing and ref checks, the guard-reason and guard-message heuristics,
and the generated docs (principle 6)."""
from __future__ import annotations

import os

from helpers import REPO, HubTestCase  # noqa: E402

from harness import docsgen as D
from harness import lint as L
from harness import manifest as M
from harness import schema_lite as SL

HARNESS = """
[harness]
coverage_note = "fixture"
guides = [
  { kind = "rule", ref = "rules/00-core.md", note = "conventions" },
]
sensors = [
  { kind = "doctor", ref = "doctor_checks" },
  { kind = "lint", ref = "guard-reasons" },
]
"""


class HarnessSectionTest(HubTestCase):
    def setUp(self):
        super().setUp()
        os.environ["HARNESS_LINT_SKIP_GATE"] = "1"
        self.core = os.path.join(self.bundles, "core")
        self.manifest = os.path.join(self.core, "bundle.toml")
        self.base = self.read(self.manifest)
        rules = sorted(os.listdir(os.path.join(self.core, "rules")))
        self.rule = "rules/" + rules[0]
        self.schema = M.load_schema("bundle.schema.json", REPO)

    def tearDown(self):
        os.environ.pop("HARNESS_LINT_SKIP_GATE", None)
        super().tearDown()

    def set_harness(self, text):
        self.write(self.manifest, self.base + text.replace("rules/00-core.md", self.rule))

    def core_bundle(self):
        return M.load_bundle(self.core)

    def lint(self):
        rep = L.Report()
        b = self.core_bundle()
        if not b.doctor_checks:
            b.doctor_checks.append({"id": "x", "cmd": "true"})
        L.lint_harness(b, rep)
        return rep

    # ------------------------------------------------------------------ schema
    def test_schema_accepts_section(self):
        self.set_harness(HARNESS)
        res = SL.validate(self.schema, self.core_bundle().data)
        self.assertEqual(res.errors, [])

    def test_schema_rejects_bad_kind_and_keys(self):
        for bad in ('guides = [{ kind = "guard", ref = "x" }]',    # sensor kind on the guide side
                    'sensors = [{ kind = "rule", ref = "x" }]',
                    'guides = [{ kind = "rule" }]',                # ref required
                    'extra = 1'):
            self.write(self.manifest, self.base + "\n[harness]\n" + bad + "\n")
            res = SL.validate(self.schema, self.core_bundle().data)
            self.assertTrue(res.errors, bad)

    def test_repo_bundles_validate_and_pair(self):
        public = M.discover_bundles([(os.path.join(REPO, "bundles"), "public")])
        self.assertEqual(len(public), 8)
        for name, b in sorted(public.items()):
            res = M.validate_bundle(b, self.schema)
            self.assertEqual(res.errors, [], name)
            self.assertEqual(b.pairing(), "paired", name)
            rep = L.Report()
            L.lint_harness(b, rep)
            self.assertEqual((rep.errors, rep.warnings), ([], []), name)

    # ------------------------------------------------------------------ pairing
    def test_paired_is_quiet(self):
        self.set_harness(HARNESS)
        rep = self.lint()
        self.assertEqual((rep.errors, rep.warnings), ([], []))

    def test_guides_only_warns(self):
        self.set_harness('\n[harness]\nguides = [{ kind = "rule", ref = "rules/00-core.md" }]\n')
        rep = self.lint()
        self.assertEqual(len(rep.warnings), 1)
        self.assertIn("feedforward only", rep.warnings[0])

    def test_sensors_only_warns(self):
        self.set_harness('\n[harness]\nsensors = [{ kind = "doctor", ref = "doctor_checks" }]\n')
        rep = self.lint()
        self.assertIn("feedback only", rep.warnings[0])

    def test_undeclared_warns_for_public_only(self):
        rep = self.lint()
        self.assertIn("no [harness] section", rep.warnings[0])
        b = M.load_bundle(self.core, origin="private")
        rep = L.Report()
        L.lint_harness(b, rep)
        self.assertEqual(rep.warnings, [])

    def test_dangling_refs_are_errors(self):
        self.set_harness('\n[harness]\nguides = [{ kind = "skill", ref = "skills/nope" }]\n'
                         'sensors = [{ kind = "doctor", ref = "no-such-check" }, { kind = "lint", ref = "nope" }]\n')
        rep = self.lint()
        self.assertEqual(len(rep.errors), 3, rep.errors)

    # ------------------------------------------------------------------ guard reasons
    def test_reason_heuristic(self):
        guard_dir = os.path.join(self.core, "guard.d")
        section = sorted(f for f in os.listdir(guard_dir) if f[:2].isdigit())[0]
        path = os.path.join(guard_dir, section)
        before = self.read(path).count("\n")
        self.write(path, self.read(path) + "\n".join([
            "",
            "# rule: foo -> deny : prints the token",
            "# rule: bar -> ask : prints the token; run 'x status' instead",
            "# rule: baz -> allow : promptless",
            "# rule: qux -> deny : see docs/x.md",
            ""]))
        hub = self.hub(require_config=False, select=False)
        rep = L.Report()
        L.lint_bundle(hub.bundles["core"], hub.bundles, hub.schema, self.schema, rep)
        flagged = [w for w in rep.warnings if "guard-reasons" in w
                   and int(w.split(".sh:")[1].split()[0]) > before]  # only the rows added here
        self.assertEqual(len(flagged), 1, flagged)
        self.assertIn("'prints the token'", flagged[0])

    def test_message_heuristic(self):
        text = "\n".join([
            'ask "foo"',                                              # 1: flagged
            'deny "foo — use bar instead"',                           # 2: clean
            'ask "$(k8s_target) ${RUN:-x} $USE"',                     # 3: expansions only: flagged
            '# deny "a comment is not a message"',                    # 4: skipped
            'x && defer "multi',                                      # 5: flagged (spans two lines)
            'line"',
            'deny "quoted \\"use\\" word"',                           # 7: clean (escaped quotes)
            'undeny "not a call"',                                    # 8: not a deny/ask/defer call
            ''])
        got = L.guard_message_findings(text)
        self.assertEqual([(ln, fn) for ln, fn, _m in got], [(1, "ask"), (3, "ask"), (5, "defer")], got)
        guard_dir = os.path.join(self.core, "guard.d")
        section = sorted(f for f in os.listdir(guard_dir) if f[:2].isdigit())[0]
        path = os.path.join(guard_dir, section)
        rep = L.Report()
        L.lint_guard_messages(self.core_bundle(), rep)
        before = list(rep.warnings)                               # the fixture's own bare messages
        self.write(path, self.read(path) + '\nask "bare message"\ndeny "bare - use x instead"\n')
        rep = L.Report()
        L.lint_guard_messages(self.core_bundle(), rep)
        added = [w for w in rep.warnings if w not in before]
        self.assertEqual(len(added), 1, added)
        self.assertIn("guard-messages: the ask message 'bare message'", added[0])
        rep = L.Report()
        L.lint_guard_messages(M.load_bundle(self.core, origin="private"), rep)
        self.assertEqual(rep.warnings, [])

    # ------------------------------------------------------------------ docs
    def test_docs_render_table_and_coverage(self):
        self.set_harness(HARNESS)
        b = self.core_bundle()
        body = D.bundle_body(b)
        self.assertIn("## Guides and sensors", body)
        self.assertIn("Pairing: **paired**", body)
        self.assertIn("| guide | rule | `%s` | conventions |" % self.rule, body)
        self.assertIn("**Not covered:** fixture", body)
        cov = D.coverage_body([b])
        self.assertIn("| [core](../bundles/core.md#guides-and-sensors) | 1 | rule | 2 | doctor, lint | paired | fixture |", cov)

    def test_coverage_page_is_generated(self):
        pages = D.expected(REPO)
        self.assertIn("docs/reference/harness-coverage.md", pages)
