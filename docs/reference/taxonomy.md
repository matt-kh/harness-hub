# Taxonomy

Every component the hub ships is classified the same way, so a human or an agent can tell
what it is, what it touches and how far it may go without a prompt, and so `harness lint` can
check it ([principle 6](../../principles/06-harness-engineering.md), variety reduction). The
vocabulary lives in `lib/harness/taxonomy.py`; the [catalog](../catalog.md) lists every
component with its facets, and each bundle page has a **Components** section.

## Ids

An id is derived from the path and never declared, so it cannot drift:
`<bundle>/<kind-dir>/<name>` with the extension stripped.

| kind | example id | from |
|---|---|---|
| bundle | `k8s` | `bundles/<b>/bundle.toml` |
| skill | `k8s/skills/k8s` | `skills/<name>/` |
| agent | `k8s/agents/k8s-triage` | `agents/<name>.md` |
| rule | `core/rules/00-conventions` | `rules/NN-<topic>.md` |
| guard section | `core/guard.d/30-git` | `guard.d/NN-<topic>.sh` |
| permission list | `core/permissions` | `permissions.toml` |
| MCP server | `jira/mcp/jira-mcp` | `[servers.<name>]` in `mcp.toml` |
| CLI | `jira/bin/jira` | the `[provides] bin` link name |
| installer | `github/install/gh` | `install/<tool>.sh` |
| doctor check | `core/doctor/jq` | `doctor_checks[].id` |
| manual step | `core/steps/install-jq` | `manual_steps[].id` |
| provider | `providers/claude` | `providers/<p>/provider.toml` |
| profile | `profiles/minimal` | `profiles/<p>.toml` |

Ids are stable: a component is never renamed to fit the scheme, because its name is also
its file name in five provider homes, its slash command and its doctor anchor. The bundle
names `providers` and `profiles` are reserved. A private bundle's ids use its own name, so
an id never reveals `local/`. Overrides in `[taxonomy.components]` address components at the
conventional paths above (`rules/NN-x.md`, `guard.d/NN-x.sh`, …); a component kept elsewhere
still gets an id and the bundle defaults, but cannot be overridden.

## Declared and derived facets

Declare only what cannot be derived — at most three words per component — and only in
`bundle.toml`, never in a skill's or agent's front matter (those files are copied into every
provider home).

```toml
[taxonomy]
domain = "kubernetes"          # required on public bundles
posture = "read-only"          # required on public bundles; inherited by skills, agents, CLIs, MCP servers
function = "client"            # optional default for skills and agents

[taxonomy.components]          # keys: the id without "<bundle>/"
"agents/k8s-triage" = { function = "investigate" }
"agents/infra-architect" = { function = "plan", note = "design only" }
```

- **domain** — what the component is about. Every component inherits the bundle's and may
  override it (a closing-keyword guard section in an SCM bundle is about the tracker).
- **function** — what it does for the agent. Declared for skills and agents; fixed for every
  other kind (rules, guard sections and permission lists *govern*, CLIs and MCP servers are
  *clients*, installers, doctor checks and manual steps are *setup*).
- **posture** — the strongest effect it has without a human prompt, weakest first:
  `read-only` < `local` < `label-gated`. Declared for skills, agents, CLIs and MCP servers;
  doctor checks are always read-only; rules, guard sections, permission lists, installers and
  manual steps take none (their decisions are derived, or a human performs them).
- **yields** — how the component steps aside for a repository-level equivalent
  ([principle 8](../../principles/08-user-level-by-design.md)); derived from the kind:
  `declaration` (reads `.harness.toml` `[owns]`: skills, guard sections), `name` (the
  provider resolves a name collision: agents), `text` (concatenated instructions whose text
  says the repository wins: rules), `config` (changed per key, never wholesale: permission
  lists), `never` (only `core/guard.d/20-credentials` and `core/permissions`), `n/a` (CLIs,
  MCP servers, installers, doctor checks, manual steps, definitions-only guard sections).

Derived, never declared: **kind** (the path), **control** (guide, sensor, or inferential
sensor, from `[harness]`), **model** (the front matter `model:`, shown as `plan`/`execute`
when it names the model policy), **yields** (above), **decisions** (`deny N · ask N · allow N` from `# rule:`
comments and permission lists), a bundle's **functions**, a profile's **domains** and
**posture**, a provider's **tier** and each kind's **reach**. Every facet is single-valued.

