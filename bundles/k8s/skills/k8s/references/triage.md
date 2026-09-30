# Triage decision tree

Keyed on what `k8s pod NS POD` and `k8s workload NS KIND/NAME` return. Walk it top-down; the
first matching leaf is the answer. Every command below is read-only unless it is in a
**Hand to the user** block — those are remediations the *human* runs (the hook asks, and the
agent never approves its own prompt).

**GitOps-first rule.** A live `kubectl`/`helm` fix is a last resort. If the workload is managed
by ArgoCD (`k8s argocd` lists it) or by a Helm release that ArgoCD owns, a live edit is reverted
on the next sync and hides the real defect. Fix the source instead:

| What is wrong | Where it is fixed |
|---|---|
| Container resources, probes, env, securityContext defaults | chart template/values in `<charts repo>/<chart>/chart/` |
| Per-environment value (replicas, limits, image tag, feature flag) | `<charts repo>/<chart>/values/<site>/…` or the overlay in `<gitops root>/apps/<app>/overlays/<env>/<stage>/<ctx>/` |
| App enabled/disabled on a context, namespace, project | `<gitops root>/clusters/<env>/<stage>/<ctx>/` |

Repo-level skills own those edits — a GitOps repo typically offers a render/preview command
to see exactly what Argo would apply, plus enable/promote helpers. See `gitops.md`.

**Context names.** A GitOps repo's cluster registry (e.g. `clusters/<env>/<stage>/<ctx>/`)
names ArgoCD clusters / deploy namespaces, *not* kubeconfig contexts; the registry entry records
which kubeconfig context hosts it (the org notes describe your layout). Always pass the kubeconfig
context explicitly.

---

## 0. Orient

```bash
# hook: allow
k8s contexts --md                                   # never hardcode a context; confirm reachability
k8s workload shop deploy/shop-api --context dev-cluster --md
k8s pod shop shop-api-0 --context dev-cluster --md
```

`k8s pod` returns phase, node, QoS, conditions, per-container `state`/`lastState`
(reason, `exitCode`, `OOMKilled`), restart counts, requests/limits, probes, image + pull policy,
pod Warning events, and redacted `--tail` logs (plus `--previous` when restarts > 0). Everything
below reads off those fields.

A `kubectl` client several minors ahead of the server prints a version-skew `WARNING:` on **stderr** — expected
noise, never a finding, never mixed into JSON.

---

## 1. `phase: Pending` — never scheduled

Read `status.conditions[type=PodScheduled].message` and the `FailedScheduling` event.

```bash
# hook: pass
kubectl --context dev-cluster --request-timeout=20s -n shop get pod shop-api-0 \
  -o jsonpath='{.status.conditions[?(@.type=="PodScheduled")].message}{"\n"}'
k8s events --ns shop --warning --since 60m --context dev-cluster --md
```

| Message contains | Cause | Evidence |
|---|---|---|
| `Insufficient cpu`/`memory` | no node has the requests free | `k8s capacity --context dev-cluster --md` (see `capacity.md`) |
| `Insufficient nvidia.com/gpu` | GPU requests exceed free integer GPUs, or the device plugin is not advertising | §7 |
| `had untolerated taint {…}` | taint/toleration mismatch | `kubectl --context dev-cluster get nodes -o json \| jq '.items[]\|{n:.metadata.name,taints:.spec.taints}'` |
| `node(s) didn't match Pod's node affinity/selector` | `nodeSelector`/affinity selects labels no node has | compare with `kubectl --context dev-cluster get nodes --show-labels` |
| `pod has unbound immediate PersistentVolumeClaims` | PVC not Bound | §6 |
| `waiting for first consumer to be created before binding` | benign for `WaitForFirstConsumer` StorageClasses — the PVC binds when the pod schedules; if both wait forever the real cause is elsewhere in this table | `kubectl --context dev-cluster get sc` |
| `node(s) exceed max volume count` / `didn't find available persistent volumes` | CSI limit / no PV | §6 |
| `0/13 nodes are available: … node(s) were unschedulable` | node cordoned | §8 |

**Hand to the user — the hook asks:** the fix is almost always a *requests* or *nodeSelector*
change in the chart values, not a live edit. Only if the cluster is genuinely full:

```bash
# hook: ask — NEVER run; hand to the user
kubectl --context dev-cluster -n shop scale deploy/shop-api --replicas=1
```

## 2. `ImagePullBackOff` / `ErrImagePull`

```bash
# hook: pass
kubectl --context dev-cluster --request-timeout=20s -n shop get pod shop-api-0 \
  -o jsonpath='{range .status.containerStatuses[*]}{.name}{"\t"}{.image}{"\t"}{.state.waiting.message}{"\n"}{end}'
```

Split on the message:
- `manifest unknown` / `not found` → tag does not exist. Check the tag the source pins:
  `grep -rn "tag:" <gitops root>/apps/<app>/overlays/<env>/<stage>/<ctx>/` and the chart's
  `values.yaml`. Fix in git, not in the cluster.
