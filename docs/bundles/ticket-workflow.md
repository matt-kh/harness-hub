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
<!-- generated:end -->
