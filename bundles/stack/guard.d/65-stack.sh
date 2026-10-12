# shellcheck shell=bash

# Section 65 (bundle stack): stk sync is label-gated inside the CLI; lifting the gate asks.
# rule: stk sync … --include-human (also …/stk, stk.py) -> ask : writes to MRs/PRs without an agent-* label; label them first (glab mr update N --label agent-worked / gh pr edit N --add-label agent-worked) or ask the user
# rule: stk sync -> allow : writes only to agent-labelled MRs/PRs (retarget, cascade rebase, lease push of -sub- branches, one leaf refresh); stk plan|status|check are reads and pass
repo_owns stack/guard.d/65-stack scm && return 0   # principle 8: the repository's .harness.toml owns this section or domain scm
# ---- Stack sync (stk) --------------------------------------------------------------
# Every `stk VERB` / `…/stk VERB` / `…/stk.py VERB` occurrence anywhere in the command (sh -c,
# xargs, env prefixes, cd … &&) is classified by its verb. The ask is deferred so a later deny
# still wins. The allow for `stk sync` is recorded only when the whole command is that one sync
# clause (optionally behind VAR=value prefixes): a compound command falls through to the other
# sections and the permission rules.
STK_CMD_RE='(^|[[:space:];&|(`"'\''])(stk|[^[:space:];&|(`"'\'']*/stk(\.py)?|stk\.py)[[:space:]]+[^;&|`)]*'
STK_SOLE_SYNC_RE='^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*[[:space:]]+)*(stk|[^[:space:];&|(`"'\'']*/stk(\.py)?|stk\.py)[[:space:]]+sync([[:space:]][^;&|`$()<>]*)?$'
if printf '%s' "$flat" | grep -qE "$STK_CMD_RE"; then
  stk_sync=""
  while IFS= read -r stk_clause; do
    [ -n "$stk_clause" ] || continue
    set -f
    # shellcheck disable=SC2046  # word splitting is the point; globbing is off
    set -- $(printf '%s' "$stk_clause" | tr -d "\"'\\\\\`();&|")
    set +f
    if [ "${2:-}" = sync ]; then
      case " $* " in
        *" --include-human "*)
          defer "stk sync --include-human writes to MRs/PRs without an agent-* label — label them first (glab mr update N --label $GOV_LABEL / gh pr edit N --add-label $GOV_LABEL) or ask the user" ;;
        *) stk_sync=1 ;;
      esac
    fi
  done <<EOF
$(printf '%s' "$flat" | grep -oE "$STK_CMD_RE")
EOF
  if [ -n "$stk_sync" ] && printf '%s' "$flat" | grep -qE "$STK_SOLE_SYNC_RE"; then
    pending_allow="stk sync (writes only to agent-labelled MRs/PRs; the CLI skips the rest)"
  fi
fi
