# shellcheck shell=bash

# Section 50 (bundle gitlab): glab governance.
# rule: glab api -X non-GET (any case, quoted, attached, $VAR) | payload flag (-f/-F/--field/--raw-field/--form/--input) -> ask : API write; ask the user, or use the matching glab subcommand
# rule: glab api write (as above) from a subagent -> deny : a raw API write can merge or change state; hand the command back to the main thread
# rule: glab mr merge|accept|approve|revoke|unapprove|delete, glab issue close|reopen|open|delete -> ask : merging, approving, deleting and issue state are human decisions; run it only on the user's explicit request (they confirm it), or ask the user instead
# rule: glab mr merge|accept|approve|revoke|unapprove|delete, glab issue close|reopen|open|delete from a subagent -> deny : a subagent never merges, approves, deletes or changes issue state; hand the command back to the main thread
# rule: glab quick action (/merge /approve /close /reopen /ready /draft …) in a note, description or title -> ask : it carries out a human decision; drop it from the text, or run the matching glab command on the user's explicit request
# rule: glab quick action, or note/description text the guard cannot read, from a subagent -> deny : a subagent never merges or changes state; pass the text inline and hand state changes back to the main thread
# rule: (close|fix|resolve|implement) KEY-123 in glab -R g/p mr create|new|update or glab mr new (forms 40 misses) -> deny : a closing keyword would change the ticket's state as a side effect; mention the key instead (KEY-123 fix parser); yields like 40 (tracker)
# rule: glab with quoted/escaped command words or a $VAR/$(…) subcommand -> ask : the subcommand cannot be checked; write it literally and unquoted instead (a subagent is denied)
# rule: glab issue create, release/repo/label mutations -> ask : team-visible; ask the user instead
# rule: glab label create -n agent-* -> allow : governance label; other labels ask
# rule: glab mr create|new -> allow : creates are ungated (a -sub- source without target / with a base target -> deny)
# rule: glab mr create -f|--fill -> ask : generated text may carry a closing keyword or a key-less title; pass --title and --description-file instead
# rule: glab mr create --related-issue -> ask : links (and may close) a GitLab issue; mention the key in the description instead
# rule: glab mr create -t TITLE not matching HARNESS_GITLAB_MR_TITLE_RE -> ask : MR titles start with the ticket key; use a title like 'PROJ-123 fix parser' instead, or set gitlab.mr_title_re (empty disables)
# rule: glab mr create -t with $VAR or backticks -> ask : the title cannot be checked; use a literal title instead
# rule: glab mr update|note|comment|close|reopen|open|rebase REF on an agent-labelled MR -> allow : human MRs ask (label it first: glab mr update REF --label agent-worked); -sub- retarget to base -> deny, retarget to the ticket branch instead; no/$VAR ref -> ask, pass a literal number
# rule: glab mr close|reopen|open, glab mr update --ready|--draft|--wip|-r on a human MR -> ask : MR state is a human decision; run it only on the user's explicit request (they confirm it), or ask the user instead
# rule: glab mr close|reopen|open, glab mr update --ready|--draft|--wip|-r from a subagent -> deny : a subagent never changes MR state; hand the command back to the main thread
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
# Section-local views (gate_writes, called from here, sees them too): the command without fd
# duplications (2>&1 would cut a clause at its '&'), and an optional repo flag between glab words
# (-R g/p, -Rg/p, -R=g/p, --repo g/p, --repo=g/p; before the noun or the verb).
# shellcheck disable=SC2168  # sections are wrapped in a function by build.sh
local flat="$flat_split"
GLR='((-R[= ]?|--repo[= ])\S+\s+)?'
GLP='\bglab\s+'"$GLR"
GL_NOUNS='mr|issue|release|repo|label'
# GitLab quick actions that carry out a human decision (or retarget) when posted in a note or a
# description; GitLab runs a quick action only at the start of a line.
GL_QA='merge|approve|unapprove|close|reopen|ready|draft|wip|submit_review|target_branch'
# Closing-keyword backstop for command forms 40's regex does not parse (-R before or after the
# noun, the glab mr new alias); it yields exactly like 40 (component 40-gitlab-closing, domain tracker).
if [ -n "${CLOSE_RE:-}" ] && ! repo_owns gitlab/guard.d/40-gitlab-closing tracker \
   && printf '%s' "$flat" | grep -qE "$CLOSE_RE" \
   && printf '%s' "$flat" | grep -qE "${GLP}mr\s+${GLR}(create|new|update)\b"; then
  deny "closing keyword + ticket key would let GitLab transition the Jira ticket as a side effect (denied even on request) — mention the key instead (e.g. '${HARNESS_TICKET_EXAMPLE:-PROJ-123} fix parser')"
