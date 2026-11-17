# shellcheck shell=bash

# Section 60 (bundle github): gh governance.
# rule: gh api -X non-GET | --input | fields without a method | graphql mutation -> ask : API write; ask the user, or use the matching gh subcommand
# rule: gh api write (as above) from a subagent -> deny : a raw API write can merge or change state; hand the command back to the main thread
# rule: gh pr merge|review, gh issue delete|transfer -> ask : merging, reviewing and deleting/transferring issues are human decisions; run it only on the user's explicit request (they confirm it), or ask the user instead
# rule: gh pr merge|review, gh issue delete|transfer from a subagent -> deny : a subagent never merges, reviews or deletes; hand the command back to the main thread
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
# rule: gh stack merge (also gh extension exec stack, gh-stack, quoted or $VAR verbs) -> ask : merging a stack is a human decision; run it only on the user's explicit request (they confirm it), or ask the user to merge the parts bottom-up
# rule: gh stack merge from a subagent -> deny : a subagent never merges; hand the command back to the main thread
# rule: gh stack view|version|help|feedback|completion, navigation (up|down|top|bottom|trunk|switch|checkout) -> pass : reads and local navigation; nothing is pushed or linked
# rule: gh stack link --base TICKET-BRANCH with literal numbers of agent-labelled -sub- PRs of that ticket branch -> allow : links existing PRs only (no push, no PR create); honours WORK_TICKET_LABELED_DECISION
# rule: gh stack link without --base, with --base matching WORK_TICKET_BASE_BRANCH_RE or a -sub- branch -> deny : the stack would sit on the default branch or a part; pass --base <ticket branch>
# rule: gh stack link with a branch-name argument -> deny : it would push the branch and create an unlabelled PR; create the PR with gh pr create -l agent-worked, then use its number instead
# rule: gh stack link with a PR that is not a -sub- PR of --base (the main PR, another ticket's part) -> deny : the main PR stays outside the stack; pass only the ticket's -sub- PR numbers instead
# rule: gh stack link with an unlabelled or fork PR, a URL, a $VAR, GH_REPO=, an unknown flag or a failed lookup -> ask : the PRs cannot be label-checked; label them (gh pr edit N --add-label agent-worked) and pass literal PR numbers
# rule: gh stack link|submit --open -> ask : marks PRs ready for review, a human decision; run gh pr ready N on the user's explicit request instead
# rule: gh stack link|submit --open from a subagent -> deny : a subagent never changes PR state; hand the command back to the main thread
# rule: gh stack push|submit|sync|rebase|modify|unstack|delete|init|add with the default branch involved (cwd branch, --base, a branch argument, init without --base, the trunk or a branch of gh stack view --json) -> deny : stacks never sit on the default branch; run it on the ticket branch's stack, or use stk sync --stack BR
# rule: gh stack push|submit|sync|rebase|modify|unstack|delete|init|add otherwise -> ask : use stk sync --stack BR (retarget, rebase, lease push), git push --force-with-lease of the -sub- branches, or gh stack link --base BR N… by PR numbers instead
# rule: gh stack alias, an unknown gh stack verb, gh extension exec of another extension -> ask : the guard cannot see the verb behind the wrapper; type gh stack VERB (or the extension's own gh command) instead
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
# Section-local view (gate_writes, called from here, sees it too): the command without fd
# duplications (2>&1 would cut a clause at its '&'). GHR/GHP come from 41 and match the attached
# repo-flag forms (-Ro/r, -R=o/r) too; so do the lookups gh_q, fetch_gh_pr and fetch_gh_issue
# (defined above 41's repo_owns line, so they exist when the repository owns 41 or tracker).
# shellcheck disable=SC2168  # sections are wrapped in a function by build.sh
local flat="$flat_split"
GH_NOUNS='pr|issue|label|release|repo|run|workflow|secret|variable|gist|auth|config|alias|ext(ension)?s?|ssh-key|gpg-key|project|cache|stack'
# Reads are free (settings.json allow). Order: token denies (prelude, above) → gh api (per clause) → team-visible
# ask → label create → pr create (per clause) → issue create (per clause) → PR/issue write gates.
# Asks are deferred so a deny anywhere in the command wins.
# PR title convention (github.pr_title_forbid_re → HARNESS_GITHUB_PR_TITLE_FORBID_RE). guard.env omits
# empty values, so an empty key in a guard.env rendered with this bundle (HARNESS_BUNDLES lists
# github) means "disabled"; without a guard.env (tests, hand-installed hook) the default applies.
if [ -n "${HARNESS_GITHUB_PR_TITLE_FORBID_RE+x}" ]; then GH_TITLE_FORBID_RE=$HARNESS_GITHUB_PR_TITLE_FORBID_RE
else case " ${HARNESS_BUNDLES:-} " in *" github "*) GH_TITLE_FORBID_RE="" ;; *) GH_TITLE_FORBID_RE='#[0-9]+' ;; esac; fi
GH_HUMAN_RE="${GHP}(pr\s+${GHR}(merge|review)|issue\s+${GHR}(delete|transfer))\b"
GH_TEAM_RE="${GHP}(pr\s+${GHR}(lock|unlock)|issue\s+${GHR}(pin|unpin|lock|unlock|develop)|release\s+${GHR}(create|edit|delete|delete-asset|upload)|repo\s+${GHR}(delete|archive|unarchive|fork|create|rename|edit|sync|deploy-key|autolink)|label\s+${GHR}(edit|delete|clone)|workflow\s+${GHR}(run|enable|disable)|run\s+${GHR}(cancel|rerun|delete)|(secret|variable)\s+${GHR}(set|delete)|gist\s+(create|edit|delete|rename)|auth\s+(login|logout|refresh|setup-git|switch)|(ssh-key|gpg-key)\s+(add|delete)|alias\s+(set|import|delete)|ext(ension)?s?\s+(install|upgrade|remove)|project\s+(close|copy|create|delete|edit|field-create|field-delete|item-add|item-archive|item-create|item-delete|item-edit|link|unlink|mark-template)|cache\s+${GHR}delete)\b"
GH_PR_BOOL_RE='^--?(d|draft|undo|edit-last|create-if-none|delete-last|y|yes|w|web|delete-branch|remove-milestone|dry-run|e|editor|rebase)$'
GH_ISSUE_BOOL_RE='^--?(e|editor|w|web|edit-last|create-if-none|delete-last|y|yes|remove-milestone|remove-parent)$'
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
    && human_decision_defer "gh pr merge/review or gh issue delete/transfer — merging, reviewing and deleting are human decisions; run it only on the user's explicit request (they confirm it), or ask the user instead"
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

