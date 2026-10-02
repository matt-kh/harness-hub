# harness-hub

An open platform for **governed AI coding agent harnesses**: the instructions, skills,
sub-agents, permission lists, MCP servers and command guard that make Claude Code, Gemini
CLI, Copilot CLI, Codex or OpenCode work like a disciplined colleague on GitHub, GitLab,
Jira, Kubernetes and Google Workspace. One gitignored config file describes your
organisation; the hub renders it, with the bundles you pick, into every provider you use.

- **For platform teams** rolling out one governed baseline to many developers, and for
  individual developers.
- **The repository is the product.** Installing means owning a copy: no service, registry,
  daemon or package manager. Seven [principles](PRINCIPLES.md) govern every change.

## Install

**From upstream** (a connected workstation):

```sh
git clone https://github.com/matt-kh/harness-hub.git ~/harness-hub && ~/harness-hub/bootstrap
```

**From your organisation's instance**: a fork or mirror on your git host with org bundles
and an org overlay. Clone it the same way; set one up with the
[self-host runbook](docs/runbooks/self-host.md).

**From a bundle file** (air-gapped): a release is one `git bundle` file plus optional tool
archives and `SHA256SUMS`, built with `harness pack`.

```sh
shasum -a 256 -c SHA256SUMS
git clone harness-hub-vX.Y.Z.bundle ~/harness-hub && ~/harness-hub/bootstrap --offline --no-install-tools
```

`bootstrap` writes `local/harness.toml`, shows the plan, applies it with backups, runs
`harness doctor` and lists pending manual steps. See
[getting started](docs/getting-started.md) and [distribution](docs/distribution.md).

## What a bundle is

A bundle is one capability, built along the lines of Martin Fowler's
[harness engineering](https://martinfowler.com/articles/harness-engineering.html):

- **Guides** steer the agent before it acts: rules, skills, permissions, agent definitions.
- **Sensors** check at or after the action: guard sections, doctor checks, test rows, a
  code-review agent.
- Each bundle declares both in `bundle.toml`; `harness lint` warns when one has no partner.
  Coverage per bundle: [harness coverage](docs/reference/harness-coverage.md).

| Bundle | What agents get | What a human sets up once |
|---|---|---|
| [core](docs/bundles/core.md) | guard engine, credential and git rules, Plan / Auto / code-reviewer agents, the `harness` CLI | nothing beyond `bootstrap` |
| [github](docs/bundles/github.md) | `gh` (pinned install), PR workflow, GitHub Issues as tracker | `gh auth login`, SSH key |
| [gitlab](docs/bundles/gitlab.md) | `glab` MR workflow, agent-labelled MRs, closing-keyword deny | `glab auth login`, SSH key |
| [jira](docs/bundles/jira.md) | `jira` CLI for Jira Server/Data Center, read-only MCP, write gate | personal access token |
| [ticket-workflow](docs/bundles/ticket-workflow.md) | `work-ticket` (ticket → MR/PR) and `create-ticket` skills | nothing; needs a tracker and an SCM bundle |
| [k8s](docs/bundles/k8s.md) | read-only `k8s` CLI, triage and audit agents, Secret redaction | kubeconfig contexts |
| [gdoc](docs/bundles/gdoc.md) | `gdoc` CLI for Docs, Drive, Sheets and Gmail drafts | a GCP OAuth client |

## Governance

- The guard **denies** reading credential files, pushing to a default branch, closing tickets
  by keyword and changing ticket state; it **asks** before merges, cluster mutations and
  writes to human-owned tickets. Every reason names what to do instead.
- Agents write promptlessly only to artefacts they own, marked by an `agent-*` label
  ([governance](docs/governance.md)).
- Hundreds of table-driven test rows, bypass attempts included, specify the guard.
- `harness plan` shows every path before `apply` writes; modified files are backed up;
  `uninstall` removes only state-listed paths. Your text outside managed blocks is untouched.

## Provider capability matrix

| Capability | claude | gemini | copilot | codex | opencode |
|---|---|---|---|---|---|
| **Tier** | **enforced** | **partial** | **partial** | **advisory** | **advisory** |
| Guard hook on shell commands | yes | yes, no "ask" | yes, no "ask" | none | none |
| Permission lists | native | partial | partial | advisory | advisory |
| Sub-agents | native | inlined | native | inlined | inlined |
| MCP servers | native | native | native | native | not managed |

"Ask" without a prompt maps to **deny** (`[providers.<name>].ask_as`). `harness status --matrix`
prints this for your machine; details: [capability matrix](docs/reference/capability-matrix.md).

## Org values never enter this repo

- Everything organisation- or person-specific lives in gitignored `local/`: config, private
  bundles, your gate denylist.
- Public bundles use `{{ config.keys }}` and documentation values (`example.com`, `PROJ-123`).
- **Secrets never go in config**: validation rejects them; tokens stay in their CLIs' own
  files, which the guard denies agents reading ([secrets](docs/reference/secrets.md)).
- A [private-identifier gate](tools/gate/README.md) checks contents, file names, commit
  messages and author emails in pre-commit and CI.

## Requirements

| | |
|---|---|
| OS | Linux, WSL2, macOS (native Windows: use WSL2) |
| bash | ≥ 4 recommended; every script parses under macOS `/bin/bash` 3.2 |
| python | 3.9+, standard library only |
| tools | `jq`, `git`, `curl` |
| providers | at least one of Claude Code, Gemini CLI, Copilot CLI, Codex, OpenCode |

Tool downloads are pinned, sha256-verified, mirrorable (`HARNESS_TOOLS_MIRROR`) and work
offline ([air-gapped runbook](docs/runbooks/air-gapped.md)). No telemetry; every outbound call is
listed in [SECURITY.md](SECURITY.md).

## Documentation

| | |
|---|---|
| [Principles](PRINCIPLES.md) | principles, vocabulary, change procedure |
| [Getting started](docs/getting-started.md) | first run on Linux / WSL2 / macOS |
| [Concepts](docs/concepts.md) | config, bundles, providers, guides and sensors |
| [Governance](docs/governance.md) | the rules and why |
| [Distribution](docs/distribution.md) | tiers, release bundle |
| [Self-host](docs/runbooks/self-host.md) | an org platform instance |
| [Runbooks](docs/runbooks/new-machine.md) | new machine, upgrade, air-gapped, migration, rotation |
| [Reference](docs/reference/cli.md) | CLI, config schema, hook policy, secrets |
| [Architecture](ARCHITECTURE.md) | normative contracts |
| [AGENTS.md](AGENTS.md) | for agents changing this repo |
| [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md) · [Changelog](CHANGELOG.md) | |

## License

[MIT](LICENSE) © matt-kh
