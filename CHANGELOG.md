# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). Before 1.0, a minor release may
change configuration; such entries carry a **Migration** paragraph, and `harness upgrade`
prints every one between your applied version and the new one.

## [Unreleased]

### Docs

- [docs/roadmap.md](docs/roadmap.md): planned bundles and extensions by tranche (P0 coverage
  gaps and lint sensors; core git and shell hygiene, `run-checks`, `worktree`, Jira Cloud, the
  `ci` bundle; then the secret-tooling, toolchain, containers, release, cloud, iac, db, hosts
  and digest bundles), the guard prefix bands reserved for them, two proposed taxonomy domains and the
  rejected candidates. Linked from README and ARCHITECTURE §3.

### Principles

- `principles_version: 1`: principles 1–7 (lightweight; developer-first; a platform for
  everyone; installed as a platform, distributable air-gapped; distributed as a git
  repository; harness engineering; extensible core). `PRINCIPLES.md` is the summary and index,
  `principles/NN-*.md` holds one document per principle.
- `principles_version: 2`: principle 8, **User-level by design: repository-level wins** —
  every hub component yields wholesale to an equivalent repository-level harness, declared
  in `.harness.toml` or found by name or text; only the developer's own credentials never
  yield: the credential-file denies (`core/guard.d/20-credentials`, `core/permissions`) and
  the `# never-yields:` preludes (commands that print a stored credential, the ask on writing
  `.harness.toml`). Checks: the `yields` taxonomy facet and lint rule, guard rows for
  `.harness.toml`, `harness repo`.
- `principles_version: 3`: principles 9 and 10. **Deterministic by construction** — any
  output reproducible from structured input (ticket bodies, facts JSON, rendered files,
  release artifacts, the built guard) is produced by a script with goldens or unit tests and
  named in the skill as the only way; the model supplies judgement and input, and judgement
  outputs keep a shape a script or guard row checks. **Composable bundles** — one canonical
  source per component, shared through declared dependencies, other bundles' CLIs and
  inlined marked blocks kept identical by `bundles/core/lib/sync_inline.py`; skill fragments
  are for org overlays only. Existing checks: render-determinism smoke, guard-build `cmp`,
  pack unit tests, create-ticket and k8s goldens, `stability` and `fragments-target` lint,
  `sync_inline.py --check`. Follow-ups (roadmap): `work-ticket` and `gdoc` suites,
  `stability` at `beta`, helper bodies outside markers, shared Jira facts, `tests-boilerplate`.
  Resolves the principle 1 open question on a shared python helper library.

### Added

- `obs` bundle (experimental; domain `operations`, read-only): the stdlib `obs` CLI
  (`backends [--probe]`, `query`, `logs`, `traces`, `trace`, `services`, `alerts`,
  `dashboards [--export]`, `lint`, `redact`) with SigNoz (verified against the v0.121.x
  source), Prometheus and Grafana adapters; every request goes through one helper with a read
  allow-list (GET, and POST only to the query endpoints), every log line, span attribute and
  label value through the shared `core` redact block (plus bearer/basic credentials and
  `obs.redact_extra_re`). Skill `obs` with references (RED/USE walk, alerts as code, one page
  per backend with the exact endpoints), agent `obs-triage` (investigate), rule
  `rules/32-obs.md`, guard section `32-obs`: reading `~/.config/obs/*` denies (a
  `# never-yields:` prelude), a literal API key on a curl/wget/http/xh command line denies,
  raw requests to a host matching `obs.hosts_re` ask, `amtool silence add|expire|import`,
  `amtool alert add`, `logcli query --tail|-f` and `grafana-cli admin|plugins install|remove`
  ask. Permissions, five doctor checks, manual steps `configure-backends` and `obs-api-key`,
  runbook [rotate-obs-key](docs/runbooks/rotate-obs-key.md), docs page
  [obs](docs/bundles/obs.md). Golden suite `skills/obs/scripts/tests/run.sh` (50 cases,
  fixture-routed HTTP via `tests/fakes/http_fixture.py`, and an `OBS_DRY_RUN` request-log case
  asserting only read endpoints); 106 guard rows incl. bypasses (path-qualified clients such as
  `/usr/bin/curl`), the `operations` yield and `OBS_HOSTS_RE` read from `guard.env`. The CLI
  never follows a redirect (the key stays on the configured host), maps 404, 3xx and a non-JSON
  answer to exit 2 (exit 3 only for a verb the backend kind lacks), refuses a backend `url` with
  userinfo, keeps `--json` output a whole document under `--max-bytes` (`"truncated"`), refuses
  to overwrite an export without `--force`, compiles `obs.redact_extra_re` on its own (a leading
  `(?i)` works) and checks `obs.hosts_re` with `grep -E`, as the guard applies it.
- `tests/fakes/http_fixture.py`: the `--log` line's `auth=yes` also counts an `*-API-KEY`
  header (SigNoz), not only `Authorization`.
