# Bundle: stack

Stacked MRs/PRs on free tiers. work-ticket delivers large tickets as a stack: a ticket branch
`BR` with its main MR/PR (`BR -> BASE`, Draft until the parts merged) and parts
`BR-sub-NN-<task>`, each its own MR/PR targeting `BR` (a **fan-in leaf**) or another part's
branch (a **chain**). Humans merge the parts bottom-up in the web UI. Between merges somebody
has to retarget, rebase and push the rest of the stack — that is `stk sync`.

**What the hosts give for free.**

| | GitLab (CE included) | GitHub (Free included) |
|---|---|---|
| Grouping | stacked MRs are shown as a stack (GA in 19.1) | none |
| Retarget when a part merges | CE retargets dependents only to the **default branch** (≤ 4 MRs), and only when the merged source branch is deleted | dependents are retargeted onto the merged PR's **base** when its head branch is deleted |
| Rebase the rest of the stack | no (`glab stack` is experimental and "not ready for production") | no |
| MR dependencies | Premium | none |

**What `stk` adds.** `stk sync --stack BR` retargets parts whose blocker merged (or that GitLab
sent to the default branch), rebases each chain in the worktree that has its top branch checked
out with one `git rebase --update-refs --onto`, pushes the rebased sub branches with
`--force-with-lease`, refreshes at most one fan-in leaf server-side when the merge method needs
an up-to-date source, and marks the main MR/PR ready once every part merged. It writes only to
agent-labelled MRs/PRs and prints every native command before it runs it. `stk plan` prints
the topology, the merge order for the human and the commands sync would run; `stk status` and
`stk check` are reads. The algorithm, including the `--update-refs` behaviour with branches
checked out in other worktrees: [sync-algorithm.md](../../bundles/stack/skills/stk/references/sync-algorithm.md).

**Chain vs fan-in.** Fanning every part in off `BR` looks parallel, but parts that touch the
same files (or the same registry file: schema, migrations list, exports index, routes,
lockfile, changelog) conflict on every remaining MR as soon as one merges. work-ticket
therefore chains parts whose `paths` overlap and fans in only provably disjoint ones (it
checks `git diff --name-only` pairwise before publishing). A chain costs a rebase after each
merge — automated here — instead of a conflict.

