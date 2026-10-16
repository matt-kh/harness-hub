#!/usr/bin/env bash
# Self-test for tools/gate/companions.sh: builds a throw-away git repo with a guard section,
# its rows, the guard engine, an engine module, a bundle manifest, a README and a CHANGELOG,
# then asserts what the gate
# reports for each kind of change on a branch off main.
# Usage: tools/gate/tests/companions-selftest.sh [-v]
set -o pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
verbose=false; [ "${1:-}" = "-v" ] && verbose=true

T=$(mktemp -d "${TMPDIR:-/tmp}/companions-selftest.XXXXXX") || exit 2
trap 'rm -rf "$T"' EXIT
pass=0; fail=0
ok()  { pass=$((pass + 1)); $verbose && echo "ok   $1"; return 0; }
bad() { fail=$((fail + 1)); echo "FAIL $1"; [ -n "${2:-}" ] && printf '%s\n' "$2" | sed 's/^/     /'; return 0; }
expect_rc() { if [ "$2" -eq "$3" ]; then ok "$1 (rc=$3)"; else bad "$1: rc=$3, want $2" "$4"; fi; }
has()   { if grep -qE -e "$2" <<<"$3"; then ok "$1"; else bad "$1: no line matching /$2/" "$3"; fi; }
hasnt() { if grep -qE -e "$2" <<<"$3"; then bad "$1: unexpected /$2/" "$3"; else ok "$1"; fi; }

R="$T/repo"
mkdir -p "$R/tools/gate" "$R/bundles/demo/guard.d" "$R/bundles/core/guard/tests" "$R/bundles/core/guard.d" \
         "$R/lib/harness" "$R/docs"
cp "$HERE/../companions.sh" "$R/tools/gate/"
G="$R/tools/gate/companions.sh"
git -C "$R" init -q -b main 2>/dev/null || { git -C "$R" init -q && git -C "$R" checkout -q -b main; }
git -C "$R" config user.name tester; git -C "$R" config user.email "tester@example.com"
git -C "$R" config commit.gpgsign false

cat >"$R/bundles/demo/guard.d/50-demo.sh" <<'EOF'
# rule: demo push --force -> deny : force pushes rewrite history; use --force-with-lease instead
case "$cmd" in
  *"demo push --force"*) deny "force pushes rewrite history; use --force-with-lease instead" ;;
esac
EOF
cat >"$R/bundles/demo/guard.d/tests.sh" <<'EOF'
t deny 'demo push --force'
EOF
printf 'deny() { :; }\n' >"$R/bundles/core/guard/engine.sh"
printf 't allow "git status"\n' >"$R/bundles/core/guard.d/tests.sh"
printf 't() { :; }\n' >"$R/bundles/core/guard/tests/lib.sh"
printf 'VALUE = 1\n' >"$R/lib/harness/mod.py"
printf '# Docs\n' >"$R/docs/a.md"
printf '# Concepts\n' >"$R/docs/concepts.md"
printf '[bundle]\nname = "demo"\nsummary = "Demo guard"\n' >"$R/bundles/demo/bundle.toml"
printf '# demo hub\n\n| Bundle | What agents get |\n|---|---|\n| demo | Demo guard |\n' >"$R/README.md"
cat >"$R/CHANGELOG.md" <<'EOF'
# Changelog

## [Unreleased]

### Added

- an earlier entry

## [0.1.0] - 2026-01-01

### Added

- first release
EOF
git -C "$R" add -A
git -C "$R" commit -q -m "initial" --no-verify

branch() { git -C "$R" checkout -q -B "$1" main; }
commit() { git -C "$R" add -A; git -C "$R" commit -q --no-verify -m "$1"; }
run() { (cd "$R" && bash "$G" "$@" 2>&1); }
SEC="$R/bundles/demo/guard.d/50-demo.sh"
ROWS="$R/bundles/demo/guard.d/tests.sh"
NEWRULE='# rule: demo reset --hard -> deny : discards work; use git stash push -m tag instead'

# ---- 1. code edit with rows ----------------------------------------------------------------
branch c1
sed 's/force"\*)/force"*|*"demo push -f"*)/' "$SEC" >"$T/s" && cat "$T/s" >"$SEC"
printf "t deny 'demo push -f'\n" >>"$ROWS"
commit "demo: deny -f too"
out=$(run --only rows --range main..HEAD); rc=$?
expect_rc "1 edit with rows is clean" 0 $rc "$out"

# ---- 2. code edit without rows ---------------------------------------------------------------
branch c2
sed 's/force"\*)/force"*|*"demo push -f"*)/' "$SEC" >"$T/s" && cat "$T/s" >"$SEC"
commit "demo: deny -f too"
out=$(run --only rows --range main..HEAD); rc=$?
expect_rc "2 edit without rows hits" 1 $rc "$out"
has   "2 message names the rows file and the marker" \
      '^rows: bundles/demo/guard\.d/50-demo\.sh: .*bundles/demo/guard\.d/tests\.sh.*bypass.*no-rows: <reason>' "$out"

