# shellcheck shell=bash

# Section 40 (bundle gitlab): closing keywords + ticket key (GitLab's Jira integration transitions tickets on them).
# rule: (close|fix|resolve|implement) KEY-123 in git commit | glab [-R g/p] mr [-R g/p] create|new|update | glab [-R g/p] api (also quoted or $VAR command words) -> deny : a closing keyword would change the ticket's state as a side effect; mention the key instead (KEY-123 fix parser)
repo_owns gitlab/guard.d/40-gitlab-closing tracker && return 0   # principle 8: the repository's .harness.toml owns this section or domain tracker
# ---- Closing keywords: GitLab's Jira integration transitions tickets on them ------
# They would change ticket state as a side effect, so block them at the source (commits, MR text, API payloads).
# repo flag(s) before the noun or the verb: -R g/p, -Rg/p, -R=g/p, --repo[=]g/p, repeated
# (same text as GLR in 50-gitlab, kept here because 40 runs, and may yield, before 50)
CL_GLR='((-R[= ]?|--repo[= ])\S+\s+)*'
CLOSE_RE='\b([Cc]los(e|es|ed|ing)|[Ff]ix(es|ed|ing)?|[Rr]esolv(e|es|ed|ing)|[Ii]mplement(s|ed|ing)?):?\s+([Ii]ssues?\s+)?[A-Z][A-Z0-9_]*-[0-9]+'
# Command words are matched on the plain and the dequoted command (glab "mr" update), and a $VAR
# or substitution in the noun or verb slot counts too: the closing keyword is what is denied.
CL_CMD_RE="\bgit\s+commit\b|\bglab\s+${CL_GLR}mr\s+${CL_GLR}(create|new|update)\b|\bglab\s+${CL_GLR}api\b|\bglab\s+${CL_GLR}[^[:space:]]*[\$\`]|\bglab\s+${CL_GLR}mr\s+${CL_GLR}[^[:space:]]*[\$\`]"
if printf '%s' "$flat" | grep -qE "$CLOSE_RE" \
   && { printf '%s' "$flat" | grep -qE "$CL_CMD_RE" || printf '%s' "$flat_dq" | grep -qE "$CL_CMD_RE"; }; then
  deny "closing keyword + ticket key would let GitLab transition the Jira ticket as a side effect (denied even on request) — mention the key instead (e.g. '${HARNESS_TICKET_EXAMPLE:-PROJ-123} fix parser')"
fi
