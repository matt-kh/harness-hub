#!/usr/bin/env bash
# build.sh — concatenate the guard into one script.
#
# Usage: build.sh OUT [BUNDLE_DIR ...]
#   OUT         target path (parent dirs are created; written atomically via a temp file + mv)
#   BUNDLE_DIR  bundle directories whose guard.d/ sections to include. Default: every
#               directory under <hub>/bundles/ (optionally filtered by HARNESS_GUARD_BUNDLES).
#   HARNESS_GUARD_BUNDLES=a,b  restrict the default set to these bundle names (core is always kept).
#
# ORDERING CONTRACT (the engine's renderer implements the same rule; keep them identical):
#   1. bundles/core/guard/engine.sh
#   2. every <bundle>/guard.d/NN-*.sh of the selected bundles, sorted by FILE BASENAME with
#      LC_ALL=C byte order across all bundles (ties broken by bundle directory name).
#      Numeric prefixes are therefore global: 10 k8s, 20 credentials, 25 k8s rules, 30 git,
#      40/41 closing keywords, 50 gitlab, 60 github, 70 jira, 80 gdoc, 90+ private bundles.
#   3. bundles/core/guard/engine-flush.sh
# Only files matching guard.d/[0-9][0-9]-*.sh are sections; guard.d/tests.sh is test data.
# The order is load-bearing: allow/ask/deny exit immediately, so an earlier section wins.
set -eu
[ $# -ge 1 ] || { echo "usage: build.sh OUT [BUNDLE_DIR ...]" >&2; exit 2; }
out=$1; shift
here=$(cd "$(dirname "$0")" && pwd)          # bundles/core/guard
core=$(cd "$here/.." && pwd)                 # bundles/core
hub_bundles=$(cd "$core/.." && pwd)          # bundles/

if [ $# -eq 0 ]; then
  for d in "$hub_bundles"/*/; do
    d=${d%/}; n=$(basename "$d")
    if [ -n "${HARNESS_GUARD_BUNDLES:-}" ] && [ "$n" != core ]; then
      case ",$HARNESS_GUARD_BUNDLES," in *",$n,"*) ;; *) continue ;; esac
    fi
    set -- "$@" "$d"
  done
fi

list=$(
  for d in "$@"; do
    [ -d "$d/guard.d" ] || continue
    for f in "$d"/guard.d/[0-9][0-9]-*.sh; do
      [ -f "$f" ] || continue
      printf '%s\t%s\t%s\n' "$(basename "$f")" "$(basename "$d")" "$f"
    done
  done | LC_ALL=C sort -t "$(printf '\t')" -k1,1 -k2,2
)

mkdir -p "$(dirname "$out")"
tmp="$out.tmp.$$"
{
  cat "$core/guard/engine.sh"
  printf '%s\n' "$list" | while IFS="$(printf '\t')" read -r base bundle path; do
    [ -n "$base" ] || continue
    printf '\n# ==== section %s (bundle %s) ====\n' "$base" "$bundle"
    cat "$path"
  done
  printf '\n# ==== flush ====\n'
  cat "$core/guard/engine-flush.sh"
} > "$tmp"
chmod 0755 "$tmp"
mv "$tmp" "$out"
