# Prometheus adapter

Prometheus HTTP API v1, stable since Prometheus 2.x; the fixtures were written against the
documented shapes for Prometheus 3.x (<https://prometheus.io/docs/prometheus/latest/querying/api/>).
Thanos Query, Grafana Mimir (under its Prometheus prefix) and VictoriaMetrics serve the same
paths; point `url` at the prefix that serves `/api/v1/query`.

## Authentication

None by default. Behind an authenticating proxy, set `auth_file`: the CLI sends
`Authorization: Bearer <key>`.

## Endpoints the CLI calls (the read allow-list)

| Command | Request | Response the CLI reads |
|---|---|---|
| `backends --probe` | `GET /api/v1/status/buildinfo` | `data.version` |
| `query` | `GET /api/v1/query?query=Q` | `data.resultType = vector`, `data.result[] = {metric, value: [ts, "v"]}` |
| `query --range` | `GET /api/v1/query_range?query=Q&start=S&end=E&step=60s` | `matrix`, `result[] = {metric, values: [[ts, "v"], …]}` |
| `alerts --firing` | `GET /api/v1/alerts` | `data.alerts[] = {labels, annotations, state, activeAt, value}` |
| `alerts --rules` | `GET /api/v1/rules` | `data.groups[].rules[] = {name, query, duration, labels, state, type}` (recording rules skipped) |

Every answer outside 2xx JSON is exit 2: a 404 (the endpoint is not served by this version,
or the id does not exist; `backends --probe` reports a 404 on the first endpoint above as
unreachable with a note), a redirect (never followed, so the key never leaves the configured
host; the message names the target), and a non-JSON body such as a login page. A 404 on
`/api/v1/status/buildinfo` usually means `url` misses the prefix (Mimir's `/prometheus`).

`logs`, `traces`, `trace`, `services` and `dashboards` exit 3 on a prometheus backend: logs live
in Loki (reach it through a grafana backend), RED needs your own metric names (`obs query`).

An in-cluster Prometheus without an ingress is not an `obs` backend: use `k8s promql`, which
goes through the Kubernetes API with your kubeconfig context.
