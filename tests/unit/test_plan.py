"""plan/apply idempotence, foreign files, drift, adopt, orphans, state, sync, uninstall."""
from __future__ import annotations

import json
import os
import types
import unittest

from helpers import HubTestCase  # noqa: E402

from harness import state as S
from harness import sync as SY


def actions(plan):
    return {it.path: it.action for it in plan.items}


class PlanApplyTest(HubTestCase):
    def test_first_apply_then_zero_changes(self):
        plan = self.apply()
        self.assertGreater(plan.changes, 30)
        self.assertEqual(plan.counts()["conflict"], 0)
        _hub, again = self.plan()
        self.assertEqual(again.changes, 0, [(i.path, i.action, i.reason) for i in again.items if i.write])
        self.assertTrue(again.summary().startswith("Plan: 0 changes"))
        self.assertTrue(os.access(self.h(".claude", "hooks", "guard-bash.sh"), os.X_OK))
        self.assertTrue(os.path.islink(self.h(".local", "bin", "demo")))

    def test_state_round_trip(self):
        self.apply(providers=["claude"])
        st = S.load("claude", "~/.claude")
        entry = st.get(self.h(".claude", "CLAUDE.md"))
        self.assertEqual(entry["mode"], "managed-block")
        self.assertEqual(sorted(entry["blocks"]), ["alpha rules/40-alpha.md", "beta rules/05-beta.md", "core rules/10-core.md"])
        self.assertIn("~/.claude/settings.json", st.files)          # ~ form keys
        # sources outside the hub are recorded as absolute paths (inside it: hub-relative)
        self.assertEqual(st.files["~/.claude/skills/demo/SKILL.md"]["source"],
                         os.path.join(self.bundles, "core", "skills", "demo", "SKILL.md"))
        data = json.loads(self.read(st.path))
        self.assertEqual(data["version"], 1)
        self.assertEqual(S.State(st.path, "claude", data).to_json()["files"], data["files"])
        # a no-op apply does not rewrite the state file
        mtime = os.stat(st.path).st_mtime_ns
        self.apply(providers=["claude"])
        self.assertEqual(os.stat(st.path).st_mtime_ns, mtime)

    def test_user_content_preserved_on_first_apply(self):
        self.write(self.h(".claude", "settings.json"), json.dumps({"theme": "dark", "permissions": {"allow": ["Bash(ls:*)"]}}))
        self.write(self.h(".claude", "CLAUDE.md"), "# Mine\n\nprose\n")
        self.write(self.h(".claude.json"), json.dumps({"numStartups": 3, "mcpServers": {"x": {"command": "y"}}}))
        self.apply(providers=["claude"])
        s = json.loads(self.read(self.h(".claude", "settings.json")))
        self.assertEqual(s["theme"], "dark")
        self.assertIn("Bash(ls:*)", s["permissions"]["allow"])
        self.assertIn("Bash(jq:*)", s["permissions"]["allow"])
        self.assertTrue(self.read(self.h(".claude", "CLAUDE.md")).startswith("# Mine\n\nprose\n"))
        cj = json.loads(self.read(self.h(".claude.json")))
        self.assertEqual(cj["numStartups"], 3)
        self.assertEqual(sorted(cj["mcpServers"]), ["alpha", "x"])
        _h, again = self.plan(providers=["claude"])
        self.assertEqual(again.changes, 0)

    def test_foreign_file_is_kept_unless_adopted(self):
        agent = self.h(".claude", "agents", "planner.md")
        self.write(agent, "my own planner\n")
        _h, plan = self.plan(providers=["claude"])
        self.assertEqual(actions(plan)[agent], "conflict")
        self.apply(providers=["claude"])
        self.assertEqual(self.read(agent), "my own planner\n")
        self.apply(providers=["claude"], adopt=[agent])
        self.assertIn("Plan things for you@example.com", self.read(agent))
        backups = os.path.join(self.home, ".local", "state", "harness", "backups")
        found = [os.path.join(d, f) for d, _s, fs in os.walk(backups) for f in fs]
        self.assertTrue(any(p.endswith(os.path.join(".claude", "agents", "planner.md")) for p in found))

    def test_foreign_skill_dir_is_a_unit(self):
        self.write(self.h(".claude", "skills", "demo", "SKILL.md"), "someone else's skill\n")
        _h, plan = self.plan(providers=["claude"])
        a = actions(plan)
        self.assertEqual(a[self.h(".claude", "skills", "demo", "SKILL.md")], "conflict")
        self.assertEqual(a[self.h(".claude", "skills", "demo", "scripts", "demo.sh")], "conflict")
        _h, plan = self.plan(providers=["claude"], adopt=[self.h(".claude", "skills", "demo")])
        self.assertEqual(actions(plan)[self.h(".claude", "skills", "demo", "scripts", "demo.sh")], "create")

    def test_identical_foreign_file_is_taken_into_state(self):
        from harness import render as R

        hub = self.hub()
        t = [t for t in R.Renderer(hub).render(hub.filter_providers(["claude"])) if t.path.endswith("planner.md")][0]
        os.makedirs(os.path.dirname(t.path), exist_ok=True)
        with open(t.path, "wb") as fh:
            fh.write(t.content)
        _h, plan = self.plan(providers=["claude"])
        self.assertEqual(actions(plan)[t.path], "skip")

    def test_hand_edit_is_a_conflict_and_adopt_overrides(self):
        self.apply(providers=["claude"])
        agent = self.h(".claude", "agents", "planner.md")
        self.write(agent, "edited\n")
        # source change + live edit -> conflict, user wins
        src = os.path.join(self.bundles, "core", "agents", "planner.md")
        self.write(src, self.read(src) + "More.\n")
        _h, plan = self.plan(providers=["claude"])
        self.assertEqual(actions(plan)[agent], "conflict")
        self.apply(providers=["claude"])
        self.assertEqual(self.read(agent), "edited\n")
        self.apply(providers=["claude"], adopt=[agent])
        self.assertIn("More.", self.read(agent))

    def test_source_update_is_an_update(self):
        self.apply(providers=["claude"])
        src = os.path.join(self.bundles, "core", "rules", "10-core.md")
        self.write(src, self.read(src) + "- new line\n")
        _h, plan = self.plan(providers=["claude"])
        self.assertEqual(actions(plan)[self.h(".claude", "CLAUDE.md")], "update")
        self.assertIn("+- new line", plan.items[[i.path for i in plan.items].index(self.h(".claude", "CLAUDE.md"))].diff())

    def test_orphans_removed_when_bundle_deactivated(self):
        self.apply(providers=["claude"])
        guard = self.h(".claude", "hooks", "guard-bash.sh")
        self.assertIn("section 40-alpha.sh", self.read(guard))
        self.write(self.cfg, self.read(self.cfg).replace('bundles = ["core", "alpha", "beta"]', 'bundles = ["core"]'))
        _h, plan = self.plan(providers=["claude"])
        a = actions(plan)
        self.assertEqual(a[self.h(".claude", "skills", "demo", "references", "alpha.md")], "orphan")
        self.apply(providers=["claude"])
        self.assertFalse(os.path.exists(self.h(".claude", "skills", "demo", "references", "alpha.md")))
        self.assertNotIn("section 40-alpha.sh", self.read(guard))
        self.assertNotIn("alpha", self.read(self.h(".claude", "CLAUDE.md")))
        self.assertFalse(os.path.exists(self.h(".claude.json")))  # we created it; now empty -> removed
        _h, plan = self.plan(providers=["claude"])
        self.assertEqual(plan.changes, 0)

    def test_json_conflict_reported_and_remembered(self):
        self.write(self.h(".claude", "settings.json"), json.dumps({"permissions": {"deny": ["Bash(jq:*)"]}}))
        plan = self.apply(providers=["claude"])
        item = [i for i in plan.items if i.path.endswith(os.path.join(".claude", "settings.json"))][0]
        self.assertEqual(item.action, "conflict")
        self.assertTrue(item.write)  # non-conflicting parts still written
        s = json.loads(self.read(self.h(".claude", "settings.json")))
        self.assertNotIn("Bash(jq:*)", s["permissions"].get("allow", []))
        self.assertIn("hooks", s)
        st = S.load("claude", "~/.claude")
        self.assertTrue(any("Bash(jq:*)" in c for c in st.conflicts))


