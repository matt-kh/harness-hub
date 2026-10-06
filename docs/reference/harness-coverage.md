# Reference: harness coverage

Which guides and sensors every public bundle contributes, after Martin Fowler's
[harness engineering](https://martinfowler.com/articles/harness-engineering.html) vocabulary:

- **Guides** (feedforward) steer the agent before it acts: rules, skills, permission lists,
  agent definitions, templates.
- **Sensors** (feedback) detect at or after the action: guard sections (computational, before a
  shell command runs), doctor checks, tests, lint rules, review agents (inferential).

Each bundle declares both in the `[harness]` section of its `bundle.toml`
(`guides`, `sensors`, `coverage_note`; see [ARCHITECTURE §3](../../ARCHITECTURE.md#3-bundles-bundlesname)).
`harness lint` warns when a bundle has guides but no sensors (feedforward only), sensors but no
guides (feedback only), or no `[harness]` section at all; a `ref` that names nothing in the
bundle is an error. The last column is the bundle's own statement of what the pairing does not
cover. Generated from `bundles/*/bundle.toml`; do not edit inside the generated region.

<!-- generated:begin source=bundles/*/bundle.toml#harness -->
| bundle | guides | guide kinds | sensors | sensor kinds | pairing | not covered |
|---|---|---|---|---|---|---|
| [core](../bundles/core.md#guides-and-sensors) | 4 | rule, permission, agent | 7 | guard, doctor, test, lint, review-agent | paired | The model policy in agents/Plan.md and agents/Auto.md is a guide only: no sensor checks which model a sub-agent ran on. |
| [gdoc](../bundles/gdoc.md#guides-and-sensors) | 3 | rule, skill, permission | 4 | guard, doctor, test | paired | The gdoc CLI itself has no unit suite; its write paths are covered by the guard rows. |
| [github](../bundles/github.md#guides-and-sensors) | 2 | rule, permission | 5 | guard, doctor, test | paired | Forks: the guard cannot read labels on a fork, so edits there ask instead of being label-gated. A PR created without -t (title from the commit or an editor) is not title-checked. |
| [gitlab](../bundles/gitlab.md#guides-and-sensors) | 2 | rule, permission | 5 | guard, doctor, test | paired | `--squash-before-merge` / `--remove-source-branch` and description sections are guides only (project defaults may already squash); an MR created without -t is not title-checked. |
| [jira](../bundles/jira.md#guides-and-sensors) | 3 | rule, skill, permission | 5 | guard, doctor, test | paired | The optional MCP server runs with READ_ONLY_MODE=true; no sensor inspects MCP calls. |
| [k8s](../bundles/k8s.md#guides-and-sensors) | 6 | rule, skill, permission, agent | 6 | guard, doctor, test | paired | The agents' read-only stance is enforced for shell commands by the guard; MCP or API access outside the shell is not sensed. |
| [ticket-workflow](../bundles/ticket-workflow.md#guides-and-sensors) | 3 | rule, skill | 5 | guard, doctor, test | paired | The size rubric, Q-checklist and MR body content are judgement calls (inferential: code-reviewer); SCM verb conventions are sensed by the gitlab/github guard sections; work-ticket has no own test suite yet. |
<!-- generated:end -->
