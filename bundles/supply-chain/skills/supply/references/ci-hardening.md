# CI hardening rubric (`supply ci`)

`supply ci FILE...` reads GitHub Actions workflows and actions, `.gitlab-ci.yml` and the files
it includes, Dockerfiles, compose files and shell scripts, and reports the CI rules below plus
the pin rules `GHA*`, `CI006`, `CI008`, `CI009`, `SH001`, `SH002` and `REG001`
([pinning.md](pinning.md)). Severities are the CLI's; agents never invent one. A rule is
silenced only with `--ignore RULE,...` on the command line and the reason in the MR/PR
description — never with a comment in the workflow; `--ignore` takes any rule id and an unknown
one lists them all. When no file given could be scanned (every one is `CI000`), `supply ci`
exits 3: unscanned is not clean.

| Rule | Severity | Matches | Fix |
|---|---|---|---|
| CI000 | info | a file the line model refuses (tab indentation), a YAML file that is not a workflow, or a file of no known kind; it was **not scanned** (a file under `.github/workflows/` is always read as a workflow, whatever its name) | indent with spaces, or check it with its own tool (actionlint, the GitLab CI lint) |
| CI001 | warn | a GitHub workflow with no top-level `permissions:` while a job also has none | `permissions: contents: read` at the top, widen per job |
| CI002 | crit / warn | `permissions: write-all` at the top or on a job (crit); a top-level scope set to `write` (warn) | the scopes a job needs, at job level |
| CI003 | crit | a `pull_request_target` workflow that checks out the pull request head: `actions/checkout` with `ref:` on `github.event.pull_request.head.*`, `github.head_ref`, `refs/pull/…`; in `run:`, `gh pr checkout X`, or `git fetch\|checkout\|pull\|switch` with `pull/…`, `github.event.pull_request.head…` or `github.head_ref` among **that git command's own arguments** (the line is split on `&&`, `;` and `\|`: an `echo` of the ref after a `git fetch origin main` is not a finding) | use `pull_request`, or split into an untrusted `pull_request` workflow and a `workflow_run` one with no checkout of the head |
| CI004 | crit / warn | GitHub: an attacker-controlled expression expanded inside `run:` or `actions/github-script` `script:` — `github.event.(issue\|pull_request\|discussion).(title\|body)`, `…(comment\|review\|review_comment\|discussion_comment).body`, `pull_request.head.(ref\|label\|repo.default_branch)`, `head_commit.message\|author.*`, `commits[*].message\|author.*`, `workflow_run.head_branch\|head_commit.*`, `pages[*].page_name`, `github.head_ref` (crit); a free-text input `inputs.X` / `github.event.inputs.X` — `type: string` under `on.workflow_call.inputs` or `on.workflow_dispatch.inputs` (a dispatch input without a type is a string), or any input of an action — (warn: only someone who can run the workflow sets it; `choice`, `boolean` and `number` inputs are never findings). GitLab: `$CI_COMMIT_MESSAGE`, `$CI_COMMIT_TITLE`, `$CI_COMMIT_BRANCH`, `$CI_MERGE_REQUEST_TITLE` and similar inside `eval`, `sh -c` or `bash -c` (warn) | pass the value through `env:` and quote the variable: `env: TITLE: ${{ … }}` then `"$TITLE"` |
| CI005 | warn | a secret printed (`echo\|printf\|cat … ${{ secrets.X }}`, `${{ toJSON(secrets) }}`; GitLab `echo $…TOKEN\|PASSWORD\|SECRET…`) or the environment dumped (`env`, `printenv`, `set`, `export -p`); `::add-mask::` lines are not findings | never print secrets; pass them as env to the step that needs them |
| CI007 | warn | a security job or step (audit, osv, scan, codeql, semgrep, trivy, grype, snyk, gitleaks, dependency review or scanning, SAST/DAST, SBOM, cosign, attest…) with `continue-on-error: true` or `allow_failure: true` | let it fail the pipeline and triage the findings |

Severity guide for the human: a `crit` here is exploitable by anyone who can open an issue, a
pull request or a commit message; a `warn` widens the blast radius of another weakness.
