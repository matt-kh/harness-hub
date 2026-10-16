#!/usr/bin/env bash
# Offline golden tests for obs.py. Every HTTP call goes through tests/fakes/http_fixture.py
# (fixture-routed urlopen, sockets disabled); the key files live in a throw-away HOME created
# here at mode 600, never in the repository. The dry-run case runs the CLI's own
# OBS_DRY_RUN / OBS_HTTP_FIXTURES path and asserts every request is a GET or a POST to an
# allow-listed read endpoint. UPDATE=1 rewrites golden/. Exits non-zero on any failure.
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
CLI="$here/../obs.py"
FIX="$here/fixtures"
GOLD="$here/golden"
DRIVER=$(cd "$here/../../../../../../tests/fakes" && pwd)/http_fixture.py
unset OBS_DEFAULT OBS_PROD_RE OBS_HOSTS_RE OBS_LOG_TAIL OBS_MAX_BYTES OBS_REDACT_EXTRA_RE OBS_TIMEOUT \
      OBS_DRY_RUN OBS_DRY_RUN_LOG OBS_HTTP_FIXTURES HARNESS_HOME
tmp=$(mktemp -d); tmp=$(cd "$tmp" && pwd -P); trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/work" "$GOLD"
fail=0; cases=0

# Fake key values: none of them may ever reach stdout or stderr.
SECRETS_RE='test-signoz-key-0001|test-signoz-prod-key-0002|test-grafana-sa-0003|test-bearer-0123456789abcdef|hunter2|s3cr3tpass|abcd1234efgh5678'  # pragma: allowlist secret (fake fixture values)

# Hermetic config: the compiled harness config the CLI reads (HARNESS_CONFIG_JSON).
cat > "$tmp/config.json" <<'JSON'
{"obs": {"default": "signoz-dev",
         "hosts_re": "^(signoz|signoz-prod|grafana|prometheus)\\.example\\.com$",
         "prod_re": "(^|[-_./:])(prod|production)([-_./:]|$)",
         "log_tail": 200, "max_bytes": 65536, "redact_extra_re": "",
         "backends": [
           {"name": "signoz-dev", "kind": "signoz", "url": "https://signoz.example.com", "auth_file": "~/.config/obs/signoz-dev.key"},
           {"name": "signoz-prod", "kind": "signoz", "url": "https://signoz-prod.example.com", "auth_file": "~/.config/obs/signoz-prod.key"},
           {"name": "prom", "kind": "prometheus", "url": "https://prometheus.example.com"},
           {"name": "grafana", "kind": "grafana", "url": "https://grafana.example.com/", "auth_file": "~/.config/obs/grafana.key"}]}}
JSON
export HARNESS_CONFIG_JSON="$tmp/config.json"

# mkhome DIR [skip-key-name]: key files at 600 in DIR/.config/obs (700)
mkhome() {
  local h=$1 skip=${2:-}
  rm -rf "$h"; mkdir -p "$h/.config/obs"; chmod 700 "$h/.config/obs"
  [ "$skip" = signoz-dev ] || printf 'test-signoz-key-0001\n' > "$h/.config/obs/signoz-dev.key"
  [ "$skip" = signoz-prod ] || printf 'test-signoz-prod-key-0002\n' > "$h/.config/obs/signoz-prod.key"
  [ "$skip" = grafana ] || printf 'test-grafana-sa-0003\n' > "$h/.config/obs/grafana.key"
  chmod 600 "$h/.config/obs/"*.key
}
mkhome "$tmp/home"

