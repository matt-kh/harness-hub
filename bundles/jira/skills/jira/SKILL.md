---
name: jira
description: Interact with the org's self-hosted Jira Server ({{ jira.url }}) — read/search/update tickets, sprints, versions, transitions, attachments, comments. Use when the user mentions a Jira ticket key (e.g. {{ core.ticket_example }}), pastes a {{ jira.url }} link, or talks about tickets, issues, sprints, epics, or transitions.
model: {{ core.model_policy.execute }}
---

# Jira (self-hosted Server 8.x)

Generic client for `{{ jira.url }}`. **Precedence:** if the current repo has its own Jira
workflow skill (e.g. a repo-level `work-jira-ticket`), that skill owns the end-to-end
workflow — use this one as the plain client underneath it.

## Tooling

Two interfaces, pick per task:
- **`jira` CLI** (this skill's `scripts/jira.py`, on PATH) — cheapest; use for everything,
  and for all **writes** (they go through permission prompts).
- **MCP Jira tools** (`mcp__*jira*`, read-only) — structured reads/JQL when you want
  parsed objects instead of text.

Run bare `jira` for the full command list. Common:

```
jira whoami                      # ALWAYS run first on a new Jira task
jira get {{ core.ticket_example }}                # full ticket as JSON
jira search '<JQL>' [max]        # e.g. 'assignee=currentUser() AND resolution IS EMPTY'
jira fields <KEY|PROJECT>        # discover custom field ids
jira transitions {{ core.ticket_example }}        # list → jira transition {{ core.ticket_example }} "In Progress"
jira set {{ core.ticket_example }} <field> <json>
jira comment {{ core.ticket_example }} "text"
```

## Contract & rules

- **Exit 2** = no/bad token, unreachable, or Jira not configured (`jira.url` unset) → tell
  the user to create a PAT ({{ jira.url }} → profile → Personal Access Tokens → save to
  `~/.config/jira`, mode 600), or fall back to the browser. Never print the token.
- **Discover, don't hardcode**: friendly field names exist only for the fields configured in
  `jira.fields` (harness config, per project). For anything else, run
  `jira fields <PROJECT>` and use raw `customfield_*` ids.
- **Plain text, not ADF**: Jira Server 8.x takes plain text (with Jira wiki markup) in
  description/comment bodies. Never send Atlassian Document Format JSON.
- **Read back after write**: Jira silently ignores writes with the wrong value shape —
  after `set`/`create`, run `jira get` and confirm the field actually changed.
- Writes go through the guard hook. Promptless: `create` carrying a provenance label,
  `label KEY add agent-*`, and every write (`set`/`comment`/`upload`/`label`/`link`/
  `transition`) on tickets that already carry any `agent-*` label. Prompted: writes to purely
  human tickets (no `agent-*` label). `transition` on a human ticket is **denied** (state is
  human-only). Native links only between agent-labelled tickets. Don't work around any of this.
- `jira create` is **denied** without a provenance label: `{{ core.agent_labels.drafted }}`
  (from `/create-ticket`) or `{{ core.agent_labels.created }}`+`{{ core.agent_labels.worked }}`
  (work-ticket sub-tickets). Prefer `/create-ticket` for new tickets.
- Use **literal ticket keys** in write commands (not `$VARS`) — the hook verifies labels
  from the command text; unexpanded variables degrade to a prompt.
