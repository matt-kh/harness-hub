#!/usr/bin/env bash
# Stub git for guard-bash hook tests: the hook only ever shells out to
#   git -C DIR rev-parse --abbrev-ref HEAD   -> $GIT_STUB_BRANCH   (unset: exit 128, "not a repo")
#   git -C DIR rev-parse --show-toplevel     -> $GIT_STUB_TOPLEVEL (unset: exit 128; hook falls back to DIR)
#   git -C DIR remote get-url origin         -> $GIT_STUB_REMOTE   (unset: https://github.com/o/r.git;
#                                               "none": exit 2, "No such remote 'origin'";
#                                               "hang": never answers, the hook's timeout fires)
# Everything else exits 1 so a stray git call in the hook is loud, not silent.
# GIT_STUB_LOG=FILE appends every call's arguments (after -C DIR), one line each.
if [ "${1:-}" = -C ]; then shift 2; fi          # the directory is irrelevant to the stub
[ -z "${GIT_STUB_LOG:-}" ] || printf '%s\n' "$*" >> "$GIT_STUB_LOG"
if [ "${1:-} ${2:-} ${3:-}" = "remote get-url origin" ]; then
  case "${GIT_STUB_REMOTE:-https://github.com/o/r.git}" in
    none) echo "error: No such remote 'origin'" >&2; exit 2 ;;
    hang) exec sleep 60 ;;                       # exec: the timeout's signal reaches the sleeper
    *) echo "${GIT_STUB_REMOTE:-https://github.com/o/r.git}"; exit 0 ;;
  esac
fi
[ "${1:-}" = rev-parse ] || exit 1
case "${2:-}" in
  --abbrev-ref) [ -n "${GIT_STUB_BRANCH:-}" ] || exit 128; echo "$GIT_STUB_BRANCH" ;;
  --show-toplevel) [ -n "${GIT_STUB_TOPLEVEL:-}" ] || exit 128; echo "$GIT_STUB_TOPLEVEL" ;;
  *) exit 1 ;;
esac
