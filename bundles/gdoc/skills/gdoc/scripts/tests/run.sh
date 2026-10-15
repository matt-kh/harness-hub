#!/usr/bin/env bash
# Offline golden tests for gdoc.py. Every HTTP call goes through tests/fakes/http_fixture.py
# (fixture-routed urlopen, no network); every case runs in its own throw-away HOME with the
# fake credential files from fixtures/homes/<kind> installed at 700/600; every write case runs
# under GDOC_DRY_RUN=1. UPDATE=1 rewrites golden/. Exits non-zero on any failure.
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
CLI="$here/../gdoc.py"
FIX="$here/fixtures"
GOLD="$here/golden"
DRIVER=$(cd "$here/../../../../../../tests/fakes" && pwd)/http_fixture.py
export HARNESS_CONFIG_JSON=/dev/null   # hermetic: never read a real build/config.json
unset GDOC_DRY_RUN GDOC_TIMEOUT GDOC_HD HARNESS_HOME
tmp=$(mktemp -d); tmp=$(cd "$tmp" && pwd -P); trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/work" "$GOLD"
fail=0; cases=0
DRY_CASES=""; ALL_CASES=""

# Fake credential values (fixtures/homes/*): none of them may ever reach stdout or stderr.
SECRETS_RE='test-access-token|test-refresh-token|test-client-secret|test-refreshed-access-token|Bearer'  # pragma: allowlist secret (fake fixture values)

DOC=doc00000000000000000000001; DOC2=doc00000000000000000000002
SHEET=sheet000000000000000000001; FOLDER=folder00000000000000000001; PDF=pdf000000000000000000000001

# Normalise what moves: the sandbox and checkout paths, any timestamp near the wall clock
# (agent_created_at / agent_marked_at stamps, a refreshed token's expiry), and the help text
# (gdoc.py's module docstring; checked once by the usage assertion, not in every golden).
norm() {
  python3 - "$1" "$here" "$tmp" "$CLI" <<'PY'
import ast, re, sys, time
from datetime import datetime
p, here, tmp, cli = sys.argv[1:5]
doc = ast.get_docstring(ast.parse(open(cli).read()), clean=False)
t = open(p).read().replace(doc, "<USAGE>").replace(tmp, "SANDBOX").replace(here, "HERE")
def near(m):
    s = m.group(0).replace("Z", "+00:00")
    try:
        when = datetime.fromisoformat(s).timestamp()
    except ValueError:
        return m.group(0)
    return "TIMESTAMP" if abs(when - time.time()) < 2 * 86400 else m.group(0)
t = re.sub(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)", near, t)
open(p, "w").write(t)
PY
}

