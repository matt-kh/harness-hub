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
# doctor check supply-config (jq) must accept and reject exactly what supply's check_identity_re does
cfgcmd=$(python3 - "$bdir/bundle.toml" "$bdir/../../lib" <<'PY'
import sys
sys.path.insert(0, sys.argv[2])
from harness.toml_compat import loads
d = loads(open(sys.argv[1], encoding="utf-8").read())
print([c["cmd"] for c in d["doctor_checks"] if c["id"] == "supply-config"][0])
PY
)
supply_py="$bdir/skills/supply/scripts/supply.py"
idfail=0; idn=0
# want: 0 = accepted, 1 = rejected, by the doctor check and by supply alike
while IFS='|' read -r want rx; do
  idn=$((idn + 1))
  if [ "$rx" = "<none>" ]; then printf '{"supply_chain": {}}\n' > "$tmp/cfg.json"
  else
    python3 -c 'import json, sys; json.dump({"supply_chain": {"identities": [{"name": "r", "identity_re": sys.argv[1], "issuer": "https://issuer.example.com"}]}}, open(sys.argv[2], "w"))' "$rx" "$tmp/cfg.json"
  fi
  HARNESS_CONFIG_JSON="$tmp/cfg.json" bash -c "$cfgcmd" > /dev/null 2>&1; got=$?
  [ "$got" = 0 ] || got=1
  sup=0
  if [ "$rx" != "<none>" ]; then
    python3 -c 'import importlib.util, sys
spec = importlib.util.spec_from_file_location("supply", sys.argv[1]); m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
try:
    m.check_identity_re(sys.argv[2], "t")
except m.AccessError:
    sys.exit(1)' "$supply_py" "$rx" > /dev/null 2>&1 || sup=1
  fi
  if [ "$got" != "$want" ] || [ "$sup" != "$want" ]; then
    echo "FAIL supply-config doctor check on identity_re '$rx': doctor=$got supply=$sup want=$want"; idfail=1
  fi
done <<'ROWS'
0|<none>
0|^https://github\.com/octocat/hello-world/\.github/workflows/release\.yml@refs/tags/v.*$
0|^a$
1|^.*$
1|^(a)?$
1|^foo\$
1|https://github\.com/octocat/.*$
1|^https://github\.com/octocat/
1|
1|^($
ROWS
[ $idfail -eq 0 ] || fail=1
echo "doctor supply-config: $idn identity_re rows $([ $idfail -eq 0 ] && echo agree with check_identity_re || echo FAILED)"

for t in "$bdir"/skills/*/scripts/tests/run.sh; do
  [ -f "$t" ] || continue
  bash "$t" > "$tmp/skill.log" 2>&1 || { fail=1; grep -E '^FAIL' "$tmp/skill.log" | head -20; }
  echo "$(basename "$(dirname "$(dirname "$(dirname "$t")")")"): $(tail -1 "$tmp/skill.log")"
done
[ $fail -eq 0 ] && echo "all $name tests passed" || echo "$name tests FAILED"
exit $fail
