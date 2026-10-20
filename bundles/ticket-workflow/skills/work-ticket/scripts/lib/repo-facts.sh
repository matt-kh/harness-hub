# shellcheck shell=bash
# work-ticket: provider-neutral, READ-ONLY repo facts. Sourced by preflight.sh (dispatcher),
# gitlab-preflight.sh and github-preflight.sh. Never writes; never prints remote URLs.
#
# Functions:
#   rf_root            -> prints the repo toplevel (exit 1 outside a git repo)
#   rf_host ROOT       -> prints the origin remote host (credentials/user/scheme/path stripped)
#   rf_provider HOST   -> prints github | gitlab | (empty = unknown). GitLab hosts: the regex
#                         $HARNESS_GITLAB_HOSTS_RE, else the literal host $HARNESS_GITLAB_HOST,
#                         else gitlab.host from the harness config,
#                         plus any host containing "gitlab"
#   rf_remote_id ROOT  -> prints <host>/<path> of origin (no scheme, credentials, port or .git;
#                         host lower-case, ssh./www.github.com read as github.com); empty
#                         without an origin
#   rf_tracker ROOT    -> prints one JSON object: the repository's tracker (github-issues | jira),
#                         tracker_source = repo (.harness.toml [repo] tracker) | config
#                         (ticket_workflow.trackers, first `match` ERE that hits the remote id) |
#                         host (github.com -> github-issues, GitLab -> jira) | null, plus project
#                         (jira only) and remote_id. Declared, never guessed past an invalid value.
#   rf_skill_desc FILE -> prints a SKILL.md front matter description on one line (plain, quoted
#                         or folded `>-` / `|` scalars)
#   rf_workflow_desc   -> rc 0 when the description on stdin covers a ticket/issue -> MR/PR
#                         workflow (lookup-only or field-only skills do not)
#   rf_load            -> sets root host def dirty precommit repo_skill repo_decl repo_owns
#                         (exits with JSON error outside a git repo, exactly like the original
#                         preflight)
#
# Principle 8 (user-level by design): the repository's own ticket workflow wins. repo_owns=true
# when <root>/.harness.toml owns ticket-workflow/skills/work-ticket or the domain delivery;
# repo_skill is the first <root>/.claude/skills/*/SKILL.md whose description covers a ticket ->
# MR/PR workflow (any name). Either one means: hand over after the read-only preflight.
# The tracker is declared per repository too: [repo] tracker in the same file wins over the
# user's ticket_workflow.trackers, which wins over the host heuristic (rf_tracker).

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

rf_root() { git rev-parse --show-toplevel 2>/dev/null; }

# >>> rf_tracker
# Canonical copy: work-ticket/scripts/lib/repo-facts.sh. create-ticket/scripts/create-facts.sh
# carries an identical copy between these markers (its suite fails when they drift).
rf_host() {
  git -C "$1" remote get-url origin 2>/dev/null | sed -E 's#^[a-z]+://([^@/]*@)?##; s#^[^@]*@##; s#[:/].*$##'
}

rf_provider() {
  local h re gl
  h=$(printf '%s' "$1" | LC_ALL=C tr '[:upper:]' '[:lower:]')
  re="${HARNESS_GITLAB_HOSTS_RE:-}"
  if [ -z "$re" ]; then
    gl="${HARNESS_GITLAB_HOST:-}"
    [ -n "$gl" ] || gl=$(hcfg gitlab.host)
    [ -z "$gl" ] || re="^$(printf '%s' "$gl" | sed 's/[.]/\\./g')\$"
  fi
  case "$h" in
    github.com|ssh.github.com|www.github.com) echo github; return 0 ;;
  esac
  if [ -n "$re" ] && printf '%s' "$h" | grep -qiE -- "$re"; then echo gitlab; return 0; fi
  case "$h" in
    *gitlab*) echo gitlab ;;
    *)        echo "" ;;
  esac
}

rf_remote_id() {  # ROOT -> <host>/<path> of origin: no scheme, credentials, port or .git; host lower-case,
                  # ssh.github.com / www.github.com read as github.com
  local u h p
  u=$(git -C "${1:-}" remote get-url origin 2>/dev/null) || return 0
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
}

