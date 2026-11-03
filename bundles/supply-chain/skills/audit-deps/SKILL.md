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
  hard finding (use the supply-triage agent). Never runs the checkout's code or tests, never
  installs a scanner or downloads a toolchain, never commits or pushes.
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

An open Dependabot or Renovate pull request for the same package is the repository's fix in
flight: name it and skip that package. Check read-only, only when the CLI is already
authenticated (never ask for a token): `gh pr list -R O/R --state open --search "NAME in:title"`
on GitHub, `glab mr list -R GROUP/REPO --search NAME` on GitLab (open merge requests by
default). No CLI or no access → say the check was skipped, under **Not verified**.

**What this skill never does.** It never runs code from the checkout: no project tests, builds,
scripts, install hooks, `.pnpmfile.cjs`, build backends, cargo wrappers or credential
providers. It never installs into the machine and never lets a tool download a toolchain or an
interpreter (`GOTOOLCHAIN=local`, `UV_PYTHON_DOWNLOADS=never`; a project that would make a tool
switch versions is a manual change). It never signs, commits or pushes.

## Arguments

- `DIR` — the checkout (default `.`).
- `--offline` — passed to `supply audit` (osv-scanner's local databases; the CLI never
  downloads them).
- `--fix patch|minor|none` — how far an upgrade may go: `patch` = the same `MAJOR.MINOR`,
  `minor` (default) = the same major, `none` = report only. **The same major** means the same
  first version component; for `0.x` the same `0.MINOR` (npm, cargo and uv treat `0.4 → 0.5`
  as breaking), and for `0.0.x` the same `0.0.PATCH` (npm `^` and cargo treat every `0.0.x`
  release as breaking, so a `0.0.x` package never upgrades here: **Needs a major upgrade**).
  Nothing ever crosses it.

## Step 1 — orient

```bash
SCRATCH=$(mktemp -d) && echo "SCRATCH=$SCRATCH"
supply detect DIR --json
```

