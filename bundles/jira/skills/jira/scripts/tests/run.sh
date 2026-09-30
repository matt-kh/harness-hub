#!/usr/bin/env bash
# Offline tests for jira.py: configuration resolution only (no Jira server is contacted —
# every write runs under JIRA_DRY_RUN=1 and every command that would talk to Jira either
# fails on the missing URL first or is a dry run).
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
CLI="$here/../jira.py"
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
export HARNESS_CONFIG_JSON=/dev/null JIRA_TOKEN=dummy-token-for-tests
unset JIRA_URL HARNESS_JIRA_FIELDS_JSON
fail=0; cases=0
chk() {  # chk <rc> <label>
  cases=$((cases + 1))
  if [ "$1" = 0 ]; then echo "PASS $2"; else echo "FAIL $2"; fail=1; fi
}

python3 "$CLI" > "$tmp/usage.out" 2>&1; rc=$?
[ "$rc" = 1 ] && grep -q "Commands (run with no args" "$tmp/usage.out"; chk $? "bare jira prints the help without any configuration"

python3 "$CLI" whoami > /dev/null 2> "$tmp/nourl.err"; rc=$?
[ "$rc" = 2 ] && grep -q "Jira is not configured" "$tmp/nourl.err"; chk $? "no jira.url / JIRA_URL: exit 2 with a clear message"

cat > "$tmp/cfg.json" <<'JSON'
{"jira": {"url": "https://jira.example.test/",
          "fields": {"story_points": "customfield_20002",
                     "PROJ": {"epic_link": "customfield_21206",
                              "testing_solution": "customfield_20100"}},
          "get_exclude": ["testing_solution"]}}
JSON
HARNESS_CONFIG_JSON="$tmp/cfg.json" JIRA_DRY_RUN=1 python3 "$CLI" create PROJ Task "t" \
  --field labels='["agent-drafted"]' --field "Epic Link"='"PROJ-1"' --field story_points=3 \
  --field "Testing Solution"='"x"' > "$tmp/create.out" 2> "$tmp/create.err"; rc=$?
[ "$rc" = 0 ]; chk $? "dry-run create succeeds with jira.url from the harness config"
grep -q 'https://jira.example.test/browse/DRY-0' "$tmp/create.out"; chk $? "base URL comes from jira.url (trailing slash stripped)"
grep -q '"customfield_21206": "PROJ-1"' "$tmp/create.err"; chk $? "project field name (Epic Link) resolves via jira.fields.PROJ"
grep -q '"customfield_20002": 3' "$tmp/create.err"; chk $? "global field name in snake form (story_points) resolves"
grep -q '"customfield_20100": "x"' "$tmp/create.err"; chk $? "jira.get_exclude entries still resolve for writes"

JIRA_URL=https://env.example.test HARNESS_CONFIG_JSON="$tmp/cfg.json" JIRA_DRY_RUN=1 python3 "$CLI" create PROJ Task "t" \
  --field labels='["agent-drafted"]' > "$tmp/env.out" 2>/dev/null
grep -q 'https://env.example.test/browse/DRY-0' "$tmp/env.out"; chk $? "JIRA_URL in the environment wins over jira.url"

HARNESS_JIRA_FIELDS_JSON='{"OTHER": {"epic_link": "customfield_9"}}' HARNESS_CONFIG_JSON="$tmp/cfg.json" \
  JIRA_DRY_RUN=1 python3 "$CLI" create OTHER Task "t" --field labels='["agent-drafted"]' \
  --field "Epic Link"='"X-1"' > /dev/null 2> "$tmp/envf.err"
grep -q '"customfield_9": "X-1"' "$tmp/envf.err"; chk $? "HARNESS_JIRA_FIELDS_JSON overrides jira.fields"

python3 - "$CLI" "$tmp/cfg.json" <<'PY'; chk $? "get surfaces configured fields per project; jira.get_exclude stays write-only"
import importlib.util, os, sys
os.environ["HARNESS_CONFIG_JSON"] = sys.argv[2]
spec = importlib.util.spec_from_file_location("jira_cli", sys.argv[1])
j = importlib.util.module_from_spec(spec); spec.loader.exec_module(j)
assert j.get_extra("PROJ") == {"customfield_20002": "storyPoints", "customfield_21206": "epicLink"}, j.get_extra("PROJ")
assert j.get_extra("OTHER") == {"customfield_20002": "storyPoints"}, j.get_extra("OTHER")
assert j.resolve_field("Epic Link", "OTHER") == "customfield_21206"   # any project's table as fallback
assert j.resolve_field("summary", "PROJ") == "summary"                # built-ins pass through
os.environ["HARNESS_JIRA_GET_EXCLUDE"] = "Story Points"
assert j.get_extra("OTHER") == {}, j.get_extra("OTHER")               # env list overrides config
PY

echo "----"
if [ $fail -eq 0 ]; then echo "all jira tests passed ($cases cases)"; else echo "jira tests FAILED"; fi
exit $fail
