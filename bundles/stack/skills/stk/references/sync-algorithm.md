# `stk sync` — the algorithm

A stack is a ticket branch `BR` with its main MR/PR (`BR -> BASE`) and parts
`BR-sub-NN-<task>`. Each open part targets `BR` or another part's branch. `stk` builds the
topology from the server's MR/PR list: every path `BR <- p1 <- p2 <- … <- top` through open
parts is processed bottom-up; a path of one part with no dependents is a **fan-in leaf**,
anything longer (or a part with dependents) is a **chain**. A foundation chain with leaves off
its top is a tree: every leaf is the top of its own path, and branches already rebased in this
run are not rebased twice.

`stk plan` runs the same code with every write replaced by "planned" (no fetch: it reads the
remote-tracking refs as of the last fetch). `stk sync` runs it for real.

## 1 Retarget (server)

An open part whose target is

- the repository's default branch while its source is a `-sub-NN-` branch (GitLab CE
  retargets dependents there when a blocker's source branch is deleted), or
- a merged part's source branch

gets a new target: the merged blocker's own target, walked until an open part or `BR` is
reached (`BR` for the misfire). GitLab `glab mr update N --target-branch T`; GitHub
`gh pr edit N -R o/r -B T` — only when GitHub did not already retarget (it does when the
merged PR's head branch is deleted). Unlabelled MRs/PRs are skipped with the label command.

## 2 Cascade (local, per path)

`git -C <main checkout> fetch origin` once, then for each path find the **lowest stale part**
`p` with target `t` (`t`'s tip is `origin/t`, or the local branch when `t` was rebased in this
run):

| Case | Old base passed to `--onto` |
|---|---|
| `p` contains the head of a merged part that is not in `t` (pre-squash or pre-rebase commits) | that merged part's head sha at merge (MR `sha` / PR `headRefOid`) |
| `t` is an open part rebased in this run | `t`'s sha before this run |
| `t` is an open part that moved (amended and pushed) | `git merge-base --fork-point origin/t p` (reflog of `origin/t`), else `git merge-base` |
| `t` is `BR`, `BR` advanced, `p` has dependents, and the merge method needs an up-to-date source (GitLab `ff` / `rebase_merge`, a GitHub "up to date" rule) | `git merge-base origin/BR p` |

A part that contains `t`'s tip is not stale; a fan-in leaf behind `BR` is step 4's, not a
cascade. With a plain merge method and merge commits, a merged blocker only needs a retarget.

Preconditions, each a skip with its reason and the manual commands: every part from `p` to
the top is agent-labelled; each has a local branch equal to `origin/<branch>`; a worktree has
the top branch checked out (`git worktree list --porcelain`); that worktree is clean
(`git status --porcelain` empty) and not mid-rebase/merge; every other worktree that has a
branch of the range checked out is clean too. Then:

```bash
git -C <other wt> switch --detach              # each lower range branch checked out elsewhere
GIT_EDITOR=true GIT_SEQUENCE_EDITOR=true \
  git -C <top wt> rebase --update-refs --onto <new base> <old base> <top>
git -C <other wt> switch <branch>              # re-attach, also after an abort
```

On a non-zero exit: `git -C <top wt> rebase --abort`, re-attach, and report the conflict with
the manual commands. Every worktree and every local branch is then exactly as it was (the
suite compares `git status --porcelain`, HEAD and `for-each-ref refs/heads` before and after).
Never `reset --hard`, never `rebase --continue` on the human's behalf.

### Finding: `--update-refs` and branches checked out in other worktrees (git 2.43.0)

Established in a throw-away repository (chain `A <- B <- C` on `feat-x`, each in its own
worktree, `feat-x` advanced, `git rebase --update-refs --onto feat-x <old> C` run in C's
worktree):

- git does **not** refuse. It silently leaves every branch that is checked out in another
  worktree out of the todo list: the interactive todo had **0** `update-ref` lines, the rebase
  exited 0, and only `C` moved — `A` and `B` stayed on the old base (stale).
- With `A`'s and `B`'s worktrees detached first (`git switch --detach`), the todo had **2**
  `update-ref` lines, git printed "Updated the following refs with --update-refs:
  refs/heads/A, refs/heads/B", all three branches sat on the new base, and
  `git switch <branch>` re-attached both worktrees cleanly (no local changes).

So the detach / re-attach around the rebase is required, not defensive: without it the push
would publish a rebased top on top of stale lower branches. As a second guard, `stk` compares
every range branch's sha before and after and refuses to push when one did not move. The
`gl-branch-checked-out-elsewhere` scenario covers it (and `.sync-lower-dirty`: a dirty lower
worktree skips the chain instead of detaching it).

## 3 Push

`git -C <top wt> push --force-with-lease origin <b1> <b2> …` for the range branches that moved
and whose MR/PR is agent-labelled. Never bare `--force`. The lease compares with the
remote-tracking refs fetched in step 2, so a push someone made since is rejected (reported:
fetch, look, re-run). `--no-push` / `stack.push = false` print the command instead. The core
guard allows exactly this form when typed by hand (a lease push of only `-sub-NN-` refs as
the whole command); every other force-push asks.

## 4 Leaf refresh (server)

A fan-in leaf behind `BR`: with `stack.leaf_refresh = auto` and a merge method that needs an
up-to-date source, **at most one** per invocation (CI cost) — `glab mr rebase N [--skip-ci]` /
`gh pr update-branch N -R o/r [--rebase]` (label-gated) — then the printed
`git -C <wt> pull --rebase origin <sub>` refreshes its worktree. Other behind leaves are
`todo` for the next run. A conflicting leaf is reported with the local commands and the hint
"parts that conflict share files: chain them".

## 5 Main ready

Every part merged (none open) and the main MR/PR is a draft: `glab mr update N --ready` /
`gh pr ready N -R o/r` (label-gated).

## Report and exit

Every step is `ran`, `planned`, `skipped`, `todo`, `conflict`, `failed` or `info`, with the
commands it ran or the commands for the human. Exit 0: nothing to do or all done; 1: some
step needs a human; 2: auth or access.
