# GitOps: ArgoCD, Helm, Kargo — and which repo to fix

No `argocd` CLI is installed and none is wanted (it would need a login and a token). Everything
here reads the **CRDs** through `kubectl`/`k8s argocd`. On dev-cluster ArgoCD lives in namespace
`argocd`.

## 1. Applications (`argoproj.io/v1alpha1`)

```bash
# hook: allow
k8s argocd --context dev-cluster --md            # apps + appsets + projects, exit 1 if any not Synced+Healthy
```

```bash
# hook: pass
kubectl --context dev-cluster -n argocd get applications -o json | jq -r '
  .items[] | [.metadata.name, .status.sync.status, .status.health.status,
              .spec.source.path, (.spec.source.targetRevision // "HEAD"),
              (.status.sync.revision // "")[0:8]] | @tsv'
```

Fields that matter:

| Field | Read it for |
|---|---|
| `status.sync.status` | `Synced` / `OutOfSync` / `Unknown` — git vs cluster |
| `status.health.status` | `Healthy` / `Progressing` / `Degraded` / `Missing` / `Suspended` |
| `status.operationState.phase` | `Running` / `Succeeded` / `Failed` / `Error` of the last sync, plus `.message` — the actual apply error |
| `status.operationState.syncResult.revision` | the git SHA that was applied (≠ `spec.source.targetRevision`) |
| `status.conditions[]` | `ComparisonError`, `InvalidSpecError`, `SyncError`, `OrphanedResourceWarning` — read `.message` verbatim |
| `spec.source.{repoURL,path,targetRevision}` | which repo/path/branch is the source of truth |
| `spec.syncPolicy.automated.{prune,selfHeal}` | `selfHeal: true` ⇒ **any live edit is reverted**; `prune: false` ⇒ deleted-in-git resources linger |
| `status.resources[]` | per-resource `status` + `health` — the one Degraded child is here |

Drill into the failing child and the apply error:

```bash
# hook: pass
kubectl --context dev-cluster -n argocd get application <app> -o json | jq '{
  phase: .status.operationState.phase,
  message: .status.operationState.message,
  conditions: .status.conditions,
  bad: [.status.resources[] | select((.status // "") != "Synced" or (.health.status // "Healthy") != "Healthy")]}'
```

Common readings:
- `OutOfSync` + `Healthy` → git moved ahead (or a live drift) and auto-sync is off/ paused. Diff is
  in `status.resources[].status`; reproduce locally with `/render-overlay <app> <env>/<stage>/<ctx>`
  in `<gitops root>`.
- `Synced` + `Degraded` → git is applied and the workload is broken ⇒ this is a **triage** problem
  (`triage.md`), not a GitOps one.
- `Unknown` + `ComparisonError` → Argo cannot render the source: bad kustomize/helm values, missing
  chart version, unreachable repo. `.message` names the file.
- `Missing` → the resource was never created (namespace absent, AppProject restriction, CRD missing).

`spec.source.path` maps straight to `<gitops root>/<path>` — Read/Grep it before drawing
conclusions.

## 2. ApplicationSets

An app that "should exist and doesn't" is almost always an ApplicationSet generator that did not
produce it.

```bash
# hook: pass
kubectl --context dev-cluster -n argocd get applicationsets -o json | jq -r '
  .items[] | {name: .metadata.name,
              generators: [.spec.generators[] | keys[]],
              conditions: [.status.conditions[]? | {type,status,message}]}'
```

- `spec.generators[]` — `git` (files/directories under the repo), `clusters` (registered Argo
  clusters, matched by label), `list`, `matrix`/`merge` (nested — read the inner generators).
- `spec.template.metadata.name` — the naming scheme; a missing app usually means the generator's
  input file is missing or a label does not match.
- `status.conditions[]` — `ErrorOccurred`/`ParametersGenerated` with the real reason.
- `spec.syncPolicy.applicationsSync: create-only|create-update|create-delete` — governs whether
  editing the appset can remove live Applications.

Example layout (adapt to your GitOps repo at `<gitops root>`; the org notes describe the
real one): the generators read `clusters/<environment>/<stage>/<context>/` — one
directory per **ArgoCD cluster / deploy namespace**, with `cluster.yaml` (`name`, `environment`,
`stage`, `context`, `cluster`, `owner`, `labels`) and `apps/<app>.yaml` opt-ins. Use
`/debug-appset <env>[/<stage>[/<ctx>]]` there rather than reasoning about generators by hand.

> **`<context>` ≠ kubeconfig context.** A registry directory name is the ArgoCD cluster / deploy
> namespace name; the kubeconfig context that actually hosts it is recorded in the registry entry
> (e.g. `cluster:` in its `cluster.yaml`). Resolve it there before running anything with `--context`.

## 3. AppProjects

When a sync fails with "not permitted", the restriction is in the project:

```bash
# hook: pass
kubectl --context dev-cluster -n argocd get appprojects -o json | jq '.items[]|{
  name: .metadata.name, sourceRepos: .spec.sourceRepos, destinations: .spec.destinations,
  clusterResourceWhitelist: .spec.clusterResourceWhitelist,
  namespaceResourceBlacklist: .spec.namespaceResourceBlacklist, roles: [.spec.roles[]?.name]}'
```

