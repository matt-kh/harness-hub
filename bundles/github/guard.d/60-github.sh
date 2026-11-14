# shellcheck shell=bash

# Section 60 (bundle github): gh governance.
# rule: gh api -X non-GET | --input | fields without a method | graphql mutation -> ask : API write; ask the user, or use the matching gh subcommand
# rule: gh api write (as above) from a subagent -> deny : a raw API write can merge or change state; hand the command back to the main thread
# rule: gh pr merge|review, gh issue delete|transfer -> ask : merging, reviewing and deleting/transferring issues are human-only; run it only on the user's explicit request (they confirm it), or ask the user instead
# rule: gh pr merge|review, gh issue delete|transfer from a subagent -> deny : a subagent never merges, reviews or deletes; hand the command back to the main thread
# rule: (close|fix|resolve) #N in gh pr create|new|edit|merge with -Ro/r or the new alias (forms 41 misses) -> deny : issue state is human-only; mention #N instead (see #N); yields like 41 (tracker)
# rule: gh with quoted/escaped command words or a $VAR/$(…) subcommand -> ask : the subcommand cannot be checked; write it literally and unquoted instead (a subagent is denied)
# rule: gh release/repo/workflow/secret/auth/gist/... mutations -> ask : team-visible; ask the user (releases are human-only)
# rule: gh label create agent-* -> allow : governance label; other labels ask
# rule: gh pr create -> allow : creates are ungated (same -sub- stacked rules as glab; the gh pr new alias too)
# rule: gh pr create -f|--fill|--fill-first|--fill-verbose -> ask : generated text may contain a closing keyword; pass -t and -F body-file instead
# rule: gh pr create -t TITLE matching HARNESS_GITHUB_PR_TITLE_FORBID_RE -> ask : issue refs belong in the PR body (mention #N there), not the title; set github.pr_title_forbid_re to change the convention (empty disables)
# rule: gh pr create -t with $VAR or backticks -> ask : the title cannot be checked; use a literal title instead
# rule: gh issue create|new without -l agent-drafted|agent-created -> deny : provenance label required; use -l agent-drafted (or agent-created) instead
# rule: gh pr edit|comment|close|reopen|ready|update-branch, gh issue edit|comment|close|reopen on an agent-labelled ref -> allow : human refs ask (label it first, or ask the user); fork PRs ask
# rule: gh pr close|reopen|ready, gh issue close|reopen on a human ref -> ask : PR/issue state is a human decision; run it only on the user's explicit request (they confirm it), or ask the user instead
# rule: gh pr close|reopen|ready, gh issue close|reopen from a subagent -> deny : a subagent never changes PR/issue state; hand the command back to the main thread
# repo-override: WORK_TICKET_BASE_BRANCH_RE = "^(master|main)$" -> default/base branches: pushes to them deny, sub MRs/PRs never target them
# repo-override: WORK_TICKET_ALLOW_TRANSITION = "" -> deprecated, no effect since #67: a state change on a human ticket or issue asks on the main thread (and is denied in a subagent) with or without it; remove it
# repo-override: WORK_TICKET_LABELED_DECISION = "allow" -> allow|ask: the decision for writes to agent-labelled tickets, issues, MRs and PRs
# never-yields: prints the developer's stored credential (principle 8 exemption; runs even when the repository owns scm)
# rule: gh auth token | gh auth status --show-token | gh config get oauth_token -> deny : prints the token; run plain 'gh auth status' instead
printf '%s' "$flat" | grep -qE '\bgh\s+auth\s+token\b' && deny "gh auth token prints the GitHub OAuth token — gh authenticates by itself; check auth with 'gh auth status'"
printf '%s' "$flat" | grep -qE '\bgh\s+auth\s+status\b[^;&|]*[[:space:]](--show-token|-t)([[:space:]=]|$)' && deny "gh auth status --show-token/-t prints the token — run plain 'gh auth status'"
printf '%s' "$flat" | grep -qE '\bgh\s+config\s+get\b[^;&|]*\boauth_token\b' && deny "gh config get oauth_token prints the token — check auth with 'gh auth status'"
repo_owns github/guard.d/60-github scm && return 0   # principle 8: the repository's .harness.toml owns this section or domain scm
# ---- GitHub (gh) ------------------------------------------------------------------
# Section-local views (gate_writes, called from here, sees them too): the command without fd
# duplications (2>&1 would cut a clause at its '&'), and a repo flag that also matches the
# attached forms -Ro/r and -R=o/r (41's shared GHR keeps the separated forms only).
# shellcheck disable=SC2168  # sections are wrapped in a function by build.sh
local flat="$flat_split"
# shellcheck disable=SC2168
local GHR='((-R[= ]?|--repo[= ])\S+\s+)?'
# shellcheck disable=SC2168
local GHP='\bgh\s+'"$GHR"
GH_NOUNS='pr|issue|label|release|repo|run|workflow|secret|variable|gist|auth|config|alias|ext(ension)?s?|ssh-key|gpg-key|project|cache'
# Reads are free (settings.json allow). Order: token denies (prelude, above) → gh api (per clause) → team-visible
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
GH_HUMAN_RE="${GHP}(pr\s+${GHR}(merge|review)|issue\s+${GHR}(delete|transfer))\b"
GH_TEAM_RE="${GHP}(pr\s+${GHR}(lock|unlock)|issue\s+${GHR}(pin|unpin|lock|unlock|develop)|release\s+${GHR}(create|edit|delete|delete-asset|upload)|repo\s+${GHR}(delete|archive|unarchive|fork|create|rename|edit|sync|deploy-key|autolink)|label\s+${GHR}(edit|delete|clone)|workflow\s+${GHR}(run|enable|disable)|run\s+${GHR}(cancel|rerun|delete)|(secret|variable)\s+${GHR}(set|delete)|gist\s+(create|edit|delete|rename)|auth\s+(login|logout|refresh|setup-git|switch)|(ssh-key|gpg-key)\s+(add|delete)|alias\s+(set|import|delete)|ext(ension)?s?\s+(install|upgrade|remove)|project\s+(close|copy|create|delete|edit|field-create|field-delete|item-add|item-archive|item-create|item-delete|item-edit|link|unlink|mark-template)|cache\s+${GHR}delete)\b"
GH_PR_BOOL_RE='^--?(d|draft|undo|edit-last|create-if-none|delete-last|y|yes|w|web|delete-branch|remove-milestone|dry-run|e|editor|rebase)$'
GH_ISSUE_BOOL_RE='^--?(e|editor|w|web|edit-last|create-if-none|delete-last|y|yes|remove-milestone|remove-parent)$'
# Closing-keyword backstop for command forms 41's shared regex does not parse (attached -Ro/r,
# the gh pr new alias); it yields exactly like 41 (component 41-github-closing, domain tracker).
if ! repo_owns github/guard.d/41-github-closing tracker \
   && printf '%s' "$flat" | grep -qiE "$GH_CLOSE_RE" \
   && printf '%s' "$flat" | grep -qE "${GHP}pr\s+${GHR}(create|new|edit|merge)\b"; then
  deny "closing keyword + GitHub issue ref (#N, owner/repo#N or issue URL) would let GitHub close the issue; issue state is human-only — mention it instead (e.g. 'part of #12')"
