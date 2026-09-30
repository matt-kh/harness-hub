#!/usr/bin/env bash
# helm stub for the k8s CLI tests. Answers from tests/fixtures/ only — no network.
# Every invocation is appended to $STUB_LOG as `helm <args>`; the CLI always puts
# `--kube-context CTX` last, which run.sh asserts.
set -u
here=$(cd "$(dirname "$0")" && pwd)
FIX="$here/fixtures"
[ -n "${STUB_LOG:-}" ] && printf 'helm %s\n' "$*" >> "$STUB_LOG"

emit() {
  local f="$FIX/$1"
  if [ ! -f "$f" ]; then echo "stub: missing fixture $1" >&2; exit 1; fi
  cat "$f"
}

# strip the trailing `--kube-context CTX`
ctx=""; rest="$*"
n=$#
if [ "$n" -ge 2 ]; then
  p=$((n - 1)); last1=${!n}; last2=${!p}      # indirect: the last two positional args
  if [ "$last2" = "--kube-context" ]; then
    ctx="$last1"
    rest=$(printf '%s ' "${@:1:$((n - 2))}"); rest="${rest% }"
  fi
fi

case "$ctx" in
  unreachable)
    echo "Error: Kubernetes cluster unreachable: Get \"https://192.0.2.1:6443/version\": dial tcp 192.0.2.1:6443: i/o timeout" >&2
    exit 1 ;;
  forbidden)
    echo "Error: query: failed to query with labels: secrets is forbidden: User \"stub\" cannot list resource in API group \"\"" >&2
    exit 1 ;;
esac

case "$rest" in
  "list -A -o json")                       emit helm-list.json ;;
  "list -n shop -o json")                 emit helm-list-shop.json ;;
  "history shop -n shop -o json")        emit helm-history-shop.json ;;
  "history reportd -n default -o json")    emit helm-history-reportd.json ;;
  "status shop -n shop -o json")         emit helm-status-shop.json ;;
  "status reportd -n default -o json")     emit helm-status-reportd.json ;;
  "get values shop -n shop -a -o json")  emit helm-values-shop.json ;;
  *)
    echo "stub: no fixture for: $*" >&2
    exit 1 ;;
esac
