#!/usr/bin/env bash
# Golden tests for supply.py. Every tool is a stub in stubs/ (SUPPLY_PATH points there, so a real
# npm, docker or cosign on PATH is never run); stubs log their argv to $STUB_LOG, answer from
# fixtures/tools and fail loudly on any signing, publishing or verification-off argument. DIR
# arguments are relative (the suite runs from fixtures/repos), so goldens carry no checkout path.
# Every case runs twice into two directories that must be identical (principle 9).
# UPDATE=1 rewrites golden/, KEEP=1 keeps the sandbox. Exits non-zero on any failure.
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
CLI="$here/../supply.py"
PY=${SUPPLY_TEST_PYTHON:-python3}
FIX="$here/fixtures"
GOLD="$here/golden"
REPOS="$FIX/repos"
unset SUPPLY_REGISTRIES_RE SUPPLY_REDACT_EXTRA_RE SUPPLY_EXCLUDE_RE SUPPLY_TIMEOUT SUPPLY_OSV_OFFLINE_DB \
      SUPPLY_MAX_BYTES SUPPLY_MAX_FILES STUB_FAIL STUB_PIP_AUDIT HARNESS_HOME
tmp=$(mktemp -d); tmp=$(cd "$tmp" && pwd -P)
[ "${KEEP:-0}" = 1 ] || trap 'rm -rf "$tmp"' EXIT
export LC_ALL=C PYTHONDONTWRITEBYTECODE=1
export SUPPLY_PATH="$here/stubs" SUPPLY_STUB_FIX="$FIX/tools" SUPPLY_DRY_RUN=1
fail=0; cases=0
mkdir -p "$GOLD" "$tmp/empty-path" "$tmp/fallback-path"
for t in npm pip-audit cargo govulncheck; do ln -s "$here/stubs/$t" "$tmp/fallback-path/$t"; done

# Hermetic config: one documentation-value signer identity.
cat > "$tmp/config.json" <<'JSON'
{"supply_chain": {"max_bytes": 65536, "pin_actions": true, "identities": [
  {"name": "release",
   "identity_re": "^https://github\\.com/octocat/hello-world/\\.github/workflows/release\\.yml@refs/tags/v.*$",
   "issuer": "https://token.actions.githubusercontent.com", "match_re": "^ghcr\\.io/octocat/"}]}}
JSON
printf '{"supply_chain": {"pin_actions": false}}\n' > "$tmp/config-noactions.json"
printf '{"supply_chain": {"identities": [{"name": "broken"}]}}\n' > "$tmp/config-badid.json"
export HARNESS_CONFIG_JSON="$tmp/config.json"

SHA=0123456789abcdef0123456789abcdef01234567
D64=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef

# Normalise what moves between machines and passes: the sandbox, the pass dir, the checkout.
norm() {
  "$PY" - "$1" "$here" "$out" "$tmp" <<'PY'
import sys
p, here, out, tmp = sys.argv[1:5]
t = open(p).read().replace(out, "OUT").replace(tmp, "SANDBOX").replace(here, "HERE")
open(p, "w").write(t)
PY
}

record() {  # record <name> <exit> <stdout-file> <stderr-file>
  local name=$1 rc=$2 o=$3 e=$4 g="$out/$1.txt"
  { echo "# exit=$rc"; echo "# stderr:"; cat "$e"; echo "# stdout:"; cat "$o"; } > "$g"
  norm "$g"
  [ "$pass" = 1 ] || return 0
  cases=$((cases + 1))
  if [ "${UPDATE:-0}" = 1 ]; then cp "$g" "$GOLD/$name.txt"; echo "UPDATED $name"; return; fi
  if [ ! -f "$GOLD/$name.txt" ]; then echo "FAIL $name (no golden — run UPDATE=1)"; fail=1; return; fi
  if diff -u "$GOLD/$name.txt" "$g" > "$out/$name.diff"; then echo "PASS $name"
  else echo "FAIL $name"; head -40 "$out/$name.diff"; fail=1; fi
}

t() {  # t <name> <expected-exit> <args...>
  local name=$1 exp=$2; shift 2
  "$PY" "$CLI" "$@" > "$out/$name.out" 2> "$out/$name.err" < /dev/null; local rc=$?
  [ "$rc" = "$exp" ] || { echo "FAIL $name: exit $rc, expected $exp"; cat "$out/$name.err"; fail=1; }
  record "$name" "$rc" "$out/$name.out" "$out/$name.err"
}

