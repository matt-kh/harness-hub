---
name: obs
description: >-
  Read-only observability client for SigNoz, Prometheus and Grafana via the `obs` CLI. Use
  when the user mentions an alert, an error spike, latency, a service's RED metrics, logs,
  traces, a trace id, a dashboard, PromQL, SigNoz, Prometheus, Grafana, Loki, alert rules or
  dashboards as code, or asks "why is service X erroring/slow". Never writes to a backend,
  never silences alerts, never prints API keys.
model: {{ core.model_policy.execute }}
---

# Observability (read-only client)

Generic client for the observability backends listed in `obs.backends`.

**Step 0 — repository-level harness (principle 8).** This is a user-level skill. Read the
repository's declaration first:

```bash
harness repo owns obs/skills/obs   # rc 0 = owned (prints why) → stop; rc 1 = carry on
```

If it is owned (by id or by its domain `operations`), or the repository ships its own skill for
the same workflow, this skill yields: say so in one line, name the repository-level skill or
convention, and stop — nothing below runs and nothing is merged. If the repository owns the
*workflow* but not the client, stay available as the plain client underneath it. Never edit
the repository's harness to fit this skill. `harness repo` explains everything the
repository declares and any `.claude/skills|agents` name collisions.

## Tooling

- **`obs` CLI** (this skill's `scripts/obs.py`, on PATH) — the only way to reach a backend. It
  bounds every read, redacts log lines, span attributes and label values, and refuses any
  request outside its read allow-list.
- **`obs-triage` agent** for anything that needs to read a lot (a firing alert, an error spike):
  hand it the service, the window and the backend; it returns a summary, not the dumps.
- **`k8s promql`** (k8s bundle) for an in-cluster Prometheus that has no ingress; `obs` never
  proxies through the Kubernetes API.
- **`promtool check rules` / `promtool test rules`** next to `obs lint` for Prometheus rule files.

```bash
# hook: allow
obs backends [--probe]                                 # ALWAYS first: names, kinds, key status, [PROD]
obs query 'sum(rate(http_server_duration_count[5m])) by (service_name)' --backend B [--range 1h --step 60s]
obs logs "severity_text = 'ERROR'" --service S --backend B --since 15m --limit 100
obs traces --service S --error --min-duration 500ms --backend B --since 30m
obs trace TRACE_ID --depth 4 --backend B
obs services --since 1h --backend B                    # RED per service (signoz)
obs alerts --firing [--rules] --backend B
obs dashboards [--export UID dashboards/UID.json [--force]] --backend B
obs lint rules/*.json dashboards/*.json                # offline
obs redact < file                                      # stdin filter
```

Global flags on every subcommand: `--backend NAME`, `--json|--md`, `--timeout 20`,
`--max-items 50`, `--max-bytes N`, `--since 15m`. A grafana backend needs `--datasource UID`
for `query` (a Prometheus datasource) and `logs` (a Loki datasource).

## Contract & rules

- **Exit codes**: `0` clean · `1` findings (read them; also a usage or query error) · `2` access
  error (401/403, 404 not found, a redirect, a non-JSON answer such as a login page,
  unreachable, timeout, key file missing) · `3` the command does not exist for this backend
  kind (a static decision, never an HTTP status; the message names the alternative). On exit 2
  name the backend and the error line; do not retry other backends hoping one works.
- **404 means not found**: the endpoint is not served by this backend version, or the id you
  passed does not exist. `obs backends --probe` reports a 404 on the version/health endpoint as
  unreachable with a note (the url points at something else).
- **Redirects are never followed.** A 3xx is exit 2 naming the target host; the API key never
  leaves the configured host. Fix `url` in `[[obs.backends]]` (scheme, host, path prefix) —
  never chase the redirect with raw `curl`. A `url` carrying `user:password@` is refused at
  load time: credentials belong in `auth_file`.
- **JSON output stays whole.** Over `--max-bytes`, trailing items of the largest list are
  dropped and the envelope carries `"truncated": {"items_dropped": N, "max_bytes": M}`; say so
  and narrow the query rather than raising the cap by default.
- **Banner** on stderr: `backend=<name> kind=<kind> url=<host> [PROD]`. Quote the backend in
  every answer. `[PROD]` means a remediation is a **suggestion for the human**, with its blast
  radius.
- **Bounded reads.** Always pass `--since`; logs take `--limit` (default `obs.log_tail`), lists
  `--max-items`, output `--max-bytes`. When more is genuinely needed:
  `obs <cmd> --json > "$SCRATCH/x.json"` and `jq` the fields you need. Never paste a log wall.
- **API keys are files, never arguments.** `~/.config/obs/<name>.key`, mode 0600, read by the
  CLI only. Reading them is denied (guard and Read permission); a key written on a command line
  is denied; `obs backends` shows presence and mode.
- **Alert rules, dashboards and silences are code.** Export (`obs dashboards --export`), edit
  the file in the owning repository, `obs lint`, open an MR. `--export` refuses an existing
  file unless `--force` (check `git status` first) and refuses an empty answer. Never write
  them back through an API, never silence an alert: hand `amtool silence add` to the user.
- Guard-hook decisions (the hook wins over `permissions.allow` — do not route around it):

  | Command | Decision | Rationale |
  |---|---|---|
  | `obs <any subcommand>` | `permissions.allow` | read-only by construction |
  | `promtool check\|test`, `amtool alert\|silence query`, `logcli query --since` | allow / pass | reads |
  | `cat\|grep\|cp\|… ~/.config/obs/*`, Read tool on `~/.config/obs/**` | **deny** (never yields) | API key files |
  | `curl\|wget\|http\|xh` (bare or path-qualified, e.g. `/usr/bin/curl`) with a literal `Authorization`, `SIGNOZ-API-KEY` or `X-API-Key` header, or `?api_key=` | **deny** | key on the command line |
  | `curl\|wget\|http\|xh` (bare or path-qualified) to a host matching `OBS_HOSTS_RE` | **ask** | raw backend access — use `obs` |
  | `amtool silence add\|expire\|import`, `amtool alert add` | **ask** | changes alert state |
  | `logcli query --tail\|-f` | **ask** | never returns |
  | `grafana-cli admin`, `grafana-cli plugins install\|remove` | **ask** | Grafana admin mutation |

  `OBS_HOSTS_RE` (`obs.hosts_re`) is a POSIX ERE: the guard applies it with `grep -E`. Write
  `[0-9]`, `[A-Za-z0-9_]`, `[[:space:]]`, never `\d`, `\w`, `\s` or `(?…)`; `obs backends`
  checks it with `grep -E` and flags Python-only syntax and any host where the two disagree.

## Procedure

**Step 1 — Orient.** Never assume which backend.

```bash
# hook: allow
obs backends --md            # add --probe when a backend may be down or its key expired
```

**Step 2 — Signal.** Start from what the user gave you: a firing alert (`obs alerts --firing`),
a service (`obs services`), a metric (`obs query`). Walk `references/triage-signals.md`
(RED for request-driven services, USE for resources) to pick the next read.

**Step 3 — Bounded reads.** Narrow to one service and one window, then traces before logs:

```bash
# hook: allow
obs traces --service checkout --error --since 30m --backend B --md
obs trace TRACE_ID --depth 4 --backend B --md
obs logs "severity_text = 'ERROR'" --service checkout --since 15m --limit 100 --backend B --md
```

Hand anything bigger to `obs-triage`.

**Step 4 — Report.** Backend (and `[PROD]`) · what is broken and since when · the evidence
(command + the field that proves it) · root cause with a confidence · **remediation for the
human**, numbered, each with its blast radius and the repository file it belongs in · what was
not verified. Stop after three unresolved hypotheses and say so.

Changing an alert rule or a dashboard is a repository change:

```bash
# hook: allow
obs dashboards --export api-red dashboards/api-red.json --backend grafana
obs lint dashboards/api-red.json rules/api.json
```

then edit, commit on a branch and open an MR in the owning repository.

## Deliberately not implemented

Not gaps — decisions. Do not work around them with raw `curl`: the hook prompts or denies, and
routing around a prompt is the one thing that is never acceptable. Tell the user what to run
instead.

- **Any write to a backend**: alert rules, dashboards, silences, notification channels, API keys.
- **`--follow` / live tail** of logs or traces.
- **Exports beyond `--max-bytes`.**
- **Native Loki and Tempo adapters** in v1: reach Loki through a grafana backend's datasource.
- **Elastic, Datadog, New Relic** adapters.
- **Reading a kubeconfig** to find in-cluster services: use `k8s promql`.

## References

- `references/triage-signals.md` — the RED / USE walk from a symptom to the next `obs` read.
- `references/alerts-as-code.md` — rule shape, multiwindow burn-rate alerts, what `obs lint` checks.
- `references/signoz.md`, `references/prometheus.md`, `references/grafana.md` — the verified
  backend versions and the exact endpoints the CLI calls.
