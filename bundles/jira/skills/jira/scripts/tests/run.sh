#!/usr/bin/env bash
# Offline tests for jira.py. Part 1: configuration resolution (no request is made — every
# write runs under JIRA_DRY_RUN=1, everything else fails on the missing URL first). Part 2:
# golden cases with every HTTP call routed through tests/fakes/http_fixture.py (no network):
# reads, error mapping, dry-run governance writes and upload. UPDATE=1 rewrites golden/.
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
CLI="$here/../jira.py"
FIX="$here/fixtures"
GOLD="$here/golden"
DRIVER=$(cd "$here/../../../../../../tests/fakes" && pwd)/http_fixture.py
tmp=$(mktemp -d); tmp=$(cd "$tmp" && pwd -P); trap 'rm -rf "$tmp"' EXIT
export HARNESS_CONFIG_JSON=/dev/null JIRA_TOKEN=dummy-token-for-tests  # pragma: allowlist secret (fake test token)
unset JIRA_URL HARNESS_JIRA_FIELDS_JSON HARNESS_JIRA_GET_EXCLUDE JIRA_DRY_RUN JIRA_INSECURE HARNESS_HOME
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
chk "$rc" "dry-run create succeeds with jira.url from the harness config"
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

# ============================================================ part 2: fixture-routed goldens
mkdir -p "$tmp/fakehome" "$tmp/work" "$GOLD"
DRY_CASES=""; ALL_CASES=""
SECRETS_RE='dummy-token-for-tests|Bearer'  # pragma: allowlist secret (fake test token)
KEY=PROJ-123

# Normalise what moves: the sandbox and checkout paths, the multipart boundary (uuid4) and
# CRLF in the upload body, and the help text (jira.py's module docstring; checked once by
# the usage assertion above, not in every golden).
norm() {
  python3 - "$1" "$here" "$tmp" "$CLI" <<'PY'
import ast, re, sys
p, here, tmp, cli = sys.argv[1:5]
doc = ast.get_docstring(ast.parse(open(cli).read()), clean=False)
t = open(p, newline="").read().replace(doc, "<USAGE>").replace(tmp, "SANDBOX").replace(here, "HERE")
t = re.sub(r"jirapyboundary[0-9a-f]{32}", "jirapyboundaryBOUNDARY", t).replace("\r\n", "\n")
open(p, "w").write(t)
PY
}

record() {  # record <name> <exit>
  local name=$1 rc=$2 g="$tmp/$1.txt"
  { echo "# exit=$rc"; echo "# stderr:"; cat "$tmp/$name.err"; echo "# stdout:"; cat "$tmp/$name.out"
    echo "# calls:"; cat "$tmp/$name.log"; } > "$g"
  norm "$g"
  cases=$((cases + 1))
  if [ "${UPDATE:-0}" = 1 ]; then cp "$g" "$GOLD/$name.txt"; echo "UPDATED $name"; return; fi
  if [ ! -f "$GOLD/$name.txt" ]; then echo "FAIL $name (no golden — run UPDATE=1)"; fail=1; return; fi
  if diff -u "$GOLD/$name.txt" "$g" > "$tmp/$name.diff"; then echo "PASS $name"
  else echo "FAIL $name"; head -40 "$tmp/$name.diff"; fail=1; fi
}

# t <name> <expected-exit> <routes> <args...>     read / error case
# w <name> <expected-exit> <routes> <args...>     write case, JIRA_DRY_RUN=1
# Every case: empty HOME (no ~/.config/jira), JIRA_URL=https://jira.example.com, the fake
# token in JIRA_TOKEN (TOKEN= before the call overrides it), friendly field names from
# fixtures/config.json.
TOKEN=$JIRA_TOKEN
run() {
  local dry=$1 name=$2 exp=$3 routes=$4 dr=""; shift 4
  : > "$tmp/$name.log"
  [ "$dry" = 1 ] && dr=1
  (cd "$tmp/work" && HOME="$tmp/fakehome" JIRA_URL=https://jira.example.com JIRA_TOKEN="$TOKEN" \
    HARNESS_CONFIG_JSON="$FIX/config.json" JIRA_DRY_RUN="$dr" \
    python3 "$DRIVER" "$CLI" "$FIX/routes/$routes.json" --log "$tmp/$name.log" -- "$@") \
    > "$tmp/$name.out" 2> "$tmp/$name.err"
  local rc=$?
  [ "$rc" = "$exp" ] || { echo "FAIL $name: exit $rc, expected $exp"; cat "$tmp/$name.err"; fail=1; }
  ALL_CASES="$ALL_CASES $name"
  [ "$dry" = 1 ] && DRY_CASES="$DRY_CASES $name"
  record "$name" "$rc"
}
t() { run 0 "$@"; }
w() { run 1 "$@"; }

