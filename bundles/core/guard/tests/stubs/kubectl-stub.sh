#!/usr/bin/env bash
# Stub kubectl for guard-bash hook tests: the hook only ever shells out to
# `kubectl config current-context` (to resolve the target when no --context is given).
# Everything else exits 1 so a stray cluster call in the hook is loud, not silent.
[ "${1:-}" = config ] && [ "${2:-}" = current-context ] || exit 1
echo dev-cluster
