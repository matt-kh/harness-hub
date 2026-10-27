#!/usr/bin/env bash
# lessons bundle: `prompt` hook (neutral envelope = Claude UserPromptSubmit) that records prompt
# SIGNALS in the guard journal, never prompt text (docs/reference/hook-policy.md "Journal").
#
# stdin  {"session_id":"…","cwd":"…","prompt":"…",…}   (read once; transcript files are never read)
# stdout NOTHING, ever: Claude adds UserPromptSubmit stdout to the model's context.
# exit   0 always; jq missing, malformed input or any error -> silent exit 0.
#
# Gate: HARNESS_LESSONS_PROMPT_SIGNALS exactly `true` (lessons.prompt_signals). A prompt that
# starts with `/` (a slash command) or is longer than 600 characters (pasted content) is skipped.
# A prompt matching HARNESS_LESSONS_CORRECTION_RE (grep -Eiq) adds one `correction` line, one
# matching HARNESS_LESSONS_DISSATISFACTION_RE one `dissatisfaction` line: at most one line per
# class per prompt, seven tab-separated fields `ts provider session kind - guard_id repo`, written
# exactly like the guard engine's journal_write (same directory rules, umask 077, retro/current
# pointer, absolute directories only). The prompt is only ever piped to grep; it is never
# written, logged or passed on a command line (no here-strings: bash < 5.1 backs them with a
# temporary file).
#
# Config comes from guard.env next to this script, PARSED like the engine does (never sourced),
# HARNESS_* keys only; a variable already set in the environment wins.
set -u
exec 2>/dev/null   # nothing on stderr either: every failure is silent
_gs="${BASH_SOURCE[0]:-$0}"
case "$_gs" in */*) _gd=${_gs%/*} ;; *) _gd=. ;; esac
_ge="$_gd/guard.env"
if [ -r "$_ge" ]; then
  while IFS= read -r _gl || [ -n "$_gl" ]; do
    case "$_gl" in ''|'#'*) continue ;; esac
    _gk=${_gl%%=*}; _gv=${_gl#*=}
    [ "$_gk" != "$_gl" ] || continue
    case "$_gk" in HARNESS_LESSONS_PROMPT_SIGNALS|HARNESS_LESSONS_CORRECTION_RE|HARNESS_LESSONS_DISSATISFACTION_RE|HARNESS_GUARD_ID|HARNESS_PROVIDER) ;; *) continue ;; esac
    [ -z "${!_gk+x}" ] || continue
    case "$_gv" in
      \'*\') _gv=${_gv#\'}; _gv=${_gv%\'}; _gq="'\\''"; _gv=${_gv//"$_gq"/\'} ;;
      \"*\") _gv=${_gv#\"}; _gv=${_gv%\"} ;;
    esac
    printf -v "$_gk" '%s' "$_gv"
  done < "$_ge" 2>/dev/null
fi
[ "${HARNESS_LESSONS_PROMPT_SIGNALS:-}" = true ] || exit 0
command -v jq >/dev/null 2>&1 || exit 0

input=$(cat 2>/dev/null) || exit 0
# One jq call: line 1 = "s" + session_id, line 2 = "c" + cwd (newlines made invalid), the rest =
# "p" + the prompt. The sentinels keep every field in place when one is empty (command
# substitution strips trailing newlines, so an empty prompt would otherwise shift the split).
_out=$(printf '%s' "$input" | jq -r 'if type != "object" then error("not an object") else
  ("s" + (.session_id // "" | tostring | split("\n") | join("!"))),
  ("c" + (.cwd // "" | tostring | split("\n") | join("!"))), ("p" + (.prompt // "" | tostring)) end' 2>/dev/null) || exit 0
unset input
_nl='
'
case "$_out" in s*"$_nl"c*"$_nl"p*) ;; *) exit 0 ;; esac
session=${_out%%"$_nl"*}; session=${session#s}; _out=${_out#*"$_nl"}
cwd=${_out%%"$_nl"*}; cwd=${cwd#c}; prompt=${_out#*"$_nl"}; prompt=${prompt#p}
unset _out
case "$prompt" in ''|/*) exit 0 ;; esac
case "$prompt" in *[![:space:]]*) ;; *) exit 0 ;; esac   # whitespace only
[ "${#prompt}" -le 600 ] || exit 0

kinds=""
if [ -n "${HARNESS_LESSONS_CORRECTION_RE:-}" ] \
   && { printf '%s\n' "$prompt"; } 2>/dev/null | grep -Eiq -- "$HARNESS_LESSONS_CORRECTION_RE" 2>/dev/null; then
  kinds="correction"
fi
if [ -n "${HARNESS_LESSONS_DISSATISFACTION_RE:-}" ] \
   && { printf '%s\n' "$prompt"; } 2>/dev/null | grep -Eiq -- "$HARNESS_LESSONS_DISSATISFACTION_RE" 2>/dev/null; then
  kinds="$kinds dissatisfaction"
fi
unset prompt
[ -n "$kinds" ] || exit 0

field() {  # VAR VALUE -> VAR = VALUE with every character outside [A-Za-z0-9._-] as _, at most 64, or -
  local LC_ALL=C
  local _jv="${2:-}"
  _jv=${_jv//[!A-Za-z0-9._-]/_}
  printf -v "$1" '%s' "${_jv:0:64}"
  [ -n "${!1}" ] || printf -v "$1" '%s' -
}
repo_name() {  # DIR -> _repo: name of the main checkout of the repository holding DIR (engine rule), or empty
  local d="${1:-}" n=0 r="" line="" g
  _repo=""
  case "$d" in /*) ;; *) return 0 ;; esac
  while [ -n "$d" ] && [ "$n" -lt 64 ]; do
    if [ -e "$d/.git" ]; then r=$d; break; fi
    d=${d%/*}; n=$((n+1))
  done
  [ -n "$r" ] || return 0
  _repo=${r##*/}
  [ -f "$r/.git" ] && [ -r "$r/.git" ] || return 0
  IFS= read -r line 2>/dev/null < "$r/.git" || [ -n "$line" ] || return 0
  case "$line" in 'gitdir: '?*) g=${line#gitdir: } ;; *) return 0 ;; esac
  g=${g%/}
  case "$g" in /*) ;; *) g="$r/$g" ;; esac
  case "$g" in */worktrees/?*) ;; *) return 0 ;; esac
  g=${g%/worktrees/*}
  case "$g" in */.git) g=${g%/.git} ;; *.git) g=${g%.git} ;; *) return 0 ;; esac
  g=${g##*/}
  case "$g" in ''|.|..) return 0 ;; esac
  _repo=$g
}

