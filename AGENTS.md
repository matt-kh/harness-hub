# AGENTS.md — working in harness-hub

Instructions for AI coding agents (and humans) changing this repository. `CLAUDE.md` is a
symlink to this file.

## Read first

1. [PRINCIPLES.md](PRINCIPLES.md) — the seven principles; open the per-principle document in
   `principles/` when your change touches that area.
2. [ARCHITECTURE.md](ARCHITECTURE.md) — the normative contracts: layout, config, bundle
   manifest, provider adapters, guard, engine commands, distribution.
3. [CONTRIBUTING.md](CONTRIBUTING.md) — checklists for bundles, providers, guard rows, releases.

## Development loop

```sh
make install        # pre-commit hooks (pre-commit, commit-msg, pre-push)
make test           # bin/harness test: guard rows, unit, bundle, skill, provider, smoke suites
make lint           # bin/harness lint + tools/gate/check-links.sh
make gate           # tools/gate/private-ids.sh + its self-test
make docs           # bin/harness docs check (generated regions are current)
make docs-generate  # bin/harness docs generate, after changing manifests, CLI or guard rules
make render-check   # render twice into one fresh HOME; diff must be empty
```

- Work against a throw-away home: `HOME=$(mktemp -d) bin/harness plan --config tests/fixtures/harness.ci.toml`.
- Faster loops: `bin/harness test unit`, `bin/harness test guard`, `bin/harness test <bundle>`.
- Unit tests alone: `python3 -m unittest discover -s tests/unit`.

## Repository map

| Path | What |
|---|---|
| `bootstrap`, `bin/harness` | entry point and launcher (bash; execs `python3 -m harness`) |
| `lib/harness/` | engine, python 3.9+ stdlib only; `_vendor/tomli` for python < 3.11 |
| `schema/` | JSON Schemas for `harness.toml`, `bundle.toml`, `provider.toml` |
| `bundles/<name>/` | one capability each: rules, skills, agents, `guard.d/`, permissions, doctor, manual steps |
| `providers/<name>/` | adapters: target paths, write modes, capabilities, hook shims |
| `profiles/` | named bundle and provider selections |
| `tools/*.lock.json` | pinned tool downloads (version, URL, sha256 per os/arch) |
| `tools/gate/` | private-identifier gate and Markdown link check |
| `tests/` | unit tests, fakes, fixtures, smoke scripts |
| `docs/` | hand-written pages with generated regions |
| `principles/` | one document per principle |
| `local/` | gitignored private overlay; never read it for content to publish, never commit it |
| `build/` | gitignored render products |

## Hard rules

- **No organisation identifiers** in any tracked file, file name, commit message or author
  address: no real hostnames, project keys, cluster names, account ids, internal IPs or work
  emails. Use documentation values (`example.com`, `PROJ-123`, `192.0.2.x`, `/home/u`).
  Run `tools/gate/private-ids.sh` before committing.
- **Standard library only** under `lib/harness/` (plus `_vendor`). No pip, npm or other
  package managers in any install path. New binaries in scripts must be on the lint
  allow-list or declared in the bundle's `requires.binaries`.
- **bash 3.2 must parse every script** and BSD userland must run it: no `mapfile`,
  `declare -A`, `${v,,}`, `sed -i`, `readlink -f`, `timeout`, `grep -P`; regexes are POSIX ERE.
  Use the helpers in `bundles/core/lib/compat.sh`. Details: CONTRIBUTING "bash 3.2 rules".
- **Every guard deny or ask reason states the alternative** (what to run or do instead), in
  its `# rule: <pattern> -> <decision> : <reason>` comment and in the emitted reason.
- **Every guide has a sensor and every sensor a guide.** Declare both in the bundle's
  `[harness]` section (`guides`, `sensors`, `coverage_note`); `harness lint` warns otherwise.
- **Every component is classified and never renamed.** Its id is derived from its path
  (`k8s/agents/k8s-triage`); its domain, function and posture live in the bundle's
  `[taxonomy]` only, never in skill or agent front matter. New components follow the naming
  convention in [docs/reference/taxonomy.md](docs/reference/taxonomy.md); `harness lint`
  warns on anything unclassified.
- **Guard behaviour changes come with test rows** in `bundles/<b>/guard.d/tests.sh`,
  including bypass attempts.
- **Generated regions are never hand-edited** (`<!-- generated:begin … -->` to
  `<!-- generated:end -->`). Change the source (manifest, adapter, CLI help, `# rule:`
  comment) and run `bin/harness docs generate`.
- **Commit identity is a noreply address**: `git config user.email "<id>+<login>@users.noreply.github.com"`.
- **No closing keywords** anywhere (`Closes #N`, `Fixes #N`, `Resolves #N`); write "#N" or
  "see #N". No ticket keys in commit subjects or branch names.
- **Never push to `main`.** Work on a branch, open a PR; humans merge.
- **Secrets never enter the repo or a command line.** Check auth with each tool's own status
  command.
- **Config changes carry a migration.** Adding, renaming or removing a config key, changing a
  default or a guard decision needs a CHANGELOG **Migration** paragraph.

## The steering loop

- When a check fires (guard, lint, test, gate, doctor), fix the cause first.
- Then, if the message did not tell you what to do instead, improve the message in the same
  PR: the next agent should be able to act on it without reading the source.
- When the same mistake recurs, add or sharpen a guide (rule, skill text) and pair it with a
  sensor (guard row, lint rule, test) rather than relying on a reviewer to catch it again.
- A sensor that fires on legitimate work is a bug: fix its pattern and add the row.

## Before you finish

- `make test`, `make lint`, `make gate`, `make docs` pass, or you state exactly which did not
  and why.
- The PR description names the principle(s) served, or "neutral", and fills the
  [PR template](.github/PULL_REQUEST_TEMPLATE.md).
- `CHANGELOG.md` has an `[Unreleased]` entry.