fi
# gl_words TEXT -> one line per glab command head: 'glab api', or 'glab NOUN VERB' (sorted)
gl_words() { printf '%s' "$1" | grep -oE "\bglab\s+${GLR}(api|(${GL_NOUNS})\s+${GLR}[A-Za-z-]+)" | sed -E 's/[[:space:]]+/ /g' | sort; }
# -- 0. hidden subcommands: command words in quotes or escapes (glab "mr" merge, gl\ab mr merge) and
#       a $VAR / $(…) / backtick in the noun or verb slot cannot be checked → human decision
if printf '%s' "$flat_dq" | grep -qE '\bglab\s' && [ "$(gl_words "$flat")" != "$(gl_words "$flat_dq")" ]; then
  human_decision_defer "glab command words in quotes or escapes cannot be checked — write the glab subcommand unquoted"
fi
if printf '%s' "$flat" | grep -qE "\bglab\s+${GLR}([^[:space:]]*[\$\`]|(${GL_NOUNS})\s+${GLR}[^[:space:]]*[\$\`])"; then
  human_decision_defer "glab subcommand from a \$VAR, \$(…) or backticks cannot be checked — write the subcommand literally"
fi
# create + agent labelling: promptless. Existing MR without an agent-* label: ask.
# merge/accept, approve, revoke/unapprove, MR/issue delete and issue close/reopen/open are human
# decisions: the main thread asks, a subagent is denied (as are raw API writes and quick actions).
# Everything else team-visible: ask. Every ask is deferred so a later deny still wins.
if printf '%s' "$flat" | grep -qE "${GLP}(${GL_NOUNS}|api)\b"; then
  # -- glab api (per clause): any method but GET/HEAD (case-insensitive, quoted, attached, $VAR)
  #    or any payload flag (-f/-F/--field/--raw-field/--form/--input, attached or not) is a write
  while IFS= read -r clause; do
    [ -n "$clause" ] || continue
    words=$(shell_words "$clause") || words=$(shell_words "${clause%[\"\']}") \
      || { human_decision_defer "glab api — could not parse the command line (unbalanced quotes); use balanced literal arguments instead"; continue; }
    toks=(); [ -z "$words" ] || while IFS= read -r _w; do toks+=("$_w"); done <<<"$words"
    a_method=""; a_payload=false; i=0
    while [ "$i" -lt "${#toks[@]}" ] && [ "${toks[i]}" != api ]; do i=$((i+1)); done; i=$((i+1))   # skip 'glab [-R x] api'
    while [ "$i" -lt "${#toks[@]}" ]; do
      tok=${toks[i]}; i=$((i+1))
      case "$tok" in
        -X|--method) a_method=${toks[i]:-}; i=$((i+1)) ;;
        -X?*)        a_method=${tok#-X}; a_method=${a_method#=} ;;
        --method=*)  a_method=${tok#*=} ;;
        -f|-F|--field|--raw-field|--form|--input) a_payload=true; i=$((i+1)) ;;
        -f?*|-F?*|--field=*|--raw-field=*|--form=*|--input=*) a_payload=true ;;
        -H|--header|--hostname|--output) i=$((i+1)) ;;
        *) ;;
      esac
    done
    a_m=$(printf '%s' "$a_method" | tr '[:lower:]' '[:upper:]')
    case "$a_m" in ''|GET|HEAD) ;; *) a_payload=true ;; esac
    $a_payload && human_decision_defer "glab api write (non-GET method or payload flag) — ask the user, or use the matching glab subcommand instead"
  done <<EOF
