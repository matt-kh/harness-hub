# Principle 5 — Distributed as a git repository

Part of [PRINCIPLES.md](../PRINCIPLES.md). Read this before changing releases, versioning,
`pack`, `verify`, `bootstrap` or `upgrade`.

## Statement

> Since this repo is a sort of meta-platform, it can follow a paradigm similar to makeself,
> such that this repo is meant to be packaged and distributed as a git repo.

- makeself turns a directory into one self-extracting file. The git equivalent is a
  **`git bundle`**: one file that is a complete, verifiable repository, cloneable with git
  alone and fetchable later for upgrades.
- The unit of distribution is therefore the repository with its history and tags, not an
  archive of its current files.

## Rationale

- Git is already on every developer machine and is the one tool every org git host speaks.
  Choosing it adds no dependency ([principle 1](01-lightweight.md)).
- History travels with the copy. A site can diff releases, read the CHANGELOG, bisect a
  regression and carry its own commits on top.
- A bundle file verifies itself (`git bundle verify`) and upgrades in place
  (`git fetch FILE.bundle`), so air-gapped sites get the same upgrade path as connected ones.
- Forks and mirrors are ordinary git operations, which makes org platform instances cheap.

## What it means in this repo

- **Release artifact** ([distribution](../docs/distribution.md)):
  - `harness-hub-vX.Y.Z.bundle`, the repository with its tags;
  - optional sidecar tool archives for the platforms a site asks for, taken from
    `tools/*.lock.json`;
  - `SHA256SUMS` over every file, and a short `INSTALL.txt`;
  - optionally `harness-hub-vX.Y.Z.run`, the makeself-style **envelope**: a tracked POSIX sh
    header plus an uncompressed tar of the files above. It is a carrier for people who want
    one file to move and check; the bundle inside is still what gets cloned and fetched, so
    the release stays a git repository.
- **Commands.**
  - `harness pack [--out DIR] [--tag TAG] [--tools os/arch,...]` builds the artifact from a
    clean tree; it refuses a dirty tree and never includes `local/`.
  - `harness pack --self-extract` adds the `.run`; `sh FILE.run --check | --list |
    --extract DIR` inspects it, and running it clones and bootstraps (or, against an existing
    clone, fetches its tags and runs `harness upgrade`).
  - `harness verify FILE.bundle` runs `git bundle verify`, lists heads and tags and checks
    `SHA256SUMS` beside the file; `harness verify FILE.run` runs `sh FILE.run --check` first.
  - `harness release check [TAG]` is the release preflight and `harness release notes TAG`
    writes the notes; pushing a SemVer tag on `main` runs both in `.github/workflows/release.yml`,
    which publishes the GitHub Release.
  - On a new machine, `git clone FILE.bundle ~/harness-hub && ~/harness-hub/bootstrap`. From an
    existing hub, `harness bootstrap --from FILE.bundle [--dest DIR] [--origin URL]` clones the
    bundle, optionally points `origin` at a real remote, then runs the clone's own bootstrap.
- **Versioning.** SemVer 2.0.0: annotated tags `vX.Y.Z` (pre-releases `vX.Y.Z-rc.N`) on
  `main`, the `VERSION` file, and a CHANGELOG section per release with a **Migration**
  paragraph whenever config or guard decisions change. Tag push = release of the same name.
- **Upgrades.** `harness upgrade [--to latest|TAG|BRANCH]` is `git fetch --tags` plus a
  checkout of the newest release tag (default), a given tag, or a fast-forward of a branch,
  then migration notes, a plan, apply and doctor. Offline, fetch from a newer bundle file
  first, or run a newer `.run` with the same `--dest`.
- **What is never in a release:** `local/`, `build/`, state files, credentials, provider CLIs,
  MCP packages.

## What it rules out

- Tarballs, zip files or language packages as the primary distribution format.
- Release steps that rewrite history or tags after publication.
- Generated artefacts committed to the repo when the engine can regenerate them (except the
  generated doc regions, which are checked for staleness).
- State or configuration that only exists outside git and cannot be recreated from the clone
  plus `local/`.

## How it is checked

| Check | Kind | Where |
|---|---|---|
| Pack in a temp clone, verify, `bootstrap --from` into a temp home, `doctor --offline` rc 0 | smoke | `tests/smoke/pack.sh` |
| Bundle and pack behaviour | unit | `tests/unit/test_pack.py` |
| `local/` and `build/` are ignored | repo | `.gitignore`, asserted by `pack` |
| `.run` envelope: deterministic payload, `--check` / `--list` / `--extract`, tamper and truncation, install and upgrade | unit | `tests/unit/test_pack.py` |
| `.run` install into a temp home (clone at the tag, `origin` under the release dir, `doctor --offline` rc 0) and the upgrade path, on Linux and macOS | smoke | `tests/smoke/pack.sh` |
| `VERSION`, tag and CHANGELOG agree; SemVer, annotated tag, on `main`, no `local/` | unit + release preflight | `tests/unit/test_release.py`, `harness release check` |
| Only SemVer tags release; preflight, CI, pack, `.run` smoke, provenance before publishing | workflow | `.github/workflows/release.yml` |

## Tensions and how they are resolved

- **With principle 1 (lightweight).** Full history makes the bundle larger than a snapshot.
  Resolution: the repo is text and small; `--tag TAG` packs only what a site needs.
- **With principle 3 (platform for everyone).** Org instances add private commits. Resolution:
  they live on the org's remote; the org packs its own bundles from its own fork with the
  same command.
- **With provider ecosystems.** Providers distribute skills through their own marketplaces.
  Resolution: the hub renders into provider homes from the clone; marketplaces are optional
  consumers, never the source of truth.

## Examples

Compliant:

- A site downloads `harness-hub-v0.2.0.bundle` and `SHA256SUMS`, checks the sums, and clones
  the bundle on the offline machine.
- An org mirror is updated with `git fetch upstream --tags` and a merge.

Non-compliant:

- Publishing a `.tar.gz` of the working tree as the release.
- A release script that bakes a maintainer's `local/harness.toml` into the artifact.
- An upgrade path that downloads files outside git without a pin and a hash.

## Open questions

- Whether `pack` should also emit an incremental bundle (`old-tag..new-tag`) for very slow
  transfer channels.

Resolved:

- Signing (decided with the first automated release): GitHub build provenance
  (`actions/attest-build-provenance`) over every asset, verified online with
  `gh attestation verify`; `SHA256SUMS` stays the offline check. Release tags must be
  annotated; signed tags are optional and reported by `harness release check`. A detached
  signature over `SHA256SUMS` stays out until a verifier exists that adds no dependency.
