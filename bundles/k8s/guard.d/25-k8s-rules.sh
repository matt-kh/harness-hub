# shellcheck shell=bash

# Section 25 (bundle k8s): kubeconfig, Secret data, cluster and infra mutations.
# rule: kubectl config use-context|set-*|delete-*|rename-context -> deny : kubeconfig is human-managed; pass --context on every command instead (see the k8s rule)
# rule: aws eks update-kubeconfig | eksctl utils write-kubeconfig -> deny : kubeconfig is human-managed; pass --context on every command instead (see the k8s rule)
# rule: kubectl get secret(s) -o yaml|json|jsonpath|template | get --raw .../secrets -> deny : Secret values are never printed; use 'k8s secret-keys NS NAME' or pipe through 'k8s redact' instead
# rule: kubectl create token -> ask : mints a ServiceAccount credential; ask the user, or use read-only k8s commands instead
# rule: kubectl exec|attach|cp|debug|port-forward|proxy -> ask : exec-class; use 'k8s pod' or 'kubectl logs' for read-only triage instead
# rule: kubectl apply|delete|edit|patch|scale|rollout restart|... (no --dry-run=client|server) -> ask : cluster mutation; use --dry-run=server, or hand the command to the user instead
# rule: helm get values|all|manifest -> ask : may print credentials; pipe every clause through 'k8s redact' instead (then allowed)
# rule: helm install|upgrade|uninstall|rollback|test|push|registry login -> ask : release mutation; use 'helm template' read-only, or hand the command to the user instead
# rule: argocd app(set) sync|delete|set|... | flux reconcile|... | eksctl create|... -> ask : GitOps / cluster mutation; change the GitOps repo instead, or hand the command to the user
# rule: pulumi up|destroy|refresh|import | terraform apply|destroy|import -> ask : IaC state mutation; run a preview / plan instead, or hand the command to the user
# never-yields: prints the developer's stored credential (principle 8 exemption; runs even when the repository owns kubernetes)
# rule: kubectl config view --raw -> deny : prints credentials; use plain 'kubectl config view' (redacted) instead
printf '%s' "$flat" | grep -qE "${KC}config\s+view\b[^;&|]*\s--raw(=true)?([[:space:]\"')]|$)" && deny "kubectl config view --raw prints credentials — drop --raw (kubectl redacts by default)"
repo_owns k8s/guard.d/25-k8s-rules kubernetes && return 0   # principle 8: the repository's .harness.toml owns this section or domain kubernetes
# ---- Kubernetes rules (run after the credential clause loop, as before the split) ----
# kubeconfig: raw credentials are denied in the never-yields prelude above; deny context-cluster-user edits
printf '%s' "$flat" | grep -qE "${KC}config\s+(use-context|set-context|set-cluster|set-credentials|set|unset|delete-context|delete-cluster|delete-user|rename-context)\b" && deny "kubeconfig mutation — never switch or edit contexts; pass --context <ctx> on every command"
printf '%s' "$flat" | grep -qE '\baws\s+eks\s+update-kubeconfig\b|\beksctl\s+utils\s+write-kubeconfig\b' && deny "kubeconfig mutation — kubeconfig is human-managed"
# Secret data output: DENY unless piped through the k8s redactor (user decision: values never)
if { printf '%s' "$flat" | grep -qE "${KC}get\b[^;&|]*(^|[[:space:],])secrets?(\.v1)?([[:space:],/]|$)" && printf '%s' "$flat" | grep -qE "$SEC_OUT_RE"; } \
   || printf '%s' "$flat" | grep -qE "${KC}get\s+--raw[= ][\"']?[^;&|\"' ]*/secrets([/?\"' ]|$)"; then
  printf '%s' "$flat" | grep -qE "$REDACT_PIPE_RE" || deny "Secret data output ($(k8s_target)) — Secret values are never printed; use 'k8s secret-keys NS NAME' (keys + sizes) or pipe through 'k8s redact'"
fi
# exec-class + credential minting: ask (agents never run these; the human may approve)
printf '%s' "$flat" | grep -qE "${KC}create\s+token\b" && ask "kubectl create token mints a ServiceAccount credential ($(k8s_target))"
printf '%s' "$flat" | grep -qE "${KC}(exec|attach|cp|debug|port-forward|proxy)\b" && ask "kubectl exec-class command ($(k8s_target)) — read-only triage uses 'k8s pod' / 'kubectl logs'"
# mutations: ask unless --dry-run=client|server. rollout status|history are reads and fall through.
if printf '%s' "$flat" | grep -qE "${KC}(apply|delete|edit|patch|create|replace|scale|drain|cordon|uncordon|taint|label|annotate|set|run|expose|autoscale|certificate|auth\s+reconcile|rollout\s+(restart|undo|pause|resume))\b" \
   && ! printf '%s' "$flat" | grep -qE "$DRY_RE"; then
  ask "kubectl mutation ($(k8s_target))"
fi
# helm: values/all/manifest may embed credentials — promptless only through the redactor
if printf '%s' "$flat" | grep -qE "${HC}get\s+(values|all|manifest)\b"; then
  n_get=$(printf '%s' "$flat" | grep -oE "${HC}get\s+(values|all|manifest)\b" | wc -l)
  n_red=$(printf '%s' "$flat" | grep -oE "$REDACT_PIPE_RE" | wc -l)
  [ "$n_red" -ge "$n_get" ] && allow "helm get values/all/manifest piped through k8s redact"
  ask "helm get values/all/manifest may print credentials ($(k8s_target)) — pipe through 'k8s redact'"
fi
printf '%s' "$flat" | grep -qE "${HC}(install|upgrade|uninstall|delete|rollback|test|push|registry\s+login)\b" && ! printf '%s' "$flat" | grep -qE "$DRY_RE" && ask "helm release mutation ($(k8s_target)) — 'helm template' renders read-only"
printf '%s' "$flat" | grep -qE '\bargocd\s+app(set)?\s+(sync|delete|set|unset|patch|rollback|terminate-op|create)\b' && ask "argocd mutation"
printf '%s' "$flat" | grep -qE '\bflux\s+(reconcile|suspend|resume|create|delete|install|uninstall|bootstrap)\b' && ask "flux mutation"
printf '%s' "$flat" | grep -qE '\beksctl\s+(create|delete|upgrade|scale|update|drain|enable|set|unset)\b' && ask "eksctl mutation"
printf '%s' "$flat" | grep -qE '\bpulumi\s+(up|destroy|refresh|import)\b' && ask "pulumi state mutation ('pulumi preview' is fine)"
printf '%s' "$flat" | grep -qE '\bterraform\s+(apply|destroy|import)\b' && ask "terraform mutation"
