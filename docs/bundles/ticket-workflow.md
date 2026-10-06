# Bundle: ticket-workflow

Two skills that turn a ticket into reviewed work, with the governance of the tracker and SCM
bundles you enabled:

- **`work-ticket`** — "work on PROJ-123" / "#12": reads and verifies the ticket against the
  code, triages and sizes it, labels it `agent-worked` (the label gate), implements on a
  branch named after a short description (no ticket key), runs the checks CI lacks, and opens
  **one MR/PR** that mentions the ticket. Large tickets are decomposed by the Plan agent into
  parts delivered as **stacked MRs/PRs** (one per part, targeting the ticket branch, plus the
  main one); humans merge bottom-up. It never merges, never transitions or closes the ticket.
- **`create-ticket`** — drafts one ticket or issue from free text, asks only for the gaps,
  renders the description deterministically, creates it with the `agent-drafted` label, reads
  it back and stops.

Needs **one tracker** (`jira` or `github`) and **one SCM** (`gitlab` or `github`); the bundle
refuses to resolve otherwise (`any_of`). Provider-specific commands come in as skill
fragments from those bundles.

If a repository owns the ticket workflow (`.harness.toml` or its own skill), `work-ticket`
runs only its read-only preflight and hands over completely
([repository-level harnesses](../repo-level.md)).

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| "no tracker bundle active" during bootstrap | `any_of` unmet | enable `jira` or `github` |
| Preflight stops at the label gate | the label could not be added or read back (permissions, or a fork you cannot label) | fix permissions; in fork flow the triage goes into the PR body instead |
| The agent asks before every comment on the ticket | the ticket is human-only (no `agent-*` label yet) | expected until the label gate passes; answer once |
| Stacked MR parts have no CI | pipelines/workflows filter on target branch | see the gitlab/github bundle troubleshooting tables |
| Branch names contain the ticket key in one repo | that repo declares `WORK_TICKET_KEY_IN_BRANCH` or owns `delivery` | expected: repository-level conventions win |
| Draft PRs unavailable | private repo on GitHub Free | the skill uses a `[WIP]` title plus the `agent-wip` label |

<!-- generated:begin source=bundles/ticket-workflow/bundle.toml -->
## Summary

/work-ticket (ticket → governed MR/PR, stacked delivery) and /create-ticket (one drafted ticket or issue)

Two skills on top of a tracker bundle and an SCM bundle. `/work-ticket KEY|#N` verifies the
ticket against the code, sizes it, gates every tracker write behind the agent-worked label,
implements on key-free branches (subagents in local worktrees), runs only the checks CI lacks
and opens MRs/PRs that mention the key without closing it; large tickets are planned by the
Plan agent and delivered as stacked MRs/PRs. `/create-ticket <text>` renders ONE ticket or
GitHub issue deterministically (render-ticket.py), creates it with the agent-drafted label,
reads it back and stops. Works with Jira + GitLab, Jira + GitHub, or GitHub alone; the skills
check the CLI they need at preflight and name the missing bundle instead of improvising.
Org-specific issue-type rules and field ids come from jira.issue_types / jira.fields.

- **Depends on:** `core`
- **Recommends:** `jira`, `gitlab`, `github`
- **Needs one of:** `jira`, `github`
- **Needs one of:** `gitlab`, `github`
- **Stability:** beta
- **Domain / posture:** delivery / label-gated

## Components

