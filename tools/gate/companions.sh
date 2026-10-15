#!/usr/bin/env bash
# Companion-file gate: fail when a change lands without the file that must change with it.
#
#   rows       a guard section (bundles/<b>/guard.d/NN-*.sh) whose code changed needs new rows
#              in bundles/<b>/guard.d/tests.sh; the guard engine (bundles/core/guard/engine*.sh)
#              needs bundles/core/guard.d/tests.sh or bundles/core/guard/tests/. A net-new
#              `# rule: … -> D :` line needs an added `t|tc|g|r|tn D` row (ask/deny: or a `tr` row).
#   changelog  a change under bundles/ lib/harness/ providers/ schema/ bin/ profiles/ templates/,
#              bootstrap or tools/*.lock.json (tests, goldens and provider READMEs excepted) needs
#              a new line in CHANGELOG.md `## [Unreleased]`.
#
# Usage: companions.sh [--ci] --range A..B [--markers-file F] [--only rows|changelog]
#   --range A..B        compare the merge base of A and B with B (B defaults to HEAD)
#   --markers-file F    extra text searched for markers (CI passes the pull-request body)
#   --only CHECK        run one check
#   --ci                also print each hit as a GitHub Actions `::error::` annotation
# Markers (reason required), in any commit body of the range or in the markers file:
#   no-rows: <reason>        no-changelog: <reason>
# Exit: 0 clean (or no usable base: skipped), 1 hits, 2 usage error.
#
# Portability: bash 3.2, git, POSIX grep -E / sed / awk (no assoc arrays, no grep -P).
set -o pipefail

ci=false; range=""; markers_file=""; only=""
usage() { sed -n '2,23p' "$0" | sed 's/^# \{0,1\}//'; }
while [ $# -gt 0 ]; do
  case "$1" in
    --ci) ci=true ;;
    --range) shift; [ $# -gt 0 ] || { echo "companions: --range needs A..B" >&2; exit 2; }; range=$1 ;;
    --range=*) range=${1#--range=} ;;
    --markers-file) shift; [ $# -gt 0 ] || { echo "companions: --markers-file needs a path" >&2; exit 2; }
      markers_file=$1 ;;
    --markers-file=*) markers_file=${1#--markers-file=} ;;
    --only) shift; only=${1:-} ;;
    --only=*) only=${1#--only=} ;;
    -h|--help) usage; exit 0 ;;
    *) echo "companions: unknown argument: $1 (see --help)" >&2; exit 2 ;;
  esac
  shift
done
case "$only" in ''|rows|changelog) ;; *) echo "companions: --only takes rows or changelog" >&2; exit 2 ;; esac
[ -n "$range" ] || { echo "companions: --range A..B is required (see --help)" >&2; exit 2; }
case "$range" in *..*) ;; *) echo "companions: --range needs A..B, got: $range" >&2; exit 2 ;; esac
if [ -n "$markers_file" ] && [ ! -r "$markers_file" ]; then
  echo "companions: cannot read markers file $markers_file" >&2; exit 2
fi

command -v git >/dev/null 2>&1 || { echo "companions: git not found" >&2; exit 2; }
ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || { echo "companions: not in a git repository" >&2; exit 2; }
cd "$ROOT" || exit 2

# ---- range ----------------------------------------------------------------------------
a=${range%%..*}; b=${range#*..}; b=${b#.}; [ -n "$b" ] || b=HEAD
skip() { echo "companions: no usable base ($1) — skipped" >&2; exit 0; }
[ -n "$a" ] || skip "empty range start"
case "$a" in *[!0]*) ;; *) skip "all-zero range start" ;; esac
case "$b" in *[!0]*) ;; *) skip "all-zero range end" ;; esac
git cat-file -e "$a^{commit}" 2>/dev/null || skip "$a not in this clone"
git cat-file -e "$b^{commit}" 2>/dev/null || skip "$b not in this clone"
base=$(git merge-base "$a" "$b" 2>/dev/null) || skip "no merge base of $a and $b"