# ---- 3. comment-only edit ----------------------------------------------------------------------
branch c3
sed 's/^# rule: demo push --force -> deny : force pushes rewrite history/# rule: demo push --force -> deny : a force push rewrites shared history/' "$SEC" >"$T/s" && cat "$T/s" >"$SEC"
commit "demo: reword the rule"
out=$(run --only rows --range main..HEAD); rc=$?
expect_rc "3 comment-only (reworded rule) edit is clean" 0 $rc "$out"

# ---- 4. new deny rule: an allow row is not enough, a tr row is ----------------------------------
branch c4
{ printf '%s\n' "$NEWRULE"; cat "$SEC"; printf 'case "$cmd" in *"demo reset --hard"*) deny "discards work" ;; esac\n'; } >"$T/s"
cat "$T/s" >"$SEC"
printf "t allow 'demo reset --soft'\n" >>"$ROWS"
commit "demo: deny reset --hard"
out=$(run --only rows --range main..HEAD); rc=$?
expect_rc "4a new deny rule with only a t allow row hits" 1 $rc "$out"
has   "4a message names the decision and the tr form" "^rows: bundles/demo/guard\.d: 1 new '-> deny' rule.*'tr' reason row" "$out"
printf "tr 'stash push' 'demo reset --hard'\n" >>"$ROWS"
commit "demo: reason row"
out=$(run --only rows --range main..HEAD); rc=$?
expect_rc "4b adding a tr row clears it" 0 $rc "$out"
printf "TZ=UTC t deny 'demo reset --hard HEAD~1'\n" >"$T/row"
branch c4c
{ printf '%s\n' "$NEWRULE"; cat "$SEC"; } >"$T/s"; cat "$T/s" >"$SEC"
printf 'case "$cmd" in *"demo reset --hard"*) deny "discards work" ;; esac\n' >>"$SEC"
cat "$T/row" >>"$ROWS"
commit "demo: deny reset --hard with an env-prefixed row"
out=$(run --only rows --range main..HEAD); rc=$?
expect_rc "4c env-prefixed t deny row counts" 0 $rc "$out"

# ---- 5. no-rows marker, with and without a reason ------------------------------------------------
branch c5
printf 'case "$cmd" in *demo-noop*) : ;; esac\n' >>"$SEC"
git -C "$R" add -A; git -C "$R" commit -q --no-verify -m "demo: refactor" -m "no-rows:"
out=$(run --only rows --range main..HEAD); rc=$?
expect_rc "5a no-rows without a reason is ignored" 1 $rc "$out"
has   "5a bare marker is reported" "'no-rows:' marker without a reason is ignored" "$out"
git -C "$R" commit -q --no-verify --amend -m "demo: refactor" -m "no-rows: pure refactor, behaviour unchanged"
out=$(run --only rows --range main..HEAD); rc=$?
expect_rc "5b no-rows with a reason waives the check" 0 $rc "$out"
has   "5b waiver is announced" "rows check waived" "$out"

# ---- 6. engine edit with core test-lib change --------------------------------------------------
branch c6
printf 'ask() { :; }\n' >>"$R/bundles/core/guard/engine.sh"
printf 'tr() { :; }\n' >>"$R/bundles/core/guard/tests/lib.sh"
commit "engine: add ask"
out=$(run --only rows --range main..HEAD); rc=$?
expect_rc "6a engine edit with bundles/core/guard/tests/ change is clean" 0 $rc "$out"
branch c6b
printf 'ask() { :; }\n' >>"$R/bundles/core/guard/engine.sh"
commit "engine: add ask"
out=$(run --only rows --range main..HEAD); rc=$?
expect_rc "6b engine edit alone hits" 1 $rc "$out"
has   "6b message names the core rows file" '^rows: bundles/core/guard/engine\.sh: .*bundles/core/guard\.d/tests\.sh' "$out"

# ---- 7. lib change without CHANGELOG ----------------------------------------------------------
branch c7
printf 'VALUE = 2\n' >"$R/lib/harness/mod.py"
commit "lib: bump value"
out=$(run --only changelog --range main..HEAD); rc=$?
expect_rc "7 lib change without CHANGELOG hits" 1 $rc "$out"
has   "7 message names the file, the sections and the marker" \
      "^changelog: CHANGELOG\.md: 1 changed file\(s\).*lib/harness/mod\.py.*Added, Changed, Fixed or Deprecated.*Migration.*no-changelog: <reason>" "$out"

# ---- 8. bullet under Unreleased is clean, under 0.1.0 is not --------------------------------------
awk '{print} /^- an earlier entry$/ {print "- lib: value is 2"}' "$R/CHANGELOG.md" >"$T/c" && cat "$T/c" >"$R/CHANGELOG.md"
commit "changelog"
out=$(run --only changelog --range main..HEAD); rc=$?
expect_rc "8a bullet under [Unreleased] is clean" 0 $rc "$out"
branch c8b
printf 'VALUE = 2\n' >"$R/lib/harness/mod.py"
awk '{print} /^- first release$/ {print "- lib: value is 2"}' "$R/CHANGELOG.md" >"$T/c" && cat "$T/c" >"$R/CHANGELOG.md"
commit "lib: bump value, wrong section"
out=$(run --only changelog --range main..HEAD); rc=$?
expect_rc "8b bullet under [0.1.0] hits" 1 $rc "$out"

