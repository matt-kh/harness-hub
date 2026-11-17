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

## 4 Native GitHub stack (server, GitHub only)

GitHub can link a chain of PRs into a native **stack** (the Stacks API, driven by the
`github/gh-stack` extension). `stk` reads it the way gh-stack does, with GETs of
`repos/o/r/stacks?per_page=100&page=N` until a page is short (at most 20 pages); a stack
without a valid number is ignored, a closed one (`open: false`) does not count. A 404 means
the repository has no Stacks API: the step is skipped and every report is what it was without
it. A 403 is an `info` step (the token cannot read stacks; sync does not fail on it), an auth
failure (401, bad credentials) exits 2 like every other access error, and any other error
`skips` the step for this run. Otherwise `plan` and `status` show each
part's stack number (`native_stack`), `check` adds an `info` finding `native_stack` (enabled,
whether `gh extension list` has the row `gh stack  github/gh-stack`, which stacks sit on the
ticket branch), and `sync` re-reads the stacks after the cascade and push, then looks at every
**linear chain of two or more open parts rooted at `BR`** (bottom to top):

| Native stack state | Step |
|---|---|
| no stack holds any part | `info` (exit 0) with the link command: stk never creates the first stack (it is linked when the parts are opened) |
| the stack's open PRs equal the chain | `info`: consistent, nothing to do |
| the stack's PRs are all open and a strict ordered prefix of the chain, its base is `BR`, every part agent-labelled, the extension installed, the main checkout resolves this repository (below) and has no local branch named like a chain PR number, every retarget landed | `gh stack link --base BR N1 N2 …` (every chain PR, bottom to top, numbers only), in the main checkout with `GH_STACK_NO_UPDATE_NOTIFIER=1` (`planned` in `stk plan`) |
| the stack still lists a merged or closed PR and the chain grew | `todo`: `gh stack link S N…` (the stack number first appends on top) |
| order or membership differs, the parts sit in two stacks, the stack's base is not `BR` | `todo`: `gh stack unstack S` and `gh stack link --base BR N…`, for the human; when a stack also holds PRs that are not parts of this ticket, only those foreign PRs are named ("decide first"), with no unstack command |
| an unlabelled part, no extension, another repository could be resolved, a local branch named like a PR number | `todo` with the label command, `gh extension install github/gh-stack` or the link command |
| a retarget of a chain part failed in this run | `skipped` with the link command: re-run after the retarget |

Why only an append: `gh stack link` is additive at the top. Given PR numbers it updates the one
stack they belong to, refuses to drop a member, and rewrites every listed PR's base to chain
onto the PR below it. Listing a merged member would therefore re-chain the first open part onto
the merged branch, and leaving it out is refused; so a stack that still lists merged PRs is
extended in add mode (`gh stack link S N…`) by the human. The extension reads the repository
from its working directory (it takes no `-R`), hence the main checkout as cwd, which stk
finds itself (`git worktree list`, the first non-bare entry) wherever it was started.

**Which repository gh stack would act on.** gh-stack resolves the repository like gh itself:
`GH_REPO`, else the checkout's git remotes, preferring a `gh repo set-default` choice
(recorded as `remote.<name>.gh-resolved`) and the remote names upstream, github, origin. stk
does not guess that order: it links only when every rule gives the same answer, i.e. neither
`GH_REPO` nor `GH_HOST` is set, `origin` is this repository, no `gh-resolved` entry names
another repository, and no other remote points to another repository on a GitHub host.
Otherwise the step is a `todo` naming the cause, with the link command. gh-stack also reads an
argument as a branch when a local branch of that name exists, so a local branch named like a
chain PR number (`git rev-parse --verify --quiet refs/heads/<N>` in the main checkout) is a
`todo` too.

What stk never does here: create a first stack, unstack, reorder, link a branch name (that
would push and open an unlabelled PR), use the default branch as `--base`, or run
`gh stack sync|push|submit|rebase|merge`. The retarget in step 1 is unchanged (`gh pr edit -B`
only when GitHub did not retarget); a failed retarget of a PR in a native stack is reported
`failed` with the stack's number and the unstack and re-link commands. Fan-in leaves and chains
that branch (a part with two dependents) stay unlinked by design: a native stack is linear.
The command stk runs is exactly the form the GitHub guard allows promptless (`gh stack link
--base <ticket branch>` with literal numbers of agent-labelled `-sub-` PRs).

## 5 Leaf refresh (server)

A fan-in leaf behind `BR`: with `stack.leaf_refresh = auto` and a merge method that needs an
up-to-date source, **at most one** per invocation (CI cost) — `glab mr rebase N [--skip-ci]` /
`gh pr update-branch N -R o/r [--rebase]` (label-gated) — then the printed
`git -C <wt> pull --rebase origin <sub>` refreshes its worktree. Other behind leaves are
`todo` for the next run. A conflicting leaf is reported with the local commands and the hint
"parts that conflict share files: chain them".

## 6 Main ready

Every part merged (none open) and the main MR/PR is a draft: `glab mr update N --ready` /
`gh pr ready N -R o/r` (label-gated).

## Report and exit

Every step is `ran`, `planned`, `skipped`, `todo`, `conflict`, `failed` or `info`, with the
commands it ran or the commands for the human. Exit 0: nothing to do or all done; 1: some
step needs a human; 2: auth or access.
