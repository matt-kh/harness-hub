# What the standard sets up

## Files (baseline pack)

| File | When |
|---|---|
| `.gitignore` | always: OS and editor files, `.env*` (but not `.env.example`), keys, logs, plus one section per detected or answered language; packs add to the `gitignore` slot |
| `.gitattributes`, `.editorconfig` | always: LF line endings, UTF-8, binary types |
| `README.md` | always: overview from the architecture answers, development, contributing (MR/PR flow, approvals, merge method, tracker), license |
| `.pre-commit-config.yaml` | `quality.precommit`: pre-commit-hooks (whitespace, EOF, YAML/TOML/JSON, merge conflicts, large files, private keys, LF) plus pack hooks |
| `.gitlab/merge_request_templates/Default.md` / `.github/pull_request_template.md` | GitLab / GitHub: ticket section (Jira key or `Issue: #N`, never a closing keyword), summary, testing, checklist |
| `.github/ISSUE_TEMPLATE/{bug,feature,config}.yml` | tracker `github-issues` |
| `.gitlab/CODEOWNERS` / `.github/CODEOWNERS` | code owners given |
| `LICENSE` | MIT or proprietary |
| `.gitlab-ci.yml` | GitLab with CI jobs: MR and default-branch pipelines; `pre-commit` job in stage `lint`; pack jobs in `test` / `build` |
| `.github/workflows/ci.yml` | GitHub with CI jobs: `pull_request` and pushes to the default branch; `lint` job; pack jobs |
| `.repo-standard.toml` | always: the answers (written by `repoboot answer`, committed with the rest) |

## Remote settings

| | GitHub | GitLab (CE included) |
|---|---|---|
| Create | `gh repo create OWNER/NAME --private\|--internal\|--public` | `glab repo create NS/NAME --… --defaultBranch BR` |
| First push | `git push -u origin BR`, only if `git ls-remote --heads origin` is empty | same |
| Merge settings | `delete_branch_on_merge=true`, `allow_auto_merge=false`; only the chosen method is allowed (squash: PR title and body make the commit message) | `merge_method` (merge or ff), `squash_option` (always / default_off / never), `only_allow_merge_if_pipeline_succeeds` (when CI jobs exist), `only_allow_merge_if_all_discussions_are_resolved=true`, `remove_source_branch_after_merge` (off with the stack bundle) |
| Default-branch protection | ruleset `repo-standard` on `~DEFAULT_BRANCH`: no deletion, no force-push, pull requests with N approvals, stale reviews dismissed, threads resolved, code-owner review when owners exist and N > 0, required checks. On a Free-plan private repository it returns 403 and is reported as a warning | protected branch: push no one, merge maintainers, no force-push. Required approvals are a Premium feature, so they are only noted |
| Labels | `core.agent_labels` (worked / created / drafted) via `gh label create` | via `glab label create` |
| `.harness.toml` | drafted from `harness repo init` with `[repo] name/tracker/project` filled in; the human reviews and commits it | same |

`repoboot check` compares the same settings on an existing remote. Each difference is a `warn` finding, and `--fix` attaches its command. Existing settings are only changed through `apply`, after the user has seen the plan.
