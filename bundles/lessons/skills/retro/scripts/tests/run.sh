#!/usr/bin/env bash
# shellcheck disable=SC2319  # `[ test ]; ok $? DESC` deliberately reads the status of the test before it
# Golden tests for retro-facts.sh: one JSON object per case (golden/<case>.json) against a stub
# `harness` (stub-hub/bin/harness, found through HARNESS_HOME or PATH) in throw-away git
# repositories. Invariants: the state fixture is byte-identical after every run (the script is
# read-only), the stub is only ever asked `lessons review|journal|list --json`, bash -n parses.
# UPDATE=1 rewrites the goldens (review the diff); KEEP=1 keeps the sandbox.
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd); F="$here/../retro-facts.sh"
tmp=$(mktemp -d); tmp=$(cd "$tmp" && pwd -P)   # real path: git prints /private/var/… on macOS
[ "${KEEP:-0}" = 1 ] && echo "sandbox: $tmp" || trap 'rm -rf "$tmp"' EXIT
fail=0; cases=0
ok() { cases=$((cases + 1)); if [ "$1" = 0 ]; then echo "PASS $2"; else echo "FAIL $2"; fail=1; fi; }

cp -R "$here/fixtures/state" "$tmp/state"
export HOME="$tmp/home" XDG_STATE_HOME="$tmp/state" HARNESS_CONFIG_JSON="$here/fixtures/config.json"
mkdir -p "$HOME"
SYSPATH=$PATH
mkrepo() {  # DIR [FIXTURE]: a git repository on branch topic, no commits
  mkdir -p "$1"; git -C "$1" init -q 2>/dev/null; git -C "$1" symbolic-ref HEAD refs/heads/topic
  [ -z "${2:-}" ] || cp -R "$2/." "$1/"
}
mkrepo "$tmp/repos/shop"; mkrepo "$tmp/repos/owns" "$here/fixtures/repos/owns"; mkdir -p "$tmp/plain"

# golden NAME DIR [args...]  (env prefixes select the stub's answers)
golden() {
  local name=$1 dir=$2; shift 2
  cases=$((cases + 1))
  : > "$tmp/stub.log"
  (cd "$dir" && STUB_LOG="$tmp/stub.log" bash "$F" "$@") > "$tmp/$name.raw" 2> "$tmp/$name.err"
  local rc=$?
  { printf '# exit %s\n' "$rc"; sed -e "s#$tmp#TMP#g" -e "s#$here#HERE#g" "$tmp/$name.raw"; printf '# calls:\n'; sed -e "s#$tmp#TMP#g" "$tmp/stub.log"; } > "$tmp/$name.out"
  if [ "${UPDATE:-0}" = 1 ]; then cp "$tmp/$name.out" "$here/golden/$name.txt"; echo "UPDATED $name"; return; fi
  if diff -u "$here/golden/$name.txt" "$tmp/$name.out" > "$tmp/$name.diff"; then echo "PASS $name"
  else echo "FAIL $name"; cat "$tmp/$name.diff"; fail=1; fi
}
export HARNESS_HOME="$here/stub-hub"
golden manual-due            "$tmp/repos/shop"
STUB_REVIEW=not-due STUB_REVIEW_RC=1 golden work-ticket-not-due "$tmp/repos/shop" --workflow work-ticket --arg PROJ-123
STUB_REVIEW=none STUB_REVIEW_RC=3 golden create-ticket-no-signals "$tmp/repos/shop" --workflow create-ticket --arg PROJ-124
STUB_REVIEW=none STUB_REVIEW_RC=4 golden review-error "$tmp/repos/shop"
golden repo-owns             "$tmp/repos/owns"
golden outside-checkout      "$tmp/plain" --workflow manual
HARNESS_CONFIG_JSON=/nonexistent golden no-config "$tmp/repos/shop"
# the CLI found on PATH when HARNESS_HOME has none
HARNESS_HOME="$tmp/nohub" PATH="$here/stub-hub/bin:$SYSPATH" golden cli-on-path "$tmp/repos/shop"
# no CLI at all: review/journal/lessons degrade to null
mkdir -p "$tmp/sysbin"; for b in bash git jq sed cat mkdir dirname find sort cp diff; do ln -s "$(command -v "$b")" "$tmp/sysbin/$b" 2>/dev/null; done
HARNESS_HOME="$tmp/nohub" PATH="$tmp/sysbin" golden no-cli "$tmp/repos/shop"
golden bad-workflow          "$tmp/repos/shop" --workflow deploy

unset HARNESS_HOME
diff -r "$here/fixtures/state" "$tmp/state" >/dev/null; ok $? "state fixture byte-identical after every run"
bad=$(cd "$tmp" && cat ./*.out | sed -n '/^# calls:/,/^# exit/p' | grep -vE '^# |^lessons (review|journal|list) --json --config /home/u/harness.toml$|^lessons (review|journal|list) --json$' || true)
[ -z "$bad" ]; ok $? "the stub is only asked lessons review|journal|list --json${bad:+ — $bad}"
bash -n "$F"; ok $? "bash -n retro-facts.sh"
for g in "$here"/golden/*.txt; do
  n=$(sed -e '1d' -e '/^# calls:/,$d' "$g" | jq -s 'length' 2>/dev/null)
  case "$(basename "$g")" in bad-workflow.txt) want=0 ;; *) want=1 ;; esac
  [ "$n" = "$want" ]; ok $? "$(basename "$g") holds $want JSON object(s)"
done
[ $fail -eq 0 ] && echo "retro-facts: $cases case(s) passed" || echo "retro-facts: FAILED"
exit $fail
