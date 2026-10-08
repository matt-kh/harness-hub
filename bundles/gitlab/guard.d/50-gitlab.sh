# shellcheck shell=bash

# Section 50 (bundle gitlab): glab governance.
# rule: glab api -X POST|PUT|PATCH|DELETE | payload flag -> ask : API write; ask the user, or use the matching glab subcommand
# rule: glab mr merge|approve|revoke|delete, issue/release/repo/label mutations -> ask : team-visible, humans merge; ask the user instead of merging or approving
# rule: glab label create -n agent-* -> allow : governance label; other labels ask
# rule: glab mr create -> allow : creates are ungated (a -sub- source without target / with a base target -> deny)
# rule: glab mr create -f|--fill -> ask : generated text may carry a closing keyword or a key-less title; pass --title and --description-file instead
# rule: glab mr create --related-issue -> ask : links (and may close) a GitLab issue; mention the key in the description instead
# rule: glab mr create -t TITLE not matching HARNESS_GITLAB_MR_TITLE_RE -> ask : MR titles start with the ticket key; use a title like 'PROJ-123 fix parser' instead, or set gitlab.mr_title_re (empty disables)
# rule: glab mr create -t with $VAR or backticks -> ask : the title cannot be checked; use a literal title instead
# rule: glab mr update|note|close|rebase REF on an agent-labelled MR -> allow : human MRs ask (label it first: glab mr update REF --label agent-worked); -sub- retarget to base -> deny, retarget to the ticket branch instead; no/$VAR ref -> ask, pass a literal number
# repo-override: WORK_TICKET_BASE_BRANCH_RE = "^(master|main)$" -> default/base branches: pushes to them deny, sub MRs/PRs never target them
# repo-override: WORK_TICKET_LABELED_DECISION = "allow" -> allow|ask: the decision for writes to agent-labelled tickets, issues, MRs and PRs
repo_owns gitlab/guard.d/50-gitlab scm && return 0   # principle 8: the repository's .harness.toml owns this section or domain scm
# ---- GitLab (glab) --------------------------------------------------------------
GLAB="${WORK_TICKET_GLAB:-glab}"
# MR title convention (gitlab.mr_title_re → HARNESS_GITLAB_MR_TITLE_RE). guard.env omits empty
# values, so an empty key in a guard.env rendered with this bundle (HARNESS_BUNDLES lists gitlab)
# means "disabled"; without a guard.env (tests, hand-installed hook) the bundle default applies.
if [ -n "${HARNESS_GITLAB_MR_TITLE_RE+x}" ]; then GL_TITLE_RE=$HARNESS_GITLAB_MR_TITLE_RE
else case " ${HARNESS_BUNDLES:-} " in *" gitlab "*) GL_TITLE_RE="" ;; *) GL_TITLE_RE='^[A-Z][A-Z0-9_]*-[0-9]+ ' ;; esac; fi
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
      # --fill / --related-issue / title convention (asks are deferred so a later deny still wins)
      # a clause cut out of `sh -c "…"` ends in the wrapper's quote: retry without it
      words=$(shell_words "$clause") || words=$(shell_words "${clause%[\"\']}") || { defer "glab mr create — could not parse the command line (unbalanced quotes); pass a literal --title"; continue; }
      toks=(); [ -z "$words" ] || while IFS= read -r _w; do toks+=("$_w"); done <<<"$words"
      mfill=false; mrel=false; mtitle=""; mhas_title=false; i=3   # skip 'glab mr create'
      while [ "$i" -lt "${#toks[@]}" ]; do
        tok=${toks[i]}; i=$((i+1))
        case "$tok" in
          -f|--fill|--fill=*) mfill=true ;;
          --related-issue|--related-issue=*) mrel=true; case "$tok" in *=*) ;; *) i=$((i+1)) ;; esac ;;
          -t|--title) mtitle=${toks[i]:-}; mhas_title=true; i=$((i+1)) ;;
          --title=*)  mtitle=${tok#*=}; mhas_title=true ;;
          -a|--assignee|-b|--target-branch|-d|--description|--description-file|-l|--label|-m|--milestone|-s|--source-branch|--reviewer|-R|--repo|--target-project) i=$((i+1)) ;;
          --*=*) ;;
          -?*) case "${toks[i]:-}" in -*|'') ;; *) i=$((i+1)) ;; esac ;;   # unknown flag: a value unless it looks like a flag
        esac
      done
      $mfill && defer "glab mr create --fill: generated text may carry a closing keyword or a key-less title; pass --title and --description-file instead"
      $mrel && defer "glab mr create --related-issue links (and may close) a GitLab issue; mention the key in the description instead"
      if $mhas_title && [ -n "$GL_TITLE_RE" ]; then
        case "$mtitle" in
          *'$'*|*'`'*) defer "glab mr create with a \$VAR/backtick title cannot be checked against gitlab.mr_title_re; use a literal title instead" ;;
          *) printf '%s' "$mtitle" | grep -qE -- "$GL_TITLE_RE" \
               || defer "MR title '$mtitle' does not match gitlab.mr_title_re ($GL_TITLE_RE): MR titles start with the ticket key (e.g. '${HARNESS_TICKET_EXAMPLE:-PROJ-123} fix parser'); set gitlab.mr_title_re to change the convention" ;;
        esac
      fi
    done <<EOF
$(printf '%s' "$flat" | grep -oE '\bglab\s+mr\s+create\b[^;&|]*')
EOF
    # creating an MR is never a write to a human artefact → promptless (label it agent-* so later edits stay promptless)
    pending_allow="glab mr create (creates are ungated; pass --label agent-worked so follow-up edits stay promptless)"
  fi

  # glab mr update|note|close|rebase <ref>: gate on the MR's existing labels
  gate_writes '\bglab\s+mr\s+(update|note|close|rebase)\b' fetch_glab_mr '^(-l|--label)$' '^--target-branch$' '' \
    '^(--(draft|ready|wip|yes|lock-discussion|unlock-discussion|remove-source-branch|squash-before-merge|unique|skip-ci)|-r|-y)$' "glab mr" '!'
fi
