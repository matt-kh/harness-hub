# Roadmap

Where the hub's bundles go next, so that the harness serves developers of every discipline
([principle 2](../principles/02-developer-first.md)) with the same guide-plus-sensor shape
([principle 6](../principles/06-harness-engineering.md)). This page is a proposal and a
backlog, not a commitment: items move between tranches as they are built, and shipped items
move to [CHANGELOG.md](../CHANGELOG.md). Numbers (prefixes, key names) are reserved here so
parallel work does not collide.

Status legend: **planned** (nothing built), **in progress** (a branch exists), **shipped**
(in `[Unreleased]` or a release; the line is removed on the next edit).

## What exists today

Seven public bundles cover source control (`github`, `gitlab`), one tracker (`jira`), the
ticket-to-merge workflow (`ticket-workflow`), Kubernetes (`k8s`), Google Workspace (`gdoc`)
and the conventions, credentials and git rules every developer needs (`core`). That is the
surface of a platform engineer. Application, data, QA, security and release engineers also
run containers, package managers, databases, cloud CLIs, infrastructure-as-code, pipelines
and remote hosts from the same terminal, and the agent sees none of it today.

The bundles also name their own gaps in `[harness].coverage_note`: `ticket-workflow` has no
guard section and no test suite for `work-ticket`; `gdoc`'s CLI has no unit suite; the
GitLab MR title convention is a guide only; GitHub fork PR edits always ask. Two engine
mechanisms have no real user: `skill_fragments` and the env override
`WORK_TICKET_KEY_IN_BRANCH`.

## Reserved guard prefixes

