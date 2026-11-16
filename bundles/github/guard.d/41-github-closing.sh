# shellcheck shell=bash

# Section 41 (bundle github): GitHub closing keywords.
# rule: (close|fix|resolve) #N | owner/repo#N | issue URL in git commit | gh [-R o/r] pr [-R o/r] create|new|edit|merge | gh api (also quoted or $VAR command words) -> deny : a closing keyword would change the issue's state as a side effect; mention #N instead (see #N, refs #N)
# ---- GitHub shared definitions (used by 41 and 60) ----
GH="${WORK_TICKET_GH:-gh}"
GHR='((-R[= ]?|--repo[= ])\S+\s+)*'                             # repo flag(s) between gh words: -R o/r, -Ro/r, -R=o/r, --repo[=]o/r, repeated
GHP='\bgh\s+'"$GHR"
# GitHub closes the referenced issue when a closing keyword reaches the default branch (PR
# title/body, commit messages). Not applied to `gh issue *` text (comments have no closing semantics).
GH_CLOSE_RE='\b(clos(e|es|ed)|fix(es|ed)?|resolv(e|es|ed)):?\s+(#[0-9]+|[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#[0-9]+|https?://(www\.)?github\.com/[^/[:space:]]+/[^/[:space:]]+/issues/[0-9]+)'
# the definitions above are shared with 60-github, so the yield check comes after them
repo_owns github/guard.d/41-github-closing tracker && return 0   # principle 8: the repository's .harness.toml owns this section or domain tracker
# Command words are matched on the plain and the dequoted command (gh "pr" edit), and a $VAR or
# substitution in the noun or verb slot counts too: the closing keyword is what is denied.
GH_CLOSE_CMD_RE="\bgit\s+commit\b|${GHP}pr\s+${GHR}(create|new|edit|merge)\b|${GHP}api\b|${GHP}[^[:space:]]*[\$\`]|${GHP}pr\s+${GHR}[^[:space:]]*[\$\`]"
if printf '%s' "$flat" | grep -qiE "$GH_CLOSE_RE" \
   && { printf '%s' "$flat" | grep -qE "$GH_CLOSE_CMD_RE" || printf '%s' "$flat_dq" | grep -qE "$GH_CLOSE_CMD_RE"; }; then
  deny "closing keyword + GitHub issue ref (#N, owner/repo#N or issue URL) would let GitHub close the issue as a side effect (denied even on request) — mention it instead (e.g. 'part of #12')"
fi
