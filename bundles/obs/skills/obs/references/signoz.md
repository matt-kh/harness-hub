# SigNoz adapter

**Verified against SigNoz v0.121.x, 2026-10-16** (tag `v0.121.1`, the public `signoz` Helm chart
0.121.1 / appVersion v0.121.1), by reading the route registrations in the SigNoz source at that
tag: `pkg/query-service/app/http_handler.go`, `pkg/apiserver/signozapiserver/querier.go` and
`alertmanager.go`, `pkg/identn/config.go`, the response types in
`pkg/types/querybuildertypes/querybuildertypesv5/resp.go`, `pkg/types/ruletypes/api_params.go`,
`pkg/types/alertmanagertypes/alert.go`, `pkg/types/dashboardtypes/dashboard.go` and
`pkg/query-service/model/{response,queryParams}.go`. The SigNoz API moved between v0.x releases:
re-check this page when the backend's `obs backends --probe` version changes minor.

## Authentication

Header `SIGNOZ-API-KEY: <key>` (`identn` config: `APIKeyConfig.Headers = ["SIGNOZ-API-KEY"]`).
Create a key with the **Viewer** role (*Settings → API Keys*); every endpoint below is
`ViewAccess` (or open), so a Viewer key is enough and keeps the CLI read-only server-side too.

## Endpoints the CLI calls (the read allow-list)

| Command | Request | Access | Response the CLI reads |
|---|---|---|---|
| `backends --probe` | `GET /api/v1/version` | open | `{version, ee, setupCompleted}` (raw JSON) |
| `backends --probe` (auth) | `GET /api/v1/rules` | view | as `alerts --rules` |
| `query` | `POST /api/v5/query_range`, `requestType: "time_series"`, one `{"type": "promql", "spec": {name, query, step}}` | view | `{status, data: {type, data: {results: [{queryName, aggregations: [{series: [{labels: [{key: {name}, value}], values: [{timestamp, value}]}]}]}]}, meta}}` |
| `logs` | `POST /api/v5/query_range`, `requestType: "raw"`, `{"type": "builder_query", "spec": {name, signal: "logs", filter: {expression}, order, limit}}` | view | `results[].rows[] = {timestamp, data: {…}}` |
| `traces`, `trace` | same with `signal: "traces"` and `selectFields` | view | same rows |
| `services` | `POST /api/v1/services` `{start, end, tags: []}` (start/end: nanosecond epoch **strings**) | view | raw list of `{serviceName, p99, avgDuration, numCalls, callRate, numErrors, errorRate, num4XX, fourXXRate}` |
| `alerts --firing` | `GET /api/v1/alerts` | view | `{status, data: [{labels, annotations, startsAt, endsAt, status: {state, silencedBy, inhibitedBy}, receivers, fingerprint}]}` |
| `alerts --rules` | `GET /api/v1/rules` | view | `{status, data: {rules: [{id, state, alert, alertType, ruleType, evalWindow, labels, condition, disabled, …}]}}` |
| `dashboards` | `GET /api/v1/dashboards` | view | `{status, data: [{id, createdAt, updatedAt, data: {title, tags, …}, locked}]}` |
| `dashboards --export ID` | `GET /api/v1/dashboards/{id}` | view | `{status, data: {id, data: {…dashboard JSON…}}}`; the CLI writes `data.data` |

The same paths also register `POST`, `PUT`, `PATCH` and `DELETE` handlers (create/edit/delete
rules and dashboards); the CLI's allow-list never sends those methods.

Not used on purpose: `GET /api/v1/query` / `query_range` (PromQL without the v5 envelope),
`/api/v4/query_range` (superseded by v5), `/api/v3/logs/livetail` (a live tail),
`/api/v2/traces/waterfall/{id}` and `/flamegraph/{id}` (POST; `trace` uses the v5 raw query
instead), `/api/v2/services` (the v1 path is marked deprecated in the source but still
registered at v0.121.1; move when it is removed).

## Unverified

Read from the source, not from a running v0.121.x instance. Confirm with `obs backends --probe`
and one call of each command against the real backend, then update this section:

- The exact key set of a `raw` row's `data` map. The CLI reads `body`, `severity_text`,
  `service.name` (or `resources_string["service.name"]`) for logs and `trace_id`, `span_id`,
  `parent_span_id`, `name`, `duration_nano`, `has_error`, `service.name` for spans; a missing key
  shows as an empty cell, never an error.
- That `parent_span_id = ''` selects root spans in a v5 filter expression (`traces`).
- The unit of `p99` / `avgDuration` in `/api/v1/services` (read as nanoseconds, shown in ms).
- Whether `/api/v1/alerts` and the v5 query handler wrap their response in `{status, data}`;
  the CLI accepts both the wrapped and the bare form.

The fixtures under `scripts/tests/fixtures/signoz/` encode exactly the shapes above.
