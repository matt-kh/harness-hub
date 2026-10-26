#!/usr/bin/env bash
# Gemini CLI BeforeAgent hook -> a harness `prompt` hook (ARCHITECTURE §5, neutral events).
#
# stdin  (Gemini): {"session_id":"…","cwd":"…","prompt":"…","hook_event_name":"BeforeAgent",…}
# hook   (neutral, Claude UserPromptSubmit):
#                  {"session_id":"…","cwd":"…","prompt":"…","hook_event_name":"UserPromptSubmit"}
# hook stdout (neutral): nothing, or {"systemMessage":"…","hookSpecificOutput":{"additionalContext":"…"}}
# stdout (Gemini): nothing, or exactly one JSON object carrying systemMessage and/or
#                  hookSpecificOutput {hookEventName:"BeforeAgent", additionalContext}
#
# HARNESS_HOOK names the bundle hook script (set in the rendered hook command). This hook never
# blocks: no decision, continue or reason is ever emitted. Without jq, on malformed input, when
# the hook fails or prints anything but exactly one JSON object, it prints nothing (Gemini would
# show stray text as a message). transcript_path is never read. Always exits 0.
set -u
hook=${HARNESS_HOOK:-}
command -v jq >/dev/null 2>&1 || exit 0
[ -n "$hook" ] && [ -r "$hook" ] || exit 0
input=$(cat)
# exactly one JSON object on stdin, else do nothing
printf '%s' "$input" | jq -se 'length == 1 and (.[0] | type) == "object"' >/dev/null 2>&1 || exit 0
neutral=$(printf '%s' "$input" | jq -sc '.[0] | {session_id: (.session_id // "" | tostring),
  cwd: (.cwd // "" | tostring), prompt: (.prompt // "" | tostring),
  hook_event_name: "UserPromptSubmit"}' 2>/dev/null) || exit 0
ev=BeforeAgent; ctx=1
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
