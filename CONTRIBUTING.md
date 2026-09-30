# Contributing

Thanks for helping. harness-hub is used on real machines to keep AI agents inside governance
rules, so changes are judged first on *can this make an agent do something it should not*,
then on everything else. [ARCHITECTURE.md](ARCHITECTURE.md) is the normative contract; this
page is the practical loop.

## Development loop

```sh
git clone git@github.com:<you>/harness-hub.git && cd harness-hub
git config user.email "<id>+<login>@users.noreply.github.com"   # the gate rejects other addresses
make install        # pre-commit hooks: pre-commit, commit-msg, pre-push
make test           # bin/harness test — guard rows, engine unit tests, bundle tests
make lint           # bin/harness lint + Markdown link check
make gate           # private-identifier gate + its self-test
make docs           # bin/harness docs check (generated regions are current)
make render-check   # render twice into fresh HOMEs, diff -r must be empty
```

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
- [ ] `docs/bundles/<name>.md` exists with a hand-written header, a **Troubleshooting**
      section, and an empty generated region; run `bin/harness docs generate`.
- [ ] `[uninstall].keeps` lists every path the user's tools own (credentials, caches).
- [ ] README bundle table and CHANGELOG updated.

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
- Add a `CHANGELOG.md` entry under `[Unreleased]`. If you add, rename or remove a config key,
  change a default, or change a guard decision, include a **Migration** paragraph that tells
  users exactly what to edit (`harness config migrate` handles pure renames).

## Releases (maintainers)

Semver tags `vX.Y.Z`, `VERSION` file, GitHub release notes = the CHANGELOG section. Before
1.0 a minor release may change config with migration notes; deprecated keys warn for two
minors, then error.
