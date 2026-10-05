# Contributing

Thanks for helping. harness-hub is used on real machines to keep AI agents inside governance
rules, so changes are judged first on *can this make an agent do something it should not*,
then on everything else. [PRINCIPLES.md](PRINCIPLES.md) is the core,
[ARCHITECTURE.md](ARCHITECTURE.md) is the normative contract, and this page is the practical
loop. Agents: start with [AGENTS.md](AGENTS.md).

## Principles first

- Every PR names the principle(s) it serves in the PR template's "Principle(s) served" line,
  or writes "neutral". Numbers are enough: "1, 6".
- A change that conflicts with a principle says so and either changes course or proposes the
  principle change in the same PR ([change procedure](principles/README.md#change-procedure)).
- The checks that implement the principles:

  | Principle | Check |
  |---|---|
  | [1 Lightweight](principles/01-lightweight.md) | `tests/unit/test_deps.py` (stdlib imports only), `harness lint` binary allow-list, bash 3.2 parse in CI |
  | [2 Developer-first](principles/02-developer-first.md) | guard reasons state an alternative; doctor `fix` names a real step |
  | [3 Platform for everyone](principles/03-platform-for-everyone.md) | private-identifier gate, template key lint |
  | [4 Install as a platform](principles/04-install-as-a-platform.md) | offline bootstrap smoke test |
  | [5 Distributed as a git repo](principles/05-distributed-as-a-git-repo.md) | `tests/smoke/pack.sh` |
  | [6 Harness engineering](principles/06-harness-engineering.md) | `harness lint` guides/sensors pairing and taxonomy checks, guard test rows |
  | [7 Extensible core](principles/07-extensible-core.md) | PR template, CHANGELOG "Principles" entries |

## Contributions are the steering loop

The harness improves when a recurring problem becomes a guide or a sensor
([principle 6](principles/06-harness-engineering.md)).

- **An agent repeated a mistake** → add or sharpen a guide (rule text, skill step) *and* pair
  it with a sensor (guard rule plus rows, lint rule, test). A guide alone is a hope.
- **A check fired without saying what to do** → fix the cause, then rewrite the message so it
  names the alternative. Agents read these messages as instructions for their next attempt.
- **A sensor fired on legitimate work** → that is a sensor bug: narrow the pattern and add a
  row for the legitimate case.
- **A sensor stayed silent when it should have fired** → add the missed case as a test row
  first, then fix the sensor.
- Agents may draft the rule, row or doc; a human reviews it like any other change.

## Development loop

```sh
git clone git@github.com:<you>/harness-hub.git && cd harness-hub
git config user.email "<id>+<login>@users.noreply.github.com"   # the gate rejects other addresses
make install        # pre-commit hooks: pre-commit, commit-msg, pre-push (unit + smoke only)
make test           # bin/harness test — guard rows, engine unit tests, bundle tests (~5 min; run before pushing guard/skill changes)
make lint           # bin/harness lint + Markdown link check
make gate           # private-identifier gate + its self-test
make docs           # bin/harness docs check (generated regions are current)
make render-check   # render twice into fresh HOMEs, diff -r must be empty
```

The noreply address covers commits you make locally; merges made through the GitHub UI use
your account's primary email instead. Before you merge a pull request in the browser, enable
both switches under GitHub *Settings → Emails*: **Keep my email addresses private** and
**Block command line pushes that expose my email**. Without them the merge commit carries the
primary address and the `gate` job on the default branch fails.

Work against a throw-away home so nothing touches your real provider directories:

```sh
HOME=$(mktemp -d) bin/harness plan --config tests/fixtures/harness.ci.toml
```

Put your own identifiers in `local/gate-denylist.txt` (gitignored, one ERE per line) before
your first commit: the gate then catches your company's hostnames and project keys, not only
the generic shapes. See [tools/gate/README.md](tools/gate/README.md).

## Adding a bundle

Read [ARCHITECTURE §3](ARCHITECTURE.md#3-bundles-bundlesname) first. Checklist:

- [ ] `bundles/<name>/bundle.toml` validates (`bin/harness lint`); `depends_on = ["core"]`
      unless there is a reason; `docs = "docs/bundles/<name>.md"`.
- [ ] Every organisation-specific value is a `[requires.config."<section>.<key>"]` with a
      description, a pattern where it makes sense and a documentation-value `example`.
      Defaults go in `defaults.toml`. Nothing organisation-specific is hard-coded anywhere.
- [ ] Secrets are declared in `[requires.secrets.<id>]` by **path only**, with the tool that
      writes them and a `rotate` runbook. The bundle never reads them.
- [ ] Guard rules in `guard.d/NN-<topic>.sh` use only the engine helpers (`allow`, `ask`,
      `deny`, `defer`, `pending_allow`); pick the numeric prefix from the table in §3; every
      rule has a `# rule: <pattern> -> <decision> : <reason>` comment (feeds
      [hook-policy](docs/reference/hook-policy.md)).
- [ ] `guard.d/tests.sh` has rows for every decision a rule can produce, **including the
      bypass attempts** you thought of (`sh -c`, `xargs`, `cd x &&`, env prefixes, quoting).
- [ ] Every `[[manual_steps]]` has `why`, a click-path or command `how`, and a `verify`
      command; every `[[doctor_checks]]` has a `fix` that names a manual step or a command.
- [ ] Doctor checks that need the network set `offline_skip = true`.
- [ ] `[harness]` declares the bundle's **guides** (`rule`, `skill`, `permission`, `agent`,
      `template`) and **sensors** (`guard`, `doctor`, `test`, `lint`, `review-agent`) as
      `{kind, ref, note}`, each `ref` naming a real path or id in the bundle, plus a
      `coverage_note` saying what the pairing does not cover. `harness lint` shows no
      unpaired-guide or unpaired-sensor warning.
- [ ] Every guard `# rule:` reason states the alternative (what to run, use or ask instead).
- [ ] `[taxonomy]` classifies the bundle: `domain` and `posture`, a `function` default if its
      skills and agents share one, and `[taxonomy.components]` overrides where a component
      differs ([taxonomy](docs/reference/taxonomy.md)). New components follow the naming
      convention there; existing ones are never renamed. `harness lint` shows no
      `taxonomy:` warning and `bin/harness docs generate` has refreshed the
      [catalog](docs/catalog.md).
- [ ] New binaries the bundle's scripts call are declared in `[requires.binaries]`; no
      package-manager install steps ([principle 1](principles/01-lightweight.md)).
- [ ] `docs/bundles/<name>.md` exists with a hand-written header, a **Troubleshooting**
      section, and an empty generated region; run `bin/harness docs generate`.
- [ ] `[uninstall].keeps` lists every path the user's tools own (credentials, caches).
- [ ] README bundle table and CHANGELOG updated.

An organisation's own bundles can also live in its **org platform instance** (a private fork
or mirror) under `bundles/<org>-<topic>/`; see the
[self-host runbook](docs/runbooks/self-host.md).

Org-specific content (your hosts, your cluster list, your ticket types) belongs in a
**private bundle** under `local/bundles/<org>/`, same layout, never in a public one.

## Adding a provider

Read [ARCHITECTURE §4](ARCHITECTURE.md#4-providers-providersname) and
[§5](ARCHITECTURE.md#5-guard). Checklist:

- [ ] `providers/<name>/provider.toml` — every target path, its write mode and the
      `[capabilities]` honestly stated (`hook_enforced = false` when there is no pre-tool hook).
- [ ] `shim.sh` if the provider has command hooks: translate its stdin to the neutral
      envelope and the decision back. Map `ask` through `[providers.<name>].ask_as`.
- [ ] Shim fixtures `tests/*.in.json` → `*.out.json` for allow, deny, ask, an unknown tool
      (pass through) and malformed JSON (deny: fail closed).
- [ ] `README.md` with a "verified against <version> on <date>" line (the weekly
      provider-drift workflow parses it) and the provider's quirks.
- [ ] `docs/providers/<name>.md`, README capability matrix, SECURITY.md coverage table.

## Guard tests and goldens

- Guard rows are the specification. A behaviour change without a row change will be
  rejected; a row change without a reason in the PR description too.
- Goldens (rendered output, skill output) are regenerated with `UPDATE=1 bin/harness test`
  and **reviewed as a diff** before committing. For pure renames, check the diff is a token
  substitution: `git diff --word-diff-regex='[A-Za-z0-9_./-]+'`.
- Test data uses documentation values only: `PROJ-123`, `example.com`, `/home/u`,
  `192.0.2.0/24`, `203.0.113.0/24`, `111122223333`.

## bash 3.2 rules

macOS ships bash 3.2 and BSD userland; CI parses every script with `/bin/bash -n` there.

- No `mapfile`/`readarray`, `declare -A`, `${var,,}`/`${var^^}`, `|&`, `&>>`, `coproc`,
  negative array indices. If a bash ≥ 4 feature is unavoidable, guard it with a
  `BASH_VERSINFO` check that `doctor` reports.
- Empty arrays under `set -u` break 3.2: expand as `${arr[@]+"${arr[@]}"}`.
- No GNU-only tools or flags: `timeout`, `readlink -f`, `sed -i`, `stat -c`, `sha256sum`,
  `grep -P`, `date -d`, `xargs -r`. Use `hn_timeout`, `hn_realpath`, `hn_sha256` from
  `bundles/core/lib/compat.sh`, or python.
- Python is stdlib only and must run on 3.9 (no `match`, no `X | Y` type unions at runtime,
  `tomllib` only through the vendored fallback).

## Commits and pull requests

- Work on a branch and open a PR; nothing is pushed to `main` directly.
- **No ticket keys in commit subjects or branch names** (mention them in the body), and
  **no closing keywords anywhere** — write "#12" or "see #12", never "Closes #12",
  "Fixes #12" or "Resolves #12". This project's own guard denies them for agents, and
  issue state stays a human decision here too.
- Subjects in the imperative, ≤ 72 characters, optional scope: `github: deny gh auth token`.
- Every PR fills the [PR template](.github/PULL_REQUEST_TEMPLATE.md) checklist.
- No DCO or CLA; by contributing you agree your work is licensed under the MIT license.
- Name the principle(s) served, or "neutral", in the PR description.
- Add a `CHANGELOG.md` entry under `[Unreleased]`. If you add, rename or remove a config key,
  change a default, or change a guard decision, include a **Migration** paragraph that tells
  users exactly what to edit (`harness config migrate` handles pure renames).

## Releases (maintainers)

Versioning is [SemVer 2.0.0](https://semver.org/spec/v2.0.0.html): annotated tags
`X.Y.Z` (pre-releases `X.Y.Z-rc.N`) on `main`, and the `VERSION` file holds the same string.
Tags are bare SemVer, no `v` prefix; a `v`-prefixed tag is ignored by the release workflow.
Pushing the tag is the release: `.github/workflows/release.yml` runs the
preflight (`harness release check`), the full CI suite, `harness pack --self-extract` with the
four tool platforms, a `.run` install smoke, and publishes the GitHub Release with the notes
from this CHANGELOG section and build provenance. Before 1.0 a minor release may change config
with migration notes; deprecated keys warn for two minors, then error.

1. **Release PR** (branch, never `main`): bump `VERSION` to `X.Y.Z`; rename
   `## [Unreleased]` to `## [X.Y.Z] - YYYY-MM-DD` and add an empty `## [Unreleased]` above
   it; update the compare links at the bottom (`[Unreleased]: …/compare/X.Y.Z...HEAD`,
   `[X.Y.Z]: …/releases/tag/X.Y.Z`); `make docs-generate`; `make test lint gate docs`.
2. **Merge** it (humans merge).
3. **Tag** the merge commit on an up-to-date `main` and run the preflight:

   ```sh
   git switch main && git pull --ff-only
   git tag -a X.Y.Z -m "harness-hub X.Y.Z"
   make release-check TAG=X.Y.Z
   ```

4. **Push the tag**: `git push origin X.Y.Z`. The `release` workflow does the rest; a tag
   name that is not bare SemVer 2.0.0 (`v1.2.3` included) ends green with every job skipped.
5. **Verify** the published release:

   ```sh
   gh release view X.Y.Z -R matt-kh/harness-hub
   gh release download X.Y.Z -R matt-kh/harness-hub -D /tmp/rel
   gh attestation verify /tmp/rel/harness-hub-X.Y.Z.bundle -R matt-kh/harness-hub
   sh /tmp/rel/harness-hub-X.Y.Z.run --check && (cd /tmp/rel && shasum -a 256 -c SHA256SUMS)
   ```

Pre-releases: `VERSION` must equal the pre-release string exactly (`1.3.0-rc.1`) and the
CHANGELOG section is `## [1.3.0-rc.1] - YYYY-MM-DD`; the GitHub release is marked
pre-release and `harness upgrade` (default `--to latest`) skips it.

Never move or delete a published tag; fix forward with the next patch version. When a run
fails after the tag was pushed (a flaky download, say), re-run it for the same tag; it never
overwrites a published release (a draft left by a failed upload is deleted and recreated, the
tag stays). `--ref X.Y.Z` is required: the CI suite tests the selected ref, so the preflight
refuses a dispatch whose ref is not the tagged commit:

```sh
gh workflow run release.yml -R matt-kh/harness-hub --ref X.Y.Z -f tag=X.Y.Z -f publish=true
```

Rehearse without publishing: `gh workflow run release.yml -R matt-kh/harness-hub --ref BRANCH`
(a dev build; the `rel` artifact holds the files), or locally
`make release-build TAG=X.Y.Z` (`TOOLS=` for an offline run) after a throw-away local tag.
