# Principle 6 — Harness engineering

Part of [PRINCIPLES.md](../PRINCIPLES.md). Read this before adding or changing anything a
bundle ships: rules, skills, permissions, agents, guard sections, doctor checks, tests.

## Statement

> Each harness bundle should, as much as possible, follow the best practices of
> <https://martinfowler.com/articles/harness-engineering.html>

- The article frames an agent as model plus harness, and the outer harness as what users
  build. Its two goals: make the agent more likely to get it right the first time, and give
  it a feedback loop that corrects it when it does not.
- This repo adopts its vocabulary and practices; the summary below is a paraphrase.

## Vocabulary (from the article, applied here)

- **Guide** — a feedforward control that steers before the agent acts: rules, skills,
  permission lists, agent definitions, templates.
- **Sensor** — a feedback control that detects after or at the action: the command guard,
  doctor checks, tests, linters, review agents.
- **Computational** — deterministic, fast, cheap enough to run on every change (guard, lint,
  tests, doctor). **Inferential** — semantic, slower, non-deterministic (a code-review agent).
- **Steering loop** — when an issue recurs, a human improves the harness (often with an agent
  drafting the rule, check or doc), so it does not recur.

## Rationale

- Guides alone are hopes: nothing confirms they were followed. Sensors alone are noisy: the
  agent repeats the mistake and is caught each time. Pairs work.
- Cheap computational checks belong as early as possible; the earlier a problem is found,
  the cheaper it is to fix. Inferential checks go where judgement is needed.
- A harness is maintained, not configured once. The repo must make maintenance routine.

## What it means in this repo

- **Every bundle declares its guides and sensors** in `bundle.toml`:
  `[harness] guides = [{kind, ref, note}]`, `sensors = [{kind, ref, note}]` and a
  `coverage_note`. Guide kinds: `rule`, `skill`, `permission`, `agent`, `template`.
  Sensor kinds: `guard`, `doctor`, `test`, `lint`, `review-agent`.
- **The docs render a "Guides and sensors" table** for each bundle in its generated region
  (`harness docs generate`).
- **Pairing.** A rule in `rules/NN-*.md` that a guard section can check has that section; a
  guard section has rule text that explains it to the agent before it acts.
- **Sensor messages are written for the agent.** Every guard deny or ask reason states the
  alternative ("…; push a branch and open a PR"), so the message itself steers the next
  attempt. Doctor FAILs name the step that fixes them.
- **The guard is a computational sensor that fires before the action**, on enforced and
  partial providers; on advisory providers only the guides apply, and the
  [capability matrix](../docs/reference/capability-matrix.md) says so.
- **Keep quality left.** Guard rows and lint run in pre-commit and CI; the code-reviewer agent
  (core) is the inferential sensor used after the change.
- **Variety reduction.** One manifest shape, one guard engine, one template syntax, fixed
  numeric prefixes. A small, fixed topology is what makes coverage checkable.
- **Ambient affordances.** `harness doctor`, `harness steps --pending`, `harness status
  --matrix` and `harness config explain` make the environment legible to agent and human.

## Anti-patterns and the repo's counter

| Anti-pattern | Counter here |
|---|---|
| Feedforward only (rules never validated) | lint warns on guides without sensors |
| Feedback only (same mistake caught repeatedly) | lint warns on sensors without guides |
| Silent sensor (no fire mistaken for success) | guard fails closed on malformed input; guard rows assert each decision; doctor reports `SKIP` explicitly |
| Incoherence (guides and sensors contradict) | rule text and guard sections live in the same bundle and the same PR; hook policy is generated from `# rule:` comments |
| Template degradation | versioned manifests, CHANGELOG Migration paragraphs, `docs check` for staleness |
| Over-trust in agent-written tests | guard rows are reviewed as the specification; goldens are reviewed as diffs |

## How it is checked

| Check | Kind | Where |
|---|---|---|
| Bundle has guides but no sensors, or sensors but no guides | lint warning | `harness lint` |
| A `# rule:` reason in `guard.d` has no alternative | lint warning | `harness lint` |
| A component is unclassified, or its [taxonomy](../docs/reference/taxonomy.md) facets contradict its kind | lint warning / error | `harness lint` (rule `taxonomy`) |
| Every guard decision has test rows, including bypass attempts | tests | `bundles/*/guard.d/tests.sh` |
| Generated "Guides and sensors" tables are current | docs | `harness docs check` |
| PR states the pairing was checked | review | [PR template](../.github/PULL_REQUEST_TEMPLATE.md) |

## Tensions and how they are resolved

- **With principle 1 (lightweight).** Sensors cost code. Resolution: prefer extending an
  existing sensor (a guard row, a doctor check) over a new mechanism.
- **With principle 2 (developer-first).** Too many sensors become friction. Resolution: a
  sensor that fires often on legitimate work is a bug in the sensor; fix its pattern or its
  message through the steering loop.
- **"As much as possible."** Some guides have no computational check (judgement calls in a
  skill). Resolution: say so in `coverage_note`, and pair them with an inferential sensor
  where one exists.

## Examples

Compliant:

- A new rule "never print kubeconfig contents" shipped with a guard deny row and a test row.
- A deny reason: "reading credential files is denied; check auth with `gh auth status`".

Non-compliant:

- A skill that tells agents to avoid force pushes, with no guard rule or test behind it and
  no `coverage_note` explaining why.
- A doctor check that exits 0 when its command is missing.

## Open questions

- Drift detection outside the change lifecycle (a scheduled `doctor` or `sync` report).
- How to declare inferential sensors that live in provider features rather than the bundle.
