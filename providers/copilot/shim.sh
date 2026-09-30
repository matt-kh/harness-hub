#!/usr/bin/env bash
# GitHub Copilot CLI preToolUse hook -> harness guard (ARCHITECTURE §5).
#
# stdin  (Copilot): {"toolName":"bash","toolArgs":"{\"command\":\"…\"}","cwd":"…",…}
#                   toolArgs is a JSON *string*
# guard  (neutral, Claude PreToolUse): {"tool_name":"Bash","tool_input":{"command":"…"},"cwd":"…"}
# stdout (Copilot): {"permissionDecision":"allow"} |
#                   {"permissionDecision":"deny","permissionDecisionReason":"…"} | nothing
#
# Copilot has no "ask": a guard "ask" becomes HARNESS_ASK_AS (deny by default, from
# [providers.copilot].ask_as). Tools other than bash/shell pass through with no output.
# Malformed input fails CLOSED (deny). Always exits 0.
set -u
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
guard=${HARNESS_GUARD:-$here/guard-bash.sh}
ask_as=${HARNESS_ASK_AS:-deny}

out_deny() {
  if command -v jq >/dev/null 2>&1; then
    jq -cn --arg r "$1" '{permissionDecision:"deny", permissionDecisionReason:$r}'
  else
    printf '{"permissionDecision":"deny","permissionDecisionReason":"harness shim: %s"}\n' "jq is not installed"
  fi
  exit 0
}

command -v jq >/dev/null 2>&1 || out_deny "jq is not installed"
input=$(cat)
printf '%s' "$input" | jq -e 'type == "object"' >/dev/null 2>&1 || out_deny "harness shim: malformed hook input"
tool=$(printf '%s' "$input" | jq -r '.toolName // empty')
case "$tool" in bash|shell) ;; *) exit 0 ;; esac
neutral=$(printf '%s' "$input" | jq -c '
  (.toolArgs // "{}") as $a
  | (if ($a | type) == "string" then ($a | fromjson) else $a end) as $args
  | if ($args | type) != "object" then error("toolArgs is not an object") else . end
  | {tool_name: "Bash", tool_input: {command: ($args.command // "" | tostring)}, cwd: (.cwd // "" | tostring)}' 2>/dev/null) \
  || out_deny "harness shim: malformed toolArgs"
[ -r "$guard" ] || out_deny "harness shim: guard not found at $guard (run harness apply)"
res=$(printf '%s' "$neutral" | bash "$guard")
[ -n "$res" ] || exit 0
decision=$(printf '%s' "$res" | jq -r '.hookSpecificOutput.permissionDecision // empty' 2>/dev/null) \
  || out_deny "harness shim: unreadable guard output"
reason=$(printf '%s' "$res" | jq -r '.hookSpecificOutput.permissionDecisionReason // ""' 2>/dev/null)
case "$decision" in
  allow) jq -cn '{permissionDecision:"allow"}' ;;
  deny)  jq -cn --arg r "$reason" '{permissionDecision:"deny", permissionDecisionReason:$r}' ;;
  ask)
    if [ "$ask_as" = "allow" ]; then
      jq -cn '{permissionDecision:"allow"}'
    else
      jq -cn --arg r "$reason" '{permissionDecision:"deny", permissionDecisionReason:($r + " (this provider cannot ask: run the command yourself if you intend it)")}'
    fi ;;
  *) out_deny "harness shim: unexpected guard decision '$decision'" ;;
esac
exit 0
