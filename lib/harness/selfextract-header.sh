#!/bin/sh
# harness-hub @VERSION@ self-extracting release envelope, written by `harness pack --self-extract`.
#
# This file is a POSIX sh header followed by an uncompressed tar of the release directory
# (the git bundle, INSTALL.txt, SHA256SUMS and any tools/ archives). The git bundle inside is
# the release; this envelope only carries it as one file. Template: lib/harness/selfextract-header.sh
#
#   sh THIS.run --check             verify the payload (size, sha256) and every SHA256SUMS line
#   sh THIS.run --list              list the payload
#   sh THIS.run --extract DIR       unpack the release directory into DIR (then follow INSTALL.txt)
#   sh THIS.run [--dest DIR] [--release-dir DIR] [--] [bootstrap flags...]
#                                   install: unpack into the release dir, git clone the bundle
#                                   into DIR (default ~/harness-hub), run its ./bootstrap; when
#                                   DIR is already a hub clone: fetch the tags, point origin at
#                                   the bundle and run `harness upgrade` with the remaining flags
#
# Needs: sh, tail, tar, wc and one of sha256sum / shasum / python3; git and bash to install.
set -eu

HN_VERSION='@VERSION@'
HN_TAG='@TAG@'
HN_BUNDLE='@BUNDLE@'
HN_PAYLOAD_SHA256='@PAYLOAD_SHA256@'
HN_PAYLOAD_SIZE='@PAYLOAD_SIZE@'
HN_SKIP='@SKIP@'

die() {
  printf 'harness-hub .run: %s\n' "$*" >&2
  exit 1
}

usage() {
  sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'
}

# Twin of hn_sha256 in bundles/core/lib/compat.sh; tests/unit/test_pack.py keeps them identical.
hn_sha256() {  # FILE
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | awk '{print $1}'
  else python3 -c 'import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$1"
  fi
}

