#!/usr/bin/env bash
# work-ticket GitHub issue facts (twin of jira-facts.sh): READ-ONLY, prints one JSON object.
# Usage: issue-facts.sh <N | #N | owner/repo#N | https://github.com/owner/repo/issues/N>
# Repo: from the ref, else `gh repo set-default --view`, else the parent of a fork origin, else origin.
# Every gh call is wrapped in `hn_timeout 20` and tolerated (partial JSON, never a crash).
# Override the binary with WORK_TICKET_GH (tests / stubs).
set -uo pipefail
# >>> hn_timeout
hn_timeout() {  # SECS CMD [ARGS...]
  local s=$1; shift
  if command -v timeout >/dev/null 2>&1; then timeout "$s" "$@"
  elif command -v gtimeout >/dev/null 2>&1; then gtimeout "$s" "$@"
  else
    python3 -c 'import subprocess, sys
try:
    sys.exit(subprocess.call(sys.argv[2:], timeout=float(sys.argv[1])))
except subprocess.TimeoutExpired:
    sys.exit(124)
except OSError:
    sys.exit(127)' "$s" "$@"
  fi
}
# <<< hn_timeout
ref="${1:-}"; [ -n "$ref" ] || { echo '{"error":"usage: issue-facts.sh N|#N|owner/repo#N|URL"}'; exit 1; }
GH="${WORK_TICKET_GH:-gh}"
export GH_PROMPT_DISABLED=1 GH_NO_UPDATE_NOTIFIER=1 GH_PAGER=cat NO_COLOR=1
root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
ghc() { command -v "$GH" >/dev/null 2>&1 || return 127; (cd "$root" && hn_timeout 20 "$GH" "$@" 2>/dev/null); }
json_or() { local v="$1" d="$2"; if [ -n "$v" ] && jq -e . <<<"$v" >/dev/null 2>&1; then printf '%s' "$v"; else printf '%s' "$d"; fi; }

repo="" num=""
case "$ref" in
  http*://github.com/*/*/issues/[0-9]*) p="${ref#*://github.com/}"; repo=$(cut -d/ -f1,2 <<<"$p"); num=$(cut -d/ -f4 <<<"$p" | grep -oE '^[0-9]+') ;;
  */*\#[0-9]*) repo="${ref%%#*}"; num="${ref##*#}" ;;
  \#[0-9]*)    num="${ref#\#}" ;;
  *)           num="$ref" ;;
esac
[[ "$num" =~ ^[0-9]+$ ]] || { jq -cn --arg r "$ref" '{error:"not an issue ref", ref:$r}'; exit 1; }

auth_ok=false; ghc auth status --hostname github.com >/dev/null && auth_ok=true
if [ -z "$repo" ] && [ "$auth_ok" = true ]; then
  repo=$(ghc repo set-default --view | tr -d '[:space:]'); [[ "$repo" == */* ]] || repo=""
fi
if [ -z "$repo" ]; then
  origin=$(git -C "$root" remote get-url origin 2>/dev/null \
    | sed -E 's#^[a-z]+://([^@/]*@)?[^/:]+[:/]##; s#^[^@]*@[^:]+:##; s#\.git$##; s#/+$##' | cut -d/ -f1,2)
  repo="$origin"
  if [ "$auth_ok" = true ] && [ -n "$origin" ]; then
    par=$(ghc repo view "$origin" --json isFork,parent | jq -r 'if .isFork then "\(.parent.owner.login)/\(.parent.name)" else "" end' 2>/dev/null)
    [[ "$par" == */* ]] && repo="$par"
  fi
fi

me='' repo_view='null' issue='null' subs='[]' parent='null'
if [ "$auth_ok" = true ] && [ -n "$repo" ]; then
  me=$(ghc api user | jq -r '.login // empty' 2>/dev/null)
  repo_view=$(json_or "$(ghc repo view "$repo" --json nameWithOwner,viewerPermission,hasIssuesEnabled,isPrivate)" 'null')
  issue=$(json_or "$(ghc issue view "$num" -R "$repo" --json number,title,body,state,labels,assignees,milestone,comments,url)" 'null')
  subs=$(json_or "$(ghc api "repos/$repo/issues/$num/sub_issues?per_page=100" \
           | jq -c '[.[]? | {number, title, state, labels:[.labels[]?.name]}]' 2>/dev/null)" '[]')
  parent=$(json_or "$(ghc api "repos/$repo/issues/$num/parent" | jq -c '{number, title, state, labels:[.labels[]?.name]}' 2>/dev/null)" 'null')
  # `gh issue view` also resolves pull-request numbers; the REST issue object carries `pull_request` for those.
  is_pr=$(ghc api "repos/$repo/issues/$num" | jq -r 'has("pull_request")' 2>/dev/null); [ "$is_pr" = true ] || is_pr=false
fi
: "${is_pr:=null}"

jq -n --arg me "$me" --arg repo "$repo" --argjson num "$num" --argjson auth "$auth_ok" \
      --argjson rv "$repo_view" --argjson issue "$issue" --argjson subs "$subs" --argjson parent "$parent" --argjson ispr "$is_pr" '
def nn: if . == "" then null else . end;
($issue | if . == null then null else
   . + {labels:[.labels[]?.name], assignees:[.assignees[]?.login], milestone:(.milestone.title // null)} end) as $i
| ($rv.viewerPermission // null) as $perm
| (if $perm == null then null else ([$perm] | inside(["WRITE","MAINTAIN","ADMIN"])) end) as $canlabel
| {provider:"github", auth_ok:$auth, me:($me|nn), repo:($repo|nn), number:$num,
   perms:{viewer_permission:$perm, can_label:$canlabel, has_issues:$rv.hasIssuesEnabled, is_private:$rv.isPrivate},
   issue:$i, is_pull_request:$ispr,
   agent_labelled:(if $i == null then null else ($i.labels | any(startswith("agent-"))) end),
   parent:$parent,
   existing_children:[$subs[].number], sub_issues:$subs,
   sub_tickets_available:((($rv.hasIssuesEnabled // false) and ($canlabel // false)))}'