Sections are concatenated in prefix order and the first `allow`, `ask` or `deny` wins
([ARCHITECTURE §5](../ARCHITECTURE.md#5-guard)). New bundles take these bands; the list in
ARCHITECTURE §3 is updated when a band is first used.

| Prefix | Section | Bundle | Why this band |
|---|---|---|---|
| `22` | `22-secrets` | secrets | credential-class denies; must run before any later `ask` |
| `26` | `26-iac` | iac | next to `25-k8s-rules`, which already asks on `terraform apply` and `pulumi up`; same decisions, first wins |
| `27` | `27-cloud` | cloud | after `25`, so the k8s deny on `aws eks update-kubeconfig` fires before cloud's generic `update-* -> ask` |
| `31` | `31-git-hygiene` | core | git family, after `30-git` |
| `35` | `35-shell-hygiene` | core | shell-level hazards (pipe to shell, privilege escalation, destructive removal outside the checkout) |
| `36` | `36-containers` | containers | local-workstation tooling |
| `37` | `37-db` | db | local and remote data tooling |
| `38` | `38-toolchain` | toolchain | package managers |
| `45` | `45-release` | release | tags and publication; after the closing-keyword sections, before the SCM CLIs |
| `55` | `55-ci` | ci | between `50-gitlab` and `60-github`; adds only the rows those two lack |
| `75` | `75-ticket-workflow` | ticket-workflow | already listed in ARCHITECTURE; unused until P0 |
| `82` | `82-hosts` | hosts | miscellaneous band, with `80-gdoc` |

Free after this table: `15`, `32`–`34`, `39`, `42`–`44`, `46`–`49`, `65`, `85`.

## Proposed taxonomy values

Two new `domain` values, added through the procedure in
[taxonomy](reference/taxonomy.md#adding-a-value) when the first bundle using them lands:

| Value | Meaning | Used by |
|---|---|---|
| `infrastructure` | cloud accounts, hosts, containers, databases and IaC outside Kubernetes | cloud, iac, containers, db, hosts |
| `code` | the checkout itself: toolchains, dependencies, generated artefacts | toolchain |

Everything else reuses existing values: `ci`, `release` and the worktree work are `scm`
(pipelines, tags and worktrees live on or for the source host); `secrets` is `base` (its
meaning already includes credentials); `digest` is `delivery`. `db` stays under
`infrastructure` until a second data bundle exists ("a value exists only while a component
uses it"). No new `function` or `posture` values are needed.

## Tranche P0: honesty and cheap sensors

Close the declared gaps and add the lint rules that would have caught them. No new
dependencies, no new bundles. **Status: in progress.**

| Item | Where | Components | Effort |
|---|---|---|---|
| Guard section 75 | `ticket-workflow` | asks on key-named branches and key-prefixed commit subjects (opt-out `WORK_TICKET_KEY_IN_BRANCH=1`, which becomes a real switch), off-convention `-sub-` worktree paths and non-squash merges of `-sub-` branches; test rows incl. bypasses | S |
| MR/PR convention asks | `gitlab`, `github` | `glab mr create --fill` / `--related-issue` / title not matching `gitlab.mr_title_re`; `gh pr create --fill*` / title matching `github.pr_title_forbid_re` (default `#[0-9]+`); empty regex disables | S |
| New lint rules | engine | `env-provides` (a `[provides.env]` key the guard would drop), `rule-guard-pairing`, `permissions-vs-guard` (an allow-listed prefix the guard denies or asks), `agent-tools` (read-only agents with write tools; hard-coded model ids), `skill-description` (length 60–1024, trigger phrase, `NOT for` scope on workflow skills), `fragments-target`, `profile-sane`, `stability` | M |
| Stability levels | `CONTRIBUTING.md`, manifests | experimental / beta / stable / deprecated criteria; `ticket-workflow` and `gdoc` move to `beta` until their suites exist | S |
| Sensor kind `provider-feature` | schema, providers | declares an inferential sensor that lives in a provider (`claude:auto-mode-classifier`); resolves an open question of principle 6 | S |
| Time to first useful session | smoke, bootstrap | the bootstrap smoke test prints elapsed seconds; `bootstrap` ends with the minutes of manual steps remaining; resolves an open question of principle 2 without telemetry | S |

## Tranche P1: core developer wins

Guides and sensors every discipline hits daily, mostly inside `core`, plus the first new
bundle. **Status: planned.**

| Item | Where | Components | Effort | Who benefits |
|---|---|---|---|---|
| Git hygiene | `core` rule + guard `31-git-hygiene` | deny `git add` of credential files (`.env*`, keys, kubeconfig); deny a staged hunk matching a secret shape; ask a staged file above `core.max_staged_kb` (default 5120); ask `--no-verify`, remote branch delete, `checkout -- .`/`restore .`, `stash drop|clear`, `filter-branch`, `reflog expire`; deny credentialed remote URLs; `git clean -n` passes. Needs the git stub to answer staged-file queries | M | all |
| Shell hygiene | `core` rule + guard `35-shell-hygiene` | ask on a download piped to a shell, on `sudo`/`doas` (`core.sudo_decision = ask|pass`), on recursive removal outside the checkout and the scratch dir, on `chmod -R 777`; regenerable local artefacts (`node_modules`, `.venv`, `dist`, `target`) pass | S | all |
| `run-checks` skill | `core/skills/run-checks` | one `ci-facts.sh` extracted from the two preflights (GitLab CI and Actions parsing, cost heuristic) plus local-runner discovery (Makefile targets, `package.json` scripts, `pyproject.toml` tools, pre-commit, go, cargo, tox, nox); runs only what CI lacks, diff-scoped; never invents a command | M | app, data, platform |
| `code-reviewer` standards | `core/agents/code-reviewer.md` | reads the first existing of `core.review.standards_files` (CONTRIBUTING, coding-standards docs, formatter configs; orgs add their own path) and reviews against it; fixed output contract (`Verdict`, findings as severity · path:line · rule · fix) reused by the review skills | S | all |
| `worktree` skill + CLI | `core/skills/worktree` | `worktree add|ls|gc|status`; layout `core.worktree_path_tmpl` (default `../{repo}_{branch}`, the convention `work-ticket` already uses); `gc` removes only clean worktrees whose branch is merged or whose upstream is gone and prints the commands for dirty ones; guard rows in `31-git-hygiene` ask on `worktree remove --force`, `branch -D` and `rm -rf` of a listed worktree | S/M | anyone running subagents or parallel branches |
| `work-ticket` test suite | `ticket-workflow` | stub-and-golden suite for `repo-facts.sh`, the preflights and the facts scripts (richer `gh`/`glab` stubs, CI fixtures, with and without PyYAML) | M | the bundle's own stability |
| `gdoc` CLI suite | `gdoc` | `GDOC_DRY_RUN=1` prints request shapes; fixture-routed HTTP; goldens for id parsing, auth status, host allow-list, provenance stamps, drafts without send | M | docs-heavy roles |
| Jira Cloud | `jira` | `jira.kind = "cloud"` implemented in `jira.py`: Basic auth from the token file, `/rest/api/2/search/jql`, `accountId` users, plain text (never ADF); MCP env form; manual step variant | M | every Jira Cloud org |
| Session banner | engine + `core/hooks/session-start.sh` | provider hooks gain an `events` list and extra hook scripts; Claude registers `SessionStart`; the script is offline, under three seconds, and prints version, bundles, drift count, guard tier, pending manual steps and the date of the last report | M | all |
| `harness report` | engine + core manual step | drift, offline doctor, pending steps and provider versions written to `~/.local/state/harness/report/latest.md`; manual step `schedule-report` with crontab and launchd snippets; doctor warns when the report is older than `core.report_max_age_days` | M | platform teams running an org instance |
| Profiles | `profiles/` | `app-dev`, `sre`, `data-eng`; drop unverified providers from `platform-engineer` until verified | S | onboarding by discipline |
| **`ci` bundle** | `bundles/ci` (`scm`, read-only; `any_of` gitlab or github) | CLI `ci runs|jobs|log|why|compare|lint|local-jobs` with bounded, redacted logs; agent `ci-triage` (investigate: root cause and the fix location, never a rerun); guard `55-ci` asks on `glab ci retry|cancel|run|trigger|delete` and on raw log reads not piped through the redactor; config `ci.log_tail`, `ci.redact_extra_re`, `ci.flaky_re` | L | everyone who waits on pipelines |
| Shared redactor | `core/lib/redact.py` | one token-shape list (PATs, cloud keys, JWTs, private-key blocks, URL userinfo, values under secret-looking keys) inlined into `k8s`, `ci` and later CLIs with the existing `sync_inline.py` markers | S | every CLI that prints logs |

## Tranche P2: breadth

Workflow skills on the SCM bundles, tooling for bundle authors, and four new bundles whose
only dependency is a tool the developer already has. **Status: planned.**

| Item | Where | Components | Effort | Who benefits |
|---|---|---|---|---|
| `/review-mr`, `/review-pr` | `gitlab/skills/review-mr`, `github/skills/review-pr` | fetch the diff, spawn `code-reviewer`, post one comment (promptless on agent-labelled MRs/PRs, the guard asks on human ones); never approve or request changes, a `Verdict` line in the comment instead | S each | reviewers, maintainers |
| Scaffolder | engine `harness new bundle|skill|agent` | writes a manifest with `[taxonomy]` and `[harness]` skeletons, `stability = "experimental"`, rule and guard templates with a `# rule:` comment that states an alternative, test row and `tests/run.sh` boilerplate, the docs page; refuses reserved and colliding names | M | contributors, org platform teams |
| Skill-trigger eval | engine `harness test skill-triggers` + lint `skill-triggers` | per skill `tests/triggers.toml` (`should`, `should_not` prompts); deterministic keyword coverage of the expanded description; reports recall, false positives and cross-skill ambiguity | M | skill authors |
| Fork PR provenance | `github` | a fork PR authored by `github.login` whose body carries `<!-- agent-provenance: agent-* -->` is treated as agent-labelled (edits promptless); other fork PRs keep asking | S/M | OSS contributors |
| k8s v2 | `k8s` CLI | `images` (untagged, undigested, off-registry images, `k8s.registries_allow_re`), `rbac` (cluster-admin to service accounts, wildcards, secrets access), `deprecations` (API versions removed within two minors); all reads, no new guard rows | S/M each | SRE, security, platform |
| Provider verification | `docs/runbooks/verify-provider.md`, lint `provider-verified`, smoke `provider-render.sh` | a human protocol per provider (install, render into a temp home, try one deny and one ask), a render-and-parse smoke, a lint warning when a profile ships a provider whose README says "not yet verified" | S code, M human time | multi-provider orgs |
| Stack status | `ticket-workflow` | read-only `stack-status.sh`: part, target, state, needs-rebase, merged parts whose worktree still exists | S | stacked-MR users |
| **`secrets` bundle** | `bundles/secrets` (`base`, read-only; guard `22`) | deny `sops -d`, `age -d`, `gpg -d` to stdout and `vault kv get`, `op read`, `pass show`; ask plaintext written to disk and Vault mutations; deny reading key material; `secrets keys FILE` (names and lengths), `secrets redact`, `secrets scan [--staged] [--deep]` (optional pinned `gitleaks`), `secrets status`; `exec-env`/`op run` forms stay allowed | S/M | all |
| **`toolchain` bundle** | `bundles/toolchain` (`code`, local; guard `38`) | ask `pip install` outside a venv, global installs (`npm -g`, `cargo install`, `go install @latest`, allow-list `toolchain.allow_global_re`), unpinned git or URL dependencies; `toolchain detect|audit|outdated` using each ecosystem's own auditor, optional pinned `osv-scanner`; `/audit-deps` | S/M | all |
| **`containers` bundle** | `bundles/containers` (`infrastructure`, local; guard `36`) | ask registry pushes, `system prune`, `volume rm`, `compose down -v`, `--privileged`, `--pid=host`, docker-socket mounts, remote engines matching `containers.remote_re`; deny `inspect` of env, `exec … env` and passwords on the `docker login` command line; `containers ps|inspect|env|logs|images|disk|compose status` (redacted); local build/run/exec/logs stay promptless | S/M | app, data, platform |
| **`release` bundle** | `bundles/release` (`scm`, local; guard `45`) | ask tag pushes and `npm|twine|cargo|gem|poetry publish`; deny moving or deleting a tag; `/cut-release [patch|minor|major]` stops at the release PR and prints the tag commands; CLI `release next|notes|check|changelog lint|tags`; first use of the `template` guide kind; flips the core row `git push --tags` from pass to ask, stated in the PR | M | release engineers, maintainers |

## Tranche P3: reach

Bundles for infrastructure, data and operations surfaces, and the digest. Each applies the
`k8s` model: an explicit target on every call, a `[PROD]` flag from a `prod_re` key, reads
free, mutations handed to the human, secret values never printed. **Status: planned.**

| Item | Where | Components | Effort | Who benefits |
|---|---|---|---|---|
| k8s `diff` | `k8s` CLI | live object vs last-applied vs the owning ArgoCD application, normalised; pointer into the GitOps root | M | GitOps operators |
| **`cloud` bundle** | `bundles/cloud` (`infrastructure`, read-only; guard `27`) | deny credential printing (`aws configure export-credentials`, `gcloud auth print-access-token`, `az account get-access-token`, secret-manager reads not piped through the redactor); deny switching the shared default profile, project or subscription; ask mutating verbs with `[PROD]`; `cloud whoami|accounts|redact|cost`; `aws eks describe-*` is a plain read here (k8s stays Kubernetes-API-only) | M | SRE, platform, data |
| **`iac` bundle** | `bundles/iac` (`infrastructure`, read-only; guard `26`) | deny `terraform state pull|show` and `output -json` unless redacted, deny reading state files; ask apply, destroy, import, `state rm|mv`, `force-unlock`, `pulumi up|destroy|refresh`, `cdk deploy`, `ansible-playbook` without `--check`; `iac plan-summary|state-ls|redact|drift`; agent `iac-reviewer` (review: blast radius, destroys, IAM changes) | M | infra, platform, data |
| **`db` bundle** | `bundles/db` (`infrastructure`, read-only; guard `37`) | read-only sessions by construction (`default_transaction_read_only`, `SET SESSION TRANSACTION READ ONLY`, `sqlite3 -readonly`); ask writing SQL and `FLUSHALL`-class commands, interactive prod sessions, dumps to stdout; deny passwords on the command line and reading `~/.pgpass`-class files; `db targets|query|schema|explain|stats|redact`; `db.targets` entries have no password field | M | app, data, QA |
| **`hosts` bundle** | `bundles/hosts` (`infrastructure`, read-only; guard `82`) | ask `ssh HOST <mutating command>`, interactive sessions, tunnels, uploads, `ssh-copy-id`; deny `StrictHostKeyChecking=no` and copying private keys; `hosts ls|check|facts|logs` reading `~/.ssh/config` internally (aliases, never keys) | S | infra, platform, QA |
| **`digest` bundle** | `bundles/digest` (`delivery`, read-only) | skill and CLI `standup [--since 24h]`: merged MRs/PRs and commits, open MRs/PRs and review requests, assigned tickets, failing pipelines (via `ci`), unread mail subjects (via `gdoc`); degrades per missing CLI; drafts only, never posts or sends | M | everyone with a standup |
| `/draft-release-notes` | `core/skills/draft-release-notes` | Keep-a-Changelog section from `git log <last tag>..HEAD`, grouped by conventional-commit type or MR/PR title; never tags or creates a release | S/M | maintainers |
| Status line | `providers/claude`, `core/bin` | opt-in `providers.claude.status_line`; model, branch, guard tier, drift count; never takes over a user's own `statusLine` | S | cosmetic |
| GitHub Projects reads | `github/permissions.toml`, `issue-facts.sh` | allow `gh project list|view|item-list|field-list`; board and status in issue facts; `item-add` stays an ask | S | GitHub-only teams |

## Engine and lint backlog

Cross-tranche items that make the hub easier to maintain and to extend.

- Lint rules not in P0: `provider-verified`, `skill-triggers`, `tests-boilerplate` (every
  `bundles/*/tests/run.sh` is identical today; introduce a template the scaffolder copies).
- `skill_fragments`: keep the mechanism, repurpose it for org overlays
  (`local/bundles/<org>/skill-fragments/<public-skill>/references/…`) and say so in ARCHITECTURE
  §3 and the self-host runbook. Public bundles keep SCM- or tracker-specific text as references
  inside the owning skill, because a fragment is silently not rendered when its bundle is
  inactive, which leaves dangling references.
- Provider hooks beyond `PreToolUse` (needed by the session banner): `events` list and
  optional extra hook scripts per bundle, registered only on providers that declare the event.
- Config keys this roadmap introduces, all with defaults and documentation-value examples:
  `gitlab.mr_title_re`, `github.pr_title_forbid_re`, `core.max_staged_kb`,
  `core.secret_shapes_extra_re`, `core.sudo_decision`, `core.review.standards_files`,
  `core.review.max_diff_kb`, `core.checks.extra_patterns`, `core.worktree_path_tmpl`,
  `core.session_banner`, `core.report_max_age_days`, `providers.claude.status_line`,
  `ci.log_tail`, `ci.redact_extra_re`, `ci.flaky_re`, `k8s.registries_allow_re`,
  `secrets.extra_token_shapes_re`, `secrets.scan_exclude_re`, `toolchain.venv_markers`,
  `toolchain.allow_global_re`, `containers.remote_re`, `containers.prod_re`,
  `containers.registries_re`, `release.changelog`, `release.version_file`,
  `release.tag_prefix`, `release.tag_re`, `release.conventional_commits`, `cloud.prod_re`,
  `cloud.accounts`, `iac.prod_re`, `iac.stateful_types_re`, `db.prod_re`, `db.targets`,
  `db.row_limit`, `hosts.prod_re`, `hosts.inventory`, `hosts.ssh_timeout`, `digest.repos`,
  `digest.since`, `digest.mail`. Every env name a guard section reads must carry a prefix the
  guard accepts (`HARNESS_`, `K8S_`, …; lint `env-provides` enforces this).

## Rejected or deferred

| Candidate | Decision | Reason |
|---|---|---|
| Plugin or marketplace packaging | rejected | a second distribution channel conflicts with principle 5 (one git bundle); revisit only if a provider stops reading home-directory skills |
| Telemetry, dashboards, usage reports | rejected | principle 2 rules out features whose audience is not the developer |
| Removing `skill_fragments` | rejected | kept for org overlays (see above) |
| A shared review bundle for `/review-mr` and `/review-pr` | rejected | the shared part is already the core `code-reviewer` agent; two thin skills cost less than a dispatch layer |
| A separate stacked-MR skill | rejected | `work-ticket` owns delivery; a read-only `stack-status.sh` suffices |
| `/standup` posting to chat or sending mail | rejected | drafts only; humans send (the gdoc bundle never sends) |
| `/standup` inside `ticket-workflow` | rejected | it spans more sources than that bundle's `any_of` allows and must degrade per missing CLI |
| EKS/GKE/AKS reads inside `k8s` | rejected | `k8s` is Kubernetes-API-only by its own contract and never reads kubeconfig; the `cloud` bundle supplies them |
| Per-language toolchain bundles | rejected | one `toolchain` bundle; splitting multiplies manifests without new sensors |
| Observability bundle (Prometheus, Grafana, Loki) | deferred | `k8s promql` covers the Kubernetes case; a standalone bundle needs per-backend auth and URL guards for a narrower audience |
| SAST wrapper | reshaped | `semgrep` needs pip (principle 1); `secrets scan` and `code-reviewer` cover the lightweight cases; CI keeps the thorough scan |
| SBOM and licence policy | reshaped | ecosystem auditors plus optional `osv-scanner` in `toolchain audit`; licence policy is org-specific and belongs in an org bundle |
| ADR / runbook documentation skill | deferred | its only sensor would be a lint; revisit as `adr` after `release` ships the `template` guide kind |
| Asking on edits to CI files | rejected | user-level friction for every developer editing CI legitimately; the skill rule stays a guide with a coverage note |
| Denying `sudo` | rejected | deny only what must never happen; `sudo` asks, and `core.sudo_decision` can relax it |
| Network calls in the session banner | rejected | offline, under three seconds; `harness report` does the slow work on a schedule |
| Jira Cloud tokens in `harness.toml` | rejected | tokens stay in the tool's own file; config validation already rejects secret-shaped values |
| Live product-driven provider verification in CI | rejected | needs a running agent; verification is a documented human protocol plus a render-and-shim smoke |

## Cross-cutting, built once

- The shared redactor in `core/lib/redact.py` (P1) before any new CLI that prints logs.
- A `tests/run.sh` template for bundles, copied by the scaffolder.
- Every new bundle ships `docs/bundles/<name>.md` with a Troubleshooting section, a README
  table row, a CHANGELOG entry (plus `### Taxonomy` for a new domain value) and, where it
  changes a decision or a key, a **Migration** paragraph.
- Row changes to existing specifications are called out in the PR: `release` flips the core
  row `git push --tags`; `iac` and `cloud` must keep every `pass` row in the k8s suite green.
- Heuristic verb lists (cloud, db, hosts) will produce false asks at first; budget a steering
  pass after two weeks of use rather than loosening the rules up front.
