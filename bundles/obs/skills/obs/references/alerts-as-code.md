# Alert rules and dashboards as code

Alert rules, dashboards and silences live as files in the repository that owns the service or
the platform, and change through an MR. `obs` reads the live state and exports dashboards; it
never writes them back.

## Prometheus rule shape

```yaml
groups:
  - name: checkout.rules
    rules:
      - alert: CheckoutHighErrorRate
        expr: |
          sum by (service) (rate(http_requests_total{service="checkout", code=~"5.."}[5m]))
            / sum by (service) (rate(http_requests_total{service="checkout"}[5m])) > 0.05
        for: 10m
        labels:
          severity: critical
        annotations:
          summary: "{{ $labels.service }} error rate above 5%"
          description: More than 5% of checkout requests fail.
          runbook_url: https://runbooks.example.com/checkout-errors
```

## Multiwindow, multi-burn-rate (SLO alerts)

For a 99.9% availability SLO (error budget 0.1%), page when the budget burns fast over both a
long and a short window, so the alert fires quickly and clears quickly:

```
( error_ratio:rate1h > (14.4 * 0.001) and error_ratio:rate5m > (14.4 * 0.001) )   # 2% of a 30-day budget in 1 h → page
( error_ratio:rate6h > (6 * 0.001)    and error_ratio:rate30m > (6 * 0.001) )     # 5% in 6 h → page
( error_ratio:rate3d > (1 * 0.001)    and error_ratio:rate6h > (1 * 0.001) )      # 10% in 3 d → ticket
```

Record each `error_ratio:rateW` once (recording rules) and alert on the records.

## What `obs lint` checks

| Finding | Applies to | Fix |
|---|---|---|
| `for` | Prometheus alert without `for:` | `for: 5m` or longer |
| `severity` | alert without a `severity` label | `labels: {severity: warning\|critical}` |
| `runbook` | alert without `runbook_url` | link the runbook |
| `description` | alert without `description` / `summary` | say what is wrong and for whom |
| `duplicate` | the same alert name twice across the files linted together | rename one |
| `hardcoded` | `namespace=`, `instance=`, `pod=` or `node=` pinned to a literal in `expr` | aggregate `by (label)` |
| `ruleType` / `threshold` | SigNoz alert JSON without `ruleType` or without `condition.target` / `condition.thresholds` | set them |
| `uid` / `title` | Grafana dashboard without a stable `uid` or a `title` | set them |
| `datasource` | a panel or target pinning a datasource uid | use `${datasource}` |

It checks shape, not semantics: run `promtool check rules` and `promtool test rules` for
Prometheus files, and review thresholds with the service owner. YAML needs PyYAML when it is
importable; otherwise convert with `yq -o json` or lint the JSON form.

## The edit loop

```
obs dashboards --export api-red dashboards/api-red.json --backend grafana
${EDITOR:-vi} dashboards/api-red.json
obs lint dashboards/api-red.json
git switch -c dashboards-api-red && git commit -am "dashboards: api-red latency panel" && open the MR
```

The repository's provisioning (Grafana provisioning, the SigNoz dashboards-as-code job, the
Prometheus rule ConfigMap) applies the merged file. Silences are operational and short-lived:
hand `amtool silence add …` to the user with its matcher and duration.
