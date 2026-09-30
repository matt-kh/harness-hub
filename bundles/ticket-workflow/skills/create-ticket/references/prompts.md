# Prompt catalogue — the only place questions are worded

Rules
- Evaluate triggers in **priority order**. Round 1 = the first ≤ 4 that fire, in ONE
  AskUserQuestion. Everything else takes its default and is shown `(default)` in the preview.
- P2/P2b/P2c/P2d are mutually exclusive (at most one type question).
- Options ≤ 4, default first (mark "(Recommended)"); "Other" is implicit free text.
- Never ask what the input or `create-facts.sh` already answers. If the user's text answers a
  question, don't ask it.
- Overflow (> 4 fired): P6 and below default silently — Medium, me, no components, no prefix,
  keys mentioned verbatim, no uploads.
- Round 2 is always P14 (preview). "Edit a field" loops are user-initiated and don't count.

| pri | id | header | ask only if… | question | options (default first) | → model |
|---|---|---|---|---|---|---|
| 1 | P1 | Project | no explicit key/prefix/project-name match in the input AND (top reporter project share < 60% or it isn't creatable) | Which Jira project should this ticket go in? | `<top>` — your most recent tickets (N of 30) / `<2nd>` / `<3rd>` — creatable projects only | `project`; re-run `create-facts.sh` |
| 2 | P2 | Issue type | class keywords absent or conflicting (defect + enhancement words), or resolved type not in this project | What kind of ticket is this? | **Bug fix** — the org's defect type (`type-rules.md`; generic: `Bug`) / **Enhancement** — Story / New Feature / Improvement / **Task** — chore, refactor, docs, investigation / **Epic** — umbrella for several tickets | `class`, `type`, `type_of_problem` |
| 2b | P2b | Type of Problem | type already fixed by the user to one that carries a problem-kind field (org rules, e.g. a change-request type) but class ambiguous | Is this a bug fix or an enhancement? | **Bug Fix** / Enhancement | `type_of_problem` |
| 2c | P2c | Category | the type requires Category (facts `required`, or a `jira.issue_types` rule) | Which Category for this <TYPE>? | createmeta `allowed` values (first 4) | `category` |
| 2d | P2d | Epic name | type = Epic and no short name inferable | Short Epic Name (shown on the board, ≤ 30 chars)? | `<summary trimmed to 30>` / free text | `epic_name` |
| 3 | P3 | Problem | `problem` empty or < 15 chars, or the input is only a solution ("add a button") | What is the problem or need this addresses — what happens today, who is affected? | free text / **Skip — I only have the solution** / **Use my input verbatim as the problem** | `problem`, `motivation` |
| 4a | P4a | Repro steps | class = defect and `steps` empty | How do you reproduce it, and what did you expect vs. see? (paste steps; I'll format them) | **Paste steps now** / **No steps yet — mark "to be captured"** / **It's intermittent — describe conditions** | `steps[]`, `actual`, `expected` (one step per line; "Expected:"/"Actual:" lines picked up) |
| 4b | P4b | Acceptance | class ∈ {enhancement, chore} and `acceptance` empty | How will we know this is done? Give 1–5 acceptance criteria or testable outcomes. | **Derive from my description** — I draft 2–3, you edit in preview / **Paste criteria** / **Not needed — small task** | `acceptance[]` ("Not needed" → section omitted) |
| 4c | P4c | Scope | class = epic, or input > 600 chars or ≥ 4 distinct asks | This looks broad. One ticket covering all of it, or should I note the boundary? | **One ticket, list everything in scope** / **One ticket + "Out of scope" section** (I propose the split) / **Only the first item** | `out_of_scope[]`, trims `acceptance` |
| 5 | P5 | Version | project has unreleased versions AND (class = defect with `affects_versions` empty, or input hints a release: "for 1.12", "next release", "hotfix") | (defect) Which version was this found in? · (other) Which release should this target? | `<latest unreleased>` / `<next>` / `<third>` / **None — leave blank** (defect: **Unknown — leave blank**) | defect → `affects_versions`; hint → `fix_versions` (both parts in one question when both apply) |
| 6 | P6 | Priority | urgency words present (urgent, blocker, ASAP, prod down, customer waiting; minor, nice-to-have, low) but no exact priority name | How urgent is this? | **Medium** / High / Critical / Blocker (Low variant when the words were minor / nice-to-have) | `priority` (no signal → Medium silently) |
| 7 | P7 | Assignee | input names a person or says "unassigned"/"for the team", and the name doesn't resolve via `jira api "/rest/api/2/user/search?username=<q>"` | Who should it be assigned to? | **Me (`<me>`)** / **Unassigned** / `<best user match>` | `assignee` (`{"name"}`); no signal → me |
| 8 | P8 | Component | project has real components AND input mentions ≥ 2 areas, or one area with no exact match | Which component(s)? (existing ones only) | up to 4 best matches / **None** | `components[]` (exact single match → set silently; none → empty) |
| 9 | P9 | Program | input mentions a customer/program token (`[XXX]`, "for ACME") not already bracketed | Prefix the summary with a program tag? | **`[TOKEN]`** / **No prefix** | `program` |
| 10 | P10 | Related | input mentions ticket keys, or "related to / duplicate of / follow-up to" without keys | Mention related tickets in the description? | **Mention `<keys>` under Related** / **No** (free text for keys) | `related[]` — mention only; this skill never creates native links |
| 11 | P11 | Evidence | class = defect and no URL / attachment / log excerpt in the input | Any evidence to reference (screenshot, video link, log excerpt)? | **None yet** / **Paste a link** / **Upload files after creation** (paths) | `evidence[]`, `attachments[]` |
| 12 | P12 | Attachments | input contains local file paths that exist (`test -f`) | Upload these N file(s) to the ticket after creation? (each upload is a separate confirmation) | **Yes, upload all** / **No — mention paths only** / **Pick a subset** | `attachments[]` |
| — | P13 | Summary | never asked in Round 1; edited via P14 | — | — | `summary` |
| — | P14 | Preview | always (Round 2) | Create this ticket in `<PROJECT>` as `<TYPE>`? (full preview shown above) | **Create** / **Edit a field** (then: summary, type, a description section, version, priority, assignee, component) / **Cancel — nothing written** | Step 5 / re-render + re-preview / stop |

Wording rules: one question per checkpoint; headers ≤ 12 chars; options carry their
consequence in the description (e.g. "Bug + Affects Version = 1.12"); never ask about ticket
state — new tickets start in `Open` and stay there until a human moves them.
