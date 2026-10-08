#!/usr/bin/env bash
# Golden tests for mq.py, driven entirely by glab-stub.sh / gh-stub.sh / git-stub.sh (stub.py).
# Each scenario (fixtures/<scenario>.json over _gitlab.json / _github.json) runs plan, status,
# check, sync and run --json against a fresh stub state; then the stub-log invariants.
# UPDATE=1 rewrites golden/. KEEP=1 keeps the per-case logs. Exits non-zero on any failure.
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
CLI="$here/../mq.py"
GOLD="$here/golden"
export GLAB="$here/glab-stub.sh" GH="$here/gh-stub.sh" GIT="$here/git-stub.sh"
export HARNESS_CONFIG_JSON=/dev/null   # hermetic: never read a real build/config.json
export HARNESS_MQ_POLL_SECONDS=0 MQ_FAKE_CLOCK=1
export HARNESS_MQ_TIMEOUT_MINUTES=20   # > the 10-minute stuck-rebase window; fewer virtual polls
unset HARNESS_MQ_LABEL HARNESS_MQ_ON_FAILURE HARNESS_MQ_UPDATE_METHOD \
      HARNESS_MQ_REQUIRE_CHECKS HARNESS_MQ_MAX_RETRIES HARNESS_GITLAB_HOSTS_RE HARNESS_GITLAB_HOST \
      WORK_TICKET_AGENT_LABEL_RE WORK_TICKET_LABEL GH_REPO GITLAB_HOST
tmp=$(mktemp -d)
export STUB_LOG="$tmp/all.log"; : > "$STUB_LOG"
fail=0; cases=0
mkdir -p "$GOLD"

norm() {  # the checkout location never reaches a golden
  python3 - "$1" "$here" <<'PY'
import sys
p = sys.argv[1]
t = open(p).read().replace(sys.argv[2], "HERE")
open(p, "w").write(t)
PY
}

record() {  # record <name> <exit> <stdout-file> <stderr-file>
  local name=$1 rc=$2 out=$3 err=$4 g="$tmp/$1.txt"
  { echo "# exit=$rc"; echo "# stderr:"; cat "$err"; echo "# stdout:"; cat "$out"; } > "$g"
  norm "$g"
  cases=$((cases + 1))
  if [ "${UPDATE:-0}" = 1 ]; then cp "$g" "$GOLD/$name.txt"; echo "UPDATED $name"; return; fi
  if [ ! -f "$GOLD/$name.txt" ]; then echo "FAIL $name (no golden — run UPDATE=1)"; fail=1; return; fi
  if diff -u "$GOLD/$name.txt" "$g" > "$tmp/$name.diff"; then echo "PASS $name"
  else echo "FAIL $name"; head -40 "$tmp/$name.diff"; fail=1; fi
}

t() {  # t <name> <scenario> <expected-exit> <args...>   (env assignments go before t via `env`)
  local name=$1 scen=$2 exp=$3; shift 3
  mkdir -p "$tmp/state/$name"
  MQ_SCENARIO=$scen STUB_STATE="$tmp/state/$name" STUB_LOG="$tmp/$name.log" \
    python3 "$CLI" "$@" > "$tmp/$name.out" 2> "$tmp/$name.err"; local rc=$?
  cat "$tmp/$name.log" >> "$STUB_LOG" 2>/dev/null
  [ "$rc" = "$exp" ] || { echo "FAIL $name: exit $rc, expected $exp"; cat "$tmp/$name.err"; fail=1; }
  record "$name" "$rc" "$tmp/$name.out" "$tmp/$name.err"
}

scen() {  # scen <scenario> "<plan status check sync run exits>" <selection...>
  local s=$1 e_plan e_status e_check e_sync e_run
  read -r e_plan e_status e_check e_sync e_run <<<"$2"
  shift 2
  t "$s.plan"   "$s" "$e_plan"   plan   "$@" --json
  t "$s.status" "$s" "$e_status" status "$@" --json
  t "$s.check"  "$s" "$e_check"  check  "$@" --json
  t "$s.sync"   "$s" "$e_sync"   sync   "$@" --json
  t "$s.run"    "$s" "$e_run"    run    "$@" --json
}

