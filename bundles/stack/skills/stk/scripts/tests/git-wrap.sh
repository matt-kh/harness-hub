#!/usr/bin/env bash
# git for the stk tests: the REAL git (the cascade runs against the sandbox repositories),
# with every call stk makes appended to $STUB_LOG as `git <args>` for the invariants.
[ -n "${STUB_LOG:-}" ] && printf 'git %s\n' "$*" >> "$STUB_LOG"
exec git "$@"
