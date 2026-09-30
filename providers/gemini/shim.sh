#!/usr/bin/env bash
# Gemini CLI BeforeTool hook -> harness guard (ARCHITECTURE §5).
#
# stdin  (Gemini): {"tool_name":"run_shell_command","tool_input":{"command":"…"},"cwd":"…",…}
# guard  (neutral, Claude PreToolUse): {"tool_name":"Bash","tool_input":{"command":"…"},"cwd":"…"}
# stdout (Gemini): {"decision":"allow"} | {"decision":"deny","reason":"…"} | nothing (no opinion)
#
# Gemini has no "ask" decision: a guard "ask" becomes HARNESS_ASK_AS (deny by default, set from
# [providers.gemini].ask_as in the rendered hook command). Any other tool passes through with
# no output. Malformed input or guard output fails CLOSED (deny). Always exits 0.
set -u
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
guard=${HARNESS_GUARD:-$here/guard-bash.sh}
ask_as=${HARNESS_ASK_AS:-deny}

out_deny() {
  if command -v jq >/dev/null 2>&1; then
    jq -cn --arg r "$1" '{decision:"deny", reason:$r}'
  else
    printf '{"decision":"deny","reason":"harness shim: %s"}\n' "jq is not installed"
  fi
  exit 0
}

command -v jq >/dev/null 2>&1 || out_deny "jq is not installed"
input=$(cat)
printf '%s' "$input" | jq -e 'type == "object"' >/dev/null 2>&1 || out_deny "harness shim: malformed hook input"
tool=$(printf '%s' "$input" | jq -r '.tool_name // empty')
[ "$tool" = "run_shell_command" ] || exit 0
neutral=$(printf '%s' "$input" | jq -c '{tool_name: "Bash",
  tool_input: {command: (.tool_input.command // "" | tostring)},
  cwd: (.cwd // "" | tostring)}') || out_deny "harness shim: could not translate the hook input"
[ -r "$guard" ] || out_deny "harness shim: guard not found at $guard (run harness apply)"
res=$(printf '%s' "$neutral" | bash "$guard")
[ -n "$res" ] || exit 0
decision=$(printf '%s' "$res" | jq -r '.hookSpecificOutput.permissionDecision // empty' 2>/dev/null) \
  || out_deny "harness shim: unreadable guard output"
reason=$(printf '%s' "$res" | jq -r '.hookSpecificOutput.permissionDecisionReason // ""' 2>/dev/null)
case "$decision" in
  allow) jq -cn --arg r "$reason" '{decision:"allow", reason:$r}' ;;
  deny)  jq -cn --arg r "$reason" '{decision:"deny", reason:$r}' ;;
  ask)
    if [ "$ask_as" = "allow" ]; then
      jq -cn --arg r "$reason" '{decision:"allow", reason:$r, systemMessage:("harness: would ask in Claude Code - " + $r)}'
    else
      jq -cn --arg r "$reason" '{decision:"deny", reason:($r + " (this provider cannot ask: run the command yourself if you intend it)")}'
    fi ;;
  *) out_deny "harness shim: unexpected guard decision '$decision'" ;;
esac
exit 0
