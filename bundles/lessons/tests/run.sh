#!/usr/bin/env bash
# Bundle `lessons` tests: the hook suite (hooks/tests/run.sh), then the doctor script
# (lib/doctor.sh) per check against throw-away lessons directories and configs. The /retro
# facts suite (skills/retro/scripts/tests/run.sh) is discovered and run on its own by
# `harness test lessons`. Exit 1 on any failure.
set -uo pipefail
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
bdir=$(cd "$here/.." && pwd)
tmp=$(mktemp -d); trap 'chmod -R u+w "$tmp" 2>/dev/null; rm -rf "$tmp"' EXIT
fail=0; cases=0
ok() { cases=$((cases + 1)); if [ "$1" = 0 ]; then echo "PASS $2"; else echo "FAIL $2"; fail=1; fi; }

bash "$bdir/hooks/tests/run.sh" > "$tmp/hooks.log" 2>&1; rc=$?
[ $rc = 0 ] || grep '^FAIL' "$tmp/hooks.log" | head -20
ok $rc "hooks: $(tail -1 "$tmp/hooks.log")"

D="$bdir/lib/doctor.sh"
bash -n "$D"; ok $? "bash -n lib/doctor.sh"
export HOME="$tmp/h"; mkdir -p "$HOME"
cfg() { printf '%s\n' "$1" > "$tmp/config.json"; }
# doc CHECK WANT-RC WANT-RE: run the check, compare rc and the first output line
doc() {
  local out rc
  out=$(HARNESS_CONFIG_JSON="$tmp/config.json" HARNESS_HOME="$tmp/stubhub" XDG_STATE_HOME="$tmp/xdg" bash "$D" "$1" 2>&1); rc=$?
  [ "$rc" = "$2" ] && printf '%s\n' "$out" | head -1 | grep -qE -- "$3"
  ok $? "doctor $1 rc $2: $(printf '%s' "$out" | head -1)"
}
L="$tmp/lib"
cfg "{\"lessons\": {\"dir\": \"$L\"}}"
doc index-fresh 0 'no lessons library yet'
mkdir -p "$L"; doc index-fresh 0 'no lesson records'
printf 'x\n' > "$L/base-001.md"; doc index-fresh 1 'no INDEX.md; run: harness lessons index'
printf 'i\n' > "$L/INDEX.md"; doc index-fresh 0 'INDEX.md is current \(1 lesson'
sleep 1; printf 'y\n' > "$L/base-001.md"; doc index-fresh 1 'older than 1 lesson record.*harness lessons index'
cfg '{"lessons": {"dir": ""}}'; mkdir -p "$tmp/xdg/harness/lessons"
doc index-fresh 0 'no lesson records in .*/xdg/harness/lessons'
cfg '{"lessons": {"dir": "~/lessons"}}'; doc index-fresh 0 "no lessons library yet \\($tmp/h/lessons\\)"

# stale-candidates against a stub CLI
mkdir -p "$tmp/stubhub/bin"
cat > "$tmp/stubhub/bin/harness" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "${STUB_LOG:-/dev/null}"
[ "$*" = "lessons list --stale --json --config /home/u/harness.toml" ] || exit 9
cat "${STUB_OUT:-/dev/null}"; exit "${STUB_RC:-0}"
STUB
chmod +x "$tmp/stubhub/bin/harness"
cfg "{\"lessons\": {\"dir\": \"$L\"}, \"_harness\": {\"config\": \"/home/u/harness.toml\"}}"
printf '[]' > "$tmp/none.json"
printf '[{"id":"base-001","status":"candidate","stale":true},{"id":"base-002","status":"confirmed","stale":true}]' > "$tmp/two.json"
STUB_OUT="$tmp/none.json" doc stale-candidates 0 'no stale candidate lessons'
STUB_OUT="$tmp/two.json" doc stale-candidates 1 '^1 stale candidate lesson.*harness lessons list --stale'
STUB_OUT="$tmp/none.json" STUB_RC=4 doc stale-candidates 1 'failed; run it by hand'
printf 'garbage' > "$tmp/bad.json"; STUB_OUT="$tmp/bad.json" doc stale-candidates 1 'printed no list'

# review-keys
cfg '{"lessons": {"correction_re": "^(no|nope)", "dissatisfaction_re": "(frustrat|annoy)"}}'
doc review-keys 0 'compile under grep -E'
cfg '{"lessons": {"correction_re": "^(no|nope", "dissatisfaction_re": "(frustrat|annoy)"}}'
doc review-keys 1 'does not compile under grep -E: lessons.correction_re; fix the value in harness.toml'
cfg '{"lessons": {"correction_re": "ok", "dissatisfaction_re": "[a-"}}'
doc review-keys 1 'lessons.dissatisfaction_re'
d=$(PYTHONPATH="$bdir/../../lib" python3 -c 'import json, sys
from harness import toml_compat
print(json.dumps({"lessons": toml_compat.load_file(sys.argv[1])["lessons"]}))' "$bdir/../core/defaults.toml")
cfg "$d"; doc review-keys 0 'compile under grep -E'
HARNESS_CONFIG_JSON="$tmp/config.json" bash "$D" nope >/dev/null 2>&1; [ $? = 2 ]; ok $? "doctor.sh: unknown check -> rc 2"

[ $fail -eq 0 ] && echo "all lessons tests passed ($cases)" || echo "lessons tests FAILED"
exit $fail
