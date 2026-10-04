# shellcheck shell=bash

# Section 60 (bundle github): gh governance.
# rule: gh auth token | gh auth status --show-token | gh config get oauth_token -> deny : prints the token; run plain 'gh auth status' instead
# rule: gh api -X non-GET | --input | fields without a method | graphql mutation -> ask : API write; ask the user, or use the matching gh subcommand
# rule: gh pr merge|review, release/repo/workflow/secret/auth/gist/... mutations -> ask : team-visible; ask the user (merges, reviews and releases are human-only)
# rule: gh label create agent-* -> allow : governance label; other labels ask
# rule: gh pr create -> allow : creates are ungated (same -sub- stacked rules as glab)
# rule: gh pr create -f|--fill|--fill-first|--fill-verbose -> ask : generated text may contain a closing keyword; pass -t and -F body-file instead
# rule: gh pr create -t TITLE matching HARNESS_GITHUB_PR_TITLE_FORBID_RE -> ask : issue refs belong in the PR body (mention #N there), not the title; set github.pr_title_forbid_re to change the convention (empty disables)
# rule: gh pr create -t with $VAR or backticks -> ask : the title cannot be checked; use a literal title instead
# rule: gh issue create without -l agent-drafted|agent-created -> deny : provenance label required; use -l agent-drafted (or agent-created) instead
# rule: gh pr|issue edit|comment|close|reopen on an agent-labelled ref -> allow : human refs ask; human issue close|reopen -> deny; fork PRs ask
# ---- GitHub (gh) ------------------------------------------------------------------
# Reads are free (settings.json allow). Order: token denies → gh api (per clause) → team-visible
# ask → label create → pr create (per clause) → issue create (per clause) → PR/issue write gates.
# Asks are deferred so a deny anywhere in the command wins.
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
# PR title convention (github.pr_title_forbid_re → HARNESS_GITHUB_PR_TITLE_FORBID_RE). guard.env omits
# empty values, so an empty key in a guard.env rendered with this bundle (HARNESS_BUNDLES lists
# github) means "disabled"; without a guard.env (tests, hand-installed hook) the default applies.
if [ -n "${HARNESS_GITHUB_PR_TITLE_FORBID_RE+x}" ]; then GH_TITLE_FORBID_RE=$HARNESS_GITHUB_PR_TITLE_FORBID_RE
else case " ${HARNESS_BUNDLES:-} " in *" github "*) GH_TITLE_FORBID_RE="" ;; *) GH_TITLE_FORBID_RE='#[0-9]+' ;; esac; fi
GH_TEAM_RE="${GHP}(pr\s+${GHR}(merge|review|update-branch|lock|unlock)|issue\s+${GHR}(delete|transfer|pin|unpin|lock|unlock|develop)|release\s+${GHR}(create|edit|delete|delete-asset|upload)|repo\s+${GHR}(delete|archive|unarchive|fork|create|rename|edit|sync|deploy-key|autolink)|label\s+${GHR}(edit|delete|clone)|workflow\s+${GHR}(run|enable|disable)|run\s+${GHR}(cancel|rerun|delete)|(secret|variable)\s+${GHR}(set|delete)|gist\s+(create|edit|delete|rename)|auth\s+(login|logout|refresh|setup-git|switch)|(ssh-key|gpg-key)\s+(add|delete)|alias\s+(set|import|delete)|ext(ension)?s?\s+(install|upgrade|remove)|project\s+(close|copy|create|delete|edit|field-create|field-delete|item-add|item-archive|item-create|item-delete|item-edit|link|unlink|mark-template)|cache\s+${GHR}delete)\b"
GH_PR_BOOL_RE='^--?(d|draft|undo|edit-last|create-if-none|delete-last|y|yes|w|web|delete-branch|remove-milestone|dry-run|e|editor)$'
GH_ISSUE_BOOL_RE='^--?(e|editor|w|web|edit-last|create-if-none|delete-last|y|yes|remove-milestone|remove-parent)$'
if printf '%s' "$flat" | grep -qE "${GHP}(pr|issue|label|api|release|repo|run|workflow|secret|variable|gist|auth|config|alias|ext(ension)?s?|ssh-key|gpg-key|project|cache)\b"; then
  # -- 1. tokens are never printed (gh uses them internally)
  printf '%s' "$flat" | grep -qE '\bgh\s+auth\s+token\b' && deny "gh auth token prints the GitHub OAuth token — gh authenticates by itself; check auth with 'gh auth status'"
  printf '%s' "$flat" | grep -qE '\bgh\s+auth\s+status\b[^;&|]*[[:space:]](--show-token|-t)([[:space:]=]|$)' && deny "gh auth status --show-token/-t prints the token — run plain 'gh auth status'"
  printf '%s' "$flat" | grep -qE '\bgh\s+config\s+get\b[^;&|]*\boauth_token\b' && deny "gh config get oauth_token prints the token — check auth with 'gh auth status'"

  # -- 2. gh api (per clause): explicit non-GET → ask; --input → ask; fields without a method
  #       (gh auto-POSTs) → ask; explicit GET/HEAD + fields → pass (query params); graphql passes
  #       only a literal query ('{…}' / 'query …', no operationName, no @file, no $VAR/$(…)).
  while IFS= read -r clause; do
    [ -n "$clause" ] || continue
    if printf '%s' "$clause" | grep -qiE '(^|[[:space:]])(-X|--method)[= ]*["'"'"']?(POST|PUT|PATCH|DELETE)\b'; then defer "gh api write (explicit non-GET method)"; continue; fi
    if printf '%s' "$clause" | grep -qE '(^|[[:space:]])--input([= ]|$)'; then defer "gh api --input (request body from a file/stdin)"; continue; fi
    words=$(shell_words "$clause") || { defer "gh api — could not parse the command line (unbalanced quotes)"; continue; }
    toks=(); [ -z "$words" ] || while IFS= read -r _w; do toks+=("$_w"); done <<<"$words"
    a_method=""; a_fields=false; a_files=false; a_opname=false; a_query=""; a_endpoint=""; i=2   # skip 'gh api'
    while [ "$i" -lt "${#toks[@]}" ]; do
      tok=${toks[i]}; i=$((i+1)); fk=""; fv=""
      case "$tok" in
        -X|--method) a_method=${toks[i]:-}; i=$((i+1)) ;;
        -X*)         a_method=${tok#-X} ;;
        --method=*)  a_method=${tok#*=} ;;
        -f|-F|--field|--raw-field) fk=$tok; fv=${toks[i]:-}; i=$((i+1)) ;;
        --field=*|--raw-field=*)   fk=${tok%%=*}; fv=${tok#*=} ;;
        -f?*|-F?*)                 fk=${tok:0:2}; fv=${tok:2} ;;
        -H|--header|-q|--jq|-t|--template|--hostname|--cache|-p|--preview) i=$((i+1)) ;;
        -*) ;;                     # booleans: --paginate --slurp -i --include --silent --verbose
        *) [ -n "$a_endpoint" ] || a_endpoint=$tok ;;
      esac
      if [ -n "$fk" ]; then
        a_fields=true
        case "${fv%%=*}" in operationName) a_opname=true ;; query) a_query=${fv#*=} ;; esac
        case "$fk" in -F|--field) case "${fv#*=}" in @*) a_files=true ;; esac ;; esac
      fi
    done
    a_m=$(printf '%s' "$a_method" | tr '[:lower:]' '[:upper:]')
    case "$a_m" in ''|GET|HEAD) ;; *) defer "gh api with method '$a_method' (only GET/HEAD pass)"; continue ;; esac
    case "$a_endpoint" in
      graphql|/graphql)
        [ -z "$a_m" ] || { defer "gh api graphql with an explicit method"; continue; }
        $a_files && { defer "gh api graphql reading @file — the operation cannot be inspected"; continue; }
        $a_opname && { defer "gh api graphql with operationName — cannot verify the operation is a query"; continue; }
        if printf '%s' "$clause" | grep -qE '\$|`'; then defer "gh api graphql with \$VAR / \$(…) — the operation cannot be inspected"; continue; fi
        a_q=$(printf '%s' "$a_query" | sed -E 's/^[[:space:]]+//')
        if ! printf '%s' "$a_q" | grep -qE '^(\{|query([^A-Za-z0-9_]|$))' \
           || printf '%s' "$a_q" | grep -qE '(^|[^A-Za-z0-9_])(mutation|subscription)([^A-Za-z0-9_]|$)'; then
          defer "gh api graphql — only literal queries pass; mutations and uninspectable operations ask"; continue
        fi ;;
      *)
        if $a_fields && [ -z "$a_m" ]; then defer "gh api with -f/-F fields and no method auto-POSTs — pass -X GET for query parameters"; continue; fi ;;
    esac
  done <<EOF