- `ticket-workflow`: golden suite for the `work-ticket` scripts
  (`skills/work-ticket/scripts/tests/run.sh`, 61 cases): provider dispatch, the GitHub and
  GitLab preflights, `issue-facts.sh`, `jira-facts.sh` and `lib/repo-facts.sh`, each run in a
  throw-away git repository against fixture-routed `gh`/`glab`/`jira` stubs
  (`bundles/ticket-workflow/tests/stubs/`; an unrouted call fails the case). CI files are
  parsed with PyYAML pinned on (a JSON-backed stand-in) and off, so both branches run on any
  host. Invariants: one JSON object on stdout, read-only `gh`/`glab`/`jira` calls, `-R` on
  every list/view, no credential from a credentialed remote in any output, fixture
  repositories unchanged. `create-ticket`'s suite adds twelve `create-facts.sh` goldens (Jira
  and GitHub, field-id config, unreachable, unauthenticated, not installed, repository-owned).
- `tools/gate/companions.sh`, the companion-file gate: a branch whose guard code in
  `bundles/<b>/guard.d/NN-*.sh` (or `bundles/core/guard/engine*.sh`) changed needs
  `guard.d/tests.sh` changes, a net-new `# rule: … -> D :` needs an added `D` row (`tr` for
  ask/deny), and a change under `bundles/`, `lib/harness/`, `providers/`, `schema/`, `bin/`,
  `profiles/`, `templates/`, `bootstrap` or `tools/*.lock.json` needs a new `[Unreleased]`
  line. Waivers: `no-rows: <reason>` / `no-changelog: <reason>` in a commit body or the PR
  description. Runs in the CI `gate` job on pull requests, as a pre-push hook and in
  `make gate`; self-test `tools/gate/tests/companions-selftest.sh` on ubuntu and macOS.
- `README.md` generated regions, rendered by `harness docs generate` and checked by
  `harness docs check`: the bundle table (`bundles/*/bundle.toml#readme`: domain / posture,
  stability, summary with `{{ key }}` placeholders shown as the key's `example` or `<key>`, and
  the manual-step count linked to the bundle page), the provider matrix with tiers
  (`providers/*/provider.toml#readme`), the principle heading, count and list
  (`PRINCIPLES.md#readme`) and the core bundle's required binaries
  (`bundles/core/bundle.toml#readme`).
- Companion-file gate check `readme`: a branch that changes `bootstrap`, `bin/harness`,
  `lib/harness/cli.py`, `PRINCIPLES.md`, `principles/`, a `bundle.toml` or `provider.toml`,
  adds or deletes a bundle or provider, or changes the getting-started, distribution,
  governance, repo-level, runbook, `SECURITY.md` or `LICENSE` pages needs a `README.md`
  change; `no-readme: <reason>` waives it. `--only readme` runs it alone.
- `harness pack [--out DIR] [--tag TAG] [--tools os/arch,...]`: writes the release artifact,
  a `git bundle` of the hub plus optional pinned tool archives, `SHA256SUMS` and
  `INSTALL.txt`. Refuses a dirty tree and never includes `local/`.
- `harness verify FILE.bundle`: `git bundle verify`, the bundle's heads and tags, and the
  `SHA256SUMS` check.
- `harness bootstrap --from FILE.bundle [--dest DIR] [--origin URL]`: clone a bundle file and
  run the clone's bootstrap.
- Bundle manifests: optional `[harness]` section with `guides`, `sensors` and
  `coverage_note`, filled in for every public bundle; generated "Guides and sensors" tables
  and a harness coverage reference.
- `harness lint` warnings for bundles with unpaired guides or sensors, guard rule reasons
  without an alternative, and script binaries outside the allow-list; a unit test that keeps
  the engine on the python standard library.
- `AGENTS.md` (with `CLAUDE.md` as a symlink): instructions for agents changing this repo.
- `HARNESS_BUILD_DIR`: where compiled config and the built guard go; tests and smoke scripts set
  it to a temporary directory so they never touch a live hub's `build/`.
- Component taxonomy ([docs/reference/taxonomy.md](docs/reference/taxonomy.md)): every
  rule, skill, agent, guard section, permission list, MCP server, CLI, installer, doctor
  check and manual step has a stable path-derived id (`k8s/agents/k8s-triage`) and a
  domain, function and posture; kind, control, model and decisions are derived. Bundle
  manifests gain an optional `[taxonomy]` section (`domain`, `posture`, `function`,
  `[taxonomy.components]` overrides), filled in for every public bundle. Nothing is renamed
  and rendered provider files are unchanged.
- `harness catalog [--kind K] [--bundle B] [--domain D] [--json]`: every bundle, component,
  provider and profile with its id and facets.
- Generated docs: [catalog](docs/catalog.md) (every component by kind, domain × posture
  matrix), the taxonomy vocabulary, and a "Components" section on every bundle page.
