#!/usr/bin/env bash
# Shim fixtures for this provider: every tests/NAME.in.json is piped through ../shim.sh with a
# stub guard and compared (jq -S) to tests/NAME.out.json. An empty .out.json means "no output".
# NAME.env (optional) holds extra KEY=value lines exported for that case.
# The stub guard decides from the command text: "allow…" allow, "deny…" deny, "ask…" ask,
# anything else no output.
set -u
here=$(cd "$(dirname "$0")" && pwd)
exec bash "$here/../../_shared/run-shim-tests.sh" "$here/../shim.sh" "$here"
