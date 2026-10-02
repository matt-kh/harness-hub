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

If a repository ships its own ticket workflow skill, `work-ticket` runs only its read-only
preflight and hands over completely ([precedence](../concepts.md#precedence)).

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| "no tracker bundle active" during bootstrap | `any_of` unmet | enable `jira` or `github` |
| Preflight stops at the label gate | the label could not be added or read back (permissions, or a fork you cannot label) | fix permissions; in fork flow the triage goes into the PR body instead |
| The agent asks before every comment on the ticket | the ticket is human-only (no `agent-*` label yet) | expected until the label gate passes; answer once |
| Stacked MR parts have no CI | pipelines/workflows filter on target branch | see the gitlab/github bundle troubleshooting tables |
| Branch names contain the ticket key in one repo | that repo sets `WORK_TICKET_KEY_IN_BRANCH=1` or has its own workflow | expected: repo-level conventions win |
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
- **Stability:** stable

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

### repo-overrides — Know the per-repo opt-outs (read once)

*once per org · needs nothing but a terminal · ~2 min*

**Why:** Repos with their own ticket workflow replace these skills wholesale; a few guard behaviours can be switched off per repo, never globally.

**How:**

In a repo's `.claude/settings.json` → `"env"`:
- `WORK_TICKET_ALLOW_TRANSITION=1` — `jira transition` / `gh issue close|reopen` on a human
  ticket asks instead of denying (repos whose own workflow moves tickets).
- `WORK_TICKET_KEY_IN_BRANCH=1` — the repo puts ticket keys in branch names (declaration only).
- `WORK_TICKET_ALLOW_DEFAULT_PUSH_RE=<regex on the repo top level>` — a default-branch push
  asks instead of denying (personal repos).
A repo-level skill such as `work-jira-ticket` is detected at preflight and takes over.

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
| sensor | doctor | `doctor_checks` | a tracker CLI and an SCM CLI on PATH, both skills rendered |
| sensor | test | `tests/run.sh` | every skill suite of this bundle |
| sensor | test | `skills/create-ticket/scripts/tests/run.sh` | golden renders of every ticket class |

**Not covered:** No permission rules and no guard section of its own: the write gates are sensed by the tracker and SCM bundles' guard sections (closing keywords, labels, stacked targets); work-ticket has no own test suite.

## Uninstall

Kept on uninstall: _nothing_

Removes the two rendered skills and the rule block; tickets, MRs and labels they created are untouched.
<!-- generated:end -->
