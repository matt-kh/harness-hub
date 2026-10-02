# Principle 1 — Lightweight, minimal dependencies

Part of [PRINCIPLES.md](../PRINCIPLES.md). Read this before adding a language, a library, a
binary, a service or a build step.

## Statement

> This repo should be lightweight, with minimal dependencies.

- The hub runs on what a developer workstation already has: `bash`, `python3` (standard
  library), `jq`, `git` and `curl`.
- Every additional dependency is a cost paid by every user, on every machine, including
  air-gapped ones. It needs a reason a reviewer can check.

## Rationale

- A harness is installed before anything else on a new machine. It cannot assume a package
  manager, a container runtime, network access or admin rights.
- Fewer moving parts means a smaller audit surface. The guard is one concatenated bash file;
  a reviewer can read all of it.
- Dependencies age. Python packages, npm trees and container images need patching; the
  standard library and POSIX tools mostly do not.
- Air-gapped distribution ([principle 4](04-install-as-a-platform.md)) is only realistic when
  the dependency list is short and every item is already present or pinned.

## What it means in this repo

- **Engine.** `lib/harness/` is python 3.9+ standard library only. The single exception is
  the vendored `lib/harness/_vendor/tomli`, used only where `tomllib` is missing (< 3.11).
- **Launcher.** `bin/harness` checks `python3 >= 3.9`, `jq` and `git`, then execs
  `python3 -m harness`. No virtualenv, no `pip install`.
- **Scripts.** Guard sections, doctor checks, installers and bundle CLIs are bash that parses
  under macOS `/bin/bash` 3.2 and avoids GNU-only flags (helpers in
  `bundles/core/lib/compat.sh`: `hn_timeout`, `hn_realpath`, `hn_sha256`).
- **Third-party tools** (`gh`, `glab`, `kubectl`, provider CLIs) are declared per bundle in
  `[requires.binaries.<tool>]`, marked `optional` where they are, and installed only by
  `harness install <tool>` from a pinned, sha256-verified `tools/<tool>.lock.json`.
- **No runtime services.** Nothing listens on a port, nothing runs in the background, nothing
  phones home ([SECURITY.md](../SECURITY.md) lists every outbound call).
- **Documentation is plain Markdown.** Generated regions are produced by the engine itself
  (`harness docs generate`), not by a site generator.

## What it rules out

- `pip`, `npm`, `cargo` or `go install` as an install step of the hub.
- Importing a third-party python module anywhere under `lib/harness/` (except `_vendor`).
- A daemon, a local web server, a database or a container image as a requirement.
- Shell features beyond bash 3.2 without a `BASH_VERSINFO` guard that `doctor` reports.
- New binaries in scripts without declaring them (see "How it is checked").
- Redistributing provider CLIs or MCP server packages inside the repo or a release.

## How it is checked

| Check | Kind | Where |
|---|---|---|
| Every `import` in `lib/harness/**` is stdlib or `_vendor` | unit test | `tests/unit/test_deps.py` |
| Binaries invoked by `bin/`, bundle, provider and gate scripts are on the allow-list or in the bundle's `requires.binaries` | lint warning | `harness lint` |
| Every script parses under `/bin/bash` 3.2 | CI | macOS job, `bash -n` |
| The engine runs on python 3.9 and 3.12 | CI | test matrix |
| Pinned tools match their lock file | install-time | `harness install` sha256 check |

- The allow-list is short and POSIX-shaped: shell, `python3`, `jq`, `git`, `curl`, `ssh`,
  archive and checksum tools, and core text utilities. Extending it is a reviewed change.

## Tensions and how they are resolved

- **With principle 2 (developer-first).** Developers need real tools (`gh`, `glab`, `kubectl`).
  Resolution: those are *bundle* dependencies, never hub dependencies. A user who does not
  enable the bundle never needs the tool.
- **With principle 6 (harness engineering).** More sensors mean more code. Resolution: sensors
  are written in bash or stdlib python and reuse the engine (`doctor`, `lint`, `test`).
  Inferential sensors (review agents) run inside the provider the user already has.
- **Optional network-fetched components.** The Jira MCP server starts through `uvx`, which
  downloads from PyPI. Resolution: it is optional (`jira.mcp.enabled = false`), documented in
  the [air-gapped runbook](../docs/runbooks/air-gapped.md), and the `jira` CLI covers the
  same reads without it.

## Examples

Compliant:

- A new doctor check written as a 20-line bash script using `jq` and `hn_timeout`.
- A YAML reader avoided by asking the tool for JSON (`kubectl … -o json | jq`).
- A new tool installed through a `tools/<tool>.lock.json` with a sha256 per OS/arch.

Non-compliant:

- `import requests` in the engine. Use `urllib.request`.
- A guard section that calls `rg` or GNU `timeout`. Use `grep -E` and `hn_timeout`.
- A bundle whose install step is `npm install -g …` without a lock file or an offline path.
- A docs build that needs a static-site generator to be readable.

## Open questions

- Whether `curl` can become optional by routing every download through python's `urllib`.
- Whether bundle CLIs written in python should share a tiny stdlib helper library or stay
  fully self-contained.
