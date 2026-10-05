# Principles

principles_version: 1

The seven principles below are the core of harness-hub. Every change to this repository
serves at least one of them or is neutral to all of them. Read this page before changing the
repo; open the linked document when your change touches that area.

- Written for humans and agents alike: one normative statement per principle, stable
  numbering, short lines.
- Referenced from [AGENTS.md](AGENTS.md), [ARCHITECTURE.md](ARCHITECTURE.md),
  [CONTRIBUTING.md](CONTRIBUTING.md), the [PR template](.github/PULL_REQUEST_TEMPLATE.md) and
  `harness lint`.
- Directory, numbering and change procedure: [principles/README.md](principles/README.md).

## The principles

1. **Lightweight.** The hub needs only bash, python 3.9+ standard library, jq, git and curl;
   any other dependency belongs to an optional bundle, is pinned and verified, and has a
   reviewed reason. → [01-lightweight](principles/01-lightweight.md)
2. **Developer-first.** Harnesses serve developer workflows across all software engineering
   disciplines; every block names the allowed alternative, and the developer's own files and
   decisions stay theirs. → [02-developer-first](principles/02-developer-first.md)
3. **A platform for everyone.** Built from a platform developer's perspective to serve an
   organisation's developers, and presented as a platform for anyone: no organisation's values
   in the repo, every org value in config. → [03-platform-for-everyone](principles/03-platform-for-everyone.md)
4. **Installed as a platform, distributable air-gapped.** Installing means owning a copy of the
   repository, never running a service; every install and upgrade path has an offline
   variant. → [04-install-as-a-platform](principles/04-install-as-a-platform.md)
5. **Distributed as a git repository.** Like makeself, but for git: a release is one
   `git bundle` file plus optional tool archives and checksums; upgrades are git
   operations. → [05-distributed-as-a-git-repo](principles/05-distributed-as-a-git-repo.md)
6. **Harness engineering.** Each bundle follows the
   [harness engineering](https://martinfowler.com/articles/harness-engineering.html) practices
   as far as possible: guides paired with sensors, cheap checks early, sensor messages that say
   what to do instead, and a steering loop. → [06-harness-engineering](principles/06-harness-engineering.md)
7. **Extensible core.** These principles are the core of the repo and change only through a
   reviewed PR with a version bump; numbers are stable and new principles are
   appended. → [07-extensible-core](principles/07-extensible-core.md)

## Vocabulary

| Term | Meaning here |
|---|---|
| hub | this repository: engine, bundles, provider adapters, docs |
| bundle | one capability in `bundles/<name>/`: rules, skills, agents, guard sections, permissions, doctor checks, manual steps |
| provider | an agent product the hub renders into (Claude Code, Gemini CLI, Copilot CLI, Codex, OpenCode) |
| guide | a feedforward control that steers the agent before it acts: rule, skill, permission, agent definition, template |
| sensor | a feedback control that detects at or after the action: guard, doctor check, test, lint, review agent |
| computational | deterministic, fast, run on every change (guard, lint, tests, doctor) |
| inferential | semantic, slower, non-deterministic (a code-review agent) |
| steering loop | when an issue recurs, improve a guide or sensor so it does not recur |
| component | one thing a bundle ships: rule, skill, agent, guard section, permission list, MCP server, CLI, installer, doctor check, manual step |
| id | a component's stable name, derived from its path: `<bundle>/<kind-dir>/<name>` (`k8s/agents/k8s-triage`) |
| domain | what a component is about: base, scm, tracker, delivery, kubernetes, workspace |
| function | what a component does for the agent: govern, client, workflow, investigate, plan, execute, review, setup |
| posture | the strongest effect a component has without a human prompt: read-only < local < label-gated |
| catalog | the generated list of every component with its id and facets ([docs/catalog.md](docs/catalog.md), `harness catalog`) |
| upstream | the public hub, the reference distribution |
| org platform instance | an organisation's fork or mirror of the hub on its own git host, with org bundles and an org overlay |
| workstation | one developer's clone plus its gitignored `local/` |
| bundle file | a `git bundle` release artifact, `harness-hub-X.Y.Z.bundle`; not to be confused with a harness bundle |

## Applying the principles

- Name the principle(s) a PR serves in its description, or write "neutral".
- When a change conflicts with a principle, say so in the PR and propose the principle change
  in the same PR; do not work around it silently.
- When a check fires, fix the cause first, then improve the check's message if it did not say
  what to do (the steering loop).

## Changing the principles

In brief (full procedure in [principles/README.md](principles/README.md)):

1. One PR edits the principle document and its statement above.
2. `principles_version` above is incremented.
3. `CHANGELOG.md` gets an entry under **Principles** in `[Unreleased]`.
4. New principles are appended with the next number; numbers are never reused.
