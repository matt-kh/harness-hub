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
  - `SHA256SUMS` over every file, and a short `INSTALL.txt`.
- **Commands.**
  - `harness pack [--out DIR] [--tag TAG] [--tools os/arch,...]` builds the artifact from a
    clean tree; it refuses a dirty tree and never includes `local/`.
  - `harness verify FILE.bundle` runs `git bundle verify`, lists heads and tags and checks
    `SHA256SUMS` beside the file.
  - On a new machine, `git clone FILE.bundle ~/harness-hub && ~/harness-hub/bootstrap`. From an
    existing hub, `harness bootstrap --from FILE.bundle [--dest DIR] [--origin URL]` clones the
    bundle, optionally points `origin` at a real remote, then runs the clone's own bootstrap.
- **Versioning.** Semver tags `vX.Y.Z`, the `VERSION` file, and a CHANGELOG section per release
  with a **Migration** paragraph whenever config or guard decisions change.
- **Upgrades.** `harness upgrade [--to TAG]` is `git fetch` plus checkout or fast-forward, then
  migration notes and a plan. Offline, fetch from a newer bundle file first.
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
| `VERSION`, tag and CHANGELOG agree | release review | [CONTRIBUTING](../CONTRIBUTING.md#releases-maintainers) |

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
- Signing: signed tags versus a detached signature over `SHA256SUMS`.
