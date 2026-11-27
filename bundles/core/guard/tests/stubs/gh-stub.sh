#!/usr/bin/env bash
# Stub gh for guard-bash hook tests (git-stub style; no network). Answers only
#   gh pr view REF [-R owner/repo] --json …      gh issue view REF [-R owner/repo] --json …
#   gh stack view --json                         (the gh-stack extension; GH_STUB_STACK=TRUNK)
# REF: N, #N, a github.com pull/issues URL, or (PRs) the head branch name. Labels are emitted the
# way gh emits them: [{"id","name","color"}]. Anything else -> stderr + exit 1 (a stray gh call is loud).
# PRs:    100 feat-x               [agent-worked] -> main
#         110 feat-x-sub-01-schema [agent-worked] -> feat-x
#         111 feat-x-sub-02-ui     [agent-worked] -> feat-x-sub-01-schema
#         112 feat-x-sub-03-docs   [bug]          -> feat-x-sub-02-ui
#         200 other                [bug]          -> main
#         210 feat-x-sub-02-api    [bug]          -> main   (auto-retargeted)
#         120 fork-fix             [agent-worked] -> main   isCrossRepository:true
#         113 feat-x-sub-04-misc   [agent-created] -> feat-x
#         114 feat-y-sub-01-done   [agent-worked] -> feat-y  (MERGED)
#         115 release-fix          [agent-worked] -> release
#         116 trunk-fix            [agent-worked] -> trunk
#         every PR is OPEN unless marked; `gh repo view [o/r] --json defaultBranchRef` answers
#         $GH_STUB_DEFAULT_BRANCH (default main); GH_STUB_REPO_FAIL=1 makes it fail
#         `pr view` / `repo view` know one repository: -R / --repo / a repo argument other than
#         o/r fails the way gh reports an unknown repository (rows can catch a repo mismatch)
# Issues: 1 [agent-worked]  2 [agent-drafted]  3 [bug]  4 []   others -> "Could not resolve to an Issue"
# Stack:  GH_STUB_STACK unset -> exit 2 (not in a stack); set -> trunk $GH_STUB_STACK with the layers
#         feat-x-sub-01-schema (PR 110) and feat-x-sub-02-ui (PR 111)
# Also answers ONE read-only GraphQL shape (section 41's batched lookup):
#   gh api [--hostname H] graphql -f query='query{repository(owner:"O",name:"R"){defaultBranchRef{name}
#     iN:issue(number:N){labels(first:50){nodes{name}}} … pN:pullRequest(number:N){baseRefName
#     headRefName isCrossRepository} …}}'
# with the issues and PRs below; the default branch is $GH_STUB_DEFAULT_BRANCH (default main). An
# unknown issue or PR is null plus an "errors" entry and exit 1, the way gh api reports it.
# Stacks REST API (gh-stack's native stacks; {owner}/{repo} or o/r):
#   gh api repos/O/R/stacks/N                  30: feat-x [110 merged, 111]   31: feat-x [110, 111, 112]
#                                              32: main [210]   33: feat-x [110, 120]   34: feat-x [110, 100]
#                                              35: feat-x [110, 113]
#                                              others -> 404, exit 1
#                                              GH_STUB_STACKS_FAIL=1: exit 1 with a 500 body (not a 404)
#   gh api repos/O/R/stacks?pull_request=N     110 -> [30]  111|112 -> [31]  120 -> [33]  100 -> [34]  113 -> [35]  others -> []
# The shape follows a recorded github.com response: pull_requests run bottom to top (part 1 first).
# `gh pr view` without a REF reads the current branch ($GIT_STUB_BRANCH, default feat-x-sub-02-ui);
# --jq/-q filters the output through jq -r.
# GH_STUB_LOG=FILE appends every call's arguments, one line each.
[ -z "${GH_STUB_LOG:-}" ] || printf '%s\n' "$*" >> "$GH_STUB_LOG"
stk_pr() {  # NUM STATE -> one stacks-API pull_requests entry
  printf '{"number":%s,"state":"%s","draft":false,"merged_at":%s,"head":{"ref":"x","sha":"0"}}' "$1" "$2" \
    "$( [ "$2" = closed ] && echo '"2026-01-01T00:00:00Z"' || echo null )"
}
stk() {  # NUM BASE PR[:closed]… -> one stack object
  local n=$1 b=$2 out="" p st; shift 2
  for p in "$@"; do st=open; case "$p" in *:closed) st=closed; p=${p%:closed} ;; esac; out="$out${out:+,}$(stk_pr "$p" "$st")"; done
  printf '{"number":%s,"base":{"ref":"%s"},"open":true,"pull_requests":[%s]}' "$n" "$b" "$out"
}
stk_by_num() {
  case "$1" in
    30) stk 30 feat-x 110:closed 111 ;;
    31) stk 31 feat-x 110 111 112 ;;
    32) stk 32 main 210 ;;
    33) stk 33 feat-x 110 120 ;;
    34) stk 34 feat-x 110 100 ;;
    35) stk 35 feat-x 110 113 ;;
    *) return 1 ;;
  esac
}
if [ "${1:-}" = api ]; then
  case "${2:-}" in
    repos/*/*/stacks\?pull_request=*)
      case "${2#*pull_request=}" in
        110) printf '[%s]\n' "$(stk_by_num 30)" ;;
        111|112) printf '[%s]\n' "$(stk_by_num 31)" ;;
        120) printf '[%s]\n' "$(stk_by_num 33)" ;;
        100) printf '[%s]\n' "$(stk_by_num 34)" ;;
        113) printf '[%s]\n' "$(stk_by_num 35)" ;;
        *) echo '[]' ;;
      esac
      exit 0 ;;
    repos/*/*/stacks/*)
      if [ -n "${GH_STUB_STACKS_FAIL:-}" ]; then echo '{"message":"Server Error","status":"500"}'; exit 1; fi
      stk_by_num "${2##*/}" && { echo; exit 0; }
      echo '{"message":"Not Found","status":"404"}'; echo "gh: Not Found (HTTP 404)" >&2; exit 1 ;;
  esac
  shift
  q=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --hostname) shift 2 ;;
      graphql) shift ;;
      -f|-F) case "${2:-}" in query=*) q=${2#query=} ;; esac; shift 2 ;;
      *) echo "gh-stub: unsupported api argument: $1" >&2; exit 1 ;;
    esac
  done
  case "$q" in 'query{repository(owner:"'*) ;; *) echo "gh-stub: unsupported api query" >&2; exit 1 ;; esac
  out="\"defaultBranchRef\":{\"name\":\"${GH_STUB_DEFAULT_BRANCH:-main}\"}"; err=0
  for a in $(printf '%s' "$q" | grep -oE '[ip][0-9]+:(issue|pullRequest)\(number:[0-9]+\)'); do
    al=${a%%:*}; num=${a##*number:}; num=${num%)}
    case "$a" in
      *issue*)
        case "$num" in
          1) v='{"labels":{"nodes":[{"name":"agent-worked"}]}}' ;;
          2) v='{"labels":{"nodes":[{"name":"agent-drafted"}]}}' ;;
          3) v='{"labels":{"nodes":[{"name":"bug"}]}}' ;;
          4) v='{"labels":{"nodes":[]}}' ;;
          *) v=null; err=1 ;;
        esac ;;
      *)
        case "$num" in
          100) v='{"baseRefName":"main","headRefName":"feat-x","isCrossRepository":false}' ;;
          110) v='{"baseRefName":"feat-x","headRefName":"feat-x-sub-01-schema","isCrossRepository":false}' ;;
          200) v='{"baseRefName":"main","headRefName":"other","isCrossRepository":false}' ;;
          210) v='{"baseRefName":"main","headRefName":"feat-x-sub-02-api","isCrossRepository":false}' ;;
          120) v='{"baseRefName":"main","headRefName":"fork-fix","isCrossRepository":true}' ;;
          *) v=null; err=1 ;;
        esac ;;
    esac
    out="$out,\"$al\":$v"
  done
  if [ "$err" = 1 ]; then
    printf '{"data":{"repository":{%s}},"errors":[{"type":"NOT_FOUND","message":"Could not resolve"}]}\n' "$out"
    exit 1
  fi
  printf '{"data":{"repository":{%s}}}\n' "$out"
  exit 0
