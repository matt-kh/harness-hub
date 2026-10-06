# Principle 2 — Developer-first

Part of [PRINCIPLES.md](../PRINCIPLES.md). Read this before adding a bundle, a guard rule, a
manual step or a user-facing message.

## Statement

> This repo is developer-first; the harnesses are mainly built for developer workflows
> encompassing all software engineering disciplines.

- The primary user is a developer at a terminal with an AI coding agent: application,
  platform, infrastructure, data, QA, security and release engineers alike.
- Governance exists to make that developer faster and safer, not to report on them.

## Rationale

- An agent is useful in proportion to how much of the developer's real workflow it can see:
  source control, tickets, clusters, documents. Bundles cover those surfaces.
- A rule that blocks without saying what to do instead costs a developer a context switch and
  teaches the agent nothing. Every block must carry its alternative.
- Developers already have tools and habits. The harness adapts to them (their editor, their
  provider, their repo's own conventions) rather than replacing them.

## What it means in this repo

- **Bundles follow workflows.** `github`, `gitlab` (delivery), `jira`, `ticket-workflow`
  (planning), `k8s` (operations), `gdoc` (documents), `core` (conventions, credentials, git).
- **Plan before write.** `harness plan` shows every path before `harness apply` touches it;
  `apply` backs up every modified file; `uninstall` removes only state-listed paths.
- **The developer's text is theirs.** Instructions are written as managed blocks; text outside
  the markers is never touched. `harness sync --adopt` moves an edit back into its bundle.
- **Repository-level beats user-level.** A repo's own `CLAUDE.md`, `.claude/` settings, skills
  or hooks replace the user-level behaviour for that concern
  ([concepts](../docs/concepts.md#precedence)).
- **Messages say what to do.** Doctor FAILs name the manual step that fixes them; guard deny
  and ask reasons name the allowed alternative; manual steps carry `why`, `how` and `verify`.
- **Humans keep human decisions** (merge, approve, ticket state, sending mail), and the agent
  hands those back with the exact command instead of stalling.

## What it rules out

- Features whose main audience is not a developer: dashboards, usage reporting, telemetry.
- Guard rules that deny without an alternative, or ask on routine read-only commands.
- Writing to a provider's runtime state (sessions, credentials, memory, plugins).
- Taking over a developer's existing files without a plan row and a backup.
- Workflows that assume one discipline (for example, "every repo deploys to Kubernetes").

## How it is checked

| Check | Kind | Where |
|---|---|---|
| Guard `# rule:` reasons state an alternative | lint warning | `harness lint` |
| `doctor_checks[].fix` that looks like an id names a real manual step | lint error | `harness lint` |
| Every manual step has an `id`, a `title` and a `how` | schema | `schema/bundle.schema.json` |
| Manual steps carry `why` and `verify` | review | add-a-bundle checklist in [CONTRIBUTING](../CONTRIBUTING.md#adding-a-bundle) |
| `plan` twice prints `0 changes`; bootstrap works in a fresh home | smoke | `tests/smoke/bootstrap.sh`, CI |
| Guard rows cover read-only commands as `allow` or pass | test rows | `bundles/*/guard.d/tests.sh` |

## Tensions and how they are resolved

- **With governance.** Safety rules slow developers down. Resolution: three decisions, used
  deliberately. *Deny* only what must never happen; *ask* what a human should see; *allow*
  what the agent owns (the `agent-*` label model in [governance](../docs/governance.md)).
- **With principle 3 (platform for everyone).** A specific team wants specific behaviour.
  Resolution: config keys, private bundles in `local/bundles/`, or org bundles in an org
  platform instance ([self-host runbook](../docs/runbooks/self-host.md)). Public bundles stay
  generic.
- **With principle 1 (lightweight).** A workflow needs a heavy tool. Resolution: the tool is a
  bundle's optional dependency, never the hub's.

## Examples

Compliant:

- A deny reason: "pushing to the default branch is denied; push a branch and open a PR".
- A doctor check whose `fix` is `gh-auth`, a manual step with a click path.
- A skill that hands a merge back to the human with the exact command to run.

Non-compliant:

- A deny reason "not allowed" with no alternative.
- A rule that asks on every `git status`.
- An `apply` step that rewrites `~/.claude/settings.json` keys the adapter does not own.

## Open questions

- How to measure "time to first useful session" without telemetry. Two local proxies exist:
  `tests/smoke/bootstrap.sh` prints the elapsed seconds of an offline bootstrap, and
  `harness bootstrap` ends with "≈ N minutes of manual steps remain", summed from the pending
  steps' `minutes`. Open: whether to track them over releases, and how to time the human part.
- Whether non-coding disciplines (design, product) belong in public bundles or org bundles.
