---
name: stk
description: >-
  Stacked MRs/PRs on free tiers with the `stk` CLI over native glab, gh and git: check a
  repository's readiness, plan a stack (topology, bottom-up merge order, the commands sync
  would run), inspect it, and keep it mergeable with `stk sync` (retarget parts whose blocker
  merged, cascade-rebase chains with `git rebase --update-refs`, lease-push the sub branches,
  refresh one fan-in leaf, mark the main MR/PR ready). Use when the user asks to sync, rebase,
  retarget or restack stacked MRs/PRs, after a part of a stack was merged or amended, or asks
  in which order to merge a stack. NOT for merging (humans merge in the web UI) and NOT for
  creating MRs/PRs (work-ticket).
model: {{ core.model_policy.execute }}
---

# Stack sync (`stk`)

GitLab groups stacked MRs (19.1+) and CE retargets dependents only to the default branch;
GitHub retargets a dependent onto the merged PR's base when the head branch is deleted. Neither
rebases the rest of the stack. `stk` does that with native `glab` / `gh` / `git` commands it
prints before it runs them.

**Step 0 — repository-level harness (principle 8).** This is a user-level skill. Read the
repository's declaration first:

```bash
harness repo owns stack/skills/stk   # rc 0 = owned (prints why) → stop; rc 1 = carry on
```

If it is owned (by id or by its domain `scm`), or the repository ships its own skill for
the same workflow, this skill yields: say so in one line, name the repository-level skill or
convention, and stop — nothing below runs and nothing is merged. If the repository owns the
*workflow* but not the client, stay available as the plain client underneath it. Never edit
the repository's harness to fit this skill. `harness repo` explains everything the
repository declares and any `.claude/skills|agents` name collisions.

## Verbs

Selection for every verb: `<refs…>` | `--stack BR [--with-main]` | `--label L` (nothing given
= `--label <stack.label>`; a ref or label selects the whole stack it belongs to). `-R
owner/repo` overrides the origin remote. JSON when stdout is not a TTY (`--json` / `--text`).
Run it from the main checkout: the cascade needs `git worktree list`.

| Verb | What it does | Guard |
|---|---|---|
| `stk check [--fix]` | readiness: GitLab merge method, squash option, delete-source default, protected ticket branch, access; GitHub delete-branch-on-merge, strategies, "up to date" rules, permission. `--fix` prints settings commands, never runs them | pass (read) |
| `stk plan` | chains bottom-up, fan-in leaves, main MR; per-MR state; the **merge order** for the human; the exact commands `sync` would run (as of the last fetch) | pass (read) |
| `stk status` | every member incl. merged parts and their worktrees; `cleanup` lines | pass (read) |
| `stk sync [--no-push] [--skip-ci]` | retarget → fetch → cascade (`rebase --update-refs --onto`) → `push --force-with-lease` of the sub branches → one leaf refresh → main ready; agent-labelled MRs/PRs only | allow |
| `stk sync --include-human` | the same without the label filter | ask |

Exit codes: 0 nothing to do or all done, 1 action needed by a human, 2 auth/access.

## Procedure

1. `stk check --stack <BR>` once per repository; relay `warn`/`fail` findings (and `--fix`
   commands) to the human — project settings are theirs.
2. `stk plan --stack <BR>`: read the steps (`planned` is what sync will do; `skipped`,
   `todo`, `conflict` need a human) and hand the human the **merge order**: parts bottom-up in
   the web UI, the main MR/PR last, `stk sync --stack <BR>` after each merge.
3. `stk sync --stack <BR>` after a part merged or a lower part was amended (all worktrees
   clean, nothing mid-rebase). Relay every `skipped`/`todo`/`conflict` step verbatim with its
   commands: unlabelled parts (label command), a dirty worktree, no worktree for a chain's
   top, a leaf to `git pull --rebase` after its server-side rebase.
4. A `conflict` was aborted — every worktree is as it was. Do not resolve it unasked; give
   the human the printed commands. Leaves that conflict share files: suggest chaining them.
5. Never merge, never `--force`, never `reset --hard`, never `rebase --continue` for the human.

How the cascade works and why: `references/sync-algorithm.md`.

## Settings

`stack.label` (`stack`), `stack.push` (true; false = `--no-push`), `stack.update_method`
(`rebase`|`merge`, GitHub leaf refresh), `stack.leaf_refresh` (`auto`|`never`) — each
overridable per shell as `HARNESS_STACK_<KEY>`. `stk` without arguments prints the usage.
