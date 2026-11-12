# Packs

A pack is a directory that holds `pack.toml` and the templates it names. Packs are read from:

1. the bundled `scripts/packs/` (only `baseline`);
2. each directory in `repo_bootstrap.pack_dirs`, or `HARNESS_REPO_BOOTSTRAP_PACK_DIRS` (paths separated by `:`), in order.

A pack with the same `id` as one read earlier replaces it. That is how an org changes the baseline: copy it, edit it, and keep the id `baseline`.

## pack.toml

```toml
[pack]
id = "python-svc"            # lower-case letters, digits, dashes
summary = "Python service on uv"
order = 20                   # render order; baseline is 0, a later pack's file replaces an earlier one's
always = false               # true: selected for every repository (like baseline)

[pack.match]                 # selected when EVERY key matches; a value or a list of accepted values
"architecture.languages" = "python"   # list answers match when they contain one of the values
"architecture.kind" = ["service", "cli"]

[pack.covers]                # further answers this pack handles (not reported as uncovered)
"architecture.toolchain" = "uv"

[[question]]                 # round 2; stored as pack.<id>.<id> in the spec
id = "python_version"
prompt = "Python version?"
type = "choice"              # string | choice | multi | list | bool | int
choices = ["3.11", "3.12", "3.13"]
default = "3.12"             # a template, e.g. "\{{ repo.name }}"
when = "architecture.container"
pattern = '^3\.[0-9]+$'
required = true

[[file]]
path = "src/{{ pack.python-svc.module }}/__init__.py"   # a template; must stay inside the repository
template = "files/init.py"                               # relative to the pack directory
when = "repo.host == gitlab"                             # optional condition

[[fragment]]                 # text added to a slot of another pack's template
slot = "gitlab_ci_jobs"
when = "quality.ci_jobs has test"
text = """
pytest:
  stage: test
  script: [uv run pytest]
"""                          # or template = "files/ci-test.yml"
```

## Template syntax

| Syntax | Meaning |
|---|---|
| `\{{ repo.name }}` | An answer. Lists are joined with `, `; booleans become `true` / `false`. |
| `\{{ fact.year }}`, `\{{ fact.dir_name }}`, `\{{ fact.languages }}` | Facts about the target directory. |
| `\{{ config.default_visibility }}`, `\{{ config.gitlab_host }}` | Bundle config. |
| `\{{ label.worked }}` | The agent labels (`worked` / `created` / `drafted`). |
| `\{{ derived.slug }}`, `\{{ derived.ssh_url }}`, `\{{ derived.web_url }}`, `\{{ derived.codeowners }}` | Values computed from the answers. |
| `{{#if COND}}…{{else}}…{{/if}}` | A condition. Supported forms: `A == v`, `A != v`, `A in a\|b`, `A has v`, `A`, `not A`, joined with `and` / `or`. |
| `{{#each LIST}}{{ . }}{{/each}}` | Repeats the block once per list item. |
| `{{slot NAME}}` | The fragments that packs added to the slot `NAME`, in pack order. |

When a block tag stands alone on its line, the whole line is removed. Runs of three or more newlines collapse to one blank line, and every file ends with exactly one newline. Output is deterministic: the same answers always render the same bytes.

## Baseline slots

| Slot | Where it goes |
|---|---|
| `gitignore` | extra `.gitignore` lines |
| `precommit_repos` | extra `repos:` entries of `.pre-commit-config.yaml`, as list items with 2-space indent |
| `gitlab_ci_jobs` | jobs of `.gitlab-ci.yml` (stages `lint`, `test`, `build`) |
| `github_ci_jobs` | jobs of `.github/workflows/ci.yml`, under `jobs:` with 2-space indent |
| `readme_development` | extra lines in the README's Development section |
| `mr_checklist` | extra checklist items in the MR/PR template |

## Writing one with the user

- Keep org values (hosts, groups, ticket formats) in the pack. They never belong in the hub's public checkout.
- Give every question a `default` where one is sensible, so the intake stays short.
- Name CI jobs after the checks you want required: on GitHub the job id is the check context listed in `quality.required_checks`.
- Test it in a scratch directory: run `repoboot answer --dir /tmp/x …`, then `repoboot plan --dir /tmp/x --text`. If anything stays open in the spec, `plan` reports it.