# ----------------------------------------------------------------------- dispatch
t unknown-command       1 empty frobnicate
t missing-args          1 empty get
t driver-no-route       3 empty whoami

# -------------------------------------------------------------------------- reads
t whoami                0 reads whoami
t get-friendly-fields   0 reads get "$KEY"
t links                 0 reads links "$KEY"
t links-none            0 reads links PROJ-200
t search                0 reads search 'project = PROJ AND resolution IS EMPTY ORDER BY updated DESC'
t search-max            0 reads search 'assignee = currentUser()' 2
t fields-project        0 reads fields PROJ
t fields-issue          0 reads fields "$KEY"
t api-mypermissions     0 reads api '/rest/api/2/mypermissions?projectKey=PROJ'
t api-bad-path          1 reads api /secure/ViewProfile.jspa
t versions              0 reads versions PROJ
t transitions           0 reads transitions "$KEY"
t attachments           0 reads attachments "$KEY"
t attachments-none      0 reads attachments PROJ-200
t download              0 reads download "$KEY" dl
t sprints               0 reads sprints PROJ
t sprints-no-board      1 reads sprints OTHER

# ------------------------------------------------------------------------- errors
t whoami-401            2 err-401 whoami
t get-403               2 err-403 get "$KEY"
t get-404               1 err-404 get PROJ-999
t get-500               1 err-500 get "$KEY"
t whoami-unreachable    2 err-unreachable whoami
TOKEN=""
t whoami-no-token       2 empty whoami
TOKEN=$JIRA_TOKEN

# ------------------------------------------- governance writes (JIRA_DRY_RUN=1: shapes only)
w label-add             0 empty label "$KEY" add agent-worked
w label-remove          0 empty label "$KEY" remove agent-drafted
w label-bad-op          1 empty label "$KEY" replace agent-worked
w transition            0 reads transition "$KEY" 'in review'
w transition-unknown    1 reads transition "$KEY" Closed
w create-labelled       0 empty create PROJ Task "Fix the config parser" \
                          --description "$(printf 'h3. Problem\nThe parser drops *quoted* keys.\n{code}key = "a b"{code}')" \
                          --field labels='["agent-drafted"]' --field "Story Points"=3 --field "Epic Link"=PROJ-100
w create-link           0 reads create PROJ Task "Split part 1" --field labels='["agent-created","agent-worked"]' \
                          --link "issue split:PROJ-100"
w create-bad-link-arg   1 empty create PROJ Task "x" --link PROJ-100
w create-no-summary     1 empty create PROJ Task
w link                  0 reads link PROJ-100 relates "$KEY"
w link-unknown-type     1 reads link PROJ-100 Duplicates "$KEY"
w link-self             1 empty link "$KEY" Relates proj-123
w comment               0 empty comment "$KEY" "$(printf 'h3. Update\n* parser fixed\n{noformat}ok{noformat}')"
w set-friendly          0 empty set "$KEY" "Story Points" 5
w set-raw-string        0 empty set "$KEY" "Testing Solution" 'unit tests in tests/run.sh'
w set-json              0 empty set "$KEY" versions '[{"name":"1.3.0"}]'
# upload bypasses JIRA_DRY_RUN (it builds its own request): the multipart POST is sent.
w upload                0 reads upload "$KEY" "$FIX/files/build.txt"
w upload-missing-file   1 reads upload "$KEY" "$FIX/files/absent.txt"
t upload-403            2 err-403 upload "$KEY" "$FIX/files/build.txt"

# ------------------------------------------------------------------- golden invariants
leaks=""
for n in $ALL_CASES; do
  grep -qE "$SECRETS_RE" "$tmp/$n.txt" && leaks="$leaks $n"   # stdout+stderr, help text cut
