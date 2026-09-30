# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). Before 1.0, a minor release may
change configuration; such entries carry a **Migration** paragraph, and `harness upgrade`
prints every one between your applied version and the new one.

## [Unreleased]

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
