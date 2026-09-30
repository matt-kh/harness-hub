# Security & posture audit rubric

```bash
# hook: allow
k8s audit --context dev-cluster --md            # whole cluster, deduplicated per owner
k8s audit --ns shop --context dev-cluster --md
k8s certs --context dev-cluster --md
```

`k8s audit` reports pod-spec posture only; RBAC, deprecated APIs and image hygiene are the manual
passes below. Exit 1 = findings, exit 2 = access error.

## 1. Severity rubric

Map every `k8s audit` finding through this table — do not invent severities. Report as
**Critical (must fix) / Warnings (should fix) / Suggestions (consider improving)**.

| Finding | Severity | Why |
|---|---|---|
| `securityContext.privileged: true` | **Critical** | full host access; node compromise = cluster compromise |
| `hostPID` / `hostIPC` / `hostNetwork: true` | **Critical** | host namespace escape / traffic interception |
| `hostPath` volume (writable, or `/`, `/etc`, `/var/run/docker.sock`) | **Critical** | host filesystem write = node takeover |
| `allowPrivilegeEscalation: true` (or unset) with `runAsNonRoot` unset | **Critical** | setuid path to root in the container |
| namespace with no PSA `enforce` label | **Critical** in `prod` contexts, Warning elsewhere | nothing stops the three above being admitted |
| ServiceAccount bound to `cluster-admin` (not a system SA) | **Critical** | §2 |
| Secret mounted as env from an unscoped SA + `automountServiceAccountToken: true` on a public-facing pod | Warning | token theft surface |
| `runAsUser: 0` / `runAsNonRoot` unset | Warning | defence in depth |
| no `resources.limits` | Warning | a single pod can evict its neighbours (`capacity.md`) |
| no `resources.requests` | Warning | scheduled as BestEffort, first to be evicted |
| image `:latest` or untagged | Warning | non-reproducible rollouts, silent drift |
| image without a digest in a `prod` context | Suggestion | tags are mutable |
| no liveness/readiness probe | Warning | failures never surface, traffic sent to dead pods |
| `capabilities.add` beyond `NET_BIND_SERVICE` | Warning | narrow it |
| `readOnlyRootFilesystem` unset | Suggestion | |
| `seccompProfile` unset (not `RuntimeDefault`) | Suggestion | |
| default SA automount on a pod that calls no API | Suggestion | |
| apiserver / cert-manager certificate < 30 d | **Critical** < 7 d, Warning < 30 d | §4 |

Escalate one level in a `[PROD]` context, and state the escalation. **Every finding names the fix
as a chart-values or overlay change** with the path in `<charts repo>` / `<gitops root>`
when it can be found (`gitops.md` §6) — never as a live `kubectl` edit.

## 2. Pod Security Admission

```bash
# hook: pass
kubectl --context dev-cluster get ns -o json | jq -r '
  .items[] | [.metadata.name,
              (.metadata.labels["pod-security.kubernetes.io/enforce"] // "-"),
              (.metadata.labels["pod-security.kubernetes.io/enforce-version"] // "-"),
              (.metadata.labels["pod-security.kubernetes.io/audit"] // "-"),
              (.metadata.labels["pod-security.kubernetes.io/warn"] // "-")] | @tsv'
```

Levels: `privileged` (no restrictions — treat as unlabelled), `baseline` (blocks hostPath,
hostNetwork/PID/IPC, privileged, most capabilities), `restricted` (baseline + runAsNonRoot,
`allowPrivilegeEscalation: false`, `seccompProfile: RuntimeDefault`, dropped capabilities).

Recommend `enforce: baseline` as the floor for application namespaces and `restricted` for
anything new; `audit`/`warn` at the next level up is the safe migration path. System namespaces
(`kube-system`, `gpu-operator`, `cattle-*`, `calico-*`) legitimately need `privileged` — do not
flag them.

Kubernetes >= 1.25 enforces PSA; PodSecurityPolicy is gone.

## 3. RBAC review

```bash
# hook: pass
kubectl --context dev-cluster get clusterrolebindings -o json | jq -r '
  .items[] | select(.roleRef.name=="cluster-admin") |
  [.metadata.name, (.subjects[]? | "\(.kind):\(.namespace // "-"):\(.name)")] | @tsv'
kubectl --context dev-cluster get clusterroles -o json | jq -r '
  .items[] | select([.rules[]? | select((.verbs[]?=="*") and ((.resources[]?=="*") or (.apiGroups[]?=="*")))] | length > 0) |
  .metadata.name'
kubectl --context dev-cluster get rolebindings -A -o json | jq -r '
  .items[] | [.metadata.namespace, .metadata.name, .roleRef.kind+"/"+.roleRef.name,
              ([.subjects[]? | .kind+":"+.name] | join(","))] | @tsv'
kubectl --context dev-cluster auth can-i --list --as system:serviceaccount:shop:shop-api -n shop
kubectl --context dev-cluster auth can-i create pods --as system:serviceaccount:shop:shop-api -n shop
kubectl --context dev-cluster auth can-i '*' '*' --all-namespaces
```

