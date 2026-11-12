# Bundle: repo-bootstrap

This bundle gives every repository the same starting point, whether it is new or already exists, local or on GitHub or GitLab. `/bootstrap-repo` (the `repoboot` CLI) works in three layers. A later layer wins over an earlier one.

1. **The baseline pack** (bundled). It writes:
   - the hygiene files: `.gitignore`, `.gitattributes`, `.editorconfig`;
   - a README;
   - MR/PR and issue templates that mention tickets but never close them;
   - CODEOWNERS and a license;
   - `.pre-commit-config.yaml`;
   - a CI lint job.
2. **Your packs** (`repo_bootstrap.pack_dirs`). These hold the architecture-specific parts: service skeletons, test and build CI jobs, extra hooks, an org MR template, and their own questions. A pack is selected by the answers it `match`es. Keep org packs in a private overlay, never in the public checkout.
3. **The answers**, kept in the repository's `.repo-standard.toml`. They come from the **standard intake**: `repoboot questions` lists only what is still open (host, owner, visibility, default branch, merge method, approvals, code owners, tracker, project kind, languages, toolchain, CI jobs…), plus the questions of the selected packs. The skill asks them in at most two rounds.

**New repository.** `repoboot plan` shows every file and the exact git, gh and glab commands. Then `repoboot apply` runs them; the guard asks first. The steps:

1. `git init -b <branch>`;
2. the initial commit;
3. `gh repo create` or `glab repo create`;
4. the first push, made only after `git ls-remote` shows the remote has no branches;
5. the merge settings;
6. default-branch protection: a GitHub ruleset, or a GitLab protected branch;
7. the `agent-*` labels.

The `.harness.toml` is printed as a draft for you to review and commit.

**Existing repository.** `repoboot check --fix` reports where the repository differs from the standard. File changes are rendered on a branch and delivered through an MR/PR (`render` refuses the default branch). Remote settings are aligned by `apply` once you have seen the plan.

| | GitHub | GitLab (CE included) |
|---|---|---|
| Merge settings | only the chosen method; delete head branches; no auto-merge | `merge_method`, `squash_option`, pipelines must succeed (with CI), threads resolved, `remove_source_branch_after_merge` |
| Protection | ruleset `repo-standard`: PRs with N approvals, no force-push or deletion, required checks | push no one, merge maintainers, no force-push |
| Plan limits | rulesets on private repositories need Pro/Team/Enterprise: a 403 is a warning | required approvals are Premium: recorded only |

With the `stack` bundle active, `remove_source_branch_after_merge` defaults to off. The reason: GitLab CE retargets the dependents of a merged part to the default branch when the part's branch is deleted (see [stack](stack.md)). Set `repo_bootstrap.gitlab_remove_source_branch` to override this.

## Troubleshooting

- **`BLOCKED: … already exists and has branches`.** `apply` never pushes into a remote that has history. Clone it and run `/bootstrap-repo` in the checkout; it then plans drift fixes instead.
- **`failed git ls-remote --heads origin: the remote is not empty`.** Someone pushed between the plan and the push, or the API's "empty" was stale. Nothing was pushed or configured. Empty the remote or clone it. Running `apply` again resumes after the initial commit.
- **`warn … rulesets on a private repository need GitHub Pro…`.** This is the Free plan. Protect the branch by hand, make the repository public, or upgrade. The other steps ran.
- **`the spec … leaves questions open`.** Run `repoboot questions --text`, then `repoboot answer KEY=VALUE` (or `--accept-defaults`).
- **`repo_bootstrap.pack_dirs: … is not a directory`.** Fix the config with `harness config set repo_bootstrap.pack_dirs '[…]'` and run `harness apply`.
- **A pack does not show up.** Its `[pack.match]` keys must all match the answers. Check them with `repoboot answer --dir /tmp/x …` followed by `repoboot plan --dir /tmp/x --text`. `uncovered` lists the answers that no pack matches.
- **`no GitLab server`.** Answer `repo.server=<host>`, or set `gitlab.host`.

<!-- generated:begin source=bundles/repo-bootstrap/bundle.toml -->
## Summary

Bootstrap git repositories to a standard, locally and on GitHub or GitLab: a standard intake, architecture packs, and `repoboot` (questions, answer, plan, render, apply, check)

