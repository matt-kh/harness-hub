#!/usr/bin/env bash
# Doctor checks of the lessons bundle (offline, read-only). Usage: doctor.sh CHECK
#   index-fresh        INDEX.md is not older than the newest lesson record (fix: harness lessons index)
#   stale-candidates   no candidate lesson is stale (fix: harness lessons list --stale, then
#                      harness lessons note|retire, or harness lessons index --prune)
#   review-keys        lessons.correction_re and lessons.dissatisfaction_re compile under grep -E
# Config: HARNESS_CONFIG_JSON (the doctor sets it to this config's build/config.json). The
# lessons directory is lessons.dir, else ${XDG_STATE_HOME:-~/.local/state}/harness/lessons.
# The first output line is the doctor's detail. Exit 0 ok (or nothing to check), 1 a problem,
# 2 usage. bash 3.2, jq, grep -E, find.
set -uo pipefail
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
lessons_dir() {
  local d; d=$(hcfg lessons.dir "")
  case "$d" in \~) d=${HOME:-} ;; \~/*) d="${HOME:-}/${d#\~/}" ;; esac
  [ -n "$d" ] || { local s="${XDG_STATE_HOME:-${HOME:+$HOME/.local/state}}"; d="${s:+$s/harness/lessons}"; }
  printf '%s\n' "$d"
}
harness_bin() {
  local h="${HARNESS_HOME:-${HOME:-}/harness-hub}/bin/harness"   # the doctor sets HARNESS_HOME
  [ -f "$h" ] || return 1
  printf '%s\n' "$h"
}

case "${1:-}" in
  index-fresh)
    d=$(lessons_dir)
    if [ -z "$d" ] || [ ! -d "$d" ]; then echo "no lessons library yet (${d:-no state directory})"; exit 0; fi
    n=$(find "$d" -maxdepth 1 -type f -name '*-[0-9][0-9][0-9].md' 2>/dev/null | wc -l | tr -d ' ')
    if [ "$n" = 0 ]; then echo "no lesson records in $d"; exit 0; fi
    if [ ! -f "$d/INDEX.md" ]; then echo "$n lesson record(s) but no INDEX.md; run: harness lessons index"; exit 1; fi
    newer=$(find "$d" -maxdepth 1 -type f -name '*-[0-9][0-9][0-9].md' -newer "$d/INDEX.md" 2>/dev/null | wc -l | tr -d ' ')
    if [ "$newer" != 0 ]; then echo "INDEX.md is older than $newer lesson record(s); run: harness lessons index"; exit 1; fi
    echo "INDEX.md is current ($n lesson record(s))"; exit 0 ;;
  stale-candidates)
    d=$(lessons_dir)
    if [ -z "$d" ] || [ ! -d "$d" ]; then echo "no lessons library yet (${d:-no state directory})"; exit 0; fi
    hb=$(harness_bin) || { echo "harness CLI not found; run harness apply"; exit 1; }
    cfg=$(hcfg _harness.config "")
    if ! out=$(bash "$hb" lessons list --stale --json ${cfg:+--config "$cfg"} 2>/dev/null); then
      echo "harness lessons list --stale failed; run it by hand to see why"; exit 1
    fi
    n=$(printf '%s' "$out" | jq -r '[.[]? | select(.status == "candidate")] | length' 2>/dev/null) || n=""
    case "$n" in ''|*[!0-9]*) echo "harness lessons list --stale --json printed no list"; exit 1 ;; esac
    if [ "$n" != 0 ]; then
      echo "$n stale candidate lesson(s); run: harness lessons list --stale (then note, retire, or index --prune)"; exit 1
    fi
    echo "no stale candidate lessons"; exit 0 ;;
  review-keys)
    bad=""
    for k in lessons.correction_re lessons.dissatisfaction_re; do
      re=$(hcfg "$k" "")
      [ -n "$re" ] || continue
      printf '' | grep -Eq -- "$re" 2>/dev/null
      [ $? -ne 2 ] || bad="$bad $k"
    done
    if [ -n "$bad" ]; then echo "does not compile under grep -E:$bad; fix the value in harness.toml [lessons], then harness apply"; exit 1; fi
    echo "lessons.correction_re and lessons.dissatisfaction_re compile under grep -E"; exit 0 ;;
  *) echo "usage: doctor.sh index-fresh|stale-candidates|review-keys" >&2; exit 2 ;;
esac