Flag, in order:
1. Non-system subjects bound to `cluster-admin` (ServiceAccounts especially) — **Critical**.
2. ClusterRoles with `verbs: ["*"]` on `resources: ["*"]` or `apiGroups: ["*"]`, and who is bound
   to them.
3. `secrets` `get`/`list`/`watch` at **cluster** scope — reads every Secret in the cluster.
4. `create` on `pods/exec`, `pods/portforward`, `serviceaccounts/token`,
   `escalate`/`bind` on roles, `impersonate` — all privilege-escalation primitives.
5. Bindings to `system:authenticated` or `system:anonymous`.

`auth can-i --list --as …` is the fastest way to state an SA's effective power in one line; note
that the identity on dev-cluster is cluster-admin, so `can-i` without `--as` always answers yes and
proves nothing.

## 4. Secret hygiene and certificates

**Secret values are never printed** — the hook denies it. Keys and sizes only:

```bash
# hook: allow
k8s secret-keys shop shop-db --context dev-cluster       # key -> N bytes, type
k8s secret-keys shop --all --context dev-cluster
```

```bash
# hook: pass
kubectl --context dev-cluster get secrets -A -o json | jq -r '
  .items[] | [.metadata.namespace, .metadata.name, .type, ([.data // {} | keys[]] | join(","))] | @tsv'
```

Check for: `Opaque` Secrets holding obviously long-lived credentials with no rotation annotation;
`kubernetes.io/service-account-token` Secrets (legacy, 1.24+ should use projected tokens);
Secrets committed anywhere under `<gitops root>/secrets/` in plaintext (that repo's own
secret scan covers keys only — read its rule before commenting); the same Secret name duplicated
across namespaces (a copy-paste credential).

Certificates — `k8s certs` covers apiserver TLS (`notAfter`), pending CSRs and cert-manager
`Certificates`. dev-cluster has **no cert-manager** as of 2026-09-23, so ingress TLS there is
static and expiry is a human calendar item; say so rather than reporting "no certificates".

```bash
# hook: pass
kubectl --context dev-cluster get csr -o json | jq -r '.items[]|select(.status.conditions==null)|.metadata.name'
kubectl --context dev-cluster get secrets -A --field-selector type=kubernetes.io/tls -o json | jq -r '
  .items[] | [.metadata.namespace, .metadata.name] | @tsv'
```

< 30 d to expiry = Warning, < 7 d = Critical.

## 5. Deprecated APIs

No `kubent`/`pluto` is installed; the apiserver counts it itself:

```bash
# hook: pass
kubectl --context dev-cluster get --raw /metrics | grep apiserver_requested_deprecated_apis
```

Each series carries `group`, `version`, `resource` and `removed_release` — anything whose
`removed_release` is at or below the target upgrade version is a **Critical** upgrade blocker.
Correlate with the caller:

```bash
# hook: pass
kubectl --context dev-cluster get --raw /metrics | grep -E 'apiserver_request_total.*(v1beta1|v1alpha1)' | head -20
```

Then grep the source repos for the offending `apiVersion` — `grep -rn "apiVersion: policy/v1beta1"
<charts repo> <gitops root>` — and report the file, not the live object. A client several
minors ahead of the server prints a skew `WARNING` on stderr: unrelated noise.

## 6. Image hygiene

```bash
# hook: pass
kubectl --context dev-cluster get pods -A -o json | jq -r '
  [.items[] | .spec.containers[] , (.spec.initContainers[]? ) | .image] | group_by(.) |
  map({image: .[0], count: length}) | sort_by(-.count) | .[] | [.count, .image] | @tsv'
```

Flag: `:latest` or no tag (Warning); no registry host, i.e. implicit Docker Hub (Warning in
air-gapped/prod contexts); `imagePullPolicy: Always` on a large image in a bandwidth-constrained
site (Suggestion); the same app running different tags across namespaces (Warning — a half-finished
promotion; check `k8s argocd` and the pins in `gitops`).

## 7. Report shape

Exactly the `code-reviewer` shape — **Critical (must fix)**, **Warnings (should fix)**,
**Suggestions (consider improving)** — each item as:

`<kind>/<name>` in `<ns>` on `<context>` — one-line problem · evidence (the command and the field
that proves it) · fix (`path/in/repo.yaml`: the value to change).

State the context and mark `[PROD]`. If a check could not run (no CRD, no metrics, access error),
list it under **Not verified** rather than passing it silently.