# -- 8. gh stack (the github/gh-stack extension; also `gh extension exec stack …` and a direct
#       `gh-stack …`). Extensions take no -R: the repository comes from the cwd. merge is a human
#       decision; link is label-gated (literal -sub- PR numbers, --base = the ticket branch);
#       verbs that push, rebase or restack deny when the default branch is involved, else ask;
#       reads and navigation pass. Asks are deferred so a deny anywhere still wins.
GHS_HEAD_RE="(${GHP}(stack|ext(ension)?s?\s+exec\s+stack)|\bgh-stack)"
GHS_PASS_RE='^(view|version|help|feedback|completion|up|down|top|bottom|trunk|switch|checkout)$'
GHS_LOCAL_RE='^(push|submit|sync|rebase|modify|unstack|delete|init|add)$'
# strings under branch-like keys of `gh stack view --json` (the trunk and every layer)
GHS_NAMES_JQ='[paths(type == "string") as $p | select(($p[-1] | tostring) | test("^(trunk|base|basebranch|baserefname|branch|branchname|name|head|headrefname)$"; "i")) | getpath($p)] | .[]'
# ghs_default_branch WHAT VALUE -> deny when VALUE is a default/base branch
ghs_default_branch() {
  [ -n "$2" ] || return 0
  printf '%s' "$2" | grep -qE -e "$BASE_BRANCH_RE" || return 0
  deny "gh stack $sverb with the default branch $2 as $1 — stacks never sit on the default branch: run it on the ticket branch's stack (gh stack init --base <ticket branch>), or use stk sync --stack BR"
}
# ghs_local: push|submit|sync|rebase|modify|unstack|delete|init|add (toks[] = the words after `stack`)
ghs_local() {
  local i=$((sverb_i+1)) tok sbase="" shas_base=false sopen=false sbr sj sn
  local -a spos
  spos=()
  while [ "$i" -lt "${#toks[@]}" ]; do
    tok=${toks[i]}; i=$((i+1))
    case "$tok" in
      -b|--base) sbase=${toks[i]:-}; shas_base=true; i=$((i+1)) ;;
      --base=*|-b=*) sbase=${tok#*=}; shas_base=true ;;
      -b?*) sbase=${tok#-b}; shas_base=true ;;
      -m|--message|--remote) i=$((i+1)) ;;
      --open) sopen=true ;;
      --open=*) case "${tok#*=}" in false|0) ;; *) sopen=true ;; esac ;;
      --*) ;;
      -*m) i=$((i+1)) ;;          # -Am / -um: a cluster ending in -m takes the message
      -*) ;;
      *) spos+=("$tok") ;;
    esac
  done
  if [ "$sverb" = submit ] && $sopen; then
    human_decision_defer "gh stack submit --open marks the PRs ready for review, a human decision — submit without --open and run gh pr ready N on the user's explicit request instead"
  fi
  sbr=$(hn_timeout 5 "$GUARD_GIT" -C "${cwd:-.}" rev-parse --abbrev-ref HEAD 2>/dev/null) || sbr=""
  ghs_default_branch "the current branch" "$sbr"
  case "$sbase" in *'$'*|*'`'*) defer "gh stack $sverb with a \$VAR --base cannot be checked — pass the ticket branch literally" ;; *) ghs_default_branch "--base" "$sbase" ;; esac
  for tok in ${spos[@]+"${spos[@]}"}; do ghs_default_branch "a branch argument" "$tok"; done
  if [ "$sverb" = init ] && ! $shas_base; then
    deny "gh stack init without --base roots the stack on the repository's default branch — pass --base <ticket branch> (the -sub- parts stack on the ticket branch)"
  fi
  if sj=$(gh_q stack view --json) && [ -n "$sj" ]; then
    while IFS= read -r sn; do ghs_default_branch "the stack's trunk or a layer" "$sn"; done <<EOF
