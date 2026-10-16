# harness-hub

One governed harness for the AI coding agents your developers already use: the rules,
skills, sub-agents, permission lists, MCP servers and command guard that make Claude Code,
Gemini CLI, Copilot CLI, Codex and OpenCode work like a careful colleague on GitHub, GitLab,
Jira, Kubernetes and Google Workspace. Built for platform teams rolling out one baseline to
many developers, and for the developer who wants that baseline on their own machine.

Without it, an agent can read a token file, push to `main` or close a ticket with a commit
message, and five providers get configured five different ways, by hand, on every machine.

The repository is the product: installing means owning a copy. No service, registry, daemon
or package manager.

## What you get

Pick the bundles you need; each one is a capability with its own docs page.

<!-- generated:begin source=bundles/*/bundle.toml#readme -->
| Bundle | Domain / posture | Stability | What agents get | One-time setup |
|---|---|---|---|---|
| [core](docs/bundles/core.md) | base / local | stable | Guard engine, credential and git rules, conventions, Plan / Auto / code-reviewer agents | [3 steps](docs/bundles/core.md#manual-steps) |
| [gdoc](docs/bundles/gdoc.md) | workspace / label-gated | beta | gdoc CLI for Google Docs / Drive / Sheets / Gmail with provenance-gated writes; drafts only, never sends | [6 steps](docs/bundles/gdoc.md#manual-steps) |
| [github](docs/bundles/github.md) | scm / label-gated | stable | GitHub CLI, PR-based workflow, GitHub Issues as the tracker, gh governance rules | [4 steps](docs/bundles/github.md#manual-steps) |
| [gitlab](docs/bundles/gitlab.md) | scm / label-gated | stable | GitLab via glab: MR-based workflow, agent-label write gates, stacked-MR rules, Jira closing-keyword deny | [4 steps](docs/bundles/gitlab.md#manual-steps) |
| [jira](docs/bundles/jira.md) | tracker / label-gated | stable | Jira Server client (jira CLI + skill), read-only jira-mcp server, Jira write governance in the guard | [3 steps](docs/bundles/jira.md#manual-steps) |
| [k8s](docs/bundles/k8s.md) | kubernetes / read-only | stable | Read-only Kubernetes client (k8s CLI + skill), triage / audit / architect agents, kubeconfig and Secret guards | [4 steps](docs/bundles/k8s.md#manual-steps) |
| [stack](docs/bundles/stack.md) | scm / label-gated | experimental | Stacked MRs/PRs on free tiers: the `stk` CLI (plan, status, check, sync) keeps a chain of dependent parts retargeted, rebased and pushed | [3 steps](docs/bundles/stack.md#manual-steps) |
| [ticket-workflow](docs/bundles/ticket-workflow.md) | delivery / label-gated | beta | /work-ticket (ticket → governed MR/PR, stacked delivery) and /create-ticket (one drafted ticket or issue) | [1 step](docs/bundles/ticket-workflow.md#manual-steps) |
<!-- generated:end -->

- Every bundle pairs **guides**, which steer the agent before it acts (rules, skills,
  permissions, agent definitions), with **sensors**, which check at or after the action
  (guard sections, doctor checks, test rows, a code-review agent), after Martin Fowler's
  [harness engineering](https://martinfowler.com/articles/harness-engineering.html).
  `harness lint` warns when a guide has no sensor; coverage per bundle:
  [harness coverage](docs/reference/harness-coverage.md).
- Every component has a stable id and a domain, function and posture (the strongest effect
  it has without a human prompt). The full list: [catalog](docs/catalog.md) or
  `harness catalog`.

## How it works

1. **Describe your organisation once**, in one gitignored file, `local/harness.toml`: your
   email, hosts, project keys, which tracker each repository uses (GitHub Issues or Jira;
   a repository's own `.harness.toml` can declare it too), the bundles and providers you use.
2. **Pick bundles**, or a profile from `profiles/`. Dependencies are added for you; a
   conflict stops with one sentence saying what is missing.
3. **Run `bootstrap`.** It renders the bundles into every provider you selected: it shows
   the plan, applies it with backups, runs `harness doctor` and lists the manual steps
   still pending.

Afterwards, `harness plan` previews a change, `harness apply` writes it, `harness doctor`
checks the machine, `harness status --matrix` prints the capability matrix and
`harness upgrade` moves to a newer release.

## Install

**From upstream**, on a connected workstation: clone and bootstrap in one line.

```sh
git clone https://github.com/matt-kh/harness-hub.git ~/harness-hub && ~/harness-hub/bootstrap
```

**From your organisation's instance**, a fork or mirror on your git host with org bundles
and an org overlay: clone it the same way; set one up with the
[self-host runbook](docs/runbooks/self-host.md).

```sh
git clone <your instance URL> ~/harness-hub && ~/harness-hub/bootstrap
```

**From a bundle file**, air-gapped: a release is one `git bundle` file plus optional tool
archives and `SHA256SUMS` (built with `harness pack`), also shipped as one self-extracting
`harness-hub-X.Y.Z.run`.

```sh
sh harness-hub-X.Y.Z.run --check && sh harness-hub-X.Y.Z.run --offline --no-install-tools
# or, from the bundle file:
shasum -a 256 -c SHA256SUMS
git clone harness-hub-X.Y.Z.bundle ~/harness-hub && ~/harness-hub/bootstrap --offline --no-install-tools
```

Step by step: [getting started](docs/getting-started.md); tiers and release files:
[distribution](docs/distribution.md).

## Works with

<!-- generated:begin source=providers/*/provider.toml#readme -->
| capability | claude | codex | copilot | gemini | opencode |
|---|---|---|---|---|---|
| guard hook | enforced | advisory | enforced | enforced | advisory |
| ask decision | native | - | mapped (ask_as) | mapped (ask_as) | - |
| permission lists | native | advisory | advisory | advisory | none |
| instructions | native | native | native | native | native |
| skills | native | native | native | native | native |
| agents | native | inlined | native | inlined | inlined |
| mcp | native | native | native | native | none |