Stable ids derived from the path, with their [taxonomy](../reference/taxonomy.md) facets (domain shown only where it differs from the bundle's). All bundles: [catalog](../catalog.md).

**Skills**

- `ticket-workflow/skills/create-ticket` — control: guide · function: workflow · posture: label-gated · model: execute · yields: declaration
- `ticket-workflow/skills/work-ticket` — control: guide · function: workflow · posture: label-gated · model: execute · yields: declaration

**Rules**

- `ticket-workflow/rules/75-ticket-workflow` — control: guide · function: govern · yields: text

**Guard sections**

- `ticket-workflow/guard.d/75-ticket-workflow` — control: sensor · function: govern · decisions: ask 4 · yields: declaration

**Permission lists**

- `ticket-workflow/permissions` — function: govern · decisions: empty (no rules) · yields: config

**Doctor checks** (function: setup · posture: read-only; table below): `ticket-workflow/doctor/ticket-workflow-scm`, `ticket-workflow/doctor/ticket-workflow-skills`, `ticket-workflow/doctor/ticket-workflow-tracker`

**Manual steps** (function: setup; table below): `ticket-workflow/steps/repo-overrides`

## Requirements

### Binaries

| binary | min version | install | optional | why |
|---|---|---|---|---|
| `git` | 2.30 |  | no | Worktrees for subagents, branch facts, stacked delivery. |
| `jq` | 1.6 |  | no | Every preflight / facts script emits JSON through jq. |
| `python3` | 3.9 |  | no | render-ticket.py and the preflight helpers. |

### Configuration

_none_

### Secrets (never in harness.toml)

_none_

## Manual steps

<a id="repo-overrides"></a>

### repo-overrides — Know how a repository yields and overrides (read once)

*once per org · needs nothing but a terminal · ~2 min*

**Why:** The hub is a user-level baseline (principle 8): a repository that owns its ticket workflow replaces these skills wholesale, and a few guard behaviours can be switched per repository, never globally.

**How:**

In the repository's `.harness.toml` (provider-neutral, committed; `harness repo` shows the effect):
- `[owns] domains = ["delivery"]` — this repository runs its own ticket → MR/PR workflow;
  `/work-ticket` and `/create-ticket` stop after their read-only preflight and hand over.
- `[overrides] WORK_TICKET_ALLOW_TRANSITION = "1"` — a transition / close / reopen on a
  human ticket asks instead of denying.
- `[overrides] WORK_TICKET_KEY_IN_BRANCH = "1"` — the repository puts ticket keys in branch
  names and commit subjects: the guard lets key-named branches and key-prefixed subjects
  pass instead of asking.
- `[overrides] WORK_TICKET_ALLOW_DEFAULT_PUSH_RE = "<regex>"` — a default-branch push asks
  instead of denying (personal repositories).
A provider `env` override (Claude Code: `.claude/settings.json` → `"env"`) of the same name
wins per key. A repository workflow skill is also detected at preflight by its description.
Full list and the credential exemption: docs/repo-level.md.

**Verify:** `true` (exit 0)

## Doctor checks

| id | severity | offline | fix |
|---|---|---|---|
| `ticket-workflow-tracker` | fail | runs | `Activate the jira or github bundle (hub.bundles) and run harness apply` |
| `ticket-workflow-scm` | fail | runs | `Activate the gitlab or github bundle (hub.bundles) and run harness apply` |
| `ticket-workflow-skills` | fail | runs | `harness apply --provider claude` |

## Guides and sensors

Guides steer the agent before it acts; sensors detect at or after the action. Pairing: **paired**.

| side | kind | ref | note |
|---|---|---|---|
| guide | rule | `rules/75-ticket-workflow.md` | ticket to MR/PR flow, label gate, key-free branches, stacked delivery |
| guide | skill | `skills/work-ticket` | the governed ticket workflow and its preflight scripts |
| guide | skill | `skills/create-ticket` | one drafted ticket or issue, rendered deterministically |
| sensor | guard | `guard.d/75-ticket-workflow.sh` | key-free branches and subjects, sub worktree paths, squash delivery |
| sensor | doctor | `doctor_checks` | a tracker CLI and an SCM CLI on PATH, both skills rendered |
| sensor | test | `tests/run.sh` | this bundle's guard rows against core + ticket-workflow only, then every skill suite |
| sensor | test | `guard.d/tests.sh` | rows for section 75 incl. bypasses |
| sensor | test | `skills/create-ticket/scripts/tests/run.sh` | golden renders of every ticket class |

**Not covered:** The size rubric, Q-checklist and MR body content are judgement calls (inferential: code-reviewer); SCM verb conventions are sensed by the gitlab/github guard sections; work-ticket has no own test suite yet.

## Uninstall

Kept on uninstall: _nothing_

Removes the two rendered skills and the rule block; tickets, MRs and labels they created are untouched.
<!-- generated:end -->