$(printf '%s' "$flat" | grep -oE '\bgh\s+api\b[^;&|]*')
EOF

  # -- 3. team-visible actions: humans merge/review; releases, repos, workflows, secrets, auth … ask
  printf '%s' "$flat" | grep -qE "$GH_TEAM_RE" \
    && defer "gh team-visible action (PR merge/review is human-only; releases/repos/workflows/secrets/auth/gists are not governed)"

  # -- 4. gh label create NAME (positional): agent-* labels are free
  while IFS= read -r clause; do
    [ -n "$clause" ] || continue
    lhead=$(printf '%s' "$clause" | grep -oE "^${GHP}label\s+${GHR}create\b" | head -1)
    words=$(shell_words "${clause:${#lhead}}") || { defer "gh label create — could not parse the command line"; continue; }
    toks=(); [ -z "$words" ] || while IFS= read -r _w; do toks+=("$_w"); done <<<"$words"
    lname=""; i=0
    while [ "$i" -lt "${#toks[@]}" ]; do
      tok=${toks[i]}; i=$((i+1))
      case "$tok" in
        -f|--force|--*=*) ;;
        -?*) i=$((i+1)) ;;          # -c/--color, -d/--description, -R/--repo take a value
        *) [ -n "$lname" ] || lname=$tok ;;
      esac
    done
    case "$lname" in *'$'*|'') defer "gh label create '${lname:-?}' — pass a literal label name"; continue ;; esac
    if printf '%s' "$lname" | grep -qE "$AGENT_LABEL_RE"; then pending_allow="gh label create '$lname' (agent-* governance label)"
    else defer "gh label create '$lname' (non-agent label)"; fi
  done <<EOF