- `harness lint` rule `taxonomy`: errors for overrides that name no component, postures on
  kinds that take none, functions that contradict a kind's fixed one, component postures
  stronger than the bundle's and the reserved bundle names `providers` / `profiles`;
  warnings for unclassified public bundles, skills, agents, CLIs and MCP servers, read-only
  agents in auto permission mode, and components `[harness]` does not declare.
- Docs: [distribution](docs/distribution.md) (tiers, release artifact, versioning), the
  [self-host runbook](docs/runbooks/self-host.md) for org platform instances, a "Guides and
  sensors" section in concepts, a bundle-file path in getting started.
- `harness pack --self-extract`: also writes `harness-hub-<version>.run`, a POSIX sh header
  (tracked as `lib/harness/selfextract-header.sh`) plus a deterministic uncompressed tar of the
  bundle, `INSTALL.txt`, `SHA256SUMS` and tool archives. `sh FILE.run --check | --list |
  --extract DIR`; run it to unpack into `~/.local/share/harness/releases/<version>/`
  (`--release-dir`), clone into `--dest` (default `~/harness-hub`) and bootstrap, or, against
  an existing clone, fetch its tags, point `origin` at its bundle and `harness upgrade`. The
  bundle stays the release; the outer `SHA256SUMS` lists the `.run`. On the upgrade path the
  bootstrap-only flags (`--no-install-tools`, `--bundles X`, ...) are dropped with a note, so
  the install command line also upgrades; a dev-build `.run` (no tag) installs only and
  refuses an existing clone.
- `harness verify FILE.run`: `sh FILE.run --check` plus the `SHA256SUMS` check.
- `harness release check [TAG] [--remote NAME] [--branch NAME] [--no-remote] [--json]`: the
  release preflight (bare SemVer 2.0.0 tag `X.Y.Z[-pre]`, no `v` prefix and no `+build`,
  annotated, `VERSION` and the dated CHANGELOG section match, `[Unreleased]` emptied, no
  `local/`, clean tree, tag on `origin/main`, unique release asset names) and `harness release
  notes TAG [--dir DIR] [--out FILE]`; `make release-check TAG=…` and `make release-build TAG=…
  [TOOLS=…]`.
- `.github/workflows/release.yml`: a tag push whose name is bare SemVer 2.0.0
  (`X.Y.Z[-pre]`; a `v`-prefixed tag is skipped) runs the preflight,
  the CI suite (`ci.yml` is now also a reusable workflow), pack with the four tool platforms
  and `--self-extract`, a `.run` install smoke, and publishes a GitHub Release (pre-release
  for `-rc.N` tags) with notes from this file and build provenance; any other tag name ends
  green with nothing released. `workflow_dispatch` makes dry-run dev builds or re-runs a tag
  (with `--ref` the tag itself; a re-run replaces a draft left by a failed upload, never a
  published release).
- SemVer 2.0.0 helpers (`util.SEMVER_RE`, `parse_semver`, `is_prerelease`, `version_key`
  with §11 precedence); `harness upgrade` orders CHANGELOG sections with them.
