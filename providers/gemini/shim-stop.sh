#!/usr/bin/env bash
# Gemini CLI AfterAgent hook -> a harness `stop` hook (ARCHITECTURE §5, neutral events).
#
# stdin  (Gemini): {"session_id":"…","cwd":"…","prompt":"…","prompt_response":"…",
#                   "stop_hook_active":false,"hook_event_name":"AfterAgent",…}
# hook   (neutral, Claude Stop):
#                  {"session_id":"…","cwd":"…","stop_hook_active":false,"hook_event_name":"Stop"}
# hook stdout (neutral): nothing, or {"systemMessage":"…","hookSpecificOutput":{"additionalContext":"…"}}
# stdout (Gemini): nothing, or exactly one JSON object carrying systemMessage and/or
#                  hookSpecificOutput {hookEventName:"AfterAgent", additionalContext}
#
# AfterAgent runs after every turn; the hook decides whether to say anything. HARNESS_HOOK names
# the bundle hook script (set in the rendered hook command). This hook never blocks: no decision,
# continue or reason is ever emitted. Without jq, on malformed input, or when the hook prints
# anything but exactly one JSON object, it prints nothing (Gemini would show stray text as a
# message). prompt, prompt_response and transcript_path are never passed on. Always exits 0.
set -u
hook=${HARNESS_HOOK:-}
command -v jq >/dev/null 2>&1 || exit 0
[ -n "$hook" ] && [ -r "$hook" ] || exit 0
input=$(cat)
printf '%s' "$input" | jq -e 'type == "object"' >/dev/null 2>&1 || exit 0
neutral=$(printf '%s' "$input" | jq -c '{session_id: (.session_id // "" | tostring),
  cwd: (.cwd // "" | tostring), stop_hook_active: (.stop_hook_active == true),
  hook_event_name: "Stop"}' 2>/dev/null) || exit 0
res=$(printf '%s' "$neutral" | bash "$hook" 2>/dev/null)
[ -n "$res" ] || exit 0
printf '%s' "$res" | jq -cs --arg ev "AfterAgent" '
  if length != 1 or (.[0] | type) != "object" then empty else .[0] |
    ((if (.systemMessage | type) == "string" then {systemMessage: .systemMessage} else {} end)
     + (if (.hookSpecificOutput.additionalContext | type) == "string"
        then {hookSpecificOutput: {hookEventName: $ev, additionalContext: .hookSpecificOutput.additionalContext}}
        else {} end))
    | if . == {} then empty else . end
  end' 2>/dev/null
exit 0