# ------------------------------------------------------------------- GitLab scenarios
#    scenario               plan status check sync run   selection
scen gl-fanin-happy         "0 0 0 0 0"   --stack feat-x
scen gl-need-rebase         "0 0 0 0 0"   --stack feat-x
scen gl-target-moved        "0 0 1 0 0"   --stack feat-x
HARNESS_MQ_MAX_RETRIES=1 t gl-target-moved.run-retries1 gl-target-moved 3 run --stack feat-x --json
scen gl-conflict            "1 1 0 1 3"   --stack feat-x
scen gl-pipeline-failed     "1 1 0 1 3"   --label merge-queue
HARNESS_MQ_ON_FAILURE=skip t gl-pipeline-failed.run-skip gl-pipeline-failed 1 run --label merge-queue --json
scen gl-no-pipeline         "0 0 1 0 3"   11
HARNESS_MQ_REQUIRE_CHECKS=false t gl-no-pipeline.run-no-require gl-no-pipeline 0 run 11 --json
scen gl-skipped-pipeline    "1 1 0 0 3"   --stack feat-x
scen gl-retarget-misfire    "0 0 0 0 0"   --stack feat-x
t gl-retarget-misfire.plan-refs gl-retarget-misfire 1 plan 12 --json
scen gl-chain               "1 1 0 1 3"   --stack feat-x
scen gl-draft               "1 1 0 1 3"   --stack feat-x
scen gl-rebase-in-progress  "0 0 0 0 3"   --stack feat-x
scen gl-main-maintainer     "0 1 1 0 3"   --stack feat-x --with-main
t gl-main-maintainer.check-fix gl-main-maintainer 1 check --fix --stack feat-x --json
scen gl-timeout             "0 0 1 0 3"   --stack feat-x
HARNESS_MQ_TIMEOUT_MINUTES=3 t gl-timeout.run-3min gl-timeout 3 run --stack feat-x --json
scen gl-premium-train       "0 0 0 0 0"   --stack feat-x
scen gl-sync-unlabelled     "1 0 0 1 3"   --stack feat-x --with-main
t gl-sync-unlabelled.sync-include-human gl-sync-unlabelled 1 sync --stack feat-x --with-main --include-human --json
t gl-sync-unlabelled.sync-skip-ci gl-sync-unlabelled 1 sync --stack feat-x --skip-ci --json

# ------------------------------------------------------------------- GitHub scenarios
scen gh-private-free        "0 0 0 0 0"   --stack feat-x
scen gh-protected-automerge "0 0 0 0 0"   --label merge-queue
scen gh-merge-queue         "0 0 0 0 0"   --label merge-queue
scen gh-behind              "0 0 0 1 0"   --label merge-queue
HARNESS_MQ_UPDATE_METHOD=merge t gh-behind.sync-merge gh-behind 1 sync --label merge-queue --json
scen gh-conflict            "1 1 0 1 3"   --stack feat-x
scen gh-no-checks           "0 0 1 0 3"   11
HARNESS_MQ_REQUIRE_CHECKS=0 t gh-no-checks.run-no-require gh-no-checks 0 run 11 --json
scen gh-chain-retargeted    "1 1 0 1 3"   --stack feat-x
scen gh-fork                "1 1 0 1 3"   --label merge-queue
scen gh-draft               "1 1 0 1 3"   --stack feat-x
scen gh-review-required     "1 1 0 1 3"   --label merge-queue
scen gh-with-main           "1 1 0 0 3"   --stack feat-x --with-main
t gh-with-main.check-fix gh-with-main 0 check --fix --json
t gl-target-moved.check-fix gl-target-moved 1 check --fix --stack feat-x --json
scen gh-sync-unlabelled     "1 0 0 1 3"   --stack feat-x --with-main
t gh-sync-unlabelled.sync-include-human gh-sync-unlabelled 1 sync --stack feat-x --with-main --include-human --json

# ------------------------------------------------------------------------- assertions
chk() {  # chk <condition-exit> <label>
  cases=$((cases + 1))
  if [ "$1" = 0 ]; then echo "PASS $2"; else echo "FAIL $2"; fail=1; fi
}
ck() { local d=$1; shift; "$@"; chk $? "$d"; }  # ck <label> <test...>
WRITE_RE='^(glab mr (rebase|merge|update)|gh pr (update-branch|merge|edit|ready)|glab api -X|gh api -X|git push)'

