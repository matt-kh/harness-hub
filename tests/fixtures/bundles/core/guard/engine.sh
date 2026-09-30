#!/usr/bin/env bash
# Fixture guard engine (tests only). Same contract as bundles/core/guard/engine.sh:
# stdin Claude PreToolUse JSON, stdout one hookSpecificOutput decision or nothing (pass),
# exit 0 always, malformed input -> deny.
set -u
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# guard.env: KEY='value' lines; variables already set in the environment win
if [ -f "$here/guard.env" ]; then
  while IFS= read -r line; do
    case "$line" in ''|'#'*) continue ;; esac
    k=${line%%=*}
    if [ -z "$(eval "printf '%s' \"\${$k+x}\"")" ]; then eval "export $line"; fi
  done < "$here/guard.env"
fi
decide() {
  jq -cn --arg d "$1" --arg r "fixture-guard: $2" \
    '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:$d,permissionDecisionReason:$r}}'
  exit 0
}
allow() { decide allow "$1"; }
ask()   { decide ask "$1"; }
deny()  { decide deny "$1"; }
input=$(cat)
command -v jq >/dev/null 2>&1 || { printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"fixture-guard: jq missing"}}'; exit 0; }
printf '%s' "$input" | jq -e 'type == "object"' >/dev/null 2>&1 || deny "malformed hook input"
cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // empty')
[ -n "$cmd" ] || exit 0
