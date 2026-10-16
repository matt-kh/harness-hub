# shellcheck shell=bash
# Guard test rows for bundle obs. Sourced by bundles/core/guard/tests/run.sh after lib.sh
# (helpers: t EXPECTED 'cmd' | tc EXPECTED CWD 'cmd' | tr 'reason-re' 'cmd' | decl … + r EXPECTED 'cmd').
# OBS_HOSTS_RE is set for the host rows below and unset at the end (rows of other bundles
# share this shell).
export OBS_HOSTS_RE='^(signoz|grafana|prometheus)\.example\.com$'

# ---- the obs CLI and other reads pass ------------------------------------------------
t pass  'obs backends --probe'
t pass  'obs query "sum(rate(calls_total[5m])) by (service_name)" --backend signoz-dev'
t pass  'obs logs "severity_text = '"'"'ERROR'"'"'" --service checkout --limit 50'
t pass  'obs dashboards --export api-red dashboards/api-red.json'
t pass  'ls -la ~/.config/obs/'
t pass  'stat ~/.config/obs/signoz-dev.key'
t pass  'install -m 600 /dev/null ~/.config/obs/signoz-dev.key'
t pass  'curl -s https://example.com/healthz'
t pass  'curl -fsSL https://downloads.example.org/tool.tar.gz -o /tmp/tool.tgz'
t pass  'wget https://www.example.org/'
t pass  'curl -H "Authorization: Bearer $TOKEN" https://api.example.org/v1/items'   # a variable, not a literal; host outside OBS_HOSTS_RE
t pass  'curl -H "Authorization: Bearer <token>" https://api.example.org/v1/items' # a placeholder
t pass  'promtool check rules rules/api.yaml'
t pass  'promtool test rules tests/api_test.yaml'
t pass  'amtool alert query --alertmanager.url=https://am.example.org'
t pass  'amtool silence query'
t pass  'logcli query --since 1h --limit 100 "{app=\"api\"}"'
t pass  'grafana-cli plugins ls'
t pass  'echo "see https://signoz.example.com/alerts in the browser"'                  # no HTTP client
# ---- API key files: never read (never-yields prelude) --------------------------------
t deny  'cat ~/.config/obs/signoz-dev.key'
t deny  'cat $HOME/.config/obs/grafana.key'
t deny  'head -1 /home/u/.config/obs/prom.key'
t deny  'grep . ~/.config/obs/*.key'
t deny  'cp ~/.config/obs/signoz-dev.key /tmp/k'
t deny  'sh -c "cat ~/.config/obs/signoz-dev.key"'                                      # bypass: wrapped
t deny  'cd /tmp && base64 ~/.config/obs/signoz-dev.key'
t deny  'curl -H "SIGNOZ-API-KEY: $(cat ~/.config/obs/signoz-dev.key)" https://signoz.example.com/api/v1/rules'
tr 'obs backends'      'cat ~/.config/obs/signoz-dev.key'
# ---- literal API keys on the command line: deny --------------------------------------
t deny  'curl -H "SIGNOZ-API-KEY: sk0123456789abcdef" https://signoz.example.com/api/v1/rules'
t deny  "curl -H 'Authorization: Bearer glsa_0123456789abcdef' https://grafana.example.com/api/search"
t deny  'curl --header "X-API-Key: 0123456789abcdef" https://api.example.org/v1/items'     # any host: the key is still on the command line
t deny  'curl -H "authorization:bearer 0123456789abcdef" https://prometheus.example.com/api/v1/query?query=up'
t deny  'wget --header="Authorization: Bearer 0123456789abcdef" https://grafana.example.com/api/health'
t deny  'http GET https://grafana.example.com/api/search Authorization:"Bearer 0123456789abcdef"'
t deny  'xh https://signoz.example.com/api/v1/rules SIGNOZ-API-KEY:0123456789abcdef'
t deny  'curl "https://grafana.example.com/api/search?api_key=0123456789abcdef"'
t deny  'curl "https://api.example.org/v1/items?limit=1&apikey=0123456789abcdef"'
t deny  'sh -c "curl -H \"SIGNOZ-API-KEY: sk0123456789abcdef\" https://signoz.example.com/api/v1/rules"'   # bypass: wrapped
t deny  'bash -lc '"'"'curl -H "Authorization: Bearer 0123456789abcdef" https://grafana.example.com/api/search'"'"
t deny  'env X=1 curl -H "SIGNOZ-API-KEY: sk0123456789abcdef" https://signoz.example.com/api/v1/rules'
t deny  'cd /tmp && curl -sH "SIGNOZ-API-KEY: sk0123456789abcdef" https://signoz.example.com/api/v1/rules'
t deny  'echo https://signoz.example.com/api/v1/rules | xargs curl -H "SIGNOZ-API-KEY: sk0123456789abcdef"'
tr 'use the obs CLI'   'curl -H "SIGNOZ-API-KEY: sk0123456789abcdef" https://signoz.example.com/api/v1/rules'
tr 'from a variable'   'curl -H "X-API-Key: 0123456789abcdef" https://api.example.org/v1/items'
# ---- raw requests to a backend host (OBS_HOSTS_RE): ask ------------------------------
t ask   'curl https://signoz.example.com/api/v1/rules'
t ask   'curl -s "https://grafana.example.com/api/search?query=api"'
t ask   "curl -s 'https://prometheus.example.com/api/v1/query?query=up'"
t ask   'curl -H "SIGNOZ-API-KEY: $SIGNOZ_KEY" https://signoz.example.com/api/v1/rules'      # a variable: not a literal, still a raw backend call
t ask   'curl -sk https://user@grafana.example.com:3000/api/health'                          # userinfo and port stripped
t ask   'wget -qO- https://prometheus.example.com/api/v1/alerts'
t ask   'curl signoz.example.com/api/v1/version'                                             # no scheme
t ask   'sh -c "curl https://signoz.example.com/api/v1/rules"'                                # bypass: wrapped
t ask   'bash -lc "curl -s https://grafana.example.com/api/health"'
t ask   'echo https://signoz.example.com/api/v1/rules | xargs curl'
t ask   'env X=1 curl https://signoz.example.com/api/v1/rules'
t ask   'cd /tmp && curl https://signoz.example.com/api/v1/rules'
t ask   'curl --url=https://signoz.example.com/api/v1/rules'
t ask   'curl https://example.com/a; curl https://signoz.example.com/api/v1/rules'
tr 'use the obs CLI'   'curl https://signoz.example.com/api/v1/rules'
OBS_HOSTS_RE='' t pass 'curl https://signoz.example.com/api/v1/rules'                       # empty regex: host rows off
OBS_HOSTS_RE='' t pass 'wget -qO- https://prometheus.example.com/api/v1/alerts'
OBS_HOSTS_RE='' t deny 'curl -H "SIGNOZ-API-KEY: sk0123456789abcdef" https://signoz.example.com/api/v1/rules'   # literal keys deny regardless
# ---- alert state, live tails, Grafana admin: ask -------------------------------------
t ask   'amtool silence add alertname=ApiDown --comment=maintenance --duration=2h'
t ask   'amtool --alertmanager.url=https://am.example.org silence expire 0123'
t ask   'amtool silence import < silences.json'
t ask   'amtool alert add alertname=Test severity=info'
t ask   'sh -c "amtool silence add alertname=ApiDown"'                                     # bypass: wrapped
t ask   'logcli query --tail "{app=\"api\"}"'
t ask   'logcli query -f "{app=\"api\"}"'
t ask   'logcli --addr=https://loki.example.org query --since 1h --follow "{app=\"api\"}"'
t ask   'grafana-cli admin reset-admin-password changeme'
t ask   'grafana-cli plugins install grafana-piechart-panel'
t ask   'grafana-cli plugins remove grafana-piechart-panel'
tr 'hand the command to the user' 'amtool silence add alertname=ApiDown'
tr 'pass --since and --limit'     'logcli query --tail "{app=\"api\"}"'
tr 'change the chart values'      'grafana-cli plugins install grafana-piechart-panel'
# ---- repository-level declaration: .harness.toml (principle 8) -----------------------
decl '[owns]' 'domains = ["operations"]'
r pass  'curl https://signoz.example.com/api/v1/rules'                                    # the repository's harness decides
r pass  'curl -H "SIGNOZ-API-KEY: sk0123456789abcdef" https://signoz.example.com/api/v1/rules'
r pass  'amtool silence add alertname=ApiDown'
r pass  'logcli query --tail "{app=\"api\"}"'
r pass  'grafana-cli admin reset-admin-password changeme'
r deny  'cat ~/.config/obs/signoz-dev.key'                                                # never yields: a stored credential
r deny  'sh -c "head -1 ~/.config/obs/grafana.key"'
decl '[owns]' 'components = ["obs/guard.d/32-obs"]'
r pass  'curl https://signoz.example.com/api/v1/rules'
r deny  'cat ~/.config/obs/signoz-dev.key'
decl '[owns]' 'domains = ["kubernetes", "scm"]'                                           # another domain: no yield
r ask   'curl https://signoz.example.com/api/v1/rules'
decl '[overrides]' 'OBS_HOSTS_RE = "^$"'                                                  # bypass: not a repo override
r ask   'curl https://signoz.example.com/api/v1/rules'
decl
unset OBS_HOSTS_RE
