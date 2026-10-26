#!/usr/bin/env bash
# GitHub Copilot CLI userPromptSubmitted hook -> a harness `prompt` hook (ARCHITECTURE §5,
# neutral events). Written to the published spec; verify on install.
#
# stdin  (Copilot): {"sessionId":"…","cwd":"…","prompt":"…",…}
#                   (read as .prompt // .userPrompt // .message and .session_id // .sessionId)
# hook   (neutral, Claude UserPromptSubmit):
#                   {"session_id":"…","cwd":"…","prompt":"…","hook_event_name":"UserPromptSubmit"}
# stdout (Copilot): nothing. Copilot documents no message channel for this event, so the hook's
#                   output (systemMessage, additionalContext) is discarded.
#
# HARNESS_HOOK names the bundle hook script (set in the rendered hook command). This hook never
# blocks; without jq or on malformed input it does nothing. transcript_path is never read.
# Always exits 0.
set -u
hook=${HARNESS_HOOK:-}
command -v jq >/dev/null 2>&1 || exit 0
[ -n "$hook" ] && [ -r "$hook" ] || exit 0
input=$(cat)
printf '%s' "$input" | jq -e 'type == "object"' >/dev/null 2>&1 || exit 0
neutral=$(printf '%s' "$input" | jq -c '{session_id: (.session_id // .sessionId // "" | tostring),
  cwd: (.cwd // "" | tostring), prompt: (.prompt // .userPrompt // .message // "" | tostring),
  hook_event_name: "UserPromptSubmit"}' 2>/dev/null) || exit 0
printf '%s' "$neutral" | bash "$hook" >/dev/null 2>&1
exit 0
