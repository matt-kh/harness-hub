## Jira ({{ jira.url }})
- Self-hosted Jira **Server 8.x** (not Cloud). Use the `jira` CLI (user-level skill) or the
  read-only `jira-mcp` tools. Plain text with wiki markup, never ADF.
- Reads are free. Creates, `agent-*` labelling, and every write to a ticket that already
  carries an `agent-*` label run promptless; writes to purely human tickets prompt.
- Ticket state is the user's decision: run `jira transition` only on the user's explicit
  request in the main thread. It asks on a human ticket and runs promptless on an
  agent-labelled one; from a subagent the guard denies it — hand the command back. Type the
  key literally: a transition whose ticket cannot be checked (`$VAR`, `xargs`) is denied.
- `jira create` needs a provenance label (`{{ core.agent_labels.drafted }}` from
  `/create-ticket`, `{{ core.agent_labels.created }}`+`{{ core.agent_labels.worked }}` for
  work-ticket sub-tickets); native links only between agent-labelled tickets.
- Custom field ids are org data: discover them with `jira fields <PROJECT>`; friendly names
  exist only for the fields configured in `jira.fields`.
- Secret: `~/.config/jira` holds the personal access token — never read or print it; check auth
  with `jira whoami`.

A repository's own instructions for the same action replace this block.
