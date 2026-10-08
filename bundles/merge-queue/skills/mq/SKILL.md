---
name: mq
description: >-
  Merge trains / merge queues on free tiers with the `mq` CLI over native glab, gh and git:
  check a repository's readiness, plan the ordered queue of a stack (`--stack BR`), a label or
  explicit MR/PR numbers, inspect it, and prepare agent-labelled MRs/PRs with `mq sync`
  (retarget misfires, server-side rebase of the queue head, main ready once every part merged).
  Use when the user asks to merge a stack bottom-up, run or plan a merge train or merge queue,
  rebase stacked parts, or asks what is left to merge in a stack. NOT for merging itself
  (`mq run` is the human's command; hand it over) and NOT for creating MRs/PRs (work-ticket).
model: {{ core.model_policy.execute }}
---

# Merge queue (`mq`)

GitLab merge trains, merged-results pipelines and MR dependencies are Premium; GitHub's merge
queue and auto-merge need a public repository or a paid plan. `mq` recreates the train with
free-tier features, one MR/PR at a time, using only native `glab` / `gh` / `git` commands that
it prints before it runs them.

**Step 0 — repository-level harness (principle 8).** This is a user-level skill. Read the
repository's declaration first:

```bash
harness repo owns merge-queue/skills/mq   # rc 0 = owned (prints why) → stop; rc 1 = carry on
```

If it is owned (by id or by its domain `scm`), or the repository ships its own skill for
the same workflow, this skill yields: say so in one line, name the repository-level skill or
convention, and stop — nothing below runs and nothing is merged. If the repository owns the
*workflow* but not the client, stay available as the plain client underneath it. Never edit
the repository's harness to fit this skill. `harness repo` explains everything the
repository declares and any `.claude/skills|agents` name collisions.

## Verbs

Selection for every verb: `<refs…>` (queue order as given) | `--stack BR [--with-main]` (the
parts `BR-sub-NN-*` by NN; `--with-main` appends BR's own MR/PR) | `--label L` (open MRs/PRs
carrying L, by number; nothing given = `--label <mq.label>`). `-R owner/repo` overrides the
origin remote. JSON when stdout is not a TTY (`--json` / `--text` force it).

| Verb | What it does | Guard |
|---|---|---|
| `mq check [--fix]` | repository readiness (merge method, pipelines-must-succeed, skipped pipelines, squash, delete-source default, your access, merge trains, CI rules; GitHub visibility, rulesets/merge queue, protection, auto-merge, delete-branch-on-merge, strategies, permission, workflows). `--fix` prints the settings commands, never runs them | pass (read) |
| `mq plan` | the ordered queue, each MR/PR's state and the exact native commands the train would run next | pass (read) |
| `mq status` | every member incl. merged parts; `cleanup` lines for merged parts whose worktree still exists | pass (read) |
| `mq sync [--skip-ci]` | agent-labelled MRs/PRs only: retarget a `-sub-` part aimed at the default branch (stack mode), rebase **only the head of the queue** server-side, mark the main MR/PR ready once every part merged; unlabelled ones are listed with the label command | allow |
| `mq sync --include-human` | the same without the label filter | ask |
| `mq run` | the train: merges | ask — **the human runs it** |

Exit codes: 0 all merged or mergeable, 1 action needed, 2 auth/access, 3 the train stopped.

## Procedure

1. `mq check` once per repository; relay `warn`/`fail` findings (and `mq check --fix`'s
   commands) to the human — project settings are theirs to change.
2. `mq plan --stack <BR>` (or the refs / label the user named). Read every row's `next`:
   `act` is what the train will do, `wait` is fine, `stop`/`fail` need the printed commands
   first (draft, conflict, failed pipeline, chained part, missing Maintainer).
3. `mq sync --stack <BR>` when parts are agent-labelled: it fixes retarget misfires and
   rebases the queue head. After a server-side rebase run the printed
   `git -C ../<repo>_<sub> pull --rebase origin <sub>` in that worktree (never `reset --hard`).
   Unlabelled MRs/PRs: tell the user, with the printed label command.
4. Hand over, verbatim: "run `mq plan --stack <BR>` then `mq run --stack <BR>` in your
   terminal". Never run `mq run` yourself and never work around the ask.
5. Afterwards `mq status --stack <BR>` shows what merged and which worktrees to remove.

Chained parts (one part targets another's branch) stop the train with the exact
`git rebase --onto` + `git push --force-with-lease` commands once the blocker merged; mq
never force-pushes. The state machine and every transition: `references/state-machine.md`.

## Settings

`mq.label` (`merge-queue`), `mq.poll_seconds` (20), `mq.timeout_minutes` (90),
`mq.on_failure` (`stop`|`skip`; a stack always stops), `mq.update_method` (`rebase`|`merge`,
GitHub), `mq.require_checks` (true), `mq.max_retries` (3) — each overridable per shell as
`HARNESS_MQ_<KEY>`. `mq` without arguments prints the full usage.
