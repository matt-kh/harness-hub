# Principle 7 — Extensible core

Part of [PRINCIPLES.md](../PRINCIPLES.md). Read this before adding, changing or removing a
principle, or before arguing that a principle no longer applies.

## Statement

> These principles are meant to be extensible and subject to change while still serving as
> the core of this repo.

- The principles are the core: every design decision should trace to one of them.
- They are not frozen: they change through the same reviewed process as code.

## Rationale

- A platform outlives its first design. Principles that cannot change get ignored; principles
  that change silently stop meaning anything.
- Agents read these files as context. A stable layout and an explicit version let an agent
  know which rules it applied and notice when they changed.

## What it means in this repo

- **Storage.** [PRINCIPLES.md](../PRINCIPLES.md) is the summary and index: one normative
  statement per principle, the vocabulary and the change procedure. Each principle has one
  document here, in `principles/NN-<slug>.md`.
- **Always referenced.** The principles are linked from:
  - [AGENTS.md](../AGENTS.md) (and its `CLAUDE.md` symlink), read at the start of every agent
    session in this repo;
  - [ARCHITECTURE.md](../ARCHITECTURE.md), whose header states it is governed by them;
  - [CONTRIBUTING.md](../CONTRIBUTING.md#principles-first) and the
    [PR template](../.github/PULL_REQUEST_TEMPLATE.md), which ask which principle a change
    serves;
  - `harness lint`, whose dependency and guides/sensors warnings implement principles 1 and 6.
- **Stable numbering.** Numbers never change and are never reused. New principles are
  appended (`08-…`). A retired principle keeps its file, marked *Retired* with the reason and
  the release.
- **Versioned.** `PRINCIPLES.md` carries `principles_version: N`; any change to a statement,
  an addition or a retirement increments it.
- **The change procedure** ([principles/README.md](README.md)): one PR that edits the
  principle document, its summary line in `PRINCIPLES.md`, bumps `principles_version` and adds
  a CHANGELOG "Principles" entry. Checks that implement the principle change in the same PR or
  are listed as follow-ups.

## What it rules out

- Editing a statement without a version bump and a CHANGELOG entry.
- Renumbering, or reusing a retired number.
- Principles kept only in an issue, a wiki or a chat; they live in the repo.
- Code that contradicts a principle without the PR saying so and proposing the change.

## How it is checked

| Check | Kind | Where |
|---|---|---|
| Every PR names the principle(s) it serves, or "neutral" | review | PR template |
| `PRINCIPLES.md` links resolve to every principle document | lint | `tools/gate/check-links.sh` |
| Principle changes carry a CHANGELOG "Principles" entry | review | CONTRIBUTING, PR template |

## Tensions and how they are resolved

- **Stability versus change.** Frequent edits erode trust. Resolution: statements change
  rarely; the per-principle documents (meaning, checks, examples) may be refined freely
  without a version bump as long as the statement's intent is unchanged.
- **Conflicts between principles.** Each document lists its tensions and the resolution. When
  a new conflict appears, the PR that meets it adds the resolution to both documents.
- **No written resolution yet.** The PR names the conflict and the choice it makes; review
  decides, and the decision is recorded in both documents. Numbering is not a ranking.

## Examples

Compliant:

- A PR adding `08-observability.md`, a summary line, `principles_version: 2` and a CHANGELOG
  "Principles" entry.
- A PR refining the examples in principle 4 with no change to its statement.

Non-compliant:

- Changing the wording of principle 1 in `PRINCIPLES.md` only.
- Deleting principle 5 because a release used a tarball.

## Open questions

- Whether `harness lint` should verify that `principles_version` changed whenever a statement
  changed (needs a baseline to compare with).
