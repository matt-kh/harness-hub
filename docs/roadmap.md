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

Eight public bundles cover source control (`github`, `gitlab`), one tracker (`jira`), the
ticket-to-merge workflow (`ticket-workflow`), stacked MRs/PRs on free tiers (`stack`),
Kubernetes (`k8s`), Google Workspace (`gdoc`)
and the conventions, credentials and git rules every developer needs (`core`). That is the
surface of a platform engineer. Application, data, QA, security and release engineers also
run containers, package managers, databases, cloud CLIs, infrastructure-as-code, pipelines
and remote hosts from the same terminal, and the agent sees none of it today.

Site reliability work has the same gap: `k8s` reads the Kubernetes API only, so the agent sees
no signals outside the cluster (metrics, logs, traces and alerts in an observability backend),
has no incident workflow spanning cluster, CI and signals, and produces no reliability
artefacts (SLOs, alert rules as code, backup and DR posture). The [SRE track](#sre-track)
plans that surface.

The bundles also name their own gaps in `[harness].coverage_note`: `work-ticket` has no
test suite; MRs/PRs created without `-t` are not title-checked; GitHub fork PR edits always
ask. One engine mechanism has no real user: `skill_fragments`.

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
| `32` | `32-obs` | obs | observability backends: after `25`–`27` so the k8s, iac and cloud credential denies win |
| `33` | `33-slo` | slo | reserved; no section in v1 (nothing it wraps mutates) |
| `34` | `34-incident` | incident | reserved; no section in v1 (its writes are sensed by gdoc `80`, jira `70`, k8s `25` and the closing-keyword sections) |
| `35` | `35-shell-hygiene` | core | shell-level hazards (pipe to shell, privilege escalation, destructive removal outside the checkout) |
| `36` | `36-containers` | containers | local-workstation tooling |
| `37` | `37-db` | db | local and remote data tooling |
| `38` | `38-toolchain` | toolchain | package managers |
| `45` | `45-release` | release | tags and publication; after the closing-keyword sections, before the SCM CLIs |
| `55` | `55-ci` | ci | between `50-gitlab` and `60-github`; adds only the rows those two lack |
| `82` | `82-hosts` | hosts | miscellaneous band, with `80-gdoc` |

Free after this table: `15`, `39`, `42`–`44`, `46`–`49`, `85`.

## Proposed taxonomy values

Three new `domain` values, added through the procedure in
[taxonomy](reference/taxonomy.md#adding-a-value) when the first bundle using them lands:

| Value | Meaning | Used by |
|---|---|---|
| `infrastructure` | cloud accounts, hosts, containers, databases and IaC outside Kubernetes | cloud, iac, containers, db, hosts |
| `code` | the checkout itself: toolchains, dependencies, generated artefacts | toolchain |
| `operations` | running systems: signals, incidents, reliability targets | obs, incident, slo |

Everything else reuses existing values: `ci`, `release` and the worktree work are `scm`
(pipelines, tags and worktrees live on or for the source host); `secrets` is `base` (its
meaning already includes credentials); `digest` is `delivery`. `db` stays under
`infrastructure` until a second data bundle exists ("a value exists only while a component
uses it"). No new `function` or `posture` values are needed.

## Tranche P0: honesty and cheap sensors

Close the declared gaps and add the lint rules that would have caught them. No new
dependencies, no new bundles. **Status: shipped**; see CHANGELOG
[`[Unreleased]`](../CHANGELOG.md#unreleased).

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
| Jira Cloud | `jira` | `jira.kind = "cloud"` implemented in `jira.py`: Basic auth from the token file, `/rest/api/2/search/jql`, `accountId` users, plain text (never ADF); MCP env form; manual step variant | M | every Jira Cloud org |
| Session banner | engine + `core/hooks/session-start.sh` | provider hooks gain an `events` list and extra hook scripts; Claude registers `SessionStart`; the script is offline, under three seconds, and prints version, bundles, drift count, guard tier, pending manual steps and the date of the last report | M | all |
| `harness report` | engine + core manual step | drift, offline doctor, pending steps and provider versions written to `~/.local/state/harness/report/latest.md`; manual step `schedule-report` with crontab and launchd snippets; doctor warns when the report is older than `core.report_max_age_days` | M | platform teams running an org instance |
| Profiles | `profiles/` | `app-dev`, `sre`, `data-eng`; drop unverified providers from `platform-engineer` until verified | S | onboarding by discipline |
| **`ci` bundle** | `bundles/ci` (`scm`, read-only; `any_of` gitlab or github) | CLI `ci runs|jobs|log|why|compare|lint|local-jobs` with bounded, redacted logs; agent `ci-triage` (investigate: root cause and the fix location, never a rerun); guard `55-ci` asks on `glab ci retry|cancel|run|trigger|delete` and on raw log reads not piped through the redactor; config `ci.log_tail`, `ci.redact_extra_re`, `ci.flaky_re` | L | everyone who waits on pipelines |
| Shared redactor | `core/lib/redact.py` | **shipped**: the `redact` block (values under secret-looking keys, Secret data as sizes, AWS key ids, JWTs, private-key blocks, URL userinfo, plus a caller's `extra_re`), inlined into `k8s` with `k8s.redact_extra_re`; `ci` and later CLIs inline the same block (principle 10) | S | every CLI that prints logs |

## SRE track

Make the harness serve site reliability work end to end: **architecting** (ADRs, design
reviews of charts, overlays and IaC, capacity, DR and SLO design), **developing** (alert
rules, dashboards, SLOs and runbooks as code; CI triage) and **operating** (incident triage
across cluster, signals, pipelines and promotions; postmortems; hygiene checks). Every piece
keeps the governance `k8s` already has: reads free, mutations handed to the human with their
blast radius, a `[PROD]` banner from a `prod_re` key, secret values never printed, writes
promptless only on `agent-*` artefacts, and deterministic artefacts rendered by scripts with
goldens ([principle 9](../principles/09-deterministic-by-construction.md)). Three new bundles
(`obs`, `incident`, `slo`), the new domain `operations`, three pulled-forward bundles and
extensions to `k8s` and `core`. **Status: in progress.**

| Item | Kind | Domain / posture / function | Prefix | Slice |
|---|---|---|---|---|
| `core/lib/redact.py` block | core extension | base | — | S0a |
| credential paths from `[requires.secrets]` → guard | engine + core `20` | base | `20` | S0b |
| **`obs`** | new bundle | operations / read-only / client (+ `obs-triage` investigate) | `32` | S2 |
| `k8s` v2a: `backups`, `audit` PDB/HPA + `--manifests`, `chart-reviewer`, auditor steps | extension | kubernetes | — | S3 |
| `/draft-adr` + `render-adr.py` | core skill | base / local / workflow | — | S4a |
| `infra-architect` ends with an ADR JSON block | k8s text | kubernetes / plan | — | S4b |
| `ci` (P1 spec + `--json` UTC timestamps + shared contract) | pull-forward | scm / read-only | `55` | S1 |
| **`incident`** | new bundle | operations / label-gated / workflow | `34` (reserved) | S5 |
| **`slo`** | new bundle | operations / read-only / client (+ `sre-reviewer`, `dr-auditor` review) | `33` (reserved) | S6 |
| `iac` (P3 spec + `plan-summary` for `pulumi preview --json`) | pull-forward | infrastructure (first use) | `26` | S7 |
| `cloud` (P3 spec + `cloud backups`, `cloud eks`) | pull-forward | infrastructure | `27` | S8 |
| `profiles/sre.toml` | profile | — | — | S9 |
| `k8s` v2b: `rbac`, `deprecations`, `images`, `diff` | roadmap items (P2, P3) | kubernetes | — | later |
| org overlay (`local/bundles/<org>`) | private | — | — | after S2, S5, S6 |

### `obs` bundle

`depends_on = ["core"]`, `recommends = ["k8s", "ci"]`, stability `experimental`; taxonomy
operations / read-only / client, agent `obs-triage` investigate. Adapters `signoz` (first),
`prometheus` (Thanos, Mimir and VictoriaMetrics compatible) and `grafana`; one class each,
read endpoints only. Banner on stderr `backend=<name> kind=<kind> url=<host> [PROD]`; exit
`0` clean, `1` findings, `2` access error, `3` unsupported by this backend kind.

```
obs backends [--probe]                         name, kind, host, key file state, reachability
obs query 'PROMQL' [--range 1h --step 60s]     metrics table
obs logs 'FILTER' [--service S] [--limit 200]  bounded, redacted log lines
obs traces --service S [--error] [--min-duration 500ms]
obs trace ID [--depth 3]                       span tree, attributes redacted
obs services                                   RED per service over --since
obs alerts [--firing] [--rules]
obs dashboards [--export UID FILE.json]        the only local write
obs lint FILE...                               alert rules and dashboards as code
obs redact                                     stdin filter (the core redact block)
```

- Agent `obs-triage`: logs, traces and alerts for one service and window in its own context;
  output is the shared investigate contract of `k8s-triage`; never raw `curl`, never silences.
- Guard `32-obs`:

  ```
  # never-yields: <reader> ~/.config/obs/* -> deny : API key files; run 'obs backends' instead
  # rule: curl|wget|http|xh ... -H '<auth header>: <literal>' | ?api_key=<literal> -> deny : API key on the command line; use the obs CLI
  # rule: curl|wget|http|xh <host matching OBS_HOSTS_RE> -> ask : raw backend access; use the obs CLI (bounded, redacted, read-only)
  # rule: amtool silence add|expire|import | amtool alert add -> ask : changes alert state; change the alert rule in the repo instead
  # rule: logcli query --tail|-f -> ask : never returns; pass --since and --limit instead
  # rule: grafana-cli admin|plugins install|remove -> ask : Grafana admin mutation; change the chart values instead
  ```

- Config (`OBS_`): `obs.default = ""`, `obs.backends = []` (`{ name, kind, url, auth_file =
  "~/.config/obs/<name>.key" }`, e.g. `https://signoz.example.com`), `obs.hosts_re = ""`
  (empty disables the host rows), `obs.prod_re` (default as `k8s.prod_re`), `obs.log_tail =
  200`, `obs.max_bytes = 65536`, `obs.redact_extra_re = ""`. Keys: `~/.config/obs/*.key`,
  Viewer role, mode 0600, a rotation runbook.
- Sensors: guard rows, doctor (`obs-cli`, `obs-backends`, `obs-keys`, `obs-hosts-re`,
  `obs-reach`), goldens per adapter driven by the HTTP fixture fake, and an `OBS_DRY_RUN=1`
  request log the suite checks for read endpoints only (POST-as-read is invisible to the
  guard, so the CLI is the trust boundary).
- Not implemented: any write to a backend (alerts, dashboards, silences, keys), `--follow`,
  native Loki/Tempo adapters in v1 (reach them via `grafana`), Elastic/Datadog/New Relic,
  reading kubeconfig to find in-cluster services.
- Seams: in-cluster Prometheus without an ingress stays `k8s promql` (`obs` never proxies
  through the apiserver); dashboards and alert rules change as files in the owning repo via
  MR/PR (`obs dashboards --export` → edit → `obs lint`).

### `incident` bundle

`depends_on = ["core"]`, `recommends = ["k8s", "ci", "obs", "gdoc", "ticket-workflow"]` (each
adds a source or a sink; the skill names what is missing). Taxonomy operations / label-gated /
workflow; `skills/triage` investigate, `skills/runbook` local, `bin/incident` read-only.

```
incident timeline --out F [--since] [--note TS text]... [--from k8s-events.json --from ci-runs.json --from obs-alerts.json]
incident postmortem META.json timeline.json [--template F] [--out DIR/YYYY-MM-DD-slug.md]
incident runbook new NAME [--service S] [--dir D]
incident runbook lint PATH...
incident summary META.json timeline.json
```

- Skills: `/triage <service|symptom> [--env E] [--since 6h]` fans out to `k8s-triage`,
  `ci-triage` and `obs-triage` in parallel, merges a UTC timeline (`--now` is an input, never
  the clock) and reports Summary · Timeline · Evidence · Root cause (confidence) · Remediation
  for the human (in `[PROD]` the GitOps revert MR first) · Not verified · Next;
  `/postmortem` (the model fills `META.json`, the CLI renders a blameless postmortem with
  TTD/TTM/TTR; sink is a repo file via MR or `gdoc create`); `/runbook new|lint`.
- Guard: none in v1 (prefix `34` reserved); its writes are sensed by `80-gdoc`, `70-jira`,
  `25-k8s-rules` and the closing-keyword sections, stated in `coverage_note`.
- Config (`INCIDENT_`): `runbook_dirs = ["docs/runbooks", "runbooks"]`,
  `runbook_max_age_days = 180`, `postmortem_dir = "docs/incidents"`, `postmortem_folder = ""`,
  `severity_levels`, `timeline_since = "6h"`, `tracker = { project = "PROJ", type = "Task",
  labels = [] }`.
- Sensors: renderer goldens (timeline, postmortem, runbook, summary), `runbook lint` (front
  matter, required sections, tagged bash blocks, `last_reviewed` age, resolvable links),
  doctor `incident-cli`, `incident-sinks`, `incident-sources`; first users of the `template`
  guide kind.
- Not implemented: paging and on-call tools, chat or status-page posting, "declare incident",
  ticket transitions (action items become `/create-ticket` drafts), running remediations,
  silencing alerts.

### `slo` bundle

`depends_on = ["core", "obs"]` (`slo check` shells out to `obs query --json`, the only data
path), `recommends = ["k8s", "cloud", "db"]`. Taxonomy operations / read-only / client; agents
`sre-reviewer` and `dr-auditor` (review).

```
slo lint DIR|FILE...                        OpenSLO-shaped definitions: keys, objective, window, SLI kind, alerting, runbook link
slo check [--backend B] [--now TS]          SLI, error budget left, burn rates 1h/6h/3d, page|ticket|ok
slo rules FILE --format prometheus|signoz [--out F]   multiwindow multi-burn rules; output passes obs lint
slo report DIR [--month YYYY-MM]            error-budget report skeleton
```

- `sre-reviewer`: SLO definitions and alert rules (objective realism, symptom vs cause,
  missing `for`/severity/runbook, duplicates, measurability) in the `code-reviewer` contract.
  `dr-auditor`: backup and DR posture (declared RPO/RTO vs evidenced mechanism, restore test,
  retention, off-site, encryption, job monitoring) from `k8s backups`, `cloud backups`,
  `db targets` and repo greps, each optional; "no backup mechanism evidenced" is Critical in
  `[PROD]`. References: `slo-design.md`, `alert-quality.md`, `backup-dr.md`, `capacity-plan.md`.
- Guard: none in v1 (prefix `33` reserved; nothing it wraps mutates).
- Config (`SLO_`): `slo.dir = "slo"`, `slo.default_window = "30d"`, `slo.burn_windows =
  ["1h/5m", "6h/30m", "3d/6h"]`, `slo.page_threshold = 14.4`, `slo.ticket_threshold = 1`.
- Sensors: `slo lint`, goldens for `check`, `rules` and `report`, exit `1` burning, `2`
  backend error, "unmeasurable" when a query returns no series.
- Not implemented: writing rules to a backend, SLO platforms (Sloth, Pyrra, Nobl9),
  auto-tuned objectives, paging.

### Pull-forward order

For this track, `ci` → `iac` → `cloud` are built ahead of their tranches; their tranche
membership and specifications above are unchanged, the track only adds:

- **`ci`** (S1): `ci runs|jobs --json` with UTC ISO timestamps as a timeline source;
  `ci-triage` uses the shared investigate contract; `ci log` inlines the core redact block.
  Pipelines are the first thing an incident has to rule out.
- **`iac`** (S7): `iac plan-summary` parses `pulumi preview --json` and `terraform show
  -json` (counts, stateful resources via `iac.stateful_types_re`, IAM diff, network widening,
  blast-radius line); `iac-reviewer` is the architect's second reviewer next to
  `chart-reviewer`. First use of domain `infrastructure`; every k8s `pass` row stays green.
- **`cloud`** (S8): adds `cloud backups` (database retention and snapshot age, bucket
  versioning and lifecycle, volume snapshot policies) and `cloud eks` (plain reads), the
  sources `dr-auditor` needs outside the cluster.

`secrets`, `db`, `hosts`, `containers` and `release` stay where they are.

### Extensions

- **`k8s` v2a** (S3): `k8s backups --context C [--ns NS]` (Velero CRDs if present,
  `VolumeSnapshot(Class)`, dump CronJobs, PVCs by StorageClass and reclaim policy; exit `1`
  when a namespace with PVCs has no evidenced backup); `k8s audit` gains PDB/HPA findings and
  `--manifests FILE...` for rendered manifests; `k8s-auditor` steps for PDB/HPA and backups;
  agent `chart-reviewer` (review: `helm lint`, `helm template … | k8s audit --manifests -`,
  server dry-run against a non-prod context, values schema, probes, resources, PDB,
  securityContext, image pinning; `code-reviewer` contract); `references/observability.md`
  points out-of-cluster questions to `obs`.
- **`core`** (S4a): `/draft-adr` with `scripts/render-adr.py MODEL.json [--dir docs/adr]
  [--template FILE]` (MADR-shaped, numbered from the directory, `--check` lints status
  vocabulary and supersedes links; a repository's own template, adr-tools or log4brains is
  used as input or yielded to). No bin link. The `code-reviewer` output contract (P1) lands
  first or with `chart-reviewer`.
- **`k8s`** (S4b): `infra-architect` ends with a fenced `adr` JSON block in the `/draft-adr`
  model shape and offers `/draft-adr`.
- **`profiles/sre.toml`** (S9): `bundles = ["core", "gitlab", "github", "jira",
  "ticket-workflow", "k8s", "gdoc", "ci", "obs", "incident", "slo", "iac", "cloud"]`,
  `providers = ["claude"]`.

### Org overlay

Organisation values never enter the public bundles. An org overlay sets them in
`local/harness.toml` (`[obs]` backends, `hosts_re` and `prod_re`; `[incident]` runbook and
postmortem paths and tracker project; `[slo]` `dir`; `[cloud]`; `[iac]` `prod_re`) and in
`local/bundles/<org>/skill-fragments/<obs|incident|slo>/references/org.md`: backend per
cluster or environment and what is instrumented, escalation contacts and severity
definitions, where runbooks, ADRs and postmortems live, candidate SLIs and declared RPO/RTO per
data store. The org notes rule gains a short SRE subsection pointing at them.

### Delivery

| Slice | Branch | Scope | Companions | Depends on |
|---|---|---|---|---|
| **A** | `sre-track` | this section, prefixes `32`–`34`, `operations`, rewritten deferred rows | CHANGELOG `### Docs` | — |
| **S0a** | `core-redact-block` | `bundles/core/lib/redact.py` inlined into `k8s` via `sync_inline.py`; k8s redact goldens byte-identical; `k8s.redact_extra_re` | `no-rows: refactor`; CHANGELOG; `sync_inline.py --check` | — |
| **S2** | `obs-bundle` | the `obs` bundle; taxonomy `operations` (schemas, facets, docs); guard `32`; docs page, README row, key rotation runbook | rows (`tr`) per deny/ask; CHANGELOG incl. `### Taxonomy`; README; docs regen | S0a |
| S0b | `guard-cred-paths-from-manifests` | engine collects `[requires.secrets].where` into the guard env; one rule in `20-credentials` | rows; CHANGELOG; hook-policy regen | — |
| S1 | `ci-bundle` | the P1 `ci` spec plus the additions above | rows (`55`); CHANGELOG; docs page; README; ARCHITECTURE §3 | S0a |
| S3 | `k8s-v2a-backups-audit` | `k8s` v2a | CHANGELOG; goldens; docs regen | S0a |
| S4a | `core-draft-adr` | `/draft-adr` | CHANGELOG; docs page; this page | — |
| S4b | `k8s-architect-adr-shape` | `infra-architect` text | CHANGELOG | S4a |
| S5 | `incident-bundle` | the `incident` bundle | CHANGELOG; docs page; README; this page (`34`) | S1, S2 |
| S6 | `slo-bundle` | the `slo` bundle | CHANGELOG; docs page; README; this page (`33`) | S2 (S3 for the k8s source) |
| S7 | `iac-bundle` | the P3 `iac` spec plus the additions above | rows (`26`); CHANGELOG `### Taxonomy`; docs page; README | S0a |
| S8 | `cloud-bundle` | the P3 `cloud` spec plus the additions above | rows (`27`); CHANGELOG; docs page; README | S0a |
| S9 | `sre-profile` | profile and getting-started row | CHANGELOG; `profile-sane` lint | S1–S8 |

The first delivery is A, S0a and S2. Until the scaffolder lands, each new-bundle PR copies the
`k8s` skeleton (manifest sections, `defaults.toml`, `guard.d/tests.sh` header, `tests/run.sh`,
docs page with Troubleshooting) and adds to the `tests-boilerplate` debt below. Stability is
`experimental` on landing, `beta` once the suite is complete and `stable` after the two-week
steering pass on guard false asks.

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
| Stack status | `stack` | shipped as `stk status` (part, target, state, behind, worktree, merged parts whose worktree still exists) | S | stacked-MR users |
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
  `bundles/*/tests/run.sh` is identical today; introduce a template the scaffolder copies;
  principle 10).
- Follow-up for the shared redactor: `redact_obj` masks values only under secret-looking keys
  and never runs `redact_text` on other string values, so `{"msg": "Authorization: Bearer …"}`
  passes through; make `redact_obj` apply `redact_text` to string values (needs a golden
  review in `k8s` and `obs`). Two `redact_text` limits for the same pass: JSON-quoted keys in
  text log lines (`"password":"…"`) are not matched by the inline rule, and a non-scheme
  multi-word value masks only its first word.
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
  `digest.since`, `digest.mail`, `obs.default`, `obs.backends`, `obs.hosts_re`,
  `obs.prod_re`, `obs.log_tail`, `obs.max_bytes`, `obs.redact_extra_re`,
  `k8s.redact_extra_re`, `incident.runbook_dirs`, `incident.runbook_max_age_days`,
  `incident.postmortem_dir`, `incident.postmortem_folder`, `incident.severity_levels`,
  `incident.timeline_since`, `incident.tracker`, `slo.dir`, `slo.default_window`,
  `slo.burn_windows`, `slo.page_threshold`, `slo.ticket_threshold`, and (shipped) `stack.label`, `stack.push`,
  `stack.update_method`, `stack.leaf_refresh`. Every env name a guard section reads must carry a prefix the
  guard accepts (`HARNESS_`, `K8S_`, `OBS_`, `INCIDENT_`, `SLO_`, …; lint `env-provides` enforces this).

## Rejected or deferred

| Candidate | Decision | Reason |
|---|---|---|
| Plugin or marketplace packaging | rejected | a second distribution channel conflicts with principle 5 (one git bundle); revisit only if a provider stops reading home-directory skills |
| Telemetry, dashboards, usage reports | rejected | principle 2 rules out features whose audience is not the developer |
| Removing `skill_fragments` | rejected | kept for org overlays (see above) |
| A shared review bundle for `/review-mr` and `/review-pr` | rejected | the shared part is already the core `code-reviewer` agent; two thin skills cost less than a dispatch layer |
| A separate stacked-MR *authoring* skill | rejected | `work-ticket` owns delivery (creating the stack); keeping it mergeable is `stk` (stack bundle) |
| Merge train (`stk run`) | deferred (v2 candidate) | humans merge stacks bottom-up today. A free-tier train would emulate GitLab merge trains / GitHub merge queues: one MR/PR at a time, server-side rebase, wait for its pipeline on that head, then arm auto-merge or merge pinned to the tested sha (`--sha`, `--match-head-commit`); a draft was dropped from #18 in favour of stack sync |
| `glab stack` | rejected for now | EXPERIMENTAL in glab 1.115 and marked "not ready for production"; stacks stay work-ticket's `-sub-NN` branches synced by `stk`; revisit when GitLab marks it GA |
| `/standup` posting to chat or sending mail | rejected | drafts only; humans send (the gdoc bundle never sends) |
| `/standup` inside `ticket-workflow` | rejected | it spans more sources than that bundle's `any_of` allows and must degrade per missing CLI |
| EKS/GKE/AKS reads inside `k8s` | rejected | `k8s` is Kubernetes-API-only by its own contract and never reads kubeconfig; the `cloud` bundle supplies them |
| Per-language toolchain bundles | rejected | one `toolchain` bundle; splitting multiplies manifests without new sensors |
| Observability bundle (Prometheus, Grafana, Loki) | un-deferred as `obs` ([SRE track](#sre-track)) | token-by-path, URL-in-config and a host-regex guard row are generic mechanisms, which removes the per-backend objection; the narrower audience is answered by the `sre` profile |
| SAST wrapper | reshaped | `semgrep` needs pip (principle 1); `secrets scan` and `code-reviewer` cover the lightweight cases; CI keeps the thorough scan |
| SBOM and licence policy | reshaped | ecosystem auditors plus optional `osv-scanner` in `toolchain audit`; licence policy is org-specific and belongs in an org bundle |
| ADR / runbook documentation skill | reshaped | `/draft-adr` (core) and `incident runbook` (incident): renderer goldens and a `--check` lint are the sensors, so the dependency on `release` shipping the `template` guide kind is dropped |
| Asking on edits to CI files | rejected | user-level friction for every developer editing CI legitimately; the skill rule stays a guide with a coverage note |
| Denying `sudo` | rejected | deny only what must never happen; `sudo` asks, and `core.sudo_decision` can relax it |
| Network calls in the session banner | rejected | offline, under three seconds; `harness report` does the slow work on a schedule |
| Jira Cloud tokens in `harness.toml` | rejected | tokens stay in the tool's own file; config validation already rejects secret-shaped values |
| Live product-driven provider verification in CI | rejected | needs a running agent; verification is a documented human protocol plus a render-and-shim smoke |

## Cross-cutting, built once

- The shared redactor in `core/lib/redact.py` (P1) before any new CLI that prints logs; it is
  also the first prerequisite of the [SRE track](#sre-track) (slice S0a). **Shipped**: new CLIs
  inline the `redact` block and add a `<bundle>.redact_extra_re` key.
- A `tests/run.sh` template for bundles, copied by the scaffolder.
- Every new bundle ships `docs/bundles/<name>.md` with a Troubleshooting section, a README
  table row, a CHANGELOG entry (plus `### Taxonomy` for a new domain value) and, where it
  changes a decision or a key, a **Migration** paragraph.
- Row changes to existing specifications are called out in the PR: `release` flips the core
  row `git push --tags`; `iac` and `cloud` must keep every `pass` row in the k8s suite green.
- Heuristic verb lists (cloud, db, hosts) will produce false asks at first; budget a steering
  pass after two weeks of use rather than loosening the rules up front.
