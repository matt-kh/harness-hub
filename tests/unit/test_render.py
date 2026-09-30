"""Templating rules, managed blocks, JSON merge, TOML blocks, guard concatenation, MCP."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import unittest

from helpers import REPO, HubTestCase  # noqa: E402

from harness import render as R
from harness import toml_compat


class TemplateTest(unittest.TestCase):
    CTX = {"a": {"b": "B", "flag": True, "n": 3, "list": ["x", "y"], "t": {"k": 1}}, "hub": {"home": "/h"}}

    def expand(self, text):
        t = R.Templater(self.CTX)
        return t.expand(text, "f.md"), t

    def test_rules(self):
        out, t = self.expand("{{ a.b }} {{a.b}} {{  a.b }} ${{ a.b }} \\{{ a.b }} {{ a.flag }} {{ a.n }} {{ a.list }} {{ a.t }}")
        self.assertEqual(out, 'B {{a.b}} {{  a.b }} ${{ a.b }} {{ a.b }} true 3 x, y {"k":1}')
        self.assertEqual(t.missing, [])

    def test_single_segment_and_uppercase_are_not_templates(self):
        out, t = self.expand("{{ a }} {{ A.b }}")
        self.assertEqual(out, "{{ a }} {{ A.b }}")

    def test_missing_keys_are_collected_and_raise(self):
        _out, t = self.expand("{{ a.nope }} and {{ z.q }}")
        self.assertEqual([k for _w, k in t.missing], ["a.nope", "z.q"])
        with self.assertRaises(R.RenderError) as cm:
            t.check()
        self.assertIn("f.md: {{ a.nope }} has no value", str(cm.exception))

    def test_template_keys(self):
        self.assertEqual(R.template_keys("{{ a.b }} ${{ c.d }} {{ e.f }} {{ a.b }}"), ["a.b", "e.f"])


class ManagedBlockTest(unittest.TestCase):
    B1 = R.Block("core", "rules/10-a.md", "one")
    B2 = R.Block("gh", "rules/40-b.md", "two")
    B3 = R.Block("core", "rules/20-c.md", "three")

    def test_create(self):
        text, state, conf = R.merge_managed_blocks(None, [self.B1, self.B2], {})
        self.assertEqual(text, "<!-- harness:begin bundle=core file=rules/10-a.md -->\none\n"
                               "<!-- harness:end bundle=core file=rules/10-a.md -->\n\n"
                               "<!-- harness:begin bundle=gh file=rules/40-b.md -->\ntwo\n"
                               "<!-- harness:end bundle=gh file=rules/40-b.md -->\n")
        self.assertEqual(set(state), {"core rules/10-a.md", "gh rules/40-b.md"})
        self.assertEqual(conf, [])

    def test_insert_into_user_file_preserves_text(self):
        live = "# My notes\n\nKeep  this   spacing.\n"
        text, _s, _c = R.merge_managed_blocks(live, [self.B1], {})
        self.assertTrue(text.startswith(live))
        self.assertIn("one", text)

    def test_replace_in_place_and_idempotent(self):
        live = "top\n\n" + R.block_text(R.Block("core", "rules/10-a.md", "old")) + "\n\nbottom\n"
        text, state, _c = R.merge_managed_blocks(live, [self.B1], {"core rules/10-a.md": R.body_sha("old")})
        self.assertEqual(text, live.replace("\nold\n", "\none\n"))
        again, _s, _c = R.merge_managed_blocks(text, [self.B1], state)
        self.assertEqual(again, text)

    def test_new_block_goes_next_to_its_ordered_neighbour(self):
        text, state, _ = R.merge_managed_blocks("user\n", [self.B1, self.B2], {})
        text2, _s, _c = R.merge_managed_blocks(text + "tail\n", [self.B1, self.B3, self.B2], state)
        self.assertLess(text2.index("one"), text2.index("three"))
        self.assertLess(text2.index("three"), text2.index("two"))
        self.assertTrue(text2.startswith("user\n"))
        self.assertTrue(text2.endswith("tail\n"))

    def test_remove_block_keeps_user_text(self):
        text, state, _ = R.merge_managed_blocks("user\n", [self.B1, self.B2], {})
        text2, state2, _ = R.merge_managed_blocks(text, [self.B1], state)
        self.assertNotIn("two", text2)
        self.assertEqual(text2, R.merge_managed_blocks("user\n", [self.B1], {})[0])
        text3, _s, _ = R.merge_managed_blocks(text2, [], state2)
        self.assertEqual(text3, "user\n")

    def test_hand_edited_block_is_a_conflict_user_wins(self):
        text, state, _ = R.merge_managed_blocks(None, [self.B1], {})
        edited = text.replace("\none\n", "\nmine\n")
        out, _s, conf = R.merge_managed_blocks(edited, [R.Block("core", "rules/10-a.md", "new")], state)
        self.assertIn("mine", out)
        self.assertEqual(len(conf), 1)
        out, _s, conf = R.merge_managed_blocks(edited, [R.Block("core", "rules/10-a.md", "new")], state, adopt=True)
        self.assertIn("new", out)
        self.assertEqual(conf, [])


def json_target(fragment, owners=("hooks", "permissions"), replace=(), sort=(), exclusive=()):
    t = R.Target("/x/settings.json", "p", "json-merge")
    t.fragment = fragment
    t.owners = [(tuple(o.split(".")), "deep") for o in owners] + [(tuple(o.split(".")), "replace") for o in replace]
    t.sort_arrays = [tuple(s.split(".")) for s in sort]
    t.exclusive = [[tuple(s.split(".")) for s in grp] for grp in exclusive]
    return t


class JsonMergeTest(unittest.TestCase):
    PERMS = ["permissions.allow", "permissions.ask", "permissions.deny"]

    def test_owner_keys_only_other_keys_preserved(self):
        live = {"theme": "dark", "permissions": {"allow": ["Bash(ls:*)"]}, "model": "x"}
        t = json_target({"permissions": {"allow": ["Bash(jq:*)"], "deny": ["Read(~/.ssh/**)"]}}, sort=self.PERMS)
        doc, owned, conf = R.merge_json(live, t, [])
        self.assertEqual(doc["theme"], "dark")
        self.assertEqual(doc["model"], "x")
        self.assertEqual(doc["permissions"]["allow"], ["Bash(jq:*)", "Bash(ls:*)"])  # dedupe + sorted
        self.assertEqual(conf, [])
        # idempotent with the recorded ownership
        doc2, owned2, _ = R.merge_json(doc, t, owned)
        self.assertEqual(doc2, doc)
        self.assertEqual(owned2, owned)

    def test_removed_contribution_is_unapplied_user_entries_stay(self):
        t = json_target({"permissions": {"allow": ["A", "B"]}})
        doc, owned, _ = R.merge_json({"permissions": {"allow": ["U"]}}, t, [])
        t2 = json_target({"permissions": {"allow": ["A"]}})
        doc2, _o, _c = R.merge_json(doc, t2, owned)
        self.assertEqual(doc2["permissions"]["allow"], ["U", "A"])

    def test_exclusive_user_placement_wins(self):
        live = {"permissions": {"deny": ["Bash(rm:*)"]}}
        t = json_target({"permissions": {"allow": ["Bash(rm:*)"]}}, exclusive=[self.PERMS])
        doc, owned, conf = R.merge_json(live, t, [])
        self.assertNotIn("allow", doc["permissions"])
        self.assertEqual(len(conf), 1)
        self.assertIn("user placement kept", conf[0])

    def test_scalar_conflict_and_adopt(self):
        t = json_target({"env": {"MODEL": "opus"}}, owners=("env",))
        doc, owned, conf = R.merge_json({"env": {"MODEL": "mine"}}, t, [])
        self.assertEqual(doc["env"]["MODEL"], "mine")
        self.assertEqual(len(conf), 1)
        doc, owned, conf = R.merge_json({"env": {"MODEL": "mine"}}, t, [], adopt=True)
        self.assertEqual(doc["env"]["MODEL"], "opus")
        self.assertEqual(conf, [])
        # later hand edit of a value we own -> conflict, user wins
        doc["env"]["MODEL"] = "edited"
        doc2, _o, conf = R.merge_json(doc, t, owned)
        self.assertEqual(doc2["env"]["MODEL"], "edited")
        self.assertEqual(len(conf), 1)

    def test_replace_mode_for_mcp_servers(self):
        live = {"projects": {"/p": {"x": 1}}, "mcpServers": {"theirs": {"command": "a"}}}
        t = json_target({"mcpServers": {"ours": {"command": "b", "args": ["1"]}}}, owners=(), replace=("mcpServers.ours",))
        doc, owned, conf = R.merge_json(live, t, [])
        self.assertEqual(doc["mcpServers"]["theirs"], {"command": "a"})
        self.assertEqual(doc["mcpServers"]["ours"], {"command": "b", "args": ["1"]})
        self.assertEqual(doc["projects"], {"/p": {"x": 1}})
        t2 = json_target({"mcpServers": {"ours": {"command": "c", "args": []}}}, owners=(), replace=("mcpServers.ours",))
        doc2, _o, conf = R.merge_json(doc, t2, owned)
        self.assertEqual(doc2["mcpServers"]["ours"], {"command": "c", "args": []})   # replaced wholesale
        self.assertEqual(conf, [])
        # a foreign server with our name is kept
        doc3, _o, conf = R.merge_json({"mcpServers": {"ours": {"command": "x"}}}, t2, [])
        self.assertEqual(doc3["mcpServers"]["ours"], {"command": "x"})
        self.assertEqual(len(conf), 1)

    def test_owner_view_hides_other_keys(self):
        t = json_target({}, owners=("hooks",))
        self.assertEqual(R.owner_view({"hooks": {"a": 1}, "oauthAccount": {"secret": 1}}, t), {"hooks": {"a": 1}})


class TomlBlockTest(unittest.TestCase):
    def test_blocks_append_replace_and_validate(self):
        live = 'model = "x"\n\n[profile.default]\nsandbox = "workspace-write"\n'
        text, state, conf = R.merge_toml_blocks(live, {"mcp": '[mcp_servers.a]\ncommand = "a"\n'}, {})
        self.assertEqual(conf, [])
        data = toml_compat.loads(text)
        self.assertEqual(data["model"], "x")
        self.assertEqual(data["mcp_servers"]["a"]["command"], "a")
        text2, state2, _ = R.merge_toml_blocks(text, {"mcp": '[mcp_servers.a]\ncommand = "b"\n'}, state)
        self.assertEqual(toml_compat.loads(text2)["mcp_servers"]["a"]["command"], "b")
        self.assertEqual(text2.count("harness:begin"), 1)
        again, _s, _c = R.merge_toml_blocks(text2, {"mcp": '[mcp_servers.a]\ncommand = "b"\n'}, state2)
        self.assertEqual(again, text2)
        removed, _s, _c = R.merge_toml_blocks(text2, {}, state2)
        self.assertEqual(toml_compat.loads(removed), toml_compat.loads(live))

    def test_invalid_combination_keeps_live(self):
        live = '[mcp_servers.a]\ncommand = "mine"\n'
        text, _s, conf = R.merge_toml_blocks(live, {"mcp": '[mcp_servers.a]\ncommand = "b"\n'}, {})
        self.assertEqual(text, live)
        self.assertIn("invalid TOML", conf[0])


class RenderHubTest(HubTestCase):
    def test_guard_concatenation_order(self):
        hub = self.hub()
        rows = R.guard_sections(hub.active_bundles)
        self.assertEqual([(r[0], r[1]) for r in rows],
                         [("15-beta.sh", "beta"), ("20-core.sh", "core"), ("40-alpha.sh", "alpha")])
        data = R.build_guard(hub.bundle("core"), hub.active_bundles).decode()
        self.assertTrue(data.startswith("#!/usr/bin/env bash\n# Fixture guard engine"))
        self.assertLess(data.index("section 15-beta.sh"), data.index("section 20-core.sh"))
        self.assertTrue(data.rstrip().endswith("exit 0"))
        self.assertNotIn("tests.sh", data)

    def test_guard_matches_core_build_sh(self):
        """The renderer and bundles/core/guard/build.sh implement the same ordering contract."""
        build = os.path.join(REPO, "bundles", "core", "guard", "build.sh")
        if not os.path.isfile(build):
            self.skipTest("bundles/core/guard/build.sh not present")
        tree = os.path.join(self.tmp, "tree", "bundles")
        shutil.copytree(self.bundles, tree)
        os.makedirs(os.path.join(tree, "core", "guard"), exist_ok=True)
        shutil.copy(build, os.path.join(tree, "core", "guard", "build.sh"))
        out = os.path.join(self.tmp, "built.sh")
        subprocess.check_call(["bash", os.path.join(tree, "core", "guard", "build.sh"), out],
                              env=dict(os.environ, HARNESS_GUARD_BUNDLES="alpha,beta"))
        hub = self.hub()
        with open(out, "rb") as fh:
            self.assertEqual(fh.read(), R.build_guard(hub.bundle("core"), hub.active_bundles))

    def test_rendered_guard_decides_and_reads_guard_env(self):
        targets = R.Renderer(self.hub()).render(self.hub().filter_providers(["claude"]))
        by = {t.path: t for t in targets}
        hooks = self.h(".claude", "hooks")
        os.makedirs(hooks)
        for name in ("guard-bash.sh", "guard.env"):
            with open(os.path.join(hooks, name), "wb") as fh:
                fh.write(by[os.path.join(hooks, name)].content)

        def run(cmd, env=None):
            p = subprocess.run(["bash", os.path.join(hooks, "guard-bash.sh")], input=cmd.encode(),
                               stdout=subprocess.PIPE, env=dict(os.environ, **(env or {})))
            return p.stdout.decode()

        out = json.loads(run(json.dumps({"tool_name": "Bash", "tool_input": {"command": "alpha-deny now"}})))
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("alpha.example.com", out["hookSpecificOutput"]["permissionDecisionReason"])
        out = json.loads(run(json.dumps({"tool_name": "Bash", "tool_input": {"command": "alpha-deny"}}),
                             {"ALPHA_HOST": "from-env"}))
        self.assertIn("from-env", out["hookSpecificOutput"]["permissionDecisionReason"])  # env wins over guard.env
        out = json.loads(run("not json"))
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(run(json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}})), "")

    def test_guard_env_quoting(self):
        env = R.guard_env({"A": "it's (^|x)$", "B": "plain"}).decode()
        self.assertIn("A='it'\\''s (^|x)$'", env)
        out = subprocess.run(["bash", "-c", "set -e; . /dev/stdin; printf '%s' \"$A\""], input=env.encode(),
                             stdout=subprocess.PIPE).stdout.decode()
        self.assertEqual(out, "it's (^|x)$")

    def test_mcp_env_files_wrapper(self):
        e = R.mcp_entry({"command": "uvx", "args": ["srv", "--x y"], "env": {"U": "1"},
                         "env_files": {"TOKEN": "~/.config/t"}})
        self.assertEqual(e["command"], "bash")
        self.assertEqual(e["args"], ["-c", "export TOKEN=\"$(cat ~/.config/t)\"; exec uvx srv '--x y'"])
        self.assertEqual(e["env"], {"U": "1"})
        self.assertNotIn("TOKEN", json.dumps(e["env"]))

    def test_every_provider_target(self):
        hub = self.hub()
        targets = {t.path: t for t in R.Renderer(hub).render(hub.active_providers)}
        claude_settings = targets[self.h(".claude", "settings.json")]
        doc = json.loads(R.pure_content(claude_settings))
        self.assertEqual(doc["hooks"]["PreToolUse"][0]["hooks"][0]["command"],
                         "bash %s" % self.h(".claude", "hooks", "guard-bash.sh"))
        self.assertEqual(doc["permissions"]["deny"], ["Read(~/.config/demo/**)"])
        self.assertEqual(doc["env"], {"CLAUDE_CODE_SUBAGENT_MODEL": "opus"})
        self.assertIn("**Trusted internal domains**: example.com", doc["autoMode"]["environment"])
        mcp = json.loads(R.pure_content(targets[self.h(".claude.json")]))
        self.assertEqual(mcp["mcpServers"]["alpha"]["type"], "stdio")
        gem = json.loads(R.pure_content(targets[self.h(".gemini", "settings.json")]))
        self.assertEqual(gem["hooks"]["BeforeTool"][0]["matcher"], "run_shell_command")
        self.assertTrue(gem["hooks"]["BeforeTool"][0]["hooks"][0]["command"].startswith("HARNESS_ASK_AS=deny bash "))
        cop = json.loads(targets[self.h(".copilot", "hooks", "harness.json")].content)
        self.assertEqual(cop["hooks"]["preToolUse"][0]["timeoutSec"], 10)
        self.assertEqual(cop["version"], 1)
        codex = toml_compat.loads(R.pure_content(targets[self.h(".codex", "config.toml")]).decode())
        self.assertEqual(codex["skills"][0]["path"], self.h(".codex", "skills", "demo"))
        self.assertIn("alpha", codex["mcp_servers"])
        self.assertIn(self.h(".agents", "skills", "demo", "SKILL.md"), targets)
        agents_md = R.pure_content(targets[self.h(".config", "opencode", "AGENTS.md")]).decode()
        self.assertIn("## Agent: planner", agents_md)
        # skill fragment overlaid, templated markdown, verbatim script
        self.assertEqual(targets[self.h(".claude", "skills", "demo", "references", "alpha.md")].content.decode(),
                         "# Alpha notes for the demo skill\n\nAlpha host is alpha.example.com.\n")
        script = targets[self.h(".claude", "skills", "demo", "scripts", "demo.sh")]
        self.assertIn(b"{{ core.ticket_example }}", script.content)
        self.assertTrue(script.executable)
        # bin links
        link = targets[self.h(".local", "bin", "demo")]
        self.assertEqual(link.link, self.h(".claude", "skills", "demo", "scripts", "demo.sh"))

    def test_missing_template_key_is_a_plan_error(self):
        self.write(os.path.join(self.bundles, "core", "rules", "10-core.md"), "{{ core.nope }}\n")
        hub = self.hub()
        with self.assertRaises(R.RenderError) as cm:
            R.Renderer(hub).render(hub.filter_providers(["claude"]))
        self.assertIn("core/rules/10-core.md: {{ core.nope }} has no value", str(cm.exception))

    def test_mcp_when_gate(self):
        os.environ["HARNESS_ALPHA_MCP_ENABLED"] = "0"
        try:
            hub = self.hub()
            paths = [t.path for t in R.Renderer(hub).render(hub.filter_providers(["claude"]))]
            self.assertNotIn(self.h(".claude.json"), paths)
        finally:
            del os.environ["HARNESS_ALPHA_MCP_ENABLED"]

    def test_permissions_dedupe_and_precedence(self):
        self.write(os.path.join(self.bundles, "alpha", "permissions.toml"),
                   '[permissions]\nallow = ["Bash(demo write:*)", "Bash(jq:*)"]\n')
        self.write(os.path.join(self.bundles, "alpha", "bundle.toml"),
                   self.read(os.path.join(self.bundles, "alpha", "bundle.toml")).replace(
                       'mcp = "mcp.toml"', 'mcp = "mcp.toml"\npermissions = "permissions.toml"'))
        hub = self.hub()
        t = [t for t in R.Renderer(hub).render(hub.filter_providers(["claude"])) if t.path.endswith("settings.json")][0]
        perms = t.fragment["permissions"]
        self.assertEqual(perms["allow"], ["Bash(demo status:*)", "Bash(jq:*)"])
        self.assertEqual(perms["ask"], ["Bash(demo write:*)"])  # ask beats allow


if __name__ == "__main__":
    unittest.main()
