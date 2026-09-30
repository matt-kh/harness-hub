#!/usr/bin/env bash
# kubectl stub for the k8s CLI tests. Answers from tests/fixtures/ only — no network,
# no kubeconfig, no real cluster. Every invocation is appended to $STUB_LOG as
# `kubectl <args>` so run.sh can assert the call invariants.
#
#   --context unreachable  -> "Unable to connect ... i/o timeout", exit 1
#   --context forbidden    -> "Error from server (Forbidden): ...", exit 1
#   anything without a fixture -> "stub: no fixture for: <args>", exit 1
set -u
here=$(cd "$(dirname "$0")" && pwd)
FIX="$here/fixtures"
[ -n "${STUB_LOG:-}" ] && printf 'kubectl %s\n' "$*" >> "$STUB_LOG"

emit() {  # cat a fixture, expanding @@NOW@@ / @@NOW-<n>m@@ / @@NOW+<n>d@@ placeholders
  local f="$FIX/$1"
  if [ ! -f "$f" ]; then echo "stub: missing fixture $1" >&2; exit 1; fi
  if grep -q '@@NOW' "$f"; then
    python3 -c '
import datetime, re, sys
t = open(sys.argv[1]).read()
now = datetime.datetime.now(datetime.timezone.utc)
U = {"m": "minutes", "h": "hours", "d": "days"}
def rep(m):
    if not m.group(1):
        d = datetime.timedelta(0)
    else:
        d = datetime.timedelta(**{U[m.group(3)]: int(m.group(2))})
        if m.group(1) == "-":
            d = -d
    return (now + d).strftime("%Y-%m-%dT%H:%M:%SZ")
sys.stdout.write(re.sub(r"@@NOW(?:([+-])(\d+)([mhd]))?@@", rep, t))
' "$f"
  else
    cat "$f"
  fi
}

ctx=""; rest="$*"
if [ "${1:-}" = "--context" ]; then ctx="${2:-}"; shift 3 2>/dev/null || shift $#; rest="$*"; fi

case "$ctx" in
  unreachable)
    echo "Unable to connect to the server: dial tcp 192.0.2.1:6443: i/o timeout" >&2
    exit 1 ;;
  forbidden)
    echo "Error from server (Forbidden): pods is forbidden: User \"stub\" cannot list resource \"pods\" in API group \"\" at the cluster scope" >&2
    exit 1 ;;
esac

case "$rest" in
  "config current-context")                     echo "dev-cluster" ;;
  "config view -o json")                        emit config-view.json ;;
  "version -o json")
    echo "WARNING: version difference between client (1.32) and server (1.26) exceeds the supported minor version skew of +/-1" >&2
    emit version.json ;;

  "get nodes -o json")                          emit nodes.json ;;
  "get pods -A -o json")                        emit pods.json ;;
  "get pods -n shop -o json")                  emit pods-shop.json ;;
  "get pods -n shop -l app=shop-api -o json") emit pods-shop-api.json ;;
  "get pod shop-api-0 -n shop -o json")       emit pod-shop-api-0.json ;;
  "get deployments.apps shop-api -n shop -o json") emit deploy-shop-api.json ;;
  "get replicasets.apps -n shop -l app=shop-api -o json") emit rs-shop-api.json ;;

  "get pvc -A -o json"|"get pvc -n shop -o json")     emit pvcs.json ;;
  "get jobs -A -o json"|"get jobs -n shop -o json")   emit jobs.json ;;
  "get pdb -A -o json"|"get pdb -n shop -o json")     emit pdbs.json ;;

  "get events -A --field-selector type=Warning -o json")     emit events-warning.json ;;
  "get events -n shop --field-selector type=Warning -o json") emit events-shop-warning.json ;;
  "get events -A -o json")                                   emit events-all.json ;;
  "get events -n shop -o json")                             emit events-shop.json ;;
  "get events -n shop --field-selector involvedObject.name=shop-api-0 -o json")
    emit events-pod-shop-api-0.json ;;

  "get applications.argoproj.io -A -o json"|"get applications.argoproj.io -n shop -o json")
    emit applications.json ;;
  "get applicationsets.argoproj.io -A -o json")  emit applicationsets.json ;;
  "get appprojects.argoproj.io -A -o json")      emit appprojects.json ;;
  "get crd applications.argoproj.io -o json")    echo '{"kind":"CustomResourceDefinition"}' ;;
  "get crd stages.kargo.akuity.io -o json")
    echo 'Error from server (NotFound): customresourcedefinitions.apiextensions.k8s.io "stages.kargo.akuity.io" not found' >&2
    exit 1 ;;

  "get certificates.cert-manager.io -A -o json"|"get certificates.cert-manager.io -n shop -o json")
    emit certificates.json ;;
  "get csr -o json")                             emit csrs.json ;;

  "get secret shop-db -n shop -o json")        emit secret-shop-db.json ;;
  "get secrets -n shop -o json")                emit secrets-shop.json ;;

  "get resourcequotas -A -o json"|"get resourcequotas -n shop -o json") emit quotas.json ;;
  "get namespaces -o json")                      emit namespaces.json ;;
  "get serviceaccounts -A -o json"|"get serviceaccounts -n shop -o json")
    emit serviceaccounts.json ;;
  "get svc -A -o json")                          emit svc-all.json ;;

  "get --raw /apis/metrics.k8s.io/v1beta1/nodes") emit metrics-nodes.json ;;
  "get --raw /api/v1/namespaces/monitoring/services/rancher-monitoring-prometheus:http-web/proxy/api/v1/query?query=up")
    emit prom-query-up.json ;;

  logs\ *)
    set -- $rest
    lpod="$2"; lc=""; prev=""
    while [ $# -gt 0 ]; do
      case "$1" in
        -c) lc="${2:-}"; shift ;;
        --previous) prev="-previous" ;;
      esac
      shift
    done
    emit "logs-${lpod}-${lc}${prev}.txt" ;;

  *)
    echo "stub: no fixture for: $*" >&2
    exit 1 ;;
esac
