## GitLab ({{ gitlab.host }})
- `glab` is authenticated to {{ gitlab.host }}; git itself stays on SSH remotes.
- MR titles start with the ticket key (e.g. `{{ core.ticket_example }} fix parser`); create with
  `--title` and `--description-file`, `--squash-before-merge --remove-source-branch`, and label
  agent-created MRs `{{ core.agent_labels.worked }}` so follow-up edits stay promptless.
- The guard asks when a `-t/--title` does not match the config key `gitlab.mr_title_re`
  (default: the ticket key and a space first; an empty value disables the check), and on
  `glab mr create --fill` (generated text may carry a closing keyword or a key-less title) and
  `--related-issue` (links, and may close, a GitLab issue) — pass a literal title and a
  description file instead.
- `glab api "<path>"` is the escape hatch for anything the CLI lacks — GETs only without
  confirmation; writes prompt.
- `glab mr create` and edits to agent-labelled MRs run promptless; edits to un-labelled MRs
  prompt; merging/approving is human-only (asks).
- Stacked delivery: sub MRs (`<branch>-sub-NN-<task>`) target the ticket branch, never the
  default branch (the guard denies it); humans merge bottom-up.
- Closing keywords + a ticket key (`Closes KEY`, `Fixes KEY`, `Resolves KEY`, `Implements KEY`)
  in commits, MR text or API payloads are denied: GitLab's Jira integration would transition
  the ticket. Mention the key instead.
- Secret: `~/.config/glab-cli/config.yml` holds the token — never read or print it; check
  auth with `glab auth status`.

A repository's own instructions for the same action replace this block.