One standard for new and existing repositories. `repoboot questions` is the standard intake:
every requirement still open (host, owner, visibility, default branch, merge method,
approvals, code owners, tracker, project kind, languages, toolchain, CI jobs…) plus the
questions of the packs the answers select; `repoboot answer` keeps the answers in the
repository's `.repo-standard.toml`. The bundled baseline pack writes the hygiene files, README,
MR/PR and issue templates, CODEOWNERS, license, pre-commit config and a CI lint job; org and
personal packs (`repo_bootstrap.pack_dirs`) add architecture-specific files, CI jobs and
questions. `repoboot apply` initialises, commits, creates the GitHub repository or GitLab
project, makes the first push only into an empty remote, and applies the merge settings,
default-branch protection and agent-* labels (the guard asks). On an existing repository
`repoboot check --fix` reports the drift with the fixing commands; files change through an
MR/PR, never on the default branch. It never writes `.harness.toml` (it prints the draft).

- **Depends on:** `core`
- **Recommends:** `ticket-workflow`
- **Needs one of:** `gitlab`, `github`
- **Stability:** experimental
- **Domain / posture:** scm / label-gated

## Components

Stable ids derived from the path, with their [taxonomy](../reference/taxonomy.md) facets (domain shown only where it differs from the bundle's). All bundles: [catalog](../catalog.md).

**Skills**

- `repo-bootstrap/skills/bootstrap-repo` — control: guide · function: setup · posture: label-gated · model: execute · yields: declaration

**Rules**

- `repo-bootstrap/rules/67-repo-bootstrap` — control: guide · function: govern · yields: text

**Guard sections**

- `repo-bootstrap/guard.d/67-repo-bootstrap` — control: sensor · function: govern · decisions: ask 1 · yields: declaration

**Permission lists**

- `repo-bootstrap/permissions` — control: guide · function: govern · decisions: allow 5 · yields: config

**CLIs**

- `repo-bootstrap/bin/repoboot` — function: client · posture: label-gated · yields: n/a

**Doctor checks** (function: setup · posture: read-only; table below): `repo-bootstrap/doctor/repoboot-cli`, `repo-bootstrap/doctor/repoboot-scm-cli`

**Manual steps** (function: setup; table below): `repo-bootstrap/steps/repo-bootstrap-packs`

## Requirements

### Binaries

| binary | min version | install | optional | why |
|---|---|---|---|---|
| `gh` | 2.60.0 | `harness install gh` | yes | GitHub: `gh repo create`, `gh api` (settings, rulesets, reads), `gh label create\|list`. |
| `git` | 2.28 |  | no | `git init -b <branch>` (2.28+), the initial commit and push, `git ls-remote` before the first push. |
| `glab` | 1.40.0 |  | yes | GitLab: `glab repo create`, `glab api` (settings, protected branches, reads), `glab label create`. |
| `python3` | 3.9 |  | no | The repoboot CLI is stdlib python (TOML via tomllib, or the hub's vendored tomli below 3.11). |

### Configuration

| key | type | required | default | description |
|---|---|---|---|---|
| `repo_bootstrap.default_license` | string | no | `"none"` | Default answer to repo.license; other licenses come from a pack. HARNESS_REPO_BOOTSTRAP_DEFAULT_LICENSE. |
| `repo_bootstrap.default_merge_method` | string | no | `"squash"` | Default answer to workflow.merge_method. HARNESS_REPO_BOOTSTRAP_DEFAULT_MERGE_METHOD. |
| `repo_bootstrap.default_visibility` | string | no | `"private"` | Default answer to repo.visibility. HARNESS_REPO_BOOTSTRAP_DEFAULT_VISIBILITY. |
| `repo_bootstrap.github_owner` | string | no | `""` | Default GitHub owner (user or organisation) for repo.owner. HARNESS_REPO_BOOTSTRAP_GITHUB_OWNER. |
| `repo_bootstrap.gitlab_namespace` | string | no | `""` | Default GitLab group or namespace path for repo.owner. HARNESS_REPO_BOOTSTRAP_GITLAB_NAMESPACE. |
| `repo_bootstrap.gitlab_remove_source_branch` | string | no | `"auto"` | GitLab project default `remove_source_branch_after_merge`. auto: false when the stack bundle is active (GitLab CE retargets a deleted blocker's dependents to the default branch), true otherwise. HARNESS_REPO_BOOTSTRAP_GITLAB_REMOVE_SOURCE_BRANCH. |
| `repo_bootstrap.pack_dirs` | array | no | `[]` | Extra pack directories (each holds <pack>/pack.toml), searched after the bundled baseline; a later directory replaces a pack of the same id. Org packs live in a private overlay. HARNESS_REPO_BOOTSTRAP_PACK_DIRS (':'-separated) wins. |
| `repo_bootstrap.required_approvals` | integer | no | `1` | Default answer to workflow.required_approvals (GitHub: enforced by the default-branch ruleset; GitLab CE/Free: recorded only). HARNESS_REPO_BOOTSTRAP_REQUIRED_APPROVALS. |

### Secrets (never in harness.toml)

_none_

## Manual steps

<a id="repo-bootstrap-packs"></a>

### repo-bootstrap-packs — Optional: point repo_bootstrap.pack_dirs at your architecture packs

*once per machine · needs nothing but a terminal · ~10 min*

**Why:** The bundled baseline is architecture-neutral; your org's or your own layouts (service skeletons, CI jobs, MR templates with a ticket section) live in packs you keep in a private overlay.

**How:**

1. Create a directory outside the public checkout, e.g. `~/harness-hub/local/repo-packs/`.
2. Add one sub-directory per pack with a `pack.toml` (format: the skill's `references/packs.md`;
   copy the bundled `baseline` pack as a start). A pack of the same id as a bundled one replaces it.
3. `harness config set repo_bootstrap.pack_dirs '["~/harness-hub/local/repo-packs"]'` and `harness apply`.
4. `repoboot questions --dir /tmp/x` lists the pack's questions once your answers select it.

**Verify:** `true` (exit 0)

## Doctor checks

| id | severity | offline | fix |
|---|---|---|---|
| `repoboot-cli` | fail | runs | `harness apply (and fix repo_bootstrap.pack_dirs if the message names it)` |
| `repoboot-scm-cli` | warn | runs | `Activate the github or gitlab bundle (hub.bundles) and run harness apply; local-only bootstraps work without one` |

## Guides and sensors

Guides steer the agent before it acts; sensors detect at or after the action. Pairing: **paired**; guides with a declared check: 3 of 3.

| side | kind | ref | note | pairs with |
|---|---|---|---|---|
| guide | rule | `rules/67-repo-bootstrap.md` | bootstrap through repoboot: intake, plan, apply (asks); existing repositories through check and an MR/PR | `guard.d/67-repo-bootstrap.sh` |
| guide | skill | `skills/bootstrap-repo` | the standard intake in at most two rounds, packs, plan review, apply, .harness.toml hand-off, retrofit | `skills/bootstrap-repo/scripts/tests/run.sh`, `doctor_checks` |
| guide | permission | `permissions.toml` | repoboot questions\|answer\|plan\|render\|check allowed; apply is not (the guard asks); never Bash(repoboot:*) | `permissions-vs-guard`, `guard.d/67-repo-bootstrap.sh` |
| sensor | guard | `guard.d/67-repo-bootstrap.sh` | repoboot apply asks, however it is wrapped | `rules/67-repo-bootstrap.md`, `permissions.toml` |
| sensor | doctor | `doctor_checks` | the repoboot CLI and its packs, an SCM CLI | `skills/bootstrap-repo` |
| sensor | test | `tests/run.sh` | this bundle's rows against core + repo-bootstrap only, then the repoboot suite | — |
| sensor | test | `guard.d/tests.sh` | rows for section 67 incl. bypasses and repository ownership | — |
| sensor | test | `skills/bootstrap-repo/scripts/tests/run.sh` | golden scenarios for every verb against stubbed gh, glab and harness and a real-git sandbox, plus invariants (plans write nothing, a non-empty remote is never pushed to, no .harness.toml, no force-push) | `skills/bootstrap-repo` |
| sensor | lint | `permissions-vs-guard` | each Bash allow/deny rule of permissions.toml run through the guard: no allowed command the guard denies or asks, no denied one it allows | `permissions.toml` |

**Not covered:** The CLI's own invariants (the first push only into an empty remote, never on the default branch of an existing repository, never .harness.toml, never a force-push) are sensed by its golden suite; the guard asks on `repoboot apply`, and hand-typed gh/glab/git writes stay with the github, gitlab and core sections.

## Uninstall

Kept on uninstall: _nothing_

Removes the repoboot link, the rendered skill, the rule block and guard section 67; repositories, their .repo-standard.toml, remote settings, rulesets, protected branches, labels and your pack directories are untouched.
<!-- generated:end -->
