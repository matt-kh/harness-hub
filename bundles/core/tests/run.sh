#!/usr/bin/env bash
# Bundle `core` tests: the full guard suite (every bundle's rows), drift of inlined helper
# copies, `bash -n` of every shell file in bundles/, the compat and config helpers, and build.sh
# determinism. Exit 1 on any failure.
set -uo pipefail
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
core=$(cd "$here/.." && pwd)
bundles=$(cd "$core/.." && pwd)
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
fail=0; cases=0
chk() { cases=$((cases + 1)); if [ "$1" = 0 ]; then echo "PASS $2"; else echo "FAIL $2"; fail=1; fi; }

# 1. guard rows (all bundles, built into a private temp dir)
GUARD_BASH="$tmp/hooks/guard-bash.sh"
bash "$core/guard/build.sh" "$GUARD_BASH"; chk $? "build.sh builds the guard"
GUARD_BASH="$GUARD_BASH" bash "$core/guard/tests/run.sh" > "$tmp/guard.log" 2>&1; rc=$?
tail -1 "$tmp/guard.log"
[ "$rc" = 0 ]; chk $? "guard rows ($(tail -1 "$tmp/guard.log"))"
[ "$rc" = 0 ] || grep -A1 '^FAIL' "$tmp/guard.log" | head -40

# 2. build determinism + ordering contract
bash "$core/guard/build.sh" "$tmp/b2.sh"
cmp -s "$GUARD_BASH" "$tmp/b2.sh"; chk $? "build.sh output is deterministic"
order=$(grep -o '^# ==== section [0-9][0-9]-[^ ]*' "$GUARD_BASH" | awk '{print $4}')
[ "$order" = "$(printf '%s\n' "$order" | LC_ALL=C sort)" ]; chk $? "sections are concatenated in basename order"
bash -n "$GUARD_BASH"; chk $? "concatenated guard parses"
HARNESS_GUARD_BUNDLES=none bash "$core/guard/build.sh" "$tmp/core-only.sh"
[ "$(grep -c '^# ==== section' "$tmp/core-only.sh")" = 2 ]; chk $? "HARNESS_GUARD_BUNDLES=none keeps only core's sections"

# 3. inlined helper copies match their canonical source
python3 "$core/lib/sync_inline.py" --check "$bundles"; chk $? "inlined hn_timeout / harness_config / hcfg copies are in sync"

# 4. every shell file parses (under /bin/bash too, which is 3.2 on macOS)
bad=""
while IFS= read -r f; do
  bash -n "$f" 2>"$tmp/n.err" || bad="$bad $f"
  if [ -x /bin/bash ] && [ "$(/bin/bash -c 'echo ${BASH_VERSINFO[0]}')" != "$(bash -c 'echo ${BASH_VERSINFO[0]}')" ]; then
    /bin/bash -n "$f" 2>>"$tmp/n.err" || bad="$bad $f(/bin/bash)"
  fi
done < <(find "$bundles" -type f \( -name '*.sh' \) -not -path '*/golden/*' | sort)
[ -z "$bad" ]; chk $? "bash -n on every *.sh${bad:+ —$bad}"

# 5. compat helpers
# shellcheck source=../lib/compat.sh
. "$core/lib/compat.sh"
hn_timeout 1 sleep 5; [ $? = 124 ]; chk $? "hn_timeout returns 124 on timeout"
hn_timeout 5 true; chk $? "hn_timeout passes the exit code through"
mkdir -p "$tmp/nopath"; ln -s "$(command -v python3)" "$tmp/nopath/python3"; ln -s "$(command -v sleep)" "$tmp/nopath/sleep"
( PATH="$tmp/nopath"; hn_timeout 1 sleep 5 ); [ $? = 124 ]; chk $? "hn_timeout python fallback (no timeout/gtimeout on PATH)"
printf 'abc' > "$tmp/abc"
[ "$(hn_sha256 "$tmp/abc")" = ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad ]; chk $? "hn_sha256"
ln -s "$tmp/abc" "$tmp/link"
[ "$(hn_realpath "$tmp/link")" = "$(cd "$tmp" && pwd -P)/abc" ]; chk $? "hn_realpath resolves symlinks"

# 6. config helpers
printf '{"a":{"b":"x","n":2,"t":{"k":"v"}}}' > "$tmp/c.json"
[ "$(HARNESS_CONFIG_JSON="$tmp/c.json" python3 "$core/lib/harness_config.py" get a.b)" = x ]; chk $? "harness_config.py get string"
[ "$(HARNESS_CONFIG_JSON="$tmp/c.json" python3 "$core/lib/harness_config.py" get a.t)" = '{"k": "v"}' ]; chk $? "harness_config.py get table as JSON"
[ "$(HARNESS_CONFIG_JSON=/nonexistent python3 "$core/lib/harness_config.py" get a.b dflt)" = dflt ]; chk $? "harness_config.py default when the file is missing"
# shellcheck source=../lib/harness_config.sh
. "$core/lib/harness_config.sh"
[ "$(HARNESS_CONFIG_JSON="$tmp/c.json" hcfg a.n)" = 2 ]; chk $? "hcfg number"
[ "$(HARNESS_CONFIG_JSON="$tmp/c.json" hcfg a.missing d)" = d ]; chk $? "hcfg default"
[ -z "$(HARNESS_CONFIG_JSON=/nonexistent hcfg a.b)" ]; chk $? "hcfg prints nothing without file or default"

echo "----"
if [ $fail -eq 0 ]; then echo "all core tests passed ($cases cases)"; else echo "core tests FAILED"; fi
exit $fail
