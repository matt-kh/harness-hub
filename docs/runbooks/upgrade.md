# Runbook: upgrade

```sh
harness upgrade              # the newest release tag (same as --to latest; pre-releases skipped)
harness upgrade --to 0.3.1   # a specific version (also a pre-release: --to 0.4.0-rc.1)
harness upgrade --to main    # follow a branch: check it out and fast-forward it
harness upgrade --no-apply   # fetch, show migration notes and the plan, stop
```

What it does:

1. `git fetch --tags` from the hub's `origin` (skipped with `--offline`), then checks out the
   target: the highest SemVer release tag for `latest` (never backwards: when the hub's
   `VERSION` is at or ahead of that tag, as on a contributor's `main`, it says so and stops
   with exit 0; `--to TAG` still pins, also to an older tag), the named tag (detached), or, for a
   local branch name, `git checkout BRANCH && git pull --ff-only`. When the fetch fails and
   the tag is already in the clone, the local tag is used. Your `local/` directory is
   untouched — it is gitignored. Local changes to tracked files are refused.
2. Prints the CHANGELOG sections (with their **Migration** notes) of every version between
   the hub's `VERSION` before and after.
3. Re-validates your config against the new schema. Deprecated keys warn (two minor releases),
   removed keys error. `harness config migrate` performs pure renames for you, preserving
   comments.
4. Shows the plan, then applies it (with backups, as always; `--yes` skips the prompt).
5. Runs `harness doctor` (with `--offline` when you passed it); its exit status is the
   upgrade's.

A clone made from a `--tag` bundle or a `.run` file has no branches (detached `HEAD`); the
default target works there unchanged. `--to main` in such a clone says so and asks for
`--to TAG`.

## Before upgrading

- `harness sync` — adopt or discard anything you changed inside provider homes, so the plan
  after the upgrade shows only the upgrade.
- Close agent sessions if the release notes mention settings or hook changes; Claude Code
  reads settings at session start and the hook on every call.

## Reading the plan after an upgrade

| Row | Meaning | Action |
|---|---|---|
| `update` | a managed file changes | review the diff; normal |
| `create` | a new skill, agent or rule | normal |
| `orphan` | a file the old version managed and the new one does not | removed after backup |
| `conflict` | you changed a hub-owned key that the new version also changes | keep yours (default) or `--overwrite PATH` |

## Rollback

```sh
cd ~/harness-hub && git checkout 0.2.4     # the version you came from
harness apply                              # re-renders the old version, backing up first
```

Individual files can also be restored from `~/.local/state/harness/backups/<timestamp>/`, which
mirrors the original paths. Config changes made by `config migrate` are backed up next to the
file as `harness.toml.bak.<timestamp>`.

## Upgrading with a `.run` file

Run the newer envelope with the same `--dest` as the installed clone (default
`~/harness-hub`):

```sh
sh harness-hub-X.Y.Z.run --check
sh harness-hub-X.Y.Z.run --yes             # add --offline air-gapped, --config FILE if not local/
```

It unpacks into `~/.local/share/harness/releases/X.Y.Z/`, fetches the bundle's tags into the
clone, points `origin` at the new bundle and runs `harness upgrade --to X.Y.Z` with the
remaining arguments (steps 1-5 above); bootstrap-only flags such as `--no-install-tools` are
dropped with a note, so the install command line works for upgrades too. A dev-build `.run`
(no tag) installs only and refuses an existing clone.

## Following main (contributors)

`harness upgrade --to main` (checkout + `git pull --ff-only`, then plan, apply, doctor). Pin
to tags for day-to-day use; `main` may carry unreleased config changes.
