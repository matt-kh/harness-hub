#!/usr/bin/env bash
# Doctor check ticket-workflow-trackers (offline, read-only): validates ticket_workflow.trackers,
# the user's per-remote tracker declarations, read as a JSON array on stdin (the doctor command
# templates the configured value into a here-document).
#   every entry is a table with `match` (an ERE that compiles under grep -E), `tracker`
#   (github-issues | jira) and `project` only together with tracker = "jira".
# The first output line is the doctor's detail: on failure it names the entry index and the fix.
# Exit 0 valid (or nothing declared), 1 a problem. bash 3.2, jq, grep -E.
set -uo pipefail
json=$(cat)
[ -n "$json" ] || json='[]'
if ! n=$(jq -er 'if type == "array" then length else error("not an array") end' <<<"$json" 2>/dev/null); then
  echo "ticket_workflow.trackers is not a list of tables; write each entry as [[ticket_workflow.trackers]] with match and tracker"
  exit 1
fi
if [ "$n" -eq 0 ]; then
  echo "no ticket_workflow.trackers: .harness.toml [repo] tracker, else the host decides (github.com -> github-issues, GitLab -> jira)"
  exit 0
fi
problems=""
add() { problems="${problems}ticket_workflow.trackers[$1]: $2
"; }
i=0
while [ "$i" -lt "$n" ]; do
  if [ "$(jq -r --argjson i "$i" '.[$i] | type' <<<"$json")" != object ]; then
    add "$i" "is not a table; write it as [[ticket_workflow.trackers]] with match and tracker"
    i=$((i + 1)); continue
  fi
  m=$(jq -r --argjson i "$i" '.[$i].match // "" | strings' <<<"$json")
  t=$(jq -r --argjson i "$i" '.[$i].tracker // "" | strings' <<<"$json")
  p=$(jq -r --argjson i "$i" '.[$i].project // "" | strings' <<<"$json")
  if [ -z "$m" ]; then
    add "$i" "match is empty; set match = \"^host/group/\" (an ERE on <host>/<path> of origin)"
  else
    # an invalid ERE: grep exits 2 (GNU, BSD) or 1 with a message; one input line, since
    # some greps compile the pattern only when they read input
    ge=$(grep -E -- "$m" <<<"example.com/owner/repo" 2>&1 >/dev/null); rc=$?
    if [ "$rc" -ge 2 ] || { [ "$rc" -eq 1 ] && [ -n "$ge" ]; }; then
      add "$i" "match '$m' is not a valid ERE (grep -E); escape dots and close every group, e.g. match = \"^github\\\\.com/owner/\""
    fi
  fi
  case "$t" in
    github-issues|jira) ;;
    *) add "$i" "tracker '$t' is not github-issues or jira; set tracker = \"github-issues\" or \"jira\"" ;;
  esac
  if [ -n "$p" ] && [ "$t" != jira ]; then
    add "$i" "project '$p' needs tracker = \"jira\"; remove project or set tracker = \"jira\""
  fi
  i=$((i + 1))
done
if [ -n "$problems" ]; then
  printf '%s' "$problems"
  exit 1
fi
echo "$n tracker declaration(s): every match compiles, every tracker is github-issues or jira"
exit 0
