#!/usr/bin/env bash
# install/gh.sh — install the GitHub CLI into $HARNESS_BIN_DIR (default ~/.local/bin), no sudo.
# Fallback used by `harness install gh` when tools/gh.lock.json is absent; the lock file path
# (pinned version + sha256 per os/arch) is preferred.
#
# Usage: gh.sh [--from ARCHIVE [--sha256 HEX]]
#   default        resolve the latest release (or $GH_VERSION), download the archive and the
#                  release checksums file, verify sha256, install bin/gh
#   --from FILE    air-gapped: install from a local gh_<ver>_<os>_<arch>.{tar.gz,zip}; the sha256
#                  comes from --sha256, $GH_SHA256, or a gh_<ver>_checksums.txt next to FILE
# Honours HTTPS_PROXY / NO_PROXY through curl. Linux (amd64/arm64) and macOS (amd64/arm64).
set -euo pipefail

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
compat="${HARNESS_HOME:-$here/../../..}/bundles/core/lib/compat.sh"
[ -r "$compat" ] || compat="$here/../../core/lib/compat.sh"
# shellcheck source=../../core/lib/compat.sh
. "$compat"

BIN_DIR="${HARNESS_BIN_DIR:-$HOME/.local/bin}"
from=""; want_sha="${GH_SHA256:-}"
while [ $# -gt 0 ]; do
  case "$1" in
    --from) from=${2:?--from needs a file}; shift 2 ;;
    --sha256) want_sha=${2:?--sha256 needs a hex digest}; shift 2 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "gh.sh: unknown argument $1" >&2; exit 2 ;;
  esac
done

case "$(uname -m)" in
  x86_64|amd64) arch=amd64 ;;
  aarch64|arm64) arch=arm64 ;;
  *) echo "gh.sh: unsupported architecture $(uname -m)" >&2; exit 1 ;;
esac
case "$(uname -s)" in
  Linux)  os=linux; ext=tar.gz ;;
  Darwin) os=macOS; ext=zip ;;
  *) echo "gh.sh: unsupported OS $(uname -s)" >&2; exit 1 ;;
esac

tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT

if [ -n "$from" ]; then
  [ -f "$from" ] || { echo "gh.sh: $from not found" >&2; exit 1; }
  pkg=$(basename "$from")
  ver=$(printf '%s' "$pkg" | sed -nE 's/^gh_([0-9]+\.[0-9]+\.[0-9]+)_.*/\1/p')
  [ -n "$ver" ] || { echo "gh.sh: cannot read the version from $pkg (expected gh_<ver>_<os>_<arch>.<ext>)" >&2; exit 1; }
  case "$pkg" in *.zip) ext=zip ;; *.tar.gz) ext=tar.gz ;; esac
  if [ -z "$want_sha" ] && [ -f "$(dirname "$from")/gh_${ver}_checksums.txt" ]; then
    want_sha=$(awk -v f="$pkg" '$2 == f {print $1}' "$(dirname "$from")/gh_${ver}_checksums.txt")
  fi
  [ -n "$want_sha" ] || { echo "gh.sh: no sha256 for $pkg — pass --sha256 or put gh_${ver}_checksums.txt next to it" >&2; exit 1; }
  cp "$from" "$tmp/$pkg"
else
  command -v curl >/dev/null 2>&1 || { echo "gh.sh: curl is required" >&2; exit 1; }
  ver="${GH_VERSION:-}"
  if [ -z "$ver" ]; then
    loc=$(curl -sSI --max-time 30 https://github.com/cli/cli/releases/latest | tr -d '\r' \
          | awk 'tolower($1)=="location:"{print $2}' | tail -1)
    ver=${loc##*/tag/v}
  fi
  if ! printf '%s' "$ver" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$'; then
    ver=$(curl -sSf --max-time 30 https://api.github.com/repos/cli/cli/releases/latest \
          | jq -r '.tag_name // empty' | sed 's/^v//')
  fi
  printf '%s' "$ver" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$' || { echo "gh.sh: could not resolve the gh version" >&2; exit 1; }
  pkg="gh_${ver}_${os}_${arch}.${ext}"
  base="https://github.com/cli/cli/releases/download/v${ver}"
  echo "fetch $pkg"
  curl -sSfL --max-time 300 -o "$tmp/$pkg" "$base/$pkg" || { echo "gh.sh: download failed: $base/$pkg" >&2; exit 1; }
  curl -sSfL --max-time 60 -o "$tmp/checksums.txt" "$base/gh_${ver}_checksums.txt" \
    || { echo "gh.sh: checksums download failed" >&2; exit 1; }
  want_sha=$(awk -v f="$pkg" '$2 == f {print $1}' "$tmp/checksums.txt")
  [ -n "$want_sha" ] || { echo "gh.sh: $pkg is not listed in the release checksums" >&2; exit 1; }
fi

got_sha=$(hn_sha256 "$tmp/$pkg")
[ "$got_sha" = "$want_sha" ] || { echo "gh.sh: sha256 mismatch for $pkg — not installing" >&2; exit 1; }
echo "ok    sha256 verified"

stem=${pkg%.tar.gz}; stem=${stem%.zip}
case "$pkg" in
  *.tar.gz) tar -xzf "$tmp/$pkg" -C "$tmp" "$stem/bin/gh" ;;
  *.zip)    (cd "$tmp" && unzip -q "$pkg" "$stem/bin/gh") ;;
esac || { echo "gh.sh: extract failed" >&2; exit 1; }
mkdir -p "$BIN_DIR"
install -m 0755 "$tmp/$stem/bin/gh" "$BIN_DIR/gh.tmp.$$" && mv "$BIN_DIR/gh.tmp.$$" "$BIN_DIR/gh"
echo "installed $BIN_DIR/gh"
"$BIN_DIR/gh" --version | head -1
GH_PROMPT_DISABLED=1 hn_timeout 15 "$BIN_DIR/gh" auth status >/dev/null 2>&1 \
  || echo "next: gh auth login --git-protocol ssh --web   (interactive; inside Claude Code type: ! gh auth login --git-protocol ssh --web)"