(
  LC_ALL=C
  prov=-; gid=-; repo=-
  case "$session" in ''|*[!A-Za-z0-9._-]*) session=- ;; esac
  [ "${#session}" -le 64 ] || session=-
  field prov "${HARNESS_PROVIDER:-}"
  field gid "${HARNESS_GUARD_ID:-}"
  repo_name "$cwd"; field repo "$_repo"
  state="${XDG_STATE_HOME:-${HOME:+$HOME/.local/state}}"
  jdir="${HARNESS_JOURNAL_DIR:-${state:+$state/harness/journal}}"
  rdir="${HARNESS_RETRO_DIR:-${state:+$state/harness/retro}}"
  # never relative: a relative dir would land in the hook's cwd (the repository)
  case "$jdir" in /*) ;; *) exit 0 ;; esac
  case "$rdir" in /*) ;; *) exit 0 ;; esac
  umask 077
  ts=$(date -u +%Y-%m-%dT%H:%M:%SZ) || exit 0
  mkdir -p "$jdir" || exit 0
  for k in $kinds; do
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$ts" "$prov" "$session" "$k" - "$gid" "$repo" >> "$jdir/${ts%%T*}.log" || exit 0
  done
  [ "$session" != - ] || exit 0
  mkdir -p "$rdir" && printf '%s\n' "$session" > "$rdir/current"
) </dev/null >/dev/null 2>&1
exit 0
