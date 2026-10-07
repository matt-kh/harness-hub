# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). Before 1.0, a minor release may
change configuration; such entries carry a **Migration** paragraph, and `harness upgrade`
prints every one between your applied version and the new one.

## [Unreleased]

### Docs

- [docs/roadmap.md](docs/roadmap.md): planned bundles and extensions by tranche (P0 coverage
  gaps and lint sensors; core git and shell hygiene, `run-checks`, `worktree`, Jira Cloud, the
  `ci` bundle; then the secret-tooling, toolchain, containers, release, cloud, iac, db, hosts
  and digest bundles), the guard prefix bands reserved for them, two proposed taxonomy domains and the
  rejected candidates. Linked from README and ARCHITECTURE §3.

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
- `harness pack --self-extract`: also writes `harness-hub-<version>.run`, a POSIX sh header
  (tracked as `lib/harness/selfextract-header.sh`) plus a deterministic uncompressed tar of the
  bundle, `INSTALL.txt`, `SHA256SUMS` and tool archives. `sh FILE.run --check | --list |
  --extract DIR`; run it to unpack into `~/.local/share/harness/releases/<version>/`
  (`--release-dir`), clone into `--dest` (default `~/harness-hub`) and bootstrap, or, against
  an existing clone, fetch its tags, point `origin` at its bundle and `harness upgrade`. The
  bundle stays the release; the outer `SHA256SUMS` lists the `.run`. On the upgrade path the
  bootstrap-only flags (`--no-install-tools`, `--bundles X`, ...) are dropped with a note, so
  the install command line also upgrades; a dev-build `.run` (no tag) installs only and
  refuses an existing clone.
- `harness verify FILE.run`: `sh FILE.run --check` plus the `SHA256SUMS` check.
- `harness release check [TAG] [--remote NAME] [--branch NAME] [--no-remote] [--json]`: the
  release preflight (bare SemVer 2.0.0 tag `X.Y.Z[-pre]`, no `v` prefix and no `+build`,
  annotated, `VERSION` and the dated CHANGELOG section match, `[Unreleased]` emptied, no
  `local/`, clean tree, tag on `origin/main`, unique release asset names) and `harness release
  notes TAG [--dir DIR] [--out FILE]`; `make release-check TAG=…` and `make release-build TAG=…
  [TOOLS=…]`.
- `.github/workflows/release.yml`: a tag push whose name is bare SemVer 2.0.0
  (`X.Y.Z[-pre]`; a `v`-prefixed tag is skipped) runs the preflight,
  the CI suite (`ci.yml` is now also a reusable workflow), pack with the four tool platforms
  and `--self-extract`, a `.run` install smoke, and publishes a GitHub Release (pre-release
  for `-rc.N` tags) with notes from this file and build provenance; any other tag name ends
  green with nothing released. `workflow_dispatch` makes dry-run dev builds or re-runs a tag
  (with `--ref` the tag itself; a re-run replaces a draft left by a failed upload, never a
  published release).
- SemVer 2.0.0 helpers (`util.SEMVER_RE`, `parse_semver`, `is_prerelease`, `version_key`
  with §11 precedence); `harness upgrade` orders CHANGELOG sections with them.
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
- Guard section 75 (bundle `ticket-workflow`): asks on branches created with a ticket key or
  `#N` in the name (`git switch -c`, `checkout -b`, `branch`, `worktree add -b`), on commits
  whose first `-m` starts with a ticket key, on `git worktree add` of a `-sub-` branch outside
  `../<repo>_<branch>`, and on merges of a `-sub-` branch without `--squash`. All decisions
  are deferred asks; `WORK_TICKET_KEY_IN_BRANCH=1` lets the two key rules pass.
- `harness lint` rules, each message saying what to do instead:
  `env-provides` (error: a `[provides.env]` key without a prefix the guard's guard.env parser
  accepts; the list is parsed from `bundles/core/guard/engine.sh`),
  `rule-guard-pairing` (warning: a `rules/NN-x.md` without a `guard.d/NN-*.sh` or the reverse,
  unless `coverage_note` names `x`), `permissions-vs-guard` (error: a `Bash(<prefix>:*)` allow
  rule the guard denies or asks, or a deny rule it allows, found by running the guard built
  from core + the bundle on `<prefix> x`), `agent-tools` (read-only agents with write tools or
  a permissionMode warn — the permissionMode check moved here from `taxonomy`; a hard-coded
  agent `model:` is an error), `skill-description` (warning: description length 60–1024 after
  expansion with the CI config, a "Use when" trigger, and for workflow skills "NOT for" plus
  `argument-hint`), `fragments-target` (error: fragments for a skill no related bundle
  provides; warning: fragments in a public bundle), `profile-sane` (error: a profile that
  names unknown or private bundles or providers, or does not resolve) and `stability`
  (warning: a `stable` bundle without a test suite per skill/CLI).
  `harness lint --skip RULE` turns one off (e.g. the slower `permissions-vs-guard`).
- Sensor kind `provider-feature` in `[harness]` sensors, `ref = "<provider>:<feature>"`,
  checked against a new optional top-level `features` list in `provider.toml`
  (`claude`: `auto-mode-classifier`, `permission-prompt`; empty elsewhere). Core declares
  `claude:auto-mode-classifier` ("reviews the Auto agent's actions"); the "Guides and
  sensors" tables render it. No migration: `features` and the new sensor kind are optional
  and no existing key changed.
- `harness bootstrap` ends with "≈ N minutes of manual steps remain (harness steps
  --pending)", summed from the pending steps' `minutes`; `tests/smoke/bootstrap.sh` prints
  the elapsed seconds.
