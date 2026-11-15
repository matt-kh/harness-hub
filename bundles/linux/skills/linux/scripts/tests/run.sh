#!/usr/bin/env bash
# Golden tests for lx.py, driven entirely by ssh-stub.sh and the fixtures (an Ubuntu 24.04 host
# `web1` and a RHEL-family prod host `db-prod-1`). No network, no key, no real host.
# UPDATE=1 rewrites golden/. KEEP=1 keeps the scratch directory. Exits non-zero on any failure.
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
CLI="$here/../lx.py"
FIX="$here/fixtures"
GOLD="$here/golden"
export LINUX_SSH_BIN="$here/ssh-stub.sh"
export LINUX_SSH_CONFIG="$FIX/ssh/config"
unset LINUX_PROD_RE LINUX_INVENTORY LINUX_SSH_TIMEOUT LINUX_REDACT_EXTRA_RE
export HARNESS_CONFIG_JSON=/dev/null   # hermetic: never read a real build/config.json
tmp=$(mktemp -d)
export STUB_LOG="$tmp/stub.log"; : > "$STUB_LOG"
fail=0; cases=0
mkdir -p "$GOLD"

record() {  # record <name> <exit> <stdout-file> <stderr-file>
  local name=$1 rc=$2 out=$3 err=$4 g="$tmp/$1.txt"
  { echo "# exit=$rc"; echo "# stderr:"; cat "$err"; echo "# stdout:"; cat "$out"; } > "$g"
  python3 - "$g" "$here" <<'PY'
import sys
p = sys.argv[1]
t = open(p).read().replace(sys.argv[2], "HERE")   # the checkout location never reaches a golden
open(p, "w").write(t)
PY
  cases=$((cases + 1))
  if [ "${UPDATE:-0}" = 1 ]; then cp "$g" "$GOLD/$name.txt"; echo "UPDATED $name"; return; fi
  if [ ! -f "$GOLD/$name.txt" ]; then echo "FAIL $name (no golden — run UPDATE=1)"; fail=1; return; fi
  if diff -u "$GOLD/$name.txt" "$g" > "$tmp/$name.diff"; then echo "PASS $name"
  else echo "FAIL $name"; head -40 "$tmp/$name.diff"; fail=1; fi
}

t() {  # t <name> <expected-exit> <args...>
  local name=$1 exp=$2; shift 2
  python3 "$CLI" "$@" > "$tmp/$name.out" 2> "$tmp/$name.err"; local rc=$?
  [ "$rc" = "$exp" ] || { echo "FAIL $name: exit $rc, expected $exp"; cat "$tmp/$name.err"; fail=1; }
  record "$name" "$rc" "$tmp/$name.out" "$tmp/$name.err"
}

ts() {  # ts <name> <expected-exit> <stdin-file> <args...>
  local name=$1 exp=$2 inp=$3; shift 3
  python3 "$CLI" "$@" < "$inp" > "$tmp/$name.out" 2> "$tmp/$name.err"; local rc=$?
  [ "$rc" = "$exp" ] || { echo "FAIL $name: exit $rc, expected $exp"; cat "$tmp/$name.err"; fail=1; }
  record "$name" "$rc" "$tmp/$name.out" "$tmp/$name.err"
}

# ---------------------------------------------------------------- per-subcommand golden
t hosts-md            0 hosts
t hosts-json          0 hosts --json
LINUX_INVENTORY="$FIX/inventory.tsv" t hosts-inventory-md   1 hosts
LINUX_INVENTORY="$FIX/inventory.tsv" t hosts-inventory-json 1 hosts --json
for h in web1 db-prod-1; do
  t "check-$h-md"     0 check "$h"
  t "check-$h-json"   0 check "$h" --json
  t "facts-$h-md"     0 facts "$h"
  t "facts-$h-json"   0 facts "$h" --json
  t "health-$h-md"    1 health "$h"
  t "health-$h-json"  1 health "$h" --json
  t "logs-$h-md"      0 logs "$h"
  t "logs-$h-json"    0 logs "$h" --json
  t "net-$h-md"       1 net "$h"
  t "net-$h-json"     1 net "$h" --json
  t "storage-$h-md"   1 storage "$h"
  t "storage-$h-json" 1 storage "$h" --json
  t "audit-$h-md"     1 audit "$h"
  t "audit-$h-json"   1 audit "$h" --json
done
t logs-filtered-json  0 logs web1 --since 30m --limit 50 --unit nginx.service --priority warning..emerg --json
t check-unreachable   2 check unreachable
t check-unreachable-json 2 check unreachable --json
t access-unreachable  2 facts unreachable
t access-denied       2 health denied
t access-hostkey      2 net hostkey
t access-unknown      2 facts nosuchhost
t access-userhost     2 facts deploy@web1
ts redact-text        0 "$FIX/redact.txt" redact
ts redact-json        0 "$FIX/redact.json" redact --json
LINUX_REDACT_EXTRA_RE='request id [0-9a-f]+' \
  ts redact-extra-re  0 "$FIX/redact.txt" redact