- `.harness.toml` repository declaration (`[repo]`, `[owns] domains/components`, `[overrides]`),
  read by the guard from the hook cwd (not from a command's target) and by skills at
  preflight; `schema/repo.schema.json`. A TOML subset parsed without a subshell per line;
  `[owns]` keys are arrays, a repeated key is ignored (the first one counts), and a file over
  16 KiB or 400 lines is ignored as a whole; stderr notes are capped at five per command.
- Asks on writing `.harness.toml`: `Write(**/.harness.toml)` and `Edit(**/.harness.toml)` in
  the core permission list, and a guard ask on shell writes (`>`, `>>`, `tee`, `cp`, `mv`,
  `dd of=`, `sed -i`, `perl -i`, `harness repo init --write`) in a never-yields prelude of
  `core/guard.d/30-git`: the declaration lifts user-level rules, so a human reviews and
  commits it.
- `harness repo [show|owns ID|init [--write]]`.
- `yields` taxonomy facet (derived) with lint rule `yields`; `# repo-override:` comments
  generating the override allow-list and the hook-policy "Repo overrides" table; a `yields`
  column in the hook-policy rule table (`owns <domain>` or `never`). Lint refuses rule code
  above a `repo_owns` line outside a `# never-yields:` prelude and override names that are
  not `WORK_TICKET_*`.
- `docs/repo-level.md`: what the hub does inside a repository, the `.harness.toml`
  reference, the Claude Code collision facts, per-provider notes, the credential exemption.
- `bundles/core/lib/harness_repo.{sh,py}` helpers; `[precedence]` in provider adapters.
- Guard section 75 (bundle `ticket-workflow`): asks on branches created with a ticket key or
  `#N` in the name (`git switch -c`, `checkout -b`, `branch`, `worktree add -b`), on commits
  whose first `-m` starts with a ticket key, on `git worktree add` of a `-sub-` branch outside
  `../<repo>_<branch>`, and on merges of a `-sub-` branch without `--squash`. All decisions
  are deferred asks; `WORK_TICKET_KEY_IN_BRANCH=1` lets the two key rules pass.
- `harness lint` rules, each message saying what to do instead:
  `env-provides` (error: a `[provides.env]` key without a prefix the guard's guard.env parser
  accepts; the list is parsed from `bundles/core/guard/engine.sh`),
  `rule-guard-pairing` (warning: a `rules/NN-x.md` without a `guard.d/NN-*.sh` or the reverse,
  unless `coverage_note` names `x`), `permissions-vs-guard` (error: a `Bash(<prefix>:*)` allow
  rule the guard denies or asks, or a deny rule it allows, found by running the guard built
  from core + the bundle on `<prefix> x`), `agent-tools` (read-only agents with write tools or
  a permissionMode warn — the permissionMode check moved here from `taxonomy`; a hard-coded
  agent `model:` is an error), `skill-description` (warning: description length 60–1024 after
  expansion with the CI config, a "Use when" trigger, and for workflow skills "NOT for" plus
  `argument-hint`), `fragments-target` (error: fragments for a skill no related bundle
  provides; warning: fragments in a public bundle), `profile-sane` (error: a profile that
  names unknown or private bundles or providers, or does not resolve) and `stability`
  (warning: a `stable` bundle without a test suite per skill/CLI).
  `harness lint --skip RULE` turns one off (e.g. the slower `permissions-vs-guard`).
- Sensor kind `provider-feature` in `[harness]` sensors, `ref = "<provider>:<feature>"`,
  checked against a new optional top-level `features` list in `provider.toml`
  (`claude`: `auto-mode-classifier`, `permission-prompt`; empty elsewhere). Core declares
  `claude:auto-mode-classifier` ("reviews the Auto agent's actions"); the "Guides and
  sensors" tables render it. No migration: `features` and the new sensor kind are optional
  and no existing key changed.
- `harness bootstrap` ends with "≈ N minutes of manual steps remain (harness steps
  --pending)", summed from the pending steps' `minutes`; `tests/smoke/bootstrap.sh` prints
  the elapsed seconds.
- `gitlab` bundle: MR title and `--fill` sensors. `glab mr create` asks on `-f/--fill`
  (generated text may carry a closing keyword or a key-less title), on `--related-issue`, on a
  literal `-t/--title` that does not match the new `gitlab.mr_title_re` (ticket key first) and
  on a `$VAR`/backtick title; an MR created without `-t` is not title-checked. Guard rows
  include `cd … &&`, `sh -c` and multi-clause bypass attempts.
- `github` bundle: PR title and `--fill` sensors. `gh pr create` asks on
  `-f/--fill/--fill-first/--fill-verbose`, on a literal `-t/--title` matching the new
  `github.pr_title_forbid_re` (issue refs belong in the body) and on a `$VAR`/backtick title.

- `stack` bundle (experimental; domain `scm`, guard section `65`): the `stk` CLI keeps stacked
  MRs/PRs mergeable on free tiers with native `glab` / `gh` / `git` commands it prints before
  running them. `stk sync` retargets parts whose blocker merged (or that GitLab CE sent to the
  default branch), rebases each chain in the worktree that has its top checked out with
  `git rebase --update-refs --onto` (lower chain branches checked out in other worktrees are
  detached and re-attached: git 2.43 silently skips them otherwise; a conflict runs
  `git rebase --abort` and leaves every worktree as found), pushes the rebased sub branches
  with `git push --force-with-lease`, refreshes at most one fan-in leaf server-side when the
  merge method needs an up-to-date source, and marks the main MR/PR ready once every part
  merged; it writes only to agent-labelled MRs/PRs. `stk plan` prints the topology, the
  bottom-up merge order for the human and the commands sync would run; `stk status` (incl.
  worktree cleanup lines) and `stk check [--fix]` are reads. There is no merge verb: humans
  merge in the UI. Golden suite over 21 GitLab and GitHub scenarios against stubbed `glab` /
  `gh` and a real-git sandbox, with invariants (lease pushes of sub branches only, never a
  push for an unlabelled MR, worktrees unchanged after a failed cascade, one leaf refresh per
  run).
- `harness lint` rule `guard-messages` (principle 6, skippable): warns on a runtime
  `deny "…"` / `ask "…"` / `defer "…"` message in a public `guard.d/NN-*.sh` that, with shell
  expansions removed, names no alternative. The alternative word list shared with
  `guard-reasons` gains *pass, pipe, check, drop, hand*.
- `gdoc` CLI golden suite (`bundles/gdoc/skills/gdoc/scripts/tests/run.sh`): dispatch, offline
  `auth status`, token refresh and HTTP error mapping (401, 403, 404, 429 retry, 500,
  unreachable), id parsing, every read command, the `api` host allow-list and every write
  under `GDOC_DRY_RUN=1`, each case in a throw-away `HOME` with fake credential files.
  Invariants: no token, client secret or `Bearer` in any output; dry-run writes send only
  GET; every Drive files request carries `supportsAllDrives=true`; no Gmail send endpoint.
