# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). Before 1.0, a minor release may
change configuration; such entries carry a **Migration** paragraph, and `harness upgrade`
prints every one between your applied version and the new one.

## [Unreleased]

### Principles

- `principles_version: 1`: principles 1–7 (lightweight; developer-first; a platform for
  everyone; installed as a platform, distributable air-gapped; distributed as a git
  repository; harness engineering; extensible core). `PRINCIPLES.md` is the summary and index,
  `principles/NN-*.md` holds one document per principle.
- `principles_version: 2`: principle 8, **User-level by design: repository-level wins** —
  every hub component yields wholesale to an equivalent repository-level harness, declared
  in `.harness.toml` or found by name or text; only the developer's own credentials never
  yield: the credential-file denies (`core/guard.d/20-credentials`, `core/permissions`) and
  the `# never-yields:` preludes (commands that print a stored credential, the ask on writing
  `.harness.toml`). Checks: the `yields` taxonomy facet and lint rule, guard rows for
  `.harness.toml`, `harness repo`.

### Added

- `harness pack [--out DIR] [--tag TAG] [--tools os/arch,...]`: writes the release artifact,
  a `git bundle` of the hub plus optional pinned tool archives, `SHA256SUMS` and
  `INSTALL.txt`. Refuses a dirty tree and never includes `local/`.
- `harness verify FILE.bundle`: `git bundle verify`, the bundle's heads and tags, and the
  `SHA256SUMS` check.
- `harness bootstrap --from FILE.bundle [--dest DIR] [--origin URL]`: clone a bundle file and
  run the clone's bootstrap.
- Bundle manifests: optional `[harness]` section with `guides`, `sensors` and
  `coverage_note`, filled in for every public bundle; generated "Guides and sensors" tables
  and a harness coverage reference.
- `harness lint` warnings for bundles with unpaired guides or sensors, guard rule reasons
  without an alternative, and script binaries outside the allow-list; a unit test that keeps
  the engine on the python standard library.
- `AGENTS.md` (with `CLAUDE.md` as a symlink): instructions for agents changing this repo.
- `HARNESS_BUILD_DIR`: where compiled config and the built guard go; tests and smoke scripts set
  it to a temporary directory so they never touch a live hub's `build/`.
- Component taxonomy ([docs/reference/taxonomy.md](docs/reference/taxonomy.md)): every
  rule, skill, agent, guard section, permission list, MCP server, CLI, installer, doctor
  check and manual step has a stable path-derived id (`k8s/agents/k8s-triage`) and a
  domain, function and posture; kind, control, model and decisions are derived. Bundle
  manifests gain an optional `[taxonomy]` section (`domain`, `posture`, `function`,
  `[taxonomy.components]` overrides), filled in for every public bundle. Nothing is renamed
  and rendered provider files are unchanged.
- `harness catalog [--kind K] [--bundle B] [--domain D] [--json]`: every bundle, component,
  provider and profile with its id and facets.
- Generated docs: [catalog](docs/catalog.md) (every component by kind, domain × posture
  matrix), the taxonomy vocabulary, and a "Components" section on every bundle page.
- `harness lint` rule `taxonomy`: errors for overrides that name no component, postures on
  kinds that take none, functions that contradict a kind's fixed one, component postures
  stronger than the bundle's and the reserved bundle names `providers` / `profiles`;
  warnings for unclassified public bundles, skills, agents, CLIs and MCP servers, read-only
  agents in auto permission mode, and components `[harness]` does not declare.
- Docs: [distribution](docs/distribution.md) (tiers, release artifact, versioning), the
  [self-host runbook](docs/runbooks/self-host.md) for org platform instances, a "Guides and
  sensors" section in concepts, a bundle-file path in getting started.
