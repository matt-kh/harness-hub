#!/usr/bin/env bash
# Self-test for tools/gate/private-ids.sh: builds a throw-away git repo with planted hits and
# a throw-away private denylist, then asserts what the gate reports in every mode.
# Planted strings are assembled at run time so this file itself stays gate-clean.
# Usage: tools/gate/tests/selftest.sh [-v]
set -o pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
verbose=false; [ "${1:-}" = "-v" ] && verbose=true

T=$(mktemp -d "${TMPDIR:-/tmp}/gate-selftest.XXXXXX") || exit 2
trap 'rm -rf "$T"' EXIT
pass=0; fail=0
ok()  { pass=$((pass + 1)); $verbose && echo "ok   $1"; return 0; }
bad() { fail=$((fail + 1)); echo "FAIL $1"; [ -n "${2:-}" ] && printf '%s\n' "$2" | sed 's/^/     /'; return 0; }
expect_rc() { if [ "$2" -eq "$3" ]; then ok "$1 (rc=$3)"; else bad "$1: rc=$3, want $2" "$4"; fi; }
has()   { if printf '%s\n' "$3" | grep -qE -e "$2"; then ok "$1"; else bad "$1: no line matching /$2/" "$3"; fi; }
hasnt() { if printf '%s\n' "$3" | grep -qiE -e "$2"; then bad "$1: unexpected /$2/" "$3"; else ok "$1"; fi; }

# ---- planted values (split so this file does not match its own patterns) ----------------
PRIV="acme""corp"                          # the private identifier
EMAIL_BAD="jane.doe""@""corp-mail.test"    # public: email outside the doc domains
IP_BAD="10.20.30"".40"
HOME_BAD="/ho""me/jdoe/src"
DIGITS="4455""66778899"
AKIA="AKIA""ABCDEFGHIJKLMNOP"
NOREPLY="1+tester""@""users.noreply.github.com"

R="$T/repo"; mkdir -p "$R/docs" "$R/tools/gate"
cp "$HERE/../private-ids.sh" "$HERE/../patterns.public.txt" "$HERE/../allowlist.txt" "$R/tools/gate/"
G="$R/tools/gate/private-ids.sh"
git -C "$R" init -q -b main 2>/dev/null || git -C "$R" init -q
git -C "$R" config user.name tester; git -C "$R" config user.email "$NOREPLY"
git -C "$R" config commit.gpgsign false

cat >"$R/docs/clean.md" <<EOF
Docs values are fine: 192.0.2.10, 203.0.113.7, you@example.com, /home/u/src, 111122223333.
Loopback 127.0.0.1 and git@github.com:owner/repo.git are fine too.
A deliberate example $IP_BAD <!-- gate-allow: documented private-range example -->
EOF
cat >"$R/docs/leaky.md" <<EOF
contact $EMAIL_BAD for access
server at $IP_BAD
checkout lives in $HOME_BAD
account $DIGITS
key $AKIA
Welcome to $(printf '%s' "$PRIV" | tr a-z A-Z) platform
EOF
echo "notes" >"$R/docs/$PRIV-notes.md"
git -C "$R" add -A
git -C "$R" commit -q -m "initial" --no-verify
BASE=$(git -C "$R" rev-parse HEAD)

DENY="$T/deny.txt"; printf '# private test list\n%s\n' "$PRIV" >"$DENY"

# ---- 1. tree scan, local mode ---------------------------------------------------------
out=$(cd "$R" && HARNESS_GATE_PRIVATE="$DENY" bash "$G" 2>&1); rc=$?
expect_rc "tree scan finds hits" 1 $rc "$out"
has   "public email hit"      '^docs/leaky\.md:1: public:email: ' "$out"
has   "public ipv4 hit"       '^docs/leaky\.md:2: public:ipv4: ' "$out"
has   "public home-dir hit"   '^docs/leaky\.md:3: public:home-dir: ' "$out"
has   "public 12-digit hit"   '^docs/leaky\.md:4: public:twelve-digit: ' "$out"
has   "public aws key hit"    '^docs/leaky\.md:5: public:aws-access-key: ' "$out"
has   "private content hit (case-insensitive)" '^docs/leaky\.md:6: private#1: ' "$out"
has   "private file-name hit" ':0: private#1: .*\(file name\)' "$out"
hasnt "doc values and gate-allow line are clean" '^docs/clean\.md:' "$out"

# ---- 2. CI mode never echoes private text ----------------------------------------------
out=$(cd "$R" && GATE_PRIVATE_DENYLIST="$PRIV" bash "$G" --ci 2>&1); rc=$?
expect_rc "ci mode fails" 1 $rc "$out"
has   "ci private hit is an index" '^docs/leaky\.md:6: private#1$' "$out"
has   "ci file-name hit hides the path" '^file name #[0-9]+:0: private#1$' "$out"
hasnt "ci output never contains the private text" "$PRIV" "$out"
has   "ci still prints public text" 'public:ipv4: ' "$out"