# ------------------------------------------------------------------------- assertions
chk() {  # chk <condition-exit> <label>
  cases=$((cases + 1))
  if [ "$1" = 0 ]; then echo "PASS $2"; else echo "FAIL $2"; fail=1; fi
}
ck() { local d=$1; shift; "$@"; chk $? "$d"; }  # ck <label> <test...>: run the test, record it

grep -q '^host=db-prod-1 os=rocky 9.4 \[PROD\]$' "$tmp/facts-db-prod-1-md.err"; chk $? "prod alias banner carries os and [PROD]"
grep -q '^host=web1 os=ubuntu 24.04$' "$tmp/facts-web1-md.err"; chk $? "non-prod banner carries os and no [PROD]"
grep -q '"prod": true' "$tmp/facts-db-prod-1-json.out"; chk $? "prod flag in the JSON envelope"

# secrets and key paths never reach stdout
for f in logs-web1-md logs-web1-json logs-db-prod-1-md logs-db-prod-1-json redact-text redact-json redact-extra-re; do
  if grep -qE 'hunter2|s3cr3t-value|AKIA[0-9A-Z]{16}|eyJhbGci|pgpass123|BEGIN [A-Z]+ PRIVATE KEY' "$tmp/$f.out"; then
    echo "FAIL $f leaks a credential"; fail=1
  else
    echo "PASS $f is redacted"
  fi
  cases=$((cases + 1))
done
grep -q 'REDACTED' "$tmp/logs-web1-md.out"; chk $? "logs output is passed through the redactor"
for f in hosts-md hosts-json hosts-inventory-md hosts-inventory-json; do
  ! grep -qiE 'identityfile|id_ed25519' "$tmp/$f.out"; chk $? "$f never shows IdentityFile"
done
! grep -qE '\*|bastion' "$tmp/hosts-json.out"; chk $? "wildcard patterns and Match blocks are not aliases"
grep -q '"alias": "lab-nixos"' "$tmp/hosts-json.out"; chk $? "Include files are parsed"
grep -q 'ghost' "$tmp/hosts-inventory-md.out"; chk $? "inventory host without an alias is flagged"

# harness parameters
LINUX_PROD_RE='^web' python3 "$CLI" facts web1 > /dev/null 2> "$tmp/p-prod.err"
grep -q '\[PROD\]' "$tmp/p-prod.err"; chk $? "LINUX_PROD_RE marks a matching alias [PROD]"
printf '{"linux":{"prod_re":"^web","ssh_timeout":7}}' > "$tmp/cfg.json"
HARNESS_CONFIG_JSON="$tmp/cfg.json" python3 "$CLI" facts web1 > /dev/null 2> "$tmp/p-cfg.err"
grep -q '\[PROD\]' "$tmp/p-cfg.err"; chk $? "linux.prod_re from the harness config is honoured"
tail -1 "$STUB_LOG" | grep -q 'ConnectTimeout=7 '; chk $? "linux.ssh_timeout from the harness config sets ConnectTimeout"
LINUX_PROD_RE='^never$' HARNESS_CONFIG_JSON="$tmp/cfg.json" python3 "$CLI" facts web1 > /dev/null 2> "$tmp/p-env.err"
! grep -q '\[PROD\]' "$tmp/p-env.err"; chk $? "LINUX_PROD_RE in the environment wins over the config"
LINUX_SSH_TIMEOUT=5 python3 "$CLI" check web1 > /dev/null 2>&1
tail -1 "$STUB_LOG" | grep -q 'ConnectTimeout=5 '; chk $? "LINUX_SSH_TIMEOUT sets ConnectTimeout"
LINUX_REDACT_EXTRA_RE='(' python3 "$CLI" redact < /dev/null > /dev/null 2> "$tmp/p-rxbad.err"; rc=$?
[ "$rc" = 1 ] && grep -q 'not a valid Python regex' "$tmp/p-rxbad.err"; chk $? "an invalid LINUX_REDACT_EXTRA_RE exits 1 with a message"
LINUX_REDACT_EXTRA_RE='(' python3 "$CLI" facts web1 > /dev/null 2>&1; rc=$?
ck "an invalid LINUX_REDACT_EXTRA_RE does not break a command that does not redact" [ "$rc" = 0 ]