- `tests/fakes/http_fixture.py`: a stdlib, CLI-agnostic HTTP driver for python CLIs. It
  loads the CLI by path, routes `urllib.request.urlopen` through a JSON routes file
  (method, URL regex, status, body, once, error), logs `METHOD URL auth=yes|no` and never
  a header value, and exits 3 on an unrouted request. Shared by the gdoc suite and, next,
  the jira suite.
- `harness lint` rules `provider-honesty` and `shim-fixtures` (principle 6, not skippable):
  errors when a provider's `[capabilities]` contradict its `[targets]` (hooks wired with
  `hook_enforced = false`, `hook_enforced` or `ask` without hooks, a `native`/`inlined`/`none`
  capability whose target mode says otherwise) and when a shim lacks `tests/run.sh`, an
  `.out.json` or a fixture for allow, deny, ask, unknown tool or malformed; warnings when
  `features` lists `permission-prompt` with `ask = false` or `docs/providers/<name>.md`
  states another tier than the capabilities give.

### Taxonomy

- New domain value `operations` ("running systems: signals, incidents, reliability
  targets"), first used by `obs`: `schema/bundle.schema.json`, `lib/harness/taxonomy.py`
  `FACETS`, and the `[owns] domains` enum of `schema/repo.schema.json`, so a repository's
  `.harness.toml` can declare `domains = ["operations"]` and every `obs` component yields there
  (except the key-file prelude).

### Deprecated

- `[bundle].tags` in `bundle.toml`: free-form and never read; `harness lint` warns
  "bundle.tags: is deprecated; use taxonomy.domain". Classify the bundle with `[taxonomy]`.

### Fixed
- `core` redact block (`redact_text`, so `k8s redact`, `pod`, `workload` and `helm --values`):
  a mid-line `key: value` / `key=value` whose value starts with an HTTP auth scheme word
  (`Bearer`, `Basic`, `Token`, `Digest`, `Negotiate`, `ApiKey`, `Api-Key`, `Key`, `SSWS`,
  `OAuth`; any case) now masks the scheme word and the token after it as one value. Before,
  only the scheme word was masked and the credential after it leaked
  (`… Authorization: ***REDACTED*** <token>`). Lines that start with the key were already
  fully masked. k8s goldens `redact-text`, `redact-extra-re`, `pod-md` and `pod-json` gain
  one fixture line.
- `bin/harness` runs the checkout it lives in: an inherited `HARNESS_HOME` naming another checkout
  is ignored with a note instead of silently making a worktree's pre-commit hooks and `make`
  targets lint and test the main checkout. `python3 -m harness` and rendered scripts still read
  the variable; `--home DIR` remains the explicit override.
- `harness test` drops git's repository-discovery variables (`GIT_DIR`, `GIT_WORK_TREE`,
  `GIT_INDEX_FILE`, …) from every suite's environment, and the pack unit tests drop them too.
  Git exports them to hooks, so the pre-push hook's unit run pointed the pack fixture
  repositories at the real checkout and failed (in a worktree, with the whole hub staged for
  deletion); the suites now pass from hooks as they do from a shell.

### Changed

- `core`: the redactor is one shared block, `bundles/core/lib/redact.py` (`# >>> redact` …
  `# <<< redact`: `KEY_BODY`, `SECRET_KEY_RE`, `REDACTED`, `redact_obj(obj, extra_re=None)`,
  `redact_text(text, extra_re=None)`), registered in `sync_inline.py` and inlined into the
  `k8s` CLI in place of its own copy (principle 10). Output with no extra regex is
  byte-identical (every k8s golden unchanged). New optional key `k8s.redact_extra_re`
  (`K8S_REDACT_EXTRA_RE`, default `""`): extra token shapes `k8s redact`, `pod`, `workload`
  and `helm --values` mask on top of the built-in list; golden `redact-extra-re`.
- `README.md` rewritten as the product page: what you get, how it works, install, works
  with, principles, governance, organisation values, requirements, documentation. It now
  names ten principles (it said eight) and states every manifest fact through a generated
  region; AGENTS.md, CONTRIBUTING.md and the PR template say to keep it true.
- `bundles/ticket-workflow/tests/run.sh` is back to the shared bundle template; its seven
  `repo-facts` checks moved into the `work-ticket` suite. `[harness]` declares the new suite
  and drops "work-ticket has no own test suite yet"; principle 9 and the roadmap no longer
  list it as a follow-up.
- Docs and the provider-drift workflow match the code again: the roadmap's gap list and
  reserved prefixes drop what shipped (P0 marked shipped), principle 6 and ARCHITECTURE list
  `provider-feature` and the `yields`, `guides-sensors` and `guard-reasons` lint rules, the
  Gemini page no longer claims permission denies become tool exclusions, and the Copilot page
  states that `allow` prints `{"permissionDecision":"allow"}`. The weekly provider-drift
  workflow reads `verified` from `providers/<p>/provider.toml` instead of each README, also
  checks OpenCode (npm `opencode-ai`), and reports a `verified` without a version number as
  unverified instead of drift.
