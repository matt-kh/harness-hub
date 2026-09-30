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
tools) and `build/guard.env` (flat `KEY=value` lines the guard sources at start-up).

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

Two rules decide which instruction or guard wins:

1. **Repository-level beats user-level, wholesale.** A repo's own `CLAUDE.md` / `AGENTS.md`,
   `.claude/` settings, skills, hooks or documented conventions for the same action
   **replace** the user-level behaviour for sessions in that repo; they are never merged.
   User-level skills detect a repo-level equivalent in their preflight and hand over to it.
2. **Hooks stack, so a repo cannot un-deny.** Provider hooks from all levels run; a user-level
   deny cannot be lifted by a repo hook. Repos therefore switch off individual user-level guard
   behaviours through environment overrides in their own settings (for Claude Code,
   `.claude/settings.json` → `"env"`), for example:

   | Variable | Effect in that repo |
   |---|---|
   | `WORK_TICKET_ALLOW_DEFAULT_PUSH_RE` | regex on the repo path; a push to its default branch asks instead of denying (personal repos) |
   | `WORK_TICKET_ALLOW_TRANSITION=1` | ticket state changes on human tickets ask instead of denying (repos whose own workflow transitions tickets) |
   | `WORK_TICKET_KEY_IN_BRANCH=1` | declares the repo puts ticket keys in branch names |
   | `WORK_TICKET_LABELED_DECISION` | `allow` or `ask` for writes to agent-labelled artefacts |

   The full list, with defaults, is in the [hook policy reference](reference/hook-policy.md).

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
| `~/harness-hub/build/` | engine scratch output; gitignored, safe to delete |
| `~/.claude`, `~/.gemini`, `~/.copilot`, `~/.codex`, `~/.config/opencode`, `~/.agents/skills` | the providers; the hub writes only what its state file lists |
| `~/.local/bin` | CLI links and pinned tools |
| `~/.local/state/harness/backups/` | backups of everything `apply` modified |
