# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). Before 1.0, a minor release may
change configuration; such entries carry a **Migration** paragraph, and `harness upgrade`
prints every one between your applied version and the new one.

## [Unreleased]

### Principles

- `principles_version: 1`: the seven principles (lightweight; developer-first; a platform for
  everyone; installed as a platform, distributable air-gapped; distributed as a git
  repository; harness engineering; extensible core). `PRINCIPLES.md` is the summary and index,
  `principles/NN-*.md` holds one document per principle.

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
  release preflight (SemVer 2.0.0 tag with `v` and no `+build`, annotated, `VERSION` and the
  dated CHANGELOG section match, `[Unreleased]` emptied, no `local/`, clean tree, tag on
  `origin/main`, unique release asset names) and `harness release notes TAG [--dir DIR]
  [--out FILE]`; `make release-check TAG=…` and `make release-build TAG=… [TOOLS=…]`.
- `.github/workflows/release.yml`: a tag push `v*` that is SemVer 2.0.0 runs the preflight,
  the CI suite (`ci.yml` is now also a reusable workflow), pack with the four tool platforms
  and `--self-extract`, a `.run` install smoke, and publishes a GitHub Release (pre-release
  for `-rc.N` tags) with notes from this file and build provenance; any other tag name ends
  green with nothing released. `workflow_dispatch` makes dry-run dev builds or re-runs a tag
  (with `--ref` the tag itself; a re-run replaces a draft left by a failed upload, never a
  published release).
- SemVer 2.0.0 helpers (`util.SEMVER_RE`, `parse_semver`, `is_prerelease`, `version_key`
  with §11 precedence); `harness upgrade` orders CHANGELOG sections with them.

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
- `harness upgrade` targets `--to latest` by default: it fetches tags and checks out the
  newest release tag (pre-releases skipped) and never moves backwards (a checkout at or ahead
  of that tag is left alone, exit 0); `--to TAG` pins; `--to BRANCH` checks out and
  fast-forwards a branch; `harness doctor` runs after a successful apply and sets the exit
  status. The upgrade and air-gapped runbooks now describe what the code does.
- CONTRIBUTING "Releases (maintainers)" is the tag-driven procedure (release PR, merge,
  annotated tag, `make release-check`, push the tag, verify).
- Principles 4 and 5: the open question on signing is resolved (build provenance verified
  online, `SHA256SUMS` offline, annotated tags, signed tags optional); principle 5 lists the
  `.run` envelope. Statements unchanged, `principles_version` stays 1.

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
- `harness upgrade` without `--to` now fetches tags and checks out the newest release tag
  instead of `git pull --ff-only` on the current branch. Contributors following `main`:
  `harness upgrade --to main`. Clones made from a `--tag` bundle (detached HEAD) now upgrade
  without extra steps. No config keys changed.

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
