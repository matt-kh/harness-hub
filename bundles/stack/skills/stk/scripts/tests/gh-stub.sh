#!/usr/bin/env bash
# gh stub for the stk tests: every call is routed by stub.py from the scenario fixture
# (pr view|list|edit|ready|update-branch, repo view, api incl. repos/o/r/stacks, extension list,
# and the gh-stack extension's link verb).
exec python3 "$(cd "$(dirname "$0")" && pwd)/stub.py" gh "$@"
