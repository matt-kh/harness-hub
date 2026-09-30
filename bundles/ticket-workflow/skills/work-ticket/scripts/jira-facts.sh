#!/usr/bin/env bash
# work-ticket Jira facts for sub-ticket creation: READ-ONLY, prints one JSON object.
# Usage: jira-facts.sh <PARENT-KEY>
set -uo pipefail
key="${1:-}"; [ -n "$key" ] || { echo '{"error":"usage: jira-facts.sh KEY"}'; exit 1; }
proj="${key%%-*}"

me=$(jira whoami 2>/dev/null | jq -r '.name // empty')
perms=$(jira api "/rest/api/2/mypermissions?projectKey=$proj" 2>/dev/null | jq -c '
  .permissions | {create: (.CREATE_ISSUES.havePermission // false), link: (.LINK_ISSUES.havePermission // false),
                  edit: (.EDIT_ISSUES.havePermission // false), transition: (.TRANSITION_ISSUES.havePermission // false),
                  delete: (.DELETE_ISSUES.havePermission // false)}' 2>/dev/null)
[ -n "$perms" ] || perms='{"create":false,"link":false,"edit":false,"transition":false,"delete":false}'

types=$(jira api "/rest/api/2/project/$proj" 2>/dev/null | jq -c '
  [.issueTypes[]? | select(.subtask == false) | .name
   | select(. != "Epic" and . != "Bug" and . != "Defects" and . != "CR")]' 2>/dev/null)
[ -n "$types" ] || types='[]'

link_types=$(jira api /rest/api/2/issueLinkType 2>/dev/null | jq -c '[.issueLinkTypes[]?.name]' 2>/dev/null)
[ -n "$link_types" ] || link_types='[]'
link_type=$(jq -r 'if index("Issue split") then "Issue split" elif index("Relates") then "Relates" else empty end' <<<"$link_types")

parent=$(jira get "$key" 2>/dev/null | jq -c '{type, status, assignee, labels, sprint, fixVersions, components, priority, epicLink, storyPoints, links}' 2>/dev/null)
[ -n "$parent" ] || parent='null'

# Which existing children (split to / blocks-style) already hang off the parent?
children=$(jq -c '[.links[]? | select(.direction == "split to") | .key]' <<<"$parent" 2>/dev/null); [ -n "$children" ] || children='[]'

jq -n --arg me "$me" --arg proj "$proj" --arg lt "$link_type" \
      --argjson perms "$perms" --argjson types "$types" --argjson link_types "$link_types" \
      --argjson parent "$parent" --argjson children "$children" '
{me:$me, project:$proj, perms:$perms,
 sub_ticket_types:$types, preferred_type:(if ($parent.type // "") as $t | ($types | index($t)) then $parent.type
                                          elif ($types | index("Task")) then "Task" else ($types[0] // null) end),
 link_types:$link_types, link_type:(if $lt=="" then null else $lt end),
 parent:$parent, existing_children:$children,
 sub_tickets_available:($perms.create and $perms.link and ($types|length>0) and $lt!="")}'
