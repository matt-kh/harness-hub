#!/usr/bin/env bash
# work-ticket preflight dispatcher: READ-ONLY. Detects the provider from the origin remote host
# and execs the provider preflight with the same arguments; its JSON object is the output.
#   github.com                          -> github-preflight.sh [ISSUE] [CANDIDATE_BRANCH ...]
#   HARNESS_GITLAB_HOSTS_RE / gitlab.host / *gitlab*  -> gitlab-preflight.sh [CANDIDATE_BRANCH ...]
#   anything else                       -> {"error":"provider unknown",...}, exit 1
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/repo-facts.sh
. "$here/lib/repo-facts.sh"
root=$(rf_root) || { echo '{"error":"not a git repo"}'; exit 1; }
host=$(rf_host "$root")
provider=$(rf_provider "$host")
if [ -z "$provider" ]; then
  jq -cn --arg host "$host" --arg root "$root" \
    '{error:"provider unknown", remote_host:(if $host=="" then null else $host end), repo_root:$root,
      hint:"origin must be github.com or a GitLab host (set gitlab.host in the harness config or HARNESS_GITLAB_HOSTS_RE)"}'
  exit 1
fi
exec "$here/${provider}-preflight.sh" "$@"
