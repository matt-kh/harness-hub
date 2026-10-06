---
name: jira
description: Interact with the org's self-hosted Jira Server ({{ jira.url }}) — read/search/update tickets, sprints, versions, transitions, attachments, comments. Use when the user mentions a Jira ticket key (e.g. {{ core.ticket_example }}), pastes a {{ jira.url }} link, or talks about tickets, issues, sprints, epics, or transitions.
model: {{ core.model_policy.execute }}
---

# Jira (self-hosted Server 8.x)

Generic client for `{{ jira.url }}`.

**Step 0 — repository-level harness (principle 8).** This is a user-level skill. Read the
repository's declaration first:

```bash
harness repo owns jira/skills/jira   # rc 0 = owned (prints why) → stop; rc 1 = carry on
```

If it is owned (by id or by its domain `tracker`), or the repository ships its own skill for
the same workflow, this skill yields: say so in one line, name the repository-level skill or
convention, and stop — nothing below runs and nothing is merged. If the repository owns the
*workflow* but not the client, stay available as the plain client underneath it. Never edit
the repository's harness to fit this skill. `harness repo` explains everything the
repository declares and any `.claude/skills|agents` name collisions.

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