# routes OUT FILE...: the listed case files first, then every backend's routes.json
routes() {
  local out=$1; shift
  python3 - "$out" "$@" "$FIX"/*/routes.json <<'PY'
import json, sys
out, files = sys.argv[1], sys.argv[2:]
merged = []
for f in files:
    merged.extend(json.load(open(f)))
json.dump(merged, open(out, "w"))
PY
}
routes "$tmp/r-common.json"
routes "$tmp/r-logs.json" "$FIX/signoz/logs.json"
routes "$tmp/r-traces.json" "$FIX/signoz/traces.json"
routes "$tmp/r-trace.json" "$FIX/signoz/trace.json"
routes "$tmp/r-loki.json" "$FIX/grafana/loki.json"
cp "$FIX/errors/err-401.json" "$tmp/r-401.json"
cp "$FIX/errors/err-unreachable.json" "$tmp/r-unreachable.json"
cp "$FIX/errors/err-redirect.json" "$tmp/r-redirect.json"
cp "$FIX/errors/err-html.json" "$tmp/r-html.json"
cp "$FIX/errors/err-404.json" "$tmp/r-404.json"

# Normalise what moves: the sandbox and checkout paths, wall-clock timestamps and epochs.
norm() {
  python3 - "$1" "$here" "$tmp" <<'PY'
import re, sys
p, here, tmp = sys.argv[1:4]
t = open(p).read().replace(tmp, "SANDBOX").replace(here, "HERE")
t = re.sub(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z", "TIMESTAMP", t)
t = re.sub(r"(?<![\d.])1[6-9]\d{17}(?!\d)", "EPOCH_NS", t)
t = re.sub(r"(?<![\d.])1[6-9]\d{11}(?!\d)", "EPOCH_MS", t)
t = re.sub(r"(?<![\d.])1[6-9]\d{8}(?!\d)", "EPOCH_S", t)
t = re.sub(r"(?m)(?<![\d.])1[6-9]\d{3,}$", "EPOCH_CUT", t)   # an epoch cut by the driver's 200-char body log
open(p, "w").write(t)
PY
}

record() {  # record <name> <exit> [extra-file]
  local name=$1 rc=$2 extra=${3:-} g="$tmp/$1.txt"
  { echo "# exit=$rc"; echo "# stderr:"; cat "$tmp/$name.err"; echo "# stdout:"; cat "$tmp/$name.out"
    echo "# calls:"; cat "$tmp/$name.log" 2>/dev/null
    if [ -n "$extra" ]; then echo "# file:"; cat "$extra"; fi; } > "$g"
  norm "$g"
  cases=$((cases + 1))
  if grep -qE "$SECRETS_RE" "$g"; then echo "FAIL $name: a fake secret reached the output"; grep -nE "$SECRETS_RE" "$g" | head -5; fail=1; fi
  if [ "${UPDATE:-0}" = 1 ]; then cp "$g" "$GOLD/$name.txt"; echo "UPDATED $name"; return; fi
  if [ ! -f "$GOLD/$name.txt" ]; then echo "FAIL $name (no golden — run UPDATE=1)"; fail=1; return; fi
  if diff -u "$GOLD/$name.txt" "$g" > "$tmp/$name.diff"; then echo "PASS $name"
  else echo "FAIL $name"; head -40 "$tmp/$name.diff"; fail=1; fi
}

check_rc() { [ "$1" = "$2" ] || { echo "FAIL $3: exit $1, expected $2"; cat "$tmp/$3.err"; fail=1; }; }

# t <name> <expected-exit> <routes> <args...>       driver-routed case in $tmp/home
# th <name> <expected-exit> <home> <routes> <args...>
th() {
  local name=$1 exp=$2 home=$3 r=$4; shift 4
  : > "$tmp/$name.log"
  (cd "$tmp/work" && HOME="$home" python3 "$DRIVER" "$CLI" "$tmp/r-$r.json" --log "$tmp/$name.log" -- "$@") \
    > "$tmp/$name.out" 2> "$tmp/$name.err"
  local rc=$?
  check_rc "$rc" "$exp" "$name"; record "$name" "$rc"
}
t() { local name=$1 exp=$2 r=$3; shift 3; th "$name" "$exp" "$tmp/home" "$r" "$@"; }

# l <name> <expected-exit> <args...>                offline (lint), no driver
l() {
  local name=$1 exp=$2; shift 2
  (cd "$FIX" && HOME="$tmp/home" python3 "$CLI" "$@") > "$tmp/$name.out" 2> "$tmp/$name.err"
  local rc=$?
  : > "$tmp/$name.log"; check_rc "$rc" "$exp" "$name"; record "$name" "$rc"
}

# ------------------------------------------------------------------------- backends
t  backends-md            0 common backends --md
t  backends-json          0 common backends --probe --json
mkhome "$tmp/home-nokey" grafana
th backends-key-missing   2 "$tmp/home-nokey" common backends --md
# ---------------------------------------------------------------------------- query
t  query-signoz-md        0 common query 'sum(rate(calls_total[5m])) by (service_name)' --md
t  query-prom-range-json  0 common --backend prom query up --range 1h --step 60s --json
t  query-grafana-ds       0 common --backend grafana query up --datasource prom-ds --md
# ----------------------------------------------------------------------------- logs
t  logs-signoz-redacted   0 logs logs "severity_text = 'ERROR'" --service checkout --limit 50 --md
t  logs-grafana-loki      0 loki --backend grafana logs timeout --service checkout --datasource loki-ds --md
t  logs-prom-unsupported  3 common --backend prom logs error
# --------------------------------------------------------------------------- traces
t  traces-signoz          0 traces traces --service checkout --error --min-duration 500ms --md
t  trace-depth            1 trace trace 4bf92f3577b34da6a3ce929d0e0e4736 --depth 2 --md
# ------------------------------------------------------------------------- services
t  services-signoz        1 common services --since 1h --md
t  services-prom-unsupported 3 common --backend prom services
# --------------------------------------------------------------------------- alerts
t  alerts-firing          1 common alerts --firing --md
t  alerts-rules           0 common --backend prom alerts --rules --md
t  alerts-grafana-json    1 common --backend grafana alerts --firing --rules --json
# ----------------------------------------------------------------------- dashboards
t  dashboards-list        0 common --backend grafana dashboards --md
rm -f "$tmp/work/dash.json"
: > "$tmp/dashboards-export.log"
(cd "$tmp/work" && HOME="$tmp/home" python3 "$DRIVER" "$CLI" "$tmp/r-common.json" --log "$tmp/dashboards-export.log" -- \
  dashboards --export 0199aaaa-bbbb-7ccc-8ddd-eeeeeeee0001 dash.json --md) > "$tmp/dashboards-export.out" 2> "$tmp/dashboards-export.err"
rc=$?; check_rc "$rc" 1 dashboards-export; record dashboards-export "$rc" "$tmp/work/dash.json"
# An existing FILE is never overwritten without --force (no request is made either).
printf 'keep me\n' > "$tmp/work/exists.json"
: > "$tmp/dashboards-export-exists.log"
(cd "$tmp/work" && HOME="$tmp/home" python3 "$DRIVER" "$CLI" "$tmp/r-common.json" --log "$tmp/dashboards-export-exists.log" -- \
  dashboards --export 0199aaaa-bbbb-7ccc-8ddd-eeeeeeee0001 exists.json --md) > "$tmp/dashboards-export-exists.out" 2> "$tmp/dashboards-export-exists.err"
rc=$?; check_rc "$rc" 1 dashboards-export-exists; record dashboards-export-exists "$rc" "$tmp/work/exists.json"
: > "$tmp/dashboards-export-force.log"
(cd "$tmp/work" && HOME="$tmp/home" python3 "$DRIVER" "$CLI" "$tmp/r-common.json" --log "$tmp/dashboards-export-force.log" -- \
  dashboards --export 0199aaaa-bbbb-7ccc-8ddd-eeeeeeee0001 exists.json --force --md) > "$tmp/dashboards-export-force.out" 2> "$tmp/dashboards-export-force.err"
rc=$?; check_rc "$rc" 1 dashboards-export-force
cases=$((cases + 1))
if cmp -s "$tmp/work/dash.json" "$tmp/work/exists.json"; then echo "PASS dashboards-export-force (overwritten)"
else echo "FAIL dashboards-export-force: --force did not write the export"; fail=1; fi
# An empty answer (OBS_DRY_RUN=1 without fixtures answers {}) writes nothing.
: > "$tmp/dashboards-export-empty.log"
(cd "$tmp/work" && HOME="$tmp/home" OBS_DRY_RUN=1 OBS_DRY_RUN_LOG="$tmp/dashboards-export-empty.log" python3 "$CLI" \
  --backend grafana dashboards --export api-red empty.json --md) > "$tmp/dashboards-export-empty.out" 2> "$tmp/dashboards-export-empty.err"
rc=$?; check_rc "$rc" 1 dashboards-export-empty; record dashboards-export-empty "$rc"
cases=$((cases + 1))
if [ -e "$tmp/work/empty.json" ]; then echo "FAIL dashboards-export-empty-file: a file was written"; fail=1
else echo "PASS dashboards-export-empty-file (nothing written)"; fi
# ----------------------------------------------------------------------------- lint
l  lint-prom-ok           0 lint lint/rules-ok.json --md
l  lint-prom-findings     1 lint lint/rules-bad.json --md
l  lint-signoz-alert      1 lint lint/signoz-alert.json --json
l  lint-grafana-dashboard 1 lint lint/dashboard-bad.json --md
l  lint-prom-prefix       1 lint lint/rules-prefix.json --md       # HighLatency is a prefix of HighLatencyCritical
cases=$((cases + 1))
if grep -qF 'rules-prefix.json:19 | alert HighLatency has no `for:`' "$tmp/lint-prom-prefix.txt" \
   && ! grep -qF 'rules-prefix.json:7 | alert HighLatency ' "$tmp/lint-prom-prefix.txt"; then echo "PASS lint-prom-prefix-line"
else echo "FAIL lint-prom-prefix-line: HighLatency not reported at line 19"; fail=1; fi
# YAML needs PyYAML (optional): exit 0 with it, exit 1 and a "PyYAML" finding without it.
if python3 -c 'import yaml' 2>/dev/null; then want=0; else want=1; fi
(cd "$FIX" && python3 "$CLI" lint lint/rules-ok.yaml --md) > "$tmp/yaml.out" 2>&1; rc=$?
cases=$((cases + 1))
if [ "$rc" = "$want" ] && { [ "$want" = 0 ] || grep -q PyYAML "$tmp/yaml.out"; }; then echo "PASS lint-prom-yaml (exit $rc)"
else echo "FAIL lint-prom-yaml: exit $rc, expected $want"; cat "$tmp/yaml.out"; fail=1; fi
# ---------------------------------------------------------------------- errors, prod
t  err-401                2 401 alerts --md
t  err-unreachable        2 unreachable query up --md
t  err-redirect           2 redirect alerts --md                   # a 3xx is never followed: the key stays on the host
cases=$((cases + 1))
if grep -q 'login.example.net' "$tmp/err-redirect.log"; then echo "FAIL err-redirect-host: a request reached the redirect target"; fail=1
else echo "PASS err-redirect-host (no request to the target)"; fi
t  err-html               2 html --backend prom query up --md        # a login page answering 200
t  err-404                2 404 alerts --md
t  probe-404              2 404 backends --probe --md               # 404 on the version endpoint: unreachable, with a note
# A backend url with userinfo is refused at load time; the credential is never printed.
python3 -c '
import json, sys
c = json.load(open(sys.argv[1]))
c["obs"]["backends"][0]["url"] = "https://admin:hunter2@signoz.example.com"  # pragma: allowlist secret (fake fixture value)
json.dump(c, open(sys.argv[2], "w"))
' "$tmp/config.json" "$tmp/config-userinfo.json"
HARNESS_CONFIG_JSON="$tmp/config-userinfo.json" t backends-url-userinfo 2 common backends --md
# obs.hosts_re is a POSIX ERE (the guard runs grep -E): Python-only syntax and dialect
# disagreements are findings.
OBS_HOSTS_RE='^(signoz|signoz-prod|grafana|prometheus)\d*\.example\.com$' t backends-hosts-re-pyonly 1 common backends --md
OBS_HOSTS_RE='^[[:alnum:].-]+$' t backends-hosts-re-dialect 1 common backends --md
# --------------------------------------------------------------------- --max-bytes
t  backends-truncated-json 0 common backends --json --max-bytes 900
cases=$((cases + 1))
if python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert d["truncated"]["items_dropped"] > 0 and d["truncated"]["max_bytes"] == 900' "$tmp/backends-truncated-json.out" \
   && [ "$(wc -c < "$tmp/backends-truncated-json.out")" -le 901 ]; then echo "PASS backends-truncated-json-valid"
else echo "FAIL backends-truncated-json-valid: not one whole JSON document within --max-bytes carrying truncated"; fail=1; fi
t  prod-banner            1 common --backend signoz-prod alerts --md
# --------------------------------------------------------------------------- redact
printf 'Authorization: Bearer test-bearer-0123456789abcdef\npassword=hunter2\nok line\n' > "$tmp/redact.in"
(cd "$tmp/work" && python3 "$CLI" redact < "$tmp/redact.in") > "$tmp/redact-text.out" 2> "$tmp/redact-text.err"
rc=$?; : > "$tmp/redact-text.log"; check_rc "$rc" 0 redact-text; record redact-text "$rc"
# The documented obs.redact_extra_re example (bundle.toml) starts with a global flag: it is
# compiled on its own, never spliced mid-pattern (re.error on Python 3.11+).
extra_example=$(python3 -c '
import re, sys
t = open(sys.argv[1]).read()
sec = t.split("[requires.config.\"obs.redact_extra_re\"]", 1)[1].split("\n[", 1)[0]
print(re.search(r"(?m)^example = \"(.*)\"$", sec).group(1))
' "$here/../../../../bundle.toml")
cases=$((cases + 1))
case "$extra_example" in
  "(?i)"*) echo "PASS redact-extra-re-example ($extra_example)" ;;
  *) echo "FAIL redact-extra-re-example: no (?i) example read from bundle.toml: $extra_example"; fail=1 ;;
esac
printf '{"msg": "GET /v1/items x-internal-token=abcd1234efgh5678 200", "auth": "Bearer test-bearer-0123456789abcdef"}\n' \
  | (cd "$tmp/work" && OBS_REDACT_EXTRA_RE="$extra_example" python3 "$CLI" redact --md) > "$tmp/redact-extra-re.out" 2> "$tmp/redact-extra-re.err"
rc=$?; : > "$tmp/redact-extra-re.log"; check_rc "$rc" 0 redact-extra-re; record redact-extra-re "$rc"
(cd "$tmp/work" && HOME="$tmp/home" OBS_REDACT_EXTRA_RE="$extra_example" python3 "$CLI" backends --md) > /dev/null 2> "$tmp/redact-extra-re-cmd.err"
rc=$?; cases=$((cases + 1))
if [ "$rc" = 0 ]; then echo "PASS redact-extra-re-backends"; else echo "FAIL redact-extra-re-backends: exit $rc"; cat "$tmp/redact-extra-re-cmd.err"; fail=1; fi
printf 'x\n' | (cd "$tmp/work" && OBS_REDACT_EXTRA_RE='x(' python3 "$CLI" redact) > "$tmp/redact-extra-re-bad.out" 2> "$tmp/redact-extra-re-bad.err"
rc=$?; : > "$tmp/redact-extra-re-bad.log"; check_rc "$rc" 1 redact-extra-re-bad; record redact-extra-re-bad "$rc"

# ------------------------------------------------------------------- dry-run requests
# The CLI's own dry-run path (no driver): every request is logged, none leaves the machine,
# responses come from fixtures/*/routes.json. Only GET, and POST to the query endpoints.
dry="$tmp/dry-run-requests.log"; : > "$dry"
: > "$tmp/dry-run-requests.out"; : > "$tmp/dry-run-requests.err"
for args in "backends --probe" "query up" "logs error --service checkout" "traces --service checkout" \
            "trace 4bf92f3577b34da6a3ce929d0e0e4736" "services" "alerts --firing --rules" "dashboards" \
            "dashboards --export 0199aaaa-bbbb-7ccc-8ddd-eeeeeeee0001 dry.json" \
            "--backend prom query up --range 1h" "--backend prom alerts --firing --rules" \
            "--backend grafana query up --datasource ds" "--backend grafana logs x --datasource ds" \
            "--backend grafana alerts --firing --rules" "--backend grafana dashboards" \
            "--backend grafana dashboards --export api-red dry2.json"; do
  # shellcheck disable=SC2086
  (cd "$tmp/work" && HOME="$tmp/home" OBS_DRY_RUN=1 OBS_DRY_RUN_LOG="$dry" OBS_HTTP_FIXTURES="$FIX" \
    python3 "$CLI" $args --json) > /dev/null 2>> "$tmp/dry-run-requests.err"
done
cases=$((cases + 1))
bad=$(grep -vE '^(GET https://[a-z.-]+\.example\.com/[^ ]*|POST https://[a-z.-]+\.example\.com/api/(v5/query_range|v1/services|ds/query))$' "$dry")
if [ -n "$bad" ] || grep -qE '^(PUT|PATCH|DELETE) ' "$dry" || [ ! -s "$dry" ]; then
  echo "FAIL dry-run-requests: non-read request(s) or empty log:"; echo "$bad"; fail=1
else echo "PASS dry-run-requests (allow-list: $(wc -l < "$dry" | tr -d ' ') requests)"; fi
cp "$dry" "$tmp/dry-run-requests.out"; : > "$tmp/dry-run-requests.log"
record dry-run-requests 0

# ---------------------------------------------------------------------------- usage
python3 "$CLI" > "$tmp/usage.out" 2>&1; rc=$?
cases=$((cases + 1))
if [ "$rc" = 1 ] && grep -q '^Commands' "$tmp/usage.out"; then echo "PASS usage"; else echo "FAIL usage (exit $rc)"; fail=1; fi

echo "----"
[ $fail -eq 0 ] && echo "obs: $cases cases passed" || echo "obs: FAILED ($cases cases)"
exit $fail
