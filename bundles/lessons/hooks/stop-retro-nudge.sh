#!/usr/bin/env bash
# lessons bundle: `stop` hook (neutral envelope = Claude Stop) that nudges once per session when
# the session's journal signals meet the review criteria (`harness lessons review`, rc 0).
#
# stdin  {"session_id":"…","stop_hook_active":false,…}: only these two keys are read;
#        transcript files are never opened.
# stdout nothing, or exactly one JSON object
#        {"systemMessage":"harness: this session met the review criteria (<counts>); run /retro"}
#        never a decision: this hook never blocks.
# exit   0 always.
#
# Silent when: stop_hook_active is true; HARNESS_LESSONS_JOURNAL is not exactly `true`; jq is
# missing; stdin is malformed; the session id is missing or not [A-Za-z0-9._-]{1,64}; the
# session was already nudged (<retro dir>/sessions/<sid> exists); the retro directory is empty
# or relative; `harness lessons review --session <sid>` exits anything but 0 (1 not due, 3 no
# signals, 4 error, anything else) or does not finish within 3 seconds; the marker cannot be
# written (so a per-turn event such as Gemini's AfterAgent never repeats the nudge).
#
# Config comes from guard.env next to this script, PARSED like the engine does (never sourced),
# HARNESS_* keys only; a variable already set in the environment wins.
set -u
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
_gs="${BASH_SOURCE[0]:-$0}"
case "$_gs" in */*) _gd=${_gs%/*} ;; *) _gd=. ;; esac
_ge="$_gd/guard.env"
if [ -r "$_ge" ]; then
  while IFS= read -r _gl || [ -n "$_gl" ]; do
    case "$_gl" in ''|'#'*) continue ;; esac
    _gk=${_gl%%=*}; _gv=${_gl#*=}
    [ "$_gk" != "$_gl" ] || continue
    case "$_gk" in HARNESS_LESSONS_JOURNAL|HARNESS_HOME) ;; *) continue ;; esac
    [ -z "${!_gk+x}" ] || continue
    case "$_gv" in
      \'*\') _gv=${_gv#\'}; _gv=${_gv%\'}; _gq="'\\''"; _gv=${_gv//"$_gq"/\'} ;;
      \"*\") _gv=${_gv#\"}; _gv=${_gv%\"} ;;
    esac
    printf -v "$_gk" '%s' "$_gv"
  done < "$_ge" 2>/dev/null
fi
[ "${HARNESS_LESSONS_JOURNAL:-}" = true ] || exit 0
command -v jq >/dev/null 2>&1 || exit 0

input=$(cat 2>/dev/null) || exit 0
_out=$(printf '%s' "$input" | jq -r 'if type == "object" then
  (.session_id // "" | tostring | split("\n") | join("!")), (.stop_hook_active == true) else empty end' 2>/dev/null) || exit 0
unset input
_nl='
'
case "$_out" in *"$_nl"*) ;; *) exit 0 ;; esac
sid=${_out%%"$_nl"*}; active=${_out#*"$_nl"}
[ "$active" = false ] || exit 0
LC_ALL=C
case "$sid" in ''|*[!A-Za-z0-9._-]*) exit 0 ;; esac
[ "${#sid}" -le 64 ] || exit 0
case "$sid" in .|..) exit 0 ;; esac

state="${XDG_STATE_HOME:-${HOME:+$HOME/.local/state}}"
rdir="${HARNESS_RETRO_DIR:-${state:+$state/harness/retro}}"
case "$rdir" in /*) ;; *) exit 0 ;; esac
marker="$rdir/sessions/$sid"
[ ! -e "$marker" ] || exit 0

hb="${HARNESS_HOME:-${HOME:-}/harness-hub}/bin/harness"
[ -f "$hb" ] || exit 0
res=$(hn_timeout 3 bash "$hb" lessons review --session "$sid" --json </dev/null 2>/dev/null)
[ $? -eq 0 ] || exit 0
counts=$(printf '%s' "$res" | jq -r '.counts | "correction \(.correction // 0), dissatisfaction \(.dissatisfaction // 0), guard-deny \(."guard-deny" // 0), guard-ask \(."guard-ask" // 0)"' 2>/dev/null) || counts=""
[ -n "$counts" ] || counts="counts unavailable"
( umask 077; mkdir -p "$rdir/sessions" && : > "$marker" ) </dev/null >/dev/null 2>&1 || exit 0
[ -e "$marker" ] || exit 0
jq -cn --arg m "harness: this session met the review criteria ($counts); run /retro" '{systemMessage: $m}' 2>/dev/null
exit 0
