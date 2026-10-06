# Concepts

The hub turns **one config file** plus **bundles** into files inside each **provider's home
directory**, and remembers exactly what it wrote. Everything else follows from that.

```text
local/harness.toml ─┐
bundles/*          ─┼─► render ─► build/rendered/<provider>/…  ─► plan ─► apply ─► ~/.claude, ~/.gemini, …
local/bundles/*    ─┘                                               │            └► <home>/.harness-state.json
                                                          diff against live files + state
```

## Config: the single source of truth

`local/harness.toml` (gitignored) holds everything specific to you or your organisation:
identity, which bundles and providers are active, hosts, Jira field ids, cluster regexes, the
trust text for Claude Code's auto mode. **No secrets**: validation rejects secret-looking keys
and values, and tokens stay in the files their own tools write
([secrets reference](reference/secrets.md)).

Layers, lowest to highest precedence:

1. `bundles/<b>/defaults.toml` of every active bundle
2. an org overlay, `local/harness.org.toml` (seeded by `harness init --from <path|git url>`),
   so one team can ship blessed hosts and regexes to everyone
3. `local/harness.toml`
4. `local/harness.user.toml` — per-machine tweaks
5. environment `HARNESS_<SECTION>_<KEY>`, e.g. `HARNESS_JIRA_URL`

`harness config explain jira.url` prints a key's description, type, default, the bundles that
need it and which layer the current value came from. The path is `--config PATH` >
`$HARNESS_CONFIG` > `$HARNESS_HOME/local/harness.toml`.

The engine compiles the layered result to `build/config.json` (for itself and the python
tools) and `build/guard.env` (flat `KEY=value` lines the guard parses at start-up — never
sourced; a variable already set in the environment wins).

## Bundles

