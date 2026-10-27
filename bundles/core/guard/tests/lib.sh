# shellcheck shell=bash
# Shared helpers for guard test rows (bundles/*/guard.d/tests.sh). Sourced by run.sh.
#
#   t  EXPECTED 'cmd'            decision for cmd run in the default cwd ($T_CWD, a main checkout)
#   tc EXPECTED CWD 'cmd'        same, with an explicit cwd
#   tr 'reason-regex' 'cmd'      the hook's reason must match (decision must not be pass)
#   g  EXPECTED 'cmd'            like t, but in a real temporary directory ($ghd/<repo>): gh
#                                lookups cd into the command's cwd, so gh write gates need one
#   decl LINE...                 write the fixture repository's .harness.toml ($rpd holds .git,
#                                $rpd/sub nests in it; principle 8); `decl` alone removes it
#   r  EXPECTED 'cmd'            like t, with cwd = the fixture repository $rpd
#   tn EXPECTED 'stderr-regex' CWD 'cmd'   decision AND the hook's stderr note must match (rows
#                                whose decision alone would pass vacuously, e.g. ignored overrides)
#   tj on|off|unset EXPECTED 'cmd'   decision like t, with HARNESS_LESSONS_JOURNAL=true|false|unset
#                                and a fresh HARNESS_JOURNAL_DIR / HARNESS_RETRO_DIR; then: on + ask
#                                or deny -> exactly one 7-field line (kind guard-ask|guard-deny,
#                                field 6 = the guard id in use, field 3 = the sanitised session) and
#                                retro/current = that session (absent for -); otherwise no journal
#                                file and no retro/current. Always: no word of the command longer
#                                than 3 characters appears in any file written. Knobs (prefix env):
#                                TJ_SESSION (default s1; empty = no session_id in the input),
#                                TJ_CWD (default $T_CWD), TJ_SITE (ERE field 5 must match),
#                                TJ_JOURNAL_DIR (journal dir to use instead; then nothing may be
#                                written there nor to retro/current)
# EXPECTED is allow | ask | deny | pass (pass = no output, the provider decides).
# Prefix env assignments work as usual: `WORK_TICKET_ALLOW_TRANSITION=1 t ask '…'`.
# NOTE: `tr` shadows the tr(1) command inside the test shell; the guard runs in its own bash.
#
# Inputs: GUARD_BASH (the concatenated guard under test; run.sh builds it) and the stubs in
# ./stubs, wired through the guard's client-path env vars. Counters: pass / fail.

GUARD_TESTS_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
STUBS="$GUARD_TESTS_DIR/stubs"
H="${GUARD_BASH:?GUARD_BASH must point at the guard under test}"
export WORK_TICKET_JIRA_PY="$STUBS/jira-stub.py"
export WORK_TICKET_GLAB="$STUBS/glab-stub.sh"
export WORK_TICKET_GDOC_PY="$STUBS/gdoc-stub.py"
export GUARD_KUBECTL="$STUBS/kubectl-stub.sh"
export GUARD_GIT="$STUBS/git-stub.sh"   # current branch via GIT_STUB_BRANCH (unset = not a repo)
export WORK_TICKET_GH="$STUBS/gh-stub.sh"
unset GIT_STUB_BRANCH GIT_STUB_TOPLEVEL WORK_TICKET_ALLOW_DEFAULT_PUSH_RE WORK_TICKET_ALLOW_TRANSITION WORK_TICKET_KEY_IN_BRANCH \
      WORK_TICKET_LABELED_DECISION WORK_TICKET_BASE_BRANCH_RE HARNESS_CRED_EXTRA_RE \
      HARNESS_LESSONS_JOURNAL HARNESS_GUARD_ID HARNESS_PROVIDER TJ_SESSION TJ_CWD TJ_SITE TJ_JOURNAL_DIR
# every row's journal (should one ever be written by mistake) lands in a sink, never in ~/.local/state
tjd=$(mktemp -d)
export HARNESS_JOURNAL_DIR="$tjd/sink/journal" HARNESS_RETRO_DIR="$tjd/sink/retro" XDG_STATE_HOME="$tjd/sink/state"
T_REPO="${T_REPO:-shop}"                     # repo directory name used by the rows
T_CWD="/home/u/dev/$T_REPO"                   # default cwd = a main checkout (need not exist)
pass=${pass:-0}; fail=${fail:-0}

