#!/usr/bin/env bash
# Guard test runner: builds the concatenated guard and runs every bundle's rows against it.
#
#   bash bundles/core/guard/tests/run.sh            all bundles; prints PASS/FAIL rows, then
#                                                   "----" and "passed=N failed=M"; exit 1 on failures
#   HARNESS_TEST_BUNDLES=core,github  run.sh        only these bundles' rows (core is always included)
#                                                   and a guard built from only these bundles' sections
#   GUARD_BASH=/path/guard-bash.sh run.sh           test an already built guard (no build step)
#   HARNESS_GUARD_ENV=/path/guard.env run.sh        env file the guard sources (default: an empty
#                                                   file, so a real build/guard.env never leaks in)
#
# The default build target is <hub>/build/guard-bash.sh (gitignored). Stubs: ./stubs.
set -u
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)       # bundles/core/guard/tests
bundles_dir=$(cd "$here/../../.." && pwd)                 # bundles/
hub=$(cd "$bundles_dir/.." && pwd)

selected() {  # NAME -> rc 0 when the bundle's rows (and sections) are part of this run
  [ "$1" = core ] && return 0
  [ -z "${HARNESS_TEST_BUNDLES:-}" ] && return 0
  case ",$HARNESS_TEST_BUNDLES," in *",$1,"*) return 0 ;; esac
  return 1
}

if [ -z "${GUARD_BASH:-}" ]; then
  GUARD_BASH="$hub/build/guard-bash.sh"
  HARNESS_GUARD_BUNDLES="${HARNESS_TEST_BUNDLES:-}" bash "$here/../build.sh" "$GUARD_BASH" \
    || { echo "build failed" >&2; exit 2; }
fi
export GUARD_BASH

empty_env=$(mktemp)
export HARNESS_GUARD_ENV="${HARNESS_GUARD_ENV:-$empty_env}"

pass=0; fail=0
# shellcheck source=lib.sh
. "$here/lib.sh"
trap 'rm -rf "$ghd" "$empty_env"' EXIT

for d in "$bundles_dir"/*/; do
  d=${d%/}; n=$(basename "$d")
  [ -f "$d/guard.d/tests.sh" ] || continue
  selected "$n" || continue
  echo "## bundle $n"
  # shellcheck disable=SC1090
  . "$d/guard.d/tests.sh"
done

echo "----"; echo "passed=$pass failed=$fail"; [ "$fail" -eq 0 ]
