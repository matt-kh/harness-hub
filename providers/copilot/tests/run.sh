#!/usr/bin/env bash
# Shim fixtures for this provider, run by providers/_shared/run-shim-tests.sh:
# - tests/NAME.in.json is piped through ../shim.sh (the guard shim) with a stub guard and compared
#   (jq -S) to tests/NAME.out.json; an empty .out.json means "no output". NAME.env (optional)
#   holds extra KEY=value lines exported for that case. The stub guard decides from the command
#   text: "allow…" allow, "deny…" deny, "ask…" ask, anything else no output.
# - tests/prompt/ and tests/stop/ do the same for ../shim-prompt.sh and ../shim-stop.sh with a stub
#   event hook; NAME.envelope.json is the neutral envelope the hook must receive (empty = the
#   hook must not run). The stub hook answers from the words in the prompt and cwd.
set -u
here=$(cd "$(dirname "$0")" && pwd)
runner="$here/../../_shared/run-shim-tests.sh"
rc=0
bash "$runner" "$here/../shim.sh" "$here" || rc=1
for ev in prompt stop; do
  printf -- '-- %s events\n' "$ev"
  bash "$runner" "$here/../shim-$ev.sh" "$here/$ev" || rc=1
done
if [ "$rc" -eq 0 ]; then echo "all shim fixtures passed"; else echo "shim fixtures FAILED"; fi
exit "$rc"
