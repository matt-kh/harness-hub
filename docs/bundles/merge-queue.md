# Bundle: merge-queue

Merge trains and merge queues on free tiers. GitLab merge trains, merged-results pipelines and
MR dependencies are Premium; GitHub's merge queue, rulesets and auto-merge exist on Free only
for public repositories. The `mq` CLI recreates the train with free-tier features, one MR/PR
at a time, using native `glab` / `gh` / `git` commands it prints before it runs them.

**Humans run the train.** Agents run `mq check`, `mq plan`, `mq status` and `mq sync`
(agent-labelled MRs/PRs only) and hand the human `mq run …`; the guard asks when an agent
invokes it.

| Native (paid / public) | Free-tier emulation in `mq` |
|---|---|
| Merge train / queue order | ordered queue (`--stack BR` by `-sub-NN`, explicit refs, or `--label L` by number); one MR/PR at a time |
| Merged-results pipeline | server-side rebase (`glab mr rebase`, `gh pr update-branch --rebase`), then the MR/PR's own pipeline/checks on that head |
| Train merges when green | GitLab `glab mr merge --auto-merge --sha` (the server arms the merge; survives `mq` dying); GitHub `gh pr merge --auto` where protection or a queue exists, else wait for `gh pr checks` and `gh pr merge --match-head-commit` |
| Failed MR dropped from the train | `mq.on_failure`: a stack stops (later parts depend on earlier ones), a label or refs selection may skip and continue |
| MR dependencies (Premium) | chained parts stop the train with the exact `git rebase --onto` + `git push --force-with-lease` commands once the blocker merged (mq never force-pushes) |

Native trains are used when present: a GitHub `merge_queue` ruleset is enqueued with
`gh pr merge --auto`, and GitLab's `merge_trains_enabled` makes `--auto-merge` add the MR to
the real train. The full state machine: [state-machine.md](../../bundles/merge-queue/skills/mq/references/state-machine.md).

## Design notes

- **Just-in-time rebase.** Only the head of the queue is rebased (O(N) pipelines, not O(N²));
  work-ticket's integration check already tested the union of the parts before publishing.
- **Server-driven arming first** (`--auto-merge --sha`, `gh pr merge --auto`): the server
  enforces approvals, threads and pipeline rules, and a killed `mq run` loses nothing. `mq run`
  is idempotent and resumes from live state; there is no local state file.
- **Pinned merges.** `--sha` / `--match-head-commit` on every merge; a target-SHA check before
  client-driven merges; `mq.max_retries` bounds busy-target loops. `ff` / `rebase_merge` make
  GitLab itself refuse a stale source.
- **Fan-in parts are file-disjoint** by work-ticket's rule, so the server-side rebase is
  conflict-free; chains are the only case that needs a local `rebase --onto`.

Known limits: with `merge_method = merge` a small race remains between the target-SHA check and
the merge; a private GitHub Free repository has no server-side gate at all, so
`mq.require_checks` is the only guard against merging an unchecked PR; `glab mr rebase` and
`gh pr update-branch` rewrite an agent branch server-side, so sub worktrees must
`git pull --rebase`.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| An MR fails with "the target is busy" after several rebases | the target branch keeps moving (`need_rebase` / target-moved loop) | raise `mq.max_retries` (`HARNESS_MQ_MAX_RETRIES`) or re-run at a quieter time; `ff` / `rebase_merge` lets GitLab refuse stale sources itself |
| Parts stop with "no pipeline on this head" | CI `rules` filter on the target branch, and parts target the ticket branch | add a `merge_request_event` rule that does not filter on `CI_MERGE_REQUEST_TARGET_BRANCH_NAME`, or set `mq.require_checks = false` deliberately |
| A sub MR suddenly targets `main` | GitLab CE retargets dependents to the default branch when a blocker's branch is deleted | `mq sync --stack BR` retargets it (agent-labelled), or run the printed `glab mr update N --target-branch BR` |
| `gh pr update-branch` prints `422 … already up to date` | the PR was already current | harmless; mq treats it as success |
| `glab mr rebase` fails with `403` | no push access to the source branch (protected or a fork) | rebase locally with the printed `git rebase` + `git push --force-with-lease` commands |
| The main MR fails with "needs Maintainer on protected main" | Developers can merge parts into the unprotected ticket branch, not into the protected default branch | ask a Maintainer to merge it (or to run `mq run --stack BR --with-main`) |
| An armed MR/PR lost its auto-merge | a new push or a failed pipeline cancels it | mq re-arms on the new head (counts toward `mq.max_retries`); check the pipeline first |
| A private GitHub repository shows "no server-side gate" and parts have no checks | GitHub Free offers rulesets, protection, auto-merge and the merge queue only for public repositories | `mq run` is the queue there; keep `mq.require_checks = true` and add a workflow so PRs get checks |
| A chained part stops with `git rebase --onto` commands | its blocker merged (squashed), and the child still carries the blocker's pre-squash commits | run the printed commands in the child's worktree, then re-run `mq run` |

