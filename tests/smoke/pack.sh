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
#   7. harness pack --tag 0.0.0-smoke --self-extract: sh FILE.run --check, --list, --extract DIR
#      (every file byte-identical), harness verify FILE.run, a tampered .run fails --check
#   8. sh FILE.run --dest TMP/hub2 ... into a second temp HOME: the clone is at the tag commit,
#      origin is under $HOME/.local/share/harness/releases/0.0.0-smoke/, doctor --offline is 0
#   9. the same .run on the same --dest (the documented --offline --no-install-tools command line)
#      takes the upgrade path: harness upgrade --to the tag, --no-install-tools dropped with a note
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
git -C "$src" tag -a 0.0.0-smoke -m smoke

step "pack"
rel="$tmp/rel"
"$src/bin/harness" pack --out "$rel" > "$tmp/pack.log" 2>&1 || { cat "$tmp/pack.log"; die "pack exited non-zero"; }
b=""
for f in "$rel"/*.bundle; do [ -f "$f" ] && b=$f; done
[ -n "$b" ] || { cat "$tmp/pack.log"; die "no .bundle written"; }
[ -s "$rel/INSTALL.txt" ] || die "INSTALL.txt missing"
[ -s "$rel/SHA256SUMS" ] || die "SHA256SUMS missing"
case "$(basename "$b")" in harness-hub-0.0.0-smoke.bundle) ;; *) die "unexpected bundle name $(basename "$b")" ;; esac
grep -q "  $(basename "$b")\$" "$rel/SHA256SUMS" || die "SHA256SUMS does not list the bundle"
git bundle list-heads "$b" | grep -q ' refs/tags/0.0.0-smoke$' || die "bundle lacks the tag"

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

step "pack --self-extract"
relx="$tmp/relx"
"$src/bin/harness" pack --out "$relx" --tag 0.0.0-smoke --self-extract > "$tmp/packx.log" 2>&1 \
  || { cat "$tmp/packx.log"; die "pack --self-extract exited non-zero"; }
run="$relx/harness-hub-0.0.0-smoke.run"
[ -f "$run" ] || { cat "$tmp/packx.log"; die "no .run written"; }
grep -q "  harness-hub-0.0.0-smoke.run\$" "$relx/SHA256SUMS" || die "SHA256SUMS does not list the .run"

step ".run --check / --list / --extract"
sh "$run" --check > "$tmp/check.log" 2>&1 || { cat "$tmp/check.log"; die ".run --check exited non-zero"; }
grep -q 'payload ok' "$tmp/check.log" || { cat "$tmp/check.log"; die ".run --check did not report ok"; }
sh "$run" --list > "$tmp/list.log" 2>&1 || { cat "$tmp/list.log"; die ".run --list exited non-zero"; }
for f in harness-hub-0.0.0-smoke.bundle INSTALL.txt SHA256SUMS; do
  grep -q "^$f\$" "$tmp/list.log" || { cat "$tmp/list.log"; die ".run --list does not name $f"; }
done
sh "$run" --extract "$tmp/x" > "$tmp/extract.log" 2>&1 || { cat "$tmp/extract.log"; die ".run --extract exited non-zero"; }
cmp "$tmp/x/harness-hub-0.0.0-smoke.bundle" "$relx/harness-hub-0.0.0-smoke.bundle" || die "extracted bundle differs"
cmp "$tmp/x/INSTALL.txt" "$relx/INSTALL.txt" || die "extracted INSTALL.txt differs"
grep -v '\.run$' "$relx/SHA256SUMS" | cmp - "$tmp/x/SHA256SUMS" || die "inner SHA256SUMS is not the outer one minus the .run line"
"$src/bin/harness" verify "$run" > "$tmp/verifyx.log" 2>&1 || { cat "$tmp/verifyx.log"; die "verify FILE.run exited non-zero"; }

step "a tampered .run fails --check"
size=$(wc -c < "$run" | tr -d ' ')
head -c $((size - 512)) "$run" > "$tmp/bad.run"
if sh "$tmp/bad.run" --check > "$tmp/badrun.log" 2>&1; then die ".run --check accepted a truncated file"; fi
grep -q 'truncated' "$tmp/badrun.log" || { cat "$tmp/badrun.log"; die "truncation error does not say truncated"; }

step "install from the .run (second temp HOME)"
mkdir -p "$tmp/home2"
dest2="$tmp/hub2"
HOME="$tmp/home2" sh "$run" --dest "$dest2" --bundles core --providers claude --yes --offline --no-install-tools \
  --config "$src/tests/fixtures/harness.ci.toml" > "$tmp/runinstall.log" 2>&1 \
  || { cat "$tmp/runinstall.log"; die ".run install exited non-zero"; }
[ "$(git -C "$dest2" rev-parse HEAD)" = "$(git -C "$src" rev-parse '0.0.0-smoke^{commit}')" ] \
  || die "the .run clone is not at the tag commit"
case "$(git -C "$dest2" remote get-url origin)" in
  "$tmp/home2/.local/share/harness/releases/0.0.0-smoke/"*) ;;
  *) die "origin $(git -C "$dest2" remote get-url origin) is not under the release dir" ;;
esac
HOME="$tmp/home2" "$dest2/bin/harness" doctor --offline --config "$src/tests/fixtures/harness.ci.toml" \
  > "$tmp/doctor2.log" 2>&1 || { cat "$tmp/doctor2.log"; die "doctor --offline after the .run install exited non-zero"; }

step "the same .run on the same --dest upgrades"
# exactly the documented command (README, getting started): the install-only flag is dropped
HOME="$tmp/home2" sh "$run" --dest "$dest2" --offline --no-install-tools --yes \
  --config "$src/tests/fixtures/harness.ci.toml" \
  > "$tmp/runupgrade.log" 2>&1 || { cat "$tmp/runupgrade.log"; die ".run upgrade path exited non-zero"; }
grep -q 'upgrading ' "$tmp/runupgrade.log" || { cat "$tmp/runupgrade.log"; die ".run did not take the upgrade path"; }
grep -q 'install-only flags ignored for the upgrade: --no-install-tools$' "$tmp/runupgrade.log" \
  || { cat "$tmp/runupgrade.log"; die ".run upgrade did not report the dropped --no-install-tools"; }

echo "smoke pack: ok ($(basename "$b"), $(basename "$run"))"
