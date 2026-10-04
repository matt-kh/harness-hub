## GitHub ({{ github.host }})
- `gh` is authenticated to {{ github.host }} (login `{{ github.login }}`); git stays on SSH
  remotes. `gh auth token` is denied. Always pass `-R owner/repo`, never `GH_REPO=` (the
  guard's label lookup cannot see it, so gated writes with `GH_REPO=` ask).
- PR-based; never push to a default branch (repos on free plans may have no server-side
  protection — the guard is the only one). Never `gh pr create --fill` (`-f`, `--fill-first`,
  `--fill-verbose`): pass `-t` and `-F body-file`. PR titles carry no `#N` — mention issues in
  the body. The guard asks on `--fill*` and on a `-t` title matching the config key
  `github.pr_title_forbid_re` (default `#[0-9]+`; an empty value disables the title check).
- GitHub Issues are the tracker for GitHub repos: `/work-ticket #N`; `/create-ticket` drafts
  issues with `{{ core.agent_labels.drafted }}`. Issue state (close/reopen) is human-only; never
  write `Closes/Fixes/Resolves #N` (or `owner/repo#N`, or an issue URL) — mention `#N` instead.
- `gh pr create` and edits to agent-labelled PRs/issues run promptless, human ones prompt;
  `gh pr merge|review` are human-only (ask). `gh api` GETs and read-only GraphQL queries pass;
  writes prompt.
- Forks/upstream: the agent cannot label there, so edits ask and delivery is a single PR.
- Secret: `~/.config/gh/hosts.yml` holds the token — never read or print it; check auth with
  `gh auth status`.
