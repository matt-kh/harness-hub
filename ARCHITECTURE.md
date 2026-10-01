# Architecture

harness-hub is a bootstrap kit for **agent harnesses**: the instructions, skills, sub-agents,
permission lists, MCP servers and command guards that make an AI coding agent behave like a
disciplined colleague. One config file describes *your* organisation; the hub renders it into
every agent provider you use.

```
                bundles/*  (public, generic)        local/  (gitignored, yours)
                ────────────────────────────        ─────────────────────────────
                rules, skills, agents, guard        harness.toml, private bundles
                rules, permissions, manifests       (org hosts, field ids, trust)
                              │                                   │
                              └──────────────┬────────────────────┘
                                             ▼
                                 harness render / plan / apply
                                             │
        ┌──────────────┬──────────────┬──────┴───────┬──────────────┬──────────────┐
        ▼              ▼              ▼              ▼              ▼              ▼
    ~/.claude      ~/.gemini      ~/.copilot     ~/.codex     ~/.config/opencode  ~/.local/bin
   (Claude Code)  (Gemini CLI)   (Copilot CLI)  (Codex CLI)   (OpenCode / Kilo)   (CLIs)
```

Provider directories are **render targets**. The hub never lives inside them, never touches
their runtime state (sessions, credentials, plugins, memory), and records every file it writes
in a state file so `plan`, `sync`, `doctor` and `uninstall` know exactly what they own.

## Contracts

The sections below are normative. Bundle authors, provider adapters and the engine all depend
on them; change them only with a schema version bump and a CHANGELOG "Migration" entry.

### 1. Repository layout

```
bootstrap                 curl-able entry: exec bin/harness bootstrap "$@"
bin/harness               bash launcher: checks python3 >= 3.9, jq, git; exec python3 -m harness
lib/harness/              engine, python stdlib only (no pip); _vendor/tomli for python < 3.11
schema/                   JSON Schema (2020-12 subset) for harness.toml, bundle.toml, provider.toml
bundles/<name>/           one bundle per capability (see §3)
providers/<name>/         one adapter per agent product (see §4)
profiles/<name>.toml      named bundle+provider selections for `bootstrap --profile`
tools/<tool>.lock.json    pinned tool downloads: version + sha256 per os/arch
tools/gate/               private-identifier gate (patterns, allowlist, script)
templates/                harness.toml template (generated from schema)
tests/                    engine unit tests, fakes/bin/*, fixtures, smoke scripts
docs/                     hand-written pages with generated regions (see §8)
local/                    GITIGNORED private overlay (see §2)
build/                    GITIGNORED render products (config.json, guard.env, rendered tree)
```

### 2. Configuration: `local/harness.toml`

Single source of truth for everything organisation- or person-specific. TOML, comments
allowed, **secrets never** (validation rejects keys named `*token*|*secret*|*password*|*bearer*`
and 30+ character high-entropy strings; secrets live in the files the tools own, listed in
`docs/reference/secrets.md`).

Layering, lowest to highest precedence:

1. `bundles/<b>/defaults.toml` for every active bundle
2. org overlay file passed to `harness init --from` (stored as `local/harness.org.toml`)
3. `local/harness.toml`
4. `local/harness.user.toml` (machine-specific)
5. environment `HARNESS_<SECTION>_<KEY>` (e.g. `HARNESS_JIRA_URL`)

Resolution: `--config PATH` > `$HARNESS_CONFIG` > `$HARNESS_HOME/local/harness.toml`.
`HARNESS_HOME` defaults to the directory that contains `bin/harness`.

Canonical keys (bundles declare what they need under `[requires.config]`; the compiled schema
is the union):

