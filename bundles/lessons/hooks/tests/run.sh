#!/usr/bin/env bash
# shellcheck disable=SC2319  # `[ test ]; ok $? DESC` deliberately reads the status of the test before it
# Tests of the lessons hooks: prompt-signal.sh against prompts.tsv (the contract for the default
# regexes) and edge cases, stop-retro-nudge.sh against a stub `harness` (stub-hub, through
# HARNESS_HOME). Every case runs a copy of the hooks next to a guard.env rendered from
# bundles/core/defaults.toml by the engine's own guard_env(), in a throw-away journal/retro dir.
# Asserted everywhere: the prompt hook prints nothing, no prompt word (> 3 chars) reaches the
# journal, a journal line has seven tab fields; static greps; each hook under one second.
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd); bdir=$(cd "$here/.." && pwd)
hub=$(cd "$bdir/../../.." && pwd)
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
fail=0; cases=0
ok() { cases=$((cases + 1)); if [ "$1" = 0 ]; then echo "PASS $2"; else echo "FAIL $2"; fail=1; fi; }
unset HARNESS_LESSONS_PROMPT_SIGNALS HARNESS_LESSONS_JOURNAL HARNESS_LESSONS_CORRECTION_RE \
  HARNESS_LESSONS_DISSATISFACTION_RE HARNESS_GUARD_ID HARNESS_PROVIDER HARNESS_JOURNAL_DIR HARNESS_RETRO_DIR
export HOME="$tmp/home" XDG_STATE_HOME="$tmp/xdg"; mkdir -p "$HOME"

H="$tmp/hooks"; mkdir -p "$H"
cp "$bdir/prompt-signal.sh" "$bdir/stop-retro-nudge.sh" "$H/"
PYTHONPATH="$hub/lib" python3 - "$hub/bundles/core/defaults.toml" "$H/guard.env" <<'PY' || { echo "FAIL could not write guard.env"; exit 1; }
import sys
from harness import toml_compat
from harness.render import guard_env
d = toml_compat.load_file(sys.argv[1])["lessons"]
env = {"HARNESS_LESSONS_PROMPT_SIGNALS": "true", "HARNESS_LESSONS_JOURNAL": "true",
       "HARNESS_LESSONS_CORRECTION_RE": d["correction_re"], "HARNESS_LESSONS_DISSATISFACTION_RE": d["dissatisfaction_re"],
       "HARNESS_GUARD_ID": "3f9c1a7e02bd", "HARNESS_PROVIDER": "claude", "HARNESS_HOME": "/nonexistent"}
open(sys.argv[2], "wb").write(guard_env(env))
PY
P="$H/prompt-signal.sh"; S="$H/stop-retro-nudge.sh"

