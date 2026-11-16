# shellcheck shell=bash

# Section 41 (bundle github): GitHub closing keywords.
# rule: (close|fix|resolve) #N | owner/repo#N | issue URL in git commit | gh [-R o/r] pr [-R o/r] create|new|edit|merge | gh api (also quoted or $VAR command words) -> deny : a closing keyword would change the issue's state as a side effect; mention #N instead (see #N, refs #N), or use the PR-to-default-branch form below in a github-issues repository
# rule: (close|fix|resolve) #N only inside literal gh [-R o/r] pr [-R o/r] create|new -B <default branch> (head not -sub-, not a fork) or gh pr edit N of a PR targeting the default branch, every #N agent-worked, repository declaring [repo] tracker = "github-issues", github.close_issue_on_merge true -> allow : GitHub closes the worked issue when the human merges the PR; 60-github still decides the create/edit. Set github.close_issue_on_merge = false to deny it again and mention #N instead
# rule: closing keyword in gh pr create|new without a literal -B, with -B not the default branch, a -sub- or fork head, a non-agent-worked or unreadable #N, a GH_REPO= prefix or more than 10 refs -> deny : pass -B <default branch> explicitly from the ticket branch, label the issue agent-worked, pass -R owner/repo; or mention #N instead
# ---- GitHub shared definitions (used by 41 and 60) ----
GH="${WORK_TICKET_GH:-gh}"
GHR='((-R[= ]?|--repo[= ])\S+\s+)*'                             # repo flag(s) between gh words: -R o/r, -Ro/r, -R=o/r, --repo[=]o/r, repeated
GHP='\bgh\s+'"$GHR"
# GitHub closes the referenced issue when a closing keyword reaches the default branch (PR
# title/body, commit messages). Not applied to `gh issue *` text (comments have no closing semantics).
GH_CLOSE_RE='\b(clos(e|es|ed)|fix(es|ed)?|resolv(e|es|ed)):?\s+(#[0-9]+|[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#[0-9]+|https?://(www\.)?github\.com/[^/[:space:]]+/[^/[:space:]]+/issues/[0-9]+)'
# GitHub lookups: run in the command's cwd (repo resolution), never prompt, never page.
gh_q() { ( cd "${cwd:-.}" 2>/dev/null && GH_PROMPT_DISABLED=1 GH_NO_UPDATE_NOTIFIER=1 GH_PAGER=cat hn_timeout 8 "$GH" "$@" 2>/dev/null ); }
# fetch_gh_pr REF [REPO] -> normalised PR JSON (N, #N, URL or head branch); rc 1 on failure
fetch_gh_pr() {
  local o; o=$(gh_q pr view "$1" ${2:+-R "$2"} --json labels,headRefName,baseRefName,isCrossRepository) || return 1
  [ -n "$o" ] || return 1
  printf '%s' "$o" | jq -ce '{labels, src: .headRefName, tgt: .baseRefName, cross: .isCrossRepository} | '"$NORM_JQ" 2>/dev/null
}
# fetch_gh_issue REF [REPO] -> normalised issue JSON; rc 1 on failure
fetch_gh_issue() {
  local o; o=$(gh_q issue view "$1" ${2:+-R "$2"} --json labels) || return 1
  [ -n "$o" ] || return 1
  printf '%s' "$o" | jq -ce '{labels} | '"$NORM_JQ" 2>/dev/null
}
# the definitions above are shared with 60-github, so the yield check comes after them
repo_owns github/guard.d/41-github-closing tracker && return 0   # principle 8: the repository's .harness.toml owns this section or domain tracker
# Command words are matched on the plain and the dequoted command (gh "pr" edit), and a $VAR or
# substitution in the noun or verb slot counts too: the closing keyword is what is denied.
GH_CLOSE_CMD_RE="\bgit\s+commit\b|${GHP}pr\s+${GHR}(create|new|edit|merge)\b|${GHP}api\b|${GHP}[^[:space:]]*[\$\`]|${GHP}pr\s+${GHR}[^[:space:]]*[\$\`]"
# The one allowed form (github.close_issue_on_merge → HARNESS_GITHUB_CLOSE_ISSUE_ON_MERGE, default
# true): in a repository whose tracker is GitHub Issues, the PR to the default branch may close the
# worked issue(s) when a human merges it. Every closing ref must be a bare #N inside a literal
# `gh pr create|new|edit` clause (GH_CLOSE_Q_RE) that targets the default branch; every #N is
# agent-worked. Anything else keeps the deny. The lookups run only here, after the keyword and a
# command head matched (time budget).
GH_CLOSE_Q_RE="${GHP}pr\s+${GHR}(create|new|edit)\b"
GH_CLOSE_MAX_REFS=10
gh_close_why=""
# gh_close_tracker_ok -> rc 0 when this repository's tracker is GitHub Issues. Today only the
# repository's own declaration counts (.harness.toml [repo] tracker); no declaration, `jira` or an
# invalid value → rc 1.
gh_close_tracker_ok() {
  local t
  [ -n "${REPO_DECL:-}" ] || return 1
  t=$(hrepo_get "$REPO_DECL" repo tracker 2>/dev/null) || return 1
  [ "$t" = github-issues ]
}
# gh_close_clause CLAUSE -> rc 0 when CLAUSE is a qualifying create/new/edit; appends "REPO N" (REPO - = the cwd repository)
# lines for its #N refs to gh_close_refs. rc 1 sets gh_close_why (what to do instead).
gh_close_clause() {
  local clause="$1" head verb repo rest words tok i base="" phead="" have_base=false pref="" nref=0 mj tgt src cross c n
  local -a toks
  head=$(printf '%s' "$clause" | grep -oE "^${GH_CLOSE_Q_RE}" | head -1)
  [ -n "$head" ] || { gh_close_why="the closing ref is not in a literal gh pr create|edit clause; write the command words unquoted"; return 1; }
  verb=$(printf '%s' "$head" | awk '{print $NF}')
  repo=$(head_repo "$head")
  rest=${clause:${#head}}
  words=$(shell_words "$rest") || words=$(shell_words "${rest%[\"\']}") \
    || { gh_close_why="gh pr $verb could not be parsed (unbalanced quotes); pass balanced literal -t/-b values"; return 1; }
  toks=(); [ -z "$words" ] || while IFS= read -r _w; do toks+=("$_w"); done <<<"$words"
  i=0
  while [ "$i" -lt "${#toks[@]}" ]; do
    tok=${toks[i]}; i=$((i+1))
    case "$tok" in
      -R|--repo) repo=${toks[i]:-}; i=$((i+1)) ;;
      --repo=*)  repo=${tok#*=} ;;
      -R?*)      repo=${tok#-R}; repo=${repo#=} ;;
      -H|--head) phead=${toks[i]:-}; i=$((i+1)) ;;
      --head=*)  phead=${tok#*=} ;;
      -H?*)      phead=${tok#-H} ;;
      -B|--base) base=${toks[i]:-}; have_base=true; i=$((i+1)) ;;
      --base=*)  base=${tok#*=}; have_base=true ;;
      -B?*)      base=${tok#-B}; have_base=true ;;
      -d|--draft|--no-maintainer-edit|-e|--editor|-w|--web|--dry-run|--remove-milestone|-f|--fill|--fill-first|--fill-verbose|--*=*) ;;
      -[tbFlamprT]?*) ;;          # attached short values
      -?*) i=$((i+1)) ;;          # -t -b -F -l -a -r -m -p -T --title --body … take a value
      *) [ -n "$pref" ] || pref=$tok; nref=$((nref+1)) ;;
    esac
  done
  case "$repo" in *'$'*|*'`'*) gh_close_why="gh pr $verb with a \$VAR repo; pass a literal -R owner/repo"; return 1 ;; esac
  case "$verb" in
    create|new)
      case "$base" in
        ''|*'$'*|*'`'*) gh_close_why="gh pr $verb without a literal base; pass -B <default branch> explicitly"; return 1 ;;
      esac
      if [ -z "$phead" ]; then
        $in_sub_worktree && { gh_close_why="gh pr $verb from a sub worktree; run it from the main checkout with explicit -H/-B"; return 1; }
        phead=$(hn_timeout 5 "$GUARD_GIT" -C "${cwd:-.}" rev-parse --abbrev-ref HEAD 2>/dev/null) || phead=""
      fi
      case "$phead" in
        ''|*'$'*|*'`'*) gh_close_why="gh pr $verb with no literal head; pass -H <ticket branch> explicitly"; return 1 ;;
        *:*) gh_close_why="gh pr $verb from a fork head ($phead); mention #N instead (the fork flow cannot close it)"; return 1 ;;
        *-sub-*) gh_close_why="sub PR ($phead) never closes the issue; put the closing ref in the main PR to the default branch instead"; return 1 ;;
      esac ;;
    edit)
      [ "$nref" = 1 ] || { gh_close_why="gh pr edit needs exactly one literal PR number; pass it"; return 1; }
      case "$pref" in *'$'*|*'`'*) gh_close_why="gh pr edit on a \$VAR; use a literal PR number"; return 1 ;; esac
      mj=$(fetch_gh_pr "$pref" "$repo") || { gh_close_why="PR $pref could not be read (auth/timeout/not found); check it with gh pr view, or mention #N instead"; return 1; }
      tgt=$(jq -r '.tgt' <<<"$mj"); src=$(jq -r '.src' <<<"$mj"); cross=$(jq -r '.cross' <<<"$mj")
      [ "$cross" != true ] || { gh_close_why="PR $pref is a cross-repository (fork) PR; mention #N instead"; return 1; }
      case "$src" in *-sub-*) gh_close_why="PR $pref is a sub PR ($src); put the closing ref in the main PR to the default branch instead"; return 1 ;; esac
      if $have_base; then
        case "$base" in ''|*'$'*|*'`'*) gh_close_why="gh pr edit $pref with no literal base; pass -B <default branch> explicitly"; return 1 ;; esac
        tgt=$base
      fi
      base=$tgt ;;
  esac
  printf '%s' "$base" | grep -qE -e "$BASE_BRANCH_RE" \
    || { gh_close_why="gh pr $verb targets $base, not the default branch; only the PR to the default branch may close the issue — pass -B <default branch>, or mention #N instead"; return 1; }
  while IFS= read -r c; do
    [ -n "$c" ] || continue
    n=$(printf '%s' "$c" | grep -oE '#[0-9]+$' | sed 's/^#//')
    if [ -z "$n" ] || ! printf '%s' "$c" | grep -qE '[[:space:]:]#[0-9]+$'; then
      gh_close_why="only a bare #N may be closed (not owner/repo#N or an issue URL); write #N with -R owner/repo instead"; return 1
    fi
    gh_close_refs="$gh_close_refs${repo:--} $n
