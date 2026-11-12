# shellcheck shell=bash

# Section 67 (bundle repo-bootstrap): repoboot apply creates repositories and changes remote settings.
# rule: repoboot apply (also …/repoboot, repoboot.py) -> ask : creates the repository, makes the first push into an empty remote and changes its settings, protection and labels; show the user `repoboot plan` first, then ask
# rule: repoboot questions|answer|plan|render|check -> pass : intake, read-only plans and checks, local renders (render refuses the default branch of an existing repository); the permission rules allow them
repo_owns repo-bootstrap/guard.d/67-repo-bootstrap scm && return 0   # principle 8: the repository's .harness.toml owns this section or domain scm
# ---- Repository bootstrap (repoboot) -------------------------------------------------
# Every `repoboot VERB` / `…/repoboot VERB` / `…/repoboot.py VERB` occurrence anywhere in the
# command (sh -c, xargs, env prefixes, cd … &&) is classified by its verb. The ask is deferred so
# a later deny still wins.
RB_CMD_RE='(^|[[:space:];&|(`"'\''])(repoboot|[^[:space:];&|(`"'\'']*/repoboot(\.py)?|repoboot\.py)[[:space:]]+[^;&|`)]*'
if printf '%s' "$flat" | grep -qE "$RB_CMD_RE"; then
  while IFS= read -r rb_clause; do
    [ -n "$rb_clause" ] || continue
    set -f
    # shellcheck disable=SC2046  # word splitting is the point; globbing is off
    set -- $(printf '%s' "$rb_clause" | tr -d "\"'\\\\\`();&|")
    set +f
    if [ "${2:-}" = apply ]; then
      defer "repoboot apply creates the repository, pushes into an empty remote and changes its settings, protection and labels — show the user \`repoboot plan\` first and ask before running it"
    fi
  done <<RBEOF
$(printf '%s' "$flat" | grep -oE "$RB_CMD_RE")
RBEOF
fi