$(printf '%s' "$flat" | grep -oE "${GHP}label\s+${GHR}create\b[^;&|]*")
EOF

  # -- 5. gh pr create (per clause): head = -H/--head (user:branch → branch), else the current
  #       branch of cwd (none inside a sub worktree → deny); base = -B/--base; -sub- rules as glab.
  #       --web / --dry-run create nothing here → no decision. --fill* and a title matching
  #       HARNESS_GITHUB_PR_TITLE_FORBID_RE (or a $VAR/backtick title) ask (deferred).
  if printf '%s' "$flat" | grep -qE "${GHP}pr\s+${GHR}create\b"; then
    while IFS= read -r clause; do
      [ -n "$clause" ] || continue
      # a clause cut out of `sh -c "…"` ends in the wrapper's quote: retry without it
      words=$(shell_words "$clause") || words=$(shell_words "${clause%[\"\']}") || { defer "gh pr create — could not parse the command line (unbalanced quotes)"; continue; }
      toks=(); [ -z "$words" ] || while IFS= read -r _w; do toks+=("$_w"); done <<<"$words"
      phead=""; pbase=""; pweb=false; pfill=false; ptitle=""; phas_title=false; i=0
      while [ "$i" -lt "${#toks[@]}" ]; do
        tok=${toks[i]}; i=$((i+1))
        case "$tok" in
          -H|--head) phead=${toks[i]:-}; i=$((i+1)) ;;
          --head=*)  phead=${tok#*=} ;;
          -B|--base) pbase=${toks[i]:-}; i=$((i+1)) ;;
          --base=*)  pbase=${tok#*=} ;;
          -w|--web|--dry-run) pweb=true ;;
          -f|--fill|--fill-first|--fill-verbose|--fill=*|--fill-first=*|--fill-verbose=*) pfill=true ;;
          -t|--title) ptitle=${toks[i]:-}; phas_title=true; i=$((i+1)) ;;
          --title=*)  ptitle=${tok#*=}; phas_title=true ;;
          -d|--draft|--no-maintainer-edit|-e|--editor|--*=*) ;;
          -?*) i=$((i+1)) ;;        # -t -b -F -l -a -r -m -p -T -R --recover take a value
        esac
      done
      $pweb && continue
      if [ -z "$phead" ]; then
        $in_sub_worktree && deny "gh pr create from inside a sub worktree ($cwd_base) without -H — run it from the main checkout with explicit -H/-B"
        phead=$(hn_timeout 5 "$GUARD_GIT" -C "${cwd:-.}" rev-parse --abbrev-ref HEAD 2>/dev/null) || phead=""
      fi
      case "$phead" in *'$'*) defer "gh pr create with a \$VAR head — use a literal branch name"; continue ;; esac
      sub_create_rules PR "${phead#*:}" "$pbase"
      $pfill && defer "gh pr create --fill: generated text may contain a closing keyword; pass -t and -F body-file instead"
      if $phas_title && [ -n "$GH_TITLE_FORBID_RE" ]; then
        case "$ptitle" in
          *'$'*|*'`'*) defer "gh pr create with a \$VAR/backtick title cannot be checked against github.pr_title_forbid_re; use a literal title instead" ;;
          *) printf '%s' "$ptitle" | grep -qE -- "$GH_TITLE_FORBID_RE" \
               && defer "PR title '$ptitle' matches github.pr_title_forbid_re ($GH_TITLE_FORBID_RE): issue refs belong in the PR body (mention #N there), not the title; set github.pr_title_forbid_re to change the convention" ;;
        esac
      fi
      pending_allow="gh pr create (creates are ungated; pass --label agent-worked so follow-up edits stay promptless)"
    done <<EOF