`SCRATCH` holds every intermediate file, outside the checkout. Shell variables may not survive
between tool calls: start each later command with `SCRATCH=<the printed path>` (or use the
provider's scratch directory when the session names one). Every use is written
`"${SCRATCH:?}"`, so an unset variable stops the command instead of writing elsewhere. Quote
the banner (`supply: dir=… ecosystems=… tools=…`).

## Step 2 — audit

```bash
supply audit DIR --json [--offline] > "${SCRATCH:?}/audit-before.json"; echo "rc=$?"
```

| rc | Meaning | Next |
|---|---|---|
| 0 | no finding in what was audited | still read `data.auditors` — then report and stop |
| 1 | findings: `OSV001`/`VUL001`, and also `AUD003` (a fallback auditor failed; status `error`) — or a usage error (no JSON on stdout) | a usage error: fix the command; else Step 3, with every `AUD003` under Unavailable ecosystems |
| 2 | access, tool or config error: osv-scanner failed or printed JSON of an unexpected shape, the offline database is missing, DIR or a `--lockfile` unreadable | report the error line (and the human's download command); stop |
| 3 | no detected ecosystem could be audited | report "unavailable" with `harness install osv-scanner` for the human; stop |

Read `data.auditors[]` (`{ecosystem, tool, status, packages}`) first: `ok` audited (with
`"offline": true`: audited against osv-scanner's local database, as current as its last
download — say so); `partial` some files audited, the rest `AUD001`; `unavailable` no auditor
or no lockfile (`AUD001`); `offline` a fallback auditor that needs the network, not audited;
`error` the auditor failed (`AUD003`). Only `ok` and `partial` count as audited; everything else
is a gap, never "clean". `AUD002` means nothing to audit. Never install a scanner yourself.

## Step 3 — plan the upgrades

For each `OSV001`/`VUL001` finding: the package, the locked version, the fixed versions in the
message, and the lockfile (the finding's `file`). Pick the **lowest fixed version allowed by
`--fix`, ignoring pre-releases** (`-rc.1`, `-beta`, `a1`, `.dev0`; a pre-release is never a
target). None allowed → **Needs a major upgrade**; none published → **No fix available**.
Several findings for one package → one upgrade to the highest of their lowest fixed versions.
Record the **limit** per package (`patch`: below the next `MAJOR.MINOR`; `minor`: below the
next major, `0.MINOR` or `0.0.PATCH`): Step 5 checks the locked result against it.

## Step 4 — upgrade with the ecosystem's tool

One package at a time. Before each command, copy the manifest and the lockfile it may touch to
`"${SCRATCH:?}"`; run from the lockfile's directory. Tool versions are read from `"${SCRATCH:?}"`
(`cd "${SCRATCH:?}" && pnpm --version`), never from DIR, where a version file could make the
tool switch. Each command updates the lockfile (and the manifest where it must) without running
anything from the checkout:

| Lockfile | Command | Needs a manual change instead when |
|---|---|---|
| `uv.lock` | `UV_PYTHON_DOWNLOADS=never uv lock --upgrade-package NAME==X.Y.Z --no-build` | it fails (a dependency or the project itself would have to be built, no usable Python) |
| `requirements.txt` compiled from `requirements.in` | `UV_PYTHON_DOWNLOADS=never uv pip compile requirements.in -o requirements.txt --upgrade-package NAME==X.Y.Z --no-build` (add `--generate-hashes` when the file has hashes) | it fails, or the file's header names another compiler (pip-tools: keep its options; say so) |
| `poetry.lock` | — | always: poetry builds sdists to read their metadata and installs `requires-plugins` from the project; give the human `poetry update NAME --lock` |
| `package-lock.json`, direct dependency | `npm install NAME@SPEC --package-lock-only --ignore-scripts` (SPEC below) | the manifest's spec is not a plain range (`npm:`, git, URL, `file:`, a tag) |
| `package-lock.json`, transitive | `npm update NAME --package-lock-only --ignore-scripts` | the parent's range excludes the fix (npm `overrides`), or Step 5 finds an overshoot |
| `pnpm-lock.yaml` | `npm_config_manage_package_manager_versions=false COREPACK_ENABLE_NETWORK=0 pnpm update NAME@X.Y.Z --lockfile-only --ignore-pnpmfile --ignore-scripts` | `.pnpmfile.cjs` exists; `pnpm update --help` (run in `"${SCRATCH:?}"`) does not list all three flags; or `package.json` `packageManager` names a pnpm version other than the one `pnpm --version` prints in `"${SCRATCH:?}"` (pnpm or corepack would switch, downloading it) |
| `Cargo.lock` | `cargo update -p NAME --precise X.Y.Z` | `rust-toolchain` or `rust-toolchain.toml` exists in the lockfile's directory or any parent (rustup would select, and may download, that toolchain); a `.cargo/config` or `.cargo/config.toml` in those directories sets `credential-provider`, `global-credential-providers`, `rustc`, `rustc-wrapper` or `rustc-workspace-wrapper` (each runs a program the checkout names); `RUSTUP_TOOLCHAIN` is set to a toolchain `rustup toolchain list` (in `"${SCRATCH:?}"`) does not show |
| `go.sum` / `go.mod` | `GOTOOLCHAIN=local go get MODULE@vX.Y.Z && GOTOOLCHAIN=local go mod tidy` | `go` or `toolchain` in `go.mod` is newer than `GOTOOLCHAIN=local go version` (it refuses rather than downloading) |

**npm SPEC keeps the manifest's range prefix** so `--fix` holds: `^1.2.3` → `NAME@^X.Y.Z`,
`~1.2.3` → `NAME@~X.Y.Z`, an exact `1.2.3` → `NAME@X.Y.Z --save-exact`. With `--fix patch` a `^`
range can still resolve past the limit; Step 5 catches it.

The rustup limitation: whether a rustup environment variable reliably stops a toolchain
auto-install has not been confirmed for every rustup version, so the rule is the file check
above, not a variable. A plain `requirements.txt` with `NAME==old`, no hashes and no `.in`
file: change that one `==` version. A hashed file without its source, a transitive dependency
whose parent's range excludes the fix (npm `overrides`, a Cargo parent bump), yarn, or a tool
that is not installed → **Needs a manual change**, with the exact edit and command for the
human. Never edit a lockfile by hand, never `npm audit fix --force`; if the guard asks on a
command, stop and hand it to the user.

## Step 5 — sensor

```bash
supply audit DIR --json [--offline] > "${SCRATCH:?}/audit-after.json"; echo "rc=$?"
supply pins DIR --json > "${SCRATCH:?}/pins-after.json"
git -C DIR diff --stat
```

- **Limit** — for each upgraded package, read its new locked version from the lockfile
  (`package-lock.json` `packages["node_modules/NAME"].version`, `pnpm-lock.yaml`, `uv.lock`
  `[[package]]`, `Cargo.lock`, `go.mod`) and compare it with the limit from Step 3. Past the
  limit (an npm `^` range or `npm update` that went further than `--fix` allows) → copy that
  package's saved manifest and lockfile back from `"${SCRATCH:?}"`, and report it under
  **Needs a manual change** with the version it would have reached.
- Each upgraded package must be gone from the findings of its ecosystem, and `data.auditors`
  must show the same statuses as before (an ecosystem that went from `ok` to `error` is a
  failure to report). A new `supply pins` finding introduced by the diff is a failure too.
- **Tests are not run.** Find the repository's test command (`Makefile`, `package.json`
  `test`, `pytest`, `cargo test`, `go test ./...`) and name it for the human; report the
  upgrade as **untested by this skill**. Running it would execute the checkout's code.

## Report

- **Fixed by this diff** — `package old → new · ids · lockfile`.
- **Needs a major upgrade (human)** — package, locked version, the first fixed major, a pointer
  to its changelog or breaking-change notes.
- **Needs a manual change** — the exact edit or command and why this skill did not make it
  (tool condition, overshoot, poetry).
- **No fix available** — package, ids, and the options from `vuln-triage.md` (replace, mitigate,
  accept with a reason and a review date); hard cases → the `supply-triage` agent.
- **Already in flight** — the open Dependabot or Renovate pull request per skipped package.
- **Unavailable ecosystems** — every auditor not `ok`, with its status and the human's fix
  (`harness install osv-scanner`, a lockfile to commit, the offline database); an `ok` row with
  `"offline": true` is listed with the database caveat.
- **Sensor** — `supply audit` before and after (findings per severity), the limit check,
  `git diff --stat`, and the test command for the human (not run).
- **Not verified** — tests (never run here), reachability (judgement unless `govulncheck` said
  "called"), the pull-request check when skipped, anything skipped. Never leave this out.

## Never

- Never cross a major version (or a `0.MINOR`, or a `0.0.PATCH`), whatever the advisory
  recommends, and never pick a pre-release.
- Never run the project's tests, build, scripts or hooks; name the test command for the human.
- Never let a tool download a toolchain or an interpreter, and never run a tool from DIR to
  learn its version.
- Never hand-edit a lockfile; regenerate it with the ecosystem's tool.
- Never install a scanner or a tool, and never install into the machine.
- Never report `unavailable`, `offline` or `error` as clean.
- Never commit, push or open a merge request: the diff is the user's to review.
