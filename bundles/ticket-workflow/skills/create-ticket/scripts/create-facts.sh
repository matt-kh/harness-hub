#!/usr/bin/env bash
# create-ticket facts for one project: READ-ONLY, prints one JSON object. Never writes.
# Usage: create-facts.sh <PROJECT-KEY>      (Jira)
#        create-facts.sh <owner/repo>       (GitHub Issues via gh; any argument containing "/")
# Config (env wins, then the harness config build/config.json):
#   HARNESS_JIRA_FIELDS_PROBLEM_DESCRIPTION_ID  [jira.fields.<PROJECT>.problem_description, then
#                                               jira.fields.problem_description] -> has_problem_description
#                                               (unset: always false; the type's field_ids still list it)
#   HARNESS_GITHUB_HOST                         [github.host] (default github.com)
# Principle 8: repo_declaration / repo_owns say whether the current repository's .harness.toml owns
# ticket-workflow/skills/create-ticket (or the domain delivery) -> the skill hands over.
set -uo pipefail
# >>> hn_timeout
hn_timeout() {  # SECS CMD [ARGS...]
  local s=$1; shift
  if command -v timeout >/dev/null 2>&1; then timeout "$s" "$@"
  elif command -v gtimeout >/dev/null 2>&1; then gtimeout "$s" "$@"
  else
    python3 -c 'import subprocess, sys
try:
    sys.exit(subprocess.call(sys.argv[2:], timeout=float(sys.argv[1])))
except subprocess.TimeoutExpired:
    sys.exit(124)
except OSError:
    sys.exit(127)' "$s" "$@"
  fi
}
# <<< hn_timeout
# >>> hcfg
hcfg() {  # KEY [DEFAULT]
  local f="${HARNESS_CONFIG_JSON:-${HARNESS_HOME:-$HOME/harness-hub}/build/config.json}" v=""
  if [ -r "$f" ] && command -v jq >/dev/null 2>&1; then
    v=$(jq -r --arg k "$1" 'try (getpath($k | split(".")) // empty | if type == "string" then . else tojson end) catch empty' "$f" 2>/dev/null) || v=""
  fi
  if [ -n "$v" ]; then printf '%s\n' "$v"; elif [ $# -ge 2 ]; then printf '%s\n' "$2"; fi
  return 0
}
# <<< hcfg
# >>> hrepo
hrepo_root() {  # [DIR] -> first ancestor holding .git (dir or worktree file); rc 1 outside a checkout
  local d="${1:-$PWD}" n=0
  case "$d" in /*) ;; *) return 1 ;; esac
  while [ -n "$d" ] && [ "$n" -lt 64 ]; do
    if [ -e "$d/.git" ]; then printf '%s\n' "$d"; return 0; fi
    d=${d%/*}; n=$((n+1))
  done
  return 1
}
hrepo_file() {  # [DIR] -> <root>/.harness.toml; rc 1 when absent
  local r; r=$(hrepo_root "${1:-}") || return 1
  [ -f "$r/.harness.toml" ] && [ -r "$r/.harness.toml" ] || return 1
  printf '%s\n' "$r/.harness.toml"
}
hrepo_trim_to() {  # VAR STR -> VAR = STR without surrounding whitespace (printf -v: no subshell per line)
  local _hs="$2"
  _hs="${_hs#"${_hs%%[![:space:]]*}"}"
  printf -v "$1" '%s' "${_hs%"${_hs##*[![:space:]]}"}"
}
hrepo_unquote_to() {  # VAR STR -> VAR = x for "x" | 'x'; rc 1 on anything else (no escapes in the subset)
  local _hv
  case "$2" in
    \"*\") _hv=${2#\"}; _hv=${_hv%\"}; case "$_hv" in *[\"\\]*) return 1 ;; esac ;;
    \'*\') _hv=${2#\'}; _hv=${_hv%\'}; case "$_hv" in *\'*) return 1 ;; esac ;;
    *) return 1 ;;
  esac
  printf -v "$1" '%s' "$_hv"
}
hrepo_get() {  # FILE SECTION KEY -> value(s), one per line; rc 1 when absent (first occurrence wins)
  local f="$1" want="$2" key="$3" sec="" line k v item rest out="" n=0 found=1 nl='
'
  [ -f "$f" ] && [ -r "$f" ] || return 1
  [ "$(($(wc -c < "$f")))" -le 16384 ] || return 1
  while IFS= read -r line || [ -n "$line" ]; do
    n=$((n+1)); [ "$n" -le 400 ] || return 1
    hrepo_trim_to line "$line"
    case "$line" in
      ''|'#'*) continue ;;
      '['*']') hrepo_trim_to sec "${line#\[}"; hrepo_trim_to sec "${sec%\]}"; continue ;;
      '['*) sec=""; continue ;;
    esac
    [ "$found" = 1 ] && [ "$sec" = "$want" ] || continue
    hrepo_trim_to k "${line%%=*}"
    [ "$k" != "$line" ] && [ "$k" = "$key" ] || continue
    hrepo_trim_to v "${line#*=}"
    case "$v" in
      '['*']')
        rest=${v#\[}; rest=${rest%\]}
        while [ -n "$rest" ]; do
          item=${rest%%,*}
          if [ "$item" = "$rest" ]; then rest=""; else rest=${rest#*,}; fi
          hrepo_trim_to item "$item"; [ -n "$item" ] || continue
          hrepo_unquote_to item "$item" || continue
          out="$out$item$nl"
        done ;;
      *) [ "$want" != owns ] || continue          # [owns] keys are arrays only
         hrepo_unquote_to v "$v" || continue; out="$v$nl" ;;
    esac
    found=0
  done < "$f"
  [ "$found" = 1 ] || printf '%s' "$out"
  return $found
}
hrepo_owns() {  # ID DOMAIN [DIR] -> rc 0 when the repository declares the component or its domain
  local f v nl='
'
  case "$1" in core/guard.d/20-credentials|core/permissions) return 1 ;; esac   # never yield
  f=$(hrepo_file "${3:-}") || return 1
  # no pipes: callers run under `set -o pipefail`, where an early `grep -q` exit is a SIGPIPE failure
  v=$(hrepo_get "$f" owns components 2>/dev/null)
  case "$nl$v$nl" in *"$nl$1$nl"*) return 0 ;; esac
  [ -n "${2:-}" ] || return 1
  v=$(hrepo_get "$f" owns domains 2>/dev/null)
  case "$nl$v$nl" in *"$nl$2$nl"*) return 0 ;; esac
  return 1
}
# <<< hrepo
repo_decl=$(hrepo_file "$PWD") || repo_decl=""
repo_owns=false
if hrepo_owns ticket-workflow/skills/create-ticket delivery "$PWD"; then repo_owns=true; fi
P="${1:-}"; [ -n "$P" ] || { echo '{"error":"usage: create-facts.sh PROJECT|owner/repo"}'; exit 1; }

# ---------------------------------------------------------------- GitHub (read-only)
if [[ "$P" == */* ]]; then
  export GH_PROMPT_DISABLED=1 GH_NO_UPDATE_NOTIFIER=1 GH_PAGER=cat
  err=""
  command -v gh >/dev/null 2>&1 || err="gh not installed (harness install gh)"
  ghhost="${HARNESS_GITHUB_HOST:-$(hcfg github.host github.com)}"
  ghq() { [ -z "$err" ] || return 1; hn_timeout 20 gh "$@" 2>/dev/null; }
  if [ -z "$err" ] && ! hn_timeout 20 gh auth status --hostname "$ghhost" >/dev/null 2>&1; then
    err="gh not authenticated to $ghhost (user runs: gh auth login --hostname $ghhost --git-protocol ssh --web)"
  fi
  me=$(ghq api user --jq .login) || me=""
  repo=$(ghq repo view "$P" --json hasIssuesEnabled,viewerPermission,nameWithOwner) || repo=""
  [ -n "$repo" ] || { [ -n "$err" ] || err="cannot read repo $P"; repo='{}'; }
  labels=$(ghq label list -R "$P" --json name,description --limit 200 | jq -c '[.[].name]' 2>/dev/null) || labels=""
  [ -n "$labels" ] || labels='[]'
  milestones=$(ghq api "repos/$P/milestones?per_page=100" --jq '[.[]|select(.state=="open")|.title]') || milestones=""
  [ -n "$milestones" ] || milestones='[]'
  # issue templates only when the cwd is a clone of this repo (remote path match; URLs never printed)
  templates='[]'
  top=$(git rev-parse --show-toplevel 2>/dev/null) || top=""
  if [ -n "$top" ] && git -C "$top" remote -v 2>/dev/null | grep -qiE "github\.com[:/]${P//./\\.}(\.git)?[[:space:]]"; then
    templates=$(cd "$top" && find .github/ISSUE_TEMPLATE -maxdepth 1 -type f 2>/dev/null | sort | jq -Rsc 'split("\n")|map(select(length>0))')
    [ -n "$templates" ] || templates='[]'
  fi
  jq -n --arg me "$me" --arg p "$P" --arg err "$err" --argjson repo "$repo" \
        --argjson labels "$labels" --argjson milestones "$milestones" --argjson templates "$templates" \
        --arg rdecl "$repo_decl" --argjson rowns "$repo_owns" '
  {provider:"github", me:$me, project:($repo.nameWithOwner // $p),
   creatable:($repo.hasIssuesEnabled == true),
   can_assign:(($repo.viewerPermission // "") | IN("WRITE","MAINTAIN","ADMIN")),
   viewer_permission:($repo.viewerPermission // null),
   labels:$labels, milestones:$milestones, templates:$templates,
   repo_declaration:(if $rdecl == "" then null else $rdecl end), repo_owns:$rowns}
  + (if $err != "" then {error:$err} else {} end)'
  exit 0
fi

# Problem Description field id (org-specific custom field; never guessed)
pd_id="${HARNESS_JIRA_FIELDS_PROBLEM_DESCRIPTION_ID:-}"
[ -n "$pd_id" ] || pd_id=$(hcfg "jira.fields.$P.problem_description")
[ -n "$pd_id" ] || pd_id=$(hcfg jira.fields.problem_description)
case "$pd_id" in '{'*) pd_id=$(jq -r '.id // empty' <<<"$pd_id" 2>/dev/null) ;; esac

me=$(jira whoami 2>/dev/null | jq -r '.name // empty')
perm=$(jira api "/rest/api/2/mypermissions?projectKey=$P" 2>/dev/null)
creatable=$(jq -r '.permissions.CREATE_ISSUES.havePermission == true' <<<"${perm:-{\}}" 2>/dev/null); [ "$creatable" = "true" ] || creatable=false
can_assign=$(jq -r '.permissions.ASSIGN_ISSUE.havePermission == true' <<<"${perm:-{\}}" 2>/dev/null); [ "$can_assign" = "true" ] || can_assign=false
can_attach=$(jq -r '.permissions.CREATE_ATTACHMENT.havePermission == true' <<<"${perm:-{\}}" 2>/dev/null); [ "$can_attach" = "true" ] || can_attach=false

# createmeta: fields is an OBJECT keyed by field id -> to_entries
types=$(jira api "/rest/api/2/issue/createmeta?projectKeys=$P&expand=projects.issuetypes.fields" 2>/dev/null | jq -c --arg pd "$pd_id" '
  [ .projects[0].issuetypes[]? | {
      name, subtask,
      required: [ .fields | to_entries[] | select(.value.required == true)
                  | select((.key | IN("project","issuetype","summary")) | not)
                  | {id: .key, name: .value.name, schema: .value.schema.type,
                     allowed: [ .value.allowedValues[]? | (.value // .name) ]} ],
      has_description: (.fields | has("description")),
      has_problem_description: (if $pd == "" then false else (.fields | has($pd)) end),
      field_ids: ( .fields | to_entries | map({key: .value.name, value: .key}) | from_entries )
  } ]' 2>/dev/null); [ -n "$types" ] || types='[]'

versions=$(jira api "/rest/api/2/project/$P/versions" 2>/dev/null | jq -c '
  [ .[] | select(((.released // false) or (.archived // false)) | not)
        | select(.name | test("^[0-9]+\\.[0-9]+(\\.[0-9]+)+$"))
        | {name, releaseDate: (.releaseDate // null)} ]
  | sort_by(.name | split(".") | map(tonumber)) | reverse' 2>/dev/null); [ -n "$versions" ] || versions='[]'

components=$(jira api "/rest/api/2/project/$P/components" 2>/dev/null | jq -c '
  [ .[].name | select(test("^[0-9]+(\\.[0-9]+)*$") | not) ]' 2>/dev/null); [ -n "$components" ] || components='[]'

priorities=$(jira api /rest/api/2/priority 2>/dev/null | jq -c '[ .[].name ]' 2>/dev/null); [ -n "$priorities" ] || priorities='[]'

labels=$(jira api "/rest/api/2/search?jql=project%3D$P%20AND%20labels%20is%20not%20EMPTY%20ORDER%20BY%20updated%20DESC&fields=labels&maxResults=100" 2>/dev/null \
  | jq -c '[ .issues[]?.fields.labels[]? ] | group_by(.) | map({label: .[0], n: length}) | sort_by(-.n) | .[0:20] | map(.label)' 2>/dev/null); [ -n "$labels" ] || labels='[]'

jq -n --arg me "$me" --arg p "$P" --argjson creatable "$creatable" --argjson can_assign "$can_assign" --argjson can_attach "$can_attach" \
      --argjson types "$types" --argjson versions "$versions" --argjson components "$components" \
      --argjson priorities "$priorities" --argjson labels "$labels" \
      --arg rdecl "$repo_decl" --argjson rowns "$repo_owns" '
{me:$me, project:$p, creatable:$creatable, can_assign:$can_assign, can_attach:$can_attach,
 types:$types, versions_unreleased:$versions, components:$components, priorities:$priorities,
 labels_in_use:$labels, repo_declaration:(if $rdecl == "" then null else $rdecl end), repo_owns:$rowns}'
