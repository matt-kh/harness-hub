#!/usr/bin/env bash
# Stub git for guard-bash hook tests: the hook only ever shells out to
#   git -C DIR rev-parse --abbrev-ref HEAD   -> $GIT_STUB_BRANCH   (unset: exit 128, "not a repo")
#   git -C DIR rev-parse --show-toplevel     -> $GIT_STUB_TOPLEVEL (unset: exit 128; hook falls back to DIR)
# Everything else exits 1 so a stray git call in the hook is loud, not silent.
dir="."
if [ "${1:-}" = -C ]; then dir="${2:-.}"; shift 2; fi
[ "${1:-}" = rev-parse ] || exit 1
case "${2:-}" in
  --abbrev-ref) [ -n "${GIT_STUB_BRANCH:-}" ] || exit 128; echo "$GIT_STUB_BRANCH" ;;
  --show-toplevel) [ -n "${GIT_STUB_TOPLEVEL:-}" ] || exit 128; echo "$GIT_STUB_TOPLEVEL" ;;
  *) exit 1 ;;
esac
