#!/usr/bin/env bash
# Stub for guard-bash hook tests: `mr view REF -F json` prints canned MRs; no network.
# 100 -> agent-worked, ticket branch -> master     110 -> agent-worked, -sub- source -> ticket branch
# 200 -> bug only, plain branch                    210 -> bug only, -sub- source (auto-retargeted to master)
# anything else -> exit 1 (unreachable / not found)
[ "${1:-}" = mr ] && [ "${2:-}" = view ] || exit 1
case "${3:-}" in
  100) echo '{"iid":100,"labels":["agent-worked"],"source_branch":"feat-x","target_branch":"master"}' ;;
  110) echo '{"iid":110,"labels":["agent-worked"],"source_branch":"feat-x-sub-01-schema","target_branch":"feat-x"}' ;;
  200) echo '{"iid":200,"labels":["bug"],"source_branch":"other","target_branch":"master"}' ;;
  210) echo '{"iid":210,"labels":["bug"],"source_branch":"feat-x-sub-02-api","target_branch":"master"}' ;;
  *)   exit 1 ;;
esac
