#!/usr/bin/env bash
# Golden tests for k8s.py, driven entirely by kubectl-stub.sh / helm-stub.sh.
# UPDATE=1 rewrites golden/. Exits non-zero on any failure.
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
CLI="$here/../k8s.py"
FIX="$here/fixtures"
GOLD="$here/golden"
export KUBECTL="$here/kubectl-stub.sh"
export HELM="$here/helm-stub.sh"
export K8S_TIMEOUT=20
export K8S_GITOPS_ROOT="$here/fixtures/gitops"
unset K8S_PROD_RE K8S_CLUSTERS_MD K8S_GITOPS_REPO_MATCH
export HARNESS_CONFIG_JSON=/dev/null   # hermetic: never read a real build/config.json
tmp=$(mktemp -d)
export STUB_LOG="$tmp/stub.log"; : > "$STUB_LOG"
fail=0; cases=0
mkdir -p "$GOLD"

# Normalise everything that moves with the wall clock so the goldens are stable.
norm() {
  python3 - "$1" "$here" <<'PY'
import re, sys
p = sys.argv[1]
t = open(p).read()
t = t.replace(sys.argv[2], "HERE")   # the checkout location never reaches a golden
t = re.sub(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", "TIMESTAMP", t)
t = re.sub(r'("age": )"\d+[smhd]"', r'\1"AGE"', t)
t = re.sub(r"(?m)^\|\s*\d+[smhd]\s*\|", "| AGE |", t)   # leading age column
t = re.sub(r"(?m)\|\s*\d+[smhd]\s*\|$", "| AGE |", t)   # trailing age column
t = re.sub(r'("days_left": )-?\d+', r"\1DAYS", t)
t = re.sub(r"\bin -?\d+ d\b", "in DAYS d", t)
open(p, "w").write(t)
PY
}

record() {  # record <name> <exit> <stdout-file> <stderr-file>
  local name=$1 rc=$2 out=$3 err=$4 g="$tmp/$1.txt"
  { echo "# exit=$rc"; echo "# stderr:"; cat "$err"; echo "# stdout:"; cat "$out"; } > "$g"
  norm "$g"
  cases=$((cases + 1))
  if [ "${UPDATE:-0}" = 1 ]; then cp "$g" "$GOLD/$name.txt"; echo "UPDATED $name"; return; fi
  if [ ! -f "$GOLD/$name.txt" ]; then echo "FAIL $name (no golden — run UPDATE=1)"; fail=1; return; fi
  if diff -u "$GOLD/$name.txt" "$g" > "$tmp/$name.diff"; then echo "PASS $name"
  else echo "FAIL $name"; head -40 "$tmp/$name.diff"; fail=1; fi
}

t() {  # t <name> <expected-exit> <args...>
  local name=$1 exp=$2; shift 2
  python3 "$CLI" "$@" > "$tmp/$name.out" 2> "$tmp/$name.err"; local rc=$?
  [ "$rc" = "$exp" ] || { echo "FAIL $name: exit $rc, expected $exp"; cat "$tmp/$name.err"; fail=1; }
  record "$name" "$rc" "$tmp/$name.out" "$tmp/$name.err"
}

ts() {  # ts <name> <expected-exit> <stdin-file> <args...>
  local name=$1 exp=$2 inp=$3; shift 3
  python3 "$CLI" "$@" < "$inp" > "$tmp/$name.out" 2> "$tmp/$name.err"; local rc=$?
  [ "$rc" = "$exp" ] || { echo "FAIL $name: exit $rc, expected $exp"; cat "$tmp/$name.err"; fail=1; }
  record "$name" "$rc" "$tmp/$name.out" "$tmp/$name.err"
}

# ---------------------------------------------------------------- per-subcommand golden
t contexts-json      1 contexts --json
t contexts-md        1 contexts --md
t contexts-only      0 contexts --only dev-cluster --json
t health-json        1 health --json
t health-md          1 health --md
t health-ns-json     1 health --ns shop --json
t pod-json           1 pod shop shop-api-0 --json
t pod-md             1 pod shop shop-api-0 --md
t workload-json      1 workload shop deploy/shop-api --json
t workload-md        1 workload shop deploy/shop-api --md
t events-json        1 events --json
t events-warning-md  1 events --warning --md
t events-ns-json     1 events --ns shop --warning --since 8h --json
t capacity-json      1 capacity --json
t capacity-md        1 capacity --md
t argocd-json        1 argocd --json
t argocd-md          1 argocd --md
t helm-json          1 helm --json
t helm-md            1 helm --md
t helm-values-json   1 helm --ns shop --values shop --json
t secret-keys-json   0 secret-keys shop shop-db --json
t secret-keys-all-md 0 secret-keys shop --all --md
t promql-json        0 promql up --json
t promql-md          0 promql up --md
t certs-json         1 certs --json
t certs-md           1 certs --md
t audit-json         1 audit --json
t audit-md           1 audit --md
t audit-ns-md        0 audit --ns shop --md
t prod-banner-json   1 health --context prod-cluster --json
t access-unreachable 2 health --context unreachable --json
t access-forbidden   2 health --context forbidden --json
ts secret-keys-stdin 0 "$FIX/secrets-shop.json" secret-keys - --json
ts redact-json       0 "$FIX/helm-values-shop.json" redact
ts redact-text       0 "$FIX/logs-shop-api-0-api-previous.txt" redact

# ------------------------------------------------------------------------- assertions
chk() {  # chk <label> <condition-exit>
  cases=$((cases + 1))
  if [ "$1" = 0 ]; then echo "PASS $2"; else echo "FAIL $2"; fail=1; fi
}

grep -q '\[PROD\]' "$tmp/prod-banner-json.err"; chk $? "prod-cluster banner carries [PROD]"
grep -q 'context=dev-cluster server=v1.26.15+testr1' "$tmp/health-json.err"
chk $? "banner carries context and server version"
grep -q '^context=dev-cluster server=v1.26.15+testr1 ns=shop$' "$tmp/health-ns-json.err"
chk $? "banner carries ns and no [PROD] on a non-prod namespace"

# secrets and credentials never reach stdout
for f in pod-json pod-md workload-json workload-md helm-values-json secret-keys-json \
         secret-keys-all-md secret-keys-stdin redact-json redact-text; do
  if grep -qE 'hunter2|s3cr3t-value|AKIA[0-9A-Z]{16}|BEGIN RSA PRIVATE KEY' "$tmp/$f.out"; then
    echo "FAIL $f leaks a credential"; fail=1
  else
    echo "PASS $f is redacted"
  fi
  cases=$((cases + 1))
done
grep -q 'REDACTED' "$tmp/redact-json.out"; chk $? "redact replaces secret-ish values"
grep -q '"password": 12' "$tmp/secret-keys-json.out"; chk $? "secret-keys prints byte sizes"
grep -q 'never printed' "$tmp/secret-keys-json.out"; chk $? "secret-keys states the value rule"

# ------------------------------------------------------------ harness parameters
K8S_GITOPS_REPO_MATCH=no-such-repo python3 "$CLI" argocd --json > "$tmp/p-match.out" 2>/dev/null
! grep -q '"local_path": "HERE\|"local_path": "/' "$tmp/p-match.out"; chk $? "K8S_GITOPS_REPO_MATCH that matches nothing skips the local-path check"
K8S_GITOPS_ROOT= python3 "$CLI" argocd --json > /dev/null 2> "$tmp/p-noroot.err"
grep -q 'k8s.gitops_root not set' "$tmp/p-noroot.err"; chk $? "unset gitops root prints one note and skips the check"
K8S_CLUSTERS_MD="$tmp/state/clusters.md" python3 "$CLI" contexts --write --json > /dev/null 2>&1
grep -q '^# Clusters' "$tmp/state/clusters.md"; chk $? "contexts --write writes K8S_CLUSTERS_MD"
printf '{"k8s":{"prod_re":"dev","clusters_doc":"%s/cfg/clusters.md"}}' "$tmp" > "$tmp/cfg.json"
HARNESS_CONFIG_JSON="$tmp/cfg.json" python3 "$CLI" health --json > /dev/null 2> "$tmp/p-prod.err"
grep -q '\[PROD\]' "$tmp/p-prod.err"; chk $? "k8s.prod_re from the harness config marks the context [PROD]"
K8S_PROD_RE='^never$' HARNESS_CONFIG_JSON="$tmp/cfg.json" python3 "$CLI" health --json > /dev/null 2> "$tmp/p-env.err"
! grep -q '\[PROD\]' "$tmp/p-env.err"; chk $? "K8S_PROD_RE in the environment wins over the config"
HARNESS_CONFIG_JSON="$tmp/cfg.json" python3 "$CLI" contexts --write --json > /dev/null 2>&1
[ -s "$tmp/cfg/clusters.md" ]; chk $? "k8s.clusters_doc from the harness config is the --write target"

# usage / unknown command
python3 "$CLI" > "$tmp/usage.out" 2>&1; rc=$?
[ "$rc" = 1 ] && grep -q "Deliberately NOT implemented" "$tmp/usage.out"; chk $? "bare k8s prints usage, exit 1"
python3 "$CLI" bogus > "$tmp/bogus.out" 2>&1; rc=$?
[ "$rc" = 1 ] && grep -q "Unknown command" "$tmp/bogus.out"; chk $? "unknown command exits 1"
python3 "$CLI" health -h > "$tmp/h.out" 2>&1; rc=$?
[ "$rc" = 0 ] && grep -q -- "--ns" "$tmp/h.out"; chk $? "k8s health -h works"

# ------------------------------------------------------------------ stub log invariants
bad=$(grep '^kubectl ' "$STUB_LOG" | grep -v '^kubectl config ' | grep -v -- '--context ' | head -3)
[ -z "$bad" ]; chk $? "every kubectl call passes --context"
bad=$(grep '^kubectl ' "$STUB_LOG" | grep -v '^kubectl config ' | grep -v -- '--request-timeout=' | head -3)
[ -z "$bad" ]; chk $? "every kubectl call passes --request-timeout"
bad=$(grep '^helm ' "$STUB_LOG" | grep -v -- '--kube-context ' | head -3)
[ -z "$bad" ]; chk $? "every helm call passes --kube-context"
! grep -q 'use-context' "$STUB_LOG"; chk $? "no call switches the kubeconfig context"
! grep 'secret' "$STUB_LOG" | grep -qE -- '-o[ =]yaml|--output[ =]yaml'; chk $? "no Secret is fetched as yaml"
! grep -qE '\b(exec|attach|cp|debug|port-forward|proxy|apply|delete|patch|edit|scale|create)\b' \
    <(grep '^kubectl ' "$STUB_LOG" | sed 's/--raw [^ ]*//'); chk $? "no mutating or exec-class call"

if [ "${KEEP:-0}" = 1 ]; then echo "artifacts in $tmp"; else rm -rf "$tmp"; fi
if [ $fail -eq 0 ]; then echo "all k8s tests passed ($cases cases)"; else echo "k8s tests FAILED"; fi
exit $fail
