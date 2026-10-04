# shellcheck shell=bash

# Section 41 (bundle github): GitHub closing keywords.
# rule: (close|fix|resolve) #N | owner/repo#N | issue URL in git commit | gh pr create|edit|merge | gh api -> deny : issue state is human-only; mention #N instead (see #N, refs #N)
# ---- GitHub shared definitions (used by 41 and 60) ----
GH="${WORK_TICKET_GH:-gh}"
GHR='((-R|--repo)[= ]\S+\s+)?'                                  # optional -R owner/repo between gh words
GHP='\bgh\s+'"$GHR"
# GitHub closes the referenced issue when a closing keyword reaches the default branch (PR
# title/body, commit messages). Not applied to `gh issue *` text (comments have no closing semantics).
GH_CLOSE_RE='\b(clos(e|es|ed)|fix(es|ed)?|resolv(e|es|ed)):?\s+(#[0-9]+|[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#[0-9]+|https?://(www\.)?github\.com/[^/[:space:]]+/[^/[:space:]]+/issues/[0-9]+)'
# the definitions above are shared with 60-github, so the yield check comes after them
repo_owns github/guard.d/41-github-closing tracker && return 0   # principle 8: the repository's .harness.toml owns this section or domain tracker
if printf '%s' "$flat" | grep -qiE "$GH_CLOSE_RE" \
   && printf '%s' "$flat" | grep -qE "\bgit\s+commit\b|${GHP}pr\s+${GHR}(create|edit|merge)\b|\bgh\s+api\b"; then
  deny "closing keyword + GitHub issue ref (#N, owner/repo#N or issue URL) would let GitHub close the issue; issue state is human-only — mention it instead (e.g. 'part of #12')"
fi
