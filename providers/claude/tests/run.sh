#!/usr/bin/env bash
# Shim fixtures for this provider, run by providers/_shared/run-provider-tests.sh:
# no guard shim (native envelope); event fixtures in tests/prompt/ and tests/stop/.
# NAME.in.json is piped through the shim and compared (jq -S) with NAME.out.json (empty = no
# output); NAME.envelope.json is the neutral envelope the stub hook must receive (empty = the hook
# must not run); NAME.env holds extra KEY=value lines for that case. The stub guard and stub hook
# answer from the words in the command, prompt or cwd (see run-shim-tests.sh).
set -u
here=$(cd "$(dirname "$0")" && pwd)
exec bash "$here/../../_shared/run-provider-tests.sh" "$here" prompt:shim-event.sh stop:shim-event.sh
