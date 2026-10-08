# shellcheck shell=bash

# Section 65 (bundle merge-queue): the train (mq run) is human-only; mq sync is label-gated inside the CLI.
# rule: mq run|merge|enqueue|train … (also …/mq, mq.py) -> ask : merging is human-only; hand the human the `mq plan` output and let them run `mq run` in their terminal instead
# rule: mq sync … --include-human -> ask : writes to MRs/PRs without an agent-* label; label them first (glab mr update N --label agent-worked / gh pr edit N --add-label agent-worked) or ask the user
# rule: mq sync -> allow : writes only to agent-labelled MRs/PRs (the CLI skips the rest and prints the label hint); mq plan|status|check are reads and pass
repo_owns merge-queue/guard.d/65-merge-queue scm && return 0   # principle 8: the repository's .harness.toml owns this section or domain scm
# ---- Merge queue (mq) -------------------------------------------------------------
# Every `mq VERB` / `…/mq VERB` / `…/mq.py VERB` occurrence anywhere in the command (sh -c, xargs, env
# prefixes, cd … &&) is classified by its verb. Asks are deferred so a later deny still wins.
# The allow for `mq sync` is recorded only when the whole command is that one sync clause
# (optionally behind VAR=value prefixes): a compound command falls through to the other
# sections and the permission rules.
MQ_CMD_RE='(^|[[:space:];&|(`"'\''])(mq|[^[:space:];&|(`"'\'']*/mq(\.py)?|mq\.py)[[:space:]]+[^;&|`)]*'
MQ_SOLE_SYNC_RE='^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*[[:space:]]+)*(mq|[^[:space:];&|(`"'\'']*/mq(\.py)?|mq\.py)[[:space:]]+sync([[:space:]][^;&|`$()<>]*)?$'
if printf '%s' "$flat" | grep -qE "$MQ_CMD_RE"; then
  mq_sync=""
  while IFS= read -r mq_clause; do
    [ -n "$mq_clause" ] || continue
    set -f
    # shellcheck disable=SC2046  # word splitting is the point; globbing is off
    set -- $(printf '%s' "$mq_clause" | tr -d "\"'\\\\\`();&|")
    set +f
    case "${2:-}" in
      run|merge|enqueue|train)
        defer "mq $2 merges — merging is human-only; hand the human the \`mq plan\` output and let them run \`mq run\` in their terminal instead" ;;
      sync)
        case " $* " in
          *" --include-human "*)
            defer "mq sync --include-human writes to MRs/PRs without an agent-* label — label them first (glab mr update N --label $GOV_LABEL / gh pr edit N --add-label $GOV_LABEL) or ask the user" ;;
          *) mq_sync=1 ;;
        esac ;;
    esac
  done <<EOF
$(printf '%s' "$flat" | grep -oE "$MQ_CMD_RE")
EOF
  if [ -n "$mq_sync" ] && printf '%s' "$flat" | grep -qE "$MQ_SOLE_SYNC_RE"; then
    pending_allow="mq sync (writes only to agent-labelled MRs/PRs; the CLI skips the rest)"
  fi
fi
