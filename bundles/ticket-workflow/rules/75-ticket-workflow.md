## Ticket workflow
- `/work-ticket KEY` (or `#N` for GitHub Issues) owns the ticket → MR/PR flow: label gate
  (`{{ core.agent_labels.worked }}`), `<short-name>` branches without ticket keys, only the checks
  CI lacks, MRs/PRs that mention the key and never close it. It defers to a repo-level
  workflow skill after its read-only preflight.
- `/create-ticket <text>` drafts ONE ticket or issue with `{{ core.agent_labels.drafted }}`,
  reads it back and stops — it never starts the work.
- Large tickets: the Plan agent (`{{ core.model_policy.plan }}`) decomposes; sub-tickets carry
  `{{ core.agent_labels.created }}` + `{{ core.agent_labels.worked }}`; delivery is stacked MRs/PRs
  that humans merge bottom-up.
