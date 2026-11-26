#!/usr/bin/env bash
# Stub for guard-bash hook tests: `mr view REF -F json` prints canned MRs; no network.
# 100 -> agent-worked, ticket branch -> master     110 -> agent-worked, -sub- source -> ticket branch
# 200 -> bug only, plain branch                    210 -> bug only, -sub- source (auto-retargeted to master)
# 113 -> agent-created, -sub- source -> feat-x     114 -> agent-worked, merged, -> feat-y
# 115 -> agent-worked, release-fix -> release      116 -> agent-worked, trunk-fix -> trunk
# 120 -> agent-worked, fork (source project 2) -> feat-x
# Every MR is opened unless marked; source and target project are 1 unless marked.
# `repo view [G/P] -F json` prints {"default_branch": $GLAB_STUB_DEFAULT_BRANCH (default master)};
# GLAB_STUB_REPO_FAIL=1 makes it fail. Known projects: g/p and g/sub/p (or none given); any other
# -R / --repo / repo argument fails (rows can catch a project mismatch).
# anything else -> exit 1 (unreachable / not found)
mr() {  # IID LABEL SOURCE TARGET [STATE] [SOURCE_PROJECT]
  printf '{"iid":%s,"state":"%s","labels":["%s"],"source_branch":"%s","target_branch":"%s","source_project_id":%s,"target_project_id":1}\n' \
    "$1" "${5:-opened}" "$2" "$3" "$4" "${6:-1}"
}
known() { case "$1" in g/p|g/sub/p) return 0 ;; *) return 1 ;; esac; }
a1=${1:-}; a2=${2:-}; a3=${3:-}
shift 2 2>/dev/null
while [ $# -gt 0 ]; do
  case "$1" in
    -R|--repo) known "${2:-}" || exit 1; shift 2 ;;
    --repo=*) known "${1#*=}" || exit 1; shift ;;
    -F|--output) shift 2 ;;
    -*) shift ;;
    *) [ "$a1" != repo ] || known "$1" || exit 1; shift ;;
  esac
done
set -- "$a1" "$a2" "$a3"
if [ "${1:-}" = repo ] && [ "${2:-}" = view ]; then
  [ -z "${GLAB_STUB_REPO_FAIL:-}" ] || exit 1
  printf '{"id":1,"default_branch":"%s"}\n' "${GLAB_STUB_DEFAULT_BRANCH:-master}"
  exit 0
fi
[ "${1:-}" = mr ] && [ "${2:-}" = view ] || exit 1
case "${3:-}" in
  100) mr 100 agent-worked feat-x master ;;
  110) mr 110 agent-worked feat-x-sub-01-schema feat-x ;;
  200) mr 200 bug other master ;;
  210) mr 210 bug feat-x-sub-02-api master ;;
  113) mr 113 agent-created feat-x-sub-04-misc feat-x ;;
  114) mr 114 agent-worked feat-y-sub-01-done feat-y merged ;;
  115) mr 115 agent-worked release-fix release ;;
  116) mr 116 agent-worked trunk-fix trunk ;;
  120) mr 120 agent-worked fork-fix feat-x opened 2 ;;
  *)   exit 1 ;;
esac
