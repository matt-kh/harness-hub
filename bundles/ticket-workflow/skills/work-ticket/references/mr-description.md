# Templates — triage comment, MR description, handoff comment

## Triage comment (Jira, plain text; `*bold*` is Jira wiki markup — never ADF)

```
[agent-triage] 2026-09-02 jdoe via Claude Code (work-ticket)
*Verified:* yes — <1–2 lines with path:line evidence> | partial — <what is missing> | no
*Classification:* <Bug|Enhancement|Task|Chore> / severity <low|med|high> / scope <S|M|L> / feasibility <ok|risky — why>
*Affected areas:* <group/repo> — <module or paths>
*Plan:*
1. <task>
2. <task>
3. <task>
*Open questions:* <numbered, or "none">
*Repo/branch:* <group/repo> <default-branch> -> <short-name>
```

## MR title

`KEY ` + the repo's observed style. Check the last ~10 merged MR titles
(`glab mr list --merged -P 10`): if they use `type(scope): summary`, produce
`KEY type(scope): summary`; otherwise `KEY Sentence summary`. Never a closing keyword.
GitHub: `gh pr list -R owner/repo --state merged -L 10 --json title`, repo style **without**
`#N`; PR body, `## Stack` (`#N` numbers), sub-PR header and handoff templates → `github.md` §6/§7.

## MR description

If `preflight.mr_template` is set, use that file's headings and fill them (many repos open
with `## JIRA Ticket`). Otherwise use this skeleton (common headings):

```markdown
## JIRA Ticket
[KEY](JIRA_URL/browse/KEY)      <!-- JIRA_URL = jira.url; `jira get KEY` prints the full `url` -->

## Why is this MR created
<problem, from the ticket + verification evidence>

## What does this MR do
<approach; behaviour-level, not a file list>
```

Always append these sections (template or not):

```markdown
## Task list
- [x] <task 1>
- [x] <task 2>
- [ ] <task 3 — only if the MR is a Draft>

## Checks
| check | in MR pipeline? | ran locally? | result |
|---|---|---|---|
| pre-commit | yes | no (CI runs it) | — |
| unit tests | no | no — not defined for this repo | — |

## CI recommendations
<ONLY when a gap exists — otherwise omit the section entirely.>
This repository has no merge-request pipeline (`.gitlab-ci.yml` defines no
`merge_request_event` rule), so the checks above ran **once locally before push** and are
not enforced by CI. Recommended follow-up, **not implemented in this MR** (separate MR on
request): add a `workflow: rules` entry for `$CI_PIPELINE_SOURCE == "merge_request_event"`
and a `lint` job running pre-commit; a repo's `.gitlab-ci.yml` (`pre-commit` job,
stage `lint`) is a working in-house pattern.

<Stacked delivery, `ci.per_branch_heavy == true`:>
Every branch push runs `<per_branch_heavy_jobs>` (legacy `only/except`, no
`merge_request_event`), so each part of this stack costs a full build/deploy. Recommended,
**not implemented here**: add `except: - /-sub-\d+-/` to those jobs, or migrate them to
`rules:` gated on `$CI_PIPELINE_SOURCE == "merge_request_event" && $CI_MERGE_REQUEST_TARGET_BRANCH_NAME == $CI_DEFAULT_BRANCH`.

<Stacked delivery, `ci.mr_heavy_jobs` non-empty:>
MR pipelines run `<mr_heavy_jobs>` for every MR regardless of target. Recommended, **not
implemented here**: add `- if: $CI_PIPELINE_SOURCE == "merge_request_event" && $CI_MERGE_REQUEST_TARGET_BRANCH_NAME != $CI_DEFAULT_BRANCH`
→ `when: never` to the heavy jobs so sub MRs targeting a ticket branch run only the checks.

## Sub-tickets
<ONLY for SINGLE delivery with sub-tickets — otherwise omit. Stacked delivery uses `## Stack` instead.>
| ticket | scope | status | sub-branch (local, squashed) |
|---|---|---|---|
| [PROJ-1301](JIRA_URL/browse/PROJ-1301) | schema | In Progress | docker-networks-sub-01-schema (2 commits) |

