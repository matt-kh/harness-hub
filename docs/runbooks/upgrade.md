# Runbook: upgrade

```sh
harness upgrade              # latest release tag
harness upgrade --to v0.3.1  # a specific version
harness upgrade --no-apply   # fetch, show migration notes and the plan, stop
```

What it does:

1. `git fetch` of the hub's remote, then checks out the target tag (or pulls `main` if you
   follow it). Your `local/` directory is untouched — it is gitignored.
2. Prints the **Migration** notes of every CHANGELOG version between the version recorded in
   your state files and the target.
3. Re-validates your config against the new schema. Deprecated keys warn (two minor releases),
   removed keys error. `harness config migrate` performs pure renames for you, preserving
   comments.
4. Shows the plan, then applies it (with backups, as always).
5. Runs `harness doctor`.

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
cd ~/harness-hub && git checkout v0.2.4    # the version you came from
harness apply                              # re-renders the old version, backing up first
```

Individual files can also be restored from `~/.local/state/harness/backups/<timestamp>/`, which
mirrors the original paths. Config changes made by `config migrate` are backed up next to the
file as `harness.toml.bak.<timestamp>`.

## Following main (contributors)

`git -C ~/harness-hub pull --ff-only && harness plan && harness apply`. Pin to tags for
day-to-day use; `main` may carry unreleased config changes.
