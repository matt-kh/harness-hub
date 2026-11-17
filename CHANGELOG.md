# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). Before 1.0, a minor release may
change configuration; such entries carry a **Migration** paragraph, and `harness upgrade`
prints every one between your applied version and the new one.

## [Unreleased]

### Docs

- Governance text for the GitHub Issues close-on-merge exception (part 04 of #80): every
  statement that said closing keywords are denied everywhere now names the one exception (the
  PR to the default branch of a repository whose tracker is GitHub Issues may close its
  `agent-worked` `#N` when `github.close_issue_on_merge` is on) and keeps the rest
  mention-only (Jira keys, commits, PR titles, sub PRs, issue text, API payloads, GitLab, the
  fork flow). [governance §4](docs/governance.md#4-closing-keywords-are-denied) gains the
  exception bullet; [getting started](docs/getting-started.md),
  [repository-level harnesses](docs/repo-level.md) (`tracker`), `SECURITY.md` (closing-keyword
  row), the github and ticket-workflow bundle pages (deny list, troubleshooting row "An issue
  closed itself on merge") follow. `/create-ticket`: non-negotiable 5 and the `render-ticket.py`
  docstring say issue text only mentions `#N`. The `Auto` agent's brief, the
  ticket-workflow rule (`rules/75-ticket-workflow.md`) and the `bootstrap-repo` skill and
  standard (PR template row) state the exception.
- [docs/bundles/supply-chain.md](docs/bundles/supply-chain.md): the hand-written body (the
  `supply` verbs and exit codes, skills and agents, guard section 38, the optional tools, a
  `[supply_chain]` example with documentation values) and Troubleshooting rows for audit
  `unavailable`/`partial` (exit 1) and exit 3 (no detected ecosystem could be audited, and the
  other unsupported inputs), `supply verify` exit 2 (identity, anchoring, `unverifiable`,
  `--github`), `supply ci` false positives and tags flagged by `supply pins`. `SECURITY.md`: a
  threat-model row for unpinned or unverified code, outbound-call rows for `supply audit`,
  `supply verify` and `supply sbom IMAGE`, and `security` among the domains a repository can
  own (every rule of section 38; the `~/.sigstore/` key deny never yields).
  [docs/roadmap.md](docs/roadmap.md): `supply-chain` shipped (experimental; the section keeps
  the design as planned and points to the bundle page), bands `38` and `35` (pipe-to-shell)
  in use, its config keys moved to the shipped list,
  S4b covers `supply-architect`;
  [docs/reference/security.md](docs/reference/security.md) marks it shipped; README names
  the supply chain and the security track.
- [docs/roadmap.md](docs/roadmap.md): the Security track. `supply-chain` (#51) is its first
  bundle and supersedes the planned `toolchain` (guard band `38`; the P2 row becomes a pointer,
  the proposed `code` domain is dropped, `toolchain.*` keys become `supply_chain.*`, env prefix
  `SUPPLY_`); candidates `appsec`, `vuln`, `iam`, `privacy` and `compliance` reserve bands `39`,
  `42`–`44` and `46`; the SAST and SBOM rows of the rejected table say what replaces them.
- [docs/reference/security.md](docs/reference/security.md): the framing for the security bundle
  family. Nine disciplines mapped to domain, function and posture with their architect /
  develop / operate components and what is out of scope for a user-level harness; the rule for
  `security` versus a system's own domain (`secrets` stays `base`, Kubernetes posture review
  stays `kubernetes`); a NIST CSF crosswalk to the `function` facet (no new values); the
  invariants every security bundle keeps; the family with guard bands `38`, `39`, `42`–`44`,
  `46` and config and env prefixes; and author guidance for verification-bypass denies and their
  test rows. Linked from the README reference row and from `SECURITY.md`.
- [docs/bundles/lessons.md](docs/bundles/lessons.md): the lessons loop (signals, review,
  reflect and record, reuse, human promotion), the lifecycle of a record, the per-provider
  matrix (claude and gemini enforce both hooks, copilot the prompt hook only, codex and
  opencode advisory) and troubleshooting. Principle 6 "What it means in this repo" names the
  loop as the routine form of the steering loop, with two "How it is checked" rows (no
  `principles_version` bump); ARCHITECTURE §3 and the roadmap list prefix `15` (rule only).
- [docs/roadmap.md](docs/roadmap.md): planned bundles and extensions by tranche (P0 coverage
  gaps and lint sensors; core git and shell hygiene, `run-checks`, `worktree`, Jira Cloud, the
  `ci` bundle; then the secret-tooling, toolchain, containers, release, cloud, iac, db, hosts
  and digest bundles), the guard prefix bands reserved for them, two proposed taxonomy domains and the
  rejected candidates. Linked from README and ARCHITECTURE §3.
- [docs/roadmap.md](docs/roadmap.md): the SRE track — three new bundles (`obs` for
  observability backends, `incident` for triage, timelines, postmortems and runbooks, `slo`
  for SLOs, burn-rate rules and backup/DR review), the `operations` taxonomy domain, guard
  prefixes 32–34, the pull-forward order `ci` → `iac` → `cloud`, the `k8s` and `core`
  extensions and the slice plan; the observability row is un-deferred as `obs` and the
  ADR/runbook row reshaped into `/draft-adr` and `incident runbook`.
- CONTRIBUTING: "Stability levels" (experimental, beta, stable, deprecated), linked from
  concepts "Bundles".
- Principle 6 open questions: declaring inferential sensors that live in provider features is
  resolved by the `provider-feature` sensor kind. Principle 2 open questions: the bootstrap
  smoke's elapsed seconds and bootstrap's remaining-minutes line are the time-to-first-useful-
  session proxies. Doc-only: the normative statements are unchanged, so `principles_version`
  stays 1.
- Principle 6 "How it is checked" (part 05 of #80): the `issue` gate row describes
  `--base-is-default`. In a PR into the default branch a closing keyword is accepted only
  before the bare `#N` of the body's first `Issue: #N` line; every other closing reference
  still fails. A checks-table refinement, so `principles_version` is unchanged.

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
- `principles_version: 4`: principle 2, **humans decide; an agent acts on an explicit
  main-thread request** — replaces "agents never merge PRs/MRs and never change ticket or issue
  state". Merging, approving, closing, reopening or readying a PR/MR, closing or reopening an
  issue and transitioning a ticket stay human decisions; an agent carries one out only when the
  user explicitly asks for it in the main thread, and the guard confirms every such call (ask).
  Subagents never do it: the guard denies when the hook input identifies a subagent caller and
  falls back to ask on providers that cannot identify one. Closing keywords stay denied.
  Checks: guard sections 50, 60, 70 rows (main ask, subagent deny), landing with the guard
  change; until then the current guard decisions apply. Follow-ups (#67): guard, rules and
  docs, skills.
- `principles_version: 5`: principle 2, "Closing keywords stay denied" gains its one
  exception (part 04 of #80): in a repository whose tracker is GitHub Issues, the one PR to the
  default branch may close its `agent-worked` issue, because the issue then closes only when a
  human merges that PR. A compliant example, a narrower non-compliant one (commits, PR titles,
  sub PRs, issue text, Jira keys) and a "How it is checked" row (section 41 rows, the
  `issue.close_on_merge` goldens) come with it. The summary statement in `PRINCIPLES.md`
  ("humans decide … issue and ticket state") is unchanged. Principle 9's read-back example
  now names the `closingIssuesReferences` read-back.

### Added

- Config key `github.close_issue_on_merge` (boolean, default `true`; env
  `HARNESS_GITHUB_CLOSE_ISSUE_ON_MERGE`), part of #80: in a repository whose tracker is
  GitHub Issues (`.harness.toml` `[repo] tracker`, else the first matching
  `ticket_workflow.trackers` entry, else a github.com origin), the PR to the default branch
  may carry a GitHub
  closing keyword for its worked issue(s), so GitHub closes them when a human merges the PR.
- github bundle: the `gh stack` extension (github/gh-stack) is pinned by one config key,
  `github.stack_extension_version` (default `0.3.0`, env `HARNESS_GITHUB_STACK_EXT_VERSION`;
  part 2 of #86). The human installs it with the new optional manual step `gh-stack-extension`
  (`gh extension install github/gh-stack --pin v0.3.0`); agents never install it. Doctor check
  `gh-stack-extension` (severity warn) passes when no `gh stack` extension is installed or
  github/gh-stack is at the configured version, and warns on another version, a third-party
  `gh stack` or a failing `gh extension list`; it and the step's verify read the non-TTY TSV
  of `gh extension list` (`GH_FORCE_TTY=` unset). `gh extension list` joins the allowed read
  permissions. The work-ticket GitHub preflight reports a read-only `gh_stack` object:
  `installed` (github/gh-stack only), `repo` (the `gh stack` row's repository, so a
  third-party one shows), `version`, `version_raw`, `expected_version`, `version_ok`
  (installed version equals the configured one), `pinned` (`ispinned` from the extension's
  `manifest.yml` under `GH_DATA_DIR` / `XDG_DATA_HOME` / `~/.local/share/gh`; null when
  unreadable), `repo_enabled` and `stacks` (`[{number, base, open, pull_requests}]`) from
  `gh api --paginate repos/OWNER/REPO/stacks?per_page=100` (404 → `repo_enabled: false`; any
  other failure or response shape → `null`). New preflight goldens cover another version,
  another extension only, none, a third-party `gh stack`, a non-semver version, unpinned and
  unreadable manifests, a 404, another response shape and the version from the environment;
  the github bundle suite runs the doctor check and the step's verify against a stubbed
  `gh extension list` and checks the key's pattern.
- work-ticket (GitHub, part 4 of #86): stacked delivery links each linear chain of ≥ 2 sub PRs
  rooted at the ticket branch into a native GitHub stack with
  `GH_STACK_NO_UPDATE_NOTIFIER=1 gh stack link --base <ticket branch> <PR numbers bottom to top>`
  after the sub PR creates and before the second pass, when preflight `gh_stack` reports the
  extension installed at the expected version and stacks enabled on the repository, and reads
  it back from the Stacks API. Fan-in leaves, side branches and the main PR stay unlinked;
  numbers only, never branch names or `--open`. Without the extension, with another version or
  without repository stacks, delivery is unchanged and the main PR's Agent notes say why and
  how to enable it; the agent never installs the extension. The `## Stack` table gains a
  GitHub-only `Stack` column, linked sub PR headers name their stack, and §6c states that
  `stk sync` keeps the stack consistent, `gh stack sync` is not used and `gh stack merge` runs
  only on the user's explicit request (references `github.md`, `mr-description.md`,
  `decomposition.md`, SKILL.md Steps 6b/6c).
- Guard engine: reads the hook input's `agent_id` (set by Claude Code on calls from a subagent
  or in-process teammate; `agent_type` is never read, since a `--agent` main thread carries it
  too) into `IN_SUBAGENT`, and offers `human_decision` / `human_decision_defer` for sections:
  deny inside a subagent (hand the command back to the main thread), else ask / defer. Guard
  rows gain the `T_AGENT`, `T_AGENT_NULL` and `T_AGENT_TYPE` knobs through one input builder.
  No guard decision changes yet; sections adopt the helpers in later parts of #67.
- Provider capability `subagent_identity` (`[capabilities]`, optional boolean, default false):
  the hook input tells a subagent call from a main-thread call, so the guard denies human
  decisions in a subagent. Set on claude only. The capability matrix (`harness status
  --matrix`, README, [capability matrix](docs/reference/capability-matrix.md)) gains the row
  "subagent deny (merge, state)": `native` on claude, `mapped (ask_as)` on copilot and gemini
  (every caller gets `ask_as`, default deny), `-` on codex and opencode (advisory); `ask only`
  names a hook that can ask but cannot identify the caller. `harness lint` `provider-honesty`
  errors on `subagent_identity = true` without an enforced guard hook. Copilot and gemini shim
  fixtures `ask-agent-id` pin that `agent_id` never reaches the neutral envelope. Part of #67.
- `core` guard section `35-shell-hygiene` and rule `rules/35-shell-hygiene.md` (#51, the last
  part; band `35` now in use, pipe-to-shell only): a download (`curl`, `wget`, `fetch`) piped
  into an interpreter that reads its program from stdin (`| sh`, `| sudo bash`, `| python3 -`,
  `| bash -s`, `| perl`, `| node`, `| ruby`; not with `-c`/`-m`/`-e`/`-n`/`-p` or a script
  operand), `sh|bash|source|. <(curl …)`, `sh|bash -c "$(curl …)"` and `eval "$(curl …)"`
  **ask** (deferred, so a later deny still wins): download to a file, check its sha256, read
  it, then run it instead. A small quote-aware matcher reads the raw command: quoted text in
  `echo`, `printf`, `grep` or a commit message is not a command, while `sh -c '…'`,
  `cd … &&`, `/usr/bin/curl`, `env X=1 curl`, subshells and quoted command words still are,
  and so are `{ …; } | sh`, `curl … | (sh)`, `if`/`for`/`while`/`case` bodies, a pipeline
  continued after a trailing `|`, `tee >(sh)`, the wrappers `timeout`, `busybox`, `exec -a`,
  `sudo -s|-i`, `su`, `xargs … sh -c`, `bash -euo pipefail`, `bash -o pipefail -c "$(curl …)"`,
  `python3 -c|perl -e|node -e|ruby -e "$(curl …)"`, `source /dev/stdin <<< "$(curl …)"`, an
  interpreter's heredoc expanding `$(curl …)`, `ash`/`mksh`/`fish`/`$SHELL` and HTTPie / `xh`
  as downloaders. `| tar xz`, `| jq .`, `| sha256sum`, `| python3 -c '…'`, `| bash -n`,
  `| bash -s < file`, `| xargs sh` and `-o file && sh file` pass. The matcher runs in the C
  locale in linear time and on any POSIX awk (the core tests rerun its rows under mawk,
  busybox awk or BSD awk when installed); what it does not see (other downloaders,
  interpreters and wrappers, remote and container shells, a download kept in a variable) is
  listed in the bundle's coverage note. The rest of band `35` (`sudo`/`doas`, recursive
  removal, `chmod -R 777`) stays planned.
- `supply-chain` bundle (#51; experimental; domain `security`, posture `local`), the first
  bundle of the security track: pin what you add, install inside the project, never switch
  verification off. Guard section 38 with its rule and permission list, the read-only `supply`
  CLI and client skill, pinned optional `osv-scanner`, `cosign` and `syft`, the workflow skills
  `/pin-deps` and `/audit-deps` and three read-only agents (the bullets below); docs page
  [supply-chain](docs/bundles/supply-chain.md). Pipe-to-shell as a command is core band `35`
  (below).
- `supply-chain` guard: rule `rules/38-supply-chain.md`, guard section `38-supply-chain` and a
  permission list.
  The section lexes the raw command once (newlines, subshells, `{ }`, `if/for` bodies, `$( )`,
  backticks and `sh -c`/`eval` strings are separate commands; quotes and backslashes removed;
  heredoc bodies are data unless a shell reads them) and exempts commands that only print or
  search text (`echo`, `grep`, `rg`, `sed`, `cat`, `git log|commit|…`) unless the line runs
  text as code. Denies switching verification off: `pip|uv --trusted-host` (and unique
  prefixes) or an `http://` index (flags, `pip config set`, `PIP_*`/`UV_*` variables),
  `uv --allow-insecure-host`, npm/pnpm/yarn `strict-ssl false` or an `http://` registry
  (`config set`, `set`, `--registry`, `--no-strict-ssl`, yarn `enableStrictSsl`,
  `npmRegistryServer`, `unsafeHttpWhitelist`, `YARN_ENABLE_STRICT_SSL`),
  `NODE_TLS_REJECT_UNAUTHORIZED=0`, git `-c|--config http.sslVerify=false|no|off|0|<empty>`,
  `git config http.sslVerify false`, `--config-env`, `GIT_CONFIG_KEY_<n>`, `GIT_SSL_NO_VERIFY`,
  `GOINSECURE=<value>`, `GOFLAGS=-insecure`, `go get -insecure`, `GOSUMDB=off`, `go env -w
  GONOSUMDB|GONOSUMCHECK=<value>`, `cosign verify* --insecure-*|--allow-*-registry|
  --private-infrastructure` (any true value), and a reader taking `cosign.key` or
  `.sigstore/**/*.key` as a file operand. The `~/.sigstore/**/*.key` read deny is a
  `# never-yields:` prelude, so owning `security` does not lift it (a repository's own
  `cosign.key` still yields with the domain); unreleased, so no migration. Asks (deferred, so a later deny still wins) on
  `pip install` outside a venv (markers: the hook's environment with `CONDA_PREFIX` only outside
  conda base, an earlier `activate` clause, a runner, a venv's `…/bin/pip` as the command word,
  `--target|--prefix` inside the checkout; a `VIRTUAL_ENV=` assignment is no marker), with
  `--user`, `--break-system-packages` or `sudo`, `uv pip install --system` and
  `UV_SYSTEM_PYTHON=1`; `npm|pnpm -g`, `yarn global add`, `cargo install` without `--locked
  --version`, `go install …@latest|@main|@master|@HEAD`; unpinned git and URL dependencies (pip,
  npm/pnpm/yarn incl. every tarball URL, cargo); a one-shot `GONOSUMDB=`/`GONOSUMCHECK=`;
  `cosign sign|attest|attach|upload|copy|clean|generate-key-pair|import-key-pair`; and `curl -k`
  or `wget --no-check-certificate` writing a file or piping into `tar|unzip|tee|dd|cpio`.
  `pipx install`, `uv tool install`, `go install m@v1.2.3` and `cargo install X --locked
  --version V` pass. `supply_chain.allow_global_re` (anchor it) must match every word after the
  first install verb. Keys `supply_chain.allow_global_re`
  (`SUPPLY_ALLOW_GLOBAL_RE`), `supply_chain.venv_markers` (`SUPPLY_VENV_MARKERS`),
  `supply_chain.registries_re`, `supply_chain.identities`, `supply_chain.redact_extra_re`,
  `supply_chain.osv_offline_db`, `supply_chain.pin_actions`, `supply_chain.max_bytes` (the last
  six for the `supply` CLI). Guard rows incl. bypasses, ordering against later denies, the
  `security` yield and `guard.env`.
  The guard's `guard.env` parser and the `env-provides` lint accept the `SUPPLY_` prefix; band
  `38` is listed in ARCHITECTURE §3.
- `supply-chain` CLI: the read-only `supply` CLI (stdlib python 3.9, inlining
  the core `harness_config` and `redact` blocks) and its client skill with six reference
  rubrics. Verbs: `detect` (ecosystems, manifests, lockfiles; never runs a tool), `pins`
  (unpinned actions, images, dependencies and unverified downloads, `GHA*`, `DKR*`, `PIP*`,
  `NPM*`, `GO*`, `CGO*`, `SH001`/`SH002`, `CI006`/`CI008`/`CI009`, `REG001`; findings carry the
  exact `ref` token) with `pins --apply FILE` (exact-token rewrites, all-or-nothing, byte-exact,
  then a re-scan; only a finding's `ref`, as a whole token, replaced by a digest or sha pin of
  the same name; no symlinks or `.git`; staged writes rolled back on a failure part-way),
  `ci FILE...` (GitHub Actions and GitLab CI hardening `CI000`–`CI009`; shell lines are lexed,
  so quoted strings, `| python -c` and case patterns are not `SH001`/`SH002`; exit 3 when no
  file could be scanned), `audit` (osv-scanner, else `npm audit`, `pip-audit` on fully hashed
  requirements only, `cargo-audit` called directly from an empty directory, `govulncheck` with
  `GOTOOLCHAIN=local`: never code from the checkout; "unavailable" is never "clean": `AUD001`
  (warn, so exit 1) for every ecosystem or file left unaudited, also one osv-scanner read
  nothing for, even when the rest audited clean; exit 3 when none could be audited; `--offline`
  runs osv-scanner with `--offline-vulnerabilities --no-resolve`: no network, neither for the
  vulnerability lookup nor for resolving a manifest's transitive dependencies),
  `sbom DIR|IMAGE` (syft, never the docker daemon; `--out` written exclusively with token-shape
  redaction only) and `sbom lint FILE` (`SBM001`–`SBM009`), `verify` (cosign keyless, key, attestation and blob-with-bundle;
  `gh attestation verify`; the subject after `--`; anchored identity regexps; never an
  `--insecure-*` flag) and `redact`. Unreadable directories are `SUP002`. Exit 0 clean, 1
  findings, 2 access/tool/config error (never a traceback), 3 unsupported; banner
  `supply: dir= ecosystems= tools=` on stderr; sorted JSON envelope without timestamps. New keys
  `supply_chain.exclude_re` (`SUPPLY_EXCLUDE_RE`) and `supply_chain.timeout`
  (`SUPPLY_TIMEOUT`); the CLI also reads `SUPPLY_REGISTRIES_RE`, `SUPPLY_REDACT_EXTRA_RE`,
  `SUPPLY_OSV_OFFLINE_DB` and `SUPPLY_MAX_BYTES` from the environment. Doctor checks
  `supply-cli` and `supply-detect`. A golden suite over fixture checkouts with stub tools
  (`SUPPLY_PATH`): every verb in JSON and Markdown, the unavailable and fallback-only paths,
  byte-exact `--apply` (CRLF and comments kept), redaction, stub-log invariants (verify only,
  no `fix`, no docker), one rubric row per rule id, and two identical runs.
- `supply-chain` tools: pinned, sha256-verified, **optional** lock files
  `tools/osv-scanner.lock.json` (2.7.0, bare binaries), `tools/cosign.lock.json` (3.1.4, bare
  binaries) and `tools/syft.lock.json` (1.55.0, tar.gz) for linux/darwin × amd64/arm64, each
  digest taken from the upstream checksum file (`osv-scanner_SHA256SUMS`,
  `cosign_checksums.txt`, `syft_1.55.0_checksums.txt`). New lock key `"optional": true`.
  `harness pack --tools-optional` ships optional locks with `--tools`. The manifest declares
  `osv-scanner` ≥ 2.7.0, `cosign` ≥ 3.1.4 (`cosign version`), `syft` ≥ 1.55.0 (the versions the
  argv and output parsing were checked against; older releases lack what supply relies on) and
  `gh` ≥ 2.49 as optional with `install`, and `npm`, `pip-audit`, `cargo-audit`, `govulncheck` as
  optional fallbacks (doctor WARNs when one is absent: no manifest field marks a binary
  fallback-only); manual steps `install-supply-tools` and `configure-identities`; doctor check
  `supply-config` (warn: every `identity_re` anchored as `supply verify` requires, the same rule
  as the CLI). The `supply` argv was checked
  against the real binaries: `audit` passes `--all-packages` (without it osv-scanner 2.7.0
  lists only vulnerable packages, so clean lockfiles counted 0), names osv-scanner's error line
  instead of its first progress line and, offline without a database, the human's download
  command; `verify` no longer passes cosign's deprecated `--offline`: offline is a file with `--bundle`
  and `--trusted-root`, or `--github` with both; `verify IMAGE --offline` with cosign is refused
  (exit 3) and `--bundle` with an image and cosign too (exit 1; cosign 3.1.4
  `verify`/`verify-attestation` have no such flag); cosign and syft failures name their `Error:`
  line; `sbom` runs syft with
  `SYFT_CHECK_FOR_APP_UPDATE=false`, and the summary and package counts leave out syft's SPDX
  document root and, for syft's own output only, CycloneDX `"type": "file"` components (absolute
  manifest paths); `sbom lint` accepts CycloneDX 1.7 (syft 1.55.0's default). `[uninstall]` also keeps
  `~/.cache/osv-scalibr/**`, where osv-scanner 2.7.0 keeps its offline databases.
- `supply-chain` skills and agents: workflow skills `/pin-deps` (`supply pins` findings →
  values resolved read-only with `git ls-remote`, `gh api` or `glab api` GETs and an installed
  `crane`/`docker buildx imagetools` → `supply pins --apply` → `supply pins` again; tags keep
  today's target, branches and `latest` are suggestions the user accepts, a `CI008` include
  with no `ref:` goes to the human; never guesses a sha, digest or checksum) and `/audit-deps`
  (`supply audit` → in-major upgrades to the lowest fixed release that is not a pre-release,
  never for a `0.0.x` package, with `UV_PYTHON_DOWNLOADS=never uv lock --upgrade-package
  NAME==X.Y.Z --no-build`, `npm install NAME@SPEC --package-lock-only --ignore-scripts` keeping
  the manifest's range prefix, `pnpm update --lockfile-only --ignore-pnpmfile --ignore-scripts`
  with package-manager switching off, `cargo update --precise` unless a `rust-toolchain` file
  or a `.cargo/config*` program setting is present, `GOTOOLCHAIN=local go get`, poetry always a
  manual change → `supply audit` again and each locked version checked against the `--fix`
  limit, an overshoot reverted; majors, no-fix, manual changes and `unavailable`/`offline`/
  `error` auditors go to the human). Neither
  runs the checkout's code or tests (the test command is named for the human), downloads a
  toolchain or interpreter, commits or pushes; both keep intermediate files in a
  `mktemp -d` scratch directory used as `"${SCRATCH:?}"`. `supply pins --apply` now keeps the
  tag of an action pinned from a tag as its comment, in the same atomic write (` # TAG`
  appended, or `# TAG - <old comment>`; `data.applied[].comment`), so no hand edit remains.
  `supply audit --offline` through osv-scanner reports an audited ecosystem as status `ok` with
  `"offline": true` (it was `offline`, which now only means a fallback auditor that needs the
  network did not run). Read-only agents `supply-architect` (plan model, design and decision record),
  `supply-auditor` (review; Critical / Warnings / Suggestions / Not verified with severities
  from the rubrics; declared as the bundle's review-agent sensor) and `supply-triage`
  (investigate one finding, stop after three unresolved hypotheses). Taxonomy overrides
  (`workflow`; `plan`, `review`, `investigate` at `read-only`) and their guides and sensors.
- Bundle `repo-bootstrap` (experimental; domain `scm`, posture `label-gated`, function `setup`).
  `/bootstrap-repo` and the `repoboot` CLI (questions, answer, plan, render, apply, check)
  bootstrap git repositories to one standard — locally and on GitHub or GitLab — and retrofit
  existing ones. A standard intake (`questions.toml`) asks only what is still open, in at most
  two rounds; answers live in the repository's `.repo-standard.toml`. The bundled `baseline`
  pack writes hygiene files, README, MR/PR and issue templates (ticket mentions, never closing
  keywords), CODEOWNERS, license, pre-commit config and a CI lint job; architecture-specific
  packs come from `repo_bootstrap.pack_dirs` (files, slot fragments, their own questions). `apply`
  creates the repository, makes the first push only after `git ls-remote` shows an empty remote,
  and sets merge settings, default-branch protection (GitHub ruleset, GitLab protected branch)
  and the `agent-*` labels; it never writes `.harness.toml` (the plan carries the draft). Guard
  section `67-repo-bootstrap` asks on `repoboot apply`; the other verbs are allowed by
  `permissions.toml`. Golden suite against stubbed gh/glab and a real-git sandbox.

  **Migration:** new config keys `repo_bootstrap.pack_dirs`, `.default_visibility`,
  `.default_merge_method`, `.required_approvals`, `.default_license`, `.github_owner`,
  `.gitlab_namespace` and `.gitlab_remove_source_branch`, all with defaults; nothing changes
  until the bundle is added to `hub.bundles`.

- Neutral hook events beyond the guard (ARCHITECTURE §3–§5; roadmap "Provider hooks beyond
  `PreToolUse`"). Bundles register hook scripts with `[[provides.hooks]]` (`event` = `prompt`
  or `stop`, with `session-start` and `session-end` reserved; `script` = `hooks/<name>.sh`;
  `when` = a dotted config key or a list of them; `timeout` in seconds, default 5); providers
  map them with `[targets.hooks.events.<event>]` (`name`, `entry`, optional `matcher`, `shim`,
  `timeout_unit` `s`|`ms`, `note`). The neutral envelope is the Claude Code payload
  (`session_id`, `cwd`, `prompt` / `stop_hook_active`), the neutral output nothing or one JSON
  object with `systemMessage` and/or `hookSpecificOutput.additionalContext`; these hooks never
  block. Every event runs behind a shim that builds the envelope and allow-lists the output
  (`systemMessage`, `additionalContext` where supported; exactly one JSON object or nothing;
  never `decision`, `continue` or `reason`): claude registers `UserPromptSubmit` and `Stop`
  behind `shim-event.sh`; gemini `BeforeAgent` and `AfterAgent` behind `shim-prompt.sh` /
  `shim-stop.sh` (timeouts in ms; `AfterAgent` passes `systemMessage` only); copilot
  `userPromptSubmitted` and `sessionEnd` in `harness.json` behind its own shims (output
  discarded: no message channel; verify on install). Event commands are
  `HARNESS_PROVIDER=<p> HARNESS_HOOK=<script> bash <shim>`; every rendered hook path,
  the guard's included, is shell-quoted (unchanged for paths without special characters). Providers without the
  event get a plan note; an unknown event is a render error. With no event hook active every
  rendered file is byte-identical to before (the copilot register file included).
  `harness status --matrix` and the README matrix gain the row "extra hook events (prompt,
  stop)"; provider pages list their events. No bundle ships a hook yet.
- Shim fixtures for the event shims under `providers/<p>/tests/{prompt,stop}/` (claude, gemini,
  copilot), with `NAME.envelope.json` asserting the envelope the hook receives and cases for a
  blocking `decision` (filtered), command substitution in the prompt (data, never run), a
  missing hook and a failing hook. `providers/_shared/run-shim-tests.sh` gains a stub
  `HARNESS_HOOK` and per-case work directories; `providers/_shared/run-provider-tests.sh`
  runs every fixture set of a provider (`guard:<shim>`, `<event>:<shim>`) and each
  `tests/run.sh` execs it.
- Opt-in guard journal (`core`; [hook policy "Journal"](docs/reference/hook-policy.md#journal)).
  With `lessons.journal = true` every ask and deny a guard section decides (not the fail-closed
  denies for malformed input or a missing jq) appends one line of seven tab-separated
  fields — `ts provider session kind site guard_id repo` — to
  `~/.local/state/harness/journal/<YYYY-MM-DD>.log` and points
  `~/.local/state/harness/retro/current` at the session. `kind` is `guard-ask` or `guard-deny`
  (`correction` and `dissatisfaction` are reserved for the lessons prompt hook); `site` is
  `<guard_section_*>:<line in the section file>`, and a flushed deferred ask is credited to the
  rule that deferred it; `session` is the hook input's `session_id` when it matches
  `[A-Za-z0-9._-]{1,64}` (ASCII), else `-`; `repo` is the main checkout's directory name (a
  linked worktree resolves to it, so `<repo>_<branch>` names never appear). The command, its
  words, paths and reasons are never written; journal failures never change a decision (HOME
  unset or a relative state dir writes nothing, never under the repository); allows add no
  process. The engine reads
  `session_id` in the same jq call as the command. `guard.env` gains `HARNESS_GUARD_ID` (12 hex
  characters of the rendered guard's sha256) and the four `HARNESS_LESSONS_*` names. The
  gemini and copilot guard shims pass `session_id` (copilot: `session_id // sessionId`) into the
  neutral envelope when present; the shared shim runner's stub guard now records its envelope,
  so guard fixtures may carry `NAME.envelope.json`. Guard test helper `tj on|off|unset EXPECTED
  'cmd'` (all seven fields, session sanitising, no word longer than three characters of the
  command or the cwd in the file) with rows in `bundles/core/guard.d/tests.sh`. `harness repo` now decodes `'\''` in
  single-quoted `guard.env` values the way the engine does.
- `harness lessons` (`lib/harness/lessons.py`; [lessons reference](docs/reference/lessons.md)):
  a private, per-workstation library of evidence-backed lessons under
  `~/.local/state/harness/lessons/` (never inside a git checkout; the CLI refuses one) and the
  only parser and writer of its records (banner, fixed-order front matter validated by a
  schema, six sections; records round-trip byte for byte). Subcommands `list`, `show`, `new`
  (refuses missing evidence, unknown domains, `invariant` outside `base`, bad refs, token
  shapes, URL userinfo, over-cap text, edits outside `bundles/`), `note` (used / helped /
  recurred; only journal-backed recurrences count toward `recurring`), `confirm`, `retire`,
  `review` (the retro gate over one session's journal lines: rc 0 due, 1 not due, 3 no
  journal, session or lines, 4 error; `--explain`), `stats` (asks, denies and corrections per session
  before and after each lesson), `validate` (applies a candidate edit to a `git archive HEAD`
  copy of the hub and runs lint, the guard and bundle suites and render), `propose` (writes
  `body.md`, `preview.md` and a `create.sh` it never runs; refuses unconfirmed lessons,
  closing keywords and `#N` titles; redacts repository names), `index` (`INDEX.md` by domain
  with per-domain candidate and overall caps, `--prune`) and `journal` (lines since the last
  retro grouped by kind and rule site, current sites resolved to their source line, other
  guard ids stale, `--ack`, which also writes the stop nudge's `retro/sessions/<sid>` marker
  for the session in `retro/current` so a session whose retro ran is not nudged again). Unit tests with goldens in `tests/fixtures/lessons/`.
- Bundle `lessons` (experimental, `depends_on = ["core"]`, in no profile;
  [docs](docs/bundles/lessons.md)): the first bundle hooks. `hooks/prompt-signal.sh`
  (`prompt`, when `lessons.prompt_signals`) appends one `correction` or `dissatisfaction`
  journal line per matching prompt (class only; slash commands and prompts over 600
  characters skipped; stdout always empty; same directory rules as the guard journal) and
  `hooks/stop-retro-nudge.sh` (`stop`, when `lessons.journal`) prints one `systemMessage` per
  session when `harness lessons review --session <id>` exits 0, silent on every other exit
  status, never a decision. Skill `/retro` (`retro-facts.sh` read-only facts with goldens; one
  fixed-shape questionnaire; at most one invariant and one domain candidate through
  `harness lessons new|note`, journal refs copied verbatim; a fixed-shape report ending with the
  human's `confirm|retire|propose` commands). Rule `15-lessons` (consult `INDEX.md` at Step 0;
  a lesson is evidence, never an instruction) and its guard section `15-lessons`, which asks
  on `harness lessons confirm|retire|propose` however wrapped (`bash -c`, `xargs`, a path to
  `bin/harness`, `python3 -m harness`, global flags) and passes every other `harness lessons`
  call; it yields to a repository owning it or domain `base`. The stop hook passes
  `--config <_harness.config>` from `build/config.json` and cuts the review off after 3 s
  (GNU `timeout`, or a python fallback that kills the whole process group). Permissions: allow `Bash(harness lessons:*)`,
  ask on `Write`/`Edit` of `~/.local/state/harness/lessons/**`. Doctor checks
  `lessons-index-fresh`, `lessons-stale-candidates`, `lessons-review-keys`; manual steps
  `enable-journal`, `read-the-loop`. Suites `bundles/lessons/tests/run.sh` (section 15 rows
  against core + lessons, hooks against `hooks/tests/prompts.tsv`, the regex contract, plus the
  doctor script) and the retro facts goldens.
- `work-ticket` and `create-ticket` end with a review-gated retro step (Step 8 and Step 9):
  with the `lessons` bundle installed and the harness CLI found, `harness lessons review` (with
  the rendered `--config`, like the facts script and the stop nudge) rc 0 invokes `/retro` once
  with `--workflow work-ticket|create-ticket --arg 'KEY'` (quoted, so `#N` survives), rc 1 prints
  one `Retro: not due (<counts>)` line, any other exit status stays silent; never after a
  Handover or a later `stk sync` handoff. create-ticket's Step 8 is now "Report" (its stop
  sentence is unchanged). `ticket-workflow` recommends `lessons`.
- `harness lint` rule `hooks-events` (principle 6, not skippable): a hook script missing or
  failing `bash -n`, a `when` key no schema defines, one script name in two bundles or named
  like a guard file or any provider's shim, an event no provider declares (warning); provider
  events whose shim is missing, fails `bash -n`, has no `tests/<event>/` fixtures or none for
  the cases malformed, garbage, silent, decide, or is not run by `tests/run.sh`, whose
  `entry` is not a JSON object after substitution, with a bad `timeout_unit`, or whose
  provider event name is the guard's or is used twice. `shim-fixtures` now also requires `tests/run.sh` for a provider with only event shims.
- Per-guide pairing (principle 6): `[harness]` guides take an optional `checks` list naming the
  sensors that check them (`ref` values of the same bundle's `sensors`; schema only, no
  `schema_version` bump). Lint rule `guide-checks` (skippable) errors on a ref no sensor
  declares and warns on a public guide without `checks` unless `coverage_note` names its topic.
  `Bundle.sensor_refs()` and `Bundle.unpaired_guides()`; `pairing()` is unchanged. Each bundle
  page's "Guides and sensors" table gains a **pairs with** column and a "guides with a declared
  check: n of m" line; `docs/reference/harness-coverage.md` gains an **unpaired guides** column.
  All nine public bundles declare `checks` on every guide and add the `permissions-vs-guard`
  lint sensor where they ship a permission list, `agent-tools` where they ship agents (core,
  k8s, obs).
- Declared tracker per repository. `.harness.toml` `[repo]` gains `tracker`
  (`github-issues` | `jira`) and `project` (Jira only; `schema/repo.schema.json`, shown by
  `harness repo`, offered by `harness repo init`). New config key `ticket_workflow.trackers`
  (`ticket-workflow` bundle, default `[]`): `[[ticket_workflow.trackers]]` entries with
  `match` (an ERE on `<host>/<path>` of `origin`), `tracker` and optional `project`; first match
  wins. Precedence: repository declaration → config → host (github.com → GitHub Issues, GitLab
  → Jira).
- `ticket-workflow`: every facts script (`github-preflight.sh`, `gitlab-preflight.sh`,
  `issue-facts.sh`, `jira-facts.sh`, `create-facts.sh`) reports a `tracker` object —
  `tracker`, `tracker_source` (`repo` | `config` | `host` | null), `project`, `remote_id` —
  from `lib/repo-facts.sh` `rf_remote_id` / `rf_tracker` (inlined into `create-facts.sh`, the
  create-ticket suite checks the copies match). `create-facts.sh --repo` prints only the cwd's
  tracker and declaration. Goldens: the `rf-tracker` table (remote shapes × declaration
  sources) and tracker cases in both suites.
- `ticket-workflow`: doctor check `ticket-workflow-trackers` (offline): every `match` compiles
  under `grep -E`, every `tracker` is known, `project` only with `jira`; a failure names the
  entry index and the fix.
- `tools/gate/companions.sh` check `issue` (`--only issue`): with `--markers-file` (the PR body
  in CI) the body must name its GitHub issue as `#N`, `owner/repo#N` or an issues URL outside
  code and comments, and never after a closing keyword; `no-issue: <reason>` waives it; without a
  body it is skipped. Self-tests in `tools/gate/tests/companions-selftest.sh`.
- harness-hub develops from GitHub Issues: its own `.harness.toml` declares
  `[repo] tracker = "github-issues"`; AGENTS.md ("Issues are the source of truth"),
  CONTRIBUTING.md and the PR template (`Issue: #N` first) say so.
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
- `jira` CLI golden suite (`bundles/jira/skills/jira/scripts/tests/run.sh`, after the
  existing configuration checks): every read command (`whoami`, `get` with configured
  friendly fields and a parsed sprint, `links`, `search`, `fields` for a project and an issue,
  `api`, `versions`, `transitions`, `attachments`, `download`, `sprints`), HTTP error mapping
  (401, 403, 404, 500, unreachable, missing token) and every governance write under
  `JIRA_DRY_RUN=1` (label add/remove, transition, labelled create, create with a link, link,
  comment, `set` by friendly name), plus `upload`, which bypasses the dry run. Runs through
  `tests/fakes/http_fixture.py` with an empty `HOME`. Invariants: the token and `Bearer` never
  in output, every request authenticated and aimed at the configured base URL, dry-run writes
  send only GET requests.
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

- New domain value `security` ("security posture of code, dependencies, artefacts and
  credentials: supply chain, appsec, vulnerabilities"): `schema/bundle.schema.json`,
  `lib/harness/taxonomy.py` `FACETS`, the `[owns] domains` enum of `schema/repo.schema.json` and
  the `--domain` choices of `harness catalog` and `harness lessons`. It lands one PR ahead of its
  first user, the `supply-chain` bundle (#51), as the roadmap's Security track names it; the
  vocabulary row reads `0` until that bundle ships. "Adding a value" in
  [taxonomy](docs/reference/taxonomy.md) now names `schema/repo.schema.json`, the hand-written
  domain lists in `ARCHITECTURE.md`, `docs/concepts.md` and `docs/repo-level.md`, and the
  one-PR-ahead allowance; a unit test (`test_handwritten_domain_lists`) keeps those lists equal
  to `FACETS`.
- New component kind `hook` (hook scripts of `[[provides.hooks]]`): id `<bundle>/hooks/<name>`,
  function fixed to `govern`, no posture, yields `n/a`; listed by `harness catalog` and
  `docs/catalog.md` ("Hook scripts"), and `[taxonomy.components]` accepts `hooks/<name>` keys.
- New domain value `operations` ("running systems: signals, incidents, reliability
  targets"), first used by `obs`: `schema/bundle.schema.json`, `lib/harness/taxonomy.py`
  `FACETS`, and the `[owns] domains` enum of `schema/repo.schema.json`, so a repository's
  `.harness.toml` can declare `domains = ["operations"]` and every `obs` component yields there
  (except the key-file prelude).

### Deprecated

- `[bundle].tags` in `bundle.toml`: free-form and never read; `harness lint` warns
  "bundle.tags: is deprecated; use taxonomy.domain". Classify the bundle with `[taxonomy]`.

### Fixed
- Closing-keyword denies (`gitlab` section 40, `github` section 41) now also match the forms
  they missed: an attached `-Ro/r` before the noun or the verb and `gh pr new` (gh); a repo flag
  before the noun or the verb, attached or not (`glab -R g/p mr update`, `glab mr -Rg/p update`,
  `glab -R g/p api`) and `glab mr new` (glab); a repo flag given twice; and a quoted or `$VAR`
  noun or verb (`gh "pr" edit`, `glab $m update`). Since #67 sections 50 and 60 denied the alias
  and attached-flag forms, and asked on quoted or `$VAR` words, but they yield when a repository
  owns `scm`, so a repository that owns `scm` and not `tracker` lost the closing-keyword deny for
  these spellings (#76). The duplicate checks in 50 and 60 are removed; section 60 uses 41's
  repo-flag pattern, which already matched the attached forms there.
- `repo-bootstrap`: `scripts/repoboot.py` is now committed executable. Before, the
  `~/.local/bin/repoboot` link failed with "Permission denied" and `harness doctor` reported
  `link-repoboot` and `repo-bootstrap/repoboot-cli` as FAIL (the golden suite calls the script
  through `python3`, so it never noticed). Run `harness apply` after updating. `harness lint`
  (rule `manifest`) now errors on a `[provides] bin` target that is missing or not executable,
  with the `git update-index --chmod=+x` command to fix it.
- Model names per provider: agent and skill front matter no longer carries the Claude aliases
  of `core.model_policy` (`fable`, `opus`) into providers that do not know them. Before,
  Copilot's agents and skills were written with `model: fable` / `model: opus`. A provider
  now declares `capabilities.models = "core"` to read the core aliases (claude does); any
  other provider takes `[providers.<name>].model_policy` (its own model names, which also wins
  for claude), and a role without a value drops the `model:` line, so the file runs on the
  session model. `harness plan` notes the dropped lines per provider. Prose that names the
  policy is unchanged.
- `core` redact block (`redact_text`, so `k8s redact`, `pod`, `workload` and `helm --values`):
  a mid-line `key: value` / `key=value` whose value starts with an HTTP auth scheme word
  (`Bearer`, `Basic`, `Token`, `Digest`, `Negotiate`, `SSWS`, `OAuth`, `ApiKey` or
  `Api-Key`; any case) now masks the scheme word and the token after it as one value. Before, only the
  scheme word was masked and the credential after it leaked
  (`… Authorization: ***REDACTED*** <token>`). Lines that start with the key were already
  fully masked. `extra_re` now runs after the built-in rules (a pattern naming a key or scheme
  word, e.g. `(?i)bearer`, hid the token from them), never touches Secret `<N bytes>` sizes,
  and is ignored with one stderr warning when it matches the empty string. `k8s` compiles
  `k8s.redact_extra_re` on first use, so an invalid value fails only the redacting commands
  (`not a valid Python regex`) instead of every command; `redact.py` rejects one with exit 1.
  k8s goldens `redact-text`, `redact-extra-re`, `pod-md` and `pod-json` gain one fixture line.
- `bin/harness` runs the checkout it lives in: an inherited `HARNESS_HOME` naming another checkout
  is ignored with a note instead of silently making a worktree's pre-commit hooks and `make`
  targets lint and test the main checkout. `python3 -m harness` and rendered scripts still read
  the variable; `--home DIR` remains the explicit override.
- `harness test` drops git's repository-discovery variables (`GIT_DIR`, `GIT_WORK_TREE`,
  `GIT_INDEX_FILE`, …) from every suite's environment, and the pack unit tests drop them too.
  Git exports them to hooks, so the pre-push hook's unit run pointed the pack fixture
  repositories at the real checkout and failed (in a worktree, with the whole hub staged for
  deletion); the suites now pass from hooks as they do from a shell.
- The work-ticket GitHub preflight no longer expands an empty candidate-branch list as
  `"${candidates[@]}"`, which bash 3.2 under `set -u` reports as an unbound variable when no
  branch is passed.

### Changed

- `/create-ticket` `render-ticket.py --check` (part 04 of #80), message only: the reason for a
  GitHub closing keyword in an issue's title or body now says it "belongs only in
  work-ticket's PR to the default branch" instead of "mention #N instead". The check is
  unchanged; the `bad-gh-closing` row now asserts the reason.
- Guard section `41-github-closing` (part of #80): a closing keyword + bare `#N` passes 41
  (section 60 still decides the create or edit) when `github.close_issue_on_merge` is on (a
  `false` in `guard.env` is final: the environment cannot switch it back on), the repository
  declares `[repo] tracker = "github-issues"`, and the command is a narrow, fully parsed form:
  one line; every clause (cut on unquoted `;` `&` `|` `(` `)` only) a top-level literal
  `gh pr create|new` with one explicit `-B` or `gh pr edit N`; every closing ref a bare `#N` in
  that command's `-t`/`-b` text; flags parsed the way gh parses them (short clusters such as
  `-dB`, attached and `=` values); the repository the cwd checkout's github.com `origin` (a `-R`
  must name it); the base (`-B`, or the edited PR's base) equal to that repository's
  `defaultBranchRef`; the head not `-sub-` and not a fork; every `#N` labelled `agent-worked` (at
  most 10 refs). The default branch, the edited PRs and the issues are read with ONE batched
  read-only `gh api graphql` query under an overall 15 s deadline. Everything else keeps the
  deny, with a reason that names the alternative: `git commit`, `gh pr merge`, `gh api`,
  `owner/repo#N`, issue URLs, quoted or `$VAR` command words, a multi-line command ("pass a long
  body with -F file"), `cd`/`pushd`/`popd`, `GH_REPO`/`GH_HOST` anywhere in the command,
  `sh -c`/`bash -c`/`eval`/`xargs`/`env`, `$(…)`, backticks, `<(…)`, heredocs and herestrings,
  other commands next to the `gh pr` one, a repeated `-B`/`-H`/`-R`/`-t`/`-b`/`-F`, an unknown
  flag, `--`, a positional argument on create, an unquoted glob or brace, a `-R` other than the
  checkout's origin, a non-github.com or missing origin, a base that is not the default branch
  (`-B master` where the default is `main`), a ref outside the `-t`/`-b` text, a lookup failure
  or overrun, and repositories without the declaration. Jira keys (section 40) are unchanged. The
  lookups `gh_q`, `fetch_gh_pr` and `fetch_gh_issue` moved from 60 into 41's shared definitions
  (above its `repo_owns` line), so both sections use them; 60 keeps its own lookups and clause
  cut, so a body with a quoted `;` that 41 lets through still asks there.
- Guard section `41-github-closing` (part 02 of #80): a repository without a `.harness.toml`
  `[repo] tracker` now has its tracker resolved the way `/work-ticket` resolves it
  (`rf_tracker`): the first `ticket_workflow.trackers` entry whose `match` ERE hits the origin
  remote id (case-insensitive), else the host (github.com → `github-issues`, any other host →
  not GitHub Issues). Stricter than `rf_tracker`, and fail closed: an empty or invalid `match`
  ERE denies (pointing at `harness doctor`) instead of being skipped. A declared tracker always
  wins (`jira` declared on a github.com repository denies; an invalid declared value denies as
  before), and a `.harness.toml` that carries a tracker the guard cannot read (dotted
  `repo.tracker`, a `repo = { … }` inline table, a trailing comment, a quoted key, a multi-line
  string or array, more than one tracker line, a tracker line outside `[repo]`, or a file the
  engine ignores as over 16 KiB / 400 lines) denies as unreadable; a `[repo]` table without a
  tracker still falls through. A matching entry naming any tracker but `github-issues`, a
  malformed list (not exactly one JSON array of objects, or a NUL inside `match`/`tracker`), no
  origin remote or a git failure or timeout deny. The list is checked twice, from the
  environment's `HARNESS_TICKET_TRACKERS` and from `guard.env`'s own value (the engine keeps it
  in `HN_GENV_TICKET_TRACKERS`, like `HN_GENV_CLOSE_ON_MERGE`): an environment value (a
  repository's provider env, even `[]`) can add a deny but never undo the user's `jira` entry.
  The resolution reuses the one origin read the allow path already makes (no extra git call,
  and no git or gh call at all without a closing keyword); the allow path needs the origin to
  be exactly `github.com/<owner>/<repo>` (so `…/r.git.git` denies), and an entry naming
  `github-issues` for another host denies. The ticket-workflow bundle renders
  `ticket_workflow.trackers` into `guard.env` as `HARNESS_TICKET_TRACKERS` (one line of JSON).
  Section 41 carries `rf_remote_id`'s normalisation between `rf_remote_norm` markers; both the
  ticket-workflow suite and the github guard rows fail when that copy and `repo-facts.sh` drift.
  Test stubs gain `GIT_STUB_LOG`, `GH_STUB_LOG` and `GIT_STUB_REMOTE=hang`.
- `/work-ticket` on GitHub Issues (part 03 of #80): the github preflight reports
  `issue.close_on_merge` — `true` when the tracker is `github-issues`,
  `github.close_issue_on_merge` is on (config, and `HARNESS_GITHUB_CLOSE_ISSUE_ON_MERGE` when
  set: anything but `true` from either is off), the delivery is not the fork flow (an unknown
  `fork_flow`, e.g. without auth, counts as fork) and the issue lives in `base_repo`. When it is
  `true`, the body of the one PR whose base is the default branch (the single PR, or the main PR
  of a stack, first and second pass) writes the closing keyword for the worked `#N` plus its
  `agent-worked` sub-issues (at most 10 bare refs), and the handoff says "merging the PR closes
  #N"; sub PRs, fork PRs, other bases and `close_on_merge: false` keep the mention and today's
  "close it yourself" text. The Step 6 read-back now checks `gh pr view --json
  closingIssuesReferences` equals exactly that set (empty otherwise; the guard cannot read `-F`
  body files, so this is the sensor), keeps the Jira-key and foreign-ref keyword greps, and
  greps every title and every mention-only body for a `#N` keyword. Commits, titles, Jira keys
  and issue text never carry a closing keyword, in any mode. The ticket-workflow test stubs now
  also unset `HARNESS_GITHUB_CLOSE_ISSUE_ON_MERGE`, `HARNESS_TICKET_TRACKERS` and
  `HARNESS_GUARD_ENV`. Review follow-ups: `issue.close_on_merge` is also `false` when origin is
  not `base_repo` (a fork with write access on its parent, which the guard denies) and when the
  guard's own `guard.env` (`HARNESS_GUARD_ENV`, else `<hooks dir>/guard.env`, parsed, never
  sourced) sets `HARNESS_GITHUB_CLOSE_ISSUE_ON_MERGE` to anything but `true`; the §6a read-back
  runs as is in both modes (`CLOSE`/`WANT`), re-reads `closingIssuesReferences` once after a few
  seconds (GitHub fills it asynchronously), greps the PR's commit messages too, and matches issue
  URLs with `www.` like the guard; at most 10 refs (worked issue + first 9 sub-issues, the rest
  listed in the handoff); the issue title sits on its own line, never right after a keyword; the
  handoff and agent notes no longer put a keyword directly before a ref. Rule `60-github` says a
  `-F` body is not checked by the guard and is read back by work-ticket.
- Guard section `41-github-closing`: a closing keyword or issue ref written with quotes or
  escapes inside it (the keyword split by quotes, a backslash before the space or the `#`) on a
  `git commit`, `gh pr create|edit|merge` or `gh api` line is now denied like the plain form; it
  used to pass 41 unseen.
- Lint rule `yields`: multi-line function definitions (a column-0 `name() {` line up to a
  column-0 `}` line) may precede a guard section's `repo_owns` line like plain shared
  assignments; defining a function runs nothing, and later sections may call it. One-line
  definitions stay stray (code could follow the closing brace on the same line), and so does a
  definition still open at the `repo_owns` line.
- GitHub guard section 60 governs the `gh stack` extension (github/gh-stack; part 1 of #86).
  `stack` joins the gh nouns, so quoted or `$VAR` verbs (`gh "stack" merge`, `gh stack $V`)
  ask on the main thread and deny in a subagent; `gh extension exec stack …` and a direct
  `gh-stack …` are judged like `gh stack …`, and `gh extension exec` of any other extension
  asks. `gh stack merge` is a human decision (asks; denied from a subagent). `gh stack link`
  is promptless only with `--base <ticket branch>` and literal numbers of agent-labelled
  `-sub-` PRs of that ticket branch; a missing `--base`, a default-branch or `-sub-` base, a
  branch-name argument (it would push and open an unlabelled PR) and a non-`-sub-` PR (the main
  PR) deny, while unlabelled or fork PRs, URLs, `$VAR` arguments, `GH_REPO=`, unknown flags and
  failed lookups ask, as do `--remote`, `GH_HOST=`, a gh-level `-R` and a preceding `cd`/`pushd`.
  `--open` on any verb, `gh stack alias`, unknown verbs, flags before the verb and
  `gh extension exec` of another extension are human decisions; `gh.exe`, `gh-stack.exe`,
  `gh extension exec -- stack` and the `gs` wrapper count as `gh stack` (`gh-stack` and `gs`
  only as a command word, so an argument such as `gh extension install github/gh-stack` keeps
  its own decision).
  `gh stack push|submit|sync|rebase|modify|unstack|delete|init|add` deny when the current
  branch (or one checked out earlier on the command line, or after `gh stack trunk|bottom`),
  `--base`, a branch argument or the trunk/layers read from `gh stack view --json` is the
  default branch (`origin/` and `refs/heads/` stripped; and `init` without `--base`), and ask otherwise, naming `stk sync --stack
  BR`, lease pushes of the `-sub-` branches and `gh stack link` by PR numbers. `gh stack alias`
  and unknown verbs ask (denied from a subagent); reads and navigation (`view`, `up`,
  `checkout` …) pass.
  `permissions.toml` allows `gh stack view` and asks on `gh stack merge`; rules/60-github.md
  gains a stacked-delivery bullet. The guard test gh stub answers `gh stack view --json`
  (`GH_STUB_STACK`) and has a second labelled sub PR (111).

- `stk` keeps a linked native GitHub stack consistent (part 3 of #86). It reads the Stacks API
  like gh-stack (`repos/o/r/stacks?per_page=100&page=N` until a short page, at most 20); a 404
  turns the feature off and every report stays as it was, a 403 is `info`, an auth failure
  exits 2, any other error skips the step. Otherwise `stk plan|status` map each part to its stack number
  (`native_stack`, `native_stacks`), `stk check` adds the `info` finding `native_stack`
  (enabled, the gh-stack extension from `gh extension list`, the stacks on the ticket branch;
  `--fix` prints `gh extension install github/gh-stack`), and `stk sync` gains a step after the
  cascade and push: per linear chain of two or more open parts rooted at `BR`, a stack whose PRs
  are all open and a strict ordered prefix of the chain is extended with
  `gh stack link --base BR <PR numbers>` (run in the main checkout with
  `GH_STACK_NO_UPDATE_NOTIFIER=1`; `planned` in `stk plan`) when every part is agent-labelled
  and the extension is installed, the main checkout cannot resolve another repository
  (`GH_REPO`/`GH_HOST` unset, origin is the repository, no `gh-resolved` default or other GitHub
  remote naming another one) and has no local branch named like a chain PR number. A consistent
  stack and a chain that was never linked are `info` (exit 0); an order or membership mismatch,
  parts in two stacks, a stack on another base, a stack still listing a merged or closed PR, an
  unlabelled part, a missing extension or an ambiguous repository are `todo` with the commands
  for the human, and a stack holding PRs outside the ticket gets no unstack command (the
  foreign PRs are named for the human to decide first). stk never
  creates a first stack, never unstacks and never runs `gh stack sync|push|rebase|merge`; fan-in
  leaves and branching chains stay unlinked by design. Retargeting is unchanged; a failed
  retarget of a stacked PR names the stack and the unstack and re-link commands. The stk test
  stub answers `gh api …/stacks`, `gh extension list` and `gh stack link`; new
  `gh-native-stack-*` scenarios (bottom merged, tail unlinked, drift, disabled, a branching chain
  and sync variants: run from a linked worktree, base not `BR`, closed stack, API 401/403/500,
  foreign PRs, ambiguous repository, branch named like a PR, pending retarget) and invariants (only `gh stack link --base feat-x <numbers>`, never a default-branch
  base, plan/status/check never link). No config change.

- GitHub and GitLab guard sections adopt "humans decide" (principle 2, part of #67). From a
  subagent (Claude Code's `agent_id`) every merge, approval and PR/MR/issue state change is
  **denied** with "hand the command back to the main thread": `gh pr merge|review`,
  `glab mr merge|approve|revoke`, `gh pr close|reopen|ready`, `gh issue close|reopen`,
  `glab mr close|reopen`, `glab mr update --ready|--draft`, `glab issue close|reopen`, on human
  and agent-labelled refs alike, before any label lookup; so are raw `gh api` / `glab api`
  writes (non-GET, fields without a method, GraphQL mutations, `--input`). On the main thread:
  merge, approve and review ask on every ref; PR/MR state asks on a human ref and stays
  promptless on an agent-labelled one; `gh issue close|reopen` on a human issue **asks**
  (was deny); `glab issue close|reopen` asks (no label model). `glab mr reopen` joins the MR
  label gate and `glab issue reopen` is guarded (both were unguarded). Labelling flags never
  make a state change free. Comments, edits, labels, rebases and `update-branch` are unchanged,
  and so are the closing-keyword denies (sections 40 and 41). A repository owning `scm` still
  passes, in a subagent too. `gate_writes` gains optional state-flag arguments and loses its
  `WORK_TICKET_ALLOW_TRANSITION` branch; `gitlab/permissions` asks on `glab issue reopen`.
- The gh and glab sections see through hidden forms of the same calls (#67 review):
  - fd duplications (`2>&1`, `>&2`, `&>`) no longer cut a clause short;
  - quoted or escaped command words (`gh "pr" merge`) and a `$VAR` / `$(…)` subcommand ask on
    the main thread and deny in a subagent;
  - `-R` / `--repo` in every spelling (attached `-Ro/r`, `--repo=`, before the noun or the
    verb) and the glab aliases (`mr accept`, `mr unapprove`, `mr|issue open`, `del`,
    `mr comment`, `mr new`) and gh aliases (`pr new`, `issue new`) count;
  - flags are parsed as the CLIs parse them (`-r=true`, `-yr`, attached short values), and
    `glab mr update --fill|--fill-commit-body|--unassign` no longer hide a following state flag;
  - every `glab api` method other than GET/HEAD in any spelling, and every payload flag, is a write;
  - GitLab quick actions (`/merge`, `/approve`, `/close`, `/reopen`, `/ready`, `/draft`,
    `/target_branch` …) in glab notes, descriptions and titles ask, and deny in a subagent,
    as does note or description text the guard cannot read (a missing or `-` description file,
    the editor, `$VAR`) in a subagent;
  - every glab ask is deferred, so a later deny in the same command still wins;
  - `gh issue delete|transfer`, `glab mr delete` and `glab issue delete` are human decisions;
  - closing keywords in the command forms sections 40 and 41 do not parse (`gh -Ro/r pr edit`,
    `gh pr new`, `glab -R g/p mr update`, `glab mr new`) are denied by sections 50 and 60,
    which yield for that check exactly as 40 and 41 do (domain `tracker`).
- The Jira guard section adopts "humans decide" too (part of #67). `jira transition` on a
  human ticket **asks** on the main thread (was deny; the ask is deferred, so a later deny in
  the same command still wins) and stays promptless on an agent-labelled ticket; from a
  subagent every transition is **denied** before any label lookup, on human and
  agent-labelled tickets alike. A transition whose ticket cannot be checked still denies:
  every transition clause needs a literal key (`$VAR`, `xargs` and quoted keys deny, also
  next to another write that has one), and a failed label lookup denies. A promptless
  `jira link`, labelled `jira create` or `jira label … add agent-*` in the same command no
  longer lets a transition through; `2>&1` no longer cuts a `jira label` clause; quoted or
  escaped command words (`jira "transition"`, `j\ira`) and a `$VAR` / `$(…)` subcommand ask
  on the main thread and deny in a subagent (a hidden non-transition write asks in both).
  Other Jira writes are unchanged, and `jira api` is GET-only in the client, so there is no
  raw API write to gate. A repository owning `tracker` still passes, in a subagent too.
- The Jira section reads the command with a small shell scanner instead of regexes over the
  whole text (#67 review). Only a jira call in command position counts: after assignments and
  wrappers (`env`, `exec`, `command`, `sudo`, `nice`, `timeout`, `xargs`, `find -exec` …), inside
  `sh|bash -c` strings, `eval`, `$(…)` and backticks, heredoc bodies fed to a shell and text
  piped into one. Text that only mentions jira (a comment body, a `"$(cat <<'X' … X)"` body, a
  commit message, a grep pattern, a path argument to `ls`) no longer asks or denies.
  - A ticket key is a whole literal word: `jira transition LBL-1/../HUM-2` denies and
    `jira comment LBL-1/../HUM-2` asks (both used LBL-1's labels before); every keyed clause
    needs its own literal key (`jira comment LBL-1 a && jira comment "$KEY" b` asks, was
    allow). The `jira` client refuses any key that is not exactly `[A-Z][A-Z0-9_]*-[0-9]+` in
    every keyed command, lower-case keys included.
  - jira the guard cannot read is a human decision (ask; deny in a subagent): fed by `xargs`
    without a verb, a `NAME=jira` variable or alias, `$(which jira)` as the command, a
    case-changed name (`JIRA`, `jira.PY`), jira code in `python|perl|node -c|-e`; a hidden
    known read passes and a hidden non-state write asks. A quoted literal key
    (`jira transition 'HUM-1' Done`) is read as the key (ask, was deny).
  - `jira set KEY status|resolution` is a state change like a transition (promptless on an
    agent-labelled ticket, ask on a human one, denied in a subagent).
  - A promptless `jira link`, labelled `jira create` or `jira label … add agent-*` no longer
    lets any other write in the same command through (was allow); every `jira link` clause is
    checked, not only the first.
  - The literal-key deny for a state change comes before any check that can stop first.
  - The scanner fails closed: a `jira VERB` call written anywhere outside a known data
    position is a hidden call. Data positions: the jira client's own arguments (comment
    bodies), `git commit|log|tag|show|…` arguments, `grep`/`rg` patterns, and `echo`/`printf`
    output or `cat`/`tee` heredocs and here-strings whose pipeline holds only non-executing
    stages (`cat`, `tee`, `grep`, `head`, `jq` …). It also reads `${…}` bodies, process
    substitutions (`<(…)`, `>(…)`), here-strings and heredocs fed to a shell, text piped into
    a shell through any number of stages, `sh -c CODE ARGS` running its positional words,
    python value options (`-X`, `-W`), command-string wrappers (`env -S`, `watch`, `script -c`,
    `su -c`, `parallel`, `git -c alias.x='!…'`), zsh `=jira`, ANSI-C `$'…'` words, globbed or
    `${VAR}`-built command words in front of a state verb, and backslash-newline splits.
  - A scanner failure (python3 missing, broken or timed out) asks on the main thread and is
    denied in a subagent, with its own reason.
  - Jira allows and asks are deferred (`pending_allow`, `defer`), so a deny in a later section
    (e.g. `gdoc api -X POST`) wins over a promptless Jira write in the same command.
  - `jira create` with more than one `--field labels` is denied (the last one wins in Jira).
  - Latency: the scanner (python3) runs only when the command can hold a jira call; it adds
    about 20 ms to such a command (`git status` is unaffected).
  - Known limit: a copied or renamed client (`cp jira x; ./x transition …`) and jira calls built
    inside other interpreters' code without the `jira VERB` text are not recognised; the
    provider's permission prompt is the backstop.
- `WORK_TICKET_ALLOW_TRANSITION` is a deprecated no-op (#67): the engine no longer reads it;
  the name stays allow-listed, so setting it is not an error, and `harness repo` reports a
  set value as "deprecated, no effect" with where to remove it. `harness repo init` no longer
  suggests it, and the ticket-workflow manual step no longer lists it.
- Rules and docs state "humans decide" (part of #67): the core, github, gitlab, jira, stack and
  ticket-workflow rules, the github/gitlab/jira/stack manifest notes, governance, concepts,
  repository-level harnesses, principle 8, SECURITY and the README now say that merges,
  approvals and PR/MR/issue/ticket state changes run only on the user's explicit main-thread
  request (the guard asks, a subagent is denied) instead of "human-only" / "never"; closing
  keywords stay denied and `WORK_TICKET_ALLOW_TRANSITION` is gone from every example.
- Skills and the Auto agent state "humans decide" (part of #67): work-ticket, create-ticket,
  stk and jira never merge, approve or change state on their own initiative — they name the
  command, and the main thread runs it only on the user's explicit request (the guard asks;
  stk merges only the part `stk plan` names next, then syncs); subagent briefs and the Auto
  agent hand such commands back, since the guard denies them in a subagent. Sub-ticket
  In-Progress moves are main-thread only; the jira skill documents the literal-key refusal.
- Closing-keyword deny reasons (sections 40, 41, 50, 60) and the `harness lessons propose`
  refusal no longer say "state is human-only": a closing keyword would change the ticket's or
  issue's state as a side effect, so it stays denied even on request.
- `harness pack --tools` skips tool locks marked `"optional": true` (with a note naming
  `--tools-optional`) unless `--tools-optional` is given (`--tools-optional` without `--tools`
  is refused, exit 2), and bootstrap no longer auto-installs a
  binary a bundle declares `optional` (it prints `harness install TOOL`; doctor already WARNs
  with the same hint). A bundle that requires a binary still gets it installed (`gh` for
  `github`); `stack` alone no longer pulls in `gh`.
- `harness lint` rule `stability` now checks `beta` bundles as well as `stable` ones: a skill
  or CLI without a `tests/run.sh`, or a `coverage_note` admitting a missing suite, warns with
  the level to move to (`beta` → `experimental`, `stable` → `beta`). CONTRIBUTING "Stability
  levels" already required the suites at `beta`; `ticket-workflow` and `gdoc` pass. Principle 9
  lists the check as shipped (principle 9).
- `/work-ticket` and `/create-ticket` read the declared tracker at preflight instead of
  guessing it from the host or the argument form: the argument must agree with it (`KEY` with
  `jira`; `#N`, `owner/repo#N` or an issue URL with `github-issues`, a bare `N` only then), a
  mismatch or an invalid declaration stops the skill with one sentence naming the source, and a
  declared Jira `project` is create-ticket's default project. A GitHub repository can declare
  Jira as its tracker (Jira tickets, GitHub PRs).
- `create-facts.sh` matches the cwd's clone by remote id (`<github host>/<owner/repo>`)
  instead of a literal `github\.com` pattern, so GitHub Enterprise clones report their issue
  templates too.
- `core`: the redactor is one shared block, `bundles/core/lib/redact.py` (`# >>> redact` …
  `# <<< redact`: `KEY_BODY`, `SECRET_KEY_RE`, `REDACTED`, `redact_obj(obj, extra_re=None)`,
  `redact_text(text, extra_re=None)`), registered in `sync_inline.py` and inlined into the
  `k8s` CLI in place of its own copy (principle 10). The block was extracted unchanged; the
  `### Fixed` bullet above describes the only behaviour changes (auth-scheme masking,
  `extra_re` ordering and empty-match guard, lazy compile). New optional key
  `k8s.redact_extra_re` (`K8S_REDACT_EXTRA_RE`, default `""`): an extra Python regex of token
  shapes `k8s redact`, the `pod`/`workload` log tails and `helm --values` mask on top of the
  built-in list; golden `redact-extra-re`.
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

### Migration

- New config key `github.close_issue_on_merge` (default `true`) and a guard decision change
  (part of #80). In a repository whose `.harness.toml` declares `[repo] tracker =
  "github-issues"`, a closing keyword + bare `#N` of an `agent-worked` issue in
  `gh pr create -B <default branch>` or `gh pr edit` of the PR to the default branch used to be
  **denied** and now passes the closing-keyword section (the PR create/edit gates of section 60
  still apply). Repositories without that declaration, or declaring `jira`, see no change. To
  keep the old deny everywhere, set `close_issue_on_merge = false` under `[github]` in your
  `harness.toml` and run `harness apply`.
- Guard decision change in section `41-github-closing` (part 02 of #80): more repositories now
  allow the PR to the default branch to close its `agent-worked` `#N`. Besides those declaring
  `[repo] tracker = "github-issues"`, every github.com repository without a `.harness.toml`
  tracker does, unless the first `ticket_workflow.trackers` entry matching its origin names
  `jira`. To keep the deny for such a repository, declare `[repo] tracker = "jira"` in its
  `.harness.toml`, or add a `[[ticket_workflow.trackers]]` entry (`match`, `tracker = "jira"`)
  to your `harness.toml`; to keep it everywhere, set `close_issue_on_merge = false` under
  `[github]`; then run `harness apply`. The `github` bundle only recommends `ticket-workflow`:
  without that bundle no `ticket_workflow.trackers` entries reach the guard and the host decides,
  so every undeclared github.com repository allows; keep the deny there with
  `[repo] tracker = "jira"` in the repository's `.harness.toml` or with
  `close_issue_on_merge = false`. A `.harness.toml` tracker must be one plain line
  `tracker = "…"` under `[repo]` without a trailing comment: dotted (`repo.tracker`), inline-table,
  commented or repeated forms now deny the closing keyword as unreadable.
- Guard decision change in section `41-github-closing`, nothing to edit in config: a closing
  keyword or issue ref hidden by quotes or escapes (the keyword split by quotes, a backslash
  before the space or the `#`) in a `git commit`, `gh pr` or `gh api` command used to pass and is
  now **denied**. Write the reference plainly as a mention (`part of #N`), or, for the PR to the
  default branch of a github-issues repository, plainly inside the `-b` text. The test stubs
  gain `GIT_STUB_REMOTE` (`git remote get-url origin`, default a github.com remote for `o/r`)
  and `GH_STUB_DEFAULT_BRANCH` (the batched GraphQL lookup, default `main`).
- New config key `github.stack_extension_version` (#86), default `0.3.0`; nothing to edit
  unless you install another gh-stack version on purpose. Run `harness apply` so the rendered
  environment carries `HARNESS_GITHUB_STACK_EXT_VERSION`. Installing the extension stays
  optional and manual (`harness steps`, step `github#gh-stack-extension`:
  `gh extension install github/gh-stack --pin v0.3.0`); `harness doctor` warns only when
  another version (or a third-party `gh stack`) is installed or `gh extension list` fails.
- Guard decision change (#86), nothing to edit in config. `gh stack …` (and
  `gh extension exec stack …`, `gh-stack …`) had no guard decision; `gh stack merge` now
  **asks** on the main thread and is **denied** from a subagent, `gh stack link` and the
  pushing/restacking verbs **ask** or are **denied** as described under Changed, and
  `gh extension exec` of another extension **asks** (and is **denied** from a subagent). Link sub PRs by number
  (`gh stack link --base <ticket branch> N1 N2`), keep stacks in sync with
  `stk sync --stack BR`, and hand `gh stack merge` to the user.
- Guard decision change (#76), nothing to edit in config. In a repository whose `.harness.toml`
  owns `scm` but not `tracker`, a closing keyword in `gh -Ro/r pr …`, `gh pr new`,
  `glab -R g/p mr …`, `glab mr new`, a repeated repo flag or a quoted / `$VAR` gh or glab
  command word used to pass and is now **denied**, as the plain spellings already were. In every
  repository, `glab -R g/p api …` with closing-keyword text anywhere in the command (an API write
  that asked, or a GET piped into a grep for the keyword) is now denied like plain `glab api`,
  and a quoted or `$VAR` gh/glab command word next to a closing keyword is denied instead of
  asked. Mention the ticket instead (`part of #12`, `PROJ-123 fix parser`).
- Guard decisions for gh and glab (#67), nothing to edit in config: `gh issue close|reopen` on
  a human issue now **asks** on the main thread instead of denying. Merges, approvals, reviews
  and PR/MR/issue state changes run from a subagent are now **denied**, as are raw `gh api` /
  `glab api` writes from a subagent: have the subagent hand such a command back, and run it
  from the main thread when the user asks for it. `glab issue reopen` and `glab mr reopen` are
  newly guarded (ask on a human ref; `glab mr reopen` on an agent-labelled MR stays promptless).
  `WORK_TICKET_ALLOW_TRANSITION` no longer affects GitHub issues (and, with the Jira entry
  below, nothing at all); a repository that set it can drop it.
  Also newly guarded: the glab aliases `mr accept`, `mr unapprove`, `mr|issue open`,
  `mr|issue del` and `mr comment` (each decided like the command it stands for), and GitLab
  quick actions in glab note and description text (ask; deny from a subagent). `gh issue
  delete|transfer`, `glab mr delete` and `glab issue delete` from a subagent are now denied
  (the main thread still asks). Quoted command words such as `gh "pr" comment` now ask instead
  of passing: write gh and glab subcommands unquoted.
- Guard decisions for Jira (#67): `jira transition` on a human ticket now **asks** on the main
  thread instead of denying; transitions run from a subagent are now **denied**, on
  agent-labelled tickets too: have the subagent hand the command back, and run it from the
  main thread when the user asks for it. `WORK_TICKET_ALLOW_TRANSITION` is a deprecated
  no-op: remove it from `.harness.toml` `[overrides]` and from any provider `env`
  (`.claude/settings.json` `"env"`); nothing replaces it, since the main thread now asks
  without it. A repository whose own workflow transitions tickets owns the `tracker` domain
  instead. Quoted Jira command words (`jira "comment" …`) now ask instead of passing: write
  jira subcommands unquoted. `jira set KEY status|resolution` follows the transition rule. The
  `jira` client now refuses lower-case or path-like keys (`proj-123`, `PROJ-1/..`): pass
  `PROJ-123`. Commands that combine a promptless Jira write with another write now go through
  the label gate for the other write (ask on a human ticket). Text that spells out a jira call
  and is handed to anything that may execute it (`foo "jira transition …"`, `script -c`,
  `watch`, a pipe into a shell) now asks, and is denied in a subagent; keep such text in a
  jira comment, a commit message or a grep pattern, or run the jira command directly.
- Guard decision change (core, every install): `curl … | sh` and the other pipe-to-shell forms
  of core section `35-shell-hygiene` (also inside `{ }` / `( )` groups, compound bodies, a
  continued line, `tee >(sh)`, `python3 -c "$(curl …)"` and an interpreter's heredoc) used to
  pass and now **ask**. Download the script to a
  file, check its sha256, read it, then run it. A repository whose `.harness.toml` owns domain
  `base` (`[owns] domains = ["base"]`) or the component (`components =
  ["core/guard.d/35-shell-hygiene"]`) lifts the section there; nothing else changes. No config
  key was added.
- `supply-chain` bundle: new keys only when you enable it (`supply-chain` in `[hub] bundles`):
  `supply_chain.allow_global_re` (`SUPPLY_ALLOW_GLOBAL_RE`), `supply_chain.venv_markers`
  (`SUPPLY_VENV_MARKERS`), `supply_chain.registries_re`, `supply_chain.identities` (array of
  tables), `supply_chain.redact_extra_re`, `supply_chain.osv_offline_db`,
  `supply_chain.pin_actions`, `supply_chain.max_bytes`, and for the `supply` CLI
  `supply_chain.exclude_re` (default `""`) and `supply_chain.timeout` (default `120`). The guard's `guard.env` parser now also
  accepts `SUPPLY_` keys (core engine and the `env-provides` lint list); nothing to edit for
  existing setups. With the bundle enabled, `pip install` outside a venv, global npm/cargo
  installs and unpinned git dependencies ask. An auto-activated conda `base` is not a venv
  (`CONDA_PREFIX` counts only when `CONDA_DEFAULT_ENV` names another env and the prefix is not
  the conda or mamba root), and a `VIRTUAL_ENV=` assignment on the command line is no marker:
  activate a project env, or use `uv` or `.venv/bin/pip`. Write `supply_chain.allow_global_re`
  anchored (`^(ruff|black)$`).
- Optional tool locks (`supply-chain`): a `tools/*.lock.json` may carry `"optional": true`.
  `harness pack --tools …` leaves such locks out unless you add `--tools-optional`; an
  air-gapped site that wants osv-scanner, cosign or syft adds the flag to its pack command.
  Bootstrap no longer installs a missing binary that a bundle declares `optional`: the one
  existing case is `gh` for `stack` without the `github` bundle (with `github` enabled, gh is
  required there and still installed); run `harness install gh`, and `harness install
  osv-scanner|cosign|syft` (or `--from FILE`) for the scanners you use. `supply_chain.osv_offline_db`
  names the directory osv-scanner keeps its databases under (`DIR/osv-scalibr/<Ecosystem>/all.zip`,
  osv-scanner 2.7.0): point it at the directory that contains `osv-scalibr/`. Doctor WARNs an
  osv-scanner older than 2.7.0, cosign older than 3.1.4 or syft older than 1.55.0: `harness
  install TOOL` puts the pinned version first in `~/.local/bin`. A script running `supply verify
  IMAGE --offline` with cosign now gets exit 3: verify the image online, or offline a downloaded
  file with `--bundle F --trusted-root F` or `--github OWNER/REPO --bundle F --trusted-root F`.
  Nothing to edit otherwise.
- Per-provider model names: one new optional config key, `[providers.<name>].model_policy`
  (`plan`, `execute`). Claude needs no edit. For Copilot, `harness apply` now writes agents
  and skills without `model:` (session model); to pin models, add
  `model_policy = { plan = "<copilot model>", execute = "<copilot model>" }` under
  `[providers.copilot]` in `local/harness.toml`, then `harness apply`.
- Declared tracker: nothing to edit. `ticket_workflow.trackers` defaults to `[]` and a
  repository without `[repo] tracker` keeps today's host rule (github.com → GitHub Issues,
  GitLab → Jira). To pin a repository's tracker, add `[repo] tracker = "jira"` (and
  `project = "KEY"`) or `"github-issues"` to its `.harness.toml`, or list
  `[[ticket_workflow.trackers]]` entries in `local/harness.toml`; then `harness doctor`.
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
  today's redaction; nothing to edit. Set it to a Python regex (e.g. `"(?i)x-internal-token=[^ ]+"`)
  under `[k8s]` and run `harness apply` to mask more token shapes.
- `obs` bundle: new keys only when you enable it (`obs` in `[hub] bundles`): `obs.backends`
  (array of tables), `obs.default`, `obs.hosts_re` (`OBS_HOSTS_RE`), `obs.prod_re`
  (`OBS_PROD_RE`), `obs.log_tail`, `obs.max_bytes`, `obs.redact_extra_re`
  (`OBS_REDACT_EXTRA_RE`); see the manual step `configure-backends`. The guard's `guard.env`
  parser now also accepts `OBS_` keys (core engine and the `env-provides` lint list); nothing
  to edit for existing setups.
- Lessons library: eight new `core` keys under `[lessons]`, read only by `harness lessons`;
  nothing to edit, and no `guard.env` change. `lessons.dir` (default `""` =
  `~/.local/state/harness/lessons`), `lessons.promote_after` (3), `lessons.max_age_days` (90),
  `lessons.index_max` (40), `lessons.index_max_candidates` (5), and the review thresholds
  `lessons.review.corrections` (2), `lessons.review.dissatisfaction` (1) and
  `lessons.review.denies` (3), where `0` disables a criterion. A `lessons.dir` you set must lie
  outside the hub and every git checkout.
- Prompt-signal regexes: the defaults of `lessons.correction_re` and
  `lessons.dissatisfaction_re` change to meet the prompt fixture list
  (`bundles/lessons/hooks/tests/prompts.tsv`). A correction no longer starts with any
  `no ` ("no changes needed" is task text): `no`, `no,`, `no.`, `no!` and `no that|this|it|you|i|not|wait|stop …`
  still match; `wrong` and `incorrect` need a word end ("Wrong-way merge", "incorrectly
  rendered" are task text); `undo` and `redo` count alone, before punctuation or before
  `that|this|it` ("undo the last migration", "Redo the layout" are task text); curly
  apostrophes (U+2019) count in `that's`, `didn't`, `don't`. Dissatisfaction matches
  `don't do that|this` instead of any `don't do` ("don't do the rebase yet" is an instruction)
  and `why did|are you` but no longer `why do you` ("why do you think the test fails?" is a
  question). `^` and `$` apply to each line of a multi-line prompt. The new values:
  `correction_re = "^(no([,.!]|$| (that|this|it|you|i|not|wait|stop)([ ,.!']|’|$))|nope|(wrong|incorrect)([^a-z-]|$)|that(’|')?s not|not what i|i (said|asked|meant|told you|wanted)|you (didn(’|')?t|did not|ignored|missed|forgot|broke|changed)|(undo|redo)([,.!]|$| (that|this|it)([^a-z-]|$))|revert (that|this|it)|try again|again[,.!]?$|still (wrong|broken|failing|not))"`,
  `dissatisfaction_re = "(frustrat|annoy|unacceptable|stop (doing|that)|why (did|are) you|don(’|')?t (do (that|this)|ever)|you keep|this is (wrong|bad|useless))"`. Nothing to edit unless you copied the old defaults into
  `harness.toml`: then replace them with these or drop them.
- Guard journal: four new `core` keys under `[lessons]`, all off or inert by default, so there
  is nothing to edit. `lessons.journal` (bool, default `false`; `HARNESS_LESSONS_JOURNAL`)
  turns the journal on; `lessons.prompt_signals` (bool, default `false`;
  `HARNESS_LESSONS_PROMPT_SIGNALS`) is declared now for the lessons prompt hook of a later
  release; `lessons.correction_re` and `lessons.dissatisfaction_re` (POSIX ERE, used
  case-insensitively; `HARNESS_LESSONS_CORRECTION_RE`, `HARNESS_LESSONS_DISSATISFACTION_RE`)
  ship defaults. `guard.env` gains `HARNESS_GUARD_ID` and those four names on the next
  `harness apply`; no guard decision changes. `harness uninstall` keeps
  `~/.local/state/harness/{lessons,journal,retro}/`.

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