A bundle is one capability, in a fixed layout ([ARCHITECTURE §3](../ARCHITECTURE.md#3-bundles-bundlesname)):
instruction fragments (`rules/`), complete skills (`skills/`), sub-agents (`agents/`), guard
sections (`guard.d/`), permission lists, MCP servers, CLIs for `~/.local/bin`, installers,
doctor checks and **manual steps**. `bundle.toml` declares all of it, plus the config keys and
secrets it needs. Bundles depend on (`depends_on`), recommend, or conflict with each other.

`{{ section.key }}` is the only template syntax. It works in rules, agents, skill Markdown and
manifest strings; scripts are copied verbatim and read their settings from the environment.
A missing key is an error at plan time, never a silent blank.

**Private bundles** live in `local/bundles/<org>/` with the same layout and are enabled the
same way (`hub.bundles`). That is where your cluster inventory, your Jira issue-type rules
and your extra guard rules go.

## Guides and sensors

The hub follows the vocabulary of Martin Fowler's
[harness engineering](https://martinfowler.com/articles/harness-engineering.html) article: an
agent is a model plus a harness, and the harness has two kinds of control
([principle 6](../principles/06-harness-engineering.md)).

| | Guides (feedforward) | Sensors (feedback) |
|---|---|---|
| When | before the agent acts | at or after the action |
| Purpose | raise the chance it is right the first time | detect and correct when it is not |
| In a bundle | `rules/`, `skills/`, `permissions.toml`, `agents/`, templates | `guard.d/`, doctor checks, `guard.d/tests.sh` and `tests/`, lint rules, review agents |
| Declared as | `[harness] guides = [{kind, ref, note}]` | `[harness] sensors = [{kind, ref, note}]` |

- **Computational** sensors are deterministic and cheap: the guard, `harness lint`, test rows,
  `harness doctor`. They run on every change or every command.
- **Inferential** sensors are semantic and slower: the core bundle's code-reviewer agent.
- **The guard is a sensor that fires before the action.** It reads the shell command text,
  decides `allow | ask | deny | pass`, and its reason says what to do instead, so the message
  also steers the next attempt.
- **Pairing.** Each bundle declares both lists and a `coverage_note` for what the pairing does
  not cover. `harness lint` warns on guides without sensors, sensors without guides, and guard
  reasons without an alternative. Each bundle page and the
  [harness coverage](reference/harness-coverage.md) reference render the tables.
- **The steering loop.** When an agent repeats a mistake, improve a guide or a sensor so it
  does not recur; contributions to this repo are that loop
  ([CONTRIBUTING](../CONTRIBUTING.md#principles-first)).
- **Provider tier limits sensors.** On advisory providers (Codex, OpenCode) the guard does not
  run; only the guides apply ([capability matrix](reference/capability-matrix.md)).

## Components, ids and taxonomy

Everything a bundle ships is a **component** — rule, skill, agent, guard section, permission
list, MCP server, CLI, installer, doctor check, manual step — and each is classified the same
way ([taxonomy](reference/taxonomy.md)):

- **Id**, derived from the path and never declared: `k8s/agents/k8s-triage`,
  `core/guard.d/30-git`, `jira/mcp/jira-mcp`; bundles are bare (`k8s`), providers and
  profiles are `providers/<p>` and `profiles/<p>`. Ids are stable; nothing is renamed to fit.
- **Declared facets**, in the bundle's `[taxonomy]` table only: **domain** (base, scm,
  tracker, delivery, kubernetes, workspace), **function** (govern, client, workflow,
  investigate, plan, execute, review, setup) and **posture**, the strongest effect without a
  human prompt (read-only < local < label-gated). The bundle sets defaults; overrides name a
  component by its id without the bundle prefix.
- **Derived facets**: kind, control (guide or sensor, from `[harness]`), model (front
  matter), decisions (`# rule:` comments and permission lists), a provider's tier, and where
  each kind of component reaches.

`harness lint` (rule `taxonomy`) keeps the classification complete and consistent; the
[catalog](catalog.md) and `harness catalog` list every component with its facets, and each
bundle page has a **Components** section. The taxonomy lives in `bundle.toml` only: rendered
provider files are unchanged by it.

## Providers

A provider adapter (`providers/<name>/provider.toml`) is data: where each kind of artefact
goes in that product's home directory and how it is written. The engine has no
provider-specific code paths. Adapters also declare **capabilities**, which give each
provider a tier — *enforced*, *partial* or *advisory*
([capability matrix](reference/capability-matrix.md)).

## Render, plan, apply, sync, state

| Command | What it does | Writes to provider homes? |
|---|---|---|
| `harness render --out DIR` | expands everything into a tree under `DIR`, deterministically (sorted keys, LF, no timestamps) | no |
| `harness plan` | renders to a temp tree and compares with the live files and the state file: `create`, `update`, `skip`, `conflict`, `orphan` per path, with diffs | no |
| `harness apply` | executes the plan; backs up every file it modifies to `~/.local/state/harness/backups/<ts>/`; writes the state file | yes |
| `harness sync` | classifies each managed path `clean`, `drifted`, `missing` or `foreign`; `--adopt` pulls a drifted file back into its source bundle | only with `--adopt` |
| `harness uninstall` | removes only paths listed in the state file, honours every bundle's `[uninstall].keeps` | yes |

The state file, `<provider home>/.harness-state.json`, records each managed path with its
sha256, owning bundle and write mode. That is how the hub knows what it owns, and why it can
promise:

- it never reads or writes a provider's runtime state (sessions, projects, credentials,
  plugins, memory);
- a file that exists but is not in the state (*foreign*) is kept unless you `--adopt` it;
- nothing is deleted without a backup, and never outside the managed set;
- `plan` twice in a row prints `0 changes`.

## Write modes and managed blocks

| Mode | Used for | Behaviour |
|---|---|---|
| `dir`, `file` | skills, agents, hook scripts | copied; tracked by sha256 |
| `managed-block` | `CLAUDE.md`, `GEMINI.md`, `AGENTS.md`, `copilot-instructions.md` | inserts or replaces a block between markers; everything outside is untouched |
| `json-merge` | `settings.json`, MCP config files | deep merge; only the adapter's `owner_keys` are replaced; on conflict **the user wins** and the plan shows `CONFLICT` |
| `toml-block` | Codex `config.toml` | a fenced managed table |

A managed block looks like this; edit outside the markers freely:

```markdown
My own notes for every session stay here.

<!-- harness:begin bundle=core file=rules/10-conventions.md -->
… rendered by harness-hub; edit bundles/core/rules/10-conventions.md instead …
<!-- harness:end bundle=core file=rules/10-conventions.md -->
```

If you edit inside a block, `sync` reports it as drifted and `sync --adopt` moves your edit
into the bundle source so it survives the next `apply` (and can be committed).

## Precedence

The hub is a **user-level harness by design** ([principle 8](../principles/08-user-level-by-design.md)):
everything it renders is a baseline that yields to an equivalent repository-level harness,
wholesale and never merged. A component yields in one of three ways:

1. **Declaration.** The repository's `.harness.toml` names the domains or component ids it
   owns (`[owns]`) and sets allow-listed overrides (`[overrides]`). The guard reads it from
   the hook's working directory; skills read it at preflight; `harness repo` shows the effect.
2. **Name.** Where the provider resolves a collision by name (Claude Code sub-agents), the
   repository's component replaces the hub's. Note the opposite for Claude Code skills: a
   hub skill shadows a repository skill of the same name until the repository turns it off
   with `skillOverrides`.
3. **Text and config.** Instruction files are concatenated, never replaced: the hub's rule
   text tells the agent the repository's wins where they differ. Provider `env` overrides
   win per key: environment > `.harness.toml` > `guard.env` > default.

The exception: the developer's own credentials never yield — the denies on reading
credential files (`core/guard.d/20-credentials`, `core/permissions`) and the `# never-yields:`
preludes (commands that print a stored credential; the ask on writing `.harness.toml`). Details, the Claude Code
facts table and the `.harness.toml` reference: [repository-level harnesses](repo-level.md).

## The `agent-*` label model

Agents may write **without prompting** only to artefacts that are marked as agent-owned;
everything purely human-written is protected. The marker is a label on tickets, issues, MRs
and PRs, and a Drive file property for Google Docs:

| Label | Set when | Meaning |
|---|---|---|
| `agent-worked` | an agent starts working a ticket, or opens an MR/PR | the agent may comment, edit and label promptlessly |
| `agent-created` | an agent creates a sub-ticket while working a parent | provenance: made by an agent as part of a worked ticket |
| `agent-drafted` | an agent drafts a new ticket from a free-text request | provenance: draft for a human to review |

Names and the matching regex (`^agent-`) are config (`core.agent_labels`,
`core.agent_label_re`). Creating an artefact requires a provenance label; adding an `agent-*`
label to an existing human ticket is the explicit, visible act of adopting it. Ticket **state**
stays human-only regardless of labels unless a repo opts in. Details:
[governance](governance.md).

## Where things live

| Path | Owner |
|---|---|
| `~/harness-hub` (`$HARNESS_HOME`) | this repository; `git pull` / `harness upgrade` |
| `~/harness-hub/local/` | you; gitignored, optionally its own private git repo |
| `~/harness-hub/build/` | build products of `local/harness.toml` (skills read `config.json`); gitignored, regenerated by `harness apply` |
| `~/.cache/harness/build/<hash>/` | build products of any other config (`--config`, fixtures, CI); safe to delete |
| `~/.claude`, `~/.gemini`, `~/.copilot`, `~/.codex`, `~/.config/opencode`, `~/.agents/skills` | the providers; the hub writes only what its state file lists |
| `~/.local/bin` | CLI links and pinned tools |
| `~/.local/state/harness/backups/` | backups of everything `apply` modified |