**Humans merge.** There is no merge verb. The guard allows a sole `stk sync` and asks for
`stk sync --include-human` (writes to unlabelled MRs/PRs). The core guard allows a hand-typed
`git push --force-with-lease origin <sub branches>` and asks for every other force-push.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| A sub MR suddenly targets `main` (misfired target) | GitLab CE retargets dependents to the default branch when a blocker's source branch is deleted | `stk sync --stack BR` retargets it to `BR` (agent-labelled); turn off "Delete source branch" by default (`stk check --fix`) |
| `cascade … conflict …; aborted` | a lower part changed lines the upper part also changed | every worktree is as it was; run the printed commands in the top part's worktree, resolve, `git rebase --continue`, push — or ask the author |
| `cascade … worktree … is not clean` (dirty worktree) | uncommitted or untracked files, or a rebase/merge in progress there | commit or stash them (or finish/abort the rebase), then re-run `stk sync` |
| `… is checked out in …, which is not clean` (branch checked out elsewhere) | a lower chain branch is checked out in another worktree; `stk` detaches it for the rebase and re-attaches it, which needs it clean | clean that worktree, then re-run |
| `no worktree has <top> checked out` | the chain's top branch has no worktree | `git worktree add ../<repo>_<top> <top>` (printed), then re-run, or run the printed commands |
| `the lease was rejected` | someone pushed one of the sub branches since the fetch | `git fetch origin`, look at their commits, re-run `stk sync` |
| `local <b> differs from origin` | unpushed local commits, or the branch is behind origin | push or pull that branch first, then re-run |
| A merged part's commits reappear in the next MR (squash vs merge) | squash (or rebase) merges rewrite the part's commits; its dependents still carry the originals | `stk sync` cascades them away (old base = the merged part's head at merge); plain merge commits need only a retarget |
| A fan-in leaf stays behind `BR` (leaf behind) | the merge method does not need an up-to-date source, `stack.leaf_refresh = never`, or another leaf was refreshed this run | nothing to do under plain merge; otherwise re-run `stk sync` after the previous leaf's pipeline, then `git -C <wt> pull --rebase origin <sub>` |
| `conflicts with BR; parts that conflict share files` | two fan-in leaves touch the same files | chain them: rebase the later part onto the earlier one and retarget it |

<!-- generated:begin source=bundles/stack/bundle.toml -->
## Summary

Stacked MRs/PRs on free tiers: the `stk` CLI (plan, status, check, sync) keeps a chain of dependent parts retargeted, rebased and pushed

Automates what GitLab's stacked MRs and GitHub's base retargeting leave to you on free tiers:
when a lower part of a stack is merged or amended, `stk sync` retargets its dependents
(`glab mr update --target-branch`, `gh pr edit -B`), rebases each chain locally in the worktree
that has its top branch checked out (`git rebase --update-refs --onto`, aborted cleanly on a
conflict), pushes the rebased sub branches with `--force-with-lease`, refreshes at most one
fan-in leaf server-side when the merge method needs an up-to-date source, and marks the main
MR/PR ready once every part merged. It writes only to agent-labelled MRs/PRs and prints every
native command before it runs it. `stk plan|status|check` are reads; `plan` prints the
bottom-up merge order for the human, who merges in the web UI. Stacks are work-ticket's
`<BR>-sub-NN-<task>` branches (`stk sync --stack BR`).

- **Depends on:** `core`
- **Recommends:** `ticket-workflow`
- **Needs one of:** `gitlab`, `github`
- **Stability:** experimental
- **Domain / posture:** scm / label-gated

## Components

Stable ids derived from the path, with their [taxonomy](../reference/taxonomy.md) facets (domain shown only where it differs from the bundle's). All bundles: [catalog](../catalog.md).

**Skills**

- `stack/skills/stk` — control: guide · function: client · posture: label-gated · model: execute · yields: declaration

**Rules**

- `stack/rules/65-stack` — control: guide · function: govern · yields: text

**Guard sections**

- `stack/guard.d/65-stack` — control: sensor · function: govern · decisions: ask 1 · allow 1 · yields: declaration

**Permission lists**

- `stack/permissions` — control: guide · function: govern · decisions: allow 4 · yields: config

**CLIs**

- `stack/bin/stk` — function: client · posture: label-gated · yields: n/a

**Doctor checks** (function: setup · posture: read-only; table below): `stack/doctor/stk-cli`, `stack/doctor/stk-git-update-refs`, `stack/doctor/stk-scm-cli`

**Manual steps** (function: setup; table below): `stack/steps/stack-github-repo-settings`, `stack/steps/stack-gitlab-project-settings`, `stack/steps/stack-read-the-flow`

## Requirements

### Binaries

| binary | min version | install | optional | why |
|---|---|---|---|---|
| `gh` | 2.60.0 | `harness install gh` | yes | GitHub stacks: PR reads, `gh pr edit -B`, `gh pr ready`, `gh pr update-branch`. |
| `git` | 2.38 |  | no | The cascade uses `git rebase --update-refs` (2.38+), worktrees and lease pushes. |
| `glab` | 1.40.0 |  | yes | GitLab stacks: MR reads (`glab api`), `glab mr update --target-branch\|--ready`, `glab mr rebase`. |
| `python3` | 3.9 |  | no | The stk CLI is stdlib python. |

### Configuration

| key | type | required | default | description |
|---|---|---|---|---|
| `stack.label` | string | no | `"stack"` | Label that selects stacks when neither refs nor --stack are given (the stacks of open MRs/PRs carrying it). HARNESS_STACK_LABEL. |
| `stack.leaf_refresh` | string | no | `"auto"` | auto: `stk sync` rebases at most one fan-in leaf server-side per run, and only when the merge method needs an up-to-date source (GitLab ff / rebase_merge, a GitHub "up to date" rule); never: report it only. HARNESS_STACK_LEAF_REFRESH. |
| `stack.push` | boolean | no | `true` | `stk sync` pushes the rebased sub branches with --force-with-lease; false rebases locally and prints the push commands (like --no-push). HARNESS_STACK_PUSH (true\|false). |
| `stack.update_method` | string | no | `"rebase"` | GitHub leaf refresh: `gh pr update-branch --rebase` (rebase) or a merge commit from the base (merge). GitLab always rebases (`glab mr rebase`). HARNESS_STACK_UPDATE_METHOD. |

### Secrets (never in harness.toml)

_none_

## Manual steps

<a id="stack-gitlab-project-settings"></a>

### stack-gitlab-project-settings — GitLab: project settings for stacked MRs

*once per org · needs maintainer · ~5 min*

**Why:** GitLab CE retargets the dependents of a merged part to the default branch when the part's source branch is deleted, and the merge method decides how much rebasing a stack needs.

**How:**

Settings → Merge requests, per project (a Maintainer):
- **Enable "Delete source branch" option by default**: off. Sub MRs inherit the default, and a
  deleted blocker branch sends its dependents to the default branch (`stk sync` repairs it,
  but it is noise).
- Merge method: plain **Merge commit** needs no rebase after a merge (only a retarget);
  **semi-linear** or **fast-forward** need the chains rebased and the fan-in leaves refreshed
  after every merge (`stk sync` does both, one leaf per run).
- Squash: either works; squashed parts leave pre-squash commits in their dependents, which
  `stk sync` cascades away.
- Sub branches (`*-sub-*`) must not be protected: `stk sync` pushes them with
  `--force-with-lease`.
Then run `stk check --stack <BR>` in a checkout (`--fix` prints the `glab api -X PUT`
commands; it never runs them).

**Verify:** `true` (exit 0)

<a id="stack-github-repo-settings"></a>

### stack-github-repo-settings — GitHub: repository settings for stacked PRs

*once per org · needs admin · ~3 min*

**Why:** With automatic head-branch deletion GitHub retargets a merged part's dependents onto its base; an "up to date" rule decides whether fan-in leaves need a refresh.

**How:**

Settings → General → Pull Requests: **Automatically delete head branches** on (GitHub then
retargets dependents itself; `stk sync` retargets when it is off). Squash or rebase merges
leave pre-merge commits in dependents; `stk sync` cascades them away. A ruleset or branch
protection that requires branches to be up to date makes `stk sync` refresh one fan-in leaf
per run with `gh pr update-branch`. Then run `stk check --stack <BR>` in a checkout.

**Verify:** `true` (exit 0)

<a id="stack-read-the-flow"></a>

### stack-read-the-flow — Read how a stack is merged (you merge it)

*once per machine · needs nothing but a terminal · ~2 min*

**Why:** Merging is human-only: stk keeps the stack mergeable, you merge it.

**How:**

- `stk plan --stack <BR>` prints the merge order: parts bottom-up, the main MR/PR last.
- Merge the first part in the web UI, then run `stk sync --stack <BR>` (or ask the agent to):
  the next part is retargeted, rebased and pushed. Repeat.
- A cascade conflict is aborted and reported with the commands; every worktree is left as it
  was. stk never uses `--force`, `reset --hard` or `rebase --continue`.

**Verify:** `true` (exit 0)

## Doctor checks

| id | severity | offline | fix |
|---|---|---|---|
| `stk-cli` | fail | runs | `harness apply` |
| `stk-scm-cli` | fail | runs | `Activate the gitlab or github bundle (hub.bundles) and run harness apply` |
| `stk-git-update-refs` | warn | runs | `Install git 2.38 or newer` |

## Guides and sensors

Guides steer the agent before it acts; sensors detect at or after the action. Pairing: **paired**.

| side | kind | ref | note |
|---|---|---|---|
| guide | rule | `rules/65-stack.md` | humans merge bottom-up; stk sync after each merge; agent-labelled parts only |
| guide | skill | `skills/stk` | the stk CLI: check, plan, status, sync and the merge-order hand-off |
| guide | permission | `permissions.toml` | stk plan\|status\|check\|sync allowed; never Bash(stk:*) |
| sensor | guard | `guard.d/65-stack.sh` | stk sync --include-human asks; a sole stk sync allows |
| sensor | doctor | `doctor_checks` | the stk CLI, an SCM CLI and git --update-refs |
| sensor | test | `tests/run.sh` | this bundle's rows against core + stack only, then the stk suite |
| sensor | test | `guard.d/tests.sh` | rows for section 65 incl. bypasses and repository ownership |
| sensor | test | `skills/stk/scripts/tests/run.sh` | golden scenarios for every verb against stubbed glab and gh and a real-git sandbox, plus invariants (lease pushes of sub branches only, worktrees untouched on conflict, one leaf refresh per run) |

**Not covered:** `stk sync`'s label gate is enforced inside the CLI (sensed by its golden suite), not by the guard; the guard only asks when the gate is lifted. Lease pushes of -sub- branches typed by hand are core section 30's.

## Uninstall

Kept on uninstall: _nothing_

Removes the stk link, the rendered skill, the rule block and guard section 65; MRs/PRs, branches, labels and project settings are untouched.
<!-- generated:end -->
