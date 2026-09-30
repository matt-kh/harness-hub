## Jira ({{ jira.url }})
- Self-hosted Jira **Server 8.x** (not Cloud). Use the `jira` CLI (user-level skill) or the
  read-only `jira-mcp` tools. Plain text with wiki markup, never ADF.
- Reads are free. Creates, `agent-*` labelling, and every write to a ticket that already
  carries an `agent-*` label run promptless; writes to purely human tickets prompt and their
  transitions are denied (state is human-only).
- `jira create` needs a provenance label (`{{ core.agent_labels.drafted }}` from
  `/create-ticket`, `{{ core.agent_labels.created }}`+`{{ core.agent_labels.worked }}` for
  work-ticket sub-tickets); native links only between agent-labelled tickets.
- Custom field ids are org data: discover them with `jira fields <PROJECT>`; friendly names
  exist only for the fields configured in `jira.fields`.
- Secret: `~/.config/jira` holds the personal access token — never read or print it; check auth
  with `jira whoami`.
