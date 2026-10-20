# Grafana adapter

Grafana HTTP API (<https://grafana.com/docs/grafana/latest/developers/http_api/>); fixtures
written against the documented shapes for Grafana 11–12.

## Authentication

A **service account token** with the **Viewer** role (*Administration → Users and access →
Service accounts → Add service account → Add token*), sent as `Authorization: Bearer <token>`.

## Endpoints the CLI calls (the read allow-list)

| Command | Request | Response the CLI reads |
|---|---|---|
| `backends --probe` | `GET /api/health`, then `GET /api/search?limit=1` (auth) | `version` |
| `query --datasource UID` | `POST /api/ds/query` `{queries: [{refId, datasource: {uid}, expr, instant, range, intervalMs, maxDataPoints}], from, to}` | `results.A.frames[] = {schema: {fields: [{name, type, labels}]}, data: {values: [[…], […]]}}` |
| `logs --datasource UID` (Loki) | `POST /api/ds/query` with a LogQL `expr`, `queryType: "range"`, `maxLines` | frames with `labels`, `Time`, `Line` fields |
| `alerts --firing` | `GET /api/alertmanager/grafana/api/v2/alerts?active=true` | Alertmanager v2 list: `{labels, annotations, startsAt, status: {state}}` |
| `alerts --rules` | `GET /api/prometheus/grafana/api/v1/rules` | Prometheus-compatible `data.groups[].rules[]` |
| `dashboards` | `GET /api/search?type=dash-db&limit=N` | `[{uid, title, folderTitle, tags}]` |
| `dashboards --export UID` | `GET /api/dashboards/uid/{uid}` | `{meta, dashboard}`; the CLI writes `dashboard` |

`POST /api/ds/query` is a read (the query travels in the body); the CLI's allow-list permits
POST only there. `traces`, `trace` and `services` exit 3 (Tempo is not supported in v1).

Every answer outside 2xx JSON is exit 2: a 404 (the endpoint is not served by this version,
or the id does not exist; `backends --probe` reports a 404 on the first endpoint above as
unreachable with a note), a redirect (never followed, so the key never leaves the configured
host; the message names the target), and a non-JSON body such as a login page. A Grafana
served under a sub-path (`root_url` with `serve_from_sub_path`) redirects or 404s at the bare
host: put the sub-path into `url`.

The datasource uid is in *Connections → Data sources → <name>* (the URL ends with it). Never
hard-code it into a dashboard: `obs lint` flags panels that pin one.
