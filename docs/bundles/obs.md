# Bundle: obs

Read-only observability for agents: the `obs` CLI with adapters for SigNoz, Prometheus-compatible
servers and Grafana (banner with backend, kind, host and `[PROD]` marker; every read bounded and
redacted; a read allow-list of endpoints), the `obs-triage` sub-agent, and guard section 32.

- Reads are free, production included; the banner makes prod visible.
- Reading the API key files under `~/.config/obs/` and writing an API key on a command line are
  **denied**; raw `curl`/`wget`/`http`/`xh` to a configured backend host **asks** (use `obs`).
- `amtool silence add|expire|import`, `amtool alert add`, `logcli query --tail` and
  `grafana-cli admin|plugins install|remove` **ask**: the agent hands you the command.
- Alert rules, dashboards and silences change as files in the owning repository, through an MR:
  `obs dashboards --export UID FILE`, edit, `obs lint FILE`. `obs` never writes to a backend,
  never follows a redirect (the API key stays on the configured host), and `--export` never
  overwrites an existing file without `--force`.

Config: `[[obs.backends]]` tables (`name`, `kind` = `signoz` | `prometheus` | `grafana`, `url`,
`auth_file`), `obs.default`, `obs.hosts_re` (the guard's backend host regex, a POSIX ERE applied
with `grep -E`; empty turns the host rows off), `obs.prod_re`, `obs.log_tail`, `obs.max_bytes`, `obs.redact_extra_re`. Keys live
one per backend in `~/.config/obs/<name>.key` (mode 0600; see the
[rotation runbook](../runbooks/rotate-obs-key.md)). An in-cluster Prometheus without an ingress
stays with `k8s promql` (k8s bundle).

The SigNoz adapter was verified against the v0.121.x source; the endpoints and what is still
unverified are listed in `bundles/obs/skills/obs/references/signoz.md`.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `obs backends` exits 2, `key file … is missing` | the backend's `auth_file` does not exist | manual step `obs-api-key`: `install -m 600 /dev/null ~/.config/obs/<name>.key`, paste the key with an editor |
| `answered 401` / `403` | key revoked, expired, or without the Viewer role | create a new Viewer key and replace the file ([rotate-obs-key](../runbooks/rotate-obs-key.md)) |
| `warning: key file … has mode-0644` | the key file is readable by other users | `chmod 600 ~/.config/obs/<name>.key` |
| `unreachable: … Connection refused` / timeouts | wrong `url`, VPN not connected, or the backend is down | `obs backends --probe`; check the url in `[[obs.backends]]` |
| `answered 404` (exit 2) | the backend version does not serve that endpoint, the id does not exist, or `url` misses a path prefix | check the id; `obs backends --probe` shows the version (a 404 there means the url points elsewhere); compare with `references/signoz.md` |
| `redirected to <host>; refusing to follow with credentials` (exit 2) | an SSO proxy, a login page or a sub-path redirect in front of the API | set `url` to the address that serves the API directly; the CLI never follows a redirect, so the key never leaves the configured host |
| `returned non-JSON … (<!DOCTYPE html>…)` (exit 2) | a login page or proxy answered 200 instead of the API | as above: fix `url` |
| `url must not carry credentials` (exit 2) | `user:password@` in a backend `url` | remove it; the key belongs in `auth_file` |
| `<file> already exists` from `dashboards --export` | the export never overwrites silently | export to a new file, or pass `--force` after checking `git status` |
| `hosts_re is a POSIX ERE used by the guard` | `obs.hosts_re` uses Python-only syntax (`\d`, `\w`, `\s`, `(?…)`), or `grep -E` and Python disagree on a host | rewrite it with `[0-9]`, `[A-Za-z0-9_]`, `[[:space:]]` and run `harness apply` |
| JSON output carries `"truncated"` | the output exceeded `--max-bytes`; trailing list items were dropped, the JSON is whole | narrow the query (`--since`, `--max-items`, a filter) |
| `… is not available on a prometheus backend` (exit 3) | logs, traces, services and dashboards need SigNoz or Grafana | use the backend kind the message names, or `obs query` |
| A grafana `query` or `logs` asks for `--datasource` | Grafana proxies to one datasource per query | pass the datasource uid (*Connections → Data sources*) |
| The agent asks before `curl https://<backend>/…` | the host matches `obs.hosts_re` | use `obs`; the raw request skips the bounds and the redactor |
| Raw `curl` to a backend is not caught | `obs.hosts_re` is empty or misses the host | set it (`harness doctor` check `obs-hosts-re` warns) and run `harness apply` |
| `obs lint` reports `PyYAML is not importable` | YAML parsing is optional | lint the JSON form (`yq -o json`) or run `promtool check rules` |