fi
# gh_words TEXT -> one line per gh command head: 'gh api', or 'gh NOUN VERB' (sorted)
gh_words() { printf '%s' "$1" | grep -oE "\bgh\s+${GHR}(api|(${GH_NOUNS})\s+${GHR}[A-Za-z-]+)" | sed -E 's/[[:space:]]+/ /g' | sort; }
# -- 0. hidden subcommands: command words in quotes or escapes (gh "pr" merge, g\h pr merge) and
#       a $VAR / $(…) / backtick in the noun or verb slot cannot be checked → human decision
if printf '%s' "$flat_dq" | grep -qE '\bgh\s' && [ "$(gh_words "$flat")" != "$(gh_words "$flat_dq")" ]; then
  human_decision_defer "gh command words in quotes or escapes cannot be checked — write the gh subcommand unquoted"
fi
if printf '%s' "$flat" | grep -qE "\bgh\s+${GHR}([^[:space:]]*[\$\`]|(${GH_NOUNS})\s+${GHR}[^[:space:]]*[\$\`])"; then
  human_decision_defer "gh subcommand from a \$VAR, \$(…) or backticks cannot be checked — write the subcommand literally"
fi
if printf '%s' "$flat" | grep -qE "${GHP}(${GH_NOUNS}|api)\b"; then
  # -- 1. tokens: denied in the never-yields prelude above

  # -- 2. gh api (per clause): explicit non-GET → ask; --input → ask; fields without a method
  #       (gh auto-POSTs) → ask; explicit GET/HEAD + fields → pass (query params); graphql passes
  #       only a literal query ('{…}' / 'query …', no operationName, no @file, no $VAR/$(…)).
  #       Every write is a human decision (it can merge or change state): a subagent is denied.
  while IFS= read -r clause; do
    [ -n "$clause" ] || continue
    if printf '%s' "$clause" | grep -qiE '(^|[[:space:]])(-X|--method)[= ]*["'"'"']?(POST|PUT|PATCH|DELETE)\b'; then human_decision_defer "gh api write (explicit non-GET method) — ask the user, or use the matching gh subcommand instead"; continue; fi
    if printf '%s' "$clause" | grep -qE '(^|[[:space:]])--input([= ]|$)'; then human_decision_defer "gh api --input (request body from a file/stdin) — ask the user, or use the matching gh subcommand instead"; continue; fi
    words=$(shell_words "$clause") || { human_decision_defer "gh api — could not parse the command line (unbalanced quotes); use balanced literal arguments instead"; continue; }
    toks=(); [ -z "$words" ] || while IFS= read -r _w; do toks+=("$_w"); done <<<"$words"
    a_method=""; a_fields=false; a_files=false; a_opname=false; a_query=""; a_endpoint=""; i=0
    while [ "$i" -lt "${#toks[@]}" ] && [ "${toks[i]}" != api ]; do i=$((i+1)); done; i=$((i+1))   # skip 'gh [-R x] api'
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
    case "$a_m" in ''|GET|HEAD) ;; *) human_decision_defer "gh api with method '$a_method' (only GET/HEAD pass)"; continue ;; esac
    case "$a_endpoint" in
      graphql|/graphql)
        [ -z "$a_m" ] || { human_decision_defer "gh api graphql with an explicit method — drop -X/--method for a read-only query, or ask the user"; continue; }
        $a_files && { human_decision_defer "gh api graphql reading @file — the operation cannot be inspected; pass the query inline as a literal -f query=... instead"; continue; }
        $a_opname && { human_decision_defer "gh api graphql with operationName — cannot verify the operation is a query; drop operationName and pass a single literal query instead"; continue; }
        if printf '%s' "$clause" | grep -qE '\$|`'; then human_decision_defer "gh api graphql with \$VAR / \$(…) — the operation cannot be inspected; pass a literal inline query instead"; continue; fi
        a_q=$(printf '%s' "$a_query" | sed -E 's/^[[:space:]]+//')
        if ! printf '%s' "$a_q" | grep -qE '^(\{|query([^A-Za-z0-9_]|$))' \
           || printf '%s' "$a_q" | grep -qE '(^|[^A-Za-z0-9_])(mutation|subscription)([^A-Za-z0-9_]|$)'; then
          human_decision_defer "gh api graphql — only literal queries pass; mutations and uninspectable operations ask"; continue
        fi ;;
      *)
        if $a_fields && [ -z "$a_m" ]; then human_decision_defer "gh api with -f/-F fields and no method auto-POSTs — pass -X GET for query parameters"; continue; fi ;;
    esac
  done <<EOF