- `unauthorized` / `authentication required` → missing or stale imagePullSecret. Confirm keys only
  (never values): `k8s secret-keys shop regcred --context dev-cluster`, and that the SA references
  it: `kubectl --context dev-cluster -n shop get sa <sa> -o jsonpath='{.imagePullSecrets}'`.
- `dial tcp … i/o timeout` / `no such host` → registry unreachable from that node (air-gapped or
  proxy). Check whether *other* nodes pull the same image fine → node-local networking.
- Pull works but is slow → `imagePullPolicy: Always` on a large image; a values change.

## 3. `CrashLoopBackOff` — started, then died

Read `lastState.terminated.{reason,exitCode,signal,message}` and the **previous** logs.

```bash
# hook: pass
kubectl --context dev-cluster --request-timeout=20s -n shop get pod shop-api-0 \
  -o jsonpath='{range .status.containerStatuses[*]}{.name}{"\t"}{.restartCount}{"\t"}{.lastState.terminated.reason}{"\t"}{.lastState.terminated.exitCode}{"\n"}{end}'
kubectl --context dev-cluster -n shop logs shop-api-0 -c api --previous --tail=100 | k8s redact
```

| exitCode | Meaning | Next |
|---|---|---|
| `0` | process exited cleanly — a one-shot command in a Deployment, or a misread entrypoint | check `command`/`args` vs the chart |
| `1` | application error | previous logs, last 100 lines; look for config/DB/env failures |
| `2` | shell/CLI misuse — bad flag, missing binary in the image | compare entrypoint with the image |
| `137` | SIGKILL — **OOMKilled if `reason: OOMKilled`**, otherwise liveness-probe kill or node pressure | §4 if OOMKilled, §5 if not |
| `139` | SIGSEGV — native crash (CUDA/driver mismatch on GPU pods, see §7) | §7, and the driver version on the node |
| `143` | SIGTERM — graceful shutdown that the app treats as failure, or `terminationGracePeriod` too short | check preStop/graceful handling |
| `126`/`127` | entrypoint not executable / not found | image build problem |

Rules of thumb: restarts climbing steadily with a fixed interval ≈ a dependency that never comes
up (DB, secret, PVC); a single burst of restarts right after a rollout ≈ a bad image or config
revision — compare with `k8s argocd` revision and the Helm history (`gitops.md`).

## 4. `OOMKilled`

`lastState.terminated.reason == OOMKilled`, exit 137.

```bash
# hook: pass
kubectl --context dev-cluster -n shop get pod shop-api-0 \
  -o jsonpath='{range .spec.containers[*]}{.name}{"\t"}{.resources.limits.memory}{"\t"}{.resources.requests.memory}{"\n"}{end}'
k8s promql 'container_memory_working_set_bytes{namespace="shop",pod=~"shop-api.*"}' --context dev-cluster
k8s promql 'max_over_time(container_memory_working_set_bytes{namespace="shop"}[24h])' --context dev-cluster
```

Decide between the two real causes:
- **Limit too low** — working set sits just under the limit and the kill is periodic → raise the
  limit in chart values (`observability.md` for the PromQL shapes; size to 24h max + ~25 %).
- **Leak** — working set grows monotonically between restarts → raising the limit only delays it;
  file it against the app.

A container with a memory *limit* and no *request* gets `Burstable` QoS and is evicted early under
node pressure; a limit == request is `Guaranteed`. Check `status.qosClass`.

## 5. Probe failures (`Unhealthy` events, restarts with no app error)

```bash
# hook: pass
k8s events --ns shop --warning --since 60m --context dev-cluster --md | grep -i unhealthy
kubectl --context dev-cluster -n shop get pod shop-api-0 \
  -o jsonpath='{range .spec.containers[*]}{.name}{"\t"}{.livenessProbe}{"\t"}{.readinessProbe}{"\t"}{.startupProbe}{"\n"}{end}'
```

- Liveness failing while the app logs normal traffic → probe path/port wrong, or
  `initialDelaySeconds`/`failureThreshold` too tight for a slow start (model loading, migrations).
  The fix is a **startupProbe** in the chart, not a bigger liveness delay.
- Readiness failing only → pod stays out of the Service; `kubectl --context C -n NS get endpoints <svc>`
  shows no addresses. Correlate with ingress 503s (ingress class `nginx`).
- Probes killing a GPU pod during CUDA init → §7.

## 6. PVC `Pending` / `FailedMount`

```bash
# hook: pass
kubectl --context dev-cluster -n shop get pvc -o wide
kubectl --context dev-cluster -n shop describe pvc <pvc> | tail -20
kubectl --context dev-cluster get sc                       # csi-nfs is the default StorageClass
k8s events --ns shop --warning --since 60m --context dev-cluster --md
```