```toml
schema_version = 1

[identity]
email = "you@example.com"

[hub]
bundles   = ["core", "github", "ticket-workflow"]
providers = ["claude"]
# profile = "github-dev"            # alternative to listing bundles; explicit lists win

[core]
default_branch_re = "^(master|main)$"   # git push here is denied (repo can opt in to ask)
ticket_example    = "PROJ-123"          # used in reasons and docs
model_policy      = { plan = "fable", execute = "opus" }
agent_labels      = { worked = "agent-worked", created = "agent-created", drafted = "agent-drafted" }
agent_label_re    = "^agent-"

[gitlab]
host = "gitlab.example.com"
personal_repo_re = ""                   # top-level paths where a default-branch push asks instead of denying

[github]
host  = "github.com"
login = "octocat"

[jira]
url  = "https://jira.example.com"
kind = "server"                         # server | cloud (only server is implemented)
link_types = ["relates", "blocks", "issue split"]
[jira.fields.PROJ]                      # per project, from `jira fields PROJ`
problem_description = "customfield_20000"
[[jira.issue_types]]                    # optional per-org type rules for create-ticket
name = "Task"; standalone = true; requires = []
[jira.mcp]
enabled = true

[k8s]
prod_re          = "(^|[-_./:])(prod|production)([-_./:]|$)"
gitops_root      = "~/dev/gitops"
gitops_repo_match = "gitops"
clusters_doc     = "local/bundles/<org>/references/clusters.md"
broken_contexts  = []

[google]
domain = "example.com"

[trust]                                 # rendered into Claude Code autoMode.environment
source_control = ["github.com/octocat/*"]
domains        = []
notes          = ""

[providers.gemini]
ask_as = "deny"                         # providers without an "ask" decision: deny | allow
[providers.copilot]
ask_as = "deny"

[doctor]
warn_only = []                          # doctor check ids downgraded to WARN
```

The engine compiles the layered result to `build/config.json` (for itself and for python
tools) and `build/guard.env` (flat `KEY=value` lines sourced by the guard; see §5). Every
bundle contributes its env names in `[provides.env]`.

Build directory: `$HARNESS_BUILD_DIR` if set; else `<hub>/build` only when the config is the
canonical `<hub>/local/harness.toml` (by realpath), because rendered skills read
`${HARNESS_HOME}/build/config.json`; any other config (fixtures, CI, experiments) compiles to
`${XDG_CACHE_HOME:-~/.cache}/harness/build/<sha1(realpath(config))[:12]>/`. `harness test`
gives every child suite a fresh temporary `HARNESS_BUILD_DIR`, so tests never overwrite the
live compiled config. `harness status` prints the resolved directory; `doctor` and
`steps --pending` export `HARNESS_CONFIG_JSON` pointing into it.

### 3. Bundles: `bundles/<name>/`

```
bundle.toml               manifest (schema/bundle.schema.json)
defaults.toml             default config values this bundle needs
rules/NN-<topic>.md       instruction fragments; rendered as managed blocks (templated)
skills/<skill>/           complete skills, Agent Skills layout (SKILL.md + scripts/ + references/)
skill-fragments/<skill>/  files overlaid into a skill owned by another bundle (same relative paths)
agents/<name>.md          sub-agent definitions (Claude Code front-matter; other providers inline)
guard.d/NN-<topic>.sh     guard rule sections (bash, sourced by concatenation, see §5)
guard.d/tests.sh          guard test rows for this bundle (uses the shared t/tc/tr/g helpers)
permissions.toml          [permissions] allow/ask/deny lists in Claude Code rule syntax
mcp.toml                  [servers.<name>] command/args/env; secrets only as env_files = { VAR = "~/path" }
bin/                      scripts exposed in ~/.local/bin (symlinked to the rendered copy)
install/<tool>.sh         tool installers used by `harness install <tool>`
doctor/*.sh               check scripts (exit 0 ok, 1 warn, 2 fail)
tests/run.sh              bundle test entry (skills' own tests live under skills/*/scripts/tests)
```

Manifest (`bundle.toml`):

```toml
[bundle]
name = "github"; schema_version = "1"; summary = "…"; description = """…"""
depends_on = ["core"]; recommends = ["ticket-workflow"]; conflicts_with = []; any_of = []
tags = []; owners = []; docs = "docs/bundles/github.md"; stability = "stable"

[requires.binaries.gh]
min_version = "2.60.0"; version_cmd = "gh --version"; version_regex = 'gh version ([0-9.]+)'
install = "gh"; optional = false; why = "…"

[requires.config."github.login"]
type = "string"; required = true; pattern = '^[A-Za-z0-9-]+$'; description = "…"; example = "octocat"

[requires.secrets.gh_token]
where = "~/.config/gh/hosts.yml"; written_by = "gh auth login"; mode = "0600"; description = "…"; rotate = "docs/runbooks/rotate-github-token.md"

[provides]
rules = ["rules/40-github.md"]; skills = []; skill_fragments = ["skill-fragments/work-ticket/**"]
agents = []; guard_rules = ["guard.d/60-github.sh"]; permissions = "permissions.toml"; mcp = ""
bin = []; env = { WORK_TICKET_GH = "gh" }

[[manual_steps]]
id = "gh-auth"; title = "…"; once_per = "account"; needs = ["browser"]; minutes = 3
why = "…"; how = """markdown, may use {{ github.host }}"""
[manual_steps.verify]
cmd = "gh auth status --hostname {{ github.host }}"; expect = { exit = 0, stdout_regex = "Logged in" }
unblocks = ["gh-auth"]

[[doctor_checks]]
id = "gh-auth"; severity = "fail"; cmd = "…"; expect = { exit = 0 }; timeout = 10
offline_skip = true; fix = "gh-auth"; providers = []

[uninstall]
keeps = ["~/.config/gh/**"]; notes = "…"
```