## What `harness lint` checks (rule `taxonomy`)

- Errors: a `[taxonomy.components]` key that names no component (the message lists the id
  forms; `harness catalog --bundle <b>` prints them); a posture on a kind that takes none; a
  function that contradicts a kind's fixed one; a component posture stronger than the
  bundle's; a bundle named `providers` or `profiles`; an unknown value (schema).
- Warnings: a public bundle without `[taxonomy]`; a public skill, agent, CLI or MCP server
  without a function or posture; a read-only agent whose front matter sets
  `permissionMode: auto`; a skill, agent, rule, guard section or non-empty permission list
  that `[harness]` declares as neither guide nor sensor (public bundles); the deprecated `[bundle].tags`.

Rule `yields` ([principle 8](../../principles/08-user-level-by-design.md)) checks that each
component carries its yield mechanism:

- Errors: a `declaration` guard section without its `repo_owns <id> <domain> && return 0`
  line, or with a wrong id or domain; a `repo_owns` line in a `never` or `n/a` section; a
  malformed or deny-listed `# repo-override:` comment, or two that give the same name
  different defaults.
- Warnings: a public skill whose preflight does not run `harness repo owns` (the Step 0
  paragraph); an agent or rule without its repository-level sentence.

## Naming new components

Nothing existing is renamed; new components follow these forms.

- **bundle** — the wrapped CLI's name (`jira`, `k8s`), or `<noun>-<noun>` across systems
  (`ticket-workflow`); an organisation's own bundles are `<org>-<topic>`.
- **skill** — a client skill is the CLI's name and ships a CLI of the same name; a workflow
  skill is `<verb>-<noun>`, invoked as `/<verb>-<noun>`.
- **agent** — `<domain-word>-<role-noun>`, the role noun mapping to one function
  (`k8s-triage`, `code-reviewer`); `Plan` and `Auto` keep their names because they override
  provider built-ins.