<!-- generated:begin source=bundles/merge-queue/bundle.toml -->
## Summary

Merge trains / merge queues on free tiers: the `mq` CLI (plan, status, check, sync, run) over glab, gh and git

Recreates GitLab merge trains and GitHub merge queues with free-tier features only, using native
`glab` / `gh` / `git` commands it prints before it runs them. `mq plan|status|check` are reads;
`mq sync` prepares agent-labelled MRs/PRs (fixes a sub part aimed at the default branch,
rebases only the head of the queue server-side, marks the main MR/PR ready once every part
merged); `mq run` is the train and is run by the human in a terminal (the guard asks when an
agent tries): one MR/PR at a time, server-side rebase, wait for the pipeline/checks on that
head, then arm the server's auto-merge or merge pinned to the tested head (`--sha`,
`--match-head-commit`). Native GitHub merge queues and GitLab Premium trains are detected and
used. Integrates with work-ticket's stacked delivery (`mq sync --stack BR`).

- **Depends on:** `core`
- **Recommends:** `ticket-workflow`
- **Needs one of:** `gitlab`, `github`
- **Stability:** experimental
- **Domain / posture:** scm / label-gated

## Components

Stable ids derived from the path, with their [taxonomy](../reference/taxonomy.md) facets (domain shown only where it differs from the bundle's). All bundles: [catalog](../catalog.md).

**Skills**

- `merge-queue/skills/mq` — control: guide · function: client · posture: label-gated · model: execute · yields: declaration

**Rules**

- `merge-queue/rules/65-merge-queue` — control: guide · function: govern · yields: text

**Guard sections**

- `merge-queue/guard.d/65-merge-queue` — control: sensor · function: govern · decisions: ask 2 · allow 1 · yields: declaration

**Permission lists**

- `merge-queue/permissions` — control: guide · function: govern · decisions: ask 1 · allow 4 · yields: config

**CLIs**

- `merge-queue/bin/mq` — function: client · posture: label-gated · yields: n/a

**Doctor checks** (function: setup · posture: read-only; table below): `merge-queue/doctor/mq-cli`, `merge-queue/doctor/mq-scm-cli`

**Manual steps** (function: setup; table below): `merge-queue/steps/mq-github-repo-settings`, `merge-queue/steps/mq-gitlab-project-settings`, `merge-queue/steps/mq-read-the-train`

## Requirements

### Binaries

| binary | min version | install | optional | why |
|---|---|---|---|---|
| `gh` | 2.60.0 | `harness install gh` | yes | GitHub queues: PR reads, `gh pr update-branch`, `gh pr checks`, `gh pr merge --auto\|--match-head-commit`. |
| `git` | 2.30 |  | no | Remote and worktree facts (`git remote get-url`, `git worktree list --porcelain`). |
| `glab` | 1.40.0 |  | yes | GitLab trains: MR reads (`glab api`), `glab mr rebase`, `glab mr merge --auto-merge --sha`. |
| `python3` | 3.9 |  | no | The mq CLI is stdlib python. |

### Configuration

| key | type | required | default | description |
|---|---|---|---|---|
| `mq.label` | string | no | `"merge-queue"` | Label that selects the queue when neither refs nor --stack are given (open MRs/PRs carrying it, by number). HARNESS_MQ_LABEL. |
| `mq.max_retries` | integer | no | `3` | Rebases / re-arms per MR/PR before it fails (bounds the need_rebase and target-moved loop on a busy target branch). HARNESS_MQ_MAX_RETRIES. |
| `mq.on_failure` | string | no | `"stop"` | What `mq run` does when an MR/PR fails in a label or refs selection: stop the train or skip it and continue. A stack always stops (later parts depend on earlier ones). HARNESS_MQ_ON_FAILURE. |
| `mq.poll_seconds` | integer | no | `20` | First poll interval while the train waits on a rebase, pipeline or merge; backs off to 60 s. HARNESS_MQ_POLL_SECONDS. |
| `mq.require_checks` | boolean | no | `true` | An MR/PR with no pipeline or checks on its head stops the train (after 3 polls) instead of merging unchecked. On a private GitHub Free repository this is the only guard. HARNESS_MQ_REQUIRE_CHECKS (1\|true\|yes). |
| `mq.timeout_minutes` | integer | no | `90` | Per-MR/PR deadline in `mq run`; on expiry the MR/PR fails and the resume command is printed. HARNESS_MQ_TIMEOUT_MINUTES. |
| `mq.update_method` | string | no | `"rebase"` | GitHub only: `gh pr update-branch --rebase` (rebase) or a merge commit from the base (merge). GitLab always rebases (`glab mr rebase`). HARNESS_MQ_UPDATE_METHOD. |

### Secrets (never in harness.toml)

_none_

## Manual steps

<a id="mq-gitlab-project-settings"></a>

### mq-gitlab-project-settings — GitLab: project merge settings for the train

*once per org · needs maintainer · ~5 min*

**Why:** With a semi-linear or fast-forward merge method GitLab itself refuses a stale source (need_rebase), and with Pipelines must succeed an armed MR merges server-side even if `mq run` dies.

**How:**

Settings → Merge requests, per project (a Maintainer):
- Merge method: **Merge commit with semi-linear history** (`rebase_merge`) or **Fast-forward**
  (`ff`). Plain merge commits leave a small race between mq's target-SHA check and the merge.
- Merge checks: **Pipelines must succeed** on; choose whether **Skipped pipelines are
  considered successful** (mq follows the project setting).
- **Enable "Delete source branch" option by default**: off — mq deletes the branches of parts
  without dependents itself; the default makes GitLab CE retarget chained parts to the default
  branch.
Then run `mq check` in a checkout (`mq check --fix` prints the `glab api -X PUT` commands; it
never runs them).

**Verify:** `true` (exit 0)

<a id="mq-github-repo-settings"></a>

### mq-github-repo-settings — GitHub: repository settings for the queue

*once per org · needs admin · ~5 min*

**Why:** Public repositories (and paid plans) can enforce checks server-side, so `mq run` arms auto-merge or enqueues; private Free repositories have none of it and `mq run` is the queue.

**How:**

Public repository (or a paid plan):
- Settings → Rules → Rulesets: a branch ruleset on the default branch with **Require status
  checks to pass**; optionally **Require merge queue** (mq then just enqueues with
  `gh pr merge --auto`).
- Settings → General → Pull Requests: **Allow auto-merge** and **Automatically delete head
  branches** (deleting a merged part's head branch is what retargets its dependents).
Private repository on GitHub Free: rulesets, protection, auto-merge and the merge queue are not
available; nothing to configure — keep `mq.require_checks = true`, it is the only guard.
Then run `mq check` in a checkout.

**Verify:** `true` (exit 0)

<a id="mq-read-the-train"></a>

### mq-read-the-train — Read how the train runs (you run it)

*once per machine · needs nothing but a terminal · ~2 min*

**Why:** Merging is human-only: the agent plans and prepares, you run the train.

**How:**

- Agents run `mq check`, `mq plan`, `mq status` and `mq sync` (agent-labelled MRs/PRs only)
  and hand you the command; you run `mq plan …` and then `mq run …` in your own terminal.
- Every native command is printed before it runs. Ctrl-C is safe: re-running resumes from live
  state (there is no local state file), and an MR/PR whose auto-merge was armed still merges
  server-side even if mq dies.
- A stack stops at the first failure; chained parts stop with the exact `git rebase --onto` +
  `git push --force-with-lease` commands (mq never force-pushes).

**Verify:** `true` (exit 0)

## Doctor checks

| id | severity | offline | fix |
|---|---|---|---|
| `mq-cli` | fail | runs | `harness apply` |
| `mq-scm-cli` | fail | runs | `Activate the gitlab or github bundle (hub.bundles) and run harness apply` |

## Guides and sensors

Guides steer the agent before it acts; sensors detect at or after the action. Pairing: **paired**.

| side | kind | ref | note |
|---|---|---|---|
| guide | rule | `rules/65-merge-queue.md` | humans run the train; agents plan, inspect and sync agent-labelled MRs/PRs |
| guide | skill | `skills/mq` | the mq CLI: check, plan, status, sync, and the hand-off of mq run |
| guide | permission | `permissions.toml` | mq plan\|status\|check\|sync allowed, mq run asks |
| sensor | guard | `guard.d/65-merge-queue.sh` | mq run and sync --include-human ask; mq sync allows |
| sensor | doctor | `doctor_checks` | the mq CLI and an SCM CLI on PATH |
| sensor | test | `tests/run.sh` | this bundle's rows against core + merge-queue only, then the mq suite |
| sensor | test | `guard.d/tests.sh` | rows for section 65 incl. bypasses and repository ownership |
| sensor | test | `skills/mq/scripts/tests/run.sh` | golden scenarios for every verb against stubbed glab, gh and git, plus stub-log invariants |

**Not covered:** `mq sync`'s label gate is enforced inside the CLI (sensed by its golden suite), not by the guard; the human-run `mq run` is outside any hook.

## Uninstall

Kept on uninstall: _nothing_

Removes the mq link, the rendered skill, the rule block and guard section 65; MRs/PRs, labels and project settings are untouched.
<!-- generated:end -->
