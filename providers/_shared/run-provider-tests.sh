#!/usr/bin/env bash
# run-provider-tests.sh TESTS_DIR SPEC... — every shim fixture set of one provider.
#
# SPEC is `guard:<shim>` (fixtures directly in TESTS_DIR) or `<event>:<shim>` (fixtures in
# TESTS_DIR/<event>/), the shim named relative to the provider directory (TESTS_DIR/..). Each set
# runs through run-shim-tests.sh; one summary line at the end. `harness lint` (hooks-events)
# checks that a provider's tests/run.sh names `<event>:<shim>` for every event shim it declares.
# Bash 3.2 compatible.
set -u
tests=$1; shift
here=$(cd "$(dirname "$0")" && pwd)
rc=0
for spec in "$@"; do
  set_name=${spec%%:*}; shim=${spec#*:}
  if [ "$set_name" = "guard" ]; then dir=$tests; else dir=$tests/$set_name; fi
  printf -- '-- %s (%s)\n' "$set_name" "$shim"
  bash "$here/run-shim-tests.sh" "$tests/../$shim" "$dir" || rc=1
done
if [ "$rc" -eq 0 ]; then echo "all shim fixtures passed"; else echo "shim fixtures FAILED"; fi
exit "$rc"
