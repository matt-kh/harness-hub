# harness-hub

A bootstrap kit for **AI coding agent harnesses**: the instructions, skills, sub-agents,
permission lists, MCP servers and command guard that make Claude Code, Gemini CLI, Copilot
CLI, Codex or OpenCode behave like a disciplined colleague on your team's GitLab, GitHub,
Jira, Kubernetes and Google Workspace.

One gitignored config file describes *your* organisation. The hub renders it, together with
the bundles you pick, into every agent provider you use.

## In 60 seconds

- **Governance first.** A command guard sits in front of the agent's shell. It denies reading
  credential files, pushing to a default branch, closing tickets by keyword or changing ticket
  state; it asks before merges, cluster mutations and writes to human-owned tickets; it lets
  agents write freely to artefacts they created (the `agent-*` label model).
  More than 500 table-driven test rows cover it.
- **Bundles, not a monolith.** Pick `core` plus what you use: `github`, `gitlab`, `jira`,
  `ticket-workflow`, `k8s`, `gdoc`. Each bundle ships rules, skills, guard sections,
  permissions, doctor checks and the **manual steps** a human must do once (OAuth clients,
  tokens, SSH keys), documented click by click.
- **Many providers, open formats.** Instructions go into managed blocks in `CLAUDE.md`,
  `GEMINI.md`, `AGENTS.md` and `copilot-instructions.md`; skills use the Agent Skills
  `SKILL.md` layout; MCP servers are registered per provider. Your own text outside the
  managed blocks is never touched.
- **Safe to run on a machine that already has a harness.** `harness plan` shows every path it
  would create or change before `apply` writes anything; every modified file is backed up; a
  state file records exactly what the hub owns, so `uninstall` removes only that.
- **Your org values never enter this repo** (see below), and CI enforces it.

## Quickstart

```sh
git clone git@github.com:matt-kh/harness-hub.git ~/harness-hub && ~/harness-hub/bootstrap
```

`bootstrap` asks for your email, lets you tick bundles and providers (installed CLIs are
pre-selected), writes `local/harness.toml`, shows the plan, applies it, runs `harness doctor`
and prints the manual steps that are still pending. Then:

```sh
harness doctor              # PASS / WARN / FAIL per check, each FAIL names the step that fixes it
harness steps --pending     # the one-time human steps you still have to do
claude                      # or gemini, copilot, codex, opencode: start a session
```

Full walk-through for Linux, WSL2 and macOS: [docs/getting-started.md](docs/getting-started.md).
Non-interactive (CI, dotfiles): `~/harness-hub/bootstrap --bundles core,github --providers claude --yes`.

## Bundles

| Bundle | What agents get | What a human sets up once |
|---|---|---|
| [core](docs/bundles/core.md) | guard engine, credential and git rules, Plan / Auto / code-reviewer agents, conventions, the `harness` CLI | nothing beyond `bootstrap` |
| [github](docs/bundles/github.md) | `gh` (pinned install), PR workflow, GitHub Issues as tracker, gh governance | `gh auth login`, SSH key |
| [gitlab](docs/bundles/gitlab.md) | `glab` MR workflow, agent-labelled MRs, closing-keyword deny | `glab auth login`, SSH key |
| [jira](docs/bundles/jira.md) | `jira` CLI for Jira Server/Data Center, read-only MCP server, write gate | personal access token |
| [ticket-workflow](docs/bundles/ticket-workflow.md) | `work-ticket` (ticket → MR/PR) and `create-ticket` skills | nothing; needs a tracker and an SCM bundle |
| [k8s](docs/bundles/k8s.md) | read-only `k8s` CLI, triage and audit agents, Secret redaction | kubeconfig contexts |
| [gdoc](docs/bundles/gdoc.md) | `gdoc` CLI for Docs, Drive, Sheets and Gmail drafts, provenance-gated writes | GCP project + Desktop OAuth client |

Profiles (`bootstrap --profile NAME`) are named selections: `minimal`, `github-dev`,
`gitlab-jira`, `platform-engineer`.

## Provider capability matrix

What each provider can actually enforce. Do not assume a lower tier enforces what a higher
one does; `harness status --matrix` prints this for your machine.

