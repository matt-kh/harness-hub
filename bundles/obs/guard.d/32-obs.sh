# shellcheck shell=bash

# Section 32 (bundle obs): observability backends — API keys, raw backend access, alert state.
# OBS_HOSTS_RE (guard.env, obs.hosts_re): ERE on a backend's host name (no scheme, no port);
# empty disables the host rows. HOME_RE and READER_RE come from core section 20.
OBS_HOSTS="${OBS_HOSTS_RE:-}"
OBS_CLIENT_RE='(^|[^[:alnum:]_./-])(curl|wget|xh|https?)([[:space:]]|$)'
OBS_LITERAL_KEY_RE='(authorization[[:space:]]*:[[:space:]]*["'"'"']?((bearer|basic|token)[[:space:]]+)?|(signoz-api-key|x-api-key)[[:space:]]*:[[:space:]]*["'"'"']?)[A-Za-z0-9._~+/=-]{8,}'
OBS_LITERAL_PARAM_RE='[?&](api_key|apikey|api-key)=[A-Za-z0-9._~+/=-]{8,}'
# never-yields: prints the developer's stored observability API key (principle 8 exemption; runs even when the repository owns operations)
# rule: <reader> ~/.config/obs/* -> deny : API key files; run 'obs backends' to see auth status instead
printf '%s' "$flat" | grep -qE "${READER_RE}${HOME_RE}/\.config/obs([/\"' ]|$)" && deny "reading ~/.config/obs/* prints an observability API key — run 'obs backends' to see each key's status (present, mode, missing) instead"
repo_owns obs/guard.d/32-obs operations && return 0   # principle 8: the repository's .harness.toml owns this section or domain operations
# rule: curl|wget|http|xh ... -H 'Authorization|SIGNOZ-API-KEY|X-API-Key: <literal>' | ?api_key=<literal> -> deny : API key on the command line; use the obs CLI instead (it reads the key file)
# rule: curl|wget|http|xh <host matching OBS_HOSTS_RE> -> ask : raw backend access; use the obs CLI (bounded, redacted, read-only) instead
# rule: amtool silence add|expire|import | amtool alert add -> ask : changes alert state; hand the command to the user, or change the alert rule in the repo instead
# rule: logcli query --tail|-f -> ask : never returns; pass --since and --limit instead
# rule: grafana-cli admin|plugins install|remove -> ask : Grafana admin mutation; hand the command to the user, or change the chart values instead
if printf '%s' "$flat" | grep -qE "$OBS_CLIENT_RE"; then
  if printf '%s' "$flat" | grep -qiE "$OBS_LITERAL_KEY_RE" || printf '%s' "$flat" | grep -qiE "$OBS_LITERAL_PARAM_RE"; then
    deny "API key or bearer token written on the command line (it lands in shell history and transcripts) — use the obs CLI instead, which reads the key file; for another API pass the token from a variable"
  fi
  if [ -n "$OBS_HOSTS" ]; then
    # one word per line, no subshell (ask must exit the hook) and no glob expansion
    while IFS= read -r _ow; do
      case "$_ow" in *.*) ;; *) continue ;; esac
      _oh=${_ow#*://}; _oh=${_oh#*@}; _oh=${_oh%%[/:?#]*}
      [ -n "$_oh" ] || continue
      printf '%s' "$_oh" | grep -qE -- "$OBS_HOSTS" 2>/dev/null \
        && ask "raw request to observability backend $_oh — use the obs CLI instead (bounded, redacted, read-only): obs backends, obs query|logs|traces|alerts"
    done <<EOF
$(printf '%s' "$flat" | tr "\"'=[:space:]" '\n\n\n\n')
EOF
  fi
fi
printf '%s' "$flat" | grep -qE '\bamtool\b[^;&|]*[[:space:]](silence[[:space:]]+(add|expire|import)|alert[[:space:]]+add)\b' \
  && ask "amtool changes alert state (silence or alert) — hand the command to the user, or change the alert rule in the repository instead"
printf '%s' "$flat" | grep -qE '\blogcli\b[^;&|]*[[:space:]]query\b[^;&|]*[[:space:]](--tail|-t|-f|--follow)([[:space:]=]|$)' \
  && ask "logcli --tail never returns — pass --since and --limit instead, or use 'obs logs' through a grafana backend"
printf '%s' "$flat" | grep -qE '\bgrafana-cli\b[^;&|]*[[:space:]](admin|plugins[[:space:]]+(install|remove|uninstall|update|update-all))\b' \
  && ask "grafana-cli admin/plugin mutation — hand the command to the user, or change the chart values instead"
