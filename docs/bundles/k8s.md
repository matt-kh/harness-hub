# Bundle: k8s

Read-only Kubernetes operations for agents: the `k8s` CLI (explicit context on every call,
banner with context, server version and `[PROD]` marker, Secret redaction), the `k8s-triage`
and `k8s-auditor` sub-agents, and the `infra-architect` design-only agent.

- Reads are free, production included; the banner makes prod visible.
- Mutations, exec-class commands, `helm install|upgrade|uninstall|rollback`, GitOps and IaC
  mutations **ask**: the agent hands you the command with its blast radius.
- `kubectl config use-context` and every other kubeconfig edit, reading the kubeconfig file,
  and printing Secret data are **denied**. `k8s secret-keys NS NAME` shows keys and sizes;
  `… | k8s redact` masks values and lifts the Secret / `helm get values` gates.
- Fixes are proposed as changes to your GitOps or chart repositories, never applied live.

Config: `k8s.prod_re` (regex marking prod contexts/namespaces), `k8s.gitops_root`,
`k8s.gitops_repo_match`, `k8s.clusters_doc` (a private cluster inventory, usually in
`local/bundles/<org>/references/`), `k8s.broken_contexts`.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `x509: certificate is valid for …, not <host>` (TLS **SAN mismatch**) | the kubeconfig `server:` uses a hostname or IP that is not in the API server certificate's SANs | point `server:` at a name in the certificate, or have the cluster admin add the SAN; do not use `insecure-skip-tls-verify` |
| `error: You must be logged in to the server (Unauthorized)` | expired client certificate or token, or an OIDC/exec plugin not logged in | refresh credentials with your cluster's login tool; list the context in `k8s.broken_contexts` until fixed so doctor stops failing |
| A context is listed but every call times out | VPN or bastion not connected | connect; `k8s contexts` shows reachability per context |
| Agent asks before a harmless `kubectl` command | the command matches a mutation or exec-class pattern | read the reason; `--dry-run=client|server` variants are exempt |
| `k8s` refuses to switch context | by design: the kubeconfig is shared with your shell | pass `--context` explicitly; switch contexts yourself if you want |
| Prod not flagged | your naming does not match `k8s.prod_re` | adjust the regex; default matches `prod`/`production` as a whole segment |
| EKS contexts fail with `exec plugin` errors | `aws` CLI missing or SSO session expired | `aws sso login --profile <p>` in your shell |
| Output shows `[redacted]` where you need a value | Secret redaction | read the value yourself; agents never see it |

<!-- generated:begin source=bundles/k8s/bundle.toml -->
<!-- generated:end -->
