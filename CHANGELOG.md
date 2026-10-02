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
- Docs: [distribution](docs/distribution.md) (tiers, release artifact, versioning), the
  [self-host runbook](docs/runbooks/self-host.md) for org platform instances, a "Guides and
  sensors" section in concepts, a bundle-file path in getting started.

### Changed

- README reframed as a public platform with three install paths (upstream, org instance,
  bundle file).
- Air-gapped runbook: offline install and upgrade use the release bundle.
- CONTRIBUTING: "Principles first", contributions as the steering loop, guides and sensors in
  the add-a-bundle checklist; PR template asks for the principle(s) served and the pairing
  check.

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