# ---------------------------------------------------------------- prompt-signal.sh
# prompt TEXT [SESSION] [CWD]: run the hook in a fresh journal; sets $J (journal dir), $R (retro dir)
n=0
prompt() {
  n=$((n + 1)); J="$tmp/j$n"; R="$tmp/r$n"
  jq -cn --arg p "$1" --arg s "${2:-s1}" --arg c "${3:-$tmp/nowhere}" '{session_id: $s, cwd: $c, prompt: $p, hook_event_name: "UserPromptSubmit"}' \
    | HARNESS_JOURNAL_DIR="$J" HARNESS_RETRO_DIR="$R" bash "$P" > "$tmp/out" 2>"$tmp/err"
  echo $? > "$tmp/rc"
}
kinds() { cat "$J"/*.log 2>/dev/null | awk -F'\t' '{print $4}' | tr '\n' ' ' | sed 's/ $//'; }
no_words() {  # TEXT: no word longer than 3 characters of TEXT appears in the journal
  local w
  for w in $(printf '%s' "$1" | tr -c 'A-Za-z0-9' ' '); do
    [ "${#w}" -gt 3 ] || continue
    if cat "$J"/*.log 2>/dev/null | grep -qiF -- "$w"; then echo "    word leaked: $w"; return 1; fi
  done
  return 0
}
check() {  # EXPECTED TEXT
  local want got
  case "$1" in correction) want=correction ;; dissatisfaction) want=dissatisfaction ;;
    both) want="correction dissatisfaction" ;; none) want="" ;; esac
  got=$(kinds)
  [ "$got" = "$want" ] && [ ! -s "$tmp/out" ] && [ "$(cat "$tmp/rc")" = 0 ] && no_words "$2" \
    && { [ -z "$want" ] || [ -z "$(cat "$J"/*.log | awk -F'\t' 'NF != 7')" ]; }
  ok $? "prompt '${2:0:50}' -> ${1}${got:+ (got $got)}"
}
while IFS= read -r line || [ -n "$line" ]; do
  case "$line" in ''|'#'*) continue ;; esac
  want=${line%%"	"*}; text=${line#*"	"}
  prompt "$text"; check "$want" "$text"
done < "$here/prompts.tsv"
long600="no, wrong $(printf '%590s' '' | tr ' ' x)"
prompt "$long600"; check correction "$long600"
long601="no, wrong $(printf '%591s' '' | tr ' ' x)"
prompt "$long601"; check none "$long601"
prompt ""; check none ""
prompt "$(printf 'here is the log:\nno, wrong path again')"; check correction "here is the log: no wrong path again"

prompt "you ignored the test" s1
line=$(cat "$J"/*.log)
[ "$(printf '%s' "$line" | awk -F'\t' '{print $2, $3, $4, $5, $6, $7}')" = "claude s1 correction - 3f9c1a7e02bd -" ]
ok $? "line fields: provider, session, kind, site -, guard id, repo - outside a checkout"
[ "$(cat "$R/current" 2>/dev/null)" = s1 ]; ok $? "retro/current names the session"
printf '%s' "$line" | awk -F'\t' '{exit !($1 ~ /^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$/)}'; ok $? "ts is UTC ISO-8601"
[ "$(ls "$J")" = "$(printf '%s' "$line" | cut -c1-10).log" ]; ok $? "file is <UTC date>.log"
if [ "$(uname -s)" != Darwin ] || true; then
  perm=$(ls -l "$J"/*.log | cut -c1-10); [ "$perm" = "-rw-------" ]; ok $? "journal file mode 0600 ($perm)"
fi

prompt "you ignored the test" "../x"
[ "$(cut -f3 "$J"/*.log)" = - ] && [ ! -e "$R/current" ]; ok $? "session ../x is recorded as - and no retro/current"
prompt "you ignored the test" "$(printf '%065d' 0 | tr 0 s)"
[ "$(cut -f3 "$J"/*.log)" = - ]; ok $? "a 65-character session id is recorded as -"

mkdir -p "$tmp/shop/.git" "$tmp/shop/src" "$tmp/shop_feature-x"
printf 'gitdir: %s\n' "$tmp/shop/.git/worktrees/shop_feature-x" > "$tmp/shop_feature-x/.git"
prompt "wrong file" s1 "$tmp/shop/src"; [ "$(cut -f7 "$J"/*.log)" = shop ]; ok $? "repo = main checkout name"
prompt "wrong file" s1 "$tmp/shop_feature-x"; [ "$(cut -f7 "$J"/*.log)" = shop ]; ok $? "repo of a linked worktree = main checkout name, never <repo>_<branch>"

# journal off, relative dirs, no jq, malformed input, broken regex
n=$((n + 1)); J="$tmp/j$n"
printf '%s' '{"session_id":"s1","prompt":"you ignored the test"}' | HARNESS_LESSONS_PROMPT_SIGNALS=false HARNESS_JOURNAL_DIR="$J" bash "$P" > "$tmp/out"
[ $? = 0 ] && [ ! -e "$J" ] && [ ! -s "$tmp/out" ]; ok $? "prompt_signals off: no file, no output"
mkdir -p "$tmp/cwd"
(cd "$tmp/cwd" && printf '%s' '{"session_id":"s1","prompt":"you ignored the test"}' | HARNESS_JOURNAL_DIR=rel HARNESS_RETRO_DIR=rel2 bash "$P" > "$tmp/out")
[ -z "$(ls -A "$tmp/cwd")" ] && [ ! -s "$tmp/out" ]; ok $? "relative journal dir: nothing written under the cwd"
(cd "$tmp/cwd" && unset HOME XDG_STATE_HOME && printf '%s' '{"session_id":"s1","prompt":"you ignored the test"}' | bash "$P" > "$tmp/out")
[ -z "$(ls -A "$tmp/cwd")" ] && [ ! -s "$tmp/out" ]; ok $? "no HOME, no XDG_STATE_HOME: nothing written"
n=$((n + 1)); J="$tmp/j$n"
printf '%s' '{"session_id":"s1","prompt":"you ignored the test"}' | PATH=/nonexistent HARNESS_JOURNAL_DIR="$J" "$BASH" "$P" > "$tmp/out"
[ $? = 0 ] && [ ! -e "$J" ] && [ ! -s "$tmp/out" ]; ok $? "jq missing: silent exit 0"
for bad in 'not json' '' '[1,2]' '{"prompt": '; do
  n=$((n + 1)); J="$tmp/j$n"
  printf '%s' "$bad" | HARNESS_JOURNAL_DIR="$J" bash "$P" > "$tmp/out" 2>&1
  [ $? = 0 ] && [ ! -e "$J" ] && [ ! -s "$tmp/out" ]; ok $? "malformed stdin '$bad': silent exit 0"
done
n=$((n + 1)); J="$tmp/j$n"
printf '%s' '{"session_id":"s1","prompt":"you ignored the test"}' | HARNESS_LESSONS_CORRECTION_RE='(' HARNESS_JOURNAL_DIR="$J" bash "$P" > "$tmp/out" 2>&1
[ $? = 0 ] && [ ! -s "$tmp/out" ] && [ -z "$(kinds)" ]; ok $? "a regex that does not compile records nothing and prints nothing"
n=$((n + 1)); J="$tmp/j$n"; mkdir -p "$tmp/ro"; chmod 500 "$tmp/ro"
printf '%s' '{"session_id":"s1","prompt":"you ignored the test"}' | HARNESS_JOURNAL_DIR="$tmp/ro/j" bash "$P" > "$tmp/out" 2>&1
[ $? = 0 ] && [ ! -s "$tmp/out" ]; ok $? "unwritable journal dir: silent exit 0"
chmod 700 "$tmp/ro"

# ---------------------------------------------------------------- stop-retro-nudge.sh
RD="$tmp/retro"; LOG="$tmp/stub.log"
nudge() {  # STDIN-JSON [env...]: run the nudge hook against the stub hub
  local in=$1; shift
  : > "$LOG"
  printf '%s' "$in" | env HARNESS_HOME="$here/stub-hub" HARNESS_RETRO_DIR="$RD" STUB_LOG="$LOG" "$@" bash "$S" > "$tmp/nout" 2>"$tmp/nerr"
  echo $? > "$tmp/nrc"
}
silent() { [ "$(cat "$tmp/nrc")" = 0 ] && [ ! -s "$tmp/nout" ]; }
called() { [ -s "$LOG" ]; }
IN='{"session_id":"s1","transcript_path":"/nonexistent/transcript.jsonl","stop_hook_active":false,"hook_event_name":"Stop"}'

nudge "$IN" HARNESS_LESSONS_JOURNAL=false
silent && ! called && [ ! -e "$RD/sessions/s1" ]; ok $? "nudge: journal off -> silent, review not run"
for rc in 1 3 4 7; do
  nudge "$IN" STUB_RC=$rc
  silent && called && [ ! -e "$RD/sessions/s1" ]; ok $? "nudge: review rc $rc -> silent, no marker"
done
nudge "$IN"
[ "$(cat "$tmp/nrc")" = 0 ] && [ "$(jq -s 'length' < "$tmp/nout")" = 1 ] \
  && [ "$(jq -r 'keys | join(",")' < "$tmp/nout")" = systemMessage ] \
  && [ "$(jq -r .systemMessage < "$tmp/nout")" = "harness: this session met the review criteria (correction 2, dissatisfaction 0, guard-deny 1, guard-ask 0); run /retro" ] \
  && [ -f "$RD/sessions/s1" ] && [ "$(cat "$LOG")" = "lessons review --session s1 --json" ]
ok $? "nudge: due -> exactly one {systemMessage} object, marker written"
grep -q '"decision"' "$tmp/nout"; [ $? = 1 ]; ok $? "nudge: no decision key is ever emitted"
nudge "$IN"
silent && ! called; ok $? "nudge: second call in the same session -> silent, review not run"
nudge '{"session_id":"s2","stop_hook_active":true}'
silent && ! called; ok $? "nudge: stop_hook_active -> silent"
for bad in 'not json' '' '[]' '"s1"' '{"session_id":'; do
  nudge "$bad"; silent && ! called; ok $? "nudge: malformed stdin '$bad' -> silent"
done
for sid in '../x' '..' 'a/b' ''; do
  nudge "$(jq -cn --arg s "$sid" '{session_id: $s, stop_hook_active: false}')"
  silent && ! called; ok $? "nudge: session '$sid' -> silent, no marker"
done
others=""; for m in "$RD"/sessions/*; do [ "${m##*/}" = s1 ] || others="$others ${m##*/}"; done
[ -z "$others" ] && [ ! -e "$tmp/x" ]; ok $? "nudge: only the s1 marker exists${others:+ —$others}"
nudge '{"session_id":"s3","stop_hook_active":false}' HARNESS_RETRO_DIR=relative
silent && ! called; ok $? "nudge: relative retro dir -> silent"
nudge '{"session_id":"s4","stop_hook_active":false}' HARNESS_HOME="$tmp/nohub"
silent && ! called; ok $? "nudge: no harness CLI -> silent"
printf '%s' '{"session_id":"s5","stop_hook_active":false}' | PATH=/nonexistent HARNESS_HOME="$here/stub-hub" HARNESS_RETRO_DIR="$RD" "$BASH" "$S" > "$tmp/nout"
[ $? = 0 ] && [ ! -s "$tmp/nout" ]; ok $? "nudge: jq missing -> silent"
chmod 500 "$RD/sessions"
nudge '{"session_id":"s6","stop_hook_active":false}'
silent; ok $? "nudge: marker cannot be written -> silent (never repeats per turn)"
chmod 700 "$RD/sessions"

# ---------------------------------------------------------------- static checks and timing
for f in "$bdir/prompt-signal.sh" "$bdir/stop-retro-nudge.sh"; do
  bash -n "$f"; ok $? "bash -n $(basename "$f")"
  [ "$(grep -c transcript_path "$f")" = 0 ]; ok $? "$(basename "$f") never names transcript_path"
done
stray=$(grep -nE '(^|[;&|({ ])(echo|printf|cat)( |$)' "$bdir/prompt-signal.sh" | grep -v '^[0-9]*:#' \
  | grep -vE 'printf -v|>|\|' || true)
[ -z "$stray" ]; ok $? "prompt-signal.sh has no echo/printf/cat to stdout${stray:+ — $stray}"
timed() {  # LABEL STDIN SCRIPT [env...]: the hook finishes in under one second
  local label=$1 in=$2 script=$3; shift 3
  local t0 t1
  t0=$(python3 -c 'import time; print(time.time())')
  printf '%s' "$in" | env "$@" bash "$script" >/dev/null 2>&1
  t1=$(python3 -c 'import time; print(time.time())')
  python3 -c 'import sys; sys.exit(0 if float(sys.argv[2]) - float(sys.argv[1]) < 1.0 else 1)' "$t0" "$t1"
  ok $? "$label runs in under one second"
}
timed "prompt-signal.sh" '{"session_id":"s1","prompt":"no, you ignored the test, why did you"}' "$P" HARNESS_JOURNAL_DIR="$tmp/jt" HARNESS_RETRO_DIR="$tmp/rt"
timed "stop-retro-nudge.sh (stub harness)" '{"session_id":"t1","stop_hook_active":false}' "$S" HARNESS_HOME="$here/stub-hub" HARNESS_RETRO_DIR="$tmp/rt"

[ $fail -eq 0 ] && echo "lessons hooks: $cases case(s) passed" || echo "lessons hooks: FAILED"
exit $fail
