#!/usr/bin/env bash
# GitHub Copilot CLI sessionEnd hook -> a harness `stop` hook (ARCHITECTURE §5, neutral events).
# Written to the published spec; verify on install.
#
# stdin  (Copilot): {"sessionId":"…","cwd":"…",…}  (session read as .session_id // .sessionId)
# hook   (neutral, Claude Stop):
#                   {"session_id":"…","cwd":"…","stop_hook_active":false,"hook_event_name":"Stop"}
# stdout (Copilot): nothing. Copilot documents no message channel for sessionEnd, so a nudge the
#                   hook prints (systemMessage) is dropped; the hook still runs for its side effects.
#
# HARNESS_HOOK names the bundle hook script (set in the rendered hook command). This hook never
# blocks; without jq or on malformed input it does nothing. transcript_path is never read.
# Always exits 0.
set -u
hook=${HARNESS_HOOK:-}
command -v jq >/dev/null 2>&1 || exit 0
[ -n "$hook" ] && [ -r "$hook" ] || exit 0
input=$(cat)
# exactly one JSON object on stdin, else do nothing
printf '%s' "$input" | jq -se 'length == 1 and (.[0] | type) == "object"' >/dev/null 2>&1 || exit 0
neutral=$(printf '%s' "$input" | jq -sc '.[0] | {session_id: (.session_id // .sessionId // "" | tostring),
  cwd: (.cwd // "" | tostring), stop_hook_active: (.stop_hook_active == true),
  hook_event_name: "Stop"}' 2>/dev/null) || exit 0
printf '%s' "$neutral" | bash "$hook" >/dev/null 2>&1
exit 0