# ---- 3. no private list → public only, says so ------------------------------------------
out=$(cd "$R" && HARNESS_GATE_PRIVATE="$T/missing" bash "$G" --ci 2>&1)
has   "missing list is announced" 'private list unavailable' "$out"
hasnt "no private hits without a list" 'private#' "$out"

# ---- 4. --files and --staged -------------------------------------------------------------
out=$(cd "$R" && HARNESS_GATE_PRIVATE="$DENY" bash "$G" --files docs/clean.md 2>&1); rc=$?
expect_rc "--files on a clean file" 0 $rc "$out"
printf 'new line %s\n' "$IP_BAD" >"$R/docs/staged.md"; git -C "$R" add docs/staged.md
out=$(cd "$R" && HARNESS_GATE_PRIVATE="$DENY" bash "$G" --staged 2>&1); rc=$?
expect_rc "--staged finds the staged hit" 1 $rc "$out"
has   "--staged reports only staged files" '^docs/staged\.md:1: public:ipv4: ' "$out"
hasnt "--staged ignores unstaged tracked files" '^docs/leaky\.md' "$out"
git -C "$R" rm -q --cached docs/staged.md; rm -f "$R/docs/staged.md"

# ---- 5. allowlist row -------------------------------------------------------------------
printf 'docs/leaky\\.md\taccount [0-9]+\tsynthetic account id in a test\n' >>"$R/tools/gate/allowlist.txt"
out=$(cd "$R" && HARNESS_GATE_PRIVATE="$DENY" bash "$G" 2>&1)
hasnt "allowlist row suppresses the hit" 'public:twelve-digit' "$out"
has   "allowlist leaves other hits" 'public:ipv4' "$out"

# ---- 6. commit range: message + author email ----------------------------------------------
echo "more" >>"$R/docs/clean.md"
git -C "$R" add -A
GIT_AUTHOR_EMAIL="dev@$PRIV.test" git -C "$R" commit -q --no-verify -m "update the $PRIV integration"
out=$(cd "$R" && HARNESS_GATE_PRIVATE="$DENY" bash "$G" --no-tree --range "$BASE..HEAD" 2>&1); rc=$?
expect_rc "range scan fails" 1 $rc "$out"
has   "private hit in commit message" '^commit:[0-9a-f]{7}:1: private#1: ' "$out"
has   "private hit in author email"   '^commit:[0-9a-f]{7}:author-email: private#1' "$out"
hasnt "committer noreply email passes" 'committer-email' "$out"
out=$(cd "$R" && GATE_PRIVATE_DENYLIST="$PRIV" bash "$G" --ci --no-tree --range "$BASE..HEAD" 2>&1)
hasnt "ci range output never contains the private text" "$PRIV" "$out"
GIT_AUTHOR_EMAIL="$EMAIL_BAD" git -C "$R" commit -q --no-verify --allow-empty -m "plain"
out=$(cd "$R" && GATE_PRIVATE_DENYLIST="$PRIV" bash "$G" --ci --no-tree --range "HEAD~1..HEAD" 2>&1)
has   "non-noreply author email flagged" '^commit:[0-9a-f]{7}:author-email: not a users\.noreply' "$out"
hasnt "ci does not echo the address" 'corp-mail' "$out"

# ---- 7. commit-msg hook mode ---------------------------------------------------------------
printf 'Add the %s adapter\n# Please enter the commit message\n' "$PRIV" >"$T/COMMIT_EDITMSG"
out=$(cd "$R" && HARNESS_GATE_PRIVATE="$DENY" bash "$G" --commit-msg-file "$T/COMMIT_EDITMSG" 2>&1); rc=$?
expect_rc "commit-msg with private text" 1 $rc "$out"
has   "commit-msg private hit" '^commit-msg:1: private#1' "$out"
printf 'Add the adapter\n' >"$T/COMMIT_EDITMSG"
out=$(cd "$R" && HARNESS_GATE_PRIVATE="$DENY" bash "$G" --commit-msg-file "$T/COMMIT_EDITMSG" 2>&1); rc=$?
expect_rc "clean commit-msg with noreply author" 0 $rc "$out"

# ---- 8. invalid private pattern refuses to run ----------------------------------------------
out=$(cd "$R" && GATE_PRIVATE_DENYLIST='bad(' bash "$G" --ci 2>&1); rc=$?
expect_rc "invalid private ERE is a setup error" 2 $rc "$out"
hasnt "setup error does not echo the pattern" 'bad\(' "$out"

echo "gate selftest: passed=$pass failed=$fail"
[ $fail -eq 0 ]