class SyncTest(HubTestCase):
    def test_classification(self):
        self.apply(providers=["claude"])
        hub = self.hub()
        os.unlink(self.h(".claude", "agents", "planner.md"))
        self.write(self.h(".claude", "skills", "demo", "scripts", "demo.sh"), "#!/bin/sh\necho edited\n")
        rows = {r["path"]: r["status"] for r in SY.classify(hub, hub.filter_providers(["claude"]))}
        self.assertEqual(rows[self.h(".claude", "agents", "planner.md")], "missing")
        self.assertEqual(rows[self.h(".claude", "skills", "demo", "scripts", "demo.sh")], "drifted")
        self.assertEqual(rows[self.h(".claude", "CLAUDE.md")], "clean")

    def test_merged_targets_compare_owned_values_only(self):
        self.apply(providers=["claude", "codex"])
        hub = self.hub()

        def status(*parts):
            rows = {r["path"]: r["status"] for r in SY.classify(hub, hub.filter_providers(["claude", "codex"]))}
            return rows[self.h(*parts)]

        cj = self.h(".claude.json")
        doc = json.loads(self.read(cj))
        doc["numStartups"] = 42                          # the provider rewrites unrelated keys
        self.write(cj, json.dumps(doc, indent=4))
        self.assertEqual(status(".claude.json"), "clean")
        doc["mcpServers"]["alpha"]["command"] = "edited"  # an owned value
        self.write(cj, json.dumps(doc))
        self.assertEqual(status(".claude.json"), "drifted")

        st = self.h(".claude", "settings.json")
        sdoc = json.loads(self.read(st))
        sdoc["theme"] = "light"
        self.write(st, json.dumps(sdoc))
        self.assertEqual(status(".claude", "settings.json"), "clean")
        del sdoc["hooks"]                                 # a rendered value removed
        self.write(st, json.dumps(sdoc))
        self.assertEqual(status(".claude", "settings.json"), "drifted")

        md = self.h(".claude", "CLAUDE.md")
        self.write(md, "# My notes\n\n" + self.read(md))  # text outside the blocks
        self.assertEqual(status(".claude", "CLAUDE.md"), "clean")
        self.write(md, self.read(md).replace("Beta has no config.", "Beta edited."))
        self.assertEqual(status(".claude", "CLAUDE.md"), "drifted")

        ct = self.h(".codex", "config.toml")
        self.write(ct, 'model = "x"\n\n' + self.read(ct))
        self.assertEqual(status(".codex", "config.toml"), "clean")
        self.write(ct, self.read(ct).replace("alpha-mcp", "alpha-edited"))
        self.assertEqual(status(".codex", "config.toml"), "drifted")

    def test_foreign(self):
        self.write(self.h(".claude", "agents", "planner.md"), "x\n")
        hub = self.hub()
        rows = {r["path"]: r["status"] for r in SY.classify(hub, hub.filter_providers(["claude"]))}
        self.assertEqual(rows[self.h(".claude", "agents", "planner.md")], "foreign")

    def test_adopt_untemplated_file_back_into_bundle(self):
        self.apply(providers=["claude"])
        live = self.h(".claude", "skills", "demo", "scripts", "demo.sh")
        self.write(live, "#!/usr/bin/env bash\necho adopted\n")
        hub = self.hub()
        rc = SY.run(hub, hub.filter_providers(["claude"]), adopt=[])
        self.assertEqual(rc, 0)
        self.assertEqual(self.read(os.path.join(self.bundles, "core", "skills", "demo", "scripts", "demo.sh")),
                         "#!/usr/bin/env bash\necho adopted\n")
        _h, plan = self.plan(providers=["claude"])
        self.assertEqual(plan.changes, 0)

    def test_templated_file_is_refused(self):
        self.apply(providers=["claude"])
        live = self.h(".claude", "skills", "demo", "SKILL.md")
        self.write(live, "changed\n")
        hub = self.hub()
        before = self.read(os.path.join(self.bundles, "core", "skills", "demo", "SKILL.md"))
        SY.run(hub, hub.filter_providers(["claude"]), adopt=[live])
        self.assertEqual(self.read(os.path.join(self.bundles, "core", "skills", "demo", "SKILL.md")), before)

    def test_adopt_untemplated_managed_block(self):
        self.apply(providers=["claude"])
        md = self.h(".claude", "CLAUDE.md")
        self.write(md, self.read(md).replace("Beta has no config.", "Beta has no config at all."))
        hub = self.hub()
        SY.run(hub, hub.filter_providers(["claude"]), adopt=[md])
        self.assertIn("at all", self.read(os.path.join(self.bundles, "beta", "rules", "05-beta.md")))
        _h, plan = self.plan(providers=["claude"])
        self.assertEqual(plan.changes, 0, [(i.path, i.action) for i in plan.items if i.write])