ts() {  # ts <name> <expected-exit> <stdin-file> <args...>
  local name=$1 exp=$2 inp=$3; shift 3
  "$PY" "$CLI" "$@" < "$inp" > "$out/$name.out" 2> "$out/$name.err"; local rc=$?
  [ "$rc" = "$exp" ] || { echo "FAIL $name: exit $rc, expected $exp"; cat "$out/$name.err"; fail=1; }
  record "$name" "$rc" "$out/$name.out" "$out/$name.err"
}

chk() {  # chk <condition-exit> <label>
  [ "$pass" = 1 ] || return 0
  cases=$((cases + 1))
  if [ "$1" = 0 ]; then echo "PASS $2"; else echo "FAIL $2"; fail=1; fi
}
ck() { local d=$1; shift; "$@"; chk $? "$d"; }  # ck <label> <test...>

run_cases() {
  cd "$REPOS" || exit 1
  export STUB_LOG="$out/stub.log" SUPPLY_DRY_RUN_LOG="$out/dry-run.log"
  : > "$STUB_LOG"; : > "$SUPPLY_DRY_RUN_LOG"
  mkdir -p "$out/work"

  # ------------------------------------------------------------------ detect
  t detect-dirty-json       0 detect dirty --json
  t detect-clean-md         0 detect clean --md
  t detect-empty-json       0 detect empty --json
  t detect-gitlab-json      0 detect gitlab-include --json
  t detect-missing          2 detect no-such-dir --json
  SUPPLY_MAX_FILES=3 t detect-truncated 0 detect dirty --json
  SUPPLY_EXCLUDE_RE='(^|/)\.github/' t detect-exclude 0 detect dirty --json
  SUPPLY_PATH="$tmp/empty-path" t detect-no-tools 0 detect clean --json

  # -------------------------------------------------------------------- pins
  t pins-dirty-json         1 pins dirty --json
  t pins-dirty-md           1 pins dirty --md
  t pins-clean-json         0 pins clean --json
  t pins-gha-injection-json 1 pins gha-injection --json
  t pins-gitlab-md          1 pins gitlab-include --md
  t pins-dockerfiles-json   1 pins dockerfiles --json
  t pins-empty-json         0 pins empty --json
  t pins-max-bytes          1 pins dirty --json --max-bytes 2000
  SUPPLY_MAX_FILES=3 t pins-truncated 1 pins dirty --json
  SUPPLY_REGISTRIES_RE='^(ghcr\.io|registry\.example\.com)$' t pins-registries 1 pins dockerfiles --json
  HARNESS_CONFIG_JSON="$tmp/config-noactions.json" t pins-no-actions 1 pins dirty --json
  SUPPLY_EXCLUDE_RE='(' t pins-bad-exclude 2 pins dirty --json

  # pins --apply on a copy: exact tokens, everything else on the line kept, byte-exact
  rm -rf "$out/work/orig" "$out/work/dirty"
  cp -R dirty "$out/work/orig"; cp -R dirty "$out/work/dirty"
  cat > "$out/work/apply.json" <<JSON
[{"file": ".github/workflows/build.yml", "line": 8, "old": "actions/checkout@v4", "new": "actions/checkout@$SHA"},
 {"file": "Dockerfile", "line": 3, "old": "alpine", "new": "alpine:3.20@sha256:$D64"},
 {"file": "requirements.txt", "line": 2, "old": "git+https://github.com/octocat/hello-world", "new": "git+https://github.com/octocat/hello-world@$SHA"},
 {"file": "package.json", "line": 5, "old": "github:octocat/hello-world", "new": "github:octocat/hello-world#$SHA"}]
JSON
  (cd "$out/work" && "$PY" "$CLI" pins dirty --apply apply.json --json > "$out/pins-apply.out" 2> "$out/pins-apply.err"; echo $? > "$out/pins-apply.rc")
  rc=$(cat "$out/pins-apply.rc"); [ "$rc" = 1 ] || { echo "FAIL pins-apply: exit $rc, expected 1"; fail=1; }
  record pins-apply "$rc" "$out/pins-apply.out" "$out/pins-apply.err"
  (cd "$out/work" && diff -r orig dirty) > "$out/pins-apply-diff.out" 2>&1
  : > "$out/empty.err"; record pins-apply-diff 1 "$out/pins-apply-diff.out" "$out/empty.err"

  rm -rf "$out/work/amb"; cp -R dirty "$out/work/amb"
  cat > "$out/work/amb.json" <<JSON
[{"file": "Dockerfile", "line": 3, "old": "alpine", "new": "alpine:3.20@sha256:$D64"},
 {"file": "Dockerfile", "line": 4, "old": "/app", "new": "/srv"},
 {"file": "Dockerfile", "line": 1, "old": "node:22", "new": "node:22@sha256:$D64"},
 {"file": "requirements.txt", "line": 9, "old": "x", "new": "y"},
 {"file": "../escape", "line": 1, "old": "x", "new": "y"}]
JSON
  (cd "$out/work" && "$PY" "$CLI" pins amb --apply amb.json --json > "$out/pins-apply-refused.out" 2> "$out/pins-apply-refused.err"; echo $? > "$out/pins-apply-refused.rc")
  rc=$(cat "$out/pins-apply-refused.rc"); [ "$rc" = 2 ] || { echo "FAIL pins-apply-refused: exit $rc, expected 2"; fail=1; }
  record pins-apply-refused "$rc" "$out/pins-apply-refused.out" "$out/pins-apply-refused.err"
  ck "a refused apply writes nothing" diff -r dirty "$out/work/amb"
  printf 'not json' > "$out/work/bad.json"
  (cd "$out/work" && "$PY" "$CLI" pins amb --apply bad.json > /dev/null 2> "$out/apply-bad.err"); rc=$?
  ck "an apply file that is not JSON exits 2" [ "$rc" = 2 ]

  # CRLF line endings, a trailing comment and indentation survive byte-exact
  mkdir -p "$out/work/crlf/.github/workflows"
  printf 'on: push\r\npermissions: {}\r\njobs:\r\n  b:\r\n    steps:\r\n      - uses:   actions/checkout@v4   # pin me\r\n' \
    > "$out/work/crlf/.github/workflows/w.yml"
  printf 'on: push\r\npermissions: {}\r\njobs:\r\n  b:\r\n    steps:\r\n      - uses:   actions/checkout@%s   # pin me\r\n' "$SHA" \
    > "$out/work/crlf-expected.yml"
  printf '[{"file": ".github/workflows/w.yml", "line": 6, "old": "actions/checkout@v4", "new": "actions/checkout@%s"}]' "$SHA" \
    > "$out/work/crlf.json"
  (cd "$out/work" && "$PY" "$CLI" pins crlf --apply crlf.json --json > "$out/crlf.out" 2>/dev/null); rc=$?
  ck "apply keeps CRLF, spacing and the comment (byte-exact)" cmp -s "$out/work/crlf/.github/workflows/w.yml" "$out/work/crlf-expected.yml"
  ck "apply then re-scans: the pinned action is clean (exit 0)" [ "$rc" = 0 ]
  mkdir -p "$out/work/noact/.github/workflows"
  cp "$out/work/crlf-expected.yml" "$out/work/noact-expected.yml"
  printf 'on: push\r\npermissions: {}\r\njobs:\r\n  b:\r\n    steps:\r\n      - uses:   actions/checkout@v4   # pin me\r\n' \
    > "$out/work/noact/.github/workflows/w.yml"
  (cd "$out/work" && HARNESS_CONFIG_JSON="$tmp/config-noactions.json" "$PY" "$CLI" pins noact --apply crlf.json --json > "$out/noact.out" 2>/dev/null)
  grep -q 'pin_actions is false' "$out/noact.out" && grep -q 'checkout@v4' "$out/work/noact/.github/workflows/w.yml"
  chk $? "pin_actions = false: --apply skips action pins and says why"

  # ---------------------------------------------------------------------- ci
  # a tab-indented workflow, generated here (the repository's YAML hook would reject the file)
  mkdir -p "$out/work/tabs/.github/workflows"
  printf 'name: broken\non: push\njobs:\n\tbuild:\n\t\truns-on: ubuntu-24.04\n' \
    > "$out/work/tabs/.github/workflows/broken.yml"
  (cd "$out/work" && "$PY" "$CLI" ci tabs/.github/workflows/broken.yml --json > "$out/ci-tabs.out" 2> "$out/ci-tabs.err"; echo $? > "$out/ci-tabs.rc")
  record ci-tabs "$(cat "$out/ci-tabs.rc")" "$out/ci-tabs.out" "$out/ci-tabs.err"
  (cd "$out/work" && "$PY" "$CLI" pins tabs --json > "$out/pins-tabs.out" 2> "$out/pins-tabs.err"; echo $? > "$out/pins-tabs.rc")
  record pins-tabs "$(cat "$out/pins-tabs.rc")" "$out/pins-tabs.out" "$out/pins-tabs.err"
  t ci-dirty-json        1 ci dirty/.github/workflows/build.yml dirty/.github/workflows/pr-target.yml \
                              dirty/.github/workflows/release.yml \
                              dirty/.gitlab-ci.yml dirty/deploy.bash --json
  t ci-gha-injection-md  1 ci gha-injection/.github/workflows/triage.yml --md
  t ci-gha-injection-json 1 ci gha-injection/.github/workflows/triage.yml --json
  t ci-gitlab-json       1 ci gitlab-include/.gitlab-ci.yml gitlab-include/ci/build.yml --json
  t ci-clean-json        0 ci clean/.github/workflows/ci.yml clean/.gitlab-ci.yml clean/scripts/install.bash clean/Dockerfile --json
  t ci-ignore-json       1 ci dirty/.github/workflows/build.yml --ignore CI001,gha001 --json
  t ci-ignore-unknown    1 ci dirty/.github/workflows/build.yml --ignore NOPE001
  t ci-unrecognised      0 ci clean/package.json --json
  t ci-missing           2 ci no-such-file.yml --json

  # ------------------------------------------------------------------- audit
  t audit-osv-json       1 audit dirty --json
  t audit-osv-md         1 audit dirty --md
  t audit-osv-clean      0 audit clean --json
  t audit-osv-nopackages 0 audit empty --json
  t audit-osv-error      2 audit gitlab-include --json
  t audit-osv-lockfile   1 audit dirty --lockfile dirty/requirements.txt --json
  t audit-osv-sbom       1 audit dirty --sbom ../sbom/good.cdx.json --json
  t audit-sbom-name      1 audit dirty --sbom ../sbom/not-sbom.json
  SUPPLY_OSV_OFFLINE_DB=/home/u/.cache/osv-db t audit-osv-offline 1 audit dirty --offline --json
  SUPPLY_PATH="$tmp/fallback-path" t audit-fallbacks-json 1 audit clean --json
  SUPPLY_PATH="$tmp/fallback-path" t audit-fallbacks-md   1 audit clean --md
  SUPPLY_PATH="$tmp/fallback-path" STUB_PIP_AUDIT=error t audit-fallback-error 1 audit clean --json
  SUPPLY_PATH="$tmp/fallback-path" t audit-fallbacks-offline 3 audit clean --offline --json
  SUPPLY_PATH="$tmp/fallback-path" t audit-fallbacks-nolock 1 audit dirty --json
  SUPPLY_PATH="$tmp/empty-path" t audit-unavailable 3 audit clean --json
  SUPPLY_PATH="$tmp/empty-path" t audit-unavailable-empty 0 audit empty --json
  SUPPLY_PATH="$tmp/empty-path" t audit-unavailable-sbom 3 audit dirty --sbom ../sbom/good.cdx.json

  # -------------------------------------------------------------------- sbom
  t sbom-dir-json        0 sbom clean --json
  t sbom-image-md        0 sbom ghcr.io/octocat/hello-world:1.0 --format cyclonedx-json --md
  rm -f "$out/clean.spdx.json"
  t sbom-out             0 sbom clean --out "$out/clean.spdx.json" --json
  t sbom-out-exists      1 sbom clean --out "$out/clean.spdx.json" --json
  t sbom-out-force       0 sbom clean --out "$out/clean.spdx.json" --force --json
  t sbom-image-missing   2 sbom oci://ghcr.io/octocat/missing:1.0 --json
  t sbom-file            3 sbom clean/Dockerfile --json
  SUPPLY_PATH="$tmp/empty-path" t sbom-unavailable 2 sbom clean --json
  t sbom-lint-good-spdx  0 sbom lint ../sbom/good.spdx.json --json
  t sbom-lint-bad-spdx   1 sbom lint ../sbom/bad.spdx.json --json
  t sbom-lint-good-cdx   0 sbom lint ../sbom/good.cdx.json --md
  t sbom-lint-bad-cdx    1 sbom lint ../sbom/bad.cdx.json --md
  t sbom-lint-not-sbom   1 sbom lint ../sbom/not-sbom.json --json
  t sbom-lint-not-json   3 sbom lint ../sbom/not-json.txt --json

  # ------------------------------------------------------------------ verify
  t verify-name-json     0 verify ghcr.io/octocat/hello-world:1.0 --identity release --json
  t verify-match-md      0 verify ghcr.io/octocat/hello-world:1.0 --md
  t verify-regexp        0 verify ghcr.io/octocat/hello-world:1.0 --identity '^https://github\.com/octocat/' \
                              --issuer https://token.actions.githubusercontent.com --json
  t verify-regexp-no-issuer 2 verify ghcr.io/octocat/hello-world:1.0 --identity '^https://github\.com/octocat/'
  t verify-no-identity   2 verify registry.example.com/app:1.0 --json
  HARNESS_CONFIG_JSON="$tmp/config-badid.json" t verify-bad-config 2 verify registry.example.com/app:1.0 --json
  t verify-key           0 verify ghcr.io/octocat/hello-world:1.0 --key cosign.pub --json
  t verify-attestation   0 verify ghcr.io/octocat/hello-world:1.0 --attestation --type slsaprovenance1 --identity release --json
  t verify-blob-no-bundle 1 verify dirty/deploy.bash --identity release
  t verify-blob          0 verify dirty/deploy.bash --bundle deploy.bash.sigstore.json --identity release --json
  t verify-github-md     0 verify oci://ghcr.io/octocat/hello-world:1.0 --github octocat/hello-world --md
  t verify-github-blob   0 verify dirty/deploy.bash --github octocat --json
  t verify-github-fail   2 verify ghcr.io/octocat/unattested:1.0 --github octocat/hello-world --json
  t verify-unsigned      2 verify ghcr.io/octocat/unsigned:1.0 --identity release --json
  t verify-mismatch      1 verify ghcr.io/octocat/mirror:1.0 --identity release --json
  t verify-offline-no-root 3 verify ghcr.io/octocat/hello-world:1.0 --identity release --offline --json
  t verify-offline-root  0 verify ghcr.io/octocat/hello-world:1.0 --identity release --offline \
                              --trusted-root ../tools/trusted-root.json --json
  t verify-key-and-github 1 verify ghcr.io/octocat/hello-world:1.0 --key cosign.pub --github octocat
  SUPPLY_PATH="$tmp/empty-path" t verify-unavailable 2 verify ghcr.io/octocat/hello-world:1.0 --identity release --json
  SUPPLY_PATH="$tmp/empty-path" t verify-gh-unavailable 2 verify dirty/deploy.bash --github octocat --json

  # ------------------------------------------------------------------ redact
  ts redact-text 0 dirty/deploy.bash redact
  ts redact-json 0 ../tools/redact-input.json redact
  SUPPLY_REDACT_EXTRA_RE='example\.com/tool\.tgz' ts redact-extra-re 0 dirty/deploy.bash redact
  SUPPLY_REDACT_EXTRA_RE='(' ts redact-bad-re 2 dirty/deploy.bash redact

  # ------------------------------------------------------------------- usage
  t usage-unknown        1 bogus
  t usage-sbom-lint      1 sbom lint

  record dry-run-requests 0 "$SUPPLY_DRY_RUN_LOG" "$out/empty.err"
  cd "$here" || exit 1
}