# ---- 9. docs-only and test-only changes need nothing ------------------------------------------
branch c9
printf 'more\n' >>"$R/docs/a.md"
printf 't() { return 0; }\n' >"$R/bundles/core/guard/tests/lib.sh"
commit "docs"
out=$(run --range main..HEAD); rc=$?
expect_rc "9 docs/tests-only change is clean" 0 $rc "$out"

# ---- 10. no-changelog marker from the markers file (PR body) ----------------------------------------
branch c10
printf 'VALUE = 3\n' >"$R/lib/harness/mod.py"
commit "lib: bump value"
printf 'Summary\r\n\r\nno-changelog: internal refactor, no user-visible change\r\n' >"$T/body.txt"
out=$(run --range main..HEAD --markers-file "$T/body.txt"); rc=$?
expect_rc "10 no-changelog in the markers file (CRLF) waives" 0 $rc "$out"

# ---- 11. unusable bases skip ----------------------------------------------------------------------
out=$(run --range 0000000000000000000000000000000000000000..HEAD); rc=$?
expect_rc "11a all-zero base skips" 0 $rc "$out"
has   "11a skip is announced" 'no usable base .* skipped' "$out"
out=$(run --range deadbeefdeadbeefdeadbeefdeadbeefdeadbeef..HEAD); rc=$?
expect_rc "11b base not in the clone skips" 0 $rc "$out"

# ---- 12. --only rows ignores the CHANGELOG, --ci annotates ---------------------------------------------
git -C "$R" checkout -q c10   # lib change, no CHANGELOG, marker only in the body file
out=$(run --only rows --range main..HEAD); rc=$?
expect_rc "12a --only rows skips the CHANGELOG check" 0 $rc "$out"
out=$(run --ci --range main..HEAD); rc=$?
expect_rc "12b --ci still fails" 1 $rc "$out"
has   "12b --ci prints an annotation" '^::error title=companion gate::changelog: ' "$out"

# ---- 13. usage errors -----------------------------------------------------------------------------
out=$(run --bogus --range main..HEAD); rc=$?
expect_rc "13a unknown flag" 2 $rc "$out"
out=$(run --only everything --range main..HEAD); rc=$?
expect_rc "13b bad --only value" 2 $rc "$out"
out=$(run); rc=$?
expect_rc "13c --range is required" 2 $rc "$out"

# ---- 14. README companion -------------------------------------------------------------------------
TOML="$R/bundles/demo/bundle.toml"
branch c14
sed 's/Demo guard/Demo guard for force pushes/' "$TOML" >"$T/b" && cat "$T/b" >"$TOML"
commit "demo: sharper summary"
out=$(run --only readme --range main..HEAD); rc=$?
expect_rc "14a manifest summary change without README hits" 1 $rc "$out"
has   "14a message names the file, the product page, docs generate and the marker" \
      '^readme: README\.md: 1 changed path\(s\).*bundles/demo/bundle\.toml.*product page.*bin/harness docs generate.*no-readme: <reason>' "$out"
hasnt "14d --only readme runs no CHANGELOG check" '^changelog: ' "$out"
out=$(run --only rows --range main..HEAD); rc=$?
expect_rc "14d --only rows skips the README check" 0 $rc "$out"
sed 's/| Demo guard |/| Demo guard for force pushes |/' "$R/README.md" >"$T/r" && cat "$T/r" >"$R/README.md"
commit "readme: regenerate"
out=$(run --only readme --range main..HEAD); rc=$?
expect_rc "14b same change with README is clean" 0 $rc "$out"
branch c14c
sed 's/Demo guard/Demo guard for force pushes/' "$TOML" >"$T/b" && cat "$T/b" >"$TOML"
git -C "$R" add -A; git -C "$R" commit -q --no-verify -m "demo: sharper summary" -m "no-readme: README does not show this bundle"
out=$(run --only readme --range main..HEAD); rc=$?
expect_rc "14c no-readme with a reason waives the check" 0 $rc "$out"
has   "14c waiver is announced" "readme check waived" "$out"
branch c14e
printf 'more\n' >>"$R/docs/concepts.md"
commit "docs: concepts"
out=$(run --range main..HEAD); rc=$?
expect_rc "14e unrelated docs page needs no README change" 0 $rc "$out"
hasnt "14e no readme hit" '^readme: ' "$out"
branch c14f
mkdir -p "$R/providers/newp"; printf 'notes\n' >"$R/providers/newp/notes.txt"
commit "providers: new adapter directory"
out=$(run --only readme --range main..HEAD); rc=$?
expect_rc "14f an added provider directory hits" 1 $rc "$out"
has   "14f message marks the directory as added" '^readme: .*providers/newp/ \(added\)' "$out"

echo "companions selftest: passed=$pass failed=$fail"
[ $fail -eq 0 ]
