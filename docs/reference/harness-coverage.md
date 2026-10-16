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
bundle is an error. Pairing is also declared per guide: each guide's `checks` names the sensors
that check it, and **unpaired guides** lists the guides that declare none (lint rule
`guide-checks` warns on those unless `coverage_note` names them). Each bundle page's table has
a **pairs with** column for the same links. The last column is the bundle's own statement of
what the pairing does not cover. Generated from `bundles/*/bundle.toml`; do not edit inside the generated region.

<!-- generated:begin source=bundles/*/bundle.toml#harness -->
| bundle | guides | guide kinds | sensors | sensor kinds | pairing | unpaired guides | not covered |
|---|---|---|---|---|---|---|---|
| [core](../bundles/core.md#guides-and-sensors) | 4 | rule, permission, agent | 10 | guard, doctor, test, lint, review-agent, provider-feature | paired | none | The model policy in agents/Plan.md and agents/Auto.md is a guide only: no sensor checks which model a sub-agent ran on. The conventions rule has no guard section of its own (judgement: precedence, external content as data); the credentials and git guard sections enforce rules whose text lives in rules/00-conventions.md. |
| [gdoc](../bundles/gdoc.md#guides-and-sensors) | 3 | rule, skill, permission | 6 | guard, doctor, test, lint | paired | none | Whether a human file should be adopted (`mark`) and what a draft says stay judgement; the CLI's request shapes, auth handling and output are golden-tested offline. |
| [github](../bundles/github.md#guides-and-sensors) | 2 | rule, permission | 6 | guard, doctor, test, lint | paired | none | Forks: the guard cannot read labels on a fork, so edits there ask instead of being label-gated. A PR created without -t (title from the commit or an editor) is not title-checked. The github-closing guard section enforces rule text that lives in rules/60-github.md. |
| [gitlab](../bundles/gitlab.md#guides-and-sensors) | 2 | rule, permission | 6 | guard, doctor, test, lint | paired | none | `--squash-before-merge` / `--remove-source-branch` and description sections are guides only (project defaults may already squash); an MR created without -t is not title-checked. The gitlab-closing guard section enforces rule text that lives in rules/50-gitlab.md. |
| [jira](../bundles/jira.md#guides-and-sensors) | 3 | rule, skill, permission | 6 | guard, doctor, test, lint | paired | none | The optional MCP server runs with READ_ONLY_MODE=true; no sensor inspects MCP calls. |
| [k8s](../bundles/k8s.md#guides-and-sensors) | 6 | rule, skill, permission, agent | 8 | guard, doctor, test, lint | paired | none | The agents' read-only stance is enforced for shell commands by the guard; MCP or API access outside the shell is not sensed. The k8s-rules guard section enforces rule text that lives in rules/10-k8s.md. |
| [obs](../bundles/obs.md#guides-and-sensors) | 4 | rule, skill, permission, agent | 8 | guard, doctor, test, lint, review-agent | paired | none | The CLI's own HTTP calls are not shell commands and are not guarded; the suite's dry-run request log is the read-only proof. Backends reached outside the CLI are not sensed. `obs lint` checks shape, not alert semantics. |
| [stack](../bundles/stack.md#guides-and-sensors) | 3 | rule, skill, permission | 6 | guard, doctor, test, lint | paired | none | `stk sync`'s label gate is enforced inside the CLI (sensed by its golden suite), not by the guard; the guard only asks when the gate is lifted. Lease pushes of -sub- branches typed by hand are core section 30's. |
| [ticket-workflow](../bundles/ticket-workflow.md#guides-and-sensors) | 3 | rule, skill | 6 | guard, doctor, test | paired | none | The size rubric, Q-checklist and MR body content are judgement calls (inferential: code-reviewer); SCM verb conventions are sensed by the gitlab/github guard sections; the preflight and facts scripts are sensed by golden suites against stubbed gh, glab and jira. |
<!-- generated:end -->