TMP=$(mktemp -d "${TMPDIR:-/tmp}/companions.XXXXXX") || exit 2
trap 'rm -rf "$TMP"' EXIT
HITS="$TMP/hits"; : >"$HITS"
CHANGED="$TMP/changed"
git diff --no-renames --name-only "$base" "$b" >"$CHANGED" || exit 2

# ---- markers --------------------------------------------------------------------------
MARK="$TMP/markers"
git log --format=%B "$base..$b" >"$MARK" 2>/dev/null
[ -n "$markers_file" ] && tr -d '\r' <"$markers_file" >>"$MARK"
marker() {  # $1 name → 0 when a marker with a reason is present; warns about a bare one
  if grep -qE "^[[:space:]]*$1:[[:space:]]*[^[:space:]]" "$MARK"; then return 0; fi
  if grep -qE "^[[:space:]]*$1:[[:space:]]*$" "$MARK"; then
    echo "companions: '$1:' marker without a reason is ignored — write '$1: <reason>'" >&2
  fi
  return 1
}
hit() { printf '%s\n' "$1" >>"$HITS"; }

changed() { grep -qxF -e "$1" "$CHANGED"; }
# diff body lines (+/-) of one file, without the ---/+++ headers
diff_lines() { git diff --no-renames -U0 "$base" "$b" -- "$1" | grep -E '^[-+]' | grep -vE '^(\+\+\+|---) '; }
code_changed() {  # $1 file → 0 when any added/removed line is neither blank nor a comment
  # (no `grep -q` at the end of a pipeline: an early exit SIGPIPEs the writer and pipefail fails it)
  [ -n "$(diff_lines "$1" | cut -c2- | grep -vE '^[[:space:]]*(#.*)?$')" ]
}

BYPASS="env-var prefixes, quoting and escapes, 'bash -c', absolute binary paths, chained commands"

# ---- check 1: guard rows --------------------------------------------------------------
check_rows() {
  local f bundle tests d added removed net rowre forms
  # sections and engine code
  grep -E '^bundles/[^/]+/guard\.d/[0-9]+-[^/]+\.sh$|^bundles/core/guard/engine[^/]*\.sh$' "$CHANGED" >"$TMP/guard" || true
  while IFS= read -r f; do
    case "$f" in
      bundles/core/guard/engine*)
        code_changed "$f" || continue
        changed bundles/core/guard.d/tests.sh && continue
        grep -qE '^bundles/core/guard/tests/' "$CHANGED" && continue
        hit "rows: $f: guard engine code changed without test changes — add rows to bundles/core/guard.d/tests.sh (or bundles/core/guard/tests/) covering it and its bypass forms ($BYPASS), or write 'no-rows: <reason>' in a commit body"
        ;;
      *)
        bundle=${f#bundles/}; bundle=${bundle%%/*}; tests="bundles/$bundle/guard.d/tests.sh"
        code_changed "$f" || continue
        changed "$tests" && continue
        hit "rows: $f: guard code changed but $tests has no changes — add t/tc/tr/g/r/tn rows for the new behaviour and its bypass forms ($BYPASS), or write 'no-rows: <reason>' in a commit body"
        ;;
    esac
  done <"$TMP/guard"

  # net-new rules per bundle and decision need rows of that decision
  grep -E '^bundles/[^/]+/guard\.d/[0-9]+-[^/]+\.sh$' "$CHANGED" | sed 's#^bundles/##; s#/.*##' | sort -u >"$TMP/bundles" || true
  while IFS= read -r bundle; do
    tests="bundles/$bundle/guard.d/tests.sh"
    # every changed section of the bundle, deleted ones included
    grep -E '^bundles/'"$bundle"'/guard\.d/[0-9]+-[^/]+\.sh$' "$CHANGED" | while IFS= read -r f; do
      diff_lines "$f"
    done >"$TMP/rules"
    if changed "$tests"; then diff_lines "$tests" | grep -E '^\+' | cut -c2- >"$TMP/rows"; else : >"$TMP/rows"; fi
    for d in allow ask deny pass; do
      rowre="^[[:space:]]*#[[:space:]]*rule:.*[[:space:]]->[[:space:]]+${d}[[:space:]]*:"
      added=$(grep -E '^\+' "$TMP/rules" | cut -c2- | grep -cE "$rowre" | tr -d ' ')
      removed=$(grep -E '^-' "$TMP/rules" | cut -c2- | grep -cE "$rowre" | tr -d ' ')
      net=$((added - removed))
      [ "$net" -gt 0 ] || continue
      # optional env prefixes (VAR=value) before the helper name
      if grep -qE "^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*[[:space:]]+)*(t|tc|g|r|tn)[[:space:]]+${d}([[:space:]]|$)" "$TMP/rows"; then
        continue
      fi
      if [ "$d" = ask ] || [ "$d" = deny ]; then
        grep -qE "^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*[[:space:]]+)*tr[[:space:]]+" "$TMP/rows" && continue
      fi
      if [ "$d" = ask ] || [ "$d" = deny ]; then forms="a 't $d' (tc/g/r/tn) row or a 'tr' reason row"
      else forms="a 't $d' (tc/g/r/tn) row"; fi
      hit "rows: bundles/$bundle/guard.d: $net new '-> $d' rule(s) but $tests adds no $d row — add $forms per rule, plus bypass forms ($BYPASS), or write 'no-rows: <reason>' in a commit body"
    done
  done <"$TMP/bundles"
}

