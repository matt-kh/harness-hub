---
name: k8s
description: >-
  Read-only Kubernetes operator client for every context in the user's kubeconfig via the
  `k8s` CLI and explicit-context kubectl. Use when the user
  mentions a cluster, context, namespace, pod, node, deployment, PVC, ingress, Helm release, ArgoCD
  app, Kargo stage, GPU scheduling, cluster capacity, certificates, cluster health or "why is X
  failing/pending/crashlooping". Never mutates, never switches kubeconfig context, never prints
  Secret values.
model: {{ core.model_policy.execute }}
---

# Kubernetes (read-only operator client)

Generic client for every context in the user's kubeconfig.

**Step 0 — repository-level harness (principle 8).** This is a user-level skill. Read the
repository's declaration first:

```bash
harness repo owns k8s/skills/k8s   # rc 0 = owned (prints why) → stop; rc 1 = carry on
```

If it is owned (by id or by its domain `kubernetes`), or the repository ships its own skill for
the same workflow, this skill yields: say so in one line, name the repository-level skill or
convention, and stop — nothing below runs and nothing is merged. If the repository owns the
*workflow* but not the client, stay available as the plain client underneath it. Never edit
the repository's harness to fit this skill. `harness repo` explains everything the
repository declares and any `.claude/skills|agents` name collisions.
A repository's own GitOps or cluster skill (e.g. a GitOps repo's `/render-overlay` or
`/promote`) owns the *edit* — this one stays the read-only client that explains what the
cluster is actually doing. `infra-architect` stays design-only and is not a runtime tool.

`<gitops root>` below is the local checkout of your GitOps repo, configured as `k8s.gitops_root`
(`K8S_GITOPS_ROOT`); `k8s argocd` prints the resolved `local_path` of every Application, and the
org notes name the repo.

## Tooling