fi
[ $# -ge 2 ] || { echo "gh-stub: usage: gh-stub.sh pr|issue view REF --json F" >&2; exit 1; }
noun=$1; verb=$2; shift 2
case "$noun $verb" in
  "pr view"|"issue view") ;;
  "repo view")
    [ -z "${GH_STUB_REPO_FAIL:-}" ] || { echo "gh-stub: repo view failed" >&2; exit 1; }
    jqx=""
    while [ $# -gt 0 ]; do
      case "$1" in
        -q|--jq) jqx=${2:-}; shift 2 ;;
        --json) shift 2 ;;
        -*) shift ;;
        *) [ "$1" = o/r ] || { echo "GraphQL: Could not resolve to a Repository with the name '$1'." >&2; exit 1; }; shift ;;
      esac
    done
    o=$(printf '{"defaultBranchRef":{"name":"%s"}}' "${GH_STUB_DEFAULT_BRANCH:-main}")
    if [ -n "$jqx" ]; then printf '%s\n' "$o" | jq -r "$jqx"; else printf '%s\n' "$o"; fi
    exit 0 ;;
  "stack view")
    [ "${1:-}" = --json ] || { echo "gh-stub: stack view needs --json" >&2; exit 1; }
    [ -n "${GH_STUB_STACK:-}" ] || { echo "not in a stack" >&2; exit 2; }
    # the gh-stack v0.3.0 schema (cmd/view.go); head is a commit, base the layer below
    printf '{"trunk":"%s","currentBranch":"%s","branches":[{"name":"feat-x-sub-01-schema","head":"0123abc","base":"%s","isCurrent":false,"isMerged":false,"isQueued":false,"needsRebase":false,"pr":{"number":110,"url":"https://github.com/o/r/pull/110","state":"OPEN"}},{"name":"feat-x-sub-02-ui","head":"4567def","base":"feat-x-sub-01-schema","isCurrent":true,"isMerged":false,"isQueued":false,"needsRebase":false,"pr":{"number":111,"url":"https://github.com/o/r/pull/111","state":"OPEN"}}]}\n' "$GH_STUB_STACK" "${GIT_STUB_BRANCH:-feat-x-sub-02-ui}" "$GH_STUB_STACK"
    exit 0 ;;
  *) echo "gh-stub: unsupported command: $noun $verb" >&2; exit 1 ;;