"
  done <<EOF
$(printf '%s' "$clause" | grep -oiE "$GH_CLOSE_RE")
EOF
  return 0
}
# gh_close_allowed -> rc 0 when every closing ref of the command takes the allowed form
gh_close_allowed() {
  local text="$flat_split" heads h n_heads n_dq n_q clauses clause n_cl=0 total in_cl=0 refs line repo n mj
  gh_close_refs=""
  case "${HARNESS_GITHUB_CLOSE_ISSUE_ON_MERGE:-true}" in
    true) ;;
    *) gh_close_why="github.close_issue_on_merge is off; mention #N instead"; return 1 ;;
  esac
  gh_close_tracker_ok || { gh_close_why="this repository declares no GitHub Issues tracker; mention #N instead, or (if its tickets are GitHub Issues) declare [repo] tracker = \"github-issues\" in .harness.toml and close an agent-worked issue from the PR to the default branch"; return 1; }
  if printf '%s' "$text" | grep -qE '(^|[[:space:];&|(])GH_REPO='; then
    gh_close_why="a GH_REPO=… prefix hides the repository from the lookup; pass -R owner/repo instead"; return 1
  fi
  # every command head that carries closing semantics is a literal gh pr create|new|edit, and the
  # dequoted text shows no extra (quoted or escaped) one
  heads=$(printf '%s' "$text" | grep -oE "$GH_CLOSE_CMD_RE")
  n_heads=$(printf '%s' "$heads" | grep -c . | tr -d ' ')
  n_dq=$(printf '%s' "$flat_dq" | grep -oE "$GH_CLOSE_CMD_RE" | grep -c . | tr -d ' ')
  [ "$n_heads" = "$n_dq" ] || { gh_close_why="gh command words in quotes, escapes or a \$VAR cannot be checked; write gh pr create|edit literally"; return 1; }
  while IFS= read -r h; do
    [ -n "$h" ] || continue
    printf '%s' "$h" | grep -qE "^${GH_CLOSE_Q_RE}$" \
      || { gh_close_why="closing refs reach GitHub only from gh pr create|edit to the default branch, never from git commit, gh pr merge, gh api or a \$VAR command; mention #N there instead"; return 1; }
  done <<EOF
