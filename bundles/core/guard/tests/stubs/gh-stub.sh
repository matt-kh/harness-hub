#!/usr/bin/env bash
# Stub gh for guard-bash hook tests (git-stub style; no network). Answers only
#   gh pr view REF [-R owner/repo] --json …      gh issue view REF [-R owner/repo] --json …
#   gh stack view --json                         (the gh-stack extension; GH_STUB_STACK=TRUNK)
# REF: N, #N, a github.com pull/issues URL, or (PRs) the head branch name. Labels are emitted the
# way gh emits them: [{"id","name","color"}]. Anything else -> stderr + exit 1 (a stray gh call is loud).
# PRs:    100 feat-x               [agent-worked] -> main
#         110 feat-x-sub-01-schema [agent-worked] -> feat-x
#         111 feat-x-sub-02-ui     [agent-worked] -> feat-x-sub-01-schema
#         200 other                [bug]          -> main
#         210 feat-x-sub-02-api    [bug]          -> main   (auto-retargeted)
#         120 fork-fix             [agent-worked] -> main   isCrossRepository:true
# Issues: 1 [agent-worked]  2 [agent-drafted]  3 [bug]  4 []   others -> "Could not resolve to an Issue"
# Stack:  GH_STUB_STACK unset -> exit 2 (not in a stack); set -> trunk $GH_STUB_STACK with the layers
#         feat-x-sub-01-schema (PR 110) and feat-x-sub-02-ui (PR 111)
# Also answers ONE read-only GraphQL shape (section 41's batched lookup):
#   gh api [--hostname H] graphql -f query='query{repository(owner:"O",name:"R"){defaultBranchRef{name}
#     iN:issue(number:N){labels(first:50){nodes{name}}} … pN:pullRequest(number:N){baseRefName
#     headRefName isCrossRepository} …}}'
# with the issues and PRs below; the default branch is $GH_STUB_DEFAULT_BRANCH (default main). An
# unknown issue or PR is null plus an "errors" entry and exit 1, the way gh api reports it.
# GH_STUB_LOG=FILE appends every call's arguments, one line each.
[ -z "${GH_STUB_LOG:-}" ] || printf '%s\n' "$*" >> "$GH_STUB_LOG"
if [ "${1:-}" = api ]; then
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
  "stack view")
    [ "${1:-}" = --json ] || { echo "gh-stub: stack view needs --json" >&2; exit 1; }
    [ -n "${GH_STUB_STACK:-}" ] || { echo "not in a stack" >&2; exit 2; }
    # the gh-stack v0.3.0 schema (cmd/view.go); head is a commit, base the layer below
    printf '{"trunk":"%s","currentBranch":"%s","branches":[{"name":"feat-x-sub-01-schema","head":"0123abc","base":"%s","isCurrent":false,"isMerged":false,"isQueued":false,"needsRebase":false,"pr":{"number":110,"url":"https://github.com/o/r/pull/110","state":"OPEN"}},{"name":"feat-x-sub-02-ui","head":"4567def","base":"feat-x-sub-01-schema","isCurrent":true,"isMerged":false,"isQueued":false,"needsRebase":false,"pr":{"number":111,"url":"https://github.com/o/r/pull/111","state":"OPEN"}}]}\n' "$GH_STUB_STACK" "${GIT_STUB_BRANCH:-feat-x-sub-02-ui}" "$GH_STUB_STACK"
    exit 0 ;;
  *) echo "gh-stub: unsupported command: $noun $verb" >&2; exit 1 ;;
esac
ref=""; json=""
while [ $# -gt 0 ]; do
  case "$1" in
    --json) json=${2:-}; shift 2 ;;
    --json=*) json=${1#*=}; shift ;;
    -R|--repo|-q|--jq) shift 2 ;;
    -*) shift ;;
    *) [ -n "$ref" ] || ref=$1; shift ;;
  esac
done
[ -n "$json" ] || { echo "gh-stub: --json is required" >&2; exit 1; }
ref=${ref#\#}
case "$ref" in
  http*://github.com/*/pull/*|http*://github.com/*/issues/*) ref=${ref##*/} ;;
esac
lbl() {  # NAME… -> gh-style label objects
  local out="" n
  for n in "$@"; do out="$out${out:+,}{\"id\":\"LA_$n\",\"name\":\"$n\",\"color\":\"7057ff\"}"; done
  printf '[%s]' "$out"
}
pr() {  # NUM HEAD BASE CROSS LABEL…
  local num=$1 h=$2 b=$3 x=$4; shift 4
  printf '{"number":%s,"labels":%s,"headRefName":"%s","baseRefName":"%s","isCrossRepository":%s}\n' "$num" "$(lbl "$@")" "$h" "$b" "$x"
}
if [ "$noun" = pr ]; then
  case "$ref" in
    100|feat-x)               pr 100 feat-x main false agent-worked ;;
    110|feat-x-sub-01-schema) pr 110 feat-x-sub-01-schema feat-x false agent-worked ;;
    111|feat-x-sub-02-ui)     pr 111 feat-x-sub-02-ui feat-x-sub-01-schema false agent-worked ;;
    200|other)                pr 200 other main false bug ;;
    210|feat-x-sub-02-api)    pr 210 feat-x-sub-02-api main false bug ;;
    120|fork-fix)             pr 120 fork-fix main true agent-worked ;;
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