- **`k8s` CLI** (this skill's `scripts/k8s.py`, on PATH) — first choice for everything. It does the
  JSON heavy lifting so multi-MB dumps never enter the context.
- **Raw `kubectl`** for anything the CLI does not cover — always
  `kubectl --context C --request-timeout=20s … -o json | jq …`.
- **`helm --kube-context C …`** for release detail (`list -a`, `history`, `status`, `template`).
- **Agents** for anything that needs to read a lot: `k8s-triage` (incident) and `k8s-auditor`
  (posture). Hand them the context/namespace/symptom; they return a summary, not the dumps.

Run bare `k8s` for the full command list. Common:

```bash
# hook: allow
k8s contexts [--write] [--only a,b]          # ALWAYS run first on a new cluster task
k8s health --context dev-cluster [--ns NS]
k8s pod NS POD --context dev-cluster
k8s workload NS deploy/NAME --context dev-cluster       # deploy|sts|ds|job|cronjob|rs|raycluster
k8s events --context dev-cluster [--ns NS] [--warning] [--since 60m]
k8s capacity --context dev-cluster [--ns NS]
k8s argocd --context dev-cluster
k8s helm --context dev-cluster [--ns NS] [--values NAME]
k8s secret-keys NS NAME --context dev-cluster           # keys + byte sizes only; also `NS --all`, or `-` from stdin
k8s redact                                              # stdin filter
k8s promql 'up' --context dev-cluster [--svc NS/NAME:PORT] [--range 1h --step 60s]
k8s certs --context dev-cluster
k8s audit --context dev-cluster [--ns NS]
```

Global flags on every subcommand: `--context CTX` (defaults to the current context — **pass it
anyway, always**), `--json|--md`, `--timeout 20`, `--max-items 50`, `--max-bytes N`, `--tail 50`.

## Contract & rules

- **Exit codes**: `0` clean · `1` findings were reported (not an error — read them) · `2` access
  error (unreachable, `Unauthorized`, TLS/SAN mismatch, context not found). On exit 2 name the
  context and the error line; do not retry other contexts hoping one works.
- **Run `k8s contexts` first and never hardcode a context.** Contexts come and go, and some may be
  broken (Unauthorized, TLS SAN mismatch) — `k8s contexts` shows which; the org notes list the
  known-broken ones. `--write` regenerates the clusters doc (`{{ k8s.clusters_doc }}`) — only on
  explicit request.
- **`--context` on every single command**, `k8s` and `kubectl` and `helm` alike. `kubectl config
  use-context` is **denied**: the kubeconfig is shared with the user's shell and is theirs.
- **Banner** on stderr: `context=<ctx> server=<ver> [ns=<ns>] [PROD]`. Quote the context in every
  answer. `[PROD]` means the remediation you produce is a **suggestion for the human**, stated with
  its blast radius — never something you try to run.
- **Output caps.** `--max-items 50` / `--max-bytes` truncate with a note. When something is genuinely
  big: `k8s <cmd> --json > "$SCRATCH/x.json"` then `jq` the fields you need. Never paste a full
  `-o json` of a namespace or a full log dump into the context — that is what the agents are for.
- **Secrets: keys and sizes, never values.** `k8s secret-keys NS NAME` (or `--all`, or `-` from
  stdin). Never `get secret … -o yaml|json|jsonpath|go-template|custom-columns`, never
  `get --raw …/secrets/…`, never `base64 -d` on Secret data. The hook denies all of it unless it is
  piped to `| k8s redact` or `| k8s secret-keys -`.
- **The kubeconfig is never read.** No `cat`/`grep`/`yq` on `~/.kube/*` or `$KUBECONFIG`, no
  `kubectl config view --raw` — both are denied, and the Read tool is denied on `~/.kube/**`. Use
  `k8s contexts` or `kubectl config get-contexts`.
- A kubectl client several minors ahead of the server prints a version-skew `WARNING:` on
  **stderr**. Expected noise, never a finding; never merge it into stdout (it would break JSON
  parsing).
- Guard-hook decisions (the hook wins over `permissions.allow` — do not try to route around it):

  | Command | Decision | Rationale |
  |---|---|---|
  | `k8s <any subcommand>` | `permissions.allow` | read-only by construction |
  | `kubectl get/describe/logs/top/events/diff/api-versions/version/cluster-info/wait`, `auth can-i`, `auth whoami`, `rollout status\|history`, `config get-contexts\|current-context\|get-clusters\|get-users`, `get --raw …` | allow | reads |
  | `helm list/history/status/template/get notes\|hooks\|metadata/env/version/repo list/search` | allow | reads |
  | `kubectl apply\|delete\|edit\|patch\|create\|replace\|scale\|drain\|cordon\|uncordon\|taint\|label\|annotate\|set\|run\|expose\|autoscale\|certificate\|auth reconcile\|rollout restart\|undo\|pause\|resume` | **ask** (reason carries `context=… ns=… [PROD]`) | mutation — hand it to the user instead |
  | any of those with `--dry-run=client\|server` | allow | renders only (`--dry-run=none` is **not** a dry run) |
  | `kubectl exec\|attach\|cp\|debug\|port-forward\|proxy` | **ask** | exec-class; the agent never runs these |
  | `kubectl create token` | **ask** | mints a ServiceAccount credential |
  | `helm install\|upgrade\|uninstall\|rollback\|test\|push`, `argocd app sync\|…`, `flux reconcile\|…`, `eksctl …`, `pulumi up\|destroy\|refresh`, `terraform apply\|destroy` | **ask** | mutation |
  | `helm get values\|all\|manifest` | **ask** | may inline credentials |
  | same **piped through `\| k8s redact`** | allow | the redactor lifts the gate |
  | `kubectl get secret … -o yaml\|json\|jsonpath\|go-template\|custom-columns`, `get --raw …/secrets` | **deny** | unless piped to `\| k8s redact` or `\| k8s secret-keys -` |
  | `kubectl config use-context\|set-*\|unset\|delete-*\|rename-context`, `aws eks update-kubeconfig` | **deny** | kubeconfig is human-managed |
  | `kubectl config view --raw`, `cat\|grep\|yq\|… ~/.kube/*` or `$KUBECONFIG`, Read tool on `~/.kube/**` | **deny** | those files hold cluster credentials |

## Procedure

**Step 0 — Orient.** Never assume which cluster.

```bash
# hook: allow
k8s contexts --md                 # reachability, server version, node count, PROD flag
```

Resolve the target: the user's words → a kubeconfig context. If they name a GitOps context
(an ArgoCD cluster / deploy-namespace name from the GitOps repo), that is **not** a kubeconfig
context — resolve it from the GitOps repo's cluster registry under `<gitops root>` (the org
notes say where the registry lives and how names map). Ask if it is still ambiguous.

**Step 1 — Health sweep.** Always before drilling in; it reframes half of all questions.

```bash
# hook: allow
k8s health --context dev-cluster --md
k8s health --context dev-cluster --ns shop --md
```

Covers node conditions, non-Running pods, restart storms, Pending PVCs, recent Warning events,
failed Jobs, ArgoCD apps not Synced+Healthy, Helm releases not `deployed`, PDBs blocking eviction,
apiserver cert expiry.

