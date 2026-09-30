# shellcheck shell=bash
# Shell twin of harness_config.py: hcfg KEY [DEFAULT] prints the value of a dotted key from
# the compiled harness config ($HARNESS_CONFIG_JSON, else ${HARNESS_HOME:-~/harness-hub}/build/config.json).
# Strings print as-is, other values as compact JSON; missing key/file -> DEFAULT (or nothing).
# Needs jq. Skill shell scripts carry an inlined copy between the markers (checked by core tests).

# >>> hcfg
hcfg() {  # KEY [DEFAULT]
  local f="${HARNESS_CONFIG_JSON:-${HARNESS_HOME:-$HOME/harness-hub}/build/config.json}" v=""
  if [ -r "$f" ] && command -v jq >/dev/null 2>&1; then
    v=$(jq -r --arg k "$1" 'try (getpath($k | split(".")) // empty | if type == "string" then . else tojson end) catch empty' "$f" 2>/dev/null) || v=""
  fi
  if [ -n "$v" ]; then printf '%s\n' "$v"; elif [ $# -ge 2 ]; then printf '%s\n' "$2"; fi
  return 0
}
# <<< hcfg