rf_tracker() {  # ROOT -> {tracker, tracker_source: repo|config|host|null, project, remote_id[, error][, warnings]}
  local root="${1:-}" id f t="" p="" src="" err="" warns="" cfg n i m rc ge nl='
'
  id=$(rf_remote_id "$root")
  # 1. the repository's declaration: .harness.toml [repo] tracker / project
  if f=$(hrepo_file "$root") && t=$(hrepo_get "$f" repo tracker); then
    src=repo
    p=$(hrepo_get "$f" repo project) || p=""
    case "$t" in
      github-issues|jira) ;;
      *) err="invalid tracker '$t' in .harness.toml [repo]; use github-issues or jira"; t=""; p="" ;;
    esac
  fi
  # 2. the user's config: ticket_workflow.trackers, first entry whose match (ERE) hits the remote id
  if [ -z "$src" ] && [ -n "$id" ]; then
    cfg=$(hcfg ticket_workflow.trackers)
    n=$(jq -r 'if type == "array" then length else 0 end' <<<"${cfg:-[]}" 2>/dev/null) || n=0
    i=0
    while [ "$i" -lt "${n:-0}" ]; do
      m=$(jq -r --argjson i "$i" '.[$i].match // "" | strings' <<<"$cfg" 2>/dev/null)
      # an invalid ERE: grep exits 2 (GNU, BSD) or 1 with a message (busybox)
      if [ -z "$m" ]; then rc=2; else ge=$(grep -iqE -- "$m" <<<"$id" 2>&1 >/dev/null); rc=$?
        [ "$rc" != 1 ] || [ -z "$ge" ] || rc=2; fi
      case "$rc" in
        0) src=config
           t=$(jq -r --argjson i "$i" '.[$i].tracker // "" | strings' <<<"$cfg" 2>/dev/null)
           p=$(jq -r --argjson i "$i" '.[$i].project // "" | strings' <<<"$cfg" 2>/dev/null)
           case "$t" in
             github-issues|jira) ;;
             *) err="invalid tracker '$t' in ticket_workflow.trackers[$i]; use github-issues or jira"; t=""; p="" ;;
           esac
           break ;;
        1) ;;
        *) warns="${warns}ticket_workflow.trackers[$i].match is not a valid ERE and was skipped (harness doctor names the fix)$nl" ;;
      esac
      i=$((i + 1))
    done
  fi
  # 3. the host: github.com -> GitHub Issues, a GitLab host -> Jira, anything else -> unknown
  if [ -z "$src" ] && [ -n "${id%%/*}" ]; then
    case "$(rf_provider "${id%%/*}")" in
      github) t=github-issues; src=host ;;
      gitlab) t=jira; src=host ;;
    esac
  fi
  if [ -n "$p" ] && [ "$t" != jira ]; then
    warns="${warns}project '$p' is used only with tracker = jira; ignored$nl"; p=""
  fi
  jq -cn --arg t "$t" --arg s "$src" --arg p "$p" --arg id "$id" --arg e "$err" --arg w "$warns" '
    def nn: if . == "" then null else . end;
    {tracker:($t|nn), tracker_source:($s|nn), project:($p|nn), remote_id:($id|nn)}
    + (if $e == "" then {} else {error:$e} end)
    + (if $w == "" then {} else {warnings:($w | split("\n") | map(select(length > 0)))} end)'
}
# <<< rf_tracker

rf_skill_desc() {
  awk 'NR == 1 && $0 !~ /^---[[:space:]]*$/ { exit }
       NR > 1 && $0 ~ /^---[[:space:]]*$/ { exit }
       grab && /^[[:space:]]/ { sub(/^[[:space:]]+/, ""); out = out (out == "" ? "" : " ") $0; next }
       grab { exit }
       /^description:/ { grab = 1; v = $0; sub(/^description:[[:space:]]*/, "", v)
                         if (v !~ /^[>|][-+]?[[:space:]]*$/) out = v; next }
       END { if (out != "") print out }' "$1" 2>/dev/null
}

rf_workflow_desc() {
  local d
  d=$(LC_ALL=C tr '[:upper:]' '[:lower:]')
  printf '%s' "$d" | grep -qE '(ticket|issue)' || return 1
  printf '%s' "$d" | grep -qE '(merge request|pull request|(^|[^a-z0-9])(mrs?|prs?)([^a-z0-9]|$))'
}

# shellcheck disable=SC2034  # rf_load sets globals for the sourcing script (see header), not for this file
rf_load() {
  local f
  root=$(rf_root) || { echo '{"error":"not a git repo"}'; exit 1; }
  host=$(rf_host "$root")
  def=$(git -C "$root" symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##')
  repo_decl=$(hrepo_file "$root") || repo_decl=""
  repo_owns=false
  if hrepo_owns ticket-workflow/skills/work-ticket delivery "$root"; then repo_owns=true; fi
  repo_skill=""
  for f in "$root"/.claude/skills/*/SKILL.md; do
    [ -f "$f" ] || continue
    if rf_skill_desc "$f" | rf_workflow_desc; then repo_skill=$f; break; fi
  done
  dirty=$(git -C "$root" status --porcelain | wc -l | tr -d ' ')
  precommit=false; [ -f "$root/.pre-commit-config.yaml" ] && precommit=true
  return 0
}
