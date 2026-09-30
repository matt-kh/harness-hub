# Type, project and version rules

## Project inference (Step 0) — never a repo ↔ project mapping
1. `--project KEY`, or an explicit key/prefix in the input (`PROJ-…`, `[PROJ]`, "in OPS").
2. Case-insensitive match of a creatable project's key or name against words in the input
   (e.g. "shop", "ops platform"). Candidate list = projects where
   `create-facts.sh` reports `creatable: true`; start from the projects in
   `jira search 'reporter = currentUser() ORDER BY created DESC' 30` (cheap, personal).
3. Otherwise: most frequent creatable project in that search. Share ≥ 60% → default silently
   (marked `(default)` in preview); else → **P1**.
4. No creatable candidate → stop and list projects the token can create in.

Which projects the token can create in is org knowledge (see the org notes, if any) — always
re-check via facts; permissions change.

## Class detection (Step 1) → keywords in the input
| class | keywords / signals |
|---|---|
| defect | bug, broken, crash, error, fails, wrong, regression, "doesn't/does not work", "should … but", steps/expected/actual present |
| enhancement | add, support, allow, improve, new, feature, option, ability, template, expose |
| chore | refactor, cleanup, docs, upgrade, bump, investigate, spike, migrate, CI, test coverage |
| epic | epic, initiative, umbrella, roadmap, "several tickets", phases |
| swtask | user says "SW Task" explicitly, or project offers SW Task and nothing else fits |
Conflict (defect + enhancement words) or none → **P2**.

## Class → type resolution (against `create-facts.sh` types)
| class | preferred type (in order, first available) | required extras |
|---|---|---|
| defect | `Bug` → `Task` (org rules may prefer another defect type — see below) | Affects Version → **P5** if unreleased versions exist |
| enhancement | `Story` → `New Feature` → `Improvement` → `Task` | — |
| chore | `Task` | — |
| epic | `Epic` (+ Epic Name, **P2d**) | — |
| swtask | a type the user names explicitly (+ Category **P2c** where required) | body goes to Problem Description when the type has no description field |
Never invent a type — if none of the preferred types exists in the project, ask **P2** with the
project's actual types as options.

**Org rules.** `jira.issue_types` in the harness config (rendered to `build/config.json`) is the
machine-checked part: `render-ticket.py --check` rejects a type marked `standalone = false`
(sub-task types), a model missing a `requires` key, and any custom field whose id is unknown
(ids come from facts or `jira.fields`, never guessed). Org-specific type *preferences* (e.g.
a change-request type with a Type-of-Problem field in place of `Bug`) live in the org notes and
override the generic preference order above.

## Version rules
- Defect: Affects Version asked (P5) when the project has unreleased versions; "found in X"
  in the input fills it silently.
- Enhancement / chore: Fix Version only when the input hints a release ("for 1.12", "next
  release", "hotfix"); otherwise blank — humans set it in planning.
- Only unreleased, junk-filtered versions from facts are offered; the newest first.

## Priority / assignee / components
- Priority: Medium unless urgency words → **P6**; an exact priority name in the input is used as-is.
- Assignee: me unless the input names someone / says unassigned → resolve via
  `jira api "/rest/api/2/user/search?username=<q>"`; ambiguous → **P7**.
- Components: only exact existing names; one exact match → set silently; else **P8** or none.

## Content placement
- Body → `description`. Where the org rules echo the problem into a Problem Description
  field, set `problem_description_echo` (the id comes from facts / `jira.fields`). A type without
  a description field → body in Problem Description only.
- Design / Epic Link / Sprint fields are **not** set by this skill (Sprint needs a board).
  Humans add them later.
- Provenance: `labels` always starts with `{{ core.agent_labels.drafted }}`; footer line is fixed.

## GitHub Issues (provider = github; `create-facts.sh owner/repo`)
Project = `owner/repo` (argument, else the cwd's github.com remote). No types, versions,
components or priorities — only labels, assignee, milestone. Render with `--provider github`.
| class | label (only if present in facts `labels`) | body |
|---|---|---|
| defect | `bug` | steps (numbered) / Actual / Expected / region / environment / evidence |
| enhancement | `enhancement` | Context / Goal / Proposed change / `- [ ]` acceptance / out of scope |
| chore | none | as enhancement |
| epic | none | Goal / `- [ ]` scope / `- [ ]` child-work checklist (no native sub-issues here) |
| swtask | — | Jira-only; map to chore |
- The renderer adds the class label itself when the repo has it; extra labels only if they
  exist in facts (never invent). Milestone only an exact open title from facts (Q: "for v0.3").
- Assignee: `@me` when facts `can_assign` (viewer ≥ WRITE), else unassigned. No priority.
- `agent-drafted` missing in facts `labels` → the one pre-create write, promptless by the
  agent-* label rule: `gh label create agent-drafted -R owner/repo -c 5319e7 -d "Drafted by an agent (create-ticket)"`,
  then re-run `create-facts.sh`. Viewer < WRITE (fork/upstream) cannot label → stop and
  tell the user to file it themselves (the hook denies an unlabelled `gh issue create`).
- Related issues are mentioned as `#N` / `owner/repo#N` — never after close/fix/resolve words.
- Attachments: `gh` cannot upload; list paths in the report for the user to drag into the web UI.
- A repo issue template (facts `templates`) → borrow its section headings, nothing else.