class UninstallTest(HubTestCase):
    def test_uninstall_removes_only_ours(self):
        from harness import uninstall as U

        self.write(self.h(".claude", "settings.json"), json.dumps({"theme": "dark"}))
        self.write(self.h(".claude", "CLAUDE.md"), "# Mine\n")
        self.write(self.h(".claude", "projects", "keep.jsonl"), "runtime\n")
        self.apply(providers=["claude"])
        ctx = types.SimpleNamespace(home=None, config=self.cfg, yes=True, dry_run=False)
        ns = types.SimpleNamespace(all=False, provider=["claude"], bundle=None, purge_tools=False)
        self.assertEqual(U.run(ctx, ns), 0)
        self.assertEqual(json.loads(self.read(self.h(".claude", "settings.json"))), {"theme": "dark"})
        self.assertEqual(self.read(self.h(".claude", "CLAUDE.md")), "# Mine\n")
        self.assertEqual(self.read(self.h(".claude", "projects", "keep.jsonl")), "runtime\n")
        self.assertFalse(os.path.exists(self.h(".claude", "hooks", "guard-bash.sh")))
        self.assertFalse(os.path.exists(self.h(".claude", "skills")))
        self.assertFalse(os.path.exists(self.h(".claude.json")))  # created by us, now empty -> removed
        self.assertFalse(os.path.lexists(self.h(".local", "bin", "demo")))
        self.assertFalse(os.path.exists(self.h(".claude", ".harness-state.json")))


if __name__ == "__main__":
    unittest.main()