**Step 2 — Drill into the symptom.** Follow `references/triage.md` — it is a decision tree keyed on
exactly these outputs.

```bash
# hook: allow
k8s workload shop deploy/shop-api --context dev-cluster --md
k8s pod shop shop-api-0 --context dev-cluster --md
k8s events --ns shop --warning --since 60m --context dev-cluster --md
```

```bash
# hook: pass
kubectl --context dev-cluster --request-timeout=20s -n shop logs deploy/shop-api --tail=50 | k8s redact
kubectl --context dev-cluster --request-timeout=20s -n shop get pod shop-api-0 -o json | jq '.status.containerStatuses'
```

Resource-shaped symptoms (Pending, OOMKilled, GPU) → `references/capacity.md` and
`references/observability.md`:

```bash
# hook: allow
k8s capacity --context dev-cluster --md
k8s promql 'container_memory_working_set_bytes{namespace="shop"}' --context dev-cluster
```

**Step 3 — Correlate with GitOps.** A live symptom nearly always has a source-of-truth cause, and a
live fix on an auto-synced app is reverted. `references/gitops.md`.

```bash
# hook: allow
k8s argocd --context dev-cluster --md
k8s helm --ns shop --context dev-cluster --md
```

Then Read/Grep the source: `spec.source.path` → `<gitops root>/<path>`, chart → the chart
repo the Application points at (see the org notes for local checkout paths). **Never edit those
repos from this skill** — name the file and the change, and point at the repo-level skill that
makes it.

**Step 4 — Report.** Context (and `[PROD]`) · what is broken · the evidence (command + the field
that proves it) · root cause with a confidence · **remediation for the human**, numbered, each with
its `--context`, its blast radius, and the GitOps alternative · what was not verified. Stop after
three unresolved hypotheses and say so.

Remediations are written out for the user to run, never executed:

```bash
# hook: ask — NEVER run; hand to the user
kubectl --context dev-cluster -n shop rollout restart deploy/shop-api
helm --kube-context dev-cluster -n shop rollback shop 3
```

## Deliberately not implemented

Not gaps — decisions. Do not work around them with raw `kubectl`: the hook prompts or
denies, and routing around a prompt is the one thing that is never acceptable. Tell the user what to
run instead.

- **Every mutation.** apply/delete/edit/patch/scale/drain/label/rollout restart, `helm
  install|upgrade|uninstall|rollback`, `argocd app sync`, `flux reconcile`, `eksctl`, `pulumi up`,
  `terraform apply`. The agent produces the command; the human runs it.
- **Exec-class as an agent action**: `exec`, `attach`, `cp`, `debug`, `port-forward`, `proxy`. Use
  `k8s pod` and `kubectl logs`; reach Prometheus/Grafana/kubelet through the apiserver proxy
  (`observability.md`), not a port-forward.
- **`kubectl create token`** and any other credential minting.
- **Secret values**, in any encoding, including `base64 -d` of a jsonpath. `k8s secret-keys` or
  `| k8s redact` only.
- **Reading, switching or editing the kubeconfig**, including `kubectl config view --raw` and
  `aws eks update-kubeconfig`. Contexts come from `k8s contexts`; `--context` is passed explicitly.
- **`logs -f`** and any other follow/watch that never returns. Bound with `--tail`/`--since`.
- **Writes to Prometheus, Grafana or Alertmanager** (no dashboard/alert/silence creation), and no
  `argocd` CLI login/install — ArgoCD is read through its CRDs.
- **AWS/EKS read surface** (`aws eks describe-*`, eksctl reads): Kubernetes API only in v1.
- **Editing the chart or GitOps repos** (the GitOps checkout and friends): read-only here; the
  repo-level skills own edits under the normal ticket → MR flow.

**v2 backlog** (not built): `k8s rbac [--as]`, `k8s deprecations`, `k8s images`, `k8s diff NS KIND NAME`.

## References

`references/triage.md` (symptom decision tree) · `references/gitops.md` (ArgoCD/Helm/Kargo, which
repo to fix) · `references/capacity.md` (requests vs usage, GPUs, quotas) ·
`references/security-audit.md` (severity rubric, PSA, RBAC, deprecated APIs) ·
`references/observability.md` (PromQL/Grafana/kubelet via the apiserver proxy, log rules) ·
`{{ k8s.clusters_doc }}` — **generated** by `k8s contexts --write`, never hand-edited; regenerate it
rather than trusting a stale row.
