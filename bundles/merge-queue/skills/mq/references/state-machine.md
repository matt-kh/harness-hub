# mq state machine

Per MR/PR, in queue order; every ACT is printed before it runs.

Outcomes: **DONE** → next MR/PR; **WAIT** → poll (`mq.poll_seconds`, backing off to 60 s,
per-MR deadline `mq.timeout_minutes`); **STOP** → the train halts with the human's commands;
**FAIL** → `mq.on_failure` (a stack always stops: later parts depend on earlier ones).

`mq plan` and `mq status` evaluate the same machine without writing: they show the next step
and the native commands the train would run from there. `mq sync` runs S1 fixes and the S2
rebase of the queue head only. `mq run` drives the whole machine.

## GitLab (CE and above)

Reads: `glab api "projects/:id/merge_requests/IID?include_diverged_commits_count=true&include_rebase_in_progress=true"`,
`glab api projects/:id`, `glab api "projects/:id/repository/branches/<target>"`.

| Step | Native command | Fields | Transitions |
|---|---|---|---|
| S0 load | api MR | `state draft labels source_branch target_branch sha squash has_conflicts detailed_merge_status merge_when_pipeline_succeeds head_pipeline{status,sha} diverged_commits_count rebase_in_progress merge_error` | merged → DONE; closed → FAIL; draft → STOP (`glab mr update IID --ready`; only `sync` un-drafts the *main* MR when all parts merged) |
| S1 target | `glab mr update IID --target-branch BR` | `target_branch`, project `default_branch` | `-sub-` source targeting the default branch (GitLab CE auto-retarget misfire after a branch delete) → fix in stack mode, STOP with the command in label mode; target is another open queued MR → chain: STOP until the blocker merges, then STOP with `git fetch origin && git rebase --onto origin/BR <blocker merged sha> <child> && git push --force-with-lease origin <child>` |
| S2 up to date | `glab mr rebase IID` (never `--skip-ci` in `run`) | `rebase_in_progress diverged_commits_count detailed_merge_status merge_error has_conflicts` | in progress → WAIT (stuck > 10 min → STOP); conflict → FAIL (print local rebase commands); diverged > 0 or `need_rebase` → ACT (counts toward `max_retries`) then WAIT until done and re-read `sha`; rebase 403 → STOP with git commands |
| S3 checks | poll | `head_pipeline`, project `only_allow_merge_if_pipeline_succeeds`, `allow_merge_on_skipped_pipeline` | pipeline missing or `head_pipeline.sha != sha` → WAIT ≤ 3 polls then `require_checks` ? STOP "no pipeline on this head (CI rules filter on target branch?)" : S4; created/pending/running → S4-arm if pipelines-must-succeed else WAIT; success → S4; failed/canceled → FAIL; skipped → S4 iff allowed; manual → STOP |
| S4-arm (preferred) | `glab mr merge IID --auto-merge --sha <sha> --yes [--squash if mr.squash] [-d]` | `state merge_when_pipeline_succeeds detailed_merge_status` | armed → WAIT until merged; MWPS dropped (pipeline failed, new push) → S0 (retry); `need_rebase` → S2 |
| S4-merge (fallback: `merge_method == merge` or pipeline already green) | target branch `.commit.id` check, then `glab mr merge IID --auto-merge=false --sha <sha> --yes [--squash] [-d]` | | target moved → S2; 405/406 → map `detailed_merge_status`; 401/403 → FAIL "needs Maintainer on protected <target>; ask a maintainer to merge !IID" |
| S5 confirm | poll | `state` | merged → DONE; deadline → FAIL (print resume command) |

`detailed_merge_status` map: WAIT `checking unchecked preparing ci_still_running approvals_syncing`;
ACT `need_rebase` (S2) `ci_must_pass` (S3); STOP `draft_status discussions_not_resolved not_approved
requested_changes blocked_status external_status_checks status_checks_must_pass policies_denied
locked_paths`; FAIL `conflict broken_status not_open`; `mergeable` → merge now.
`merge_trains_enabled` on the project (Premium) → banner "native train available", `--auto-merge`
adds the MR to it, S4-merge is skipped.

## GitHub

Reads: `gh pr view N -R O/R --json state,isDraft,isCrossRepository,mergeable,mergeStateStatus,headRefOid,headRefName,baseRefName,autoMergeRequest,reviewDecision,labels,mergedAt`,
`gh repo view O/R --json deleteBranchOnMerge,autoMergeAllowed,squashMergeAllowed,rebaseMergeAllowed,mergeCommitAllowed,isPrivate,visibility,viewerPermission,defaultBranchRef`,
`gh api repos/O/R/rules/branches/BASE`, `gh api repos/O/R/branches/BASE/protection` (404 = none),
`gh api repos/O/R/compare/BASE...HEAD` (`.behind_by`).

| Step | Native command | Transitions |
|---|---|---|
| S0 load | `gh pr view` | MERGED → DONE; CLOSED → FAIL; draft → STOP (`gh pr ready N`); cross-repository → STOP (fork PRs are never stacked) |
| S1 base | `gh pr edit N -B BR` | `-sub-` head based on the default branch → fix/STOP as GitLab; chain → STOP; after blocker merge + branch delete GitHub retargets onto the blocker's base (good) but the child carries pre-squash commits → STOP with `git rebase --onto origin/BR <blocker headRefOid> <child>` |
| S2 up to date | `gh pr update-branch N [--rebase]` | CONFLICTING/DIRTY → FAIL; UNKNOWN → WAIT; `behind_by > 0` or BEHIND → ACT (retry counter); stderr `422 … already up to date` → fine; new `headRefOid` → S3 |
| S3 checks | `gh pr checks N --json bucket,state,name [--required if a rule lists required checks]` | no checks → `require_checks` ? STOP : S4; all pass → S4; a failure → FAIL; pending (exit 8) → WAIT (or S4 when the server gates the merge) |
| S4-queue (native) | `gh pr merge N --auto` (no strategy flag) when `rules/branches/BASE` has `merge_queue` | WAIT until MERGED; removed from queue → S0 (retry) |
| S4-arm | `gh pr merge N --auto --squash\|--rebase\|--merge --match-head-commit <headRefOid>` when protection + `autoMergeAllowed` | WAIT until MERGED; BEHIND/BLOCKED after target moved → S2; `reviewDecision` REVIEW_REQUIRED/CHANGES_REQUESTED → STOP |
| S4-merge (private Free, no protection) | compare `behind_by` then `gh pr merge N --squash --match-head-commit <headRefOid> [-d]` | behind → S2; head mismatch → S0 (retry); UNSTABLE → STOP unless `--allow-unstable` |
| S5 confirm | poll `state` | MERGED → DONE; deadline → FAIL |

Strategy: `squash` when allowed (the stack convention), else `rebase`, else `merge`.

## Branch deletion

On by default for parts with no open dependents (mirrors ticking "Delete source branch"; on
GitHub it is what retargets dependents); never for a chain blocker unless `--delete-blockers`;
`--keep-branches` disables it.

## Retries and resumption

Each rebase, update and re-arm counts toward `mq.max_retries`; beyond it the MR/PR fails with
"the target is busy". `mq run` keeps no local state: re-running it resumes from the live state
of every MR/PR, and an armed MR/PR merges server-side even if mq is interrupted.