$(printf '%s' "$flat" | grep -oE "${GHP}api\b[^;&|]*")
EOF

  # -- 3. humans merge/review and delete/transfer issues (a human decision: main thread asks, a
  #       subagent is denied); team-visible actions — releases, repos, workflows, secrets, auth … — ask
  printf '%s' "$flat" | grep -qE "$GH_HUMAN_RE" \
    && human_decision_defer "gh pr merge/review or gh issue delete/transfer — merging, reviewing and deleting are human-only; run it only on the user's explicit request (they confirm it), or ask the user instead"
  printf '%s' "$flat" | grep -qE "$GH_TEAM_RE" \
    && defer "gh team-visible action (releases/repos/workflows/secrets/auth/gists are not governed) — ask the user instead"

  # -- 4. gh label create NAME (positional): agent-* labels are free
  while IFS= read -r clause; do
    [ -n "$clause" ] || continue
    lhead=$(printf '%s' "$clause" | grep -oE "^${GHP}label\s+${GHR}create\b" | head -1)
    words=$(shell_words "${clause:${#lhead}}") || { defer "gh label create — could not parse the command line; pass a literal label name instead"; continue; }
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
    else defer "gh label create '$lname' (non-agent label) — use an agent-* name, or ask the user"; fi
  done <<EOF
