# shellcheck shell=bash
# work-ticket: provider-neutral, READ-ONLY repo facts. Sourced by preflight.sh (dispatcher),
# gitlab-preflight.sh and github-preflight.sh. Never writes; never prints remote URLs.
#
# Functions:
#   rf_root            -> prints the repo toplevel (exit 1 outside a git repo)
#   rf_host ROOT       -> prints the origin remote host (credentials/user/scheme/path stripped)
#   rf_provider HOST   -> prints github | gitlab | (empty = unknown). GitLab hosts: the regex
#                         $HARNESS_GITLAB_HOSTS_RE, else the literal host $HARNESS_GITLAB_HOST,
#                         else gitlab.host from the harness config,
#                         plus any host containing "gitlab"
#   rf_load            -> sets root host def dirty precommit repo_skill (exits with JSON error
#                         outside a git repo, exactly like the original preflight)

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

rf_root() { git rev-parse --show-toplevel 2>/dev/null; }

rf_host() {
  git -C "$1" remote get-url origin 2>/dev/null | sed -E 's#^[a-z]+://([^@/]*@)?##; s#^[^@]*@##; s#[:/].*$##'
}

rf_provider() {
  local h re gl
  h=$(printf '%s' "$1" | LC_ALL=C tr '[:upper:]' '[:lower:]')
  re="${HARNESS_GITLAB_HOSTS_RE:-}"
  if [ -z "$re" ]; then
    gl="${HARNESS_GITLAB_HOST:-}"
    [ -n "$gl" ] || gl=$(hcfg gitlab.host)
    [ -z "$gl" ] || re="^$(printf '%s' "$gl" | sed 's/[.]/\\./g')\$"
  fi
  case "$h" in
    github.com|ssh.github.com|www.github.com) echo github; return 0 ;;
  esac
  if [ -n "$re" ] && printf '%s' "$h" | grep -qiE -- "$re"; then echo gitlab; return 0; fi
  case "$h" in
    *gitlab*) echo gitlab ;;
    *)        echo "" ;;
  esac
}

# shellcheck disable=SC2034  # rf_load sets globals for the sourcing script (see header), not for this file
rf_load() {
  root=$(rf_root) || { echo '{"error":"not a git repo"}'; exit 1; }
  host=$(rf_host "$root")
  def=$(git -C "$root" symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##')
  repo_skill=""
  if [ -f "$root/.claude/skills/work-jira-ticket/SKILL.md" ]; then
    repo_skill="$root/.claude/skills/work-jira-ticket/SKILL.md"
  else
    repo_skill=$(grep -lsiE '^description:.*(jira|github|issue).*(ticket|issue)' "$root"/.claude/skills/*/SKILL.md 2>/dev/null | head -1)
  fi
  dirty=$(git -C "$root" status --porcelain | wc -l | tr -d ' ')
  precommit=false; [ -f "$root/.pre-commit-config.yaml" ] && precommit=true
  return 0
}