$heads
EOF
  # every closing ref lies inside a qualifying clause, and every clause was cut on its own
  clauses=$(printf '%s' "$text" | grep -oE "${GH_CLOSE_Q_RE}[^;&|]*")
  n_q=$(printf '%s' "$text" | grep -oE "$GH_CLOSE_Q_RE" | grep -c . | tr -d ' ')
  total=$(printf '%s' "$text" | grep -oiE "$GH_CLOSE_RE" | grep -c . | tr -d ' ')
  while IFS= read -r clause; do
    [ -n "$clause" ] || continue
    n_cl=$((n_cl+1))
    in_cl=$((in_cl + $(printf '%s' "$clause" | grep -oiE "$GH_CLOSE_RE" | grep -c . | tr -d ' ')))
    gh_close_clause "$clause" || return 1
  done <<EOF
$clauses
EOF
  [ "$n_cl" = "$n_q" ] || { gh_close_why="more than one gh pr command in one clause; run each gh pr create|edit as its own command"; return 1; }
  [ "$in_cl" = "$total" ] || { gh_close_why="a closing ref outside the gh pr create|edit text (another command, or after a ; & | in the body); put it only in the PR body (-b or -F file) of that command"; return 1; }
  refs=$(printf '%s' "$gh_close_refs" | sort -u)
  [ "$(printf '%s' "$refs" | grep -c . | tr -d ' ')" -le "$GH_CLOSE_MAX_REFS" ] \
    || { gh_close_why="more than $GH_CLOSE_MAX_REFS closing refs in one command; close the rest by hand, or mention them instead"; return 1; }
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    repo=${line%% *}; n=${line#* }; [ "$repo" != - ] || repo=""
    mj=$(fetch_gh_issue "$n" "$repo") || { gh_close_why="issue #$n could not be read (auth/timeout/not found); check it with gh issue view, or mention #$n instead"; return 1; }
    labels_have "$(jq -c '.labels' <<<"$mj")" "$GOV_LABEL" \
      || { gh_close_why="issue #$n is not labelled $GOV_LABEL (only worked issues close on merge); mention #$n instead, or ask the user to label it"; return 1; }
  done <<EOF
$refs
EOF
  return 0
}
if printf '%s' "$flat" | grep -qiE "$GH_CLOSE_RE" \
   && { printf '%s' "$flat" | grep -qE "$GH_CLOSE_CMD_RE" || printf '%s' "$flat_dq" | grep -qE "$GH_CLOSE_CMD_RE"; }; then
  gh_close_allowed \
    || deny "closing keyword + GitHub issue ref (#N, owner/repo#N or issue URL) would let GitHub close the issue as a side effect (denied even on request) — mention it instead (e.g. 'part of #12'); ${gh_close_why}"
fi
