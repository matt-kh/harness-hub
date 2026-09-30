# shellcheck shell=bash
# Shared helpers for guard test rows (bundles/*/guard.d/tests.sh). Sourced by run.sh.
#
#   t  EXPECTED 'cmd'            decision for cmd run in the default cwd ($T_CWD, a main checkout)
#   tc EXPECTED CWD 'cmd'        same, with an explicit cwd
#   tr 'reason-regex' 'cmd'      the hook's reason must match (decision must not be pass)
#   g  EXPECTED 'cmd'            like t, but in a real temporary directory ($ghd/<repo>): gh
#                                lookups cd into the command's cwd, so gh write gates need one
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
unset GIT_STUB_BRANCH GIT_STUB_TOPLEVEL WORK_TICKET_ALLOW_DEFAULT_PUSH_RE WORK_TICKET_ALLOW_TRANSITION WORK_TICKET_KEY_IN_BRANCH
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
