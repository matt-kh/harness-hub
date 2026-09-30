#!/usr/bin/env bash
# Shim fixtures for this provider (see providers/_shared/run-shim-tests.sh).
set -u
here=$(cd "$(dirname "$0")" && pwd)
exec bash "$here/../../_shared/run-shim-tests.sh" "$here/../shim.sh" "$here"
