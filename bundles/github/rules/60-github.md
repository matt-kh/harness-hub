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
  issues with `{{ core.agent_labels.drafted }}`. Never write `Closes/Fixes/Resolves #N` (or
  `owner/repo#N`, or an issue URL) — mention `#N` instead (denied). One exception: in a
  repository whose tracker is GitHub Issues (its `.harness.toml` `[repo] tracker`, else the first
  matching `ticket_workflow.trackers` entry, else a github.com origin; a declared `jira` always
  wins), the body of the PR to the default branch (`gh pr create -R owner/repo -H <ticket branch> -B <default branch>`,
  `-B` written out, or `gh pr edit N` of such a PR) may say `Closes #N` for issues labelled
  `{{ core.agent_labels.worked }}`, so GitHub closes them when a human merges it. Write it as one
  plain one-line command run from that repository's checkout (no `cd`, `GH_REPO`, `sh -c`,
  `$(…)` or other commands on the line; each flag once; `-R` only for that checkout's own repo),
  with the plain text in `-b`, or in a `-F` file, which the guard cannot check, so work-ticket
  reads it back (`closingIssuesReferences`). Never in commits, sub PRs, fork PRs, `gh pr merge` or
  `gh api`; `github.close_issue_on_merge = false` turns the exception off.
- `gh pr create` and edits to agent-labelled PRs/issues run promptless, human ones prompt.
- Humans decide: `gh pr merge|review` and `gh issue delete|transfer` always ask;
  `gh pr close|reopen|ready` and `gh issue close|reopen` ask on a human PR/issue and run
  promptless on an agent-labelled one. Run them only on the user's explicit request in the main
  thread; from a subagent the guard denies them — hand the command back.
- `gh api` GETs and read-only GraphQL queries pass; writes prompt (denied from a subagent).
  Write gh subcommands literally and unquoted: `gh "pr" merge` or a `$VAR` subcommand asks.
- `gh pr update-branch N [--rebase]` (server-side update from the base branch) runs promptless
  on agent-labelled PRs and asks on human and fork PRs; refresh the local worktree afterwards
  with `git pull --rebase`.
- Stacked delivery: sub PRs (`<branch>-sub-NN-<task>`) target the ticket branch or their
  blocker's sub branch, never the default branch (the guard denies it); humans decide the
  merges, bottom-up. A chain is linked as a native GitHub stack with
  `gh stack link --base <ticket branch> N1 N2 …` by PR numbers only (agent-labelled `-sub-` PRs;
  the main PR stays outside; a branch name would push and open an unlabelled PR, so it is
  denied). `gh stack merge` is a human decision (asks; denied from a subagent), as are
  `--open`, `gh stack alias`, unknown verbs and flags before the verb: put the verb first. `stk sync --stack BR` keeps the stack in sync; `gh stack sync|push|submit|rebase`
  are not used (they ask, and deny on the default branch).
- Forks/upstream: the agent cannot label there, so edits ask and delivery is a single PR.
- Secret: `~/.config/gh/hosts.yml` holds the token — never read or print it; check auth with
  `gh auth status`.

A repository's own instructions for the same action replace this block.
