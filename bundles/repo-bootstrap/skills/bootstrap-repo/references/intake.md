# The standard intake

The source of truth is `scripts/questions.toml`, and `repoboot questions` resolves it against the answers given so far. This page explains what each answer drives.

| Id | Asked when | Drives |
|---|---|---|
| `repo.host` | always | `github` / `gitlab` / `local`: which remote steps run, and which templates (MR or PR, CI file, CODEOWNERS location) |
| `repo.name`, `repo.owner` | host is not local (name: always) | the slug `owner/name`, the SSH remote, `gh repo create` / `glab repo create` |
| `repo.server` | gitlab | the GitLab host (default `gitlab.host`); `glab api --hostname` |
| `repo.visibility` | host is not local | `--private` / `--internal` / `--public` |
| `repo.description` | always (optional) | README, create flags |
| `repo.license`, `.license_holder`, `.license_year` | always; holder and year with MIT or proprietary | `LICENSE`, README |
| `workflow.default_branch` | always | `git init -b`, the first push, protection, the CI trigger |
| `workflow.merge_method` | host is not local | GitHub: which merge methods are allowed. GitLab: `merge_method` and `squash_option` |
| `workflow.required_approvals` | host is not local | GitHub: the ruleset's pull-request rule. GitLab CE/Free: recorded in the spec and README only |
| `workflow.codeowners` | always (optional) | `CODEOWNERS`; on GitHub with approvals > 0, code-owner review is required |
| `workflow.tracker`, `.tracker_project` | always; project with jira | MR/PR template (ticket section), issue templates, the `.harness.toml` draft's `[repo] tracker/project` |
| `workflow.agent_labels` | host is not local | creates the `core.agent_labels` labels |
| `architecture.kind` | always | pack selection; README |
| `architecture.languages` | always (default: detected from marker files) | pack selection, `.gitignore` sections |
| `architecture.toolchain` | when languages are set | pack selection (`covers`) |
| `architecture.container`, `.deploy` | service/cli/other; deploy for most kinds | pack selection; README |
| `architecture.notes` | always (optional) | README; read by the skill when it writes a pack |
| `quality.precommit` | always | `.pre-commit-config.yaml`, the README's Development section |
| `quality.ci_jobs` | host is not local | CI file (`lint` = the pre-commit job; `test` / `build` come from packs); GitLab "pipelines must succeed" |
| `quality.required_checks` | github with CI | the ruleset's required status checks |
| `pack.<id>.<key>` | round 2, when the pack is selected | the pack's templates |

## Rounds

- **Round 1** covers the standard intake: identity, workflow, architecture and quality.
- **Round 2** covers the questions that only exist once round 1 is answered. These are mainly
  the selected packs' questions, plus any question whose `when` condition the round-1 answers
  just made true.

The skill asks at most two rounds. After that, every question still open takes its default,
and the skill says so.