# merges are always pinned to the tested head
bad=$(grep '^glab mr merge ' "$STUB_LOG" | grep -v -- ' --sha ' | head -3)
ck "no glab mr merge without --sha" [ -z "$bad" ]
bad=$(grep '^gh pr merge ' "$STUB_LOG" | grep -vE -- ' --auto( |$)| --match-head-commit ' | head -3)
ck "no gh pr merge without --auto or --match-head-commit" [ -z "$bad" ]
ck "the suite exercised both merge kinds" grep -q -- '--auto-merge --sha' "$STUB_LOG"
# read-only verbs
bad=""
for f in "$tmp"/*.plan*.log "$tmp"/*.status.log "$tmp"/*.check*.log; do
  [ -f "$f" ] || continue
  grep -qE "$WRITE_RE" "$f" && bad="$bad $(basename "$f")"
done
ck "plan, status and check issue reads only" [ -z "$bad" ]
# sync: label gate and just-in-time rebase
bad=""
for f in "$tmp"/*.sync*.log; do
  n=$(grep -cE '^(glab mr rebase|gh pr update-branch) ' "$f")
  [ "$n" -le 1 ] || bad="$bad $(basename "$f")"
done
ck "sync rebases at most one MR/PR per invocation" [ -z "$bad" ]
bad=$(grep -E "$WRITE_RE" "$tmp"/gl-sync-unlabelled.sync.log "$tmp"/gh-sync-unlabelled.sync.log \
        "$tmp"/gl-sync-unlabelled.sync-skip-ci.log | grep -E ' 1[02]( |$)')
ck "sync never writes to an unlabelled MR/PR" [ -z "$bad" ]
ck "sync rebased the labelled queue head" grep -q '^glab mr rebase 11$' "$tmp/gl-sync-unlabelled.sync.log"
ck "sync --skip-ci passes it to glab mr rebase" grep -q '^glab mr rebase 11 --skip-ci$' "$tmp/gl-sync-unlabelled.sync-skip-ci.log"
ck "sync prints the label command for an unlabelled MR" grep -q 'glab mr update 12 --label agent-worked' "$tmp/gl-sync-unlabelled.sync.out"
ck "sync prints the label command for an unlabelled PR" grep -q 'gh pr edit 12 -R o/r --add-label agent-worked' "$tmp/gh-sync-unlabelled.sync.out"
ck "sync prints the worktree refresh after a server-side rebase" grep -q 'git -C /home/u/dev/r_feat-x-sub-01-api pull --rebase origin feat-x-sub-01-api' "$tmp/gl-sync-unlabelled.sync.out"
ck "sync fixes a retarget misfire in stack mode" grep -q '^glab mr update 12 --target-branch feat-x$' "$tmp/gl-retarget-misfire.sync.log"
ck "sync marks the main PR ready once every part merged" grep -q '^gh pr ready 10 -R o/r$' "$tmp/gh-with-main.sync.log"
! grep -qE '^(gh pr ready|glab mr update [0-9]+ --ready)' "$tmp"/*.run*.log; chk $? "run never marks a draft ready"
# GitHub calls always name the repository
bad=$(grep '^gh pr ' "$STUB_LOG" | grep -v -- ' -R o/r' | head -3)
ck "every gh pr call carries -R" [ -z "$bad" ]
bad=$(grep -E '^gh (repo view|api) ' "$STUB_LOG" | grep -vE ' (repos/)?o/r( |/|$)' | head -3)
ck "every gh repo/api call names the repository" [ -z "$bad" ]
! grep -qE -- '--force|push --force|reset --hard' "$STUB_LOG"; chk $? "mq never force-pushes or resets"
# behaviour spot checks
ck "need_rebase after arming re-arms on the new head" grep -q '^glab mr merge 11 --auto-merge --sha head11-2' "$tmp/gl-need-rebase.run.log"
ck "target moved: max_retries=1 stops the train" grep -q 'target is busy' "$tmp/gl-target-moved.run-retries1.out"
ck "target moved: default retries rebase twice, then merge" [ "$(grep -c '^glab mr rebase 11' "$tmp/gl-target-moved.run.log")" = 2 ]
ck "on_failure=skip skips the failed MR and merges the next" grep -q '"outcome": "skipped"' "$tmp/gl-pipeline-failed.run-skip.out"
ck "on_failure=stop leaves the rest not reached" grep -q '"outcome": "not reached"' "$tmp/gl-pipeline-failed.run.out"
ck "no pipeline + require_checks stops" grep -q 'mq.require_checks is on' "$tmp/gl-no-pipeline.run.out"
ck "chain stops with rebase --onto after the blocker merges" grep -q 'git rebase --onto origin/feat-x head11-1 feat-x-sub-02-ui' "$tmp/gl-chain.run.out"
ck "a chain blocker keeps its branch" grep -q '^glab mr merge 11 --auto-merge=false --sha head11-1 --yes --squash$' "$tmp/gl-chain.run.log"
ck "403 on the main MR asks for a Maintainer" grep -q 'needs Maintainer on protected main' "$tmp/gl-main-maintainer.run.out"
ck "timeout prints the resume command" grep -q 're-run `mq run --stack feat-x`' "$tmp/gl-timeout.run-3min.out"
ck "premium train banner" grep -q 'native merge train available' "$tmp/gl-premium-train.plan.out"
ck "GitHub merge queue enqueues without a strategy" grep -q '^gh pr merge 21 -R o/r --auto$' "$tmp/gh-merge-queue.run.log"
ck "GitHub dequeued PR is re-enqueued" [ "$(grep -c '^gh pr merge 22 ' "$tmp/gh-merge-queue.run.log")" = 2 ]
ck "GitHub 422 already up to date is not a failure" grep -q '"outcome": "merged"' "$tmp/gh-behind.run.out"
ck "update_method=merge drops --rebase" grep -q '^gh pr update-branch 21 -R o/r$' "$tmp/gh-behind.sync-merge.log"
ck "GitHub required checks are filtered with --required" grep -q '^gh pr checks 21 -R o/r --json bucket,state,name --required' "$tmp/gh-protected-automerge.run.log"
ck "GitHub pre-squash commits stop with rebase --onto" grep -q 'git rebase --onto origin/feat-x head11-1 feat-x-sub-02-ui' "$tmp/gh-chain-retargeted.run.out"
ck "check --fix prints the settings command" grep -q 'glab api -X PUT projects/:id -f merge_method=rebase_merge' "$tmp/gl-target-moved.check-fix.out"

# ------------------------------------------------------------ harness parameters
mkdir -p "$tmp/state/p1" "$tmp/state/p2" "$tmp/state/p3" "$tmp/state/p4" "$tmp/state/p5"
printf '{"mq":{"label":"from-config","max_retries":7}}' > "$tmp/cfg.json"
MQ_SCENARIO=gl-fanin-happy STUB_STATE="$tmp/state/p1" HARNESS_CONFIG_JSON="$tmp/cfg.json" \
  python3 "$CLI" plan --json > "$tmp/p-cfg.out" 2>/dev/null
grep -q '"label": "from-config"' "$tmp/p-cfg.out"; chk $? "mq.label from the harness config selects the label"
MQ_SCENARIO=gl-fanin-happy STUB_STATE="$tmp/state/p2" HARNESS_CONFIG_JSON="$tmp/cfg.json" HARNESS_MQ_LABEL=from-env \
  python3 "$CLI" plan --json > "$tmp/p-env.out" 2>/dev/null
grep -q '"label": "from-env"' "$tmp/p-env.out"; chk $? "HARNESS_MQ_LABEL in the environment wins over the config"
MQ_SCENARIO=gl-fanin-happy STUB_STATE="$tmp/state/p3" HARNESS_MQ_ON_FAILURE=sometimes \
  python3 "$CLI" plan --json > /dev/null 2> "$tmp/p-bad.err"; rc=$?
[ "$rc" = 1 ] && grep -q 'use one of: stop, skip' "$tmp/p-bad.err"; chk $? "an invalid mq.on_failure names the choices"
MQ_SCENARIO=gl-fanin-happy STUB_STATE="$tmp/state/p4" HARNESS_GITLAB_HOSTS_RE='^nomatch$' \
  python3 "$CLI" plan --stack feat-x --json > "$tmp/p-host.out" 2>/dev/null
grep -q '"provider": "gitlab"' "$tmp/p-host.out"; chk $? "a gitlab.* host is GitLab without a hosts regex match"
MQ_SCENARIO=gh-private-free STUB_STATE="$tmp/state/p5" \
  python3 "$CLI" plan --stack feat-x --text > "$tmp/p-text.out" 2>/dev/null
grep -q '^mq plan — github o/r — stack feat-x' "$tmp/p-text.out"; chk $? "--text prints the table"

# usage / unknown verb
python3 "$CLI" > "$tmp/usage.out" 2>&1; rc=$?
[ "$rc" = 1 ] && grep -q "Deliberately NOT implemented" "$tmp/usage.out"; chk $? "bare mq prints usage, exit 1"
python3 "$CLI" --help > "$tmp/help.out" 2>&1; rc=$?
[ "$rc" = 0 ] && grep -q "Exit codes" "$tmp/help.out"; chk $? "mq --help exits 0"
python3 "$CLI" bogus > "$tmp/bogus.out" 2>&1; rc=$?
[ "$rc" = 1 ] && grep -q "Unknown verb" "$tmp/bogus.out"; chk $? "unknown verb exits 1"
python3 "$CLI" sync -h > "$tmp/h.out" 2>&1; rc=$?
[ "$rc" = 0 ] && grep -q -- "--include-human" "$tmp/h.out"; chk $? "mq sync -h works"
MQ_SCENARIO=gl-fanin-happy python3 "$CLI" plan 12 --stack feat-x > /dev/null 2> "$tmp/both.err"; rc=$?
[ "$rc" = 1 ] && grep -q 'not several' "$tmp/both.err"; chk $? "refs and --stack together exit 1"

if [ "${KEEP:-0}" = 1 ]; then echo "artifacts in $tmp"; else rm -rf "$tmp"; fi
if [ $fail -eq 0 ]; then echo "all mq tests passed ($cases cases)"; else echo "mq tests FAILED"; fi
exit $fail
