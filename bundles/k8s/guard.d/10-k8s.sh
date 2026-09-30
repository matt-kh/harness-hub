# shellcheck shell=bash

# Section 10 (bundle k8s): Kubernetes definitions only (kubectl/helm verb prefixes, dry-run,
# Secret-output flags, the redactor pipe, k8s_target for reasons). The rules live in
# 25-k8s-rules.sh so they keep running after the credential clause loop (order is load-bearing).
# (definitions only: no rules in this section; they are shared by 25-k8s-rules.sh)
# ---- Kubernetes / kubeconfig ---------------------------------------------------------
GUARD_KUBECTL="${GUARD_KUBECTL:-kubectl}"
PROD_RE="${K8S_PROD_RE:-(^|[-_./:])(prod|production)([-_./:]|\$)}"
KC='\bkubectl(\s+--?[a-zA-Z][a-zA-Z0-9-]*(=\S+|\s+[^ -]\S*)?)*\s+'   # kubectl + any global flags, then the verb
HC='\bhelm(\s+--?[a-zA-Z][a-zA-Z0-9-]*(=\S+|\s+[^ -]\S*)?)*\s+'
DRY_RE='\s--dry-run(=(client|server))?(\s|$)'                          # anchored: --dry-run=none is NOT a dry run
SEC_OUT_RE='(^|\s)(-o|--output)[= ]?(yaml|json|jsonpath|jsonpath-as-json|jsonpath-file|go-template|go-template-file|custom-columns|custom-columns-file|template)\b|(^|\s)--template([= ]|$)'
REDACT_PIPE_RE='\|\s*(python3\s+)?\S*k8s(\.py)?\s+(redact|secret-keys)\b'
k8s_target() {  # -> "context=<ctx> [ns=<ns>] [PROD]" from --context/--kube-context/-n, else kubeconfig current-context
  local c n p=""; c=$(flag_val '--context|--kube-context' "$flat"); n=$(flag_val '-n|--namespace' "$flat")
  [ -n "$c" ] || c=$(hn_timeout 5 "$GUARD_KUBECTL" config current-context 2>/dev/null)
  printf '%s\n%s\n' "$c" "$n" | grep -qiE "$PROD_RE" && p=" [PROD]"
  printf 'context=%s%s%s' "${c:-unknown}" "${n:+ ns=$n}" "$p"
}