**Tier:** enforced on claude; partial on copilot, gemini; advisory on codex, opencode.
<!-- generated:end -->

Where a provider has no "ask", an ask maps to **deny** (`[providers.<name>].ask_as`).
Details per provider: [capability matrix](docs/reference/capability-matrix.md).

<!-- generated:begin source=PRINCIPLES.md#readme -->
## Built on ten principles

Ten principles govern every change to the hub; each links to its document (checks, tensions, examples). Summary and vocabulary: [PRINCIPLES.md](PRINCIPLES.md).

- **1. Lightweight.** → [01-lightweight](principles/01-lightweight.md)
- **2. Developer-first.** → [02-developer-first](principles/02-developer-first.md)
- **3. A platform for everyone.** → [03-platform-for-everyone](principles/03-platform-for-everyone.md)
- **4. Installed as a platform, distributable air-gapped.** → [04-install-as-a-platform](principles/04-install-as-a-platform.md)
- **5. Distributed as a git repository.** → [05-distributed-as-a-git-repo](principles/05-distributed-as-a-git-repo.md)
- **6. Harness engineering.** → [06-harness-engineering](principles/06-harness-engineering.md)
- **7. Extensible core.** → [07-extensible-core](principles/07-extensible-core.md)
- **8. User-level by design: repository-level wins.** → [08-user-level-by-design](principles/08-user-level-by-design.md)
- **9. Deterministic by construction.** → [09-deterministic-by-construction](principles/09-deterministic-by-construction.md)
- **10. Composable bundles.** → [10-composable-bundles](principles/10-composable-bundles.md)
<!-- generated:end -->

## Governance you can audit

- The guard **denies** reading credential files, pushing to a default branch, closing
  tickets by keyword and changing ticket state. It **asks** before merges, cluster mutations
  and writes to human-owned tickets. Every reason names what to do instead
  ([hook policy](docs/reference/hook-policy.md)).