| Capability | claude | gemini | copilot | codex | opencode |
|---|---|---|---|---|---|
| **Tier** | **enforced** | **partial** | **partial** | **advisory** | **advisory** |
| Guard hook on shell commands | enforced | enforced, no "ask" (mapped by `ask_as`) | enforced, no "ask" (mapped by `ask_as`) | none (instructions only) | none (instructions only) |
| Permission lists | native | partial (denies become tool exclusions) | partial | advisory | advisory |
| Instructions | `~/.claude/CLAUDE.md` | `~/.gemini/GEMINI.md` | `~/.copilot/copilot-instructions.md` | `~/.codex/AGENTS.md` | `~/.config/opencode/AGENTS.md` |
| Skills | native | native | native | native | native |
| Sub-agents | native | inlined into instructions | native | inlined | inlined |
| MCP servers | native | native | native | native | not managed |

"Ask" decisions on providers without an ask prompt default to **deny** with a reason telling
the user to run the command themselves (`[providers.<name>].ask_as = "allow"` opts out).
Details and quirks: [docs/providers/](docs/providers/claude.md), generated matrix:
[docs/reference/capability-matrix.md](docs/reference/capability-matrix.md).

## Your org values never enter this repo

Everything organisation- or person-specific lives in `local/` — gitignored, optionally its
own private git repository with no public remote:

```text
local/
├── harness.toml          # identity, hosts, Jira field ids, cluster regexes, trust text
├── harness.user.toml     # optional per-machine overrides
├── bundles/<org>/        # a private bundle: org rules, cluster notes, extra guard rules
└── gate-denylist.txt     # your identifiers, for the private-identifier gate
```

- Public bundles only contain `{{ config.keys }}` and documentation values (`example.com`,
  `PROJ-123`, `192.0.2.x`).
- **Secrets never go in config.** Validation rejects keys named like tokens or passwords and
  high-entropy values; tokens stay in the files their own CLIs write (`~/.config/gh`,
  `~/.config/glab-cli`, `~/.config/jira`, `~/.config/gdoc`, kubeconfig), and the guard denies
  agents reading them. Map: [docs/reference/secrets.md](docs/reference/secrets.md).
- A private-identifier gate ([tools/gate](tools/gate/README.md)) runs in pre-commit and CI
  over file contents, file names, commit messages and author emails. Contributors keep their
  own denylist in `local/gate-denylist.txt`; CI gets the maintainer's via a secret and only
  ever prints `private#<n>`.

## Requirements

| | |
|---|---|
| OS | Linux, WSL2, macOS. Native Windows is not supported (use WSL2). |
| bash | ≥ 4 recommended (Homebrew bash on macOS); every script *parses* under macOS `/bin/bash` 3.2 and `doctor` reports features that need 4 |
| python | 3.9+, standard library only (no pip installs) |
| tools | `jq` (the guard fails closed without it), `git`, `curl` |
| providers | at least one of Claude Code, Gemini CLI, Copilot CLI, Codex, OpenCode |

Tool downloads (`harness install gh`) are pinned and sha256-verified, honour `HTTPS_PROXY`
and `HARNESS_TOOLS_MIRROR`, and work air-gapped with `--from FILE`
([runbook](docs/runbooks/air-gapped.md)). No telemetry; every outbound call is listed in
[SECURITY.md](SECURITY.md).

## Documentation

| Start here | |
|---|---|
| [Getting started](docs/getting-started.md) | first run on Linux / WSL2 / macOS |
| [Concepts](docs/concepts.md) | config → bundles → providers → render / plan / apply / state |
| [Governance](docs/governance.md) | the rules agents follow and why |
| [Runbooks](docs/runbooks/new-machine.md) | new machine, upgrade, air-gapped, migrating an existing harness, token rotation |
| [Reference](docs/reference/cli.md) | CLI, config schema, hook policy, secrets, capability matrix |
| [Architecture](ARCHITECTURE.md) | the normative contracts for bundles, providers and the engine |
| [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md) · [Changelog](CHANGELOG.md) | |

## License

[MIT](LICENSE) © matt-kh