## Stack
<ONLY for STACKED delivery (main MR). Regenerated on every sync; IIDs filled in the second pass.>
Stacked delivery: review the **parts** below; treat this MR as the **integration view** (its
diff is the union of all parts — do not re-review it line by line). Merge **bottom-up in the
GitLab UI**: parts into `docker-networks` (Developer), then this MR (Maintainer). Nothing here
is merged by the agent.

| # | MR | sub-ticket | source → target | merge after | status |
|---|---|---|---|---|---|
| 1 | !12 | [PROJ-1301](JIRA_URL/browse/PROJ-1301) | `docker-networks-sub-01-schema` → `docker-networks` | — | Ready |
| 2 | !13 | [PROJ-1302](JIRA_URL/browse/PROJ-1302) | `docker-networks-sub-02-api` → `docker-networks` | — | Ready |
| 3 | !14 | [PROJ-1303](JIRA_URL/browse/PROJ-1303) | `docker-networks-sub-03-ui` → `docker-networks-sub-02-api` | !13, then agent retargets to `docker-networks` | Draft |
| — | !11 (this) | [KEY](JIRA_URL/browse/KEY) | `docker-networks` → `master` | all parts | Draft |

(No Jira sub-tickets → the sub-ticket column reads `part N`.)

## Agent notes
- Jira: labelled `agent-worked`; ticket status unchanged (human-operated).
- Sub-tickets: <N> created (`agent-created`, Issue split from KEY); planned by {{ core.model_policy.plan }} (Plan agent); mode: <subagents|ultracode|single> — or "none".
- Sub-branch commits squashed into this branch: <n> (or "none" / "n/a — stacked delivery").
- Delivery: <single | stacked — M parts, see `## Stack`>.
- Related (mention only, not linked): <KEY-2>, <KEY-3> — or "none".
- Harness: repo-level `CLAUDE.md` / `.claude/` updated in this MR: <paths — why> — or "none".
```

Mentioning child keys here makes the GitLab↔Jira integration post the MR link on each child
automatically — no per-child Jira comments needed.

## Sub MR description (stacked delivery, one per part)

```markdown
> **Stack — part N of M** for [KEY](JIRA_URL/browse/KEY) · main MR !11 · prev !12 · next !14
> **Merge after:** !12 · **Target:** `docker-networks` (never `master`) · tick "Delete source branch" when merging.

## JIRA Ticket
[PROJ-1302](JIRA_URL/browse/PROJ-1302) — split from [KEY](JIRA_URL/browse/KEY)
<no Jira sub-tickets → just the parent link>

## Why is this MR created
<this part's problem slice>

## What does this MR do
<behaviour-level; only this part>

## Task list
- [x] <task>

## Checks
| check | in MR pipeline? | ran locally? | result |
|---|---|---|---|

## Agent notes
- Part of a stacked delivery; main MR !11 carries the full `## Stack` table and merge order.
- Depends on !12 (`docker-networks-sub-01-schema`): retargeted to `docker-networks` by the agent after !12 merges. <or "no dependencies">
```
Title: `KEY [part N/M] <task>` (with Jira sub-tickets, `<task>` = the child's title). Never a
closing keyword. `prev`/`next` follow decomposition order; `!TBD` until the second pass.

Rules: mention the key as a link, never `Closes/Fixes/Resolves/Implements KEY`. After
creation, read the description back and grep for closing keywords (Step 6).

## Handoff comment (Jira)

Single delivery:
```
MR opened: <url> (<branch> -> <default-branch>). Merge is by a maintainer.
CI on MR: <yes — pipeline #<id> | no — checks ran locally once, see MR>.
Ticket status unchanged — move it yourself when appropriate.
Sub-tickets: KEY-a, KEY-b (agent-created; move them with this ticket).   <- only if any
```

Stacked delivery:
```
Stacked MRs opened for KEY: M parts + 1 main. Merge bottom-up in the GitLab UI (the agent never merges):
  1. !12 [part 1/M] <task> -> docker-networks
  2. !13 [part 2/M] <task> -> docker-networks
  3. !14 [part 3/M] <task> -> !13's branch (after !13; the agent retargets it to docker-networks)
  main: !11 <main url> docker-networks -> <base> — Draft until all parts are merged; merge last (Maintainer).
CI on MRs: <yes — M+1 pipelines | no — checks ran locally per part, see each MR>.
Ticket status unchanged — move it yourself when appropriate.
Sub-tickets: KEY-a, KEY-b (agent-created; move them with this ticket).   <- only if any
```
