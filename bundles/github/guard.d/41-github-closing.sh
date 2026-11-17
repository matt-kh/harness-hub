# shellcheck shell=bash

# Section 41 (bundle github): GitHub closing keywords.
# rule: (close|fix|resolve) #N | owner/repo#N | issue URL in git commit | gh [-R o/r] pr [-R o/r] create|new|edit|merge | gh api (also quoted or $VAR command words, and a keyword or ref written with quotes or escapes) -> deny : a closing keyword would change the issue's state as a side effect; mention #N instead (see #N, refs #N), or use the PR-to-default-branch form below in a github-issues repository
# rule: (close|fix|resolve) #N only in the -b/-t text of a top-level literal gh [-R o/r] pr [-R o/r] create|new -B <default branch> (head not -sub-, not a fork) or gh pr edit N of a PR targeting the default branch, in the cwd checkout's own github.com repository, every #N agent-worked, the repository's tracker github-issues (.harness.toml [repo] tracker > first matching ticket_workflow.trackers entry > github.com host), github.close_issue_on_merge true -> allow : GitHub closes the worked issue when the human merges the PR; 60-github still decides the create/edit. Set github.close_issue_on_merge = false to deny it again and mention #N instead
# rule: closing keyword in gh pr create|new|edit without a literal -B, with a base that is not the repository's default branch, a -sub- or fork head, a non-agent-worked or unreadable #N, more than 10 refs, a multi-line command, cd/pushd/popd, GH_REPO/GH_HOST, sh -c/eval/xargs/$(…)/backticks, a repeated -B/-H/-R/-t/-b/-F, an unknown flag, --, a -R other than the checkout's origin, no canonical github.com/<owner>/<repo> origin, a tracker that resolves to anything but github-issues (a declared one wins: jira declared on github.com denies; a match naming another tracker in guard.env's list or the environment's denies), a .harness.toml tracker the guard cannot read, a malformed ticket_workflow.trackers or one with an invalid match ERE -> deny : run gh pr create|edit as its own one-line command from the ticket branch's checkout with -B <default branch> and the body in -b (or -F file); label the issue agent-worked; or mention #N instead
# ---- GitHub shared definitions (used by 41 and 60) ----
GH="${WORK_TICKET_GH:-gh}"
GHR='((-R[= ]?|--repo[= ])\S+\s+)*'                             # repo flag(s) between gh words: -R o/r, -Ro/r, -R=o/r, --repo[=]o/r, repeated
GHP='\bgh\s+'"$GHR"
# GitHub closes the referenced issue when a closing keyword reaches the default branch (PR
# title/body, commit messages). Not applied to `gh issue *` text (comments have no closing semantics).
GH_CLOSE_RE='\b(clos(e|es|ed)|fix(es|ed)?|resolv(e|es|ed)):?\s+(#[0-9]+|[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#[0-9]+|https?://(www\.)?github\.com/[^/[:space:]]+/[^/[:space:]]+/issues/[0-9]+)'
# GitHub lookups: run in the command's cwd (repo resolution), never prompt, never page.
gh_q() {
  ( cd "${cwd:-.}" 2>/dev/null && GH_PROMPT_DISABLED=1 GH_NO_UPDATE_NOTIFIER=1 GH_PAGER=cat hn_timeout 8 "$GH" "$@" 2>/dev/null )
}
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
# true; `false` from the environment or from guard.env is final): in a repository whose tracker is
# GitHub Issues, the PR to the default branch may close the worked issue(s) when a human merges it.
# The allow path is deliberately narrow and fails closed. The command is one line; every clause
# (cut on unquoted ; & | ( ) only) is a top-level literal `gh pr create|new|edit`; every closing
# ref is a bare #N inside its -b/-t text; flags are parsed the way gh parses them (clusters,
# attached and = values) and an unknown, repeated or `--` one denies. The repository is the cwd
# checkout's github.com origin (-R must name it), the base is that repository's default branch
# and every #N is agent-worked: one batched GraphQL read, under an overall deadline.
GH_CLOSE_Q_RE="${GHP}pr\s+${GHR}(create|new|edit)\b"
GH_CLOSE_MAX_REFS=10
GH_CLOSE_MAX_CLAUSES=5
GH_CLOSE_BUDGET=15        # seconds for every lookup of the allow path together (hooks time out at 20+ s)
gh_close_why=""
# The tracker, resolved the way work-ticket's rf_tracker does (ticket-workflow repo-facts.sh):
# the repository's declaration (.harness.toml [repo] tracker) > the first ticket_workflow.trackers
# entry whose match (ERE, case-insensitive) hits the origin remote id > the host (github.com ->
# github-issues, any other host -> not GitHub Issues). Stricter than rf_tracker, and fail closed:
# a declaration the guard cannot read, a malformed list, an invalid match ERE, a matching entry
# with any tracker but github-issues, or no origin remote denies. The list is read twice: from
# HARNESS_TICKET_TRACKERS (the environment, else guard.env) and from guard.env's own value
# (HN_GENV_TICKET_TRACKERS, engine.sh), so an environment value cannot undo the user's jira entry.
# gh_close_tracker_decl -> rc 0 when the repository declares a tracker (gh_close_tracker = the
# value, gh_close_tsrc = repo); rc 1 when it declares none; rc 2 when a .harness.toml carries a
# tracker the guard cannot read (a dotted or inline-table key, a trailing comment, a quoted key,
# a multi-line string, more than one tracker line, or a file the guard ignored). No git or gh call.
gh_close_tracker_decl() {
  local f n
  gh_close_tracker=""; gh_close_tsrc=""
  if [ -z "${REPO_DECL:-}" ]; then
    # a .harness.toml the engine ignored (too large, too long, unreadable) may still declare one
    [ -n "${REPO_ROOT:-}" ] && [ -e "$REPO_ROOT/.harness.toml" ] && return 2
    return 1
  fi
  f=$REPO_DECL
  if gh_close_tracker=$(hrepo_get "$f" repo tracker 2>/dev/null); then gh_close_tsrc=repo; else gh_close_tracker=""; fi
  # every line that could set a tracker in TOML: a tracker key (bare, quoted or dotted) anywhere,
  # or a repo inline table; only one plain `tracker = "x"` line is readable
  n=$(grep -cE "^[[:space:]]*([\"']?repo[\"']?[[:space:]]*\.[[:space:]]*)?[\"']?tracker[\"']?[[:space:]]*[=.]|^[[:space:]]*[\"']?repo[\"']?[[:space:]]*=" "$f" 2>/dev/null | command tr -d ' ')
  case "${n:-0}" in
    0) [ -z "$gh_close_tsrc" ] && return 1; return 2 ;;            # read without a visible line: unreadable
    1) grep -qE "^[[:space:]]*tracker[[:space:]]*=[[:space:]]*(\"[^\"\\\\]*\"|'[^']*')[[:space:]]*\$" "$f" 2>/dev/null || return 2
       [ -n "$gh_close_tsrc" ] || return 2
       return 0 ;;
    *) return 2 ;;
  esac
}
# gh_close_tracker_list LIST ID -> gh_close_tracker / gh_close_tsrc (config|empty): the first entry
# of LIST (JSON) whose match hits ID. rc 1: LIST is not exactly one JSON array of objects whose
# match/tracker are NUL-free strings; rc 2: an entry's match is empty or not a valid ERE.
gh_close_tracker_list() {
  local cfg="$1" id="$2" m t rc ge
  gh_close_tracker=""; gh_close_tsrc=""
  [ -n "$cfg" ] || return 0
  jq -se 'length == 1 and (.[0] | type == "array" and all(.[]; type == "object"
            and all(.match, .tracker; . == null or (type == "string" and (contains("\u0000") | not)))))' \
     <<<"$cfg" >/dev/null 2>&1 || return 1
  # match and tracker of every entry, NUL-terminated (an ERE may hold any other byte)
  while IFS= read -r -d '' m && IFS= read -r -d '' t; do
    # an invalid ERE: grep exits 2 (GNU, BSD) or 1 with a message (busybox)
    [ -n "$m" ] || return 2
    ge=$(grep -iqE -- "$m" <<<"$id" 2>&1 >/dev/null); rc=$?
    [ "$rc" != 1 ] || [ -z "$ge" ] || rc=2
    case "$rc" in
      0) gh_close_tracker=$t; gh_close_tsrc=config; return 0 ;;
      1) ;;
      *) return 2 ;;
    esac
  done < <(jq -j '.[] | (.match // ""), "\u0000", (.tracker // ""), "\u0000"' <<<"$cfg" 2>/dev/null)
  return 0
}
# gh_close_tracker_resolve ID -> gh_close_tracker / gh_close_tsrc (config|host|empty) of an
# undeclared repository whose origin remote id is ID, from both lists, else the host; a match
# naming anything but github-issues in either list wins. rc 1: a list is malformed; rc 2: a
# list holds an invalid match ERE.
gh_close_tracker_resolve() {
  local id="$1" l rc t="" src=""
  gh_close_tracker=""; gh_close_tsrc=""
  [ -n "$id" ] || return 0
  for l in "${HARNESS_TICKET_TRACKERS:-}" "${HN_GENV_TICKET_TRACKERS:-}"; do
    gh_close_tracker_list "$l" "$id"; rc=$?
    [ "$rc" = 0 ] || return "$rc"
    [ "$gh_close_tsrc" = config ] || continue
    if [ "$gh_close_tracker" != github-issues ] || [ -z "$src" ]; then t=$gh_close_tracker; src=config; fi
    [ "$t" = github-issues ] || break
  done
  if [ -n "$src" ]; then gh_close_tracker=$t; gh_close_tsrc=$src; return 0; fi
  gh_close_tracker=""; gh_close_tsrc=""
  case "${id%%/*}" in github.com) gh_close_tracker=github-issues; gh_close_tsrc=host ;; esac
  return 0
}
# gh_close_remote_id URL -> <host>/<path> of a git remote URL: no scheme, credentials, port or .git;
# host lower-case, ssh./www.github.com read as github.com. The lines between the markers are
# rf_remote_id's (ticket-workflow repo-facts.sh) after its git call, byte for byte: the
# ticket-workflow suite (bundles/ticket-workflow/tests/run.sh) fails when they drift.
gh_close_remote_id() {
  local u="$1" h p
# >>> rf_remote_norm (github guard.d/41-github-closing.sh inlines these lines; ticket-workflow tests/run.sh fails on drift)
  case "$u" in
    [A-Za-z]*://*) u=$(printf '%s\n' "$u" | sed -E 's#^[A-Za-z][A-Za-z0-9+.-]*://([^@/]*@)?##; s#^([^/:]*):[0-9]*#\1#') ;;
    *)             u=$(printf '%s\n' "$u" | sed -E 's#^[^@/:]*@##; s#^([^/:]+):/*#\1/#') ;;
  esac
  while :; do case "$u" in */) u=${u%/} ;; *) break ;; esac; done
  u=${u%.git}
  h=${u%%/*}; p=${u#"$h"}; h=${h##*@}
  [ -n "$h$p" ] || return 0
  h=$(printf '%s' "$h" | LC_ALL=C tr '[:upper:]' '[:lower:]')
  case "$h" in ssh.github.com|www.github.com) h=github.com ;; esac   # aliases of github.com
  printf '%s%s\n' "$h" "$p"
# <<< rf_remote_norm
}
# gh_close_repo_name REPO -> lower-case owner/repo of a -R value or a remote id on github.com
# (owner/repo, github.com/owner/repo, a github.com URL); rc 1 for any other host or shape
gh_close_repo_name() {
  local r
  r=$(printf '%s' "$1" | LC_ALL=C tr '[:upper:]' '[:lower:]')
  case "$r" in *://*) r=$(gh_close_remote_id "$r") ;; esac
  r=${r#github.com/}; r=${r%.git}
  printf '%s' "$r" | grep -qE '^[a-z0-9_.-]+/[a-z0-9_.-]+$' || return 1
  printf '%s' "$r"
}
# gh_close_secs MAX -> seconds left for the next lookup (at most MAX); rc 1 when the deadline passed
gh_close_secs() {
  local left=$((GH_CLOSE_BUDGET - (SECONDS - gh_close_t0)))
  [ "$left" -ge 1 ] || return 1
  [ "$left" -le "$1" ] || left=$1
  printf '%s' "$left"
}
# gh_close_lex TEXT -> gh_close_w (array): the words of TEXT the way the shell reads them (quotes
# and escapes removed); gh_close_b (array): the index in gh_close_w where each clause ends (an
# unquoted ; & | ( or ); indices, not a sentinel word: bash 3.2 mangles $'\001' in arrays).
# Redirection targets are dropped and an unquoted # at word start ends the input (a comment).
# rc 1: unbalanced quote; rc 2: an unquoted glob or brace (* ? [ { }); rc 3: a heredoc or
# herestring (<<).
gh_close_lex() {
  local LC_ALL=C s="$1" n=${#1} i=0 c w="" inw=0 q="" drop=0
  gh_close_w=(); gh_close_b=()
  while [ "$i" -lt "$n" ]; do
    c=${s:i:1}; i=$((i+1))
    if [ -n "$q" ]; then
      if [ "$c" = "$q" ]; then q=""
      elif [ "$q" = '"' ] && [ "$c" = '\' ] && [ "$i" -lt "$n" ]; then
        case "${s:i:1}" in '"'|'\'|'$'|'`') w+=${s:i:1}; i=$((i+1)) ;; *) w+=$c ;; esac
      else w+=$c; fi
      continue
    fi
    case "$c" in
      ' '|$'\t'|';'|'&'|'|'|'('|')')
        if [ "$inw" = 1 ]; then
          if [ "$drop" = 1 ]; then drop=0; else gh_close_w+=("$w"); fi
          w=""; inw=0
        fi
        case "$c" in ' '|$'\t') ;; *) gh_close_b+=("${#gh_close_w[@]}") ;; esac ;;
      "'"|'"') q=$c; inw=1 ;;
      '\') w+=${s:i:1}; i=$((i+1)); inw=1 ;;
      '#') if [ "$inw" = 1 ]; then w+=$c; else break; fi ;;
      '*'|'?'|'['|'{'|'}') return 2 ;;
      '<'|'>')
        if [ "$c" = '<' ] && [ "${s:i:1}" = '<' ]; then return 3; fi
        if [ "$inw" = 1 ]; then
          case "$w" in *[!0-9]*) gh_close_w+=("$w") ;; esac                  # '2>' : drop the fd number
          w=""; inw=0
        fi
        while [ "${s:i:1}" = '>' ]; do i=$((i+1)); done
        drop=1 ;;
      *) w+=$c; inw=1 ;;
    esac
  done
  [ -z "$q" ] || return 1
  if [ "$inw" = 1 ] && [ "$drop" = 0 ]; then gh_close_w+=("$w"); fi
  return 0
}
# gh_close_clause WORD… -> rc 0 when the clause is a literal gh pr create|new|edit that may carry
# closing refs. Sets gc_verb, gc_repo (-R value or empty), gc_head (create: -H value or empty),
# gc_base (-B value or empty), gc_pr (edit: the PR number) and gc_text (the -t/-b values, one per
# line). rc 1 sets gh_close_why (what to do instead).
gh_close_clause() {
  local tok f v s c i=1 nb=0 nh=0 nr=0 nt=0 nbody=0 nf=0 npos=0 parg=""
  local -a t
  t=("$@")
  gc_verb=""; gc_repo=""; gc_head=""; gc_base=""; gc_pr=""; gc_text=""
  case "${t[0]}" in
    gh) ;;
    cd|pushd|popd)
      gh_close_why="${t[0]} before gh: the lookups read the hook's cwd, not the directory gh runs in; run gh pr create|edit from the checkout itself (the tool call's cwd), without cd"; return 1 ;;
    sh|bash|zsh|dash|ksh|eval|xargs|env|exec|command|builtin|sudo|nohup|timeout|nice|time|source|.)
      gh_close_why="gh pr create|edit inside ${t[0]} cannot be checked; run it as its own top-level command"; return 1 ;;
    *)
      gh_close_why="the command runs ${t[0]} next to gh pr create|edit; run gh pr create|edit as its own command (one per tool call)"; return 1 ;;
  esac
  for tok in "${t[@]}"; do
    case "$tok" in *'$'*|*'`'*) gh_close_why="a \$VAR or substitution in gh pr create|edit cannot be checked; write literal values (or the body in -F file)"; return 1 ;; esac
  done
  # gh [-R o/r]… pr [-R o/r]… create|new|edit
  while :; do
    case "${t[i]:-}" in
      pr) [ -z "$gc_verb" ] || break; gc_verb="pr"; i=$((i+1)); continue ;;
      -R|--repo) gc_repo=${t[i+1]:-}; nr=$((nr+1)); i=$((i+2)); continue ;;
      --repo=*)  gc_repo=${t[i]#*=}; nr=$((nr+1)); i=$((i+1)); continue ;;
      -R?*)      gc_repo=${t[i]#-R}; gc_repo=${gc_repo#=}; nr=$((nr+1)); i=$((i+1)); continue ;;
    esac
    break
  done
  case "$gc_verb/${t[i]:-}" in
    pr/create|pr/new|pr/edit) gc_verb=${t[i]}; i=$((i+1)) ;;
    *) gh_close_why="only gh pr create|edit may carry a closing ref; run that command on its own, without other gh commands"; gc_verb=""; return 1 ;;
  esac
  while [ "$i" -lt "${#t[@]}" ]; do
    tok=${t[i]}; i=$((i+1)); f=""; v=""
    case "$tok" in
      --) gh_close_why="-- in gh pr $gc_verb hides flags from the check; drop it"; return 1 ;;
      --*=*) f=${tok%%=*}; v=${tok#*=} ;;
      --draft|--dry-run|--editor|--fill|--fill-first|--fill-verbose|--no-maintainer-edit|--web|--remove-milestone) continue ;;
      --repo|--head|--base|--title|--body|--body-file|--assignee|--label|--milestone|--project|--reviewer|--template|--recover|--add-assignee|--add-label|--add-project|--add-reviewer|--remove-assignee|--remove-label|--remove-project|--remove-reviewer)
        f=$tok; v=${t[i]:-}; i=$((i+1)) ;;
      --?*) gh_close_why="unknown flag $tok in gh pr $gc_verb; use only gh's documented flags"; return 1 ;;
      -?*)
        # a cluster of short flags: booleans (-d -e -f -w) then at most one value flag whose value
        # is the rest of the token (=value too) or the next word (-dB main == -d -B main)
        s=${tok#-}
        while [ -n "$s" ]; do
          c=${s:0:1}; s=${s:1}
          case "$c" in
            d|e|f|w) continue ;;
            R) f=--repo ;; H) f=--head ;; B) f=--base ;; t) f=--title ;; b) f=--body ;; F) f=--body-file ;;
            a|l|m|p|r|T) f=-$c ;;
            *) gh_close_why="unknown flag -$c in gh pr $gc_verb; use only gh's documented flags"; return 1 ;;
          esac
          if [ -n "$s" ]; then v=${s#=}; else v=${t[i]:-}; i=$((i+1)); fi
          break
        done
        [ -n "$f" ] || continue ;;
      *) npos=$((npos+1)); parg=$tok; continue ;;
    esac
    case "$f" in
      --repo) gc_repo=$v; nr=$((nr+1)) ;;
      --head) gc_head=$v; nh=$((nh+1)) ;;
      --base) gc_base=$v; nb=$((nb+1)) ;;
      --title) gc_text="$gc_text$v
"; nt=$((nt+1)) ;;
      --body) gc_text="$gc_text$v
"; nbody=$((nbody+1)) ;;
      --body-file) nf=$((nf+1)) ;;
      --assignee|--label|--milestone|--project|--reviewer|--template|--recover|--add-assignee|--add-label|--add-project|--add-reviewer|--remove-assignee|--remove-label|--remove-project|--remove-reviewer) ;;
      --*) gh_close_why="unknown flag $f in gh pr $gc_verb; use only gh's documented flags"; return 1 ;;
    esac
  done
  if [ "$nr" -gt 1 ] || [ "$nh" -gt 1 ] || [ "$nb" -gt 1 ] || [ "$nt" -gt 1 ] || [ "$nbody" -gt 1 ] || [ "$nf" -gt 1 ]; then
    gh_close_why="a repeated -R/-H/-B/-t/-b/-F in gh pr $gc_verb (gh keeps the last one); pass each once"; return 1
  fi
  case "$gc_verb" in
    create|new)
      [ "$npos" = 0 ] || { gh_close_why="gh pr $gc_verb takes no positional argument ($parg); remove it"; return 1; }
      [ "$nb" = 1 ] && [ -n "$gc_base" ] || { gh_close_why="gh pr $gc_verb without a literal base; pass -B <default branch> explicitly"; return 1; } ;;
    edit)
      [ "$npos" = 1 ] || { gh_close_why="gh pr edit needs exactly one literal PR number; pass it"; return 1; }
      case "$parg" in ''|*[!0-9]*) gh_close_why="gh pr edit $parg: pass the PR number (digits only)"; return 1 ;; esac
      [ "$nh" = 0 ] || { gh_close_why="gh pr edit takes no -H; remove it"; return 1; }
      [ "$nb" = 0 ] || [ -n "$gc_base" ] || { gh_close_why="gh pr edit $parg with an empty -B; pass -B <default branch> or leave the base alone"; return 1; }
      gc_pr=$parg ;;
  esac
  return 0
}
# gh_close_batch OWNER/REPO ISSUES PRS SECS -> .data.repository of ONE read-only GraphQL query:
# defaultBranchRef, iN: issue(number:N){labels} per issue, pN: pullRequest(number:N){base, head,
# cross} per PR. rc 1 on any failure (auth, timeout, not found).
gh_close_batch() {
  local o=${1%%/*} r=${1#*/} n q out
  q="query{repository(owner:\"$o\",name:\"$r\"){defaultBranchRef{name}"
  for n in $2; do q="$q i$n:issue(number:$n){labels(first:50){nodes{name}}}"; done
  for n in $3; do q="$q p$n:pullRequest(number:$n){baseRefName headRefName isCrossRepository}"; done
  q="$q}}"
  out=$(GH_PROMPT_DISABLED=1 GH_NO_UPDATE_NOTIFIER=1 GH_PAGER=cat hn_timeout "$4" "$GH" api --hostname github.com graphql -f "query=$q" 2>/dev/null) || return 1
  printf '%s' "$out" | jq -ce '.data.repository // empty' 2>/dev/null
}
# gh_close_allowed -> rc 0 when every closing ref of the command takes the allowed form
gh_close_allowed() {
  local heads h n_heads n_dq rc total total_dq in_text k start c n v issues="" prs="" n_cl=0 url id origin repo dflt j
  local -a cl_verb cl_repo cl_head cl_base cl_pr
  gh_close_t0=$SECONDS
  case "${HARNESS_GITHUB_CLOSE_ISSUE_ON_MERGE:-true}/${HN_GENV_CLOSE_ON_MERGE:-true}" in
    true/true) ;;
    *) gh_close_why="github.close_issue_on_merge is off; mention #N instead"; return 1 ;;
  esac
  # a declared tracker decides here, before any lookup; an undeclared one is resolved in step 3
  gh_close_tracker_decl; rc=$?
  case "$rc/$gh_close_tracker" in
    0/github-issues|1/*) ;;
    0/*) gh_close_why="this repository's .harness.toml declares a [repo] tracker other than \"github-issues\" (its tickets are not GitHub Issues); mention #N instead"; return 1 ;;
    *) gh_close_why="this repository's .harness.toml declares a tracker the guard cannot read (a dotted or inline-table key, a trailing comment, a quoted key, more than one tracker line, or a file over 16 KiB / 400 lines); write one plain line tracker = \"github-issues\" or tracker = \"jira\" under [repo], without a trailing comment, or mention #N instead"; return 1 ;;
  esac
  # 1. the text: one line, no repository or host override, no substitution, nothing hidden by quotes
  case "$cmd" in *"$_gh_nl"*|*$'\r'*)
    gh_close_why="a multi-line command lets the next line's words read as flags; write gh pr create|edit on one line and pass a long body with -F file"; return 1 ;;
  esac
  if printf '%s\n%s' "$flat" "$flat_dq" | grep -qE '\bGH_(REPO|HOST)\b'; then
    gh_close_why="GH_REPO/GH_HOST hide the repository from the lookup; drop them and pass -R owner/repo from that repository's checkout"; return 1
  fi
  case "$flat" in *'$('*|*'`'*|*'<('*|*'>('*)
    gh_close_why="a \$(…), backtick or <(…) substitution cannot be checked; run gh pr create|edit as its own command with literal values (or the body in -F file)"; return 1 ;;
  esac
  total=$(printf '%s' "$flat_split" | grep -oiE "$GH_CLOSE_RE" | grep -c . | tr -d ' ')
  total_dq=$(printf '%s' "$flat_dq" | grep -oiE "$GH_CLOSE_RE" | grep -c . | tr -d ' ')
  [ "$total" = "$total_dq" ] || { gh_close_why="a closing keyword or ref written with quotes or escapes (Clo\"ses\", \\#N) cannot be checked; write it plainly inside the -b text"; return 1; }
  # every command head that carries closing semantics is a literal gh pr create|new|edit, and the
  # dequoted text shows no extra (quoted or escaped) one
  heads=$(printf '%s' "$flat_split" | grep -oE "$GH_CLOSE_CMD_RE")
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
  # 2. the words, cut into clauses on unquoted ; & | ( ) only
  gh_close_lex "$flat_split"; rc=$?
  case "$rc" in
    0) ;;
    1) gh_close_why="the command could not be parsed (unbalanced quotes); pass balanced literal -t/-b values"; return 1 ;;
    2) gh_close_why="an unquoted glob or brace (* ? [ { }) can expand into extra flags; quote the value"; return 1 ;;
    *) gh_close_why="a heredoc or herestring cannot be checked; pass the body with -b, or with -F file"; return 1 ;;
  esac
  gh_close_b+=("${#gh_close_w[@]}")
  start=0; in_text=0
  for k in "${gh_close_b[@]}"; do
      if [ "$k" -gt "$start" ]; then
        n_cl=$((n_cl+1))
        [ "$n_cl" -le "$GH_CLOSE_MAX_CLAUSES" ] || { gh_close_why="more than $GH_CLOSE_MAX_CLAUSES commands in one line; run each gh pr create|edit as its own command"; return 1; }
        gh_close_clause "${gh_close_w[@]:start:k-start}" || return 1
        cl_verb+=("$gc_verb"); cl_repo+=("$gc_repo"); cl_head+=("$gc_head"); cl_base+=("$gc_base"); cl_pr+=("$gc_pr")
        # the closing refs of this clause: only in its -t/-b text, only bare #N
        while IFS= read -r c; do
          [ -n "$c" ] || continue
          in_text=$((in_text+1))
          v=$(printf '%s' "$c" | grep -oE '#[0-9]+$' | sed 's/^#//')
          if [ -z "$v" ] || ! printf '%s' "$c" | grep -qE '[[:space:]:]#[0-9]+$'; then
            gh_close_why="only a bare #N may be closed (not owner/repo#N or an issue URL); write #N from the repository's own checkout instead"; return 1
          fi
          case " $issues " in *" $v "*) ;; *) issues="$issues${issues:+ }$v" ;; esac
        done <<EOF
$(printf '%s' "$gc_text" | grep -oiE "$GH_CLOSE_RE")
EOF
        [ -z "$gc_pr" ] || case " $prs " in *" $gc_pr "*) ;; *) prs="$prs${prs:+ }$gc_pr" ;; esac
      fi
      start=$k
  done
  [ "$in_text" = "$total" ] || { gh_close_why="a closing ref outside the -t/-b text of gh pr create|edit (another command, a comment, a redirection or another flag); put it only in the PR body (-b or -F file) of that command"; return 1; }
  [ "$(printf '%s\n' $issues | grep -c .)" -le "$GH_CLOSE_MAX_REFS" ] \
    || { gh_close_why="more than $GH_CLOSE_MAX_REFS closing refs in one command; close the rest by hand, or mention them instead"; return 1; }
  # 3. the repository: the cwd checkout's origin remote (its one git read) resolves an undeclared
  # tracker; the origin must be on github.com and a -R must name that same repository
  v=$(gh_close_secs 5) || { gh_close_why="the lookups ran out of time; mention #N instead, or retry"; return 1; }
  url=$(hn_timeout "$v" "${GUARD_GIT:-git}" -C "${cwd:-.}" remote get-url origin 2>/dev/null) || url=""
  id=$(gh_close_remote_id "$url")
  [ -n "$id" ] || { gh_close_why="the cwd checkout has no origin remote (or git did not answer); run gh pr create|edit from the repository's own checkout, or mention #N instead"; return 1; }
  if [ "$gh_close_tsrc" != repo ]; then
    gh_close_tracker_resolve "$id"; rc=$?
    case "$rc" in
      0) ;;
      2) gh_close_why="ticket_workflow.trackers has an entry whose match is empty or not a valid ERE; fix it in harness.toml (harness doctor names the entry) and run harness apply, or mention #N instead"; return 1 ;;
      *) gh_close_why="ticket_workflow.trackers (HARNESS_TICKET_TRACKERS) is not a JSON list of tables; fix it in harness.toml (harness doctor names the entry) and run harness apply, or mention #N instead"; return 1 ;;
    esac
    case "$gh_close_tsrc/$gh_close_tracker" in
      */github-issues) ;;
      config/*) gh_close_why="the first ticket_workflow.trackers entry matching $id names a tracker other than github-issues; mention #N instead, or declare [repo] tracker = \"github-issues\" in the repository's .harness.toml"; return 1 ;;
      *) gh_close_why="no GitHub Issues tracker for $id (no .harness.toml [repo] tracker, no matching ticket_workflow.trackers entry, not a github.com remote); mention #N instead"; return 1 ;;
    esac
  fi
  origin=$(gh_close_repo_name "$id" 2>/dev/null) \
    && [ "$(printf '%s' "$id" | LC_ALL=C tr '[:upper:]' '[:lower:]')" = "github.com/$origin" ] \
    || { gh_close_why="the cwd checkout has no github.com/<owner>/<repo> origin remote (the allow path covers github.com repositories only); run gh pr create|edit from the repository's own checkout, or mention #N instead"; return 1; }
  j=0
  while [ "$j" -lt "${#cl_verb[@]}" ]; do
    if [ -n "${cl_repo[j]}" ]; then
      repo=$(gh_close_repo_name "${cl_repo[j]}") && [ "$repo" = "$origin" ] \
        || { gh_close_why="-R ${cl_repo[j]} is not this checkout's origin ($origin); run the command from that repository's checkout, or mention #N instead"; return 1; }
    fi
    case "${cl_verb[j]}" in
      create|new)
        h=${cl_head[j]}
        if [ -z "$h" ]; then
          $in_sub_worktree && { gh_close_why="gh pr ${cl_verb[j]} from a sub worktree; run it from the main checkout with explicit -H/-B"; return 1; }
          v=$(gh_close_secs 5) || { gh_close_why="the lookups ran out of time; mention #N instead, or retry"; return 1; }
          h=$(hn_timeout "$v" "${GUARD_GIT:-git}" -C "${cwd:-.}" rev-parse --abbrev-ref HEAD 2>/dev/null) || h=""
        fi
        case "$h" in
          ''|HEAD) gh_close_why="gh pr ${cl_verb[j]} with no literal head; pass -H <ticket branch> explicitly"; return 1 ;;
          *:*) gh_close_why="gh pr ${cl_verb[j]} from a fork head ($h); mention #N instead (the fork flow cannot close it)"; return 1 ;;
          *-sub-*) gh_close_why="sub PR ($h) never closes the issue; put the closing ref in the main PR to the default branch instead"; return 1 ;;
        esac ;;
    esac
    j=$((j+1))
  done
  # 4. one batched read: the default branch, every edited PR and every closed issue
  v=$(gh_close_secs 8) || { gh_close_why="the lookups ran out of time; mention #N instead, or retry"; return 1; }
  dflt=$(gh_close_batch "$origin" "$issues" "$prs" "$v") \
    || { gh_close_why="$origin could not be read (auth/timeout, or an issue or PR that does not exist); check it with gh issue view / gh pr view, or mention #N instead"; return 1; }
  repo=$dflt
  dflt=$(jq -r '.defaultBranchRef.name // empty' <<<"$repo")
  [ -n "$dflt" ] || { gh_close_why="the default branch of $origin could not be read; mention #N instead"; return 1; }
  j=0
  while [ "$j" -lt "${#cl_verb[@]}" ]; do
    h=${cl_base[j]}
    if [ "${cl_verb[j]}" = edit ]; then
      n=${cl_pr[j]}
      v=$(jq -c --arg k "p$n" '.[$k] // empty' <<<"$repo")
      [ -n "$v" ] || { gh_close_why="PR $n could not be read; check it with gh pr view, or mention #N instead"; return 1; }
      [ "$(jq -r '.isCrossRepository' <<<"$v")" != true ] || { gh_close_why="PR $n is a cross-repository (fork) PR; mention #N instead"; return 1; }
      h=$(jq -r '.headRefName' <<<"$v")
      case "$h" in *-sub-*) gh_close_why="PR $n is a sub PR ($h); put the closing ref in the main PR to the default branch instead"; return 1 ;; esac
      h=${cl_base[j]}
      [ -n "$h" ] || h=$(jq -r '.baseRefName' <<<"$v")
    fi
    [ "$h" = "$dflt" ] || { gh_close_why="gh pr ${cl_verb[j]} targets $h, not the default branch $dflt; only the PR to the default branch may close the issue — pass -B $dflt, or mention #N instead"; return 1; }
    j=$((j+1))
  done
  for n in $issues; do
    v=$(jq -c --arg k "i$n" '[(.[$k].labels.nodes // [])[] | .name]' <<<"$repo")
    labels_have "$v" "$GOV_LABEL" \
      || { gh_close_why="issue #$n is not labelled $GOV_LABEL (only worked issues close on merge); mention #$n instead, or ask the user to label it"; return 1; }
  done
  return 0
}
_gh_nl='
'
# a closing ref in the plain or the dequoted text (Clo"ses #1", Closes\ \#1) of a git commit / gh pr / gh api line
if { printf '%s' "$flat" | grep -qiE "$GH_CLOSE_RE" || printf '%s' "$flat_dq" | grep -qiE "$GH_CLOSE_RE"; } \
   && { printf '%s' "$flat" | grep -qE "$GH_CLOSE_CMD_RE" || printf '%s' "$flat_dq" | grep -qE "$GH_CLOSE_CMD_RE"; }; then
  gh_close_allowed \
    || deny "closing keyword + GitHub issue ref (#N, owner/repo#N or issue URL) would let GitHub close the issue as a side effect (denied even on request) — mention it instead (e.g. 'part of #12'); ${gh_close_why}"
fi