tc() {  # expected cwd command
  local exp="$1" cwd="$2" cmd="$3" out d
  out=$(jq -cn --arg cwd "$cwd" --arg c "$cmd" '{cwd:$cwd,tool_input:{command:$c}}' | bash "$H")
  d=$(jq -r '.hookSpecificOutput.permissionDecision // "pass"' <<<"${out:-{\}}")
  if [ "$d" = "$exp" ]; then pass=$((pass+1)); printf 'PASS %-5s | [%s] %s\n' "$d" "$(basename "$cwd")" "$cmd"
  else fail=$((fail+1)); printf 'FAIL want=%s got=%s | [%s] %s\n   %s\n' "$exp" "$d" "$(basename "$cwd")" "$cmd" "$(jq -r '.hookSpecificOutput.permissionDecisionReason // ""' <<<"${out:-{\}}")"; fi
}
t() { tc "$1" "$T_CWD" "$2"; }
tr() {  # reason-regex command  -- asserts the hook reason matches (decision must not be pass)
  local re="$1" cmd="$2" out d r
  out=$(jq -cn --arg cwd "$T_CWD" --arg c "$cmd" '{cwd:$cwd,tool_input:{command:$c}}' | bash "$H")
  d=$(jq -r '.hookSpecificOutput.permissionDecision // "pass"' <<<"${out:-{\}}")
  r=$(jq -r '.hookSpecificOutput.permissionDecisionReason // ""' <<<"${out:-{\}}")
  if printf '%s' "$r" | grep -qE "$re"; then pass=$((pass+1)); printf 'PASS %-5s | reason~/%s/ | %s\n' "$d" "$re" "$cmd"
  else fail=$((fail+1)); printf 'FAIL reason !~ /%s/ | %s\n   got=%s %s\n' "$re" "$cmd" "$d" "$r"; fi
}
# real directories for rows whose lookups cd into the cwd (gh); removed by run.sh on exit
ghd=$(mktemp -d); mkdir -p "$ghd/$T_REPO" "$ghd/${T_REPO}_feat-x-sub-01-schema"
g() { tc "$1" "$ghd/$T_REPO" "$2"; }
# a real fixture repository for .harness.toml rows (principle 8); removed by run.sh on exit
rpd=$(mktemp -d); mkdir -p "$rpd/.git" "$rpd/sub"
decl() { if [ $# -eq 0 ]; then rm -f "$rpd/.harness.toml"; else printf '%s\n' "$@" > "$rpd/.harness.toml"; fi; }
r() { tc "$1" "$rpd" "$2"; }
tn() {  # expected stderr-regex cwd command
  local exp="$1" re="$2" cwd="$3" cmd="$4" out err d ef
  ef=$(mktemp)
  out=$(jq -cn --arg cwd "$cwd" --arg c "$cmd" '{cwd:$cwd,tool_input:{command:$c}}' | bash "$H" 2>"$ef")
  err=$(cat "$ef"); rm -f "$ef"
  d=$(jq -r '.hookSpecificOutput.permissionDecision // "pass"' <<<"${out:-{\}}")
  if [ "$d" = "$exp" ] && printf '%s' "$err" | grep -qE -e "$re"; then
    pass=$((pass+1)); printf 'PASS %-5s | stderr~/%s/ | [%s] %s\n' "$d" "$re" "$(basename "$cwd")" "$cmd"
  else
    fail=$((fail+1)); printf 'FAIL want=%s got=%s, stderr !~ /%s/ | [%s] %s\n   stderr=%s\n' "$exp" "$d" "$re" "$(basename "$cwd")" "$cmd" "$err"
  fi
}

# journal rows (opt-in guard journal): see the header
# the id the renderer would write for this guard (sha256 of guard-bash.sh, 12 hex chars)
TJ_GUARD_ID=$(python3 -c 'import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest()[:12])' "$H")
tj() {  # on|off|unset expected command
  local mode="$1" exp="$2" cmd="$3" cwd="${TJ_CWD:-$T_CWD}" sid="${TJ_SESSION-s1}" want_sid w why="" in out d
  local run="$tjd/run.$((pass+fail))" jdir rdir files n line f
  rm -rf "$run"; mkdir -p "$run"
  jdir="${TJ_JOURNAL_DIR:-$run/journal}"; rdir="$run/retro"
  want_sid=$sid
  case "$want_sid" in ''|*[!A-Za-z0-9._-]*) want_sid=- ;; esac
  [ "${#want_sid}" -le 64 ] || want_sid=-
  if [ -n "$sid" ]; then in=$(jq -cn --arg s "$sid" --arg cwd "$cwd" --arg c "$cmd" '{session_id:$s,cwd:$cwd,tool_input:{command:$c}}')
  else in=$(jq -cn --arg cwd "$cwd" --arg c "$cmd" '{cwd:$cwd,tool_input:{command:$c}}'); fi
  out=$(
    case "$mode" in on) export HARNESS_LESSONS_JOURNAL=true ;; off) export HARNESS_LESSONS_JOURNAL=false ;; *) unset HARNESS_LESSONS_JOURNAL ;; esac
    export HARNESS_JOURNAL_DIR="$jdir" HARNESS_RETRO_DIR="$rdir" HARNESS_GUARD_ID="$TJ_GUARD_ID" HARNESS_PROVIDER=claude
    printf '%s' "$in" | bash "$H" 2>/dev/null
  )
  d=$(jq -r '.hookSpecificOutput.permissionDecision // "pass"' <<<"${out:-{\}}")
  [ "$d" = "$exp" ] || why="decision $d"
  files=$(find "$run" "$jdir" -type f 2>/dev/null | sort -u)
  if [ "$mode" = on ] && [ -z "${TJ_JOURNAL_DIR:-}" ] && { [ "$exp" = ask ] || [ "$exp" = deny ]; }; then
    n=$(find "$jdir" -type f -name '*.log' 2>/dev/null | wc -l | command tr -d ' ')
    if [ "$n" != 1 ]; then why="$why; $n journal files"
    else
      line=$(cat "$jdir"/*.log)
      [ "$(printf '%s\n' "$line" | wc -l | command tr -d ' ')" = 1 ] || why="$why; not exactly one line"
      printf '%s\n' "$line" | awk -F '\t' 'NF != 7 { exit 1 }' || why="$why; not 7 tab fields: $line"
      [ "$(printf '%s' "$line" | cut -f4)" = "guard-$exp" ] || why="$why; kind $(printf '%s' "$line" | cut -f4)"
      [ "$(printf '%s' "$line" | cut -f6)" = "$TJ_GUARD_ID" ] || why="$why; guard id $(printf '%s' "$line" | cut -f6)"
      [ "$(printf '%s' "$line" | cut -f3)" = "$want_sid" ] || why="$why; session $(printf '%s' "$line" | cut -f3)"
      [ -z "${TJ_SITE:-}" ] || printf '%s' "$line" | cut -f5 | grep -qE -e "$TJ_SITE" || why="$why; site $(printf '%s' "$line" | cut -f5) !~ $TJ_SITE"
      if [ "$want_sid" = - ]; then [ ! -e "$rdir/current" ] || why="$why; retro/current written for session -"
      else [ "$(cat "$rdir/current" 2>/dev/null)" = "$want_sid" ] || why="$why; retro/current != $want_sid"; fi
    fi
  else
    [ -z "$files" ] || why="$why; wrote $(printf '%s' "$files" | command tr '\n' ' ')"
    [ -z "${TJ_JOURNAL_DIR:-}" ] || [ ! -e "$TJ_JOURNAL_DIR" ] || why="$why; created $TJ_JOURNAL_DIR"
  fi
  # privacy: no word of the command (split on anything but letters and digits) longer than 3 chars
  for w in $(printf '%s' "$cmd" | command tr -c 'A-Za-z0-9' ' '); do
    [ "${#w}" -gt 3 ] || continue
    while IFS= read -r f; do
      [ -n "$f" ] || continue
      if grep -qF -- "$w" "$f"; then why="$why; command word '$w' in ${f##*/}"; fi
    done <<EOF
$files
EOF
  done
  rm -rf "$run"
  if [ -z "$why" ]; then pass=$((pass+1)); printf 'PASS %-5s | journal %s [%s] %s\n' "$d" "$mode" "$want_sid" "$cmd"
  else fail=$((fail+1)); printf 'FAIL want=%s | journal %s [%s] %s\n   %s\n' "$exp" "$mode" "$want_sid" "$cmd" "${why#; }"; fi
}