- No `storageClassName` and no default SC → Pending forever. dev-cluster's default is
  **`csi-nfs`** (csi-driver-nfs); other contexts differ — check, never assume.
- `FailedMount … mount.nfs: access denied` / `no route to host` → NFS export/permission problem on
  the server, not in Kubernetes. Evidence: the node's kubelet events and which node the pod landed on.
- `volume is already exclusively attached` → `ReadWriteOnce` PVC and a rescheduled pod; check the
  old pod is really gone (`kubectl --context C -n NS get pod -o wide`).
- `WaitForFirstConsumer` → see §1.

## 7. Node `NotReady` / pressure

```bash
# hook: pass
k8s health --context dev-cluster --md
kubectl --context dev-cluster get nodes -o json | jq -r '
  .items[] | [.metadata.name, ([.status.conditions[]|select(.status=="True")|.type]|join(","))] | @tsv'
kubectl --context dev-cluster describe node <node> | sed -n '/Conditions/,/Allocated/p'
```

- `MemoryPressure`/`DiskPressure`/`PIDPressure` True → kubelet is evicting. Find the consumer with
  `k8s capacity --context dev-cluster --md`; on DiskPressure, image/log growth is the usual cause.
- `NotReady` with `KubeletNotReady … network plugin` → Calico on that node; check
  `kubectl --context dev-cluster -n kube-system get pods -o wide | grep <node>`.
- Cordoned (`spec.unschedulable: true`) → someone is draining it.

**Hand to the user — the hook asks:** uncordon/drain/delete-node are all human actions.

```bash
# hook: ask — NEVER run; hand to the user
kubectl --context dev-cluster uncordon <node>
```

## 8. GPU-specific (dev-cluster only)

`nvidia.com/gpu` is an **integer, non-overcommittable** resource — see `capacity.md`.

```bash
# hook: pass
kubectl --context dev-cluster get nodes -o json | jq -r '
  .items[] | select(.status.capacity["nvidia.com/gpu"]) |
  [.metadata.name, .status.capacity["nvidia.com/gpu"], .status.allocatable["nvidia.com/gpu"]] | @tsv'
kubectl --context dev-cluster -n gpu-operator get pods -o wide        # operator + validator + device plugin
kubectl --context dev-cluster -n gpu-operator logs ds/nvidia-device-plugin-daemonset --tail=50 | k8s redact
k8s promql 'DCGM_FI_DEV_GPU_UTIL' --context dev-cluster
```

| Symptom | Cause |
|---|---|
| allocatable `nvidia.com/gpu: 0` on a GPU node | device plugin not running, or the GPU Operator **validator** pod failing — check `nvidia-operator-validator` and `nvidia-driver-daemonset` on that node |
| Pod Pending `Insufficient nvidia.com/gpu` while GPUs look free | fractional request (not allowed — must be a whole number), or GPUs held by a finished-but-not-deleted pod |
| exit 139 / `CUDA error: no kernel image` / `driver version is insufficient` | container CUDA newer than the node driver — an image/values fix |
| `DCGM_FI_DEV_GPU_UTIL` absent | dcgm-exporter down; GPU dashboards blind, not a workload fault |

## 9. Platform hints

**KubeRay** (`raycluster` is a valid `k8s workload` kind):

```bash
# hook: pass
k8s workload <ns> raycluster/<name> --context dev-cluster --md
kubectl --context dev-cluster -n <ns> get rayclusters -o json | jq '.items[]|{n:.metadata.name,state:.status.state,ready:.status.availableWorkerReplicas,desired:.status.desiredWorkerReplicas}'
```
Head pod Pending blocks the whole cluster; workers Pending on `Insufficient nvidia.com/gpu` is §8.
`state: unhealthy` with a healthy head usually means workers cannot reach the head's GCS port —
check the head Service endpoints.

**JupyterHub**: user pods are created by the hub. A user pod Pending on GPU is §8; `hub` CrashLoop
on a DB error usually points at its PVC (§6). The `hub` and `proxy` pods carry the real logs, not
the singleuser pod.

**CloudNativePG**: the `Cluster` CR is the truth, not the pods.

```bash
# hook: pass
kubectl --context dev-cluster -n <ns> get clusters.postgresql.cnpg.io -o json | jq '.items[]|{n:.metadata.name,instances:.status.instances,ready:.status.readyInstances,primary:.status.currentPrimary,phase:.status.phase}'
```
`phase` stuck on `Waiting for the instances to become active` → the instance pods' PVCs (§6).
Never restart a primary by hand; CNPG does switchovers — that is a human decision on the CR.

---

## Stopping rule

Three unresolved hypotheses is the limit — report Evidence + the best hypothesis with a confidence
and say what was not verified, rather than widening the search. Big log/JSON dumps belong in the
`k8s-triage` agent, not in the main context: write them to `$SCRATCH/*.json` with `--json` and
`jq` the fields you need.
