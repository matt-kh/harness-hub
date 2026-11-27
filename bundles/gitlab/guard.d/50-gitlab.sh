# shellcheck shell=bash

# Section 50 (bundle gitlab): glab governance.
# rule: glab api -X non-GET (any case, quoted, attached, $VAR) | payload flag (-f/-F/--field/--raw-field/--form/--input) -> ask : API write; ask the user, or use the matching glab subcommand
# rule: glab api write (as above) from a subagent -> deny : a raw API write can merge or change state; hand the command back to the main thread
# rule: glab mr merge N [-s|--squash|-r|--rebase|-y|--yes|--auto-merge=false] [-R group/project] as the only command on the line, main thread, of an opened non-fork MR labelled agent-worked whose target is not the project's default branch (nor matches WORK_TICKET_BASE_BRANCH_RE) -> allow : the user asked for the merge in the main thread and the MR is agent-worked work that does not land on the default branch; honours WORK_TICKET_LABELED_DECISION
# rule: glab mr merge otherwise (into the default branch, an MR without agent-worked, a fork, closed or unreadable MR, -d, -m/--squash-message text, --sha, --auto-merge=true, any other flag, the accept alias, a compound or wrapped line, quotes) -> ask : merging into the default branch or merging human work is a human decision; run it only on the user's explicit request (they confirm it), or ask the user instead
# rule: glab mr approve|revoke|unapprove|delete, glab issue close|reopen|open|delete -> ask : approving, deleting and issue state are human decisions; run it only on the user's explicit request (they confirm it), or ask the user instead
# rule: glab mr merge|accept|approve|revoke|unapprove|delete, glab issue close|reopen|open|delete from a subagent -> deny : a subagent never merges, approves, deletes or changes issue state; hand the command back to the main thread
# rule: glab quick action (/merge /approve /close /reopen /ready /draft …) in a note, description or title -> ask : it carries out a human decision; drop it from the text, or run the matching glab command on the user's explicit request
# rule: glab quick action, or note/description text the guard cannot read, from a subagent -> deny : a subagent never merges or changes state; pass the text inline and hand state changes back to the main thread
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
GL_MERGE_MSG="glab mr merge — merging is a human decision; run it only on the user's explicit request (they confirm it), or ask the user instead"
GL_NL='
'
GL_CR=$(printf '\r')
# gl_q ARGS… -> glab in the command's cwd (project resolution), bounded; rc 1 on failure
gl_q() { ( cd "${cwd:-.}" 2>/dev/null && hn_timeout 8 "$GLAB" "$@" 2>/dev/null ); }
# gl_mr_merge: the merge label gate, as gh_pr_merge in 60-github. One plain command line that
# merges an opened, non-fork MR labelled agent-worked into a branch that is not the project's
# default branch (glab repo view) and does not match WORK_TICKET_BASE_BRANCH_RE. Flags: the merge
# method, -y, --auto-merge=false and -R group/project only (no -d, commit text or --sha). Anything else,
# and any failed lookup, defers the human-decision ask; a subagent is denied.
gl_mr_merge() {
  local mline tok mnum="" mrepo="" mbad="" seen="" why="" mj mtgt dflt k=1
  local -a mt
  [ "$IN_SUBAGENT" != true ] || { human_decision_defer "$GL_MERGE_MSG"; return 0; }
  # the raw command: $flat drops fd duplications with the digits before them (o/r2>&1 -> o/r)
  mline=$(printf '%s' "$cmd" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')
  case "$cmd" in *"$GL_NL"*|*"$GL_CR"*) why="the command spans more than one line (each line is its own command)" ;; esac
  case "$mline" in
    *[\;\&\|\`\$\(\)\<\>\"\'\\]*) [ -n "$why" ] || why="it is not the only command on the line, or carries quotes, \$VARs or redirections" ;;
  esac
  if [ -z "$why" ]; then
    read -r -a mt <<<"$mline"
    [ "${mt[0]:-}" = glab ] || why="only a plain one-line glab mr merge N [-s|-r] [-y] [-R group/project] is label-checked"
  fi
  while [ -z "$why" ] && [ "$k" -lt "${#mt[@]}" ]; do
    tok=${mt[k]}; k=$((k+1))
    case "$tok" in
      -R|--repo) [ -z "$mrepo" ] && [ "$k" -lt "${#mt[@]}" ] || { mbad=$tok; break; }; mrepo=${mt[k]}; k=$((k+1)) ;;
      --repo=*)  [ -z "$mrepo" ] || { mbad=$tok; break; }; mrepo=${tok#*=} ;;
      mr)        [ -z "$seen" ] || { mbad=$tok; break; }; seen="mr" ;;
      merge)     [ "$seen" = mr ] || { mbad=$tok; break; }; seen="merge" ;;
      -s|--squash|-r|--rebase|-y|--yes|--auto-merge=false) [ "$seen" = merge ] || { mbad=$tok; break; } ;;
      *[!0-9]*)  mbad=$tok; break ;;
      *)         [ "$seen" = merge ] && [ -z "$mnum" ] || { mbad=$tok; break; }; mnum=$tok ;;
    esac
  done
  [ -n "$why" ] || [ -z "$mbad" ] || why="the argument $mbad cannot be checked"
  [ -n "$why" ] || [ "$seen" = merge ] || why="only a plain one-line glab mr merge N [-s|-r] [-y] [-R group/project] is label-checked"
  [ -n "$why" ] || [ -n "$mnum" ] || why="no literal MR number (pass glab mr merge N)"
  case "$mrepo" in
    '') ;;
    *[!A-Za-z0-9_./-]*|/*|*/|*//*|.*|*/.*) [ -n "$why" ] || why="-R $mrepo is not a plain group/project" ;;
    */*) ;;
    *) [ -n "$why" ] || why="-R $mrepo is not a plain group/project" ;;
  esac
  if [ -z "$why" ]; then
    mj=$(gl_q mr view "$mnum" ${mrepo:+-R "$mrepo"} -F json </dev/null) && [ -n "$mj" ] || why="MR !$mnum could not be read"
  fi
  if [ -z "$why" ]; then
    dflt=$(gl_q repo view ${mrepo:+"$mrepo"} -F json </dev/null | jq -r '.default_branch // empty' 2>/dev/null) && [ -n "$dflt" ] \
      || why="the project's default branch could not be read"
  fi
  if [ -z "$why" ]; then
    mtgt=$(jq -r '.target_branch // ""' <<<"$mj" 2>/dev/null)
    if [ "$(jq -r '.state // ""' <<<"$mj" 2>/dev/null)" != opened ]; then why="MR !$mnum is not open"
    elif ! jq -e '(.source_project_id // 0) == (.target_project_id // 1)' <<<"$mj" >/dev/null 2>&1; then why="MR !$mnum is a fork MR"
    elif ! labels_have "$(jq -c '[(.labels // [])[] | if type == "object" then .name else . end]' <<<"$mj" 2>/dev/null)" "$GOV_LABEL"; then why="MR !$mnum is not labelled $GOV_LABEL"
    elif [ -z "$mtgt" ] || [ "$mtgt" = "$dflt" ] || printf '%s' "$mtgt" | grep -qE -e "$BASE_BRANCH_RE"; then
      why="MR !$mnum merges into the default branch ${mtgt:-?}"
    fi
  fi
  [ -n "$why" ] || [ "$LABELED_DECISION" = allow ] || why="WORK_TICKET_LABELED_DECISION=$LABELED_DECISION"
  if [ -n "$why" ]; then human_decision_defer "$GL_MERGE_MSG ($why)"; return 0; fi
  pending_allow="glab mr merge of $GOV_LABEL MR !$mnum into $mtgt (not the default branch; the user asked for it in the main thread)"
}
# Section-local views (gate_writes, called from here, sees them too): the command without fd
# duplications (2>&1 would cut a clause at its '&'), and an optional repo flag between glab words
# (-R g/p, -Rg/p, -R=g/p, --repo g/p, --repo=g/p; before the noun or the verb).
# shellcheck disable=SC2168  # sections are wrapped in a function by build.sh
local flat="$flat_split"
GLR='((-R[= ]?|--repo[= ])\S+\s+)*'   # same text as CL_GLR in 40-gitlab-closing
GLP='\bglab\s+'"$GLR"
GL_NOUNS='mr|issue|release|repo|label'
# GitLab quick actions that carry out a human decision (or retarget) when posted in a note or a
# description; GitLab runs a quick action only at the start of a line.
GL_QA='merge|approve|unapprove|close|reopen|ready|draft|wip|submit_review|target_branch'
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
  printf '%s' "$flat" | grep -qE "${GLP}(mr\s+${GLR}(accept|approve|revoke|unapprove|delete|del)|issue\s+${GLR}(close|reopen|open|delete|del))\b" \
    && human_decision_defer "glab MR merge/approve/revoke/delete or issue close/reopen/delete (a human decision) — run it only on the user's explicit request (they confirm it), or ask the user instead"
  printf '%s' "$flat" | grep -qE "${GLP}mr\s+${GLR}merge\b" && gl_mr_merge
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
