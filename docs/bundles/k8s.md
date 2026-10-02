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
## Summary

Read-only Kubernetes client (k8s CLI + skill), triage / audit / architect agents, kubeconfig and Secret guards

Ships the stdlib `k8s` CLI (contexts, health, pod, workload, events, capacity, argocd, helm,
secret-keys, redact, promql, certs, audit — every call with an explicit --context and a request
timeout), its skill and references, the k8s-triage / k8s-auditor (execution model) and
infra-architect (planning model, design only) agents, and guard sections 10 + 25: kubeconfig
reads and edits deny, Secret data output denies unless piped through `k8s redact`, cluster /
release / GitOps / IaC mutations and exec-class commands ask with `context=… [PROD]` in the
reason. Mutations are always handed to the human.

- **Depends on:** `core`
- **Stability:** stable
- **Domain / posture:** kubernetes / read-only

## Components

Stable ids derived from the path, with their [taxonomy](../reference/taxonomy.md) facets (domain shown only where it differs from the bundle's). All bundles: [catalog](../catalog.md).

**Skills**

- `k8s/skills/k8s` — control: guide · function: client · posture: read-only · model: execute

**Agents**

- `k8s/agents/infra-architect` — control: guide · function: plan · posture: read-only · model: plan
- `k8s/agents/k8s-auditor` — control: guide · function: review · posture: read-only · model: execute
- `k8s/agents/k8s-triage` — control: guide · function: investigate · posture: read-only · model: execute

**Rules**

- `k8s/rules/10-k8s` — control: guide · function: govern

**Guard sections**

- `k8s/guard.d/10-k8s` — control: sensor · function: govern · decisions: helper (no rules)
- `k8s/guard.d/25-k8s-rules` — control: sensor · function: govern · decisions: deny 4 · ask 7

**Permission lists**

- `k8s/permissions` — control: guide · function: govern · decisions: deny 12 · ask 45 · allow 42

**CLIs**

- `k8s/bin/k8s` — function: client · posture: read-only

**Doctor checks** (function: setup · posture: read-only; table below): `k8s/doctor/clusters-doc`, `k8s/doctor/helm-binary`, `k8s/doctor/k8s-cli`, `k8s/doctor/kube-contexts`, `k8s/doctor/kubectl-binary`

**Manual steps** (function: setup; table below): `k8s/steps/clusters-doc`, `k8s/steps/gitops-checkout`, `k8s/steps/install-kubectl`, `k8s/steps/kubeconfig-contexts`

## Requirements

### Binaries

| binary | min version | install | optional | why |
|---|---|---|---|---|
| `helm` | 3.10.0 |  | yes | Release status / history for `k8s helm` and `k8s health`. |
| `kubectl` | 1.25.0 |  | no | Every k8s CLI call shells out to kubectl --context C --request-timeout=Ts. |
| `python3` | 3.9 |  | no | The k8s CLI is stdlib python. |

### Configuration

| key | type | required | default | description |
|---|---|---|---|---|
| `k8s.broken_contexts` | array | no | `[]` | Contexts known to be broken (Unauthorized, TLS SAN mismatch); documentation for the org notes and doctor, never used to skip a context silently. |
| `k8s.clusters_doc` | string | no | `"~/.local/state/harness/k8s/clusters.md"` | File `k8s contexts --write` regenerates (a relative path is under HARNESS_HOME, e.g. a private bundle's references/). K8S_CLUSTERS_MD. |
| `k8s.gitops_repo_match` | string | no | `""` | Substring of an Application's repoURL that marks it as that checkout. Empty = the basename of k8s.gitops_root. K8S_GITOPS_REPO_MATCH. |
| `k8s.gitops_root` | string | no | `""` | Local checkout of your GitOps repo; `k8s argocd` maps spec.source.path into it. Empty = the local-path check is skipped. K8S_GITOPS_ROOT. |
| `k8s.prod_re` | string | no | `"(^\|[-_./:])(prod\|production)([-_./:]\|$)"` | Case-insensitive ERE on context and namespace names marking production ([PROD] banner; remediations become suggestions only). K8S_PROD_RE. |

### Secrets (never in harness.toml)

| id | where | written by | mode | rotate |
|---|---|---|---|---|
| `kubeconfig` | `~/.kube/config` | human / cluster admins (kubeconfig merge) | 0600 |  |

## Manual steps

<a id="install-kubectl"></a>

### install-kubectl — Install kubectl (and helm)

*once per machine · needs nothing but a terminal · ~3 min*

**Why:** The k8s CLI is a thin, read-only layer over kubectl and helm.

**How:**

- kubectl: https://kubernetes.io/docs/tasks/tools/ — pick a client within one or two minors of
  your servers (a newer client prints a harmless skew WARNING on stderr).
- helm 3: `curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash`
  or `brew install helm`.
Both go into `~/.local/bin` or any directory on PATH.

**Verify:** `kubectl version --client` (exit 0)

<a id="kubeconfig-contexts"></a>

### kubeconfig-contexts — Merge your clusters' kubeconfig contexts (human-managed)

*once per machine · needs admin · ~10 min*

**Why:** Agents never read, switch or edit the kubeconfig; every command passes --context explicitly, so each cluster needs a context you created.

**How:**

1. Get a kubeconfig per cluster from its admins (RKE2/k3s: `/etc/rancher/*/…yaml` with the
   server address fixed; EKS: `aws eks update-kubeconfig --name <cluster> --alias <ctx>` run by
   YOU, never by the agent).
2. Merge: `KUBECONFIG=~/.kube/config:new.yaml kubectl config view --flatten > /tmp/merged &&
   install -m 600 /tmp/merged ~/.kube/config && rm /tmp/merged new.yaml`.
3. Give contexts stable, meaningful names (`kubectl config rename-context old new`) — prod ones
   should match `k8s.prod_re` (default: a `prod`/`production` segment).
4. `k8s contexts --md` shows reachability; list known-broken ones in `k8s.broken_contexts`.

**Verify:** `kubectl config get-contexts -o name | grep -q .` (exit 0)

<a id="clusters-doc"></a>

### clusters-doc — Generate the clusters doc

*once per machine · needs nothing but a terminal · ~1 min*

**Why:** The skill and agents read it to orient; it is generated, never hand-edited.

**How:**

Run `k8s contexts --write` (probes every context in parallel and writes `{{ k8s.clusters_doc }}`). Re-run after adding or fixing contexts.

**Verify:** `test -s {{ k8s.clusters_doc }}` (exit 0)

<a id="gitops-checkout"></a>

### gitops-checkout — Clone your GitOps repo and set k8s.gitops_root (optional)

*once per machine · needs nothing but a terminal · ~2 min*

**Why:** `k8s argocd` and the agents map an Application's spec.source.path to local files to explain drift; without a checkout that check is skipped.

**How:**

`git clone <your gitops repo> ~/dev/<name>`, then in `local/harness.toml`:
```
[k8s]
gitops_root = "~/dev/<name>"
gitops_repo_match = "<substring of the repoURL>"   # optional, defaults to the directory name
```
and `harness apply`.

**Verify:** `true` (exit 0)

## Doctor checks

| id | severity | offline | fix |
|---|---|---|---|
| `kubectl-binary` | fail | runs | [install-kubectl](#install-kubectl) |
| `helm-binary` | warn | runs | [install-kubectl](#install-kubectl) |
| `k8s-cli` | fail | runs | `harness apply` |
| `kube-contexts` | warn | runs | [kubeconfig-contexts](#kubeconfig-contexts) |
| `clusters-doc` | warn | runs | [clusters-doc](#clusters-doc) |

## Guides and sensors

Guides steer the agent before it acts; sensors detect at or after the action. Pairing: **paired**.

| side | kind | ref | note |
|---|---|---|---|
| guide | rule | `rules/10-k8s.md` | read-only by default, explicit --context, Secret keys only, prod remediations are suggestions |
| guide | skill | `skills/k8s` | the k8s CLI: contexts, triage views, secret-keys, redact |
| guide | permission | `permissions.toml` | read-only kubectl/helm allowed |
| guide | agent | `agents/k8s-triage.md` | read-only incident triage that hands remediations to the human |
| guide | agent | `agents/k8s-auditor.md` | read-only posture review |
| guide | agent | `agents/infra-architect.md` | design-only infrastructure advice |
| sensor | guard | `guard.d/10-k8s.sh` | kubectl/helm clause parsing shared by the rules section |
| sensor | guard | `guard.d/25-k8s-rules.sh` | kubeconfig, Secret data, cluster, release, GitOps and IaC mutations |
| sensor | doctor | `doctor_checks` | kubectl, helm, the k8s CLI, contexts and the clusters doc |
| sensor | test | `guard.d/tests.sh` | guard rows with stubbed kubectl and helm |
| sensor | test | `tests/run.sh` | this bundle's rows against core + k8s only |
| sensor | test | `skills/k8s/scripts/tests/run.sh` | the k8s CLI against stubbed kubectl and helm |

**Not covered:** The agents' read-only stance is enforced for shell commands by the guard; MCP or API access outside the shell is not sensed.

## Uninstall

Kept on uninstall: `~/.kube/**`

The kubeconfig and the generated clusters doc are yours; uninstall removes only the rendered skill, agents, rules and guard sections.
<!-- generated:end -->
