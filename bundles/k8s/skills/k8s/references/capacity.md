# Capacity: requests vs usage, GPUs, quotas

```bash
# hook: allow
k8s capacity --context dev-cluster --md            # whole cluster, per node
k8s capacity --ns shop --context dev-cluster --md # + that namespace's quotas
```

## 1. What `k8s capacity` computes

Per node, from `kubectl get nodes -o json` and `kubectl get pods --all-namespaces -o json`
(non-terminal pods only — `Succeeded`/`Failed` excluded):

- `allocatable` for `cpu`, `memory`, `ephemeral-storage`, `nvidia.com/gpu`, `pods`
  (**allocatable**, not `capacity` — the difference is kube/system-reserved, and scheduling uses
  allocatable).
- Σ requests and Σ limits over all containers **plus** `max(initContainers)` per pod, which is how
  the scheduler computes a pod's footprint.
- `requests / allocatable` per resource, and the pod count vs the pod limit (110 by default).
- Live usage from `--raw /apis/metrics.k8s.io/v1beta1/nodes` (metrics-server is installed on
  dev-cluster).
- Any `ResourceQuota` in scope (`--ns`), as `used` vs `hard`.

Findings fire at **> 90 %** of allocatable for any resource, on `nvidia.com/gpu` fully allocated,
and on a quota at its `hard` limit.

## 2. Requests vs limits vs live usage — read them separately

Three different numbers, three different failure modes:

| Number | Governs | Symptom when wrong |
|---|---|---|
| **requests** | scheduling only | Pending `Insufficient cpu/memory` although nodes look idle (over-requested), or nodes oversubscribed and thrashing (under-requested) |
| **limits** | enforcement | CPU throttling; memory limit ⇒ `OOMKilled` (`triage.md` §4) |
| **live usage** | reality | the gap to requests is the waste |

A cluster can be 95 % *requested* and 20 % *used* — that is a requests-hygiene problem, and the fix
is values in `helm-charts`/`gitops`, never a live edit. Say which of the three is the
constraint in any capacity finding.

Raw view of the same data:

```bash
# hook: pass
kubectl --context dev-cluster get nodes -o json | jq -r '
  .items[] | [.metadata.name, .status.allocatable.cpu, .status.allocatable.memory,
              (.status.allocatable["nvidia.com/gpu"] // "0"), (.spec.unschedulable // false)] | @tsv'
kubectl --context dev-cluster get --raw /apis/metrics.k8s.io/v1beta1/nodes | jq -r '
  .items[] | [.metadata.name, .usage.cpu, .usage.memory] | @tsv'
kubectl --context dev-cluster top nodes           # same data, human units
kubectl --context dev-cluster -n shop top pods --containers
```

QoS matters under pressure: `Guaranteed` (requests == limits, all containers) is evicted last,
`Burstable` next, `BestEffort` (no requests/limits) first. `k8s pod` prints `qosClass`.

## 3. GPU scheduling

`nvidia.com/gpu` is an **extended resource**: integer only, **no overcommit, no fractional
requests, and requests must equal limits**. The scheduler does simple bin-packing on whole GPUs.

```bash
# hook: pass
kubectl --context dev-cluster get nodes -o json | jq -r '
  .items[] | select(.status.capacity["nvidia.com/gpu"]) |
  [.metadata.name, .status.capacity["nvidia.com/gpu"], .status.allocatable["nvidia.com/gpu"]] | @tsv'
kubectl --context dev-cluster get pods -A -o json | jq -r '
  [.items[] | select(.status.phase=="Running") | .spec.containers[].resources.requests["nvidia.com/gpu"] // "0" | tonumber] | add'
```

Consequences to state plainly when reporting:
- Free GPUs are `Σ allocatable − Σ requested by non-terminal pods`. A pod requesting 2 GPUs needs
  2 free **on one node** — cluster-wide free GPUs are not enough.
- `allocatable nvidia.com/gpu: 0` on a GPU node means the NVIDIA device plugin / GPU Operator
  validator is unhealthy, not that the GPUs are busy (`triage.md` §8).
- Idle-but-held GPUs (a notebook or Ray worker sitting at 0 % utilisation) are the usual cause of
  "no GPUs available" — prove it with `DCGM_FI_DEV_GPU_UTIL` before blaming capacity.
- Time-slicing/MIG, if ever enabled by the GPU Operator, changes `capacity` but not the
  integer-only rule.

## 4. Quota headroom

```bash
# hook: pass
kubectl --context dev-cluster -n shop get resourcequota -o json | jq -r '
  .items[] | .metadata.name as $n | .status.hard | to_entries[] |
  [$n, .key, .value] | @tsv'
kubectl --context dev-cluster -n shop get resourcequota -o json | jq '.items[]|{name:.metadata.name,used:.status.used,hard:.status.hard}'
kubectl --context dev-cluster -n shop get limitrange -o yaml
```

A namespace at its quota rejects **pod creation** with `exceeded quota:` on the ReplicaSet/Job, not
on a pod — so the symptom is "replicas stuck at N−1 with no Pending pod". Check
`kubectl --context C -n NS describe rs <rs> | tail -20` for the quota message. A `LimitRange`
silently injects default requests/limits, which is why a pod can have requests nobody wrote.

## 5. PromQL companions

Rancher Monitoring Prometheus is at `cattle-monitoring-system/rancher-monitoring-prometheus:9090`
(auto-discovered by `k8s promql`; see `observability.md` for the proxy mechanics).

```bash
# hook: allow
k8s promql 'sum by (node) (kube_pod_container_resource_requests{resource="cpu"})' --context dev-cluster
k8s promql 'sum by (node) (kube_pod_container_resource_requests{resource="memory"})' --context dev-cluster
k8s promql 'sum by (namespace) (container_memory_working_set_bytes{container!=""})' --context dev-cluster
k8s promql 'topk(10, rate(container_cpu_usage_seconds_total{container!=""}[5m]))' --context dev-cluster
k8s promql 'avg by (Hostname, gpu) (DCGM_FI_DEV_GPU_UTIL)' --context dev-cluster
k8s promql 'avg by (Hostname, gpu) (DCGM_FI_DEV_FB_USED / DCGM_FI_DEV_FB_FREE)' --context dev-cluster
```

Useful pairs:
- **Waste**: `kube_pod_container_resource_requests{resource="memory"}` vs
  `container_memory_working_set_bytes` for the same namespace — the ratio is the over-request.
- **Throttling**: `rate(container_cpu_cfs_throttled_seconds_total[5m])` > 0 with CPU usage below the
  limit ⇒ the limit is the bottleneck, not the node.
- **Sizing a limit**: `max_over_time(container_memory_working_set_bytes[7d])` + ~25 % headroom.
- **Idle GPUs**: `DCGM_FI_DEV_GPU_UTIL` near 0 on a GPU that `kube_pod_container_resource_requests{resource="nvidia_com_gpu"}` shows as allocated.

Metric availability is not guaranteed — if a query returns an empty vector, say so rather than
inferring zero.