- `.harness.toml` repository declaration (`[repo]`, `[owns] domains/components`, `[overrides]`),
  read by the guard from the hook cwd (not from a command's target) and by skills at
  preflight; `schema/repo.schema.json`. A TOML subset parsed without a subshell per line;
  `[owns]` keys are arrays, a repeated key is ignored (the first one counts), and a file over
  16 KiB or 400 lines is ignored as a whole; stderr notes are capped at five per command.
- Asks on writing `.harness.toml`: `Write(**/.harness.toml)` and `Edit(**/.harness.toml)` in
  the core permission list, and a guard ask on shell writes (`>`, `>>`, `tee`, `cp`, `mv`,
  `dd of=`, `sed -i`, `perl -i`, `harness repo init --write`) in a never-yields prelude of
  `core/guard.d/30-git`: the declaration lifts user-level rules, so a human reviews and
  commits it.
- `harness repo [show|owns ID|init [--write]]`.
- `yields` taxonomy facet (derived) with lint rule `yields`; `# repo-override:` comments
  generating the override allow-list and the hook-policy "Repo overrides" table; a `yields`
  column in the hook-policy rule table (`owns <domain>` or `never`). Lint refuses rule code
  above a `repo_owns` line outside a `# never-yields:` prelude and override names that are
  not `WORK_TICKET_*`.
- `docs/repo-level.md`: what the hub does inside a repository, the `.harness.toml`
  reference, the Claude Code collision facts, per-provider notes, the credential exemption.
- `bundles/core/lib/harness_repo.{sh,py}` helpers; `[precedence]` in provider adapters.

### Deprecated

- `[bundle].tags` in `bundle.toml`: free-form and never read; `harness lint` warns
  "bundle.tags: is deprecated; use taxonomy.domain". Classify the bundle with `[taxonomy]`.

### Changed

- README reframed as a public platform with three install paths (upstream, org instance,
  bundle file).
- Air-gapped runbook: offline install and upgrade use the release bundle.
- CONTRIBUTING: "Principles first", contributions as the steering loop, guides and sensors in
  the add-a-bundle checklist; PR template asks for the principle(s) served and the pairing
  check.
- Every guard section runs as a function; yielding sections start with
  `repo_owns <id> <domain> && return 0`; `core/guard.d/20-credentials` and `core/permissions`
  never yield, and neither do the token-printing denies, which move into `# never-yields:`
  preludes above the `repo_owns` line (`gh auth token`, `gh auth status --show-token`,
  `gh config get oauth_token` in `github/guard.d/60-github`; `kubectl config view --raw` in
  `k8s/guard.d/25-k8s-rules`, which now also denies the flag when it closes a quoted
  `sh -c "…"` string). Repo-settable regexes are passed to `grep -e`. `work-ticket` preflight reports `repo_declaration`/`repo_owns` and detects any
  repository skill by its (folded) description. Skills carry a "Step 0 — repository-level
  harness" paragraph; agents say a same-named repository agent wins; rules end with the
  repository sentence. Precedence is one rule in one vocabulary across concepts, governance,
  getting started, provider pages, the core rule, the ticket-workflow rule and manual step.
  `guard.env` is described as parsed, never sourced. The example repository skill name is a
  placeholder. `Auto` no longer names a personal path.

### Migration

- Component taxonomy: `schema_version` stays `"1"` and every new key is optional, so
  existing manifests keep loading. In every public or private `bundle.toml`, delete
  `tags = [...]` from `[bundle]` and add a `[taxonomy]` section with `domain` (base, scm,
  tracker, delivery, kubernetes, workspace) and `posture` (read-only, local, label-gated);
  add `function` (govern, client, workflow, investigate, plan, execute, review, setup) as a
  default for skills and agents, and `[taxonomy.components]` entries such as
  `"agents/<name>" = { function = "review", posture = "read-only" }` for every skill, agent,
  CLI (`bin/<name>`) and MCP server (`mcp/<server>`) that differs from the bundle. Run
  `harness lint`: its `taxonomy:` messages list the ids (`harness catalog --bundle <b>`) and
  the allowed values. A rule, skill, agent, guard section or permission list missing from
  `[harness]` is reported too; declare it as a guide or sensor. Then run
  `harness docs generate` to refresh the bundle pages and the catalog.
- Repositories: nothing required. Provider `env` overrides keep working and win per key.
  To declare what your repository owns, add `.harness.toml` (`[owns]`, `[overrides]`) and
  run `harness repo`. Overrides settable from `.harness.toml` are exactly
  `WORK_TICKET_ALLOW_DEFAULT_PUSH_RE`, `WORK_TICKET_ALLOW_TRANSITION`,
  `WORK_TICKET_LABELED_DECISION`, `WORK_TICKET_BASE_BRANCH_RE`, `WORK_TICKET_KEY_IN_BRANCH`;
  only `WORK_TICKET_*` names can ever be repo overrides, and client paths,
  `HARNESS_GUARD_ENV`, `HARNESS_CRED_EXTRA_RE` and every `*_PY`, `GUARD_*`, `HARNESS_*` or
  `*CRED*` name are never repo-settable. Keep the file within 16 KiB and 400 lines, write
  each key once and `[owns]` values as arrays. Owning a domain lifts every rule of its
  sections except the never-yields preludes, including the human-only merge asks (`scm`) and
  the Secret-value and kubeconfig-mutation denies (`kubernetes`); see docs/repo-level.md
  "What owning a domain lifts". Agents can no longer write `.harness.toml` without asking:
  a human creates and commits it (`harness repo init` prints a draft).
  Bundle authors (public, org and private): add the `repo_owns` line to each rule-bearing
  guard section, with only shared assignments and, for commands that print a stored
  credential, a `# never-yields:` prelude above it; name honoured overrides `WORK_TICKET_*`
  and give each a `# repo-override:` comment; add the Step 0
  paragraph to skills and the baseline sentence to agents (it uses an em dash:
  `(User-level baseline, principle 8 — a repository-level agent of the same name replaces
  it.)`, so an unquoted YAML description stays a plain scalar); `harness lint` names what is
  missing. Run `harness apply` to re-render the guard.

## [0.1.0] - 2026-09-30

Initial public release.

### Added

- Engine (`bin/harness`, python stdlib only): `bootstrap`, `init`, `bundles`,
  `config validate|get|set|explain|migrate`, `plan`, `apply`, `sync`, `render`, `doctor`,
  `status --matrix`, `install`, `upgrade`, `uninstall`, `test`, `lint`,
  `docs generate|check`, `steps --pending`, `version`.
- Single gitignored config `local/harness.toml` with layering (bundle defaults → org overlay
  → user → machine → `HARNESS_*` environment) and secret-value rejection.
- Bundles: `core`, `github`, `gitlab`, `jira`, `ticket-workflow`, `k8s`, `gdoc`, each with
  rules, skills, guard sections, permissions, manual steps and doctor checks.
- Providers: Claude Code (enforced), Gemini CLI and Copilot CLI (partial: guard hook, no
  ask prompt), Codex and OpenCode (advisory).
- Guard: one concatenated `guard-bash.sh` per provider home built from per-bundle sections,
  with the full table-driven test suite.
- Platform: CI on Ubuntu and macOS (bash 3.2 syntax gate, python 3.9 and 3.12), render
  determinism and bootstrap smoke tests, private-identifier gate, Markdown link check,
  weekly provider version drift check, issue and PR templates.
- Documentation: getting started, concepts, governance, per-bundle and per-provider pages
  with generated regions, runbooks and reference pages.

[Unreleased]: https://github.com/matt-kh/harness-hub/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/matt-kh/harness-hub/releases/tag/v0.1.0
