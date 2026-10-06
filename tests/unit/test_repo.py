"""`harness repo` and the shared `.harness.toml` subset parser (principle 8: user-level by design)."""
from __future__ import annotations

import io
import json
import os
import types
from contextlib import redirect_stderr, redirect_stdout

from helpers import REPO, HubTestCase  # noqa: E402

from harness import cli
from harness import repo as RP
from harness import taxonomy as T
from harness import toml_compat

GOOD = """# a comment
[repo]
name = "shop"
harness = 'docs/agent-workflow.md'

[owns]
domains = ["tracker"]
components = ["core/guard.d/20-core", 'core/skills/demo']

[overrides]
WORK_TICKET_ALLOW_TRANSITION = "1"
WORK_TICKET_ALLOW_DEFAULT_PUSH_RE = '^/home/u/dev/shop$'
"""


class SubsetParserTest(HubTestCase):
    def setUp(self):
        super().setUp()
        self.hr = RP.parser_module()
        self.root = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(self.root, ".git"))
        os.makedirs(os.path.join(self.root, "a", "b"))

    def test_subset_agrees_with_toml(self):
        data, problems = self.hr.parse_subset(GOOD)
        self.assertEqual(problems, [])
        self.assertEqual(data, toml_compat.loads(GOOD))

    def test_subset_refuses_what_bash_cannot_parse(self):
        cases = {
            'components = ["a"] # trailing': "one-line array of strings",
            'domains = "scm"': "one-line array of strings",
            'x = ["a\\\\.b"]': "unquoted or escaped array item",
            "[owns": "unterminated section header",
            "owns = [": "one-line array of strings",
            '"quoted key" = "x"': "bad key",
            "components = [a, b]": "unquoted or escaped array item",
            "just words": "not key = value",
        }
        for line, why in cases.items():
            _d, problems = self.hr.parse_subset("[owns]\n" + line + "\n")
            self.assertTrue(problems and why in problems[0][1], (line, problems))
            self.assertEqual(problems[0][0], 2, line)
        _d, problems = self.hr.parse_subset('[repo]\nx = "a\\\\.b"\n')
        self.assertEqual(problems, [(2, "x must be a quoted string or a one-line array (no inline comments or escapes)")])
        data, problems = self.hr.parse_subset("#" * 17000)
        self.assertEqual((data, problems), ({}, [(0, "larger than 16 KiB")]))
        data, problems = self.hr.parse_subset("[owns]\n" + "#\n" * 400)
        self.assertEqual((data, problems), ({}, [(0, "more than 400 lines")]))
        data, problems = self.hr.parse_subset('[owns]\ndomains = ["scm"]\n' + "#\n" * 398)
        self.assertEqual((data, problems), ({"owns": {"domains": ["scm"]}}, []))   # exactly 400 lines

    def test_subset_duplicates_and_line_ends(self):
        data, problems = self.hr.parse_subset('[owns]\ndomains = ["scm"]\ndomains = ["tracker"]\n')
        self.assertEqual(data, {"owns": {"domains": ["scm"]}})
        self.assertEqual(problems, [(3, "duplicate key domains in [owns]; the guard uses the first")])
        # an invalid first line does not count as the first occurrence
        data, problems = self.hr.parse_subset('[owns]\ndomains = "scm"\ndomains = ["tracker"]\n')
        self.assertEqual(data, {"owns": {"domains": ["tracker"]}})
        # CRLF and other separators: split on \n only, like bash `read`; \r is trimmed whitespace
        data, problems = self.hr.parse_subset('[repo]\r\nname = "a\x0cb"\r\n')
        self.assertEqual((data, problems), ({"repo": {"name": "a\x0cb"}}, []))

    def test_root_and_worktree_file(self):
        self.assertEqual(RP.find_root(os.path.join(self.root, "a", "b")), self.root)
        wt = os.path.join(self.tmp, "wt")
        os.makedirs(wt)
        self.write(os.path.join(wt, ".git"), "gitdir: /elsewhere/.git/worktrees/x\n")
        self.assertEqual(RP.find_root(wt), wt)
        self.assertIsNone(RP.find_root(self.home))
        self.assertIsNone(self.hr.repo_root("relative/dir"))

    def test_repo_owns(self):
        self.write(os.path.join(self.root, ".harness.toml"), GOOD)
        sub = os.path.join(self.root, "a", "b")
        self.assertTrue(self.hr.repo_owns("core/guard.d/20-core", "base", sub))           # by id
        self.assertTrue(self.hr.repo_owns("jira/guard.d/70-jira", "tracker", sub))         # by domain
        self.assertFalse(self.hr.repo_owns("k8s/skills/k8s", "kubernetes", sub))
        self.write(os.path.join(self.root, ".harness.toml"),
                   '[owns]\ndomains = ["base"]\ncomponents = ["core/guard.d/20-credentials", "core/permissions"]\n')
        self.assertFalse(self.hr.repo_owns("core/guard.d/20-credentials", "base", sub))   # never yields
        self.assertFalse(self.hr.repo_owns("core/permissions", "base", sub))


