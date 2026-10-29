#!/usr/bin/env bash
# Claude Code UserPromptSubmit / Stop hook -> a harness `prompt` / `stop` hook (ARCHITECTURE §5,
# neutral events). Claude's payload is the neutral envelope; this shim only filters it.
#
# stdin  (Claude): {"session_id":"…","transcript_path":"…","cwd":"…","hook_event_name":"…",
#                   "prompt":"…" | "stop_hook_active":…, "last_assistant_message":"…"}
# hook   (neutral): the same object without transcript_path and last_assistant_message
# hook stdout (neutral): nothing, or {"systemMessage":"…","hookSpecificOutput":{"additionalContext":"…"}}
# stdout (Claude): nothing, or exactly one JSON object with systemMessage and, for
#                  UserPromptSubmit only, hookSpecificOutput {hookEventName, additionalContext}
#
# Claude adds plain stdout of a UserPromptSubmit hook to the model's context and honours
# decision/continue/reason: the shim lets none of that through. HARNESS_HOOK names the bundle
# hook script (set in the rendered hook command). Without jq, on malformed input, when the hook
# fails or prints anything but exactly one JSON object, it prints nothing. Always exits 0.
set -u
hook=${HARNESS_HOOK:-}
command -v jq >/dev/null 2>&1 || exit 0
[ -n "$hook" ] && [ -r "$hook" ] || exit 0
input=$(cat)
# exactly one JSON object on stdin, else do nothing
printf '%s' "$input" | jq -se 'length == 1 and (.[0] | type) == "object"' >/dev/null 2>&1 || exit 0
neutral=$(printf '%s' "$input" | jq -sc '.[0] | del(.transcript_path, .last_assistant_message)' 2>/dev/null) || exit 0
ev=$(printf '%s' "$neutral" | jq -r '.hook_event_name // "" | tostring' 2>/dev/null) || exit 0
ctx=0; [ "$ev" = "UserPromptSubmit" ] && ctx=1
res=$(printf '%s' "$neutral" | bash "$hook" 2>/dev/null) || exit 0   # a failing hook says nothing
[ -n "$res" ] || exit 0
printf '%s' "$res" | jq -cs --arg ev "$ev" --arg ctx "$ctx" '
  if length != 1 or (.[0] | type) != "object" then empty else .[0] |
    ((if (.systemMessage | type) == "string" then {systemMessage: .systemMessage} else {} end)
     + ((.hookSpecificOutput | if type == "object" then .additionalContext else null end) as $c
        | if $ctx == "1" and ($c | type) == "string"
          then {hookSpecificOutput: {hookEventName: $ev, additionalContext: $c}} else {} end))
    | if . == {} then empty else . end
  end' 2>/dev/null
exit 0
