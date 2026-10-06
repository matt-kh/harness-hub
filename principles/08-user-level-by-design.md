# Principle 8 — User-level by design: repository-level wins

Part of [PRINCIPLES.md](../PRINCIPLES.md). Read this before adding a component, a guard
section, a skill preflight, an agent description, or any text that tells an agent which
instruction wins.

## Statement

> harness-hub is a user-level harness by design. Every component it installs is a baseline
> that yields to an equivalent repository-level harness — wholesale, never merged — except
> the denies that protect the developer's own credentials.

- Many developers already carry a repository-level harness tuned to their domain. The hub
  must be useful beside it without competing with it or diluting its guidance.
- A repository declares what it owns in `.harness.toml`; where it declares nothing, hub
  components recognise an equivalent by name or by text and hand over.
- The developer's own credentials belong to the developer, not to the repository: a cloned
  repository's committed settings never lift the credential-file denies or the denies on
  commands that print a stored credential, and never write the declaration on the agent's
  behalf.

## Rationale

- A user-level harness is installed once and travels into every repository; a
  repository-level harness is reviewed with the code and knows the domain. When both speak
  to the same action, the one reviewed with the code is right more often.
- Merging two harnesses produces a third that nobody wrote. Replacement keeps each legible:
  either the hub's component runs or the repository's does.
- Providers already decide some collisions (Claude Code: project agents win, personal
  skills shadow project skills, hooks stack and a deny at any scope wins). Stating the rule
  as policy is not enough: each component must know how to yield on its surface, and the
  developer must be able to see what yields where (`harness repo`).
- The developer's credentials are not the repository's concern. A repository may own branch
  naming, ticket transitions or cluster edits; it may not read `~/.config/gh` or `~/.ssh`.

## What it means in this repo