class RepoCommandTest(HubTestCase):
    def setUp(self):
        super().setUp()
        self.root = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(self.root, ".git"))
        self.decl = os.path.join(self.root, ".harness.toml")
        # two allow-listed overrides in the fixture guard sections
        sec = os.path.join(self.bundles, "core", "guard.d", "20-core.sh")
        head = "# rule: fixture-deny ... -> deny : fixture deny rule\n"
        self.write(sec, self.read(sec).replace(head, head + (
            '# repo-override: WORK_TICKET_ALLOW_TRANSITION = "" -> =1: transitions ask\n'
            '# repo-override: WORK_TICKET_BASE_BRANCH_RE = "^(master|main)$" -> base branches\n')))
        self._env = {k: os.environ.pop(k) for k in ("WORK_TICKET_ALLOW_TRANSITION", "WORK_TICKET_BASE_BRANCH_RE")
                     if k in os.environ}

    def tearDown(self):
        os.environ.update(self._env)
        super().tearDown()

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = cli.main(list(argv) + ["--config", self.cfg])
        return rc, out.getvalue() + err.getvalue()

    def comps(self):
        hub = self.hub(require_config=False, select=False)
        return [c for n in sorted(hub.bundles) for c in T.components(hub.bundles[n])]

    # ------------------------------------------------------------------ API
    def test_load_reports_problems(self):
        self.write(self.decl, "[owns]\ndomains = [\"nope\", \"base\"]\n"
                              "components = [\"core/guard.d/20-core\", \"core/permissions\", \"zz/skills/x\", "
                              "\"core/agents/planner\", \"core/rules/10-core\"]\n"
                              "[overrides]\nGUARD_GIT = \"/bin/true\"\nWORK_TICKET_LABEL = \"x\"\n"
                              "WORK_TICKET_ALLOW_TRANSITION = \"1\" # inline\n[extra]\nk = \"v\"\n")
        names = ["WORK_TICKET_ALLOW_TRANSITION", "WORK_TICKET_BASE_BRANCH_RE"]
        decl = RP.load(self.root, self.comps(), names, home=REPO)
        msgs = "\n".join(str(p) for p in decl.problems)
        for want in ("line 7: WORK_TICKET_ALLOW_TRANSITION must be a quoted string",
                     "[overrides] WORK_TICKET_ALLOW_TRANSITION: TOML reads \"1\" but the guard's subset reads null",
                     "unknown section [extra]",
                     "schema: owns.domains[0]",
                     "unknown domain 'nope'",
                     "domains = base: the credential section",
                     "zz/skills/x names no component",
                     "core/permissions never yields",
                     "core/agents/planner yields by name",
                     "core/rules/10-core yields by text",
                     "GUARD_GIT is settable only from the developer's own environment",
                     "WORK_TICKET_LABEL is not a repo override"):
            self.assertIn(want, msgs)

    def test_load_reports_duplicates_and_non_utf8(self):
        self.write(self.decl, '[owns]\ndomains = ["tracker"]\ndomains = ["scm"]\n[overrides]\nWORK_TICKET_FOO_PY = "x"\n')
        decl = RP.load(self.root, self.comps(), ["WORK_TICKET_ALLOW_TRANSITION"], home=REPO)
        errors = [str(p) for p in decl.problems if p.level == "error"]
        self.assertTrue(any("line 3: duplicate key domains in [owns]; the guard uses the first" in e for e in errors), errors)
        self.assertTrue(any("WORK_TICKET_FOO_PY is settable only from the developer's own environment" in e
                            for e in errors), errors)
        self.assertEqual(decl.domains, ["tracker"])
        with open(self.decl, "wb") as fh:
            fh.write(b'[repo]\nname = "caf\xe9"\n[owns]\ndomains = ["scm"]\n')
        decl = RP.load(self.root, self.comps(), [], home=REPO)          # no UnicodeDecodeError
        self.assertEqual(decl.domains, ["scm"])
        self.assertTrue(any("not UTF-8" in str(p) and p.level == "warning" for p in decl.problems), decl.problems)
        rc, out = self.run_cli("repo", self.root)
        self.assertIn("not UTF-8", out)

    def test_yielding_and_effective_overrides(self):
        self.write(self.decl, '[owns]\ndomains = ["tracker"]\ncomponents = ["core/guard.d/20-core"]\n'
                              '[overrides]\nWORK_TICKET_ALLOW_TRANSITION = "1"\nWORK_TICKET_BASE_BRANCH_RE = "^(trunk)$"\n')
        comps = self.comps()
        decl = RP.load(self.root, comps, home=REPO)
        got = {c.id: why for c, why in RP.yielding(decl, comps)}
        self.assertIn("lists it in [owns] components", got["core/guard.d/20-core"])
        self.assertIn("lists its domain tracker", got["alpha/guard.d/40-alpha"])
        hub = self.hub(require_config=False, select=False)
        ovr = T.repo_overrides([hub.bundles[n] for n in sorted(hub.bundles)])
        settings = [(".claude/settings.json", {"env": {"WORK_TICKET_BASE_BRANCH_RE": "^(release)$"}})]
        res = {o["name"]: o for o in RP.effective_overrides(
            decl, ovr, {"WORK_TICKET_ALLOW_TRANSITION": "0"}, settings, {"WORK_TICKET_BASE_BRANCH_RE": "^(dev)$"})}
        self.assertEqual((res["WORK_TICKET_ALLOW_TRANSITION"]["value"], res["WORK_TICKET_ALLOW_TRANSITION"]["source"]),
                         ("0", "environment"))
        self.assertEqual(res["WORK_TICKET_ALLOW_TRANSITION"]["shadowed"], [".harness.toml=1"])
        b = res["WORK_TICKET_BASE_BRANCH_RE"]
        self.assertEqual((b["value"], b["source"]), ("^(release)$", ".claude/settings.json env"))
        self.assertEqual(b["shadowed"], [".harness.toml=^(trunk)$", "guard.env=^(dev)$"])
        res = {o["name"]: o for o in RP.effective_overrides(decl, ovr, {}, [], {"WORK_TICKET_BASE_BRANCH_RE": "x"})}
        self.assertEqual(res["WORK_TICKET_BASE_BRANCH_RE"]["source"], ".harness.toml")   # file beats guard.env
        res = {o["name"]: o for o in RP.effective_overrides(RP.Declaration(None), ovr, {}, [], {})}
        self.assertEqual((res["WORK_TICKET_BASE_BRANCH_RE"]["value"], res["WORK_TICKET_BASE_BRANCH_RE"]["source"]),
                         ("^(master|main)$", "default"))

    def test_collisions_and_disable_all_hooks(self):
        self.write(os.path.join(self.root, ".claude", "skills", "demo", "SKILL.md"), "---\nname: demo\n---\n")
        self.write(os.path.join(self.root, ".claude", "skills", "mine", "SKILL.md"), "---\nname: mine\n---\n")
        self.write(os.path.join(self.root, ".claude", "agents", "planner.md"), "---\nname: planner\n---\n")
        self.write(os.path.join(self.root, ".claude", "settings.json"), '{"disableAllHooks": true}')
        hub = self.hub(require_config=False, select=False)
        bundles = [hub.bundles[n] for n in sorted(hub.bundles)]
        prov = types.SimpleNamespace(name="claude", precedence={"skills": "user", "agents": "project",
                                                                "repo_dir": ".claude",
                                                                "skill_override_hint": '"skillOverrides": {"<name>": "off"}'})
        got = {(c["kind"], c["name"]): c for c in RP.collisions(self.root, bundles, [prov])}
        self.assertEqual(sorted(got), [("agent", "planner"), ("skill", "demo")])
        self.assertIn("shadows the repository's", got[("skill", "demo")]["effect"])
        self.assertIn('"skillOverrides": {"demo": "off"}', got[("skill", "demo")]["fix"])
        self.assertIn("replaces the hub's", got[("agent", "planner")]["effect"])
        self.assertEqual(got[("skill", "demo")]["hub"], "core/skills/demo")
        self.assertEqual(RP.hooks_disabled(RP._settings(self.root, [prov])), [".claude/settings.json"])
        self.assertEqual(hub.providers["claude"].precedence["skills"], "user")   # the adapter declares it

    # ------------------------------------------------------------------ CLI
    def test_cli_show(self):
        rc, out = self.run_cli("repo", self.root)
        self.assertEqual(rc, 0, out)
        self.assertIn("declaration  none - `harness repo init` prints a template", out)
        self.assertIn("nothing: every guard section and skill applies", out)
        self.assertIn("never yields: core/permissions", out)   # fixture bundles: only the permission list
        self.write(self.decl, '[owns]\ndomains = ["tracker"]\n[overrides]\nWORK_TICKET_ALLOW_TRANSITION = "1"\n')
        rc, out = self.run_cli("repo", "show", self.root)
        self.assertEqual(rc, 0, out)
        self.assertIn("alpha/guard.d/40-alpha", out)
        self.assertIn('WORK_TICKET_ALLOW_TRANSITION  "1"', out)
        rc, out = self.run_cli("repo", self.root, "--json")
        data = json.loads(out)
        self.assertEqual([y["id"] for y in data["yielding"]], ["alpha/guard.d/40-alpha"])
        self.assertEqual(data["declaration"]["owns"]["domains"], ["tracker"])
        self.write(self.decl, '[overrides]\nHARNESS_CRED_EXTRA_RE = ""\n')
        rc, out = self.run_cli("repo", self.root)
        self.assertEqual(rc, 1)                                   # errors in the declaration
        self.assertIn("HARNESS_CRED_EXTRA_RE is settable only from the developer's own environment", out)
        rc, out = self.run_cli("repo", os.path.join(self.tmp, "home"))
        self.assertIn("not inside a git checkout", out)

    def test_cli_owns(self):
        self.write(self.decl, '[owns]\ndomains = ["base"]\ncomponents = ["alpha/guard.d/40-alpha", "core/permissions"]\n')
        rc, out = self.run_cli("repo", "owns", "alpha/guard.d/40-alpha", self.root)
        self.assertEqual(rc, 0, out)
        self.assertIn("owned: alpha/guard.d/40-alpha yields here (.harness.toml lists it in [owns] components)", out)
        rc, out = self.run_cli("repo", "owns", "core/guard.d/20-core", self.root)
        self.assertEqual(rc, 0, out)
        self.assertIn("lists its domain base", out)
        rc, out = self.run_cli("repo", "owns", "core/permissions", self.root)
        self.assertEqual(rc, 1)
        self.assertIn("never yields", out)
        rc, out = self.run_cli("repo", "owns", "beta/guard.d/15-beta", self.root)
        self.assertEqual(rc, 1)
        rc, out = self.run_cli("repo", "owns", "nope/skills/x", self.root)
        self.assertEqual(rc, 2)
        self.assertIn("names no component", out)
        rc, out = self.run_cli("repo", "owns")
        self.assertEqual(rc, 2)

    def test_cli_init(self):
        rc, out = self.run_cli("repo", "init", self.root)
        self.assertEqual(rc, 0)
        self.assertIn("[owns]", out)
        self.assertIn("#   core/guard.d/20-core", out)
        self.assertFalse(os.path.exists(self.decl))
        data, problems = RP.parser_module().parse_subset(out)
        self.assertEqual(problems, [])
        self.assertEqual(data, {k: v for k, v in toml_compat.loads(out).items() if v})  # only comments
        rc, out = self.run_cli("repo", "init", self.root, "--write")
        self.assertEqual(rc, 0, out)
        self.assertTrue(os.path.isfile(self.decl))
        self.write(self.decl, "# mine\n")
        rc, out = self.run_cli("repo", "init", self.root, "--write")
        self.assertEqual(rc, 1)
        self.assertIn("already exists", out)
        self.assertEqual(self.read(self.decl), "# mine\n")
        rc, out = self.run_cli("repo", "init", self.home, "--write")
        self.assertEqual(rc, 1)
        self.assertIn("not inside a git checkout", out)
