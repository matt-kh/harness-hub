## Observability
- **Read-only.** Use the `obs` CLI (skill `obs`) for every backend read: run `obs backends`
  first, then pass `--backend NAME` explicitly. In-cluster Prometheus without an ingress is
  `k8s promql`, not `obs`.
- Banner on stderr is `backend=<name> kind=<kind> url=<host> [PROD]`. Prod backends (matching
  `OBS_PROD_RE`) read freely, but there **remediations are suggestions for the human**, stated
  with their blast radius, never executed.
- **Bounded and redacted.** Logs and traces always with `--since` and `--limit` / `--max-items`;
  `obs` redacts log lines, span attributes and label values. Never `logcli --tail`, never a
  follow mode.
- **Alert rules, dashboards and silences change only as files in the owning repository,
  through an MR**: `obs dashboards --export UID FILE`, edit, `obs lint FILE`, MR. Never write
  them through a backend API; `amtool silence add|expire` and `grafana-cli admin` are handed to
  the user.
- **API keys stay in `~/.config/obs/*.key`**: reading those files is **denied**, an API key
  written on a command line is **denied**, and raw `curl`/`wget` to a backend host
  (`OBS_HOSTS_RE`) **asks** — use `obs` instead.
- Agent: `obs-triage` (firing alert / error spike → root cause + remediation for the human).

A repository's own instructions for the same action replace this block.