$(printf '%s' "$flat" | grep -oE "${GLP}api\b[^;&|]*")
EOF
  printf '%s' "$flat" | grep -qE "${GLP}(mr\s+${GLR}(merge|accept|approve|revoke|unapprove|delete|del)|issue\s+${GLR}(close|reopen|open|delete|del))\b" \
    && human_decision_defer "glab MR merge/approve/revoke/delete or issue close/reopen/delete (a human decision) — run it only on the user's explicit request (they confirm it), or ask the user instead"
  printf '%s' "$flat" | grep -qE "${GLP}(issue\s+${GLR}(create|new)|release\s+${GLR}(create|delete|upload)|repo\s+${GLR}(delete|archive|fork|create)|label\s+${GLR}(edit|delete))\b" \
    && defer "glab team-visible mutation (issues/releases/repos are not governed) — ask the user instead"

  # -- GitLab quick actions in notes, descriptions and titles (glab mr|issue note|comment|create|new|update):
  #    a line starting with /merge, /approve, /close, /reopen, /ready, /draft … is a human decision.
  #    Text the guard cannot read (a missing or '-' description file, '-' (editor), $VAR, $(…)) is
  #    denied in a subagent only; the main thread's description files are read when they exist.
  if printf '%s' "$flat" | grep -qE "${GLP}(mr|issue)\s+${GLR}(note|comment|create|new|update)\b"; then
    qa_hit=false; qa_blind=false
    printf '%s\n' "$cmd" | grep -qE "^[[:space:]\"']*/(${GL_QA})([[:space:]]|$)" && qa_hit=true   # heredoc / multi-line bodies
    while IFS= read -r clause; do
      [ -n "$clause" ] || continue
      words=$(shell_words "$clause") || words=$(shell_words "${clause%[\"\']}") || { qa_blind=true; continue; }
      toks=(); [ -z "$words" ] || while IFS= read -r _w; do toks+=("$_w"); done <<<"$words"
      i=0
      while [ "$i" -lt "${#toks[@]}" ]; do
        tok=${toks[i]}; i=$((i+1)); qt=""; qf=""; qset=false
        case "$tok" in
          -m|--message|-d|--description|-t|--title) qt=${toks[i]:-}; i=$((i+1)); qset=true ;;
          --message=*|--description=*|--title=*)    qt=${tok#*=}; qset=true ;;
          -m?*|-d?*|-t?*)                            qt=${tok:2}; qset=true ;;
          --description-file)                        qf=${toks[i]:-}; i=$((i+1)) ;;
          --description-file=*)                      qf=${tok#*=} ;;
        esac
        if $qset; then
          case "$qt" in -|*'$'*|*'`'*) qa_blind=true ;; esac
          printf '%s' "$qt" | grep -qE "(^|[[:space:]])/(${GL_QA})([[:space:]]|$)" && qa_hit=true
        fi
        if [ -n "$qf" ]; then
          case "$qf" in \~/*) qf="$HOME/${qf#\~/}" ;; /*) ;; *) qf="${cwd:-.}/$qf" ;; esac
          case "$qf" in *'$'*|*'`'*|*/-) qa_blind=true; continue ;; esac
          if [ -f "$qf" ] && [ -r "$qf" ]; then
            grep -qE "^[[:space:]]*/(${GL_QA})([[:space:]]|$)" -- "$qf" 2>/dev/null && qa_hit=true
          else
            qa_blind=true
          fi
        fi
      done
    done <<EOF