abspath() {  # PATH (need not exist)
  case $1 in
    /*) printf '%s\n' "$1" ;;
    *) printf '%s/%s\n' "$(pwd)" "$1" ;;
  esac
}

mode=install
dest=
reldir=
xdir=
while [ $# -gt 0 ]; do
  case $1 in
    -h|--help) usage; exit 0 ;;
    --check) mode=check; shift ;;
    --list) mode=list; shift ;;
    --extract)
      [ $# -ge 2 ] || die "--extract needs a directory: sh $0 --extract DIR"
      mode=extract; xdir=$2; shift 2 ;;
    --extract=*) mode=extract; xdir=${1#--extract=}; shift ;;
    --dest)
      [ $# -ge 2 ] || die "--dest needs a directory: sh $0 --dest DIR"
      dest=$2; shift 2 ;;
    --dest=*) dest=${1#--dest=}; shift ;;
    --release-dir)
      [ $# -ge 2 ] || die "--release-dir needs a directory: sh $0 --release-dir DIR"
      reldir=$2; shift 2 ;;
    --release-dir=*) reldir=${1#--release-dir=}; shift ;;
    --) shift; break ;;
    *) break ;;  # the first unknown word and everything after it go to bootstrap / upgrade
  esac
done

[ -f "$0" ] || die "cannot read the envelope from \$0 ($0); save the file and run: sh FILE.run"
case $HN_SKIP in
  ''|*[!0-9]*) die "corrupt header (skip count '$HN_SKIP'); re-download the .run and check it against SHA256SUMS" ;;
esac

tmp=$(mktemp -d "${TMPDIR:-/tmp}/harness-run.XXXXXX") || die "mktemp failed; set TMPDIR to a writable directory"
trap 'rm -rf "$tmp"' EXIT
trap 'exit 1' HUP INT TERM

# payload -> $tmp/payload.tar, size and sha256 checked against the header
tail -n +"$HN_SKIP" "$0" > "$tmp/payload.tar" || die "cannot read the payload from $0"
size=$(wc -c < "$tmp/payload.tar" | tr -d ' ')
if [ "$size" != "$HN_PAYLOAD_SIZE" ]; then
  if [ "$size" -lt "$HN_PAYLOAD_SIZE" ]; then
    die "payload truncated ($size of $HN_PAYLOAD_SIZE bytes); re-download the .run and check it against SHA256SUMS"
  fi
  die "payload is $size bytes, the header says $HN_PAYLOAD_SIZE; re-download the .run and check it against SHA256SUMS"
fi
sum=$(hn_sha256 "$tmp/payload.tar")
[ "$sum" = "$HN_PAYLOAD_SHA256" ] \
  || die "payload sha256 mismatch (got $sum, want $HN_PAYLOAD_SHA256); re-download the .run and check it against SHA256SUMS"

if [ "$mode" = list ]; then
  tar -tf "$tmp/payload.tar"
  exit 0
fi

# unpack and check every SHA256SUMS line of the release directory
mkdir "$tmp/x"
tar -xf "$tmp/payload.tar" -C "$tmp/x" || die "tar could not unpack the payload; use --extract DIR on another machine and copy the files"
[ -f "$tmp/x/SHA256SUMS" ] || die "the payload has no SHA256SUMS; re-download the .run"
n=0
while read -r want name; do
  [ -n "$want" ] || continue
  name=${name#\*}
  [ -f "$tmp/x/$name" ] || die "$name is listed in SHA256SUMS but missing from the payload; re-download the .run"
  got=$(hn_sha256 "$tmp/x/$name")
  [ "$got" = "$want" ] || die "sha256 mismatch for $name; re-download the .run and check it against SHA256SUMS"
  n=$((n + 1))
done < "$tmp/x/SHA256SUMS"
[ -f "$tmp/x/$HN_BUNDLE" ] || die "the payload lacks $HN_BUNDLE; re-download the .run"

if [ "$mode" = check ]; then
  echo "harness-hub $HN_VERSION: payload ok ($size bytes, sha256 $sum), $n file(s) match SHA256SUMS"
  exit 0
fi

if [ "$mode" = extract ]; then
  mkdir -p "$xdir" || die "cannot create $xdir; pick a writable directory with --extract DIR"
  tar -xf "$tmp/payload.tar" -C "$xdir" || die "tar could not unpack into $xdir; pick another directory"
  echo "extracted harness-hub $HN_VERSION into $xdir; next: follow $xdir/INSTALL.txt"
  exit 0
fi

# install / upgrade
command -v git >/dev/null 2>&1 \
  || die "git is not installed; install git (and bash, python3 >= 3.9, jq), or use --extract DIR and follow INSTALL.txt"
[ -n "${HOME:-}" ] || [ -n "$dest" ] || die "HOME is not set; pass --dest DIR and --release-dir DIR"
reldir=$(abspath "${reldir:-${XDG_DATA_HOME:-$HOME/.local/share}/harness/releases/$HN_VERSION}")
dest=${dest:-$HOME/harness-hub}
mkdir -p "$reldir" || die "cannot create $reldir; pass --release-dir DIR (a writable directory)"
tar -xf "$tmp/payload.tar" -C "$reldir" || die "tar could not unpack into $reldir; pass --release-dir DIR"
bundle=$reldir/$HN_BUNDLE
echo "release files: $reldir"
unset HARNESS_HOME

if [ -d "$dest/.git" ]; then
  # upgrade an existing clone from this bundle: new tags, origin -> the bundle, harness upgrade
  git -C "$dest" fetch -q "$bundle" 'refs/tags/*:refs/tags/*' \
    || die "git fetch from $bundle into $dest failed; fix the clone (git -C $dest status) or pass --dest DIR for a fresh install"
  if git -C "$dest" remote get-url origin >/dev/null 2>&1; then
    git -C "$dest" remote set-url origin "$bundle"
  else
    git -C "$dest" remote add origin "$bundle"
  fi
  [ -f "$dest/bin/harness" ] || die "$dest is a git clone but not a harness hub; pass --dest DIR"
  echo "upgrading $dest to ${HN_TAG:-the newest release tag} (origin is now $bundle)"
  rm -rf "$tmp"
  trap - EXIT
  exec bash "$dest/bin/harness" upgrade --to "${HN_TAG:-latest}" "$@"
fi

if [ -e "$dest" ] && { [ ! -d "$dest" ] || [ -n "$(ls -A "$dest" 2>/dev/null)" ]; }; then
  die "$dest exists and is not empty (and is not a hub clone); pass --dest DIR (a new or empty directory) or remove it"
fi
if [ -n "$HN_TAG" ]; then
  git -c advice.detachedHead=false clone -q -b "$HN_TAG" "$bundle" "$dest" \
    || die "git clone of $bundle failed; check the output above, or use --extract DIR and follow INSTALL.txt"
else
  git -c advice.detachedHead=false clone -q "$bundle" "$dest" \
    || die "git clone of $bundle failed; check the output above, or use --extract DIR and follow INSTALL.txt"
fi
[ -f "$dest/bootstrap" ] || die "$dest has no bootstrap script; is this a harness-hub release? Use --extract DIR to inspect it"
echo "cloned harness-hub $HN_VERSION into $dest (origin $bundle)"
rm -rf "$tmp"
trap - EXIT
# the marker line below is never executed: exec replaces this shell
# shellcheck disable=SC2093
exec bash "$dest/bootstrap" "$@"
__PAYLOAD_BELOW__
