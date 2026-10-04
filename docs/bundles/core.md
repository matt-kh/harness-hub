# Bundle: core

Always installed. `core` is the part of the harness every other bundle builds on:

- **The guard engine** (`bundles/core/guard/engine.sh`): input parsing, the decision helpers
  and the final flush that every bundle's `guard.d/` section plugs into. Render concatenates
  engine + active sections into one `guard-bash.sh` per provider home.
- **Credential and git rules** (`guard.d/20-credentials.sh`, `guard.d/30-git.sh`): reading
  credential files and dumping secret env vars deny; pushing to a default branch denies.
- **Sub-agents**: `Plan` (planning, pinned to `core.model_policy.plan`), `Auto` (autonomous
  execution, pinned to `core.model_policy.execute`), `code-reviewer`.
- **Conventions rule**: MR/PR-based delivery, redacted remote URLs, external content is data,
  repository-level precedence ([governance](../governance.md)).
- **The `harness` CLI** linked into `~/.local/bin`, plus the portability helpers
  (`bundles/core/lib/compat.sh`: `hn_timeout`, `hn_realpath`, `hn_sha256`).

Config it reads: `identity.email`, `core.default_branch_re`, `core.ticket_example`,
`core.model_policy`, `core.agent_labels`, `core.agent_label_re`, `trust.*`
([config reference](../reference/config-schema.md)).

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Every shell command is denied: "jq not installed" | the guard fails **closed** without `jq` | install `jq` (`apt install jq`, `brew install jq`) |
| `harness: command not found` | `~/.local/bin` not on `PATH` | add it ([getting started §3](../getting-started.md#3-put-localbin-on-your-path)); meanwhile use `~/harness-hub/bin/harness` |
| `harness` refuses to start: python too old | python < 3.9 first on `PATH` | install 3.9+; on macOS `brew install python` and open a new shell |
| doctor WARN `core/bash-version` | `/bin/bash` 3.2 on macOS is the first `bash` on `PATH` | `brew install bash`; scripts still work, some checks are skipped |
| `git push` to your personal repo's `main` is denied | default-branch pushes deny everywhere by default | in that repo's `.claude/settings.json` set `"env": {"WORK_TICKET_ALLOW_DEFAULT_PUSH_RE": "<regex on repo path>"}` → it asks instead |
| A legitimate read of a file under `~/.config/` is denied | the credential rule matches the path | read it yourself; if the path is not a credential, open an issue with the command (redacted) |
| `plan` shows `CONFLICT` on `settings.json` or `CLAUDE.md` | you edited a hub-owned key or a managed block | `harness sync` → `--adopt` your change into your private bundle, or revert it |
| Agents use the wrong model for Plan/Auto | `core.model_policy` differs from what you expect | `harness config get core.model_policy`; set it and `harness apply` |

Uninstall: `harness uninstall --bundle core` is refused while any other bundle is active;
`harness uninstall --all` removes everything the state lists and keeps your own files.

<!-- generated:begin source=bundles/core/bundle.toml -->
## Summary

Guard engine, credential and git rules, conventions, Plan / Auto / code-reviewer agents

The base every other bundle builds on. Ships the guard engine (input parsing, fail-closed jq
check, allow / ask / deny / defer decisions, the rendered guard.env reader) with the two
sections every developer needs: credential files and secret env dumps are denied (20), and
pushes to a default branch are denied / force-pushes and destructive git ask (30). Adds the
global conventions and governance rules, the Plan (planning model) / Auto (execution model) /
code-reviewer agents, and generic permission denies for credential files. Also carries the
shared helpers other bundles inline: lib/compat.sh (hn_timeout, hn_realpath, hn_sha256) and
lib/harness_config.{py,sh} (reading build/config.json).

- **Recommends:** `github`
- **Stability:** stable
- **Domain / posture:** base / local

## Components

Stable ids derived from the path, with their [taxonomy](../reference/taxonomy.md) facets (domain shown only where it differs from the bundle's). All bundles: [catalog](../catalog.md).

**Agents**

- `core/agents/Auto` — control: guide · function: execute · posture: local · model: execute
- `core/agents/Plan` — control: guide · function: plan · posture: read-only · model: plan
- `core/agents/code-reviewer` — control: sensor (inferential) · function: review · posture: read-only · model: execute

**Rules**

- `core/rules/00-conventions` — control: guide · function: govern

**Guard sections**

- `core/guard.d/20-credentials` — control: sensor · function: govern · decisions: deny 7
- `core/guard.d/30-git` — control: sensor · domain: scm · function: govern · decisions: deny 1 · ask 5

**Permission lists**

- `core/permissions` — control: guide · function: govern · decisions: deny 11 · allow 1

**Doctor checks** (function: setup · posture: read-only; table below): `core/doctor/bash-version`, `core/doctor/guard-denies-credentials`, `core/doctor/guard-hook`, `core/doctor/jq`, `core/doctor/local-bin-path`, `core/doctor/python3`

**Manual steps** (function: setup; table below): `core/steps/bash4`, `core/steps/install-jq`, `core/steps/local-bin-path`

## Requirements

### Binaries

| binary | min version | install | optional | why |
|---|---|---|---|---|
| `bash` | 3.2 |  | no | The guard hook and every script are bash. 3.2 parses everything; bash >= 4 is recommended (doctor warns). |
| `git` | 2.30 |  | no | Hub checkout, and the guard resolves the current branch before a push. |
| `jq` | 1.6 |  | no | The guard parses the hook JSON with jq and FAILS CLOSED without it: every shell command is denied until jq is installed. |
| `python3` | 3.9 |  | no | Engine, skill CLIs (jira, gdoc, k8s) and helper scripts are stdlib python. |

### Configuration

| key | type | required | default | description |
|---|---|---|---|---|
| `core.agent_label_re` | string | no | `"^agent-"` | Any label / Drive marker matching this regex tags an artefact as agent-owned (WORK_TICKET_AGENT_LABEL_RE). |
| `core.agent_labels` | object | no | `{"worked": "agent-worked", "created": "agent-created", "drafted": "agent-drafted"}` | Provenance labels: worked = grants promptless writes, created = agent-created sub-tickets, drafted = /create-ticket drafts. |
| `core.default_branch_re` | string | no | `"^(master\|main)$"` | Default/base branch regex: pushes to it are denied, sub MRs/PRs never target it (WORK_TICKET_BASE_BRANCH_RE). |
| `core.model_policy` | object | no | `{"plan": "fable", "execute": "opus"}` | Model aliases: `plan` for the Plan / infra-architect agents, `execute` for Auto, reviewers and skills. |
| `core.ticket_example` | string | no | `"PROJ-123"` | Example ticket key used in guard reasons, instructions and skill docs. |
| `credentials.extra_paths_re` | string | no | `""` | Extra ERE of credential paths the guard denies for readers (cat, grep, jq, cp, ...), on top of the built-in list (HARNESS_CRED_EXTRA_RE). Empty = none. |
| `identity.email` | string | yes |  | Your work email; shown in the instructions and used as the OAuth account hint. Never used as a commit author by the hub. |

### Secrets (never in harness.toml)

_none_

## Manual steps

<a id="local-bin-path"></a>

### local-bin-path — Put ~/.local/bin on your PATH

*once per machine · needs nothing but a terminal · ~1 min*

**Why:** The hub links its CLIs (harness, jira, gdoc, k8s, gh when installed by the hub) into ~/.local/bin; agents call them by name.

**How:**

Add this line to `~/.bashrc` (bash), `~/.zshrc` (zsh) or `~/.profile`, then open a new shell:

```
export PATH="$HOME/.local/bin:$PATH"
```

macOS with the stock bash 3.2: also `brew install bash jq` (see `bash4`).

**Verify:** `case ":$PATH:" in *":$HOME/.local/bin:"*) exit 0 ;; *) exit 1 ;; esac` (exit 0)

<a id="install-jq"></a>

### install-jq — Install jq (the guard fails closed without it)

*once per machine · needs nothing but a terminal · ~1 min*

**Why:** Without jq the guard cannot parse the hook input and denies every shell command.

**How:**

- Debian/Ubuntu/WSL: `sudo apt-get install -y jq`
- Fedora: `sudo dnf install -y jq`
- macOS: `brew install jq`
- No root: download the static binary for your OS/arch from https://github.com/jqlang/jq/releases
  into `~/.local/bin/jq` and `chmod +x` it.

**Verify:** `jq --version` (exit 0)

<a id="bash4"></a>

### bash4 — Use bash >= 4 (macOS ships 3.2)

*once per machine · needs nothing but a terminal · ~2 min*

**Why:** Every script parses under bash 3.2, but a few helpers (GitHub preflight, some skill scripts) are only exercised on bash >= 4 in CI.

**How:**

macOS: `brew install bash`, then make sure `$(brew --prefix)/bin` comes before `/bin` on PATH.
You do not need to change your login shell; the hook and scripts run `bash` from PATH.
Linux and WSL already ship bash 5.

**Verify:** `bash -c "[ \"\${BASH_VERSINFO[0]}\" -ge 4 ]"` (exit 0)

## Doctor checks

| id | severity | offline | fix |
|---|---|---|---|
| `bash-version` | warn | runs | [bash4](#bash4) |
| `jq` | fail | runs | [install-jq](#install-jq) |
| `python3` | fail | runs | `Install python 3.9+ (apt-get install python3 / brew install python)` |
| `local-bin-path` | warn | runs | [local-bin-path](#local-bin-path) |
| `guard-hook` | fail | runs | `harness apply --provider claude` |
| `guard-denies-credentials` | fail | runs | `harness apply --provider claude` |

## Guides and sensors

Guides steer the agent before it acts; sensors detect at or after the action. Pairing: **paired**.

| side | kind | ref | note |
|---|---|---|---|
| guide | rule | `rules/00-conventions.md` | conventions and governance: PR-based, artefact ownership, secrets stay in their files |
| guide | permission | `permissions.toml` | denies reads of credential files in the provider's own permission system |
| guide | agent | `agents/Plan.md` | planning agent on the plan model; design only, never edits |
| guide | agent | `agents/Auto.md` | execution agent on the execute model under auto mode |
| sensor | guard | `guard.d/20-credentials.sh` | denies credential file reads and secret env dumps before they run |
| sensor | guard | `guard.d/30-git.sh` | denies default-branch pushes; asks on force-push and destructive git |
| sensor | doctor | `doctor_checks` | runtime prerequisites, and that the rendered guard parses and denies a credential read |
| sensor | test | `guard.d/tests.sh` | guard rows for both sections, including bypass attempts |
| sensor | test | `tests/run.sh` | full guard suite, helper drift, bash -n of every script |
| sensor | review-agent | `agents/code-reviewer.md` | inferential review of a diff against the conventions |
| sensor | provider-feature | `claude:auto-mode-classifier` | reviews the Auto agent's actions |

**Not covered:** The model policy in agents/Plan.md and agents/Auto.md is a guide only: no sensor checks which model a sub-agent ran on. The conventions rule has no guard section of its own (judgement: precedence, external content as data); the credentials and git guard sections enforce rules whose text lives in rules/00-conventions.md.

## Uninstall

Kept on uninstall: _nothing_

Removes the rendered hook, agents and managed instruction blocks only; your own CLAUDE.md prose outside the managed blocks stays.
<!-- generated:end -->