# ---- check 2: CHANGELOG ---------------------------------------------------------------
TRIGGER='^(bundles/|lib/harness/|providers/|schema/|bin/|profiles/|templates/|bootstrap$|tools/[^/]+\.lock\.json$)'
EXEMPT='(^|/)tests/|(^|/)goldens?/|guard\.d/tests\.sh$|^providers/[^/]+/README\.md$'
unreleased() {  # $1 rev → entry lines of its CHANGELOG.md [Unreleased] section
  git show "$1:CHANGELOG.md" 2>/dev/null | tr -d '\r' | awk '
    /^## \[Unreleased\]/ { on = 1; next }
    /^## / { on = 0 }
    on && $0 !~ /^[[:space:]]*$/ && $0 !~ /^#/ { print }'
}
check_changelog() {
  local n list
  grep -E "$TRIGGER" "$CHANGED" | grep -vE "$EXEMPT" >"$TMP/trig" || true
  [ -s "$TMP/trig" ] || return 0
  unreleased "$base" >"$TMP/cl.base"
  unreleased "$b" >"$TMP/cl.head"
  # lines of head not in base, counted as a multiset (a duplicated bullet is still new)
  [ -n "$(awk 'FILENAME == ARGV[1] { c[$0]++; next } c[$0] > 0 { c[$0]--; next } { print }' \
          "$TMP/cl.base" "$TMP/cl.head")" ] && return 0
  n=$(wc -l <"$TMP/trig" | tr -d ' ')
  list=$(head -3 "$TMP/trig" | tr '\n' ' ' | sed 's/ $//'); [ "$n" -gt 3 ] && list="$list …"
  hit "changelog: CHANGELOG.md: $n changed file(s) need an entry under '## [Unreleased]' ($list) — add a bullet under ### Added, Changed, Fixed or Deprecated (plus a **Migration** paragraph if a config key, default or guard decision changed), or write 'no-changelog: <reason>' in a commit body"
}

ran=""
if [ "$only" != changelog ]; then
  if marker no-rows; then echo "companions: rows check waived by a 'no-rows:' marker" >&2
  else check_rows; fi
  ran="rows"
fi
if [ "$only" != rows ]; then
  if marker no-changelog; then echo "companions: changelog check waived by a 'no-changelog:' marker" >&2
  else check_changelog; fi
  ran="${ran:+$ran, }changelog"
fi

# ---- report ---------------------------------------------------------------------------
nfiles=$(wc -l <"$CHANGED" | tr -d ' ')
if [ -s "$HITS" ]; then
  cat "$HITS"
  if $ci; then sed 's/^/::error title=companion gate::/' "$HITS"; fi
  echo "companions: $(wc -l <"$HITS" | tr -d ' ') hit(s) in $nfiles changed file(s) ($(git rev-parse --short "$base")..$(git rev-parse --short "$b"))" >&2
  exit 1
fi
echo "companions: clean ($ran; $nfiles changed file(s), $(git rev-parse --short "$base")..$(git rev-parse --short "$b"))" >&2
exit 0