<!-- generated:begin source=bundles/obs/bundle.toml -->
## Summary

Read-only observability client (obs CLI + skill) for SigNoz, Prometheus and Grafana, an obs-triage agent, and API-key and raw-backend guards

Ships the stdlib `obs` CLI (backends, query, logs, traces, trace, services, alerts, dashboards,
lint, redact — every call bounded, redacted and limited to a read allow-list of endpoints), with
adapters for SigNoz, Prometheus-compatible servers and Grafana, its skill and references, the
obs-triage agent (execution model, investigate only) and guard section 32: reading the API key
files denies, an API key written on a command line denies, raw curl/wget to a configured backend
host asks, and alert-state changes (amtool silence), live tails (logcli --tail) and Grafana admin
commands ask. Alert rules, dashboards and silences change only as files in the owning
repository, through a merge request.

- **Depends on:** `core`
- **Recommends:** `k8s`
- **Stability:** experimental
- **Domain / posture:** operations / read-only

## Components

Stable ids derived from the path, with their [taxonomy](../reference/taxonomy.md) facets (domain shown only where it differs from the bundle's). All bundles: [catalog](../catalog.md).

**Skills**

- `obs/skills/obs` — control: guide · function: client · posture: read-only · model: execute · yields: declaration

**Agents**

- `obs/agents/obs-triage` — control: guide + sensor (inferential) · function: investigate · posture: read-only · model: execute · yields: name

**Rules**

- `obs/rules/32-obs` — control: guide · function: govern · yields: text

**Guard sections**

- `obs/guard.d/32-obs` — control: sensor · function: govern · decisions: deny 2 · ask 4 · yields: declaration

**Permission lists**

- `obs/permissions` — control: guide · function: govern · decisions: deny 1 · ask 3 · allow 5 · yields: config

**CLIs**

- `obs/bin/obs` — function: client · posture: read-only · yields: n/a

**Doctor checks** (function: setup · posture: read-only; table below): `obs/doctor/obs-backends`, `obs/doctor/obs-cli`, `obs/doctor/obs-hosts-re`, `obs/doctor/obs-keys`, `obs/doctor/obs-reach`

**Manual steps** (function: setup; table below): `obs/steps/configure-backends`, `obs/steps/obs-api-key`

## Requirements

### Binaries

| binary | min version | install | optional | why |
|---|---|---|---|---|
| `python3` | 3.9 |  | no | The obs CLI is stdlib python. |

### Configuration

| key | type | required | default | description |
|---|---|---|---|---|
| `obs.backends` | array | no | `[]` | Observability backends, as [[obs.backends]] tables: name, kind (signoz \| prometheus \| grafana), url, auth_file (a key file under ~/.config/obs, mode 0600; optional for prometheus). Never the key itself. |
| `obs.default` | string | no | `""` | Backend name `obs` uses without --backend. Empty = the first entry of obs.backends. |
| `obs.hosts_re` | string | no | `""` | POSIX ERE (the guard applies it with grep -E) matching your backends' host names (no scheme, no port); raw curl/wget/http/xh to a matching host asks (guard section 32). Use [0-9], [A-Za-z0-9_] and [[:space:]], never \d, \w, \s or (?…): `obs backends` and doctor check it with grep -E and flag Python-only syntax. Empty = those rows are off; doctor warns when backends exist. OBS_HOSTS_RE. |
| `obs.log_tail` | integer | no | `200` | Default number of lines `obs logs` returns (--limit overrides). |
| `obs.max_bytes` | integer | no | `65536` | Default output cap in bytes (--max-bytes overrides); `dashboards --export` refuses larger files. |
| `obs.prod_re` | string | no | `"(^\|[-_./:])(prod\|production)([-_./:]\|$)"` | Case-insensitive ERE on backend names and hosts marking production ([PROD] banner; remediations become suggestions only). OBS_PROD_RE. |
| `obs.redact_extra_re` | string | no | `""` | Extra Python regex of token shapes every obs output redacts in addition to the built-in list; compiled on its own, so a leading global flag such as (?i) works. OBS_REDACT_EXTRA_RE. |

### Secrets (never in harness.toml)

| id | where | written by | mode | rotate |
|---|---|---|---|---|
| `obs_keys` | `~/.config/obs/*.key` | human (a Viewer-role API key or service-account token pasted from each backend's UI) | 0600 | docs/runbooks/rotate-obs-key.md |

## Manual steps

<a id="configure-backends"></a>

### configure-backends — Describe your observability backends in local/harness.toml

*once per machine · needs nothing but a terminal · ~5 min*

**Why:** The obs CLI only talks to backends you list, by URL; the guard asks on raw requests to their hosts.

**How:**

Add one table per backend to `local/harness.toml` (documentation values shown):
```
[obs]
default = "signoz-dev"
hosts_re = '^(signoz|grafana)\.example\.com$'

[[obs.backends]]
name = "signoz-dev"
kind = "signoz"                      # signoz | prometheus | grafana
url = "https://signoz.example.com"
auth_file = "~/.config/obs/signoz-dev.key"

[[obs.backends]]
name = "grafana"
kind = "grafana"
url = "https://grafana.example.com"
auth_file = "~/.config/obs/grafana.key"
```
Never put a key in this file. Then run `harness apply` and `obs backends`.

**Verify:** `obs backends --names | grep -q .` (exit 0)

<a id="obs-api-key"></a>

### obs-api-key — Create a read-only API key per backend

*once per account · needs browser · ~5 min*

**Why:** The CLI authenticates with a key file you write; a Viewer-role key keeps every agent read inherently read-only on the backend side too.

**How:**

1. Create the key in each backend's UI with the **Viewer** role:
   SigNoz *Settings → API Keys*; Grafana *Administration → Service accounts* (Viewer, add a token);
   Prometheus needs one only behind an authenticating proxy.
2. Write it without it passing through your shell history:
   ```
   install -d -m 700 ~/.config/obs
   install -m 600 /dev/null ~/.config/obs/signoz-dev.key
   ${EDITOR:-vi} ~/.config/obs/signoz-dev.key      # paste the key, save
   ```
3. `obs backends --probe` shows `auth ok` per backend.

**Verify:** `obs backends --json >/dev/null 2>&1; test $? -ne 2` (exit 0)

## Doctor checks

| id | severity | offline | fix |
|---|---|---|---|
| `obs-cli` | fail | runs | `harness apply` |
| `obs-backends` | warn | runs | [configure-backends](#configure-backends) |
| `obs-keys` | fail | runs | [obs-api-key](#obs-api-key) |
| `obs-hosts-re` | warn | runs | [configure-backends](#configure-backends) |
| `obs-reach` | warn | skipped | [obs-api-key](#obs-api-key) |

## Guides and sensors

Guides steer the agent before it acts; sensors detect at or after the action. Pairing: **paired**; guides with a declared check: 4 of 4.

| side | kind | ref | note | pairs with |
|---|---|---|---|---|
| guide | rule | `rules/32-obs.md` | read-only, obs backends first, bounded and redacted reads, alert rules and dashboards change as repo files | `guard.d/32-obs.sh` |
| guide | skill | `skills/obs` | the obs CLI: backends, query, logs, traces, services, alerts, dashboards, lint | `skills/obs/scripts/tests/run.sh`, `doctor_checks` |
| guide | permission | `permissions.toml` | obs and read-only rule tooling allowed, alert-state changes ask, key files denied to Read | `permissions-vs-guard`, `guard.d/32-obs.sh` |
| guide | agent | `agents/obs-triage.md` | read-only signal triage that hands remediations to the human | `guard.d/32-obs.sh`, `agent-tools` |
| sensor | guard | `guard.d/32-obs.sh` | key files, literal API keys, raw backend requests, amtool/logcli/grafana-cli | `rules/32-obs.md`, `permissions.toml`, `agents/obs-triage.md` |
| sensor | doctor | `doctor_checks` | the CLI, backends, key files, hosts_re and reachability | `skills/obs` |
| sensor | test | `guard.d/tests.sh` | guard rows incl. bypasses and the operations yield | — |
| sensor | test | `tests/run.sh` | this bundle's rows against core + obs only | — |
| sensor | test | `skills/obs/scripts/tests/run.sh` | the obs CLI against fixture-routed HTTP, incl. the dry-run request allow-list | `skills/obs` |
| sensor | review-agent | `agents/obs-triage.md` | evidence-cited triage of firing alerts, logs and traces | — |
| sensor | lint | `permissions-vs-guard` | each Bash allow/deny rule of permissions.toml run through the guard: no allowed command the guard denies or asks, no denied one it allows | `permissions.toml` |
| sensor | lint | `agent-tools` | the read-only triage agent sets no permissionMode and lists no write tools | `agents/obs-triage.md` |

**Not covered:** The CLI's own HTTP calls are not shell commands and are not guarded; the suite's dry-run request log is the read-only proof. Backends reached outside the CLI are not sensed. `obs lint` checks shape, not alert semantics.

## Uninstall

Kept on uninstall: `~/.config/obs/**`

The key files are yours; uninstall removes only the rendered skill, agent, rule and guard section.
<!-- generated:end -->