- **rule and guard section** — `NN-<topic>`; a rule and the guard section that enforces it
  share `NN-<topic>`; prefixes follow the bands in
  [ARCHITECTURE §3](../../ARCHITECTURE.md#3-bundles-bundlesname).
- **doctor check, manual step** — `<subject>-<aspect>` (`gh-auth`, `install-kubectl`);
  **MCP server** — `<system>-mcp`; **installer, provider** — the binary's name;
  **profile** — the audience or `<scm>-<tracker>`.

## Adding a value

A value exists only while a component uses it. To add one:

1. Add it to the enum in `schema/bundle.schema.json` and to `FACETS` in
   `lib/harness/taxonomy.py` with a one-line meaning (a unit test keeps the two equal).
2. Classify at least one component with it in its bundle's `[taxonomy]`.
3. Run `bin/harness docs generate` and `bin/harness lint`.
4. Add a CHANGELOG `[Unreleased]` entry under a `### Taxonomy` heading.

## Vocabulary

<!-- generated:begin source=lib/harness/taxonomy.py -->
### domain

| value | meaning | components using it |
|---|---|---|
| `base` | the harness itself: engine, credentials, conventions, core agents | 15 (core) |
| `scm` | source hosts, branches, MRs/PRs | 24 (core, github, gitlab) |
| `tracker` | tickets, issues, their state | 15 (github, gitlab, jira) |
| `delivery` | ticket-to-merge workflow spanning tracker and SCM | 8 (ticket-workflow) |
| `kubernetes` | clusters, Helm, GitOps, IaC targeting them | 18 (k8s) |
| `workspace` | docs, drive, sheets, mail | 15 (gdoc) |

### function

| value | meaning | components using it |
|---|---|---|
| `govern` | constrains the agent and says what to do instead | 24 (core, gdoc, github, gitlab, jira, k8s, ticket-workflow) |
| `client` | thin interface to one system | 7 (gdoc, jira, k8s) |
| `workflow` | multi-step governed procedure | 2 (ticket-workflow) |
| `investigate` | diagnoses to a root cause, never applies the fix | 1 (k8s) |
| `plan` | designs; read-only | 2 (core, k8s) |
| `execute` | implements autonomously | 1 (core) |
| `review` | assesses and reports | 2 (core, k8s) |
| `setup` | installs, verifies or configures once | 56 (core, gdoc, github, gitlab, jira, k8s, ticket-workflow) |

### posture

| value | meaning | components using it |
|---|---|---|
| `read-only` | reads only | 38 (core, gdoc, github, gitlab, jira, k8s, ticket-workflow) |
| `local` | edits the checkout and its own branches; other remote writes pass the guard | 1 (core) |
| `label-gated` | writes promptlessly only to agent-* artefacts; human ones ask | 6 (gdoc, jira, ticket-workflow) |

### yields

| value | meaning | components using it |
|---|---|---|
| `declaration` | returns early when the repository's .harness.toml owns its id or domain | 13 (core, gdoc, github, gitlab, jira, k8s, ticket-workflow) |
| `name` | the provider shadows it with a repository component of the same name | 6 (core, k8s) |
| `text` | concatenated with the repository's instructions, which come last and win | 7 (core, gdoc, github, gitlab, jira, k8s, ticket-workflow) |
| `config` | merged by the provider's permission system; a repository can add rules, never lift a deny | 6 (gdoc, github, gitlab, jira, k8s, ticket-workflow) |
| `never` | the developer's own credentials: no repository setting lifts it | 2 (core) |
| `n/a` | no repository-level equivalent | 61 (core, gdoc, github, gitlab, jira, k8s, ticket-workflow) |

### Facets by kind

| kind | id | control | domain | function | posture | model | decisions | yields |
|---|---|---|---|---|---|---|---|---|
| bundle | `<bundle>` | — | declared (required on public) | derived: union | declared (required on public) | — | — | — |
| skill | `<bundle>/skills/<name>` | derived: `[harness]` | inherited, overridable | declared (required) | declared (required) | derived: front matter | — | derived: `declaration` |
| agent | `<bundle>/agents/<name>` | derived: `[harness]` | inherited, overridable | declared (required) | declared (required) | derived: front matter | — | derived: `name` |
| rule | `<bundle>/rules/<name>` | derived: `[harness]` | inherited, overridable | fixed: govern | not allowed | — | — | derived: `text` |
| guard | `<bundle>/guard.d/<name>` | derived: `[harness]` | inherited, overridable | fixed: govern | not allowed | — | derived: `# rule:` comments | derived: `declaration` (`n/a` without `# rule:` comments; `never` for `core/guard.d/20-credentials`) |
| permission | `<bundle>/permissions` | derived: `[harness]` | inherited, overridable | fixed: govern | not allowed | — | derived: allow/ask/deny lists | derived: `config` (`never` for `core/permissions`) |
| mcp | `<bundle>/mcp/<name>` | — | inherited, overridable | fixed: client | declared (required) | — | — | derived: `n/a` |
| bin | `<bundle>/bin/<name>` | — | inherited, overridable | fixed: client | declared (required) | — | — | derived: `n/a` |
| installer | `<bundle>/install/<name>` | — | inherited, overridable | fixed: setup | not allowed | — | — | derived: `n/a` |
| doctor | `<bundle>/doctor/<name>` | derived: `[harness]` | inherited, overridable | fixed: setup | fixed: read-only | — | — | derived: `n/a` |
| step | `<bundle>/steps/<name>` | — | inherited, overridable | fixed: setup | not allowed | — | — | derived: `n/a` |
| provider | `providers/<name>` | — | — | — | — (tier instead) | — | — | — |
| profile | `profiles/<name>` | — | derived: union | — | derived: max | — | — | — |

### Reach by kind

| kind | reach |
|---|---|
| bundle | selected in `[hub].bundles` or through a profile; rendered into every active provider. |
| skill | native on claude, codex, copilot, gemini, opencode. |
| agent | native on claude, copilot; inlined on codex, gemini, opencode. |
| rule | native on claude, codex, copilot, gemini, opencode. |
| guard | enforced on claude; partial on copilot, gemini; advisory on codex, opencode. |
| permission | native on claude; advisory on codex, copilot, gemini; none on opencode. |
| mcp | native on claude, codex, copilot, gemini; none on opencode. |
| bin | provider-independent: linked into `~/.local/bin`, callable by every provider and by you. |
| installer | provider-independent: run by `harness install <tool>`. |
| doctor | provider-independent: run by `harness doctor`. |
| step | provider-independent: done once by a human; `harness steps --pending` lists the open ones. |
| provider | the tier: enforced (guard hook with ask), partial (guard hook, ask mapped), advisory (no hook). |
| profile | a named bundle and provider selection: `[hub].profile` or `harness bootstrap --profile`. |
<!-- generated:end -->
