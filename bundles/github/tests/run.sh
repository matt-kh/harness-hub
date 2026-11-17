#!/usr/bin/env bash
# Bundle tests: this bundle's guard rows against a guard built from core + this bundle only
# (proves the sections do not depend on any other bundle), then every skill suite under
# skills/*/scripts/tests/run.sh. Exit 1 on any failure.
set -uo pipefail
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
bdir=$(cd "$here/.." && pwd); name=$(basename "$bdir")
core=$(cd "$bdir/../core" && pwd)
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
fail=0

if [ -f "$bdir/guard.d/tests.sh" ]; then
  HARNESS_GUARD_BUNDLES=$name bash "$core/guard/build.sh" "$tmp/hooks/guard-bash.sh" || fail=1
  GUARD_BASH="$tmp/hooks/guard-bash.sh" HARNESS_TEST_BUNDLES=$name \
    bash "$core/guard/tests/run.sh" > "$tmp/guard.log" 2>&1 || { fail=1; grep -A1 '^FAIL' "$tmp/guard.log"; }
  echo "guard ($name + core): $(tail -1 "$tmp/guard.log")"
fi
# doctor check gh-stack-extension and the gh-stack-extension step's verify against a stubbed
# `gh extension list`: an absent extension never fails doctor (PASS), another version warns
# (rc 1 under severity warn), and the step counts as done only at the pinned version.
python3 - "$bdir/bundle.toml" "$bdir/../../lib" "$tmp" <<'PY'
import sys
sys.path.insert(0, sys.argv[2])
from harness.toml_compat import loads
d = loads(open(sys.argv[1], encoding="utf-8").read())
chk = [c for c in d["doctor_checks"] if c["id"] == "gh-stack-extension"][0]
step = [s for s in d["manual_steps"] if s["id"] == "gh-stack-extension"][0]
assert chk["severity"] == "warn" and chk["fix"] == step["id"]
key = d["requires"]["config"]["github.stack_extension_version"]
want = key["default"]
# the key's pattern (schema_lite: re.search) takes the default and a prerelease, never a v
# prefix or a trailing newline (`$` would match before one)
import re
for v, ok in ((want, True), ("1.2.3-rc.1", True), ("v0.3.0", False), (want + "\n", False), ("0.3", False)):
    assert bool(re.search(key["pattern"], v)) is ok, "pattern %r on %r" % (key["pattern"], v)
for f, c in (("doc.sh", chk["cmd"]), ("step.sh", step["verify"]["cmd"])):
    open(sys.argv[3] + "/" + f, "w").write(c.replace("{{ github.stack_extension_version }}", want) + "\n")
PY
mkdir -p "$tmp/bin"
printf '#!/bin/sh\ncat "%s/gh.out"\nexit "$(cat "%s/gh.rc")"\n' "$tmp" "$tmp" > "$tmp/bin/gh"; chmod +x "$tmp/bin/gh"
sxfail=0; sxn=0
while IFS='|' read -r label rc listing want_doc want_step; do
  sxn=$((sxn + 1))
  printf '%b' "$listing" > "$tmp/gh.out"; echo "$rc" > "$tmp/gh.rc"
  PATH="$tmp/bin:$PATH" bash "$tmp/doc.sh" > "$tmp/doc.out" 2>&1; got_doc=$?
  PATH="$tmp/bin:$PATH" bash "$tmp/step.sh" > /dev/null 2>&1; got_step=$?
  [ "$got_step" = 0 ] || got_step=1
  if [ "$got_doc" != "$want_doc" ] || [ "$got_step" != "$want_step" ]; then
    echo "FAIL gh-stack-extension $label: doctor rc=$got_doc (want $want_doc) '$(head -1 "$tmp/doc.out")', step verify rc=$got_step (want $want_step)"
    sxfail=1
  fi
done <<'ROWS'
pinned|0|gh dash\towner/gh-dash\tv4.0.0\ngh stack\tgithub/gh-stack\tv0.3.0\n|0|0
other-version|0|gh stack\tgithub/gh-stack\tv0.2.1\n|1|1
absent|0|gh dash\towner/gh-dash\tv4.0.0\n|0|1
no-extensions|0||0|1
list-fails|1|error: could not read extensions\n|1|1
third-party|0|gh stack\tother/gh-stack\tv0.3.0\n|1|1
raw-version|0|gh stack\tgithub/gh-stack\t1a2b3c4d\n|1|1
other-name|0|gh stacks\tgithub/gh-stack\tv0.3.0\n|0|1
ROWS
[ $sxfail -eq 0 ] || fail=1
echo "doctor gh-stack-extension: $sxn rows $([ $sxfail -eq 0 ] && echo pass || echo FAILED)"
for t in "$bdir"/skills/*/scripts/tests/run.sh; do
  [ -f "$t" ] || continue
  bash "$t" > "$tmp/skill.log" 2>&1 || { fail=1; grep -E '^FAIL' "$tmp/skill.log" | head -20; }
  echo "$(basename "$(dirname "$(dirname "$(dirname "$t")")")"): $(tail -1 "$tmp/skill.log")"
done
[ $fail -eq 0 ] && echo "all $name tests passed" || echo "$name tests FAILED"
exit $fail