- README reframed as a public platform with three install paths (upstream, org instance,
  bundle file).
- Air-gapped runbook: offline install and upgrade use the release bundle.
- CONTRIBUTING: "Principles first", contributions as the steering loop, guides and sensors in
  the add-a-bundle checklist; PR template asks for the principle(s) served and the pairing
  check.
- `harness upgrade` targets `--to latest` by default: it fetches tags and checks out the
  newest release tag (pre-releases skipped) and never moves backwards (a checkout at or ahead
  of that tag is left alone, exit 0); `--to TAG` pins; `--to BRANCH` checks out and
  fast-forwards a branch; `harness doctor` runs after a successful apply and sets the exit
  status. The upgrade and air-gapped runbooks now describe what the code does.
- CONTRIBUTING "Releases (maintainers)" is the tag-driven procedure (release PR, merge,
  annotated bare SemVer tag `X.Y.Z`, `make release-check`, push the tag, verify).
- Principles 4 and 5: the open question on signing is resolved (build provenance verified
  online, `SHA256SUMS` offline, annotated tags, signed tags optional); principle 5 lists the
  `.run` envelope. Statements unchanged (the bump to 2 above is principle 8).
- Every guard section runs as a function; yielding sections start with
  `repo_owns <id> <domain> && return 0`; `core/guard.d/20-credentials` and `core/permissions`
  never yield, and neither do the token-printing denies, which move into `# never-yields:`
  preludes above the `repo_owns` line (`gh auth token`, `gh auth status --show-token`,
  `gh config get oauth_token` in `github/guard.d/60-github`; `kubectl config view --raw` in
  `k8s/guard.d/25-k8s-rules`, which now also denies the flag when it closes a quoted
  `sh -c "…"` string). Repo-settable regexes are passed to `grep -e`. `work-ticket` preflight reports `repo_declaration`/`repo_owns` and detects any
  repository skill by its (folded) description. Skills carry a "Step 0 — repository-level
  harness" paragraph; agents say a same-named repository agent wins; rules end with the
  repository sentence. Precedence is one rule in one vocabulary across concepts, governance,
  getting started, provider pages, the core rule, the ticket-workflow rule and manual step.
  `guard.env` is described as parsed, never sourced. The example repository skill name is a
  placeholder. `Auto` no longer names a personal path.
- work-ticket's skill description shortened to 1024 characters or fewer (rule
  `skill-description`), keeping its triggers, "NOT for" scope, repo-level hand-over and GitHub
  mode. Coverage notes of core, github, gitlab, k8s and ticket-workflow name the topics whose
  rule or guard section is unpaired by number (`rule-guard-pairing`).
- `gitlab/guard.d/50-gitlab`: `glab mr rebase REF [--skip-ci]` joins the MR label gate of
  `glab mr update|note|close` (agent-labelled MRs allow, human MRs ask, no or `$VAR` ref asks);
  it previously passed ungated. The gitlab rule names the command and the `git pull --rebase`
  refresh afterwards.
- `github/guard.d/60-github`: `gh pr update-branch REF [--rebase]` leaves the team-action asks
  and joins the PR label gate (agent-labelled PRs allow, human and fork PRs ask, no or `$VAR`
  ref asks); `Bash(gh pr update-branch:*)` leaves the github `permissions.toml` `ask` list. The
  github rule names the command. Both commands are what a merge queue runs to bring a stacked
  part up to date with its base.

- Core guard (section 30): a lease push of only `-sub-NN-` branches — `git [-C DIR] push
  --force-with-lease[=…] <remote> <refs…>` as the whole command, every source and destination
  a `-sub-NN-` branch and none matching `WORK_TICKET_BASE_BRANCH_RE` — is now **allowed**
  (stacked parts are agent-owned and lease-protected). `--force`, `-f`, `+ref`, a lease push
  with no ref, a `$VAR` ref, any non-sub ref, a compound command, or a push from inside a sub
  worktree still ask; pushes to a base branch still deny. `git -C DIR push --force` now asks
  too (it used to slip past the force-push pattern).
- `work-ticket` stacked delivery is chain-by-default: the Plan agent lists `paths` per part,
  parts whose paths overlap (incl. shared registry files) must form one chain, fan-in only for
  file-disjoint parts, verified pairwise with `git diff --name-only` before publishing; chains
  may be any depth. §6b uses `stk check`, §6c `stk sync --stack "$BR"` (manual fallback:
  `rebase --update-refs --onto` + lease push, now allowed), Step 7 hands over the merge order
  from `stk plan`; the Stack table shows chain order. `ticket-workflow` recommends `stack`.
