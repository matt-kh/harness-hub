---
name: bootstrap-repo
description: >-
  Bootstrap a git repository to a standard, locally or on GitHub / GitLab, with the `repoboot`
  CLI. It runs the standard intake (the questions still open, plus those of the architecture
  packs the answers select) and keeps the answers in `.repo-standard.toml`. It then renders the
  baseline and pack files, makes the initial commit, creates the remote and pushes into it only
  while it is empty, and applies the merge settings, default-branch protection and agent-*
  labels. It also retrofits existing repositories: drift report, file fixes through an MR/PR,
  remote fixes. Use when the user asks to create, init, set up, scaffold or bootstrap a repo /
  repository / project (GitHub or GitLab or local), to apply the repo standard or best
  practices to a repo, to check a repo against the standard, or to write an architecture pack.
  NOT for working a ticket in an existing repo (work-ticket) and NOT for writing the
  repository's .harness.toml (the human commits the draft).
model: {{ core.model_policy.execute }}
---

# Repository bootstrap (`repoboot`)

**Step 0 — repository-level harness (principle 8).** This is a user-level skill. Read the
repository's declaration first:

```bash
harness repo owns repo-bootstrap/skills/bootstrap-repo   # rc 0 = owned (prints why) → stop; rc 1 = carry on
```

If it is owned (by id or by its domain `scm`), or the repository ships its own skill for
the same workflow, this skill yields: say so in one line, name the repository-level skill or
convention, and stop — nothing below runs and nothing is merged. If the repository owns the
*workflow* but not the client, stay available as the plain client underneath it. Never edit
the repository's harness to fit this skill. `harness repo` explains everything the
repository declares and any `.claude/skills|agents` name collisions.

For a brand-new directory there is no declaration yet. The command prints `not inside a git checkout`; carry on.

## Verbs

Every verb takes `--dir DIR` (default `.`) and `--spec FILE` (default `DIR/.repo-standard.toml`). Output is JSON when stdout is not a TTY; `--text` gives a readable view for the user.

| Verb | What it does | Guard |
|---|---|---|
| `repoboot questions [--round 1\|2]` | The open questions, with resolved defaults, choices and help: the standard intake plus the questions of the selected packs. | pass (read) |
| `repoboot answer K=V… [--accept-defaults] [--infer]` | Validates and writes answers into the spec. `--infer` fills what the checkout already shows. An empty value removes an answer. | pass (local) |
| `repoboot plan` | Lists the packs, the uncovered answers and each file's status (create / same / differs). Gives the exact git, gh and glab commands `apply` would run, plus the `.harness.toml` draft. Remote checks are GETs only. | pass (read) |
| `repoboot render [--force]` | Writes the files: missing ones, plus differing ones with `--force`. Refuses on the default branch of an existing repository. | pass (local) |
| `repoboot apply [--force]` | New repository: init → commit → create → push into the empty remote → settings → protection → labels. Existing repository: the remote fix steps of `plan` only. | **ask** |
| `repoboot check [--fix]` | Compares the files and remote settings with the standard. `--fix` prints the commands; it runs nothing. | pass (read) |

Exit codes: 0 means done or nothing to do. 1 means a human is needed (open questions, a warning, a refusal). 2 means an authentication or access problem: check `gh auth status` or `glab auth status`.

## Procedure — new repository

1. **Facts.** Collect the target directory and the host the user named, plus what their message already answers. Record those answers with `repoboot answer K=V …` before asking anything. In an existing checkout without a spec, run `repoboot answer --infer` first.
2. **Intake, round 1.** Run `repoboot questions --round 1`. Ask the open questions in ONE `AskUserQuestion` call: at most 4 questions per call, so batch the rest in a second call and fold any remaining ones into a short list.
   - Questions that have a `default` are not asked one by one. List them as "I'll use these defaults: …" and offer one "change any?" choice.
   - Questions without a default, especially `required` ones, are always asked.
   - Use `choices` as options. Mark the default "(Recommended)" and put it first.
   - `architecture.*` decides which packs apply. Ask it plainly ("What kind of project? Which languages?") and never guess it from the name.
3. **Record** with `repoboot answer K=V …`, then `repoboot answer --accept-defaults` for the defaults the user accepted.
4. **Intake, round 2.** Run `repoboot questions` again. Answers can open new questions, and the selected packs add their own (ids `pack.<id>.<key>`). Ask them in one more call, then record them. **There are never more than two rounds.** Anything still open after that takes its default, and you say so.
5. **Uncovered architecture.** If `plan` lists `uncovered` answers, say plainly that no pack covers them and that only the baseline is used. Offer to write a pack ("Write a pack" below) before continuing, or to continue on the baseline. Never hand-write files outside a pack to fill the gap.
6. **Plan.** Run `repoboot plan --text` and show the user:
   - the file list;
   - the remote steps (create, push, settings, protection, labels);
   - the notes (Free-plan rulesets, GitLab approvals, `remove_source_branch` with the stack bundle).

   If the plan is `BLOCKED` (the remote already has branches, or origin differs), relay the message and stop.
7. **Apply.** Run `repoboot apply --text`; the guard asks.
   - `warn` results such as a GitHub Free private-repo ruleset are reported, not retried.
   - After a `failed` result, fix the cause and run `apply` again. It resumes after the initial commit.
8. **`.harness.toml`.** Show the `harness_toml_draft` and ask the user to review it and commit it in the first MR/PR, or keep it out. Never write it yourself (the guard asks on writes to it).
9. **Read back.** Run `repoboot check --dir DIR --text` and report the result. "Clean" means no `warn` and no `fail`.

## Procedure — existing repository (retrofit)

1. If the repository has no spec, run `repoboot answer --infer`. Then run the intake as above, but only for what is still open.
2. Run `repoboot check --fix --text` and relay the findings by group: files, settings, protection, labels.
3. **Files** go through an MR/PR, never onto the default branch:
   1. `git switch -c repo-standard`.
   2. `repoboot render`. For differing files, show the diff, then run `render --force` only for the ones the user accepts.
   3. Commit with `.repo-standard.toml` included.
   4. Open the MR/PR with the normal governance (`agent-worked` label, no closing keywords).
4. **Remote settings, protection and labels**: show the `remote` steps of `repoboot plan`, then run `repoboot apply` (it asks). If the CI file is not merged yet, apply the pipeline and required-check settings only after the MR/PR merges; `plan` adds a note when this applies.

## Write a pack

Packs hold the "specific architectures": org conventions, service skeletons, CI jobs and MR templates with a ticket section. They live in the user's `repo_bootstrap.pack_dirs`, never in the hub's public checkout. Read `references/packs.md`, then:

1. Ask what the architecture needs: files, the CI jobs per host, pre-commit hooks, and the questions a repository of that kind must answer. Ask in at most two rounds.
2. Write `<pack_dir>/<id>/pack.toml` and its `files/` templates. Set `match` on the answers that select it, for example `"architecture.languages" = "python"` and `"architecture.kind" = "service"`.
3. Check it: `repoboot answer --dir /tmp/x …` with matching answers, then `repoboot plan --dir /tmp/x --text`.

## References

- `references/intake.md`: the standard questions and what each one drives.
- `references/standard.md`: what the baseline writes and which remote settings each host gets.
- `references/packs.md`: the pack format, the template syntax and the slots.