done
[ -z "$leaks" ]; chk $? "the token and the Bearer header never reach stdout or stderr outside the help${leaks:+ (leaked:$leaks)}"
! grep -rqE "$SECRETS_RE" "$GOLD"; chk $? "no golden holds the token or a Bearer header"

cat "$tmp"/*.log > "$tmp/all-calls"
[ -s "$tmp/all-calls" ] && ! grep -qv ' auth=yes$' "$tmp/all-calls"
chk $? "every request carries an Authorization header"
! cut -d' ' -f2 "$tmp/all-calls" | grep -qv '^https://jira\.example\.com/'
chk $? "every request goes to the configured base URL"

bad=""
for n in $DRY_CASES; do
  [ "$n" = upload ] && continue
  grep -qv '^GET ' "$tmp/$n.log" && bad="$bad $n"
done
[ -z "$bad" ]; chk $? "dry-run writes send only GET requests (upload excepted)${bad:+ (non-GET in:$bad)}"
grep -qx 'POST https://jira.example.com/rest/api/2/issue/PROJ-123/attachments auth=yes' "$tmp/upload.log"
chk $? "upload sends its multipart POST even under JIRA_DRY_RUN=1"
[ ! -s "$tmp/whoami-no-token.log" ] && [ ! -s "$tmp/link-self.log" ] && [ ! -s "$tmp/label-bad-op.log" ]
chk $? "a missing token, a self link or a bad label op fail before any request"

python3 - "$tmp" <<'PY'; chk $? "dry-run request bodies: label update verb, transition id, labelled create, outward link side"
import json, sys
def dry(name):
    out = []
    for line in open(f"{sys.argv[1]}/{name}.err"):
        if line.startswith("DRY-RUN "):
            _, method, path, body = line.rstrip("\n").split(" ", 3)
            out.append((method, path, json.loads(body)))
    return out
assert dry("label-add") == [("PUT", "/rest/api/2/issue/PROJ-123", {"update": {"labels": [{"add": "agent-worked"}]}})]
assert dry("transition") == [("POST", "/rest/api/2/issue/PROJ-123/transitions", {"transition": {"id": "21"}})]
[(m, p, b)] = dry("create-labelled")
assert (m, p) == ("POST", "/rest/api/2/issue") and b["fields"]["labels"] == ["agent-drafted"]
assert b["fields"]["customfield_20002"] == 3 and b["fields"]["customfield_20006"] == "PROJ-100"
assert b["fields"]["description"].startswith("h3. Problem\n")       # wiki markup, never ADF
[(m, p, b)] = dry("create-link")
assert b["update"] == {"issuelinks": [{"add": {"type": {"name": "Issue split"}, "inwardIssue": {"key": "PROJ-100"}}}]}
assert dry("link") == [("POST", "/rest/api/2/issueLink",
                        {"type": {"name": "Relates"}, "inwardIssue": {"key": "PROJ-100"}, "outwardIssue": {"key": "PROJ-123"}})]
assert dry("set-friendly") == [("PUT", "/rest/api/2/issue/PROJ-123", {"fields": {"customfield_20002": 5}})]
assert dry("set-raw-string")[0][2] == {"fields": {"customfield_20100": "unit tests in tests/run.sh"}}
PY
python3 - "$tmp/get-friendly-fields.out" <<'PY'; chk $? "get surfaces configured fields (sprint parsed) and keeps get_exclude write-only"
import json, sys
o = json.load(open(sys.argv[1]))
assert o["storyPoints"] == 3 and o["epicLink"] == "PROJ-100", o
assert o["sprint"] == {"id": 42, "name": "Sprint 12"}, o.get("sprint")
assert "testingSolution" not in o and o["url"] == "https://jira.example.com/browse/PROJ-123"
assert [l["direction"] for l in o["links"]] == ["relates to", "split from"]
PY
printf 'log line 1\nlog line 2\n' | cmp -s - "$tmp/work/dl/build.log"
chk $? "download writes each attachment's bytes into DIR"

echo "----"
if [ $fail -eq 0 ]; then echo "all jira tests passed ($cases cases)"; else echo "jira tests FAILED"; fi
exit $fail