# logs bounds and validation (no ssh call on a rejected argument)
grep -F -- "--since \\'-1h\\' -n 200" "$STUB_LOG" | grep -q 'journalctl'; chk $? "logs without --since/--limit uses --since -1h -n 200"
grep -F -- "--since \\'-30m\\' -n 50 -u \\'nginx.service\\' -p \\'warning..emerg\\'" "$STUB_LOG" | grep -q journalctl
chk $? "logs passes --since, -n, -u and -p through"
before=$(wc -l < "$STUB_LOG")
python3 "$CLI" logs web1 --since 'now; reboot' > /dev/null 2>&1; rc=$?; ck "logs rejects a malformed --since" [ "$rc" = 1 ]
python3 "$CLI" logs web1 --limit 100000 > /dev/null 2>&1; rc=$?; ck "logs rejects --limit above the cap" [ "$rc" = 1 ]
python3 "$CLI" logs web1 --unit 'x;reboot' > /dev/null 2>&1; rc=$?; ck "logs rejects a unit with shell metacharacters" [ "$rc" = 1 ]
python3 "$CLI" logs web1 --priority 'err;id' > /dev/null 2>&1; rc=$?; ck "logs rejects a malformed --priority" [ "$rc" = 1 ]
after=$(wc -l < "$STUB_LOG")
ck "rejected logs arguments never reach ssh" [ "$before" = "$after" ]
! grep -qE ' -- (nosuchhost|deploy@web1) ' "$STUB_LOG"; chk $? "unknown aliases and user@host never reach ssh"

# global flag placement, usage, version
python3 "$CLI" --json facts web1 > "$tmp/lead.out" 2>/dev/null
cmp -s "$tmp/lead.out" "$tmp/facts-web1-json.out"; chk $? "\`lx --json facts\` equals \`lx facts --json\`"
python3 "$CLI" > "$tmp/usage.out" 2>&1; rc=$?
[ "$rc" = 1 ] && grep -q "Deliberately NOT implemented" "$tmp/usage.out"; chk $? "bare lx prints usage, exit 1"
python3 "$CLI" bogus > "$tmp/bogus.out" 2>&1; rc=$?
[ "$rc" = 1 ] && grep -q "Unknown command" "$tmp/bogus.out"; chk $? "unknown command exits 1"
python3 "$CLI" --version > "$tmp/ver.out" 2>&1; rc=$?
[ "$rc" = 0 ] && grep -qE '^lx [0-9]+\.[0-9]+\.[0-9]+$' "$tmp/ver.out"; chk $? "lx --version"
python3 "$CLI" logs -h > "$tmp/h.out" 2>&1; rc=$?
[ "$rc" = 0 ] && grep -q -- "--since" "$tmp/h.out"; chk $? "lx logs -h works"

# ------------------------------------------------------------------ stub log invariants
n=$(grep -c '^ssh ' "$STUB_LOG")
ck "the stub saw the remote calls ($n)" [ "$n" -gt 20 ]
bad=$(grep '^ssh ' "$STUB_LOG" | grep -v -- '-o BatchMode=yes ' | head -3)
ck "every ssh call passes -o BatchMode=yes" [ -z "$bad" ]
bad=$(grep '^ssh ' "$STUB_LOG" | grep -vE -- '-o ConnectTimeout=[0-9]+ ' | head -3)
ck "every ssh call passes -o ConnectTimeout" [ -z "$bad" ]
! grep -qi 'StrictHostKeyChecking\|UserKnownHostsFile' "$STUB_LOG"; chk $? "no ssh call touches host-key checking"
opts=$(sed 's/ -- .*//' "$STUB_LOG")   # the ssh options only, without the alias and script
! printf '%s\n' "$opts" | grep -qE ' -t{1,2}( |$)'; chk $? "no ssh call requests a tty (-t)"
bad=$(grep '^ssh ' "$STUB_LOG" | grep -v -- ' -T -n -- ' | head -3)
ck "every ssh call passes -T -n and ends options with --" [ -z "$bad" ]
! grep -qE 'journalctl( [^ \\|;]+)* (-f|--follow)( |\\|$)|tail -[fF]' "$STUB_LOG"; chk $? "no follow mode is ever sent"
! grep -qE '(^| |\\n)(sudo|rm|systemctl (restart|stop|start|enable|disable|mask)|reboot|shutdown|kill|mkfs|dd|tee|mv|cp|chmod|chown|apt(-get)? (install|upgrade|update|remove)|dnf (install|upgrade|update|remove)) ' "$STUB_LOG"
chk $? "no remote script carries a mutating command"
! printf '%s\n' "$opts" | grep -qE ' -(L|R|D|W|A|X|Y|N|f|M|O)( |$)'; chk $? "no forwarding or background flags"
! grep -qi 'identityfile\|\.ssh/id_' "$STUB_LOG"; chk $? "no ssh call names a key file"

if [ "${KEEP:-0}" = 1 ]; then echo "artifacts in $tmp"; else rm -rf "$tmp"; fi
if [ $fail -eq 0 ]; then echo "all lx tests passed ($cases cases)"; else echo "lx tests FAILED"; fi
exit $fail
