# Observability: PromQL, Grafana, kubelet, apiserver metrics, logs

No port-forward, no proxy, no browser. Everything goes through the **apiserver service/node proxy**
with `kubectl get --raw`, which is a plain read (`hook: pass`). `kubectl port-forward` and
`kubectl proxy` are exec-class — the hook asks and the agent never runs them.

On dev-cluster (Rancher Monitoring, ns `cattle-monitoring-system`):
Prometheus `rancher-monitoring-prometheus:9090`, Grafana `rancher-monitoring-grafana` (port 80),
Alertmanager `rancher-monitoring-alertmanager:9093`. Other contexts differ — discover, never
hardcode.

## 1. PromQL

```bash
# hook: allow
k8s promql 'up' --context dev-cluster                                 # auto-discovers the Prometheus svc
k8s promql 'sum by (namespace) (kube_pod_status_phase{phase="Pending"})' --context dev-cluster
k8s promql 'rate(container_cpu_usage_seconds_total{namespace="shop"}[5m])' \
  --svc cattle-monitoring-system/rancher-monitoring-prometheus:9090 --context dev-cluster
k8s promql 'container_memory_working_set_bytes{namespace="shop"}' --range 1h --step 60s --context dev-cluster
```

`k8s promql` prefers services named `rancher-monitoring-prometheus`, `prometheus-operated`,
`prometheus-k8s` on port 9090 and tabulates instant vectors. Discover by hand when it cannot:

```bash
# hook: pass
kubectl --context dev-cluster get svc -A | grep -Ei 'prometheus|grafana|alertmanager'
```

Raw form — the exact proxy path (`services/<name>:<port>/proxy` + the Prometheus HTTP API path):

```bash
# hook: pass
kubectl --context dev-cluster --request-timeout=20s get --raw \
  '/api/v1/namespaces/cattle-monitoring-system/services/rancher-monitoring-prometheus:9090/proxy/api/v1/query?query=up' | jq '.data.result[:5]'
```

**URL-encode the query — always.** `{`, `}`, `"`, spaces, `+`, `&`, `#` and `%` break the request or
truncate it silently:

```bash
# hook: pass
Q=$(python3 -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1],safe=""))' \
     'sum by (node) (kube_pod_container_resource_requests{resource="cpu"})')
kubectl --context dev-cluster get --raw \
  "/api/v1/namespaces/cattle-monitoring-system/services/rancher-monitoring-prometheus:9090/proxy/api/v1/query?query=$Q" \
  | jq -r '.data.result[] | [.metric.node, .value[1]] | @tsv'
```

Range queries need `start`/`end` (unix seconds) and `step`:

```bash
# hook: pass
END=$(date +%s); START=$((END-3600))
kubectl --context dev-cluster get --raw \
  "/api/v1/namespaces/cattle-monitoring-system/services/rancher-monitoring-prometheus:9090/proxy/api/v1/query_range?query=$Q&start=$START&end=$END&step=60" \
  | jq '.data.result[] | {metric, n: (.values|length), first: .values[0], last: .values[-1]}'
```

Reading the response: `.status` must be `success`; `.data.resultType` is `vector` (instant) or
`matrix` (range); `.data.result[].value` is `[ts, "string"]` — the value is a **string**, cast it.
An empty `.data.result` means "no such series", which is a finding about the exporter, not a zero.
Other useful endpoints through the same proxy: `/api/v1/label/__name__/values` (what metrics exist),
`/api/v1/targets?state=active` (scrape health), `/api/v1/rules`, `/api/v1/alerts`.

Cap the blast radius: a raw range query over a wide selector returns megabytes. Add a `topk(...)`
or a `sum by (...)`, redirect to `$SCRATCH/*.json`, and `jq` out the few fields needed.

## 2. Grafana and Alertmanager through the proxy

```bash
# hook: pass
kubectl --context dev-cluster get --raw \
  '/api/v1/namespaces/cattle-monitoring-system/services/rancher-monitoring-grafana:80/proxy/api/health'
kubectl --context dev-cluster get --raw \
  '/api/v1/namespaces/cattle-monitoring-system/services/rancher-monitoring-grafana:80/proxy/api/search?type=dash-db' \
  | jq -r '.[] | [.uid, .title] | @tsv'
kubectl --context dev-cluster get --raw \
  '/api/v1/namespaces/cattle-monitoring-system/services/rancher-monitoring-alertmanager:9093/proxy/api/v2/alerts' \
  | jq -r '.[] | [.labels.alertname, .labels.severity, .status.state] | @tsv'
```

