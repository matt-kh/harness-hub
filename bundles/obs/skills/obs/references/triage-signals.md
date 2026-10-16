# Triage by signal: RED and USE

Pick the walk by what is failing: **RED** for anything that serves requests (services, APIs,
queues consumers), **USE** for resources (hosts, pods, disks, connection pools).

## RED — Rate, Errors, Duration

1. **Which service moved first?** `obs services --since 1h --md` (SigNoz) lists calls, rate,
   error % and p99 per service, worst error rate first. On Prometheus:
   ```
   obs query 'sum by (service) (rate(http_requests_total[5m]))' --range 1h --backend prom
   obs query 'sum by (service) (rate(http_requests_total{code=~"5.."}[5m])) / sum by (service) (rate(http_requests_total[5m]))' --range 1h --backend prom
   ```
2. **Errors** — `obs traces --service S --error --since 30m`, then `obs trace ID --depth 4`:
   the deepest span with an error status is usually the cause; its service is the next hop.
3. **Duration** — `obs traces --service S --min-duration 500ms` and the slowest trace's tree:
   one span taking most of the root's time is the bottleneck (a database call, a lock, a
   downstream timeout).
4. **Rate** — a drop to zero with no errors is upstream (traffic not arriving: ingress, DNS,
   a client); a spike is load (check USE next).
5. **Logs last** — `obs logs "severity_text = 'ERROR'" --service S --since 15m --limit 100`
   for the message the trace pointed at.

## USE — Utilisation, Saturation, Errors

- CPU: `rate(container_cpu_usage_seconds_total[5m])` vs limits; throttling:
  `rate(container_cpu_cfs_throttled_periods_total[5m]) / rate(container_cpu_cfs_periods_total[5m])`.
- Memory: `container_memory_working_set_bytes` vs limits (OOMKilled pods: `k8s pod`).
- Saturation: queue length, connection-pool waiters, `node_load5` / cores.
- Errors: `node_filesystem_avail_bytes`, disk and network error counters.

## When to stop

Three hypotheses without a confirmed cause: report what you have, with a confidence and the
checks you could not run (backend exit 3, access error, data outside the retention window).
