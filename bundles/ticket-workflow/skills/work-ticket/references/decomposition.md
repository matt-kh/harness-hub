# Large tickets — {{ core.model_policy.plan }} planning (Step 2b) and governed sub-tickets (Step 3b)

## Step 2b — planning with the Plan agent (latest {{ core.model_policy.plan }})

Trigger: size L or XL (see `enquiries.md`). Call the **`Plan`** subagent (user-level override,
pinned to {{ core.model_policy.plan }}, read-only tools) with:

- full `jira get KEY` JSON (+ parent JSON if any) and attachment summaries;
- verification evidence from Step 1 (`path:line` list) and the preflight JSON;
- the repo-level skill path if `repo_skill` is set;
- constraints: read-only (no jira/glab/gh/git writes); 2–8 sub-tickets, each ≤ ~1 day,
  **file-disjoint**; **each sub-ticket becomes its own MR targeting the ticket branch `<BR>`**
  (stacked delivery, the L/XL default) — keep every part independently reviewable and
  mergeable on its own; `depends_on` **only for true build/runtime dependencies** (a dependent
  part chains onto its blocker's branch and needs a rebase + retarget after the blocker
  merges) and **at most one blocker per part** — needing two means chain linearly or merge the
  parts; no part may target the base branch directly; respect the precedence rule
  (principle 8: when `repo_skill`/`repo_owns` is set, the repository's branch and MR
  conventions apply to every part). (Q8b = single: parts converge into one MR on `<BR>`
  instead — same decomposition.)

Required output — markdown summary **plus** one fenced JSON block, saved verbatim to
`$SCRATCH/KEY-decomposition.json`:

```json
{"sub_tickets":[{"id":"01","title":"...","scope":"...","acceptance":["..."],
                 "paths":["..."],"depends_on":[],"parallel_group":"A","risk":"low|med|high",
                 "delivery_note":"optional, e.g. must merge before 03"}],
 "risks":["..."],"order":["01","02"],"open_questions":["..."],"size_check":"L|XL|actually-M"}
```

`size_check: actually-M` → skip Q7/Q8 and continue as M with the plan as the task list.
The main thread ({{ core.model_policy.execute }}) presents the table (id · title · paths · group · deps · risk), then
asks **Q7, Q8 and Q8b** in one AskUserQuestion call (Q8b default from preflight `ci.*`).

## Step 3b — sub-tickets (only after the label gate, only if Q7 = create)

```bash
bash ~/.claude/skills/work-ticket/scripts/jira-facts.sh KEY   # perms, types, link_type, parent fields
```
`sub_tickets_available=false` → say why (no create/link permission in this project, or no
link type) and continue with the task list only.
GitHub: `issue-facts.sh N` instead; sub-issues via `gh issue create -l agent-created,agent-worked`
+ `gh issue edit N --add-sub-issue <child>`, Markdown body, no In-Progress state (`github.md` §3b).

Per sub-ticket:
- **Type**: `preferred_type` from jira-facts (parent's type if allowed, else `Task`). Use
  a special type only when the parent has that type (copy its required fields, ids from
  `jira fields <PROJECT>` / `jira.fields`). Never a sub-task type, `Epic`, or a type the org
  rules (`jira.issue_types`) mark `standalone = false`.
- **Summary**: `[KEY] <imperative task title>` (≤ 80 chars).
- **Description** (plain text):
  ```
  Split from KEY by Claude Code (work-ticket) on <date> for <user>.
  *Scope:* <what this piece delivers>
  *Acceptance criteria:*
  1. ...
  *Files/modules:* <paths>
  *Depends on:* <sibling keys or none>
  *Delivery:* (stacked) own MR "KEY [part N/M] <title>" -> branch <BR>; merged bottom-up by humans; parent MR <BR> -> <BASE>.
             (single)  converges into KEY's MR on branch <BR>; no separate MR.
  ```
- **Labels**: `["agent-created","agent-worked"]` **in the create call** (the hook denies
  `--link` creates without both). **Assignee**: `{"name":"<me>"}` from jira-facts.
- Copy from the parent when present: sprint (`--field customfield_21204=<id>`), `fixVersions`,
  `components`, `priority`; Epic parent → `--field customfield_21206=KEY`.
- **Link**: `--link "<link_type>:KEY"` (Issue split → parent "split to" child).

Batch every create into **one Bash call** (hook: allow — every create carries both labels), literal keys:

```bash
jira create PROJ Task "[PROJ-1280] Add network template schema" \
  --description "$(cat $SCRATCH/PROJ-1280-sub-01.txt)" \
  --field labels='["agent-created","agent-worked"]' --field assignee='{"name":"jdoe"}' \
  --link "Issue split:PROJ-1280"
jira create PROJ Task "[PROJ-1280] ..." ... --link "Issue split:PROJ-1280"
jira links PROJ-1280                       # read-back: one "split to <CHILD>" per sub-ticket
jira get <CHILD> | jq -c .labels             # both labels; if missing → jira label <CHILD> add ... first
```

Hard sibling dependencies only: `jira link <BLOCKER> Blocks <BLOCKED>` (hook: allow — both agent-worked).
Preview payloads without sending: `JIRA_DRY_RUN=1` (the hook still applies).

## Sub-ticket state (user decision)

- Parent stays untouched — always.
- Agent-created sub-tickets may move to the project's **In-Progress equivalent only**, when
  their work starts: `jira transitions <CHILD>` → one batched
  `jira transition <CHILD-1> "<name>" && jira transition <CHILD-2> "<name>"` (hook: allow —
  every key carries an agent-* label). No In-Progress state → skip silently.
- Never Testing/Done/Closed states — the MR is not merged; humans move parent and children
  together. Closing keywords stay forbidden everywhere.

## Reporting
- MR: stacked → `## Stack` table in the main MR (absorbs the sub-ticket column); single →
  `## Sub-tickets` table (see `mr-description.md`).
- Parent handoff comment appends: `Sub-tickets: KEY-a, KEY-b (agent-created; move them with this ticket).`
- No per-child comments — mentioning child keys in the MR makes the GitLab integration post
  the MR link on each child automatically. (GitHub: a `#N` mention in the PR adds the
  cross-reference to each child's timeline.)
