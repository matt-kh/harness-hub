## Ticket workflow
- `/work-ticket KEY` (or `#N` for GitHub Issues) owns the ticket → MR/PR flow: label gate
  (`{{ core.agent_labels.worked }}`), `<short-name>` branches without ticket keys, only the checks
  CI lacks, MRs/PRs that mention the key and never close it. It yields to a repository-level
  ticket workflow (declared in `.harness.toml` or found at preflight) after its read-only
  preflight (principle 8).
- The guard asks on branch names and commit subjects that carry a ticket key; a repository whose
  convention puts keys there sets `WORK_TICKET_KEY_IN_BRANCH = "1"` in `.harness.toml`
  `[overrides]` (a provider `env` override of the same name also works).
- `/create-ticket <text>` drafts ONE ticket or issue with `{{ core.agent_labels.drafted }}`,
  reads it back and stops — it never starts the work.
- Large tickets: the Plan agent (`{{ core.model_policy.plan }}`) decomposes; sub-tickets carry
  `{{ core.agent_labels.created }}` + `{{ core.agent_labels.worked }}`; delivery is stacked MRs/PRs
  that humans merge bottom-up.

A repository's own instructions for the same action replace this block.
