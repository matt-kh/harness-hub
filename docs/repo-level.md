# Repository-level harnesses

What the hub does inside your repository, how to tell it what your repository owns, and what
each provider does when the hub's components and your repository's collide
([principle 8](../principles/08-user-level-by-design.md)).

## What the hub does in your repository

Everything the hub installed is user-level: a baseline that yields to your repository's own
harness for every concern you cover, wholesale — except denies on reading the developer's own
credential files, which are not yours to lift.

Your repository-level harness is whatever your repository ships for its agents: `CLAUDE.md` /
`AGENTS.md`, `.claude/` or the provider's equivalent (skills, agents, hooks, settings), and an
optional `.harness.toml`. Nothing is merged: for a given concern either the hub's component
runs or yours does. A hub component yields in one of three ways:

- **Declaration.** Your `.harness.toml` names the domains or component ids your harness owns.
  The hub's guard reads it from the hook's working directory and skips every section you own;
  the hub's skills read it at preflight and hand over before they ask, label or write
  anything.
- **Name.** Where the provider resolves a collision by name, your component of the same name
  replaces the hub's (Claude Code sub-agents). Claude Code skills resolve the other way; see
  [below](#claude-code-what-stacks-what-shadows).
- **Text and config.** Instruction files are concatenated, never replaced, so the hub's rule
  text tells the agent that your repository's text wins where the two differ. Settings merge
  per key: a provider `env` override wins over the hub's defaults.

| Component kind | Yields by | Effect in your repository |
|---|---|---|
| skill | `declaration` | stops after its read-only preflight when you own its id or domain, or ship a skill for the same workflow; names yours and hands over |
| guard section | `declaration` | emits nothing (pass) when you own its id or domain, so the provider's own rules and your hook decide |
| agent | `name` | your agent of the same name runs instead (where the provider resolves agents by name) |
| rule | `text` | stays in the agent's context; its text says your instructions win where they differ |
| permission list | `config` | merged by the provider; you can add entries, never lift a deny |
| credential denies | `never` | always apply: `core/guard.d/20-credentials`, `core/permissions`, and the `# never-yields:` preludes (commands that print a stored credential; the ask on shell writes to `.harness.toml`) |
| CLI, MCP server, installer, doctor check, manual step | `n/a` | nothing repository-level corresponds |

The generated [reference at the end of this page](#reference-what-yields) lists every
component with its `yields` value.

## Declaring ownership: `.harness.toml`

`.harness.toml` sits at the repository root (the directory holding `.git`, whether that is a
directory or a worktree's `.git` file). It is provider-neutral: the same file steers the
guard under every provider that runs it and the hub's skills under every provider.

```toml
# .harness.toml — repository-level harness declaration (harness-hub, principle 8).
# Provider-neutral: the hub's guard reads it from the hook's cwd, its skills at preflight.
# Commit it. No secrets, no hostnames needed.
[repo]
# optional: a name for this repository's harness
name = "shop"
# optional: where your own harness is described
harness = "docs/agent-workflow.md"

[owns]
# Domains this repository's own harness covers: every hub component in them yields here.
# Values: base, scm, tracker, delivery, kubernetes, workspace (docs/reference/taxonomy.md).
domains = ["delivery"]
# Single components by id (`harness catalog`) when a whole domain is too much.
components = ["core/guard.d/30-git"]

[overrides]
# Allow-listed WORK_TICKET_* guard settings only (docs/reference/hook-policy.md#repo-overrides).
# A provider env override of the same name (.claude/settings.json "env") wins per key.
# transitions on human tickets ask instead of deny
WORK_TICKET_ALLOW_TRANSITION = "1"
# this repo puts ticket keys in branch names
WORK_TICKET_KEY_IN_BRANCH = "1"
# allow | ask for writes to agent-labelled artefacts
WORK_TICKET_LABELED_DECISION = "allow"
```

`harness repo` prints what the file changes; commit the file; nothing in it is a secret.

- **`[repo]`** is informational: a name and a pointer to where your own harness is described.
- **`[owns] domains`** takes the taxonomy domains (`base`, `scm`, `tracker`, `delivery`,
  `kubernetes`, `workspace`; [taxonomy](reference/taxonomy.md)). Every hub component in an
  owned domain yields here.
- **`[owns] components`** takes component ids as `harness catalog` prints them
  (`core/guard.d/30-git`, `ticket-workflow/skills/work-ticket`), for when a whole domain is
  too much.
- **`[overrides]`** sets guard behaviours for this repository only. Only the allow-listed
  `WORK_TICKET_*` names count (table in the [hook policy](reference/hook-policy.md#repo-overrides));
  other names are ignored and reported by `harness repo`. A provider `env` override of the
  same name wins, even when it is set to an empty value. Per key the order is: environment >
  `.harness.toml` `[overrides]` > `guard.env` > default. Client paths and engine or credential
  settings (`HARNESS_GUARD_ENV`, `HARNESS_CRED_EXTRA_RE`, every `*_PY`, `GUARD_*`, `HARNESS_*`
  and `*CRED*` name) are never read from the file.

The guard parses the file in bash, so it accepts a TOML subset: `[section]` headers,
`key = "string"` (or single-quoted) and `key = ["a", "b"]`, one statement per line, and `#`
comment lines. Inline comments, escapes, multi-line arrays and inline tables are not part of
the subset; each key appears once (a repeat is ignored, the first one counts), `[owns]` keys
are arrays, and the file stays within 16 KiB and 400 lines (a larger file is ignored as a
whole). Anything outside the subset is ignored with one note on stderr (at most five per
command, then a count) — the guard fails open on the file, never closed — and `harness repo`
validates the file with the full parser and names what the guard would ignore.

**Where the guard looks.** The guard finds the declaration from the hook's working directory
(the agent's cwd), not from the command's target: `git -C ../other push` and
`cd ../other && git push` are judged under the declaration of the repository the agent is in.

**Who writes it.** A human. The declaration lifts user-level rules, so an agent that wrote it
would authorise itself: the hub's permission list asks before `Write`/`Edit` of
`**/.harness.toml`, and the guard asks before shell writes to it (`>`, `>>`, `tee`, `cp`,
`mv`, `dd of=`, `sed -i`, `harness repo init --write`). Neither ask yields. `harness repo init`
without `--write` prints a draft for the human to review and commit.

Owning `core/guard.d/20-credentials`, `core/permissions` or the domain `base` has no effect on
the credential denies ([below](#the-credential-exemption)).

## Claude Code: what stacks, what shadows

Verified against the Claude Code documentation, 2026-10.

| Surface | On collision | Consequence | What your repository does |
|---|---|---|---|
| instructions (`CLAUDE.md`) | concatenated managed → user → project → `CLAUDE.local.md`, never replaced | both texts reach the agent | write your rule; the hub's rule tells the agent your text wins where they differ |
| skills | enterprise > personal > project: a hub skill **shadows** your skill of the same name | your `/work-ticket` would lose | give your skill a distinct name, or turn the hub skill off with `skillOverrides` (`"off"` or `"name-only"`) or `permissions.deny: ["Skill(<name>)"]` in `.claude/settings.json`; the hub skill also yields itself at Step 0 |
| sub-agents | project `.claude/agents` wins on a name collision | your agent runs | ship an agent of the same name |
| hooks | all scopes run; the most restrictive decision wins (deny > defer > ask > allow) | your hook cannot lift a hub deny | declare `[owns]`: the hub's guard yields from inside; `disableAllHooks: true` switches off every user hook (not recommended; `harness repo` warns) |
| permissions | lists merge; a deny at any scope wins | you can add, not remove | nothing to do (the credential `Read(...)` denies stay) |
| `env` | ordinary settings key; project overrides user per key; reaches hook commands | per-key overrides | `"env": {"WORK_TICKET_ALLOW_TRANSITION": "1"}` wins over `.harness.toml` |

The `skillOverrides` snippet, as `harness repo` prints it for a repository that ships its own
ticket workflow, goes into the repository's `.claude/settings.json`:

```json
{ "skillOverrides": { "work-ticket": "off" } }
```

## Other providers

- **Gemini CLI** reads `GEMINI.md` hierarchically (home, then project directories). Whether
  project settings stack hooks or pass environment to them is not covered by the hub;
  `.harness.toml` works regardless, because the guard reads it from the hook's cwd.
- **Copilot CLI** reads `.github/copilot-instructions.md` as the repository location, which
  the hub does not manage. Hook stacking with project settings is not covered; `.harness.toml`
  works through the hook's cwd, and skills honour it at preflight.
- **Codex and OpenCode** (and Kilo) read `AGENTS.md` up the directory tree and
  `.agents/skills`, repository locations the hub does not manage. They have no command hook
  at all, so `[overrides]` has no effect there and `[owns]` reaches skills and rules only.

## What owning a domain lifts

Owning a domain (or a section's id) skips **every** rule of the yielding sections except
their `# never-yields:` preludes, including rules that look like safety rails. Decide with
the list in front of you; the [hook policy](reference/hook-policy.md) shows each rule with its
`yields` value.

- **`scm`** (`core/guard.d/30-git`, `gitlab/guard.d/50-gitlab`, `github/guard.d/60-github`):
  the default-branch push deny, the force-push and destructive-git asks, the stacked-delivery
  rules, the label gates, the `glab api`/`gh api` write asks, the human-only merge, approve and
  review asks, and the GitHub issue close/reopen deny (it lives in `60-github`).
- **`tracker`** (`jira/guard.d/70-jira`, `gitlab/guard.d/40-gitlab-closing`,
  `github/guard.d/41-github-closing`): the Jira transition deny, the label gate and the
  provenance-label rule on creates, and the closing-keyword denies.
- **`kubernetes`** (`k8s/guard.d/25-k8s-rules`): the mutation and exec-class asks, the
  `helm get values` ask, the Secret-value deny (`kubectl get secret … -o yaml`) and the
  kubeconfig-mutation denies (`kubectl config use-context`, `set-*`).
- **`workspace`** (`gdoc/guard.d/80-gdoc`): the Drive provenance gate and the mail-send ask.

To keep one of them, own single components instead of the domain, or set an override
(`WORK_TICKET_ALLOW_TRANSITION = "1"` turns the transition deny into an ask and keeps the rest
of `tracker`).

## The credential exemption

Never yield, whatever the file says:

- `core/guard.d/20-credentials` — denies shell reads of the kubeconfig,
  `~/.config/{gh,glab-cli,jira,gdoc}`, `~/.aws`, `~/.ssh` (except `*.pub`), `.env*` files and
  agent credential files, and secret environment dumps;
- `core/permissions` — the matching `Read(...)` denies, and the asks on `Write`/`Edit` of
  `**/.harness.toml`;
- the `# never-yields:` preludes above a section's `repo_owns` line: in
  `github/guard.d/60-github` the commands that print the stored GitHub token (`gh auth token`,
  `gh auth status --show-token`, `gh config get oauth_token`), in `k8s/guard.d/25-k8s-rules`
  `kubectl config view --raw`, and in `core/guard.d/30-git` the ask on shell writes to
  `.harness.toml`.

They protect the developer who installed the hub, not the repository; a cloned repository's
committed settings cannot lift them, and `[owns]` naming them is ignored. The guard also
hard-lists `20-credentials` as never yielding; the list is fixed in the engine and in the
taxonomy (a unit test keeps the two equal). `harness lint` refuses a `repo_owns` line in the
credential section and any rule code above a `repo_owns` line outside a `# never-yields:`
prelude, and the hook policy marks every prelude rule `never`.

## `harness repo`

Run it inside a repository (or pass a directory):

```sh
harness repo [show] [DIR] [--json]   # what yields here and why
harness repo owns ID [DIR]           # rc 0 owned (prints why), 1 not owned, 2 unknown id
harness repo init [DIR] [--write]    # draft a .harness.toml; --write creates it
```

`harness repo show` prints the repository root and whether a `.harness.toml` was found; for
each hub component, its `yields` value and whether it yields here and why (an owned domain,
an owned id, a name collision); name collisions with the repository's `.claude/skills` and
`.claude/agents`; every resolved override with its source (environment, `.harness.toml`,
`guard.env` or default); warnings (unknown override names, lines the guard would ignore,
`disableAllHooks`); and the provider snippet (`skillOverrides`) the repository needs.
`--json` prints the same as one object.

`harness repo owns ID` is what the hub's skills run at preflight: exit 0 means the
repository owns that component (by id or by its domain), 1 means it does not, 2 means the id
is unknown.

## Reference: what yields

<!-- generated:begin source=lib/harness/taxonomy.py#repo -->
Components that yield by declaration: listing a domain in `[owns] domains` covers every row of that domain; `[owns] components` takes the ids below.

| domain | guard sections that yield | skills that yield |
|---|---|---|
| `base` | — | — |
| `scm` | `core/guard.d/30-git`, `github/guard.d/60-github`, `gitlab/guard.d/50-gitlab`, `merge-queue/guard.d/65-merge-queue` | `merge-queue/skills/mq` |
| `tracker` | `github/guard.d/41-github-closing`, `gitlab/guard.d/40-gitlab-closing`, `jira/guard.d/70-jira` | `jira/skills/jira` |
| `delivery` | `ticket-workflow/guard.d/75-ticket-workflow` | `ticket-workflow/skills/create-ticket`, `ticket-workflow/skills/work-ticket` |
| `kubernetes` | `k8s/guard.d/25-k8s-rules` | `k8s/skills/k8s` |
| `workspace` | `gdoc/guard.d/80-gdoc` | `gdoc/skills/gdoc` |

| id | kind | domain | bundle |
|---|---|---|---|
| `core/guard.d/30-git` | guard | scm | core |
| `gdoc/guard.d/80-gdoc` | guard | workspace | gdoc |
| `gdoc/skills/gdoc` | skill | workspace | gdoc |
| `github/guard.d/41-github-closing` | guard | tracker | github |
| `github/guard.d/60-github` | guard | scm | github |
| `gitlab/guard.d/40-gitlab-closing` | guard | tracker | gitlab |
| `gitlab/guard.d/50-gitlab` | guard | scm | gitlab |
| `jira/guard.d/70-jira` | guard | tracker | jira |
| `jira/skills/jira` | skill | tracker | jira |
| `k8s/guard.d/25-k8s-rules` | guard | kubernetes | k8s |
| `k8s/skills/k8s` | skill | kubernetes | k8s |
| `merge-queue/guard.d/65-merge-queue` | guard | scm | merge-queue |
| `merge-queue/skills/mq` | skill | scm | merge-queue |
| `ticket-workflow/guard.d/75-ticket-workflow` | guard | delivery | ticket-workflow |
| `ticket-workflow/skills/create-ticket` | skill | delivery | ticket-workflow |
| `ticket-workflow/skills/work-ticket` | skill | delivery | ticket-workflow |

Never yield, whatever the file says: `core/guard.d/20-credentials`, `core/permissions`, and the `# never-yields:` prelude rules of `core/guard.d/30-git`, `github/guard.d/60-github`, `k8s/guard.d/25-k8s-rules` (marked `never` in the [hook policy](reference/hook-policy.md)). Agents yield by name, rules by text and permission lists by config ([taxonomy](reference/taxonomy.md)).
<!-- generated:end -->

Override names and defaults: [hook policy → Repo overrides](reference/hook-policy.md#repo-overrides).
