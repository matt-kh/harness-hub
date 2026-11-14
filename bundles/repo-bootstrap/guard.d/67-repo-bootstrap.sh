# shellcheck shell=bash

# Section 67 (bundle repo-bootstrap): repoboot apply creates repositories and changes remote settings.
# rule: repoboot apply, or any verb that is not a literal questions|answer|plan|render|check|help ($VAR, $(…), xargs, an alias variable) -> ask : creates the repository, makes the first push into an empty remote and changes its settings, protection and labels; show the user `repoboot plan` first, then ask (type the verb literally)
# rule: repoboot questions|answer|plan|render|check|help -> pass : intake, read-only plans and checks, local renders (render refuses the default branch of an existing repository); the permission rules allow them
repo_owns repo-bootstrap/guard.d/67-repo-bootstrap scm && return 0   # principle 8: the repository's .harness.toml owns this section or domain scm
# ---- Repository bootstrap (repoboot) -------------------------------------------------
# Fail closed: every `repoboot` / `…/repoboot` / `…/repoboot.py` occurrence anywhere in the command
# (sh -c, xargs, env prefixes, cd … &&) is classified by its verb, and only a literal read/local
# verb passes. A bare `repoboot` fed by xargs, a verb from $VAR / $'…' / $(…), and repoboot held
# in a variable all ask. The ask is deferred so a later deny still wins.
RB_CMD_RE='(^|[[:space:];&|(`"'\''])(repoboot|[^[:space:];&|(`"'\''=]*/repoboot(\.py)?|repoboot\.py)([[:space:]]+[^;&|`)]*)?([;&|`)]|$)'
RB_ALIAS_RE='=["'\'']?([^[:space:];&|"'\'']*/)?repoboot(\.py)?(["'\''[:space:];&|]|$)'
rb_ask=""
if printf '%s' "$flat" | grep -qE "$RB_ALIAS_RE"; then
  rb_ask=1
elif printf '%s' "$flat" | grep -qE "$RB_CMD_RE"; then
  while IFS= read -r rb_clause; do
    [ -n "$rb_clause" ] || continue
    set -f
    # shellcheck disable=SC2046  # word splitting is the point; globbing is off
    set -- $(printf '%s' "$rb_clause" | tr -d "\"'\\\\\`();&|")
    set +f
    case "${2:-}" in
      questions|answer|plan|render|check|help|-h|--help) ;;
      "")
        # bare `repoboot`: prints the usage, unless xargs or a `…` substitution supplies the verb
        case "$rb_clause" in *'`') rb_ask=1 ;; esac
        if printf '%s' "$flat" | grep -qE '(^|[[:space:];&|(])xargs([[:space:]]|$)'; then rb_ask=1; fi ;;
      *) rb_ask=1 ;;
    esac
  done <<RBEOF
$(printf '%s' "$flat" | grep -oE "$RB_CMD_RE")
RBEOF
fi
if [ -n "$rb_ask" ]; then
  defer "repoboot apply creates the repository, pushes into an empty remote and changes its settings, protection and labels — show the user \`repoboot plan\` first and ask before running it (type the verb literally; read-only verbs: questions, answer, plan, render, check)"
fi