- Agents write without a prompt only to artefacts they own, marked by an `agent-*` label
  ([governance](docs/governance.md)).
- **User-level by design.** Everything the hub installs is a baseline that yields wholesale
  to a repository's own harness, declared in a committed `.harness.toml` or found by name or
  text. Only the rules protecting your own credentials stay
  ([repository-level harnesses](docs/repo-level.md)).
- Hundreds of table-driven test rows, bypass attempts included, specify the guard.
- `harness plan` shows every path before `harness apply` writes; modified files are backed
  up; `harness uninstall` removes only the paths it recorded. Your text outside managed
  blocks is never touched.

## Your organisation stays out of the repo

- Everything specific to your organisation or to you lives in gitignored `local/`: config,
  private bundles, your gate denylist.
- Public bundles use `{{ config.keys }}` and documentation values (`example.com`,
  `PROJ-123`).
- **Secrets never go in config**: validation rejects them; tokens stay in their CLIs' own
  files, which the guard denies agents reading ([secrets](docs/reference/secrets.md)).
- A [private-identifier gate](tools/gate/README.md) checks contents, file names, commit
  messages and author emails in pre-commit and CI.

## Requirements

Linux, WSL2 or macOS (native Windows: use WSL2), at least one of Claude Code, Gemini CLI,
Copilot CLI, Codex or OpenCode, and `curl` for downloads (not needed offline). Every script
parses under macOS `/bin/bash` 3.2; the engine is python standard library only. The core
bundle requires:

<!-- generated:begin source=bundles/core/bundle.toml#readme -->
| Binary | Minimum | Why |
|---|---|---|
| `bash` | ≥ 3.2 | The guard hook and every script are bash. 3.2 parses everything; bash >= 4 is recommended (doctor warns). |
| `git` | ≥ 2.30 | Hub checkout, and the guard resolves the current branch before a push. |
| `jq` | ≥ 1.6 | The guard parses the hook JSON with jq and FAILS CLOSED without it: every shell command is denied until jq is installed. |
| `python3` | ≥ 3.9 | Engine, skill CLIs (jira, gdoc, k8s) and helper scripts are stdlib python. |
<!-- generated:end -->

Tool downloads are pinned, sha256-verified, mirrorable (`HARNESS_TOOLS_MIRROR`) and work
offline ([air-gapped runbook](docs/runbooks/air-gapped.md)). No telemetry; every outbound
call is listed in [SECURITY.md](SECURITY.md).

## Documentation

| | |
|---|---|
| [Principles](PRINCIPLES.md) | principles, vocabulary, change procedure |
| [Getting started](docs/getting-started.md) | first run on Linux / WSL2 / macOS |
| [Concepts](docs/concepts.md) | config, bundles, providers, guides and sensors |
| [Governance](docs/governance.md) | the rules and why |
| [Repository-level harnesses](docs/repo-level.md) | what the hub does in your repo, `.harness.toml`, provider collision facts |
| [Distribution](docs/distribution.md) | tiers, release bundle |
| [Self-host](docs/runbooks/self-host.md) | an org platform instance |
| [Runbooks](docs/runbooks/new-machine.md) | new machine, upgrade, air-gapped, migration, rotation |
| [Catalog](docs/catalog.md) | every bundle, skill, agent, rule, guard section and check, with its id and facets |
| [Reference](docs/reference/cli.md) | CLI, config schema, hook policy, secrets, [taxonomy](docs/reference/taxonomy.md) |
| [Roadmap](docs/roadmap.md) | planned bundles and extensions by tranche, reserved guard prefixes, rejected ideas |
| [Architecture](ARCHITECTURE.md) | normative contracts |
| [AGENTS.md](AGENTS.md) | for agents changing this repo |
| [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md) · [Changelog](CHANGELOG.md) | |

## License

[MIT](LICENSE) © matt-kh