pass=1; out="$tmp/pass1"; mkdir -p "$out"; run_cases
pass=2; out="$tmp/pass2"; mkdir -p "$out"; run_cases > "$tmp/pass2.log" 2>&1
pass=1; out="$tmp/pass1"
cases=$((cases + 1))
: > "$tmp/det.diff"
for g in "$tmp/pass1"/*.txt; do
  diff "$g" "$tmp/pass2/$(basename "$g")" >> "$tmp/det.diff" 2>&1
done
if [ -s "$tmp/det.diff" ]; then
  echo "FAIL two runs differ (principle 9)"; head -20 "$tmp/det.diff"; fail=1
else
  echo "PASS two runs produce identical output"
fi

# ---------------------------------------------------------------------- assertions
cd "$REPOS" || exit 1
for f in "$out"/*.err; do
  n=$(basename "$f" .err)
  case "$n" in redact-*|sbom-lint-*|usage-*|empty|apply-bad|pins-apply-diff|verify-key-and-github|ci-ignore-unknown|audit-sbom-name|verify-blob-no-bundle) continue ;;
    detect-missing|ci-missing|pins-bad-exclude|sbom-file) continue ;;  # refused before the scan starts
  esac
  head -1 "$f" | grep -qE '^supply: dir=[^ ]+ ecosystems=[a-z,-]+ tools=[a-z,-]+$' || { echo "FAIL banner shape in $n: $(head -1 "$f")"; fail=1; }
done
chk 0 "every command except redact and sbom lint prints the banner first"
grep -q 'tools=none' "$out/detect-no-tools.err"; chk $? "SUPPLY_PATH=<empty dir> means no tools, even with npm or docker on PATH"
grep -q '^supply: dir=- ecosystems=none' "$out/verify-name-json.err"; chk $? "an image target banners dir=-"

"$PY" - "$out" <<'PY'
import json, os, sys
out, bad = sys.argv[1], []
for fn in sorted(os.listdir(out)):
    if not fn.endswith(".out") or fn.startswith(("redact-", "pins-apply-diff")):
        continue
    txt = open(os.path.join(out, fn)).read()
    if not txt.startswith("{"):
        continue
    try:
        env = json.loads(txt)
    except ValueError as e:
        bad.append("%s: not JSON (%s)" % (fn, e)); continue
    fs = env.get("findings", [])
    keys = [(f["file"], f["line"], f["id"], f["message"]) for f in fs]
    if keys != sorted(keys):
        bad.append("%s: findings not sorted" % fn)
    for k in ("command", "dir", "ecosystems", "tools", "findings", "data"):
        if k not in env:
            bad.append("%s: envelope lacks %s" % (fn, k))
    for f in fs:
        if f["severity"] not in ("crit", "warn", "info") or not f["fix"]:
            bad.append("%s: bad finding %r" % (fn, f))
print("\n".join(bad))
sys.exit(1 if bad else 0)
PY
chk $? "every JSON output parses, carries the envelope, and its findings are sorted with a fix"

leaks=$(grep -lE 'hunter2|s3cr3tpass|abc123def456' "$out"/*.out "$out"/*.err "$out/clean.spdx.json" 2>/dev/null)
ck "no fixture secret (password=hunter2, URL credentials, token=) reaches stdout, stderr or --out" [ -z "$leaks" ]
grep -q 'REDACTED' "$out/pins-dirty-json.out"; chk $? "a finding snippet from a file is redacted"
grep -q 'REDACTED' "$out/sbom-out.out" || grep -q 'REDACTED' "$out/clean.spdx.json"; chk $? "syft output is redacted before it is written"
bad=$(grep -lE "$here|/home/|/Users/" "$GOLD"/*.txt 2>/dev/null | grep -v 'audit-osv-offline\|dry-run-requests')
ck "no golden carries an absolute checkout or home path" [ -z "$bad" ]
"$PY" -c 'import json,sys; json.load(open(sys.argv[1]))' "$out/clean.spdx.json"; chk $? "sbom --out writes a whole JSON document"
ck "the sbom --out file is sorted JSON" "$PY" -c 'import json,sys; t=open(sys.argv[1]).read(); sys.exit(0 if t==json.dumps(json.loads(t),indent=2,sort_keys=True,ensure_ascii=False)+"\n" else 1)' "$out/clean.spdx.json"
grep -q 'already exists' "$out/sbom-out-exists.err"; chk $? "sbom --out refuses an existing file without --force"

# offline-only commands never run a tool
STUB_LOG="$tmp/offline.log"; : > "$STUB_LOG"; export STUB_LOG
for args in "detect dirty" "pins dirty" "ci dirty/deploy.bash" "sbom lint ../sbom/good.spdx.json"; do
  # shellcheck disable=SC2086
  "$PY" "$CLI" $args --json > /dev/null 2>&1
done
"$PY" "$CLI" redact < dirty/deploy.bash > /dev/null 2>&1
ck "detect, pins, ci, sbom lint and redact never run a tool" [ ! -s "$STUB_LOG" ]

# stub-log invariants (pass 1)
L="$out/stub.log"
bad=$(grep '^osv-scanner ' "$L" | grep -v '^osv-scanner scan source --format json' | head -3)
ck "every osv-scanner call is 'scan source --format json'" [ -z "$bad" ]
! grep -qE '^osv-scanner .*(\bfix\b|--download-offline-databases)' "$L"; chk $? "osv-scanner never runs fix or downloads databases"
grep -q '^osv-scanner .*--offline-vulnerabilities' "$L"; chk $? "--offline maps to --offline-vulnerabilities"
bad=$(grep '^cosign ' "$L" | grep -vE '^cosign verify(-attestation|-blob|-blob-attestation)? ' | head -3)
ck "every cosign call is verify*" [ -z "$bad" ]
bad=$(grep -E '^cosign verify(-attestation)? ' "$L" | grep -v -- '--output json' | head -3)
ck "every cosign image verification asks for --output json" [ -z "$bad" ]
! grep -qE '^cosign .*(--insecure|--allow-)' "$L"; chk $? "no cosign call carries --insecure-* or --allow-*-registry"
bad=$(grep '^syft ' "$L" | grep -vE '^syft scan (dir|registry):[^ ]+ -o (spdx|cyclonedx)-json -q$' | head -3)
ck "every syft call is 'scan dir:|registry: -o FORMAT -q'" [ -z "$bad" ]
bad=$(grep '^gh ' "$L" | grep -v '^gh attestation verify .*--format json' | head -3)
ck "every gh call is 'attestation verify … --format json'" [ -z "$bad" ]
bad=$(grep '^npm ' "$L" | grep -v '^npm audit --json --audit-level=none$' | head -3)
ck "every npm call is 'npm audit --json --audit-level=none'" [ -z "$bad" ]
! grep -qiE 'docker' "$L" "$out/dry-run.log"; chk $? "the docker daemon is never called"
ck "the dry-run log matches the stub log one for one" [ "$(wc -l < "$out/dry-run.log")" = "$(wc -l < "$L")" ]

# usage
"$PY" "$CLI" > "$tmp/usage.out" 2>&1; rc=$?
[ "$rc" = 1 ] && grep -q "Deliberately NOT implemented" "$tmp/usage.out"; chk $? "bare supply prints usage, exit 1"
"$PY" "$CLI" --help > "$tmp/help.out" 2>&1; rc=$?
[ "$rc" = 0 ] && grep -q "Commands" "$tmp/help.out"; chk $? "supply --help exits 0"
"$PY" "$CLI" pins -h > /dev/null 2>&1; chk $? "supply pins -h exits 0"
SUPPLY_REDACT_EXTRA_RE='(' "$PY" "$CLI" detect clean --json > /dev/null 2>&1; chk $? "a bad redact regex does not break a command that redacts nothing"

# every rule id of the CLI is documented exactly once, as a rubric row, in references/
"$PY" - "$CLI" "$here/../../references" <<'PY2'
import glob, os, re, sys
cli, refs = sys.argv[1], sys.argv[2]
body = open(cli).read().split("RULES = {", 1)[1].split("\n}\n", 1)[0]
ids = sorted(set(re.findall(r'^    "([A-Z]+[0-9]{3})":', body, re.M)))
rows = {}
for p in sorted(glob.glob(os.path.join(refs, "*.md"))):
    for m in re.finditer(r"(?m)^\| ([A-Z]+[0-9]{3}) \| (crit|warn|info)", open(p).read()):
        rows.setdefault(m.group(1), []).append(os.path.basename(p))
bad = ["%s: documented %d times %s" % (i, len(rows.get(i, [])), rows.get(i, [])) for i in ids if len(rows.get(i, [])) != 1]
bad += ["%s: documented but not a CLI rule" % i for i in sorted(set(rows) - set(ids))]
print("\n".join(bad))
sys.exit(1 if bad or not ids else 0)
PY2
chk $? "every rule id is documented once in references/ with a severity"

# static checks
for f in "$here"/stubs/* "$here/run.sh"; do /bin/bash -n "$f" || { echo "FAIL bash -n $f"; fail=1; }; done
chk 0 "stubs and run.sh parse with bash -n"
"$PY" -m py_compile "$CLI"; chk $? "supply.py compiles"
rm -rf "$here/../__pycache__"

cd "$here" || exit 1
if [ "${KEEP:-0}" = 1 ]; then echo "artifacts in $tmp"; fi
if [ $fail -eq 0 ]; then echo "all supply tests passed ($cases cases)"; else echo "supply tests FAILED"; fi
exit $fail
