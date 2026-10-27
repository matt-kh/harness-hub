#!/usr/bin/env bash
# retro facts: READ-ONLY, prints one JSON object for the /retro skill. Never writes anything.
# Usage: retro-facts.sh [--workflow work-ticket|create-ticket|manual] [--arg VALUE]
# Output keys:
#   harness        path of the harness CLI used: ${HARNESS_HOME:-~/harness-hub}/bin/harness, else
#                  `harness` on PATH, else null (then review, journal and lessons are null too)
#   git            {root, branch, repo} of the cwd's checkout (repo = basename of root), or null
#   repo_owns      true when the cwd repository's .harness.toml owns lessons/skills/retro or the
#                  domain base (the inlined hrepo block, same rule as `harness repo owns`)
#   active_bundles hub.bundles as rendered (build/config.json _harness.bundles), or null
#   review         `harness lessons review --json` on rc 0 (due) and rc 1 (not due);
#                  {"due": null, "reason": "rc N"} on any other rc; {"due": null, "reason":
#                  "harness CLI not found"} without the CLI
#   journal        `harness lessons journal --json` (lines since retro/last), or null
#   lessons        `harness lessons list --json` (every status but retired), or null
#   workflow       {name, arg}: the caller (work-ticket, create-ticket) or manual
# Config: HARNESS_CONFIG_JSON (default ${HARNESS_HOME:-~/harness-hub}/build/config.json); the CLI
# runs with --config <_harness.config> when the config names one. bash 3.2, jq, git.
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
usage() { echo "usage: retro-facts.sh [--workflow work-ticket|create-ticket|manual] [--arg VALUE]" >&2; exit 2; }
wf=manual; arg=""; have_arg=0
while [ $# -gt 0 ]; do
  case "$1" in
    --workflow) [ $# -ge 2 ] || usage; wf=$2; shift 2 ;;
    --arg) [ $# -ge 2 ] || usage; arg=$2; have_arg=1; shift 2 ;;
    -h|--help) usage ;;
    *) usage ;;
  esac
done
case "$wf" in work-ticket|create-ticket|manual) ;; *) echo "retro-facts.sh: unknown --workflow $wf" >&2; usage ;; esac
command -v jq >/dev/null 2>&1 || { echo "retro-facts.sh: jq is required" >&2; exit 2; }

hb=""
if [ -f "${HARNESS_HOME:-${HOME:-}/harness-hub}/bin/harness" ]; then hb="${HARNESS_HOME:-${HOME:-}/harness-hub}/bin/harness"
else  # the CLI on PATH (the hub links bin/harness into ~/.local/bin)
  _ifs=$IFS; IFS=:
  for _d in ${PATH:-}; do
    if [ -n "$_d" ] && [ -f "$_d/harness" ] && [ -x "$_d/harness" ]; then hb="$_d/harness"; break; fi
  done
  IFS=$_ifs
fi
cfg=$(hcfg _harness.config "")

# cli SUBCOMMAND...: harness lessons SUBCOMMAND --json, stdout only; returns the CLI's rc
cli() {
  local out rc
  out=$(hn_timeout 30 "$hb" lessons "$@" --json ${cfg:+--config "$cfg"} </dev/null 2>/dev/null)
  rc=$?
  printf '%s' "$out"
  return $rc
}
json_or_null() {  # TEXT -> TEXT when it is one JSON value, else null
  if [ -n "$1" ] && printf '%s' "$1" | jq -e -s 'length == 1' >/dev/null 2>&1; then printf '%s' "$1"; else printf 'null'; fi
}

git_json=null
if root=$(git rev-parse --show-toplevel 2>/dev/null) && [ -n "$root" ]; then
  branch=$(git symbolic-ref --short -q HEAD 2>/dev/null) || branch=""
  [ -n "$branch" ] || branch=$(git rev-parse --short HEAD 2>/dev/null) || branch=""
  git_json=$(jq -cn --arg r "$root" --arg b "$branch" '{root: $r, branch: (if $b == "" then null else $b end), repo: ($r | split("/") | last)}')
fi
owns=false
hrepo_owns lessons/skills/retro base "$PWD" && owns=true
bundles=$(json_or_null "$(hcfg _harness.bundles "")")

if [ -n "$hb" ]; then
  r=$(cli review); rrc=$?
  case "$rrc" in
    0|1) review=$(json_or_null "$r")
         [ "$review" != null ] || review=$(jq -cn --arg r "rc $rrc" '{due: null, reason: ("no JSON from harness lessons review, " + $r)}') ;;
    *) review=$(jq -cn --arg r "rc $rrc" '{due: null, reason: $r}') ;;
  esac
  journal=null; lessons=null
  if j=$(cli journal); then journal=$(json_or_null "$j"); fi
  if l=$(cli list); then lessons=$(json_or_null "$l"); fi
  hbj=$(jq -cn --arg h "$hb" '$h')
else
  review='{"due":null,"reason":"harness CLI not found"}'; journal=null; lessons=null; hbj=null
fi

jq -n --argjson harness "$hbj" --argjson git "$git_json" --argjson owns "$owns" --argjson bundles "$bundles" \
  --argjson review "$review" --argjson journal "$journal" --argjson lessons "$lessons" \
  --arg wf "$wf" --arg arg "$arg" --argjson have_arg "$have_arg" \
  '{harness: $harness, git: $git, repo_owns: $owns, active_bundles: $bundles, review: $review,
    journal: $journal, lessons: $lessons,
    workflow: {name: $wf, arg: (if $have_arg == 1 then $arg else null end)}}'