- `gitlab` bundle: MR title and `--fill` sensors. `glab mr create` asks on `-f/--fill`
  (generated text may carry a closing keyword or a key-less title), on `--related-issue`, on a
  literal `-t/--title` that does not match the new `gitlab.mr_title_re` (ticket key first) and
  on a `$VAR`/backtick title; an MR created without `-t` is not title-checked. Guard rows
  include `cd … &&`, `sh -c` and multi-clause bypass attempts.
- `github` bundle: PR title and `--fill` sensors. `gh pr create` asks on
  `-f/--fill/--fill-first/--fill-verbose`, on a literal `-t/--title` matching the new
  `github.pr_title_forbid_re` (issue refs belong in the body) and on a `$VAR`/backtick title.

### Deprecated

- `[bundle].tags` in `bundle.toml`: free-form and never read; `harness lint` warns
  "bundle.tags: is deprecated; use taxonomy.domain". Classify the bundle with `[taxonomy]`.

### Fixed
- `bin/harness` runs the checkout it lives in: an inherited `HARNESS_HOME` naming another checkout
  is ignored with a note instead of silently making a worktree's pre-commit hooks and `make`
  targets lint and test the main checkout. `python3 -m harness` and rendered scripts still read
  the variable; `--home DIR` remains the explicit override.
- `harness test` drops git's repository-discovery variables (`GIT_DIR`, `GIT_WORK_TREE`,
  `GIT_INDEX_FILE`, …) from every suite's environment, and the pack unit tests drop them too.
  Git exports them to hooks, so the pre-push hook's unit run pointed the pack fixture
  repositories at the real checkout and failed (in a worktree, with the whole hub staged for
  deletion); the suites now pass from hooks as they do from a shell.

### Changed

- README reframed as a public platform with three install paths (upstream, org instance,
  bundle file).
- Air-gapped runbook: offline install and upgrade use the release bundle.
- CONTRIBUTING: "Principles first", contributions as the steering loop, guides and sensors in
  the add-a-bundle checklist; PR template asks for the principle(s) served and the pairing
  check.
- `harness upgrade` targets `--to latest` by default: it fetches tags and checks out the
  newest release tag (pre-releases skipped) and never moves backwards (a checkout at or ahead
  of that tag is left alone, exit 0); `--to TAG` pins; `--to BRANCH` checks out and
  fast-forwards a branch; `harness doctor` runs after a successful apply and sets the exit
  status. The upgrade and air-gapped runbooks now describe what the code does.
- CONTRIBUTING "Releases (maintainers)" is the tag-driven procedure (release PR, merge,
  annotated bare SemVer tag `X.Y.Z`, `make release-check`, push the tag, verify).
- Principles 4 and 5: the open question on signing is resolved (build provenance verified
  online, `SHA256SUMS` offline, annotated tags, signed tags optional); principle 5 lists the
  `.run` envelope. Statements unchanged (the bump to 2 above is principle 8).
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
- work-ticket's skill description shortened to 1024 characters or fewer (rule
  `skill-description`), keeping its triggers, "NOT for" scope, repo-level hand-over and GitHub
  mode. Coverage notes of core, github, gitlab, k8s and ticket-workflow name the topics whose
  rule or guard section is unpaired by number (`rule-guard-pairing`).

### Stability

- `ticket-workflow` and `gdoc`: `stable` → `beta`; their coverage notes admit a missing test
  suite (work-ticket, the gdoc CLI), which the
  [stability criteria](CONTRIBUTING.md#stability-levels) require for `stable`.

### Docs

- CONTRIBUTING: "Stability levels" (experimental, beta, stable, deprecated), linked from
  concepts "Bundles".
- Principle 6 open questions: declaring inferential sensors that live in provider features is
  resolved by the `provider-feature` sensor kind. Principle 2 open questions: the bootstrap
  smoke's elapsed seconds and bootstrap's remaining-minutes line are the time-to-first-useful-
  session proxies. Doc-only: the normative statements are unchanged, so `principles_version`
  stays 1.

### Migration

- MR/PR title conventions: two new optional config keys. `gitlab.mr_title_re` (default
  `"^[A-Z][A-Z0-9_]*-[0-9]+ "`, a ticket key and a space first; env
  `HARNESS_GITLAB_MR_TITLE_RE`) is the ERE a `glab mr create -t` title must match;
  `github.pr_title_forbid_re` (default `"#[0-9]+"`; env `HARNESS_GITHUB_PR_TITLE_FORBID_RE`)
  is the ERE a `gh pr create -t` title must not match. Guard decisions change from allow to
  ask for `glab mr create --fill|--related-issue`, `gh pr create --fill|--fill-first|--fill-verbose`
  (and `-f`), and for literal titles that break the convention. Setting either key to an empty
  string (`mr_title_re = ""` under `[gitlab]`, `pr_title_forbid_re = ""` under `[github]`)
  disables the title check; the `--fill` asks stay. Run `harness apply` to re-render the guard
  and `guard.env`.
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
- `harness upgrade` without `--to` now fetches tags and checks out the newest release tag
  instead of `git pull --ff-only` on the current branch. Contributors following `main`:
  `harness upgrade --to main`. Clones made from a `--tag` bundle (detached HEAD) now upgrade
  without extra steps. No config keys changed.
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
- Guard section 75: repos that put ticket keys in branch names or commit subjects set
  `WORK_TICKET_KEY_IN_BRANCH = "1"` in `.harness.toml` `[overrides]` (or the provider `env`;
  previously accepted but a no-op); the guard now asks on key-named branches, key-prefixed commit subjects,
  off-convention sub worktree paths and non-squash merges of `-sub-` branches.

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
