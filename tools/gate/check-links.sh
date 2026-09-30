#!/usr/bin/env bash
# Link check for Markdown: every relative link in *.md must resolve to an existing path, and a
# `#anchor` must name a heading of the target file. External links are skipped unless
# --external (curl HEAD; failures are warnings, never errors — rate limits and outages).
#
# Usage: check-links.sh [--external] [-q] [FILE.md ...]
#   no files → every tracked + untracked-not-ignored *.md in the repository
# An anchor resolves when it equals, for some heading of the target file:
#   - the GitHub slug of the heading text (lower-case, punctuation dropped, spaces → '-'),
#   - the heading's first word, for the `### <id> — <title>` convention (ARCHITECTURE §8), or
#   - an explicit <a id="…"> / <a name="…"> / id="…" in the file.
# Links inside fenced code blocks and `inline code` are ignored.
# Exit: 0 all relative links resolve, 1 broken links, 2 usage error.
set -o pipefail
external=false; quiet=false; files=()
while [ $# -gt 0 ]; do
  case "$1" in
    --external) external=true ;;
    -q) quiet=true ;;
    -h|--help) sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) echo "check-links: unknown option $1" >&2; exit 2 ;;
    *) files[${#files[@]}]=$1 ;;
  esac
  shift
done

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || ROOT=$(cd "$HERE/../.." && pwd)
cd "$ROOT" || exit 2
TMP=$(mktemp -d "${TMPDIR:-/tmp}/links.XXXXXX") || exit 2
trap 'rm -rf "$TMP"' EXIT

if [ ${#files[@]} -eq 0 ]; then
  git ls-files -z --cached --others --exclude-standard -- '*.md' >"$TMP/list" 2>/dev/null
  while IFS= read -r -d '' f; do [ -f "$f" ] && files[${#files[@]}]=$f; done <"$TMP/list"
fi

# extract FILE → "line<TAB>target" for inline links and reference definitions
extract_links() {
  awk '
    /^[[:space:]]*(```|~~~)/ { fence = !fence; next }
    fence { next }
    {
      line = $0
      gsub(/`[^`]*`/, "", line)                      # drop inline code spans
      if (match(line, /^[[:space:]]*\[[^]]+\]:[[:space:]]*[^[:space:]]+/)) {   # [ref]: target
        def = substr(line, RSTART, RLENGTH); sub(/^[^]]*\]:[[:space:]]*/, "", def)
        print NR "\t" def
      }
      while (match(line, /\]\([^)[:space:]]+([[:space:]]+"[^"]*")?\)/)) {
        t = substr(line, RSTART + 2, RLENGTH - 3)
        sub(/[[:space:]].*$/, "", t)
        print NR "\t" t
        line = substr(line, RSTART + RLENGTH)
      }
    }' "$1"
}

# anchors FILE → one anchor candidate per line
anchors() {
  awk '
    /^[[:space:]]*(```|~~~)/ { fence = !fence; next }
    fence { next }
    /^#{1,6}[[:space:]]/ {
      h = $0; sub(/^#+[[:space:]]+/, "", h); sub(/[[:space:]]+#+[[:space:]]*$/, "", h)
      first = h; sub(/[[:space:]].*$/, "", first); gsub(/`/, "", first); print first
      s = tolower(h)
      gsub(/\[[^]]*\]\([^)]*\)/, "", s)              # rarely used, but keep slugs sane
      gsub(/[^a-z0-9 _-]/, "", s); gsub(/ /, "-", s)
      n = seen[s]++; if (n) print s "-" n; else print s
    }
    {
      l = $0
      while (match(l, /(id|name)="[^"]+"/)) {
        a = substr(l, RSTART, RLENGTH); sub(/^[^"]*"/, "", a); sub(/"$/, "", a); print a
        l = substr(l, RSTART + RLENGTH)
      }
    }' "$1"
}

broken=0; checked=0; ext_warn=0
for f in ${files[@]+"${files[@]}"}; do
  dir=$(dirname "$f")
  extract_links "$f" >"$TMP/links"
  while IFS="$(printf '\t')" read -r n t; do
    [ -n "$t" ] || continue
    t=${t#<}; t=${t%>}
    case "$t" in
      http://*|https://*)
        if $external; then
          if ! curl -sSfIL --max-time 10 -o /dev/null "$t" 2>/dev/null &&
             ! curl -sSfL --max-time 10 -r 0-0 -o /dev/null "$t" 2>/dev/null; then
            echo "$f:$n: warn: external link did not answer: $t" >&2; ext_warn=$((ext_warn + 1))
          fi
        fi
        continue ;;
      mailto:*|tel:*|ftp://*|data:*|'{{'*) continue ;;
    esac
    checked=$((checked + 1))
    path=${t%%#*}; anchor=""
    case "$t" in *'#'*) anchor=${t#*#} ;; esac
    path=${path%%\?*}
    if [ -z "$path" ]; then target=$f
    else
      case "$path" in /*) target=".$path" ;; *) target="$dir/$path" ;; esac
    fi
    if [ ! -e "$target" ]; then
      echo "$f:$n: broken link: $t"; broken=$((broken + 1)); continue
    fi
    if [ -n "$anchor" ] && [ -f "$target" ]; then
      case "$target" in *.md|*.markdown) ;; *) continue ;; esac
      if ! anchors "$target" | grep -qxF -e "$anchor"; then
        echo "$f:$n: missing anchor: $t"; broken=$((broken + 1))
      fi
    fi
  done <"$TMP/links"
done

$quiet || echo "check-links: ${#files[@]} files, $checked relative links, $broken broken$($external && echo ", $ext_warn external warnings")" >&2
[ $broken -eq 0 ]
