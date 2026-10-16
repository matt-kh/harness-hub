#!/usr/bin/env bash
# Golden tests for render-ticket.py (golden/<class>/ directories) and create-facts.sh
# (golden/cf-*.txt: `# exit / # stderr / # stdout / # calls:` against the fixture-routed gh and
# jira stubs of bundles/ticket-workflow/tests/stubs, in throw-away git repositories).
# UPDATE=1 rewrites golden files (review the diff); KEEP=1 keeps the sandbox.
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd); R="$here/../render-ticket.py"; F="$here/fixtures/facts-PROJ.json"
GF="$here/fixtures/facts-owner-repo.json"
# shellcheck source=../../../../tests/stubs/lib.sh
. "$here/../../../../tests/stubs/lib.sh"
tw_init "$here"   # hermetic: HARNESS_CONFIG_JSON=/dev/null, empty HOME, stubbed gh/jira; sets tmp, fail, cases
# golden NAME FIXTURE FACTS [extra render args...]
golden() {
  local fx=$1 model=$2 facts=$3; shift 3
  local out="$tmp/$fx"
  cases=$((cases + 1))
  python3 "$R" --model "$here/fixtures/$model.json" --facts "$facts" --out-dir "$out" --check "$@" >/dev/null || { echo "FAIL render $fx"; fail=1; return; }
  # normalise the tmp path in create.sh so goldens are location-independent
  python3 -c 'import sys
o = sys.argv[1]
for p in sys.argv[2:]:
    t = open(p).read(); open(p, "w").write(t.replace(o, "OUT"))' "$out" "$out/create.sh" "$out/preview.md"   # BSD/GNU-neutral in-place edit
  if [ "${UPDATE:-0}" = 1 ]; then mkdir -p "$here/golden/$fx"; cp "$out"/* "$here/golden/$fx/"; echo "UPDATED $fx"; return; fi
  if diff -ru "$here/golden/$fx" "$out" >"$tmp/$fx.diff"; then echo "PASS $fx"; else echo "FAIL $fx"; cat "$tmp/$fx.diff"; fail=1; fi
}
for fx in defect enhancement chore epic swtask; do golden "$fx" "$fx" "$F"; done
golden gh-defect gh-defect "$GF" --provider github
golden gh-enhancement gh-enhancement "$GF" --provider github
for bad in bad-summary bad-component; do
  if python3 "$R" --model "$here/fixtures/$bad.json" --facts "$F" --out-dir "$tmp/$bad" --check 2>/dev/null; then echo "FAIL $bad (check should reject)"; fail=1; else echo "PASS $bad rejected"; fi
done
bad='bad-gh-closing'
if python3 "$R" --model "$here/fixtures/$bad.json" --facts "$GF" --out-dir "$tmp/$bad" --check --provider github 2>/dev/null; then echo "FAIL $bad (check should reject)"; fail=1; else echo "PASS $bad rejected"; fi
# provenance label must be present in every rendered command
for fx in defect enhancement chore epic swtask; do
  grep -q -- "--field 'labels=\[\"agent-drafted\"" "$tmp/$fx/create.sh" || { echo "FAIL $fx: no agent-drafted label in create.sh"; fail=1; }
done
for fx in gh-defect gh-enhancement; do
  grep -qE -- " -l '?agent-drafted(,|'| |$)" "$tmp/$fx/create.sh" || { echo "FAIL $fx: no -l agent-drafted in create.sh"; fail=1; }
done
# harness config: type rules (jira.issue_types) and field ids (jira.fields); ids are never guessed
C="$here/fixtures/config-rules.json"
# ok LABEL CMD...: CMD must succeed; nok LABEL WANT CMD...: CMD must fail with stderr matching WANT
ok()  { local label=$1; shift; cases=$((cases + 1)); if "$@" >/dev/null 2>"$tmp/cfg.err"; then echo "PASS ${label}"; else echo "FAIL ${label}"; cat "$tmp/cfg.err"; fail=1; fi; }
nok() { local label=$1 want=$2; shift 2; cases=$((cases + 1)); if "$@" >/dev/null 2>"$tmp/cfg.err" || ! grep -qE "$want" "$tmp/cfg.err"; then echo "FAIL ${label}"; cat "$tmp/cfg.err"; fail=1; else echo "PASS ${label}"; fi; }
rt()  { python3 "$R" --model "$here/fixtures/$1.json" --out-dir "$tmp/cfg-$1-$2" --check; }
ok "generic rules: CR without type_of_problem renders" rt cr-no-top a
ok "generic rules: Bug renders standalone" rt bug a
HARNESS_CONFIG_JSON=$C nok "config rule: CR requires type_of_problem" "CR requires type_of_problem \(Bug Fix" rt cr-no-top b
HARNESS_CONFIG_JSON=$C nok "config rule: Bug is not standalone" "sub-task type" rt bug b
nok "no facts, no config: unknown field id fails" "field id for type_of_problem unknown" rt defect c
HARNESS_CONFIG_JSON=$C ok "no facts, config ids: renders" rt defect d
grep -q "customfield_20103=" "$tmp/cfg-defect-d/create.sh" && grep -q "customfield_20000=" "$tmp/cfg-defect-d/create.sh" \
  && echo "PASS configured field ids reach create.sh" || { echo "FAIL configured field ids reach create.sh"; fail=1; }

# ------------------------------------------------------------------ create-facts.sh (read-only facts)
CF="$here/../create-facts.sh"; RP="$tmp/repos"
tw_repo "$RP/clone" "git@github.com:owner/repo.git"         "$FIXT/repos/gh-templates"
tw_repo "$RP/ghe"   "git@github.example.com:owner/repo.git" "$FIXT/repos/gh-templates"
tw_repo "$RP/owns"  "https://github.com/owner/repo.git"     "$FIXT/repos/owns"
tw_repo "$RP/trk"   "git@gitlab.example.com:group/repo.git" "$FIXT/repos/tracker-jira"
mkdir -p "$RP/plain"
t cf-jira-full            0 -                   "$RP/plain" "$CF" PROJ
HARNESS_CONFIG_JSON="$FIXT/config-pd-global.json" \
  t cf-jira-pd-config     0 -                   "$RP/plain" "$CF" PROJ
HARNESS_CONFIG_JSON="$FIXT/config-rules.json" \
  t cf-jira-pd-object     0 -                   "$RP/plain" "$CF" PROJ
HARNESS_CONFIG_JSON="$FIXT/config-rules.json" HARNESS_JIRA_FIELDS_PROBLEM_DESCRIPTION_ID=customfield_20001 \
  t cf-jira-pd-env-wins   0 -                   "$RP/plain" "$CF" PROJ
t cf-jira-unreachable     0 cf-jira-unreachable "$RP/plain" "$CF" PROJ
t cf-gh-full              0 -                   "$RP/clone" "$CF" owner/repo
t cf-gh-outside-clone     0 -                   "$RP/plain" "$CF" owner/repo
t cf-gh-unauth            0 cf-gh-unauth        "$RP/clone" "$CF" owner/repo
PATH="$SYSBIN" \
  t cf-gh-not-installed   0 -                   "$RP/clone" "$CF" owner/repo
HARNESS_GITHUB_HOST=github.example.com \
  t cf-gh-host            0 cf-gh-host          "$RP/ghe"   "$CF" owner/repo
HARNESS_CONFIG_JSON="$FIXT/config-ghe.json" \
  t cf-gh-ghe-templates   0 cf-gh-host          "$RP/ghe"   "$CF" owner/repo
t cf-repo-owns            0 -                   "$RP/owns"  "$CF" PROJ
t cf-tracker-host         0 -                   "$RP/clone" "$CF" --repo
t cf-tracker-declared     0 -                   "$RP/trk"   "$CF" --repo
t cf-tracker-none         0 -                   "$RP/plain" "$CF" --repo
t cf-usage                1 -                   "$RP/plain" "$CF"

A="$tmp/calls.all"
bad=$(grep '^gh ' "$A" | grep -vE '^gh (auth status --hostname [^ ]+|api [^ -][^ ]*( --jq .*)?|repo view [^ -][^ ]*/[^ ]+ --json [^ ]+|label list -R [^ ]+/[^ ]+ .*)$' | head -3)
ck "create-facts: gh calls are reads (auth status, api GET, repo view, label list -R)" [ -z "$bad" ]
bad=$(grep '^gh ' "$A" | grep -E -- ' (-f|-F|--field|--raw-field|--input|-X|--method)( |=|$)' | head -3)
ck "create-facts: no gh write flags" [ -z "$bad" ]
bad=$(grep '^jira ' "$A" | grep -vE '^jira (whoami|api /rest/api/2/[^ ]+)$' | head -3)
ck "create-facts: jira calls are whoami and api GETs" [ -z "$bad" ]
grep -q '"error": "gh not installed' "$tmp/cf-gh-not-installed.out"; chk $? "create-facts: gh missing from PATH is reported, not fatal"
grep -q '"templates": \[\]' "$tmp/cf-gh-outside-clone.out"; chk $? "create-facts: no templates outside a clone of the repository"
for c in cf-gh-full cf-gh-host cf-gh-ghe-templates; do
  grep -q '"\.github/ISSUE_TEMPLATE/bug\.md"' "$tmp/$c.out"; chk $? "create-facts: $c reports the clone's issue templates (remote id = github host/owner/repo)"
done
blk() { sed -n '/^# >>> rf_tracker$/,/^# <<< rf_tracker$/p' "$1"; }
[ -n "$(blk "$CF")" ] && cmp -s <(blk "$CF") <(blk "$here/../../../work-ticket/scripts/lib/repo-facts.sh")
chk $? "create-facts: the rf_tracker block is identical to work-ticket/scripts/lib/repo-facts.sh (copy it over)"

tw_finish create-ticket
