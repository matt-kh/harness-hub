# shellcheck shell=bash

# Section 40 (bundle gitlab): closing keywords + ticket key (GitLab's Jira integration transitions tickets on them).
# rule: (close|fix|resolve|implement) KEY-123 in git commit | glab mr create|update | glab api -> deny : ticket state is human-only
# ---- Closing keywords: GitLab's Jira integration transitions tickets on them ------
# Ticket state is human-only, so block them at the source (commits, MR text, API payloads).
CLOSE_RE='\b([Cc]los(e|es|ed|ing)|[Ff]ix(es|ed|ing)?|[Rr]esolv(e|es|ed|ing)|[Ii]mplement(s|ed|ing)?):?\s+([Ii]ssues?\s+)?[A-Z][A-Z0-9_]*-[0-9]+'
if printf '%s' "$flat" | grep -qE "$CLOSE_RE" \
   && printf '%s' "$flat" | grep -qE '\bgit\s+commit\b|\bglab\s+mr\s+(create|update)\b|\bglab\s+api\b'; then
  deny "closing keyword + ticket key would let GitLab transition the Jira ticket; ticket state is human-only — mention the key instead (e.g. '${HARNESS_TICKET_EXAMPLE:-PROJ-123} fix parser')"
fi