- **A declaration file.** `.harness.toml` at the repository root, provider-neutral,
  committed: `[owns] domains`, `[owns] components` (taxonomy ids) and `[overrides]`
  (allow-listed names) — [ARCHITECTURE §11](../ARCHITECTURE.md#11-repository-level-declaration-harnesstoml),
  [repository-level harnesses](../docs/repo-level.md).
- **Every component carries a `yields` facet**, derived from its kind:
  `declaration` (reads `.harness.toml`: skills, guard sections), `name` (the provider
  resolves a collision by name: agents), `text` (concatenated instructions; the text says the
  repository wins: rules), `config` (a repo changes it per key, never wholesale: permission
  lists), `never` (only `core/guard.d/20-credentials` and `core/permissions`), `n/a`
  ([taxonomy](../docs/reference/taxonomy.md)).
- **Guard sections start with the yield check.** A section whose domain or id the
  repository owns emits nothing (pass), so the provider's own rules and the repository's
  hook decide. `20-credentials` has no such check.
- **Skills run Step 0.** Read `.harness.toml`, detect a repository-level equivalent, hand
  over before any question, label or write (the standard paragraph in
  [CONTRIBUTING](../CONTRIBUTING.md#standard-texts)).
- **Agents are baselines.** Their description says so in one standard sentence; a
  repository agent of the same name replaces them where the provider resolves by name.
- **Rules state the order.** Instruction files are concatenated, never replaced; the core
  rule tells the agent that the repository's text wins where the two differ.
- **Overrides are allow-listed.** The `WORK_TICKET_*` names in the hook policy's "Repo
  overrides" table; client paths and engine or credential settings never come from a
  repository.
  Every other variable the guard reads from `guard.env` is a developer-environment setting
  rendered from `harness.toml`, not a repository override. Provider `env` overrides keep
  working and win per key: environment > `.harness.toml` > `guard.env` > default.
- **A human writes the declaration.** It lifts user-level rules, so the agent never writes
  it: file writes and shell writes to `.harness.toml` ask. The guard reads it from the hook's
  cwd (not from a command's target directory) and ignores a file over 16 KiB or 400 lines.
- **`harness repo`**, run inside a repository, lists what yields and why, name collisions,
  resolved overrides and the provider snippet (`skillOverrides`) a repository needs.
- **Skills never edit the user-level harness**, and edit a repository's harness only inside
  the change that makes it stale — never to fit the hub.

## What it rules out

- A hub component that keeps acting when the repository owns its domain or id.
- A rule that claims to replace a repository instruction (providers concatenate; the hub
  cannot).
- Merging: borrowing half a repository workflow and running the rest of the hub's.
- `yields = never` on anything but the credential components, and rule code above a
  `repo_owns` line outside a `# never-yields:` prelude; a prelude holds only commands that
  print a stored credential (and the ask on shell writes to `.harness.toml`) — org bundles
  included.
- An agent writing `.harness.toml` itself: it would authorise itself. File writes and shell
  writes to it ask, and those asks never yield.
- Repository overrides outside the allow-list; a repository narrowing the credential regexes.
- Detecting one organisation's repository-skill name instead of a declaration or a generic
  description match.
- Editing a repository's harness to make it fit the hub.

## How it is checked

| Check | Kind | Where |
|---|---|---|
| Public skills, guard sections, agents and rules carry their yield mechanism (the `repo_owns` line, the Step 0 paragraph, the baseline sentence); no `repo_owns` line in the credential section | lint rule `yields` | `harness lint` |
| `never` only on `core/guard.d/20-credentials` and `core/permissions`, identical in the engine and the taxonomy | unit test | `tests/unit/test_taxonomy.py` |
| Rule code above a `repo_owns` line only inside a `# never-yields:` prelude (plain shared assignments aside); preludes only in `core/guard.d/30-git`, `github/guard.d/60-github`, `k8s/guard.d/25-k8s-rules` | lint rule `yields`, unit test | `harness lint`, `tests/unit/test_taxonomy.py` |
| `gh auth token`, `gh auth status --show-token`, `gh config get oauth_token`, `kubectl config view --raw` still deny when `.harness.toml` owns `scm`, `kubernetes`, `tracker` and `workspace`; shell writes to `.harness.toml` ask in an owning repository | test rows | `bundles/{github,k8s,core}/guard.d/tests.sh` |
| A guard section passes when `.harness.toml` owns its domain or id; `20-credentials` still denies with the same file present (bypass row); `[overrides]` outside the allow-list are ignored; environment wins over the file | test rows | `bundles/*/guard.d/tests.sh` (`tc` rows with fixture repositories) |
| `harness repo` lists yielding components, collisions and resolved overrides for a fixture repository; warns on unknown override names and `disableAllHooks` | unit test | `tests/unit/test_repo.py` |
| "Repo overrides" table and the "what yields" region are current | docs | `harness docs check` |
| Statement, vocabulary and the repo-level page link from AGENTS, ARCHITECTURE, CONTRIBUTING, README | lint | `tools/gate/check-links.sh` |

## Tensions and how they are resolved

- **With principle 6 (harness engineering).** A yielded guard section stops sensing.
  Resolution: the yield is explicit (declared in the repository, listed by `harness repo`)
  and coverage moves to the repository's harness, which the hub lists but cannot verify;
  the skill or rule that yields says so in its output, so a silent gap never looks like
  success.
- **With governance (the credential exemption).** Governance says every rule is adaptable
  per repository; this principle keeps two components fixed. Resolution: the label model,
  ticket-state rule and branch rules are the organisation's process and yield; credential
  files and the stored credentials behind them are the developer's property and do not. The
  exemption is two component ids, fixed in the engine and the taxonomy (a unit test keeps them
  equal), plus the marked `# never-yields:` preludes that deny printing a stored credential
  (`gh auth token`, `gh auth status --show-token`, `gh config get oauth_token`,
  `kubectl config view --raw`) and ask before shell writes to `.harness.toml`; lint refuses
  any other code above a `repo_owns` line, and the hook policy marks every such rule `never`.
- **With principle 3 (platform for everyone).** An organisation may want a repo-proof
  rule in its org bundle. Resolution: org bundles yield like public ones; a rule that must
  hold against a repository belongs server-side (branch protection, CI), not in a
  user-level harness.
- **With principle 2 (developer-first).** None: "the developer's own files and decisions
  stay theirs" is the same rule seen from the developer's side.

## Examples

Compliant:

- A repository with `[owns] domains = ["delivery"]`: `/work-ticket` and `/create-ticket`
  stop after their read-only preflight and name the repository's workflow; adding
  `"tracker"` (or the override `WORK_TICKET_ALLOW_TRANSITION = "1"`) lets the repository's
  workflow transition tickets.
- `k8s/agents/k8s-triage` yields by `name`; the repository ships
  `.claude/agents/k8s-triage.md`; Claude Code runs the repository's.
- `WORK_TICKET_ALLOW_TRANSITION = "1"` in `.harness.toml`: a transition on a human ticket
  asks instead of denying; `cat ~/.config/gh/hosts.yml` is still denied in that repository.

Non-compliant:

- A guard section that reads `.harness.toml` but keeps denying "to be safe".
- A skill that detects a repository workflow and still adds the `agent-worked` label first.
- An org bundle whose branch-naming guard section carries no `repo_owns` line.
- A rule file saying "this text overrides the repository's CLAUDE.md".

## Open questions

- Gemini CLI and Copilot CLI: whether a project-level settings file can pass environment
  to hooks; today the hub documents only `.harness.toml` for them.
- Codex and OpenCode have no hook: `[overrides]` has no effect and `[owns]` reaches only
  skills and rules. Whether `harness repo` should say so per active provider.
- What owning a domain lifts, by design: everything in its sections except the preludes.
  Owning `scm` lifts the human-only merge, approve and review asks and the GitHub issue
  close/reopen deny; owning `kubernetes` lifts the Secret-value deny (`kubectl get secret -o
  yaml`) and the kubeconfig-mutation denies (`use-context`, `set-*`); owning `tracker` lifts the
  transition and closing-keyword denies. Open: whether kubeconfig mutations — they edit the
  developer's own file — should join the never-yields prelude next to `kubectl config view
  --raw`. Default: no.
- Whether a repository may extend (never narrow) `HARNESS_CRED_EXTRA_RE`.
- Monorepos: one `.harness.toml` at the git root, or nearest-ancestor lookup from the cwd.
