# shellcheck shell=bash

# Section 50 (bundle gitlab): glab governance.
# rule: glab api -X POST|PUT|PATCH|DELETE | payload flag -> ask : API write
# rule: glab mr merge|approve|revoke|delete, issue/release/repo/label mutations -> ask : team-visible, humans merge
# rule: glab label create -n agent-* -> allow : governance label; other labels ask
# rule: glab mr create -> allow : creates are ungated (a -sub- source without target / with a base target -> deny)
# rule: glab mr update|note|close REF on an agent-labelled MR -> allow : human MRs ask; -sub- retarget to base -> deny
# ---- GitLab (glab) --------------------------------------------------------------
GLAB="${WORK_TICKET_GLAB:-glab}"
# fetch_glab_mr REF [REPO] -> normalised MR JSON (IID or branch); rc 1 on failure
fetch_glab_mr() {
  local o; o=$(hn_timeout 8 "$GLAB" mr view "$1" ${2:+-R "$2"} -F json 2>/dev/null) || return 1
  [ -n "$o" ] || return 1
  printf '%s' "$o" | jq -ce '{labels, src: .source_branch, tgt: .target_branch, cross: false} | '"$NORM_JQ" 2>/dev/null
}
# create + agent labelling: promptless. Existing MR without an agent-* label: ask.
# merge/approve/revoke/delete: always ask (humans merge). Everything else team-visible: ask.
if printf '%s' "$flat" | grep -qE '\bglab\s+(mr|issue|release|repo|label|api)\b'; then
  # glab api (per clause): non-GET method, or a payload flag (which flips the default method to POST)
  while IFS= read -r clause; do
    [ -n "$clause" ] || continue
    printf '%s' "$clause" | grep -qE '(-X|--method)[= ]+(POST|PUT|DELETE|PATCH)|(^|[[:space:]])(-F|--field|--form|-f|--raw-field|--input)([= ]|$)' && ask "glab api write (non-GET or payload flag)"
  done <<EOF
$(printf '%s' "$flat" | grep -oE '\bglab\s+api\b[^;&|]*')
EOF
  printf '%s' "$flat" | grep -qE '\bglab\s+(mr\s+(merge|approve|revoke|delete)|issue\s+(create|close|delete)|release\s+(create|delete|upload)|repo\s+(delete|archive|fork|create)|label\s+(edit|delete))\b' \
    && ask "glab team-visible mutation (MR merge/approve is human-only; issues/releases/repos are not governed)"

  # glab label create -n NAME: agent-* labels are free
  if printf '%s' "$flat" | grep -qE '\bglab\s+label\s+create\b'; then
    lname=$(printf '%s' "$flat" | grep -oE -- '(-n|--name)[= ]+["'"'"']?[^"'"'"' ]+' | head -1 | sed -E 's/^(-n|--name)[= ]+["'"'"']?//')
    printf '%s' "$lname" | grep -qE "$AGENT_LABEL_RE" && allow "glab label create '$lname' (agent-* governance label)"
    ask "glab label create '${lname:-?}' (non-agent label)"
  fi

  # glab mr create (per clause): sub MRs (-sub- source) must target the ticket branch, never master|main
  if printf '%s' "$flat" | grep -qE '\bglab\s+mr\s+create\b'; then
    while IFS= read -r clause; do
      [ -n "$clause" ] || continue
      csrc=$(flag_val '-s|--source-branch' "$clause"); ctgt=$(flag_val '-b|--target-branch' "$clause")
      sub_create_rules MR "$csrc" "$ctgt"
      [ -z "$csrc" ] && $in_sub_worktree && deny "glab mr create from inside a sub worktree ($cwd_base) without -s — run it from the main checkout with explicit -s/-b"
    done <<EOF
$(printf '%s' "$flat" | grep -oE '\bglab\s+mr\s+create\b[^;&|]*')
EOF
    # creating an MR is never a write to a human artefact → promptless (label it agent-* so later edits stay promptless)
    pending_allow="glab mr create (creates are ungated; pass --label agent-worked so follow-up edits stay promptless)"
  fi

  # glab mr update|note|close <ref>: gate on the MR's existing labels
  gate_writes '\bglab\s+mr\s+(update|note|close)\b' fetch_glab_mr '^(-l|--label)$' '^--target-branch$' '' \
    '^(--(draft|ready|wip|yes|lock-discussion|unlock-discussion|remove-source-branch|squash-before-merge|unique)|-r|-y)$' "glab mr" '!'
fi
