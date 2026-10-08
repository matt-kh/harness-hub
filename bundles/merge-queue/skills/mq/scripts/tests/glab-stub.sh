#!/usr/bin/env bash
# glab stub for the mq tests: every call is routed by stub.py from the scenario fixture.
exec python3 "$(cd "$(dirname "$0")" && pwd)/stub.py" glab "$@"
