#!/usr/bin/env bash
# Distribution smoke test: pack the hub, verify the bundle, install from it, doctor it.
#
#   1. snapshot the working tree (tracked + untracked, not ignored) into a temp git repo
#   2. harness pack --out REL                 (bundle + INSTALL.txt + SHA256SUMS)
#   3. harness verify REL/<bundle>            (git bundle verify + SHA256SUMS)
#   4. pack refuses a dirty tree
#   5. bootstrap --from <bundle> --dest TMP/hub --bundles core --providers claude --yes
#      --offline --config <snapshot>/tests/fixtures/harness.ci.toml   (temp HOME, fakes on PATH)
#   6. the installed hub's doctor --offline exits 0
# Nothing outside the temp directory is written (HARNESS_BUILD_DIR keeps build/ products there).
set -eu
here=$(cd "$(dirname "$0")/../.." && pwd)
tmpdir=${TMPDIR:-/tmp}
tmp=$(mktemp -d "${tmpdir%/}/harness-pack.XXXXXX")
trap 'rm -rf "$tmp"' EXIT
tmp=$(cd "$tmp" && pwd -P)
mkdir -p "$tmp/home"
HOME="$tmp/home"; export HOME
HARNESS_BUILD_DIR="$tmp/build"; export HARNESS_BUILD_DIR
unset HARNESS_HOME HARNESS_CONFIG XDG_STATE_HOME XDG_DATA_HOME XDG_CONFIG_HOME 2>/dev/null || true
export PATH="$here/tests/fakes/bin:$PATH"
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 GIT_TERMINAL_PROMPT=0
export GIT_AUTHOR_NAME=smoke GIT_AUTHOR_EMAIL=smoke@example.com GIT_COMMITTER_NAME=smoke GIT_COMMITTER_EMAIL=smoke@example.com
die() { echo "FAIL: $*" >&2; exit 1; }
step() { echo "== $*"; }

step "snapshot the working tree"
src="$tmp/src"
mkdir -p "$src"
(cd "$here" && git ls-files -z --cached --others --exclude-standard) > "$tmp/files"
(cd "$here" && while IFS= read -r -d '' f; do
  [ -e "$f" ] || [ -L "$f" ] || continue          # deleted but not yet committed
  case "$f" in local/*) continue ;; esac
  mkdir -p "$src/$(dirname "$f")"
  cp -P "$f" "$src/$f"
done) < "$tmp/files"
git -C "$src" init -q
git -C "$src" add -A
git -C "$src" commit -q -m "smoke snapshot"
git -C "$src" tag -a v0.0.0-smoke -m smoke

step "pack"
rel="$tmp/rel"
"$src/bin/harness" pack --out "$rel" > "$tmp/pack.log" 2>&1 || { cat "$tmp/pack.log"; die "pack exited non-zero"; }
b=""
for f in "$rel"/*.bundle; do [ -f "$f" ] && b=$f; done
[ -n "$b" ] || { cat "$tmp/pack.log"; die "no .bundle written"; }
[ -s "$rel/INSTALL.txt" ] || die "INSTALL.txt missing"
[ -s "$rel/SHA256SUMS" ] || die "SHA256SUMS missing"
case "$(basename "$b")" in harness-hub-v0.0.0-smoke.bundle) ;; *) die "unexpected bundle name $(basename "$b")" ;; esac
grep -q "  $(basename "$b")\$" "$rel/SHA256SUMS" || die "SHA256SUMS does not list the bundle"
git bundle list-heads "$b" | grep -q ' refs/tags/v0.0.0-smoke$' || die "bundle lacks the tag"

step "verify"
"$src/bin/harness" verify "$b" > "$tmp/verify.log" 2>&1 || { cat "$tmp/verify.log"; die "verify exited non-zero"; }
grep -q '^verify: ok' "$tmp/verify.log" || { cat "$tmp/verify.log"; die "verify did not report ok"; }
grep -q '^sha256  ' "$tmp/verify.log" || { cat "$tmp/verify.log"; die "verify did not check SHA256SUMS"; }

step "a tampered SHA256SUMS fails verify"
cp -R "$rel" "$tmp/bad"
printf '%064d  %s\n' 0 "$(basename "$b")" > "$tmp/bad/SHA256SUMS"
if "$src/bin/harness" verify "$tmp/bad/$(basename "$b")" > "$tmp/bad.log" 2>&1; then
  cat "$tmp/bad.log"; die "verify accepted a wrong sha256"
fi

step "a dirty tree is refused"
echo dirty > "$src/dirty.txt"
if "$src/bin/harness" pack --out "$tmp/rel-dirty" > "$tmp/dirty.log" 2>&1; then
  die "pack accepted a dirty tree"
fi
grep -q 'dirty' "$tmp/dirty.log" || { cat "$tmp/dirty.log"; die "dirty refusal does not say why"; }
rm -f "$src/dirty.txt"

step "bootstrap --from the bundle"
dest="$tmp/hub"
"$src/bootstrap" --from "$b" --dest "$dest" --bundles core --providers claude --yes --offline \
  --config "$src/tests/fixtures/harness.ci.toml" > "$tmp/bootstrap.log" 2>&1 \
  || { cat "$tmp/bootstrap.log"; die "bootstrap --from exited non-zero"; }
[ -x "$dest/bin/harness" ] || die "the clone has no bin/harness"
[ "$(git -C "$dest" rev-parse HEAD)" = "$(git -C "$src" rev-parse HEAD)" ] || die "the clone is not at the packed commit"
[ "$(git -C "$dest" remote get-url origin)" = "$b" ] || die "origin is not the bundle file"
[ -x "$HOME/.claude/hooks/guard-bash.sh" ] || { cat "$tmp/bootstrap.log"; die "bootstrap did not render the guard"; }
grep -q "$dest/" "$HOME/.claude/settings.json" "$HOME/.claude/hooks/guard-bash.sh" 2>/dev/null \
  || [ "$(readlink "$HOME/.local/bin/harness" 2>/dev/null)" != "" ] \
  || echo "note: no rendered path names the installed hub (fine for the core bundle)"

step "doctor --offline in the installed hub"
"$dest/bin/harness" doctor --offline --config "$src/tests/fixtures/harness.ci.toml" > "$tmp/doctor.log" 2>&1 \
  || { cat "$tmp/doctor.log"; die "doctor --offline exited non-zero"; }

echo "smoke pack: ok ($(basename "$b"))"