$(printf '%s' "$flat" | grep -oE "${GLP}(mr|issue)\s+${GLR}(note|comment|create|new|update)\b[^;&|]*")
EOF
    $qa_hit && human_decision_defer "GitLab quick action (/merge, /approve, /close, /reopen, /ready, /draft …) in a glab note or description carries out a human decision — drop it from the text, or run the matching glab command on the user's explicit request"
    if $qa_blind && [ "$IN_SUBAGENT" = true ]; then
      human_decision_defer "glab note/description text the guard cannot read (missing or '-' file, editor, \$VAR, \$(…)) may hold a GitLab quick action — pass the text inline or as a readable file"
    fi
  fi

  # -- glab label create -n NAME: agent-* labels are free (recorded, so a later deny still wins)
  if printf '%s' "$flat" | grep -qE "${GLP}label\s+${GLR}create\b"; then
    lname=$(printf '%s' "$flat" | grep -oE -- '(-n|--name)[= ]+["'"'"']?[^"'"'"' ]+' | head -1 | sed -E 's/^(-n|--name)[= ]+["'"'"']?//')
    if printf '%s' "$lname" | grep -qE "$AGENT_LABEL_RE"; then pending_allow="glab label create '$lname' (agent-* governance label)"
    else defer "glab label create '${lname:-?}' (non-agent label) — use an agent-* name, or ask the user"; fi
  fi

  # -- glab mr create|new (per clause): sub MRs (-sub- source) must target the ticket branch, never master|main
  if printf '%s' "$flat" | grep -qE "${GLP}mr\s+${GLR}(create|new)\b"; then
    while IFS= read -r clause; do
      [ -n "$clause" ] || continue
      csrc=$(flag_val '-s|--source-branch' "$clause"); ctgt=$(flag_val '-b|--target-branch' "$clause")
      # --fill / --related-issue / title convention (asks are deferred so a later deny still wins)
      # a clause cut out of `sh -c "…"` ends in the wrapper's quote: retry without it
      if ! { words=$(shell_words "$clause") || words=$(shell_words "${clause%[\"\']}"); }; then
        sub_create_rules MR "$csrc" "$ctgt"
        [ -z "$csrc" ] && $in_sub_worktree && deny "glab mr create from inside a sub worktree ($cwd_base) without -s — run it from the main checkout with explicit -s/-b"
        defer "glab mr create — could not parse the command line (unbalanced quotes); pass a literal --title"; continue
      fi
      toks=(); [ -z "$words" ] || while IFS= read -r _w; do toks+=("$_w"); done <<<"$words"
      mfill=false; mrel=false; mtitle=""; mhas_title=false; i=0
      while [ "$i" -lt "${#toks[@]}" ] && [ "${toks[i]}" != create ] && [ "${toks[i]}" != new ]; do i=$((i+1)); done; i=$((i+1))   # skip 'glab [-R x] mr [-R x] create'
      while [ "$i" -lt "${#toks[@]}" ]; do
        tok=${toks[i]}; i=$((i+1))
        case "$tok" in
          -f|--fill|--fill=*) mfill=true ;;
          --related-issue|--related-issue=*) mrel=true; case "$tok" in *=*) ;; *) i=$((i+1)) ;; esac ;;
          -t|--title) mtitle=${toks[i]:-}; mhas_title=true; i=$((i+1)) ;;
          --title=*)  mtitle=${tok#*=}; mhas_title=true ;;
          -s|--source-branch) csrc=${toks[i]:-}; i=$((i+1)) ;;
          --source-branch=*)  csrc=${tok#*=} ;;
          -b|--target-branch) ctgt=${toks[i]:-}; i=$((i+1)) ;;
          --target-branch=*)  ctgt=${tok#*=} ;;
          -s?*) csrc=${tok#-s}; csrc=${csrc#=} ;;   # attached short values: -sbranch, -bmain, -t"x"
          -b?*) ctgt=${tok#-b}; ctgt=${ctgt#=} ;;
          -t?*) mtitle=${tok#-t}; mtitle=${mtitle#=}; mhas_title=true ;;
          -a|--assignee|-d|--description|--description-file|-l|--label|-m|--milestone|--reviewer|-R|--repo|--target-project) i=$((i+1)) ;;
          --*=*|-[adlmR]?*) ;;
          -?*) case "${toks[i]:-}" in -*|'') ;; *) i=$((i+1)) ;; esac ;;   # unknown flag: a value unless it looks like a flag
        esac
      done
      sub_create_rules MR "$csrc" "$ctgt"
      [ -z "$csrc" ] && $in_sub_worktree && deny "glab mr create from inside a sub worktree ($cwd_base) without -s — run it from the main checkout with explicit -s/-b"
      $mfill && defer "glab mr create --fill: generated text may carry a closing keyword or a key-less title; pass --title and --description-file instead"
      $mrel && defer "glab mr create --related-issue links (and may close) a GitLab issue; mention the key in the description instead"
      if $mhas_title && [ -n "$GL_TITLE_RE" ]; then
        case "$mtitle" in
          *'$'*|*'`'*) defer "glab mr create with a \$VAR/backtick title cannot be checked against gitlab.mr_title_re; use a literal title instead" ;;
          *) printf '%s' "$mtitle" | grep -qE -- "$GL_TITLE_RE" \
               || defer "MR title '$mtitle' does not match gitlab.mr_title_re ($GL_TITLE_RE): MR titles start with the ticket key; use a title like that instead (e.g. '${HARNESS_TICKET_EXAMPLE:-PROJ-123} fix parser'), or set gitlab.mr_title_re to change the convention" ;;
        esac
      fi
    done <<EOF
$(printf '%s' "$flat" | grep -oE "${GLP}mr\s+${GLR}(create|new)\b[^;&|]*")
EOF
    # creating an MR is never a write to a human artefact → promptless (label it agent-* so later edits stay promptless)
    pending_allow="glab mr create (creates are ungated; pass --label agent-worked so follow-up edits stay promptless)"
  fi

  # -- glab mr update|note|comment|close|reopen|open|rebase <ref>: gate on the MR's existing labels;
  #    close|reopen|open and update --ready|--draft|--wip|-r are state (a subagent is denied — with a
  #    fail-closed text check for the update flags —, a human MR asks)
  gate_writes "${GLP}mr\s+${GLR}(update|note|comment|close|reopen|open|rebase)\b" fetch_glab_mr '^(-l|--label)$' '^--target-branch$' '^(close|reopen|open)$' \
    '^(--(draft|ready|wip|yes|lock-discussion|unlock-discussion|remove-source-branch|squash-before-merge|unique|skip-ci|fill|fill-commit-body|unassign)|-r|-y|-f)$' "glab mr" '!' \
    '^(--(draft|ready|wip)|-r)$' '^update$' '(^|[[:space:]])(--(ready|draft|wip)|-[A-Za-z]*r[A-Za-z]*)([[:space:]=]|$)'
fi
