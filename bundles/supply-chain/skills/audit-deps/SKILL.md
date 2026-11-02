---
name: audit-deps
description: >-
  Fix known-vulnerable dependencies within the same major version, as a diff for review: runs
  `supply audit`, upgrades each vulnerable package to its fixed version with the ecosystem's own
  lockfile tool (uv, npm, pnpm, cargo, go), re-runs `supply audit` as the check and reports
  what was fixed, what needs a major upgrade, what has no fix and which ecosystems could not
  be audited. Use when the user says fix the vulnerabilities, bump vulnerable dependencies,
  "supply audit found …", a CVE, GHSA or OSV id in a lockfile, `npm audit fix`, Dependabot
  security alerts, or runs /audit-deps. NOT for pinning actions, images or git dependencies
  (use /pin-deps), NOT for major upgrades (listed for the human), and NOT for investigating one
  hard finding (use the supply-triage agent). Never installs a scanner, never commits or
  pushes.
argument-hint: "[DIR] [--offline] [--fix patch|minor|none]"
model: {{ core.model_policy.execute }}
---

# audit-deps — patch vulnerable dependencies within the major

Known vulnerabilities in locked versions are fixed by upgrading to a fixed release with the
ecosystem's own tool, so the lockfile stays generated, never hand-edited. Crossing a major
version is a design change: it is listed for the human, never applied. The decision tree is
`{{ provider.skills_dir }}/supply/references/vuln-triage.md`.

**Step 0 — repository-level harness (principle 8).** This is a user-level skill. Read the
repository's declaration first:

```bash
harness repo owns supply-chain/skills/audit-deps   # rc 0 = owned (prints why) → stop; rc 1 = carry on
```

If it is owned (by id or by its domain `security`), or the repository ships its own skill for
the same workflow, this skill yields: say so in one line, name the repository-level skill or
convention, and stop — nothing below runs and nothing is written. Never edit the
repository's harness to fit this skill. `harness repo` explains everything the
repository declares and any `.claude/skills|agents` name collisions.

An open Dependabot or Renovate security pull request for the same package is the repository's
fix in flight: name it and skip that package.

## Arguments

- `DIR` — the checkout (default `.`).
- `--offline` — passed to `supply audit` (osv-scanner's local databases; the CLI never
  downloads them).
- `--fix patch|minor|none` — how far an upgrade may go: `patch` = the same `MAJOR.MINOR`,
  `minor` (default) = the same major, `none` = report only. **The same major** means the same
  first version component, and for `0.x` the same `0.MINOR` (npm, cargo and uv treat `0.4 → 0.5`
  as breaking). Nothing ever crosses it.

## Step 1 — orient

```bash
supply detect DIR --json
```

Quote the banner (`supply: dir=… ecosystems=… tools=…`).

## Step 2 — audit

```bash
supply audit DIR --json [--offline] > "$SCRATCH/audit-before.json"; echo "rc=$?"
```

| rc | Meaning | Next |
|---|---|---|
| 0 | no finding in what was audited | still read `data.auditors` — then report and stop |
| 1 | findings | Step 3 |
| 2 | osv-scanner or an auditor failed, an unexpected JSON shape, an offline database missing | report the error line (and the human's download command); stop |
| 3 | no detected ecosystem could be audited | report "unavailable" with `harness install osv-scanner` for the human; stop |

Read `data.auditors[]` (`{ecosystem, tool, status, packages}`) first: `ok` audited; `partial`
some files audited, the rest `AUD001`; `unavailable` no auditor or no lockfile (`AUD001`);
`offline` not audited offline; `error` the auditor failed (`AUD003`). Only `ok` and `partial`
count as audited; everything else is a gap, never "clean". `AUD002` means nothing to audit.
Never install a scanner yourself.

## Step 3 — plan the upgrades

For each `OSV001`/`VUL001` finding: the package, the locked version, the fixed versions in the
message, and the lockfile (the finding's `file`). Pick the lowest fixed version allowed by
`--fix`. None allowed → **Needs a major upgrade**; none published → **No fix available**.
Several findings for one package → one upgrade to the highest of their lowest fixed versions.

## Step 4 — upgrade with the ecosystem's tool

Run from the lockfile's directory; each command updates the lockfile (and the manifest where it
must) without running the project's install scripts:

| Lockfile | Command |
|---|---|
| `uv.lock` | `uv lock --upgrade-package NAME==X.Y.Z` |
| `poetry.lock` | `poetry update NAME --lock` (only within the manifest's range; else Needs a manifest change) |
| `requirements.txt` compiled from `requirements.in` | `uv pip compile requirements.in -o requirements.txt --upgrade-package NAME==X.Y.Z` (add `--generate-hashes` when the file has hashes) |
| `package-lock.json` | `npm install NAME@X.Y.Z --package-lock-only --ignore-scripts` for a direct dependency; `npm update NAME --package-lock-only --ignore-scripts` for a transitive one |
| `pnpm-lock.yaml` | `pnpm update NAME@X.Y.Z --lockfile-only` |
| `Cargo.lock` | `cargo update -p NAME --precise X.Y.Z` |
| `go.sum` / `go.mod` | `GOTOOLCHAIN=local go get MODULE@vX.Y.Z && GOTOOLCHAIN=local go mod tidy` |

A plain `requirements.txt` with `NAME==old` and no hashes and no `.in` file: change that one
`==` version. A hashed file without its source, a transitive dependency whose parent's range
excludes the fix (npm `overrides`, a Cargo parent bump), yarn, or a tool that is not installed
→ **Needs a manual change**, with the exact edit for the human. Never edit a lockfile by hand,
never `npm audit fix --force`, never install into the machine; if the guard asks on a command,
stop and hand it to the user.

## Step 5 — sensor

```bash
supply audit DIR --json [--offline] > "$SCRATCH/audit-after.json"; echo "rc=$?"
supply pins DIR --json > "$SCRATCH/pins-after.json"
git -C DIR diff --stat
```

Each upgraded package must be gone from the findings of its ecosystem, and `data.auditors`
must show the same statuses as before (an ecosystem that went from `ok` to `error` is a
failure to report). A new `supply pins` finding introduced by the diff is a failure too. If the
repository has a test command you can find (`Makefile`, `package.json` `test`, `pytest`,
`cargo test`, `go test ./...`), run it; else say the upgrade is untested.

## Report

- **Fixed by this diff** — `package old → new · ids · lockfile`.
- **Needs a major upgrade (human)** — package, locked version, the first fixed major, a pointer
  to its changelog or breaking-change notes.
- **Needs a manual change** — the exact edit and why the tool could not make it.
- **No fix available** — package, ids, and the options from `vuln-triage.md` (replace, mitigate,
  accept with a reason and a review date); hard cases → the `supply-triage` agent.
- **Unavailable ecosystems** — every auditor not `ok`, with its status and the human's fix
  (`harness install osv-scanner`, a lockfile to commit, the offline database).
- **Sensor** — `supply audit` before and after (findings per severity), `git diff --stat`, the
  test command and its result.
- **Not verified** — reachability (judgement unless `govulncheck` said "called"), tests not
  run, anything skipped. Never leave this out.

## Never

- Never cross a major version (or a `0.MINOR`), whatever the advisory recommends.
- Never hand-edit a lockfile; regenerate it with the ecosystem's tool.
- Never install a scanner or a tool, and never install into the machine.
- Never report `unavailable`, `offline` or `error` as clean.
- Never commit, push or open a merge request: the diff is the user's to review.