$(printf '%s' "$sj" | jq -r "$GHS_NAMES_JQ" 2>/dev/null)
EOF
  fi
  defer "gh stack $sverb pushes, rebases or restacks branches outside the -sub- governance — use stk sync --stack BR (retarget, rebase, lease push), git push --force-with-lease of the -sub- branches, or gh stack link --base BR N… by PR numbers instead"
}
# ghs_link: label gate for gh stack link (toks[] = the words after `stack`)
ghs_link() {
  local i=$((sverb_i+1)) tok lbase="" lhas_base=false lopen=false lbad="" lvar=false p n mj lsrc lml lroot
  local -a lpos lnums
  lpos=(); lnums=()
  while [ "$i" -lt "${#toks[@]}" ]; do
    tok=${toks[i]}; i=$((i+1))
    case "$tok" in
      --base|-b) lbase=${toks[i]:-}; lhas_base=true; i=$((i+1)) ;;
      --base=*|-b=*) lbase=${tok#*=}; lhas_base=true ;;
      --open) lopen=true ;;
      --open=*) case "${tok#*=}" in false|0) ;; *) lopen=true ;; esac ;;
      --remote) i=$((i+1)) ;;
      --remote=*|--no-atomic|--no-atomic=*) ;;
      -*) [ -n "$lbad" ] || lbad=$tok ;;
      *) lpos+=("$tok") ;;
    esac
  done
  $lopen && human_decision_defer "gh stack link --open marks the PRs ready for review, a human decision — link without --open and run gh pr ready N on the user's explicit request instead"
  if printf '%s' "$flat" | grep -qE '(^|[[:space:];&|(])GH_REPO='; then
    defer "gh stack link with GH_REPO=… — the label lookup cannot see it; cd into a checkout of that repository and run it there instead"
  fi
  $lhas_base || deny "gh stack link without --base bottoms the stack on the repository's default branch — pass --base <ticket branch> and the -sub- PR numbers (bottom to top)"
  case "$lbase" in
    *'$'*|*'`'*) lvar=true; defer "gh stack link with a \$VAR --base cannot be checked — pass the ticket branch literally" ;;
    *-sub-*) deny "gh stack link --base $lbase: a -sub- branch is a part, not the stack's base — pass --base <ticket branch> (${lbase%%-sub-*})" ;;
    *) printf '%s' "$lbase" | grep -qE -e "$BASE_BRANCH_RE" \
         && deny "gh stack link --base $lbase: the stack would sit on the default branch — pass --base <ticket branch>; the main PR stays outside the stack" ;;
  esac
  [ -z "$lbad" ] || defer "gh stack link with the unrecognised flag $lbad cannot be checked — use only --base, --remote and --no-atomic"
  [ "${#lpos[@]}" -gt 0 ] || { defer "gh stack link without PR numbers — pass the -sub- PR numbers, bottom to top"; return 0; }
  for p in "${lpos[@]}"; do
    case "$p" in
      *'$'*|*'`'*) defer "gh stack link with a \$VAR argument cannot be checked — pass literal PR numbers" ;;
      http://*|https://*) defer "gh stack link with a PR URL — pass the PR number instead, so its labels can be checked" ;;
      '#'*) defer "gh stack link $p — pass the bare PR number instead" ;;
      *[!0-9]*) deny "gh stack link $p: a branch-name argument pushes the branch and creates an unlabelled PR — create it with gh pr create -H BR -B BLOCKER -l $GOV_LABEL, then use its PR number instead" ;;
      *) lnums+=("$p") ;;
    esac
  done
  for n in ${lnums[@]+"${lnums[@]}"}; do
    mj=$(fetch_gh_pr "$n") || { defer "gh stack link: could not read PR #$n (gh pr view failed: auth/timeout/not found) — check it with gh pr view $n, then retry"; continue; }
    lsrc=$(jq -r '.src' <<<"$mj"); lml=$(jq -c '.labels' <<<"$mj")
    if [ "$(jq -r '.cross' <<<"$mj")" = true ]; then defer "gh stack link: PR #$n is a cross-repository (fork) PR whose labels cannot be governed — ask the user instead"; continue; fi
    case "$lsrc" in
      *-sub-*) ;;
      *) deny "gh stack link: PR #$n ($lsrc) is not a -sub- PR — the main PR stays outside the stack; pass only the ticket's -sub- PR numbers instead: gh stack link --base <ticket branch> N…" ;;
    esac
    lroot=${lsrc%%-sub-*}
    if ! $lvar && [ "$lroot" != "$lbase" ]; then
      deny "gh stack link: PR #$n ($lsrc) is a part of $lroot, not of $lbase — pass --base $lroot and only that ticket's -sub- PRs"
    fi
    labels_match_re "$lml" "$AGENT_LABEL_RE" \
      || defer "gh stack link: PR #$n is not agent-labelled — label it first (gh pr edit $n --add-label $GOV_LABEL) or ask the user"
  done
  [ "$LABELED_DECISION" = allow ] || defer "gh stack link of agent-labelled PRs (WORK_TICKET_LABELED_DECISION=$LABELED_DECISION) — ask the user to confirm it"
  pending_allow="gh stack link of agent-labelled -sub- PRs onto the ticket branch (no push, no PR create)"
}
# a merge in any spelling the dequoted command shows (gh "stack" merge, gh-stack "merge", g\h stack merge)
if printf '%s' "$flat_dq" | grep -qE "${GHS_HEAD_RE}\s+merge\b"; then
  human_decision_defer "gh stack merge — merging a stack is a human decision; run it only on the user's explicit request (they confirm it), or ask the user to merge the parts bottom-up"