`destinations` (server + namespace globs), `sourceRepos`, and the cluster-resource whitelist are
the three that bite. Projects are defined in `<gitops root>/projects/<environment>/`.

## 4. Helm release states

```bash
# hook: allow
k8s helm --ns shop --context dev-cluster --md
k8s helm --ns shop --values shop --context dev-cluster     # values, redacted by the CLI
```

```bash
# hook: pass
helm --kube-context dev-cluster -n shop list -a -o json | jq -r '.[]|[.name,.status,.chart,.app_version,.updated]|@tsv'
helm --kube-context dev-cluster -n shop history shop -o json | jq -r '.[]|[.revision,.status,.chart,.description]|@tsv'
helm --kube-context dev-cluster -n shop status shop -o json | jq '{status:.info.status,desc:.info.description}'
```

| Status | Meaning | Action |
|---|---|---|
| `deployed` | current, healthy release | — |
| `failed` | the last install/upgrade errored; the previous revision's objects may still be live | read `history` `description` for the error; fix the chart/values in git |
| `pending-install` | install interrupted (helm killed, timeout) — **release lock held** | human runs a rollback/uninstall |
| `pending-upgrade` | upgrade interrupted — **lock held**, further upgrades fail with "another operation is in progress" | human runs `helm rollback` |
| `pending-rollback` | rollback interrupted — same lock | same |
| `superseded` | an older revision, normal in `history` | — |
| `uninstalling` | delete in progress or stuck (finalizers) | check the release's resources |

**Stuck `pending-*` lock — hand to the user; the hook asks:**

```bash
# hook: ask — NEVER run; hand to the user
helm --kube-context dev-cluster -n shop rollback shop <last-deployed-revision>
```

Pick `<last-deployed-revision>` from `helm history` (the newest `deployed` row). If the release is
ArgoCD-managed, prefer letting Argo re-sync after the git fix over a manual rollback — say so.

`helm get values|all|manifest` may inline credentials: the hook asks unless piped through
`| k8s redact`, and `k8s helm --values NAME` does it for you. `helm template` renders read-only and
is always fine; `helm --dry-run=client|server` is exempt from the mutation ask.

## 5. Kargo (only when the CRDs exist)

dev-cluster has **no Kargo CRDs** as of 2026-09-23 — `k8s argocd` prints `kargo: CRDs not installed`
and that is not a finding. Check before reading anything Kargo-shaped:

```bash
# hook: pass
kubectl --context dev-cluster get crd -o name | grep kargo.akuity.io || echo "no kargo CRDs"
kubectl --context dev-cluster -n <kargo-ns> get stages -o json | jq '.items[]|{
  name:.metadata.name, phase:.status.phase, current:.status.currentFreight.id,
  health:.status.health.status, lastPromo:.status.lastPromotion.name}'
kubectl --context dev-cluster -n <kargo-ns> get promotions -o json | jq '.items[]|{
  name:.metadata.name, stage:.spec.stage, freight:.spec.freight, phase:.status.phase, message:.status.message}'
kubectl --context dev-cluster -n <kargo-ns> get freight -o json | jq '.items[]|{
  id:.metadata.name, images:[.images[]?|{repo:.repoURL,tag:.tag}], commits:[.commits[]?|{repo:.repoURL,id:.id}]}'
```

Stage `phase`: `NotApplicable` / `Steady` / `Promoting` / `Verifying` / `Failed`. A stage stuck in
`Promoting` usually has a failed Promotion whose `status.message` names the git or Argo step.
Promotion config in `<gitops root>/kargo/<env>/` has **no skill** — it is hand-edited there.

## 6. Which repo to fix

| Symptom | Fix in |
|---|---|
| Template bug, missing probe/resource block, wrong label selector | `<charts repo>/<chart>/chart/` (`templates/`, `values.yaml`, `values.schema.json`) |
| Default value wrong for every environment | same chart's `values.yaml` |
| Value wrong for one environment/site | `<charts repo>/<chart>/values/<site>/…` |
| Value wrong for one context only | `<gitops root>/apps/<app>/overlays/<env>/<stage>/<ctx>/` |
| Chart version pin / image tag promotion | the pin in `<gitops root>` (`/promote`) |
| App should (not) run on a context | `<gitops root>/clusters/<env>/<stage>/<ctx>/apps/<app>.yaml` (`/enable-app`) |
| New context | `<gitops root>/clusters/…` (`/add-context`) |
| New app for an existing chart | `<gitops root>/apps/<app>/` (`/new-app`) |
| ArgoCD cannot render / permission denied | `argocd/` appsets or `projects/<env>/` in gitops |

**This skill never edits those repos.** It reads them (Read/Grep) to explain a live symptom and
then names the file and the change. The repo-level skills of those repos (validate / render / promote / enable helpers, whatever
they provide) own the edits, under the normal ticket → MR flow — and a GitOps repo may carry its
own guard hook that blocks cluster-mutating commands outright.