# mkhome DIR KIND: KIND is ready|expired|badmode (files from fixtures/homes/KIND) or missing.
mkhome() {
  local h=$1 kind=$2
  rm -rf "$h"; mkdir -p "$h"
  [ "$kind" = missing ] && return 0
  mkdir -p "$h/.config/gdoc"
  cp "$FIX/homes/$kind/client_secret.json" "$FIX/homes/$kind/token.json" "$h/.config/gdoc/"
  if [ "$kind" = badmode ]; then
    chmod 755 "$h/.config/gdoc"; chmod 644 "$h/.config/gdoc/"*.json
  else
    chmod 700 "$h/.config/gdoc"; chmod 600 "$h/.config/gdoc/"*.json
  fi
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

# t <name> <expected-exit> <home-kind> <routes> <args...>       read / auth / dispatch case
# w <name> <expected-exit> <home-kind> <routes> <args...>       write case, GDOC_DRY_RUN=1
run() {
  local dry=$1 name=$2 exp=$3 kind=$4 routes=$5; shift 5
  mkhome "$tmp/home-$name" "$kind"; : > "$tmp/$name.log"
  if [ "$dry" = 1 ]; then
    (cd "$tmp/work" && HOME="$tmp/home-$name" GDOC_DRY_RUN=1 python3 "$DRIVER" "$CLI" \
      "$FIX/routes/$routes.json" --log "$tmp/$name.log" -- "$@") > "$tmp/$name.out" 2> "$tmp/$name.err"
  else
    (cd "$tmp/work" && HOME="$tmp/home-$name" python3 "$DRIVER" "$CLI" \
      "$FIX/routes/$routes.json" --log "$tmp/$name.log" -- "$@") > "$tmp/$name.out" 2> "$tmp/$name.err"
  fi
  local rc=$?
  [ "$rc" = "$exp" ] || { echo "FAIL $name: exit $rc, expected $exp"; cat "$tmp/$name.err"; fail=1; }
  ALL_CASES="$ALL_CASES $name"
  [ "$dry" = 1 ] && DRY_CASES="$DRY_CASES $name"
  record "$name" "$rc"
}
t() { run 0 "$@"; }
w() { run 1 "$@"; }

# ------------------------------------------------------------------------- dispatch
t usage                 1 missing empty
t unknown-command       1 missing empty frobnicate
t mail-send-absent      1 ready   empty mail send --to a@example.com
t sheet-no-subcommand   1 missing empty sheet
t too-many-args         1 ready   empty meta "$DOC" extra
t unknown-flag          1 ready   empty get "$DOC" --bogus

# ------------------------------------------------------------- auth status (offline)
t auth-status-ready     0 ready   empty auth status
t auth-status-missing   2 missing empty auth status
t auth-status-badmode   0 badmode empty auth status
t auth-status-expired   0 expired empty auth status

# --------------------------------------------------------------------- auth (online)
t whoami                0 ready   reads whoami
t whoami-refresh        0 expired refresh whoami
t refresh-invalid-grant 2 expired refresh-invalid-grant whoami
t whoami-not-signed-in  2 missing reads whoami
t whoami-401            2 ready   err-401 whoami
t whoami-403-scope      2 ready   err-403-scope whoami
t meta-403              1 ready   err-403 meta "$DOC"
t meta-404              1 ready   err-404 meta "$DOC"
t whoami-429-retry      0 ready   err-429 whoami
t whoami-500            1 ready   err-500 whoami
t whoami-unreachable    2 ready   err-unreachable whoami
t driver-no-route       3 ready   empty whoami

# ----------------------------------------------------------------------- id parsing
t id-bare               0 ready   reads meta "$DOC"
t id-doc-url            0 ready   reads meta "https://docs.google.com/document/d/$DOC/edit#heading=h.1"
t id-sheet-url          0 ready   reads meta "https://docs.google.com/spreadsheets/d/$SHEET/edit?gid=0"
t id-folder-url         0 ready   reads meta "https://drive.google.com/drive/u/0/folders/$FOLDER"
t id-query-param        0 ready   reads meta "https://drive.google.com/open?id=$PDF"
t id-quoted             0 ready   reads meta "'$DOC'"
t id-bad                1 ready   reads meta not-a-drive-id

# ----------------------------------------------------------------------------- reads
t search-phrase         0 ready   reads search "release checklist's notes"
t search-operators      0 ready   reads search "name contains 'QBR' and trashed=false" 5
t list-recent           0 ready   reads list
t list-folder           0 ready   reads list --folder "https://drive.google.com/drive/folders/$FOLDER" 10
t get-outline           0 ready   reads get "$DOC"
t get-tab               0 ready   reads get "$DOC" --tab t.1
t get-pre-tabs          0 ready   reads get "$DOC2"
t get-json              0 ready   reads get "$DOC2" --json
t get-not-a-doc         1 ready   reads get "$SHEET"
t export-md-stdout      0 ready   reads export "$DOC"
t export-csv-file       0 ready   reads export "$SHEET" sheet.csv
t export-txt-forced     0 ready   reads export "$DOC" --txt
t export-two-formats    1 ready   reads export "$DOC" --md --txt
t export-pdf-refused    1 ready   reads export "$PDF"
t comments              0 ready   reads comments "$DOC"
t comments-none         0 ready   reads comments "$DOC2"
t sheet-get-tabs        0 ready   reads sheet get "$SHEET"
t sheet-get-range       0 ready   reads sheet get "$SHEET" 'Sheet1!A1:B3'
t mail-search           0 ready   reads mail search "from:alice newer_than:7d"
t mail-get-plain        0 ready   reads mail get msg0001
t mail-get-html         0 ready   reads mail get msg0002

# -------------------------------------------------------------------- host allow-list
t api-ok                0 ready   reads api "https://www.googleapis.com/drive/v3/about?fields=user"
t api-http-denied       1 ready   reads api "http://www.googleapis.com/drive/v3/about"
t api-other-host        1 ready   reads api "https://evil.example.com/drive/v3/files"
t api-lookalike-host    1 ready   reads api "https://www.googleapis.com.example.com/drive/v3/about"

# ------------------------------------------------------------ dry-run writes (no sends)
w create                0 missing empty create "Kickoff notes" --from "$FIX/files/notes.md"
w create-folder-plain   0 ready   empty create Kickoff --from "$FIX/files/notes.md" --plain --folder "https://drive.google.com/drive/folders/$FOLDER"
w create-no-from        1 ready   empty create Kickoff
w create-missing-file   1 ready   empty create Kickoff --from "$FIX/files/absent.md"
w import-open-comments  1 ready   reads import "$DOC" "$FIX/files/notes.md"
w import-force          0 ready   reads import "$DOC" "$FIX/files/notes.md" --force
w import-clean          0 ready   reads import "$DOC2" "$FIX/files/notes.md"
w import-not-a-doc      1 ready   reads import "$SHEET" "$FIX/files/notes.md"
w append-text           0 ready   reads append "$DOC" "Decision: ship it."
w append-heading-tab    0 ready   reads append "$DOC" --from "$FIX/files/append.txt" --heading "Risks" --tab t.1
w append-pre-tabs       0 ready   reads append "$DOC2" "Plain addition"
w append-bad-tab        1 ready   reads append "$DOC" "x" --tab t.9
w append-no-text        1 ready   reads append "$DOC"
w replace               0 ready   empty replace "$DOC" "offline" "hermetic"
w replace-case-tab      0 ready   empty replace "$DOC" "Goals" "Aims" --match-case --tab t.0
w mark-created          0 ready   empty mark "$DOC" agent-created
w mark-worked           0 ready   empty mark "https://docs.google.com/document/d/$DOC2/edit" agent-worked
w mark-none             0 ready   empty mark "$DOC" none
w mark-bad-value        1 ready   empty mark "$DOC" human
w sheet-append          0 ready   empty sheet append "$SHEET" 'Sheet1!A:C' '[["a","b",1]]'
w sheet-update-file     0 ready   empty sheet update "$SHEET" "'Q1 costs'!A2:C3" "@$FIX/files/rows.json"
w sheet-bad-rows        1 ready   empty sheet append "$SHEET" 'Sheet1!A:C' '{"a":1}'
w mail-draft            0 missing empty mail draft --to bob@example.com --cc team@example.com --subject "Agenda" --body "Draft agenda attached."
w mail-draft-reply      0 ready   reads mail draft --reply-to msg0002 --body-file "$FIX/files/body.txt"
w mail-draft-reply-to   0 ready   reads mail draft --reply-to msg0001 --to carol@example.com --subject "Re: Quarterly plan" --body "Noted."
w mail-draft-no-to      1 ready   empty mail draft --subject "Agenda" --body "x"
w mail-draft-no-body    1 ready   empty mail draft --to bob@example.com --subject "Agenda"
w mail-draft-two-bodies 1 ready   empty mail draft --to bob@example.com --subject S --body x --body-file "$FIX/files/body.txt"
w mail-draft-no-sender  1 ready   reads mail draft --reply-to msg0003 --body "x"

# ------------------------------------------------------------------------- assertions
chk() {  # chk <rc> <label>
  cases=$((cases + 1))
  if [ "$1" = 0 ]; then echo "PASS $2"; else echo "FAIL $2"; fail=1; fi
}

python3 - "$CLI" "$tmp/usage.out" <<'PY'; chk $? "bare gdoc prints the module docstring (the help) on stdout"
import ast, sys
doc = ast.get_docstring(ast.parse(open(sys.argv[1]).read()), clean=False)
assert open(sys.argv[2]).read() == doc + "\n"
PY

leaks=""
for n in $ALL_CASES; do
  grep -qE "$SECRETS_RE" "$tmp/$n.out" "$tmp/$n.err" && leaks="$leaks $n"
done
[ -z "$leaks" ]; chk $? "no fake token, client secret or Bearer header in any output${leaks:+ (leaked:$leaks)}"

bad=""
for n in $DRY_CASES; do
  grep -qv '^GET ' "$tmp/$n.log" && bad="$bad $n"
done
[ -z "$bad" ]; chk $? "dry-run writes send only GET requests${bad:+ (non-GET in:$bad)}"

cat "$tmp"/*.log > "$tmp/all-calls"
! grep -E '/(drive/v3|upload/drive/v3)/files' "$tmp/all-calls" | grep -qv 'supportsAllDrives=true'
chk $? "every Drive files request carries supportsAllDrives=true"
cat "$tmp"/*.err | grep '^DRY-RUN' > "$tmp/all-dry" || true
[ -s "$tmp/all-dry" ] && ! grep -E '/drive/v3/files' "$tmp/all-dry" | grep -qv 'supportsAllDrives=true'
chk $? "every dry-run Drive write carries supportsAllDrives=true"
! grep -E 'googleapis\.com/(drive|gmail|v1|v4)|docs\.googleapis|sheets\.googleapis' "$tmp/all-calls" | grep -q 'auth=no'
chk $? "every API request carries an Authorization header"
grep -q '^POST https://oauth2.googleapis.com/token auth=no$' "$tmp/all-calls" \
  && ! grep -q '^POST https://oauth2.googleapis.com/token auth=yes$' "$tmp/all-calls"
chk $? "the token endpoint is called without a bearer token"
! grep -qE '/send|messages/send|drafts/send' "$tmp/all-calls" "$tmp/all-dry"
chk $? "nothing is ever sent: no Gmail send endpoint in any request"
[ ! -s "$tmp/create.log" ] && [ ! -s "$tmp/mail-draft.log" ]
chk $? "dry-run create and plain mail draft need no credentials and make no request"
grep -q '"agent_provenance": "agent-created", "agent_tool": "claude-code", "agent_created_at": "TIMESTAMP"' "$GOLD/create.txt"
chk $? "create stamps agent_provenance=agent-created with a creation time"
grep -q '"agent_provenance": null' "$GOLD/mark-none.txt"
chk $? "mark none clears the provenance properties"
python3 - "$tmp" <<'PY'; chk $? "mail drafts: recipient, subject and threading headers (Reply-To wins, no Re: Re:)"
import base64, email, json, sys
def draft(name):
    line = [l for l in open(f"{sys.argv[1]}/{name}.err") if l.startswith("DRY-RUN POST ")][0]
    body = json.loads(line.split(" ", 3)[3])["message"]
    msg = email.message_from_bytes(base64.urlsafe_b64decode(body["raw"]))
    return body, msg
b, m = draft("mail-draft")
assert (m["To"], m["Cc"], m["Subject"], m["In-Reply-To"]) == ("bob@example.com", "team@example.com", "Agenda", None)
assert "threadId" not in b and m.get_payload().strip() == "Draft agenda attached."
b, m = draft("mail-draft-reply")
assert (m["To"], m["Subject"], b["threadId"]) == ("team@example.com", "Re: Offsite", "thr0002"), (m["To"], m["Subject"])
assert m["In-Reply-To"] == "<m2@mail.example.com>" and m["References"] == "<m0@mail.example.com> <m2@mail.example.com>"
b, m = draft("mail-draft-reply-to")
assert (m["To"], m["Subject"], b["threadId"]) == ("carol@example.com", "Re: Quarterly plan", "thr0001")
assert m["References"] == "<m1@mail.example.com>"
PY
tokf="$tmp/home-whoami-refresh/.config/gdoc/token.json"
python3 - "$tokf" <<'PY'; chk $? "a refresh rewrites token.json at mode 600 with the new access token"
import json, os, stat, sys
p = sys.argv[1]
assert stat.S_IMODE(os.stat(p).st_mode) == 0o600, oct(os.stat(p).st_mode)
assert stat.S_IMODE(os.stat(os.path.dirname(p)).st_mode) == 0o700
tok = json.load(open(p))
assert tok["access_token"] == "test-refreshed-access-token" and tok["refresh_token"] == "test-refresh-token"
PY
grep -c '^GET .*/about' "$tmp/whoami-429-retry.log" | grep -qx 2
chk $? "a 429 on GET is retried exactly once"
grep -qx 'venue,100' "$tmp/work/sheet.csv" 2>/dev/null
chk $? "export FILE writes the bytes to the file"

echo "----"
if [ $fail -eq 0 ]; then echo "all gdoc tests passed ($cases cases)"; else echo "gdoc tests FAILED"; fi
exit $fail
