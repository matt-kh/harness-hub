# Subagent protocol — local worktrees; converge (single) or publish (stacked)

Subagents never push, never create MRs, never touch Jira. They work on local sub-branches in
git worktrees. What happens to those branches depends on **Q8b Delivery**:
- **single** (S/M, or Q8b = single): squash-merged into the ticket branch by the main agent,
  one push, one MR (today's flow).
- **stacked** (L/XL default): each sub-branch is pushed by the main thread and gets its own
  MR targeting the ticket branch (see SKILL Step 6b). Nothing is merged locally.

## Naming (consistent with the sibling `repo_branch` worktree convention; NO ticket key anywhere)

- Ticket branch: `<short-name>` (e.g. `docker-networks`) — the key lives on the MR title
- Sub-branch: `<short-name>-sub-NN-<task>` (NN = decomposition id, e.g. `docker-networks-sub-01-schema`)
- Worktree dir: `../<repo>_<sub-branch>` (e.g. `../shop_docker-networks-sub-01-schema`)

The `-sub-` infix is load-bearing for the guard hook: a `git push` of a `-sub-` branch issued
from **inside a sub worktree** (where subagents run) asks; a `glab mr create` whose source is
a `-sub-` branch is **denied** unless it targets a ticket/sub branch (never `master|main`).
GitHub: the same rule applies to `gh pr create -H <-sub- branch> -B <base>` (no `-B` → denied).

## Create

```bash
REPO=$(basename "$(git rev-parse --show-toplevel)")
START="$BR"                                   # or the blocker's sub-branch when depends_on is set
git worktree add -b "$BR-sub-NN-<task>" "../${REPO}_$BR-sub-NN-<task>" "$START"
```

Only for tasks that are **file-disjoint** (2–8). Stacked delivery: a part with `depends_on`
starts from its blocker's branch **after the blocker is implemented** (chain); everything else
starts from `$BR` (fan-in). Single delivery: sequential/overlapping work stays on `$BR`.
`--no-subagents` skips worktrees entirely.

## Subagent brief (Agent tool; default model is {{ core.model_policy.execute }} via CLAUDE_CODE_SUBAGENT_MODEL)

> Work only inside `<worktree path>` on branch `<sub-branch>`. Task: <one task>.
> Commit as `<imperative summary>` — no ticket key in commit messages; keep commits focused.
> Do NOT `git push`, do NOT create or switch branches, do NOT run `jira`, `glab` or `gh` write
> commands, do NOT touch files outside your task. Self-check with the narrowest relevant
> command (single test file / lint on changed files). Report: files changed, how you
> verified, anything unfinished.

The user-level guard hook applies to subagents too (hooks are session-wide).

## Converge (single delivery — main agent, on `$BR`, in the main checkout)

```bash
git merge --squash "$BR-sub-NN-<task>" && git commit -m "<task summary>"   # one commit per task, no ticket key
git worktree remove "../${REPO}_$BR-sub-NN-<task>" && git branch -D "$BR-sub-NN-<task>"
git worktree prune
```

- `--squash` (not `--no-ff`): the MR is squashed on merge anyway; one commit per task is
  what a reviewer wants to see.
- Conflicts are resolved by the main agent here — never re-dispatch a subagent to "fix" a merge.
- Before Step 5: `git worktree list` shows only the main checkout; `git branch --list '*-sub-*'` is empty.

## Publish (stacked delivery — main agent, main checkout)

No local merge. Before publishing, run the **integration check** in an ephemeral, never-pushed
worktree so the union of all parts is known to build and pass Step 5 checks:

```bash
git worktree add --detach "../${REPO}_$BR-integration" "$BR"
( cd "../${REPO}_$BR-integration" \
  && for s in $(git branch --list "$BR-sub-*" --format='%(refname:short)'); do git merge --no-edit "$s" || exit 1; done \
  && <Step 5 checks> )
git worktree remove --force "../${REPO}_$BR-integration"
```
Conflicts here mean two parts touch the same files: fix inside the **owning** sub worktree
(parts must stay file-disjoint); never re-dispatch a subagent to "fix a merge".

Then SKILL Step 6b: one `git push -u origin <branch>` per branch (ticket branch first), one
`glab mr create -s <sub> -b <target>` per part, second-pass descriptions with literal IIDs.
GitHub: `gh pr create -R owner/repo -H <sub> -B <target>` per part (`github.md` §6b); never in fork flow.

### Worktree lifecycle (stacked)

- Sub worktrees **stay until their MR is merged** — review fixes are committed there and
  pushed with a plain `git push origin <sub-branch>` (no MR change needed).
- Cleanup only for merged parts (read the state first, never guess):
  ```bash
  glab mr list --source-branch "$BR-sub-01-schema" --all -F json | jq -r '.[0].state'   # merged
  # GitHub: gh pr list -R owner/repo --head "$BR-sub-01-schema" --state all --json state | jq -r '.[0].state'   # MERGED
  git worktree remove "../${REPO}_$BR-sub-01-schema" && git branch -D "$BR-sub-01-schema" && git worktree prune
  ```
- `git worktree list` = main checkout + one entry per **open** sub MR.
- Remote sub branches are deleted by humans ("Delete source branch" when merging) — the agent
  never deletes remote branches. GitHub: "Delete branch" after merge is what retargets the
  dependents; deleting before merge closes the PR.
