#!/usr/bin/env bash
# Golden tests for render-ticket.py. UPDATE=1 rewrites golden files.
set -uo pipefail
export HARNESS_CONFIG_JSON=/dev/null   # hermetic: never read a real build/config.json
here=$(cd "$(dirname "$0")" && pwd); R="$here/../render-ticket.py"; F="$here/fixtures/facts-PROJ.json"
GF="$here/fixtures/facts-owner-repo.json"
tmp=$(mktemp -d); fail=0
# golden NAME FIXTURE FACTS [extra render args...]
golden() {
  local fx=$1 model=$2 facts=$3; shift 3
  local out="$tmp/$fx"
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
for bad in bad-gh-closing; do
  if python3 "$R" --model "$here/fixtures/$bad.json" --facts "$GF" --out-dir "$tmp/$bad" --check --provider github 2>/dev/null; then echo "FAIL $bad (check should reject)"; fail=1; else echo "PASS $bad rejected"; fi
done
# provenance label must be present in every rendered command
for fx in defect enhancement chore epic swtask; do
  grep -q -- "--field 'labels=\[\"agent-drafted\"" "$tmp/$fx/create.sh" || { echo "FAIL $fx: no agent-drafted label in create.sh"; fail=1; }
done
for fx in gh-defect gh-enhancement; do
  grep -qE -- " -l '?agent-drafted(,|'| |$)" "$tmp/$fx/create.sh" || { echo "FAIL $fx: no -l agent-drafted in create.sh"; fail=1; }
done
# harness config: type rules (jira.issue_types) and field ids (jira.fields); ids are never guessed
C="$here/fixtures/config-rules.json"
ok()  { if "$@" >/dev/null 2>"$tmp/cfg.err"; then echo "PASS ${label}"; else echo "FAIL ${label}"; cat "$tmp/cfg.err"; fail=1; fi; }
nok() { if "$@" >/dev/null 2>"$tmp/cfg.err" || ! grep -qE "$want" "$tmp/cfg.err"; then echo "FAIL ${label}"; cat "$tmp/cfg.err"; fail=1; else echo "PASS ${label}"; fi; }
rt()  { python3 "$R" --model "$here/fixtures/$1.json" --out-dir "$tmp/cfg-$1-$2" --check; }
label="generic rules: CR without type_of_problem renders"                ok rt cr-no-top a
label="generic rules: Bug renders standalone"                          ok rt bug a
label="config rule: CR requires type_of_problem" want="CR requires type_of_problem \(Bug Fix" HARNESS_CONFIG_JSON=$C nok rt cr-no-top b
label="config rule: Bug is not standalone" want="sub-task type"        HARNESS_CONFIG_JSON=$C nok rt bug b
label="no facts, no config: unknown field id fails" want="field id for type_of_problem unknown" nok rt defect c
label="no facts, config ids: renders"                                 HARNESS_CONFIG_JSON=$C ok rt defect d
grep -q "customfield_20103=" "$tmp/cfg-defect-d/create.sh" && grep -q "customfield_20000=" "$tmp/cfg-defect-d/create.sh" \
  && echo "PASS configured field ids reach create.sh" || { echo "FAIL configured field ids reach create.sh"; fail=1; }
rm -rf "$tmp"; [ $fail -eq 0 ] && echo "all golden tests passed"; exit $fail