esac
ref=""; json=""; jqx=""
while [ $# -gt 0 ]; do
  case "$1" in
    --json) json=${2:-}; shift 2 ;;
    --json=*) json=${1#*=}; shift ;;
    -q|--jq) jqx=${2:-}; shift 2 ;;
    -R|--repo) [ "${2:-}" = o/r ] || { echo "GraphQL: Could not resolve to a Repository with the name '${2:-}'." >&2; exit 1; }; shift 2 ;;
    --repo=*) [ "${1#*=}" = o/r ] || { echo "GraphQL: Could not resolve to a Repository with the name '${1#*=}'." >&2; exit 1; }; shift ;;
    -*) shift ;;
    *) [ -n "$ref" ] || ref=$1; shift ;;
  esac
done
[ -n "$json" ] || { echo "gh-stub: --json is required" >&2; exit 1; }
ref=${ref#\#}
[ -n "$ref" ] || [ "$noun" != pr ] || ref=${GIT_STUB_BRANCH:-feat-x-sub-02-ui}
if [ -n "$jqx" ]; then GH_STUB_LOG="" "$0" "$noun" "$verb" "$ref" --json "$json" | jq -r "$jqx"; exit "${PIPESTATUS[0]}"; fi
case "$ref" in
  http*://github.com/*/pull/*|http*://github.com/*/issues/*) ref=${ref##*/} ;;
esac
lbl() {  # NAME… -> gh-style label objects
  local out="" n
  for n in "$@"; do out="$out${out:+,}{\"id\":\"LA_$n\",\"name\":\"$n\",\"color\":\"7057ff\"}"; done
  printf '[%s]' "$out"
}
pr() {  # NUM HEAD BASE CROSS LABEL…  (state: $PR_STATE, default OPEN)
  local num=$1 h=$2 b=$3 x=$4; shift 4
  printf '{"number":%s,"state":"%s","labels":%s,"headRefName":"%s","baseRefName":"%s","isCrossRepository":%s}\n' "$num" "${PR_STATE:-OPEN}" "$(lbl "$@")" "$h" "$b" "$x"
}
if [ "$noun" = pr ]; then
  case "$ref" in
    100|feat-x)               pr 100 feat-x main false agent-worked ;;
    110|feat-x-sub-01-schema) pr 110 feat-x-sub-01-schema feat-x false agent-worked ;;
    111|feat-x-sub-02-ui)     pr 111 feat-x-sub-02-ui feat-x-sub-01-schema false agent-worked ;;
    112|feat-x-sub-03-docs)   pr 112 feat-x-sub-03-docs feat-x-sub-02-ui false bug ;;
    200|other)                pr 200 other main false bug ;;
    210|feat-x-sub-02-api)    pr 210 feat-x-sub-02-api main false bug ;;
    120|fork-fix)             pr 120 fork-fix main true agent-worked ;;
    113|feat-x-sub-04-misc)   pr 113 feat-x-sub-04-misc feat-x false agent-created ;;
    114|feat-y-sub-01-done)   PR_STATE=MERGED pr 114 feat-y-sub-01-done feat-y false agent-worked ;;
    115|release-fix)          pr 115 release-fix release false agent-worked ;;
    116|trunk-fix)            pr 116 trunk-fix trunk false agent-worked ;;
    *) echo "GraphQL: Could not resolve to a PullRequest with the number of $ref." >&2; exit 1 ;;
  esac
else
  case "$ref" in
    1) printf '{"number":1,"labels":%s}\n' "$(lbl agent-worked)" ;;
    2) printf '{"number":2,"labels":%s}\n' "$(lbl agent-drafted)" ;;
    3) printf '{"number":3,"labels":%s}\n' "$(lbl bug)" ;;
    4) printf '{"number":4,"labels":[]}\n' ;;
    *) echo "GraphQL: Could not resolve to an Issue with the number of $ref. (repository.issue)" >&2; exit 1 ;;
  esac
fi
