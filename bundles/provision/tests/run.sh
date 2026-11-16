#!/usr/bin/env bash
# Bundle tests: this bundle's guard rows against a guard built from core + linux + this bundle only
# (section 85 reads linux's 82 definitions, the dependency it declares; the rows prove it needs no
# other bundle), then every skill suite under skills/*/scripts/tests/run.sh. Exit 1 on any failure.
set -uo pipefail
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
bdir=$(cd "$here/.." && pwd); name=$(basename "$bdir")
core=$(cd "$bdir/../core" && pwd)
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
fail=0

if [ -f "$bdir/guard.d/tests.sh" ]; then
  HARNESS_GUARD_BUNDLES="linux,$name" bash "$core/guard/build.sh" "$tmp/hooks/guard-bash.sh" || fail=1
  GUARD_BASH="$tmp/hooks/guard-bash.sh" HARNESS_TEST_BUNDLES=$name \
    bash "$core/guard/tests/run.sh" > "$tmp/guard.log" 2>&1 || { fail=1; grep -A1 '^FAIL' "$tmp/guard.log"; }
  echo "guard ($name + linux + core): $(tail -1 "$tmp/guard.log")"
fi
for t in "$bdir"/skills/*/scripts/tests/run.sh; do
  [ -f "$t" ] || continue
  bash "$t" > "$tmp/skill.log" 2>&1 || { fail=1; grep -E '^FAIL' "$tmp/skill.log" | head -20; }
  echo "$(basename "$(dirname "$(dirname "$(dirname "$t")")")"): $(tail -1 "$tmp/skill.log")"
done
[ $fail -eq 0 ] && echo "all $name tests passed" || echo "$name tests FAILED"
exit $fail
