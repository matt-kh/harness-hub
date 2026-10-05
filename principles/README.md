# principles/

One document per principle of harness-hub. [PRINCIPLES.md](../PRINCIPLES.md) at the root is
the summary and index; agents read it first and open a document here when their change
touches that area.

## Documents

| # | Document | In one line |
|---|---|---|
| 1 | [01-lightweight.md](01-lightweight.md) | bash, stdlib python, jq, git, curl; nothing else without a reason |
| 2 | [02-developer-first.md](02-developer-first.md) | built for developer workflows; every block says what to do instead |
| 3 | [03-platform-for-everyone.md](03-platform-for-everyone.md) | a platform team's design, generic enough for any organisation |
| 4 | [04-install-as-a-platform.md](04-install-as-a-platform.md) | installing means owning a copy; works air-gapped |
| 5 | [05-distributed-as-a-git-repo.md](05-distributed-as-a-git-repo.md) | released as a `git bundle`, upgraded with git |
| 6 | [06-harness-engineering.md](06-harness-engineering.md) | guides paired with sensors, sensor messages that steer |
| 7 | [07-extensible-core.md](07-extensible-core.md) | the principles are the core and change through review |

## Layout of each document

- **Statement** — the principle's wording and intent.
- **Rationale** — why it holds.
- **What it means in this repo** — concrete files, commands and conventions.
- **What it rules out**.
- **How it is checked** — the lint, test, gate, CI or review step.
- **Tensions and how they are resolved** — with other principles.
- **Examples** — compliant and non-compliant changes.
- **Open questions**.

## Numbering

- Numbers are stable: never renumbered, never reused.
- New principles are appended: `08-<slug>.md`, `09-<slug>.md`.
- A retired principle keeps its file with a *Retired in X.Y.Z: reason* line under the title.

## Change procedure

One pull request that:

1. edits (or adds) the principle document here;
2. updates its summary statement in [PRINCIPLES.md](../PRINCIPLES.md);
3. increments `principles_version` in the `PRINCIPLES.md` header;
4. adds an entry under a **Principles** heading in the `[Unreleased]` section of
   [CHANGELOG.md](../CHANGELOG.md);
5. updates or lists as follow-ups the checks that implement the principle.

Refinements that leave a statement's intent unchanged (better examples, a new check, a new
tension) need only step 1 and a normal CHANGELOG entry.