$(printf '%s' "$flat" | grep -oE "${GHP}pr\s+${GHR}create\b[^;&|]*")
EOF
  fi

  # -- 6. gh issue create (per clause): every created issue carries a provenance label
  if printf '%s' "$flat" | grep -qE "${GHP}issue\s+${GHR}create\b"; then
    while IFS= read -r clause; do
      [ -n "$clause" ] || continue
      words=$(shell_words "$clause") || { defer "gh issue create — could not parse the command line (unbalanced quotes)"; continue; }
      toks=(); [ -z "$words" ] || while IFS= read -r _w; do toks+=("$_w"); done <<<"$words"
      iprov=false; iweb=false; i=0
      while [ "$i" -lt "${#toks[@]}" ]; do
        tok=${toks[i]}; i=$((i+1)); lv=""
        case "$tok" in
          -l|--label) lv=${toks[i]:-}; i=$((i+1)) ;;
          --label=*)  lv=${tok#*=} ;;
          -w|--web) iweb=true ;;
          -e|--editor|--*=*) ;;
          -?*) i=$((i+1)) ;;        # -t -b -F -a -m -p -T -R --recover take a value
        esac
        [ -n "$lv" ] && printf '%s' "$lv" | tr ',' '\n' | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//' \
          | grep -qxE "(${DRAFTED_LABEL}|${CREATED_LABEL})" && iprov=true
      done
      $iweb && continue
      $iprov || deny "gh issue create without a provenance label — pass -l ${DRAFTED_LABEL} (create-ticket) or -l ${CREATED_LABEL},${GOV_LABEL} (work-ticket sub-issues)"
      pending_allow="gh issue create carrying a provenance label"
    done <<EOF
$(printf '%s' "$flat" | grep -oE "${GHP}issue\s+${GHR}create\b[^;&|]*")
EOF
  fi

  # -- 7. writes to existing PRs / issues: gated on their labels (fork PRs ask; human issue
  #       close|reopen deny). A GH_REPO=… prefix would make the lookup read the wrong repo → ask.
  GH_PR_W_RE="${GHP}pr\s+${GHR}(edit|comment|close|reopen|ready|update-branch)\b"
  GH_IS_W_RE="${GHP}issue\s+${GHR}(edit|comment|close|reopen)\b"
  if printf '%s' "$flat" | grep -qE "$GH_PR_W_RE|$GH_IS_W_RE" && printf '%s' "$flat" | grep -qE '(^|[[:space:];&|(])GH_REPO='; then
    defer "gh write with GH_REPO=… — the label lookup cannot see it; pass -R owner/repo instead"
  fi
  gate_writes "$GH_PR_W_RE" fetch_gh_pr '^--add-label$' '^(-B|--base)$' '' "$GH_PR_BOOL_RE" "gh pr" '#'
  gate_writes "$GH_IS_W_RE" fetch_gh_issue '^--add-label$' '' '^(close|reopen)$' "$GH_ISSUE_BOOL_RE" "gh issue" '#'
fi