$(printf '%s' "$flat" | grep -oE "${GHP}label\s+${GHR}create\b[^;&|]*")
EOF

  # -- 5. gh pr create (per clause): head = -H/--head (user:branch → branch), else the current
  #       branch of cwd (none inside a sub worktree → deny); base = -B/--base; -sub- rules as glab.
  #       --web / --dry-run create nothing here → no decision. --fill* and a title matching
  #       HARNESS_GITHUB_PR_TITLE_FORBID_RE (or a $VAR/backtick title) ask (deferred).
  if printf '%s' "$flat" | grep -qE "${GHP}pr\s+${GHR}(create|new)\b"; then
    while IFS= read -r clause; do
      [ -n "$clause" ] || continue
      # a clause cut out of `sh -c "…"` ends in the wrapper's quote: retry without it
      words=$(shell_words "$clause") || words=$(shell_words "${clause%[\"\']}") || { defer "gh pr create — could not parse the command line (unbalanced quotes); pass literal -t/-F/-l values instead"; continue; }
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
          -H?*) phead=${tok#-H} ;;  # attached short values: -Hbranch, -Bmain, -t"x", -Ro/r
          -B?*) pbase=${tok#-B} ;;
          -t?*) ptitle=${tok#-t}; phas_title=true ;;
          -[bFlamprTR]?*) ;;
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
$(printf '%s' "$flat" | grep -oE "${GHP}pr\s+${GHR}(create|new)\b[^;&|]*")
EOF
  fi

  # -- 6. gh issue create (per clause): every created issue carries a provenance label
  if printf '%s' "$flat" | grep -qE "${GHP}issue\s+${GHR}(create|new)\b"; then
    while IFS= read -r clause; do
      [ -n "$clause" ] || continue
      words=$(shell_words "$clause") || { defer "gh issue create — could not parse the command line (unbalanced quotes); pass literal -t/-F/-l values instead"; continue; }
      toks=(); [ -z "$words" ] || while IFS= read -r _w; do toks+=("$_w"); done <<<"$words"
      iprov=false; iweb=false; i=0
      while [ "$i" -lt "${#toks[@]}" ]; do
        tok=${toks[i]}; i=$((i+1)); lv=""
        case "$tok" in
          -l|--label) lv=${toks[i]:-}; i=$((i+1)) ;;
          --label=*)  lv=${tok#*=} ;;
          -w|--web) iweb=true ;;
          -e|--editor|--*=*) ;;
          -l?*) lv=${tok#-l} ;;     # attached short values: -lagent-drafted, -Ro/r
          -[tbFamTpR]?*) ;;
          -?*) i=$((i+1)) ;;        # -t -b -F -a -m -p -T -R --recover take a value
        esac
        [ -n "$lv" ] && printf '%s' "$lv" | tr ',' '\n' | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//' \
          | grep -qxE "(${DRAFTED_LABEL}|${CREATED_LABEL})" && iprov=true
      done
      $iweb && continue
      $iprov || deny "gh issue create without a provenance label — pass -l ${DRAFTED_LABEL} (create-ticket) or -l ${CREATED_LABEL},${GOV_LABEL} (work-ticket sub-issues)"
      pending_allow="gh issue create carrying a provenance label"
    done <<EOF
$(printf '%s' "$flat" | grep -oE "${GHP}issue\s+${GHR}(create|new)\b[^;&|]*")
EOF
  fi

  # -- 7. writes to existing PRs / issues: gated on their labels (fork PRs ask). PR close|reopen|
  #       ready and issue close|reopen are state: a subagent is denied, a human ref asks.
  #       A GH_REPO=… prefix would make the lookup read the wrong repo → ask.
  GH_PR_W_RE="${GHP}pr\s+${GHR}(edit|comment|close|reopen|ready|update-branch)\b"
  GH_IS_W_RE="${GHP}issue\s+${GHR}(edit|comment|close|reopen)\b"
  if printf '%s' "$flat" | grep -qE "$GH_PR_W_RE|$GH_IS_W_RE" && printf '%s' "$flat" | grep -qE '(^|[[:space:];&|(])GH_REPO='; then
    defer "gh write with GH_REPO=… — the label lookup cannot see it; pass -R owner/repo instead"
  fi
  gate_writes "$GH_PR_W_RE" fetch_gh_pr '^--add-label$' '^(-B|--base)$' '^(close|reopen|ready)$' "$GH_PR_BOOL_RE" "gh pr" '#'
  gate_writes "$GH_IS_W_RE" fetch_gh_issue '^--add-label$' '' '^(close|reopen)$' "$GH_ISSUE_BOOL_RE" "gh issue" '#'
fi