Grafana's API requires auth for most endpoints; anonymous access varies by install, so a 401 here
is normal — do **not** hunt for the admin credential (the Secret gate denies it). Give the user the
dashboard UID/title and let them open it. Never render a dashboard; query Prometheus directly for
the numbers instead.

## 3. Kubelet stats (per-node, no metrics-server dependency)

```bash
# hook: pass
kubectl --context dev-cluster get --raw /api/v1/nodes/<node>/proxy/stats/summary | jq '{
  node: .node.nodeName,
  cpu: .node.cpu.usageNanoCores, mem: .node.memory.workingSetBytes,
  fs: {used: .node.fs.usedBytes, cap: .node.fs.capacityBytes},
  imagefs: {used: .node.runtime.imageFs.usedBytes, cap: .node.runtime.imageFs.capacityBytes},
  topPods: [.pods[] | {ns: .podRef.namespace, name: .podRef.name, mem: .memory.workingSetBytes}] }'
```

This is the authoritative source for **DiskPressure** triage (`node.fs` vs `runtime.imageFs`) and
works when metrics-server does not. `/proxy/metrics/cadvisor` and `/proxy/metrics/resource` on the
same node path give the raw cadvisor series.

## 4. Apiserver metrics

```bash
# hook: pass
kubectl --context dev-cluster get --raw /metrics | grep apiserver_requested_deprecated_apis
kubectl --context dev-cluster get --raw /metrics | grep -E '^apiserver_request_total.*code="(429|5..)"' | head
kubectl --context dev-cluster get --raw /metrics | grep -E '^etcd_(request_duration|db_total_size)' | head
kubectl --context dev-cluster get --raw /healthz?verbose | head -30
kubectl --context dev-cluster get --raw /readyz?verbose | head -30
```

`/metrics` is megabytes — always `grep` at the pipe, never dump it into the context.
Deprecated-API counting is in `security-audit.md` §5.

## 5. Events

```bash
# hook: allow
k8s events --ns shop --warning --since 60m --context dev-cluster --md   # grouped by reason with counts
```

```bash
# hook: pass
kubectl --context dev-cluster -n shop events --types=Warning --for pod/shop-api-0
kubectl --context dev-cluster events -A --types=Warning
kubectl --context dev-cluster -n shop get events --field-selector type=Warning \
  --sort-by=.lastTimestamp -o json | jq -r '.items[-20:][] | [.lastTimestamp,.reason,.involvedObject.kind+"/"+.involvedObject.name,.message] | @tsv'
```

Events default to a **1 h TTL** (kube-apiserver `--event-ttl`) — an empty result means "nothing recent", never "nothing
happened". Prefer the server-side `--types=Warning` / `--field-selector` filter over grepping a
full dump.

## 6. Log rules

```bash
# hook: pass
kubectl --context dev-cluster -n shop logs deploy/shop-api --tail=50 | k8s redact
kubectl --context dev-cluster -n shop logs shop-api-0 -c api --previous --tail=100 | k8s redact
kubectl --context dev-cluster -n shop logs -l app=shop-api --tail=20 --max-log-requests=5 --prefix | k8s redact
kubectl --context dev-cluster -n shop logs shop-api-0 --since=15m --timestamps | k8s redact
```

- **Always bound the output**: `--tail=N` (default 50 via `k8s --tail`) or `--since=15m`. An
  unbounded `logs` on a chatty pod is tens of MB.
- **Never `-f`/`--follow`** — it never returns and burns the turn. To watch, re-run with
  `--since=<interval>`.
- **Always pipe through `k8s redact`** (or use `k8s pod`, which redacts for you): application logs
  routinely contain passwords, tokens, JWTs, `AKIA…` keys and `://user:pass@` DSNs.
- `--previous` is where a CrashLoop's real error lives; the current container has just started.
- No `stern` is installed — use `-l <selector> --prefix --max-log-requests=N` for multi-pod logs.
- **Never paste a full log dump into the main context.** Redirect to
  `$SCRATCH/<pod>.log`, grep it, and quote the few lines that matter — or hand the whole
  investigation to the **`k8s-triage`** agent, whose job is to read the dumps in its own context and
  return a summary.
