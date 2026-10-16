#!/usr/bin/env bash
# Bundle tests: this bundle's guard rows against a guard built from core + this bundle only
# (proves the sections do not depend on any other bundle), then every skill suite under
# skills/*/scripts/tests/run.sh, then the doctor check script lib/check-trackers.sh. Exit 1 on any
# failure.
set -uo pipefail
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
bdir=$(cd "$here/.." && pwd); name=$(basename "$bdir")
core=$(cd "$bdir/../core" && pwd)
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
fail=0

if [ -f "$bdir/guard.d/tests.sh" ]; then
  HARNESS_GUARD_BUNDLES=$name bash "$core/guard/build.sh" "$tmp/hooks/guard-bash.sh" || fail=1
  GUARD_BASH="$tmp/hooks/guard-bash.sh" HARNESS_TEST_BUNDLES=$name \
    bash "$core/guard/tests/run.sh" > "$tmp/guard.log" 2>&1 || { fail=1; grep -A1 '^FAIL' "$tmp/guard.log"; }
  echo "guard ($name + core): $(tail -1 "$tmp/guard.log")"
fi
for t in "$bdir"/skills/*/scripts/tests/run.sh; do
  [ -f "$t" ] || continue
  bash "$t" > "$tmp/skill.log" 2>&1 || { fail=1; grep -E '^FAIL' "$tmp/skill.log" | head -20; }
  echo "$(basename "$(dirname "$(dirname "$(dirname "$t")")")"): $(tail -1 "$tmp/skill.log")"
done
# doctor check ticket-workflow-trackers (lib/check-trackers.sh): exit code and first line per input
ct() {  # EXIT FIRST-LINE-ERE JSON
  local out rc
  out=$(printf '%s\n' "$3" | bash "$bdir/lib/check-trackers.sh" 2>&1); rc=$?
  if [ "$rc" = "$1" ] && printf '%s\n' "$out" | head -1 | grep -qE -- "$2"; then n_ct=$((n_ct + 1))
  else fail=1; echo "FAIL check-trackers $3: rc=$rc, want $1 /$2/"; printf '%s\n' "$out" | sed 's/^/  /'; fi
}
n_ct=0
ct 0 '^no ticket_workflow.trackers' '[]'
ct 0 '^2 tracker declaration' '[{"match":"^github\\.com/owner/","tracker":"github-issues"},{"match":"^gitlab\\.example\\.com/","tracker":"jira","project":"PROJ"}]'
ct 1 '^ticket_workflow.trackers\[1\]: match .* is not a valid ERE.*escape dots' '[{"match":"^x/","tracker":"jira"},{"match":"^x/(","tracker":"jira"}]'
ct 1 '^ticket_workflow.trackers\[0\]: tracker .trello. is not github-issues or jira' '[{"match":"^x/","tracker":"trello"}]'
ct 1 '^ticket_workflow.trackers\[0\]: project .PROJ. needs tracker = "jira"' '[{"match":"^x/","tracker":"github-issues","project":"PROJ"}]'
ct 1 '^ticket_workflow.trackers\[0\]: match is empty' '[{"tracker":"jira"}]'
ct 1 '^ticket_workflow.trackers is not a list of tables' 'not json'
echo "check-trackers: $n_ct case(s) passed"
[ $fail -eq 0 ] && echo "all $name tests passed" || echo "$name tests FAILED"
exit $fail