fi
# gh extension exec of anything but stack hides the extension's verb
if printf '%s' "$flat" | grep -oE "${GHP}ext(ension)?s?\s+exec\s+\S+" | grep -qvE '\sstack$'; then
  defer "gh extension exec of an extension the guard does not know — run it as gh EXTENSION VERB (gh stack VERB for gh-stack), or ask the user"
fi
if printf '%s' "$flat_dq" | grep -qE "${GHS_HEAD_RE}"; then
  while IFS= read -r clause; do
    [ -n "$clause" ] || continue
    shead=$(printf '%s' "$clause" | grep -oE "^${GHS_HEAD_RE}" | head -1)
    rest=${clause:${#shead}}
    case "$rest" in ''|[[:space:]]*) ;; *) continue ;; esac   # gh-stack-foo, a quote: not this command
    # a clause cut out of `sh -c "…"` ends in the wrapper's quote: retry without it
    words=$(shell_words "$rest") || words=$(shell_words "${rest%[\"\']}") \
      || { defer "gh stack — could not parse the command line (unbalanced quotes); pass balanced literal arguments instead"; continue; }
    toks=(); [ -z "$words" ] || while IFS= read -r _w; do toks+=("$_w"); done <<<"$words"
    sverb=""; sverb_i=0
    while [ "$sverb_i" -lt "${#toks[@]}" ]; do
      case "${toks[sverb_i]}" in -*) sverb_i=$((sverb_i+1)) ;; *) sverb=${toks[sverb_i]}; break ;; esac
    done
    case "$sverb" in
      '') continue ;;                                   # gh stack / --help / --version print help
      *'$'*|*'`'*) human_decision_defer "gh stack verb from a \$VAR, \$(…) or backticks cannot be checked — write the verb literally"; continue ;;
      merge) human_decision_defer "gh stack merge — merging a stack is a human decision; run it only on the user's explicit request (they confirm it), or ask the user to merge the parts bottom-up"; continue ;;
      alias) defer "gh stack alias installs a wrapper (gs) that hides the verb from the guard — type gh stack VERB instead"; continue ;;
      link) ghs_link; continue ;;
    esac
    if printf '%s' "$sverb" | grep -qE "$GHS_PASS_RE"; then continue; fi
    if printf '%s' "$sverb" | grep -qE "$GHS_LOCAL_RE"; then ghs_local; continue; fi
    # not a word (a path after a gh-stack URL: git clone …/gh-stack /tmp/x) → not this command
    printf '%s' "$sverb" | grep -qE '^[A-Za-z][A-Za-z0-9-]*$' || continue
    defer "gh stack $sverb is not a verb the guard knows — use a documented gh stack verb, or ask the user"
  done <<EOF
$(printf '%s' "$flat" | grep -oE "${GHS_HEAD_RE}([[:space:]][^;&|]*)?")
EOF
fi