Rules:
- `{{ section.key }}` is the only template syntax (spaces required, lowercase dotted key). It is
  expanded in `rules/*.md`, `agents/*.md`, `*.md` under `skills/`, and in manifest strings
  (`how`, `cmd`). Scripts are copied verbatim. A missing key with no default is a `plan` error.
- `doctor_checks[].fix` must name a `manual_steps[].id` in the same bundle or be a literal
  command; `harness lint` fails on dangling ids.
- Numeric prefixes order rule fragments and guard sections across bundles
  (`10` k8s, `20` credentials, `30` git, `40` closing keywords, `50` gitlab, `60` github,
  `70` jira, `80` gdoc, `90+` private).

### 4. Providers: `providers/<name>/`

```
provider.toml             where each artifact goes and how it is written
shim.sh                   hook envelope translation (only if the provider has command hooks)
README.md                 verified-against version and date, quirks
tests/*.in.json,*.out.json  shim fixtures
```

```toml
[provider]
name = "claude"; binary = "claude"; version_cmd = "claude --version"; min_version = "2.0.0"; home = "~/.claude"

[targets]
instructions = { path = "~/.claude/CLAUDE.md", mode = "managed-block" }
skills       = { path = "~/.claude/skills/<name>", mode = "dir" }
agents       = { path = "~/.claude/agents/<name>.md", mode = "file" }
settings     = { path = "~/.claude/settings.json", mode = "json-merge", owner_keys = ["hooks", "permissions", "env", "autoMode"] }
hooks        = { path = "~/.claude/hooks", mode = "dir", event = "PreToolUse", matcher = "Bash", shim = "" }
mcp          = { mode = "json-merge", path = "~/.claude.json", key = "mcpServers" }

[capabilities]
hook_enforced = true; permissions = "native"; ask = true; skills = "native"; agents = "native"; mcp = "native"
```

Write modes: `dir` and `file` (copy, tracked by sha256), `managed-block` (insert/replace a
block delimited by `<!-- harness:begin bundle=<b> file=<f> -->` … `<!-- harness:end bundle=<b> file=<f> -->`,
everything outside untouched), `json-merge` (deep merge; only `owner_keys` are replaced, every
other key preserved; on conflict the user wins and the plan shows `CONFLICT`), `toml-block`
(a fenced managed table in Codex `config.toml`).

### 5. Guard

The guard is a bash script that decides `allow | ask | deny | pass` for a shell command.
Its **neutral envelope is the Claude Code PreToolUse format** so that the existing 500+ test
rows stay valid:

```
stdin : {"tool_name":"Bash","tool_input":{"command":"…"},"cwd":"…"}
stdout: {"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow|ask|deny","permissionDecisionReason":"…"}}
        (nothing on stdout = pass, let the provider's own permission system decide)
exit  : 0 always; malformed input → deny (fail closed)
```

`bundles/core/guard/engine.sh` holds the input parsing, decision helpers (`allow`, `ask`,
`deny`, `defer`, `pending_allow`, `flush`) and the final flush. Each bundle's
`guard.d/NN-*.sh` is a section that only uses those helpers. **Render concatenates**
`engine.sh` + active sections sorted by prefix + `engine-flush.sh` into one
`hooks/guard-bash.sh` per provider home, so runtime cost equals today's single file and the
audit surface is one file. The concatenated script sources `hooks/guard.env` (from
`build/guard.env`) at start; environment variables already set win.

Provider shims translate envelopes:

| provider | stdin | decision mapping |
|---|---|---|
| claude | native | native |
| gemini | `{tool_name:"run_shell_command", tool_input:{command}, cwd}` → neutral | `allow`→`{decision:"allow"}`, `deny`→`{decision:"deny",reason}`, `ask`→ per `providers.gemini.ask_as` |
| copilot | `{toolName:"bash", toolArgs:"<json string>"}` → neutral | `deny`→`{permissionDecision:"deny",permissionDecisionReason}`, `ask`→ per `providers.copilot.ask_as` |
| codex, opencode | no command hook | advisory only; `harness status --matrix` says so |

Test rows live in `bundles/<b>/guard.d/tests.sh` and use the shared helpers from
`bundles/core/guard/tests/lib.sh` (`t EXPECTED 'cmd'`, `tc EXPECTED cwd 'cmd'`,
`tr EXPECTED 'reason-regex' 'cmd'`, `g` for git-stub state). `harness test guard` builds the
concatenated script for **all** bundles into `build/` and runs every bundle's rows against it
with stubs from `bundles/core/guard/tests/stubs/` on `PATH`.

### 6. Engine commands

`bootstrap`, `init`, `bundles`, `config validate|get|set|explain|migrate`, `plan`, `apply`,
`sync`, `render`, `doctor`, `status [--matrix]`, `install <tool>`, `upgrade`, `uninstall`,
`test [suite]`, `lint`, `docs generate|check`, `steps [--pending]`, `version`. Global flags:
`--config`, `--home`, `--json`, `--offline`, `--yes`, `--dry-run`. Environment: `HARNESS_HOME`,
`HARNESS_CONFIG`, `HARNESS_OFFLINE`, `NO_COLOR`.

`plan` renders to a temporary tree and diffs against the live targets and the state file:
`create | update | skip | conflict | orphan` per path. `apply` executes the plan, backing up
every modified file to `~/.local/state/harness/backups/<timestamp>/` and writing
`<provider home>/.harness-state.json` (`{version, applied_at, files: {path: {sha256, bundle, mode}}}`).
`sync` (and `status`) classifies each managed path as `clean | drifted | missing | foreign`;
merged targets (`json-merge`, `managed-block`, `toml-block`) compare only the owned values or
blocks, so keys and text the provider or user own never count as drift. It can adopt a
drifted rendered file back into its source bundle (`--adopt`) so that edits made through the
provider land in the repo.

Rendering is deterministic: sorted keys, LF endings, no timestamps inside rendered content.

### 7. State, backups, safety

- The engine only ever writes paths it declared in the plan. Runtime state of a provider
  (`projects/`, `sessions/`, `.credentials.json`, `plugins/`, `skills/synced/`, memory) is
  never read, listed or written.
- Foreign files (present, not in state) are kept; `--adopt PATH` backs up and replaces; nothing
  is deleted without a backup and never outside the managed set.
- `uninstall` removes only state-listed paths and honours every bundle's `[uninstall].keeps`.

### 8. Documentation

Hand-written pages with generated regions:
`<!-- generated:begin source=bundles/github/bundle.toml -->` … `<!-- generated:end -->`.
`harness docs generate` rewrites the regions from manifests, provider adapters, the CLI help
and the `# rule: <pattern> -> <decision> : <reason>` comments in guard sections;
`harness docs check` fails when a region is stale. Manual steps in `docs/bundles/<b>.md` use
`### <id> — <title>` headings so `doctor` can link `docs/bundles/<b>.md#<id>`.

### 9. Portability

Supported: Linux, WSL2, macOS. Bash 3.2 must parse every script (`bash -n` in CI on macOS);
bash ≥ 4 features (`mapfile`, `declare -A`) are allowed only behind a `BASH_VERSINFO` check
that `doctor` reports. Never rely on GNU-only `timeout`, `readlink -f`, `sed -i`, `stat -c`,
`sha256sum`: use the `hn_timeout`, `hn_realpath`, `hn_sha256` helpers from
`bundles/core/lib/compat.sh` or python. All python is stdlib and runs on 3.9+.
Regexes in `sed`/`awk` are POSIX ERE only: BSD sed has no `\s \S \b \w \< \>` (they match the
literal letter; use `[[:space:]]`, `[^[:alnum:]_]`, …). Brace a variable that is directly followed
by a non-ASCII character (`"${var}—"`, not `"$var—"`): macOS ctype counts bytes ≥ 0x80 as
identifier characters, so the unbraced form names another, unset variable. `bundles/core/tests/run.sh`
checks both.
