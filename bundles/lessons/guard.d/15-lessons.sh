# shellcheck shell=bash

# Section 15 (bundle lessons): the human decisions on a lesson ask; every other harness lessons call passes.
# rule: harness lessons confirm|retire|propose (also …/bin/harness, python3 -m harness, global flags before `lessons`) -> ask : a human decision on a lesson; run it yourself, or ask the user (/retro never runs it)
repo_owns lessons/guard.d/15-lessons base && return 0   # principle 8: the repository's .harness.toml owns this section or domain base
# ---- Lessons: human decisions -----------------------------------------------------
# `harness … lessons confirm|retire|propose` anywhere in the command (sh -c, xargs, env prefixes,
# cd … &&, a path to bin/harness, `python3 -m harness`), with any global flags between `harness`
# and `lessons`, within one clause. Deferred, so a later deny still wins. `new`, `note`, `index`,
# `journal`, `list`, `show`, `review`, `stats` and `validate` are left to the permission rules.
LESSONS_HUMAN_RE='(^|[[:space:];&|(`"'\''/])harness[[:space:]]+([^;&|`)]*[[:space:]])?lessons[[:space:]]+(confirm|retire|propose)([^A-Za-z0-9_-]|$)'
if printf '%s' "$flat" | grep -qE "$LESSONS_HUMAN_RE"; then
  defer "harness lessons confirm|retire|propose is a human decision on a lesson — run it yourself, or ask the user to (/retro never runs it)"
fi