- `docs/roadmap.md`: guard band `65` is now `65-stack`; the planned `stack-status.sh` shipped as
  `stk status`; a merge train (`stk run`) is a v2 candidate; `glab stack` stays rejected while
  experimental upstream. Leaf refresh relies on the `glab mr rebase` / `gh pr update-branch`
  label gates of #17 (gitlab and github sections), not part of this bundle.
- Guard messages: every runtime deny/ask message in core (credentials, git), gdoc, github,
  gitlab, jira and k8s now states the alternative its `# rule:` comment names (ask the user,
  push a branch, use the matching subcommand, `--dry-run=server`, `helm template`, ...);
  decisions are unchanged and `docs/reference/hook-policy.md` is byte-identical. New `tr`
  rows in each bundle's `guard.d/tests.sh` pin the wording.

### Stability

- `ticket-workflow` and `gdoc`: `stable` → `beta`; their coverage notes admit a missing test
  suite (work-ticket, the gdoc CLI), which the
  [stability criteria](CONTRIBUTING.md#stability-levels) require for `stable`.

### Docs

- CONTRIBUTING: "Stability levels" (experimental, beta, stable, deprecated), linked from
  concepts "Bundles".
- Principle 6 open questions: declaring inferential sensors that live in provider features is
  resolved by the `provider-feature` sensor kind. Principle 2 open questions: the bootstrap
  smoke's elapsed seconds and bootstrap's remaining-minutes line are the time-to-first-useful-
  session proxies. Doc-only: the normative statements are unchanged, so `principles_version`
  stays 1.

### Migration

- MR/PR title conventions: two new optional config keys. `gitlab.mr_title_re` (default
  `"^[A-Z][A-Z0-9_]*-[0-9]+ "`, a ticket key and a space first; env
  `HARNESS_GITLAB_MR_TITLE_RE`) is the ERE a `glab mr create -t` title must match;
  `github.pr_title_forbid_re` (default `"#[0-9]+"`; env `HARNESS_GITHUB_PR_TITLE_FORBID_RE`)
  is the ERE a `gh pr create -t` title must not match. Guard decisions change from allow to
  ask for `glab mr create --fill|--related-issue`, `gh pr create --fill|--fill-first|--fill-verbose`
  (and `-f`), and for literal titles that break the convention. Setting either key to an empty
  string (`mr_title_re = ""` under `[gitlab]`, `pr_title_forbid_re = ""` under `[github]`)
  disables the title check; the `--fill` asks stay. Run `harness apply` to re-render the guard
  and `guard.env`.
- Component taxonomy: `schema_version` stays `"1"` and every new key is optional, so
  existing manifests keep loading. In every public or private `bundle.toml`, delete
  `tags = [...]` from `[bundle]` and add a `[taxonomy]` section with `domain` (base, scm,
  tracker, delivery, kubernetes, workspace) and `posture` (read-only, local, label-gated);
  add `function` (govern, client, workflow, investigate, plan, execute, review, setup) as a
  default for skills and agents, and `[taxonomy.components]` entries such as
  `"agents/<name>" = { function = "review", posture = "read-only" }` for every skill, agent,
  CLI (`bin/<name>`) and MCP server (`mcp/<server>`) that differs from the bundle. Run
  `harness lint`: its `taxonomy:` messages list the ids (`harness catalog --bundle <b>`) and
  the allowed values. A rule, skill, agent, guard section or permission list missing from
  `[harness]` is reported too; declare it as a guide or sensor. Then run
  `harness docs generate` to refresh the bundle pages and the catalog.
- `harness upgrade` without `--to` now fetches tags and checks out the newest release tag
  instead of `git pull --ff-only` on the current branch. Contributors following `main`:
  `harness upgrade --to main`. Clones made from a `--tag` bundle (detached HEAD) now upgrade
  without extra steps. No config keys changed.
- Repositories: nothing required. Provider `env` overrides keep working and win per key.
  To declare what your repository owns, add `.harness.toml` (`[owns]`, `[overrides]`) and
  run `harness repo`. Overrides settable from `.harness.toml` are exactly
  `WORK_TICKET_ALLOW_DEFAULT_PUSH_RE`, `WORK_TICKET_ALLOW_TRANSITION`,
  `WORK_TICKET_LABELED_DECISION`, `WORK_TICKET_BASE_BRANCH_RE`, `WORK_TICKET_KEY_IN_BRANCH`;
  only `WORK_TICKET_*` names can ever be repo overrides, and client paths,
  `HARNESS_GUARD_ENV`, `HARNESS_CRED_EXTRA_RE` and every `*_PY`, `GUARD_*`, `HARNESS_*` or
  `*CRED*` name are never repo-settable. Keep the file within 16 KiB and 400 lines, write
  each key once and `[owns]` values as arrays. Owning a domain lifts every rule of its
  sections except the never-yields preludes, including the human-only merge asks (`scm`) and
  the Secret-value and kubeconfig-mutation denies (`kubernetes`); see docs/repo-level.md
  "What owning a domain lifts". Agents can no longer write `.harness.toml` without asking:
  a human creates and commits it (`harness repo init` prints a draft).
  Bundle authors (public, org and private): add the `repo_owns` line to each rule-bearing
  guard section, with only shared assignments and, for commands that print a stored
  credential, a `# never-yields:` prelude above it; name honoured overrides `WORK_TICKET_*`
  and give each a `# repo-override:` comment; add the Step 0
  paragraph to skills and the baseline sentence to agents (it uses an em dash:
  `(User-level baseline, principle 8 — a repository-level agent of the same name replaces
  it.)`, so an unquoted YAML description stays a plain scalar); `harness lint` names what is
  missing. Run `harness apply` to re-render the guard.
- Guard section 75: repos that put ticket keys in branch names or commit subjects set
  `WORK_TICKET_KEY_IN_BRANCH = "1"` in `.harness.toml` `[overrides]` (or the provider `env`;
  previously accepted but a no-op); the guard now asks on key-named branches, key-prefixed commit subjects,
  off-convention sub worktree paths and non-squash merges of `-sub-` branches.
- Server-side rebase/update gates: `glab mr rebase REF` changes from pass to the MR label gate
  (agent-labelled MRs allow; human MRs, a missing ref and a `$VAR` ref ask);
  `gh pr update-branch REF` changes from always-ask (team action) to the PR label gate
  (agent-labelled PRs allow; human and fork PRs, a missing ref and a `$VAR` ref ask). Label
  the MR/PR `agent-worked` to keep these promptless. No config keys changed. Run
  `harness apply` to re-render the guard and the permission lists.

- `stack` bundle (opt-in: add `"stack"` to `hub.bundles`, then `harness apply`): four new
  config keys, each overridable per shell by its env name — `stack.label` (`"stack"`,
  `HARNESS_STACK_LABEL`), `stack.push` (`true`, `HARNESS_STACK_PUSH`), `stack.update_method`
  (`"rebase"` | `"merge"`, `HARNESS_STACK_UPDATE_METHOD`), `stack.leaf_refresh` (`"auto"` |
  `"never"`, `HARNESS_STACK_LEAF_REFRESH`). New guard decisions in section 65: a sole
  `stk sync` allows, `stk sync --include-human` asks; permissions allow
  `stk plan|status|check|sync`. Needs git 2.38+ (`rebase --update-refs`).
- Core guard decision change for everyone: `git push --force-with-lease origin <-sub-NN-
  branches…>` typed as the whole command now allows instead of asking (every other
  force-push still asks); nothing to edit.
- `k8s.redact_extra_re` (`K8S_REDACT_EXTRA_RE`): new optional key, default `""` keeps
  today's redaction; nothing to edit. Set it to a regex (e.g. `"(?i)x-internal-token=[^ ]+"`)
  under `[k8s]` and run `harness apply` to mask more token shapes.
- `obs` bundle: new keys only when you enable it (`obs` in `[hub] bundles`): `obs.backends`
  (array of tables), `obs.default`, `obs.hosts_re` (`OBS_HOSTS_RE`), `obs.prod_re`
  (`OBS_PROD_RE`), `obs.log_tail`, `obs.max_bytes`, `obs.redact_extra_re`
  (`OBS_REDACT_EXTRA_RE`); see the manual step `configure-backends`. The guard's `guard.env`
  parser now also accepts `OBS_` keys (core engine and the `env-provides` lint list); nothing
  to edit for existing setups.

## [0.1.0] - 2026-09-30

Initial public release.

### Added

- Engine (`bin/harness`, python stdlib only): `bootstrap`, `init`, `bundles`,
  `config validate|get|set|explain|migrate`, `plan`, `apply`, `sync`, `render`, `doctor`,
  `status --matrix`, `install`, `upgrade`, `uninstall`, `test`, `lint`,
  `docs generate|check`, `steps --pending`, `version`.
- Single gitignored config `local/harness.toml` with layering (bundle defaults → org overlay
  → user → machine → `HARNESS_*` environment) and secret-value rejection.
- Bundles: `core`, `github`, `gitlab`, `jira`, `ticket-workflow`, `k8s`, `gdoc`, each with
  rules, skills, guard sections, permissions, manual steps and doctor checks.
- Providers: Claude Code (enforced), Gemini CLI and Copilot CLI (partial: guard hook, no
  ask prompt), Codex and OpenCode (advisory).
- Guard: one concatenated `guard-bash.sh` per provider home built from per-bundle sections,
  with the full table-driven test suite.
- Platform: CI on Ubuntu and macOS (bash 3.2 syntax gate, python 3.9 and 3.12), render
  determinism and bootstrap smoke tests, private-identifier gate, Markdown link check,
  weekly provider version drift check, issue and PR templates.
- Documentation: getting started, concepts, governance, per-bundle and per-provider pages
  with generated regions, runbooks and reference pages.

[Unreleased]: https://github.com/matt-kh/harness-hub/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/matt-kh/harness-hub/releases/tag/v0.1.0
