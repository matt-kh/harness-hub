# shellcheck shell=bash
# Section 20 (fixture core)
# rule: fixture-deny ... -> deny : fixture deny rule
# rule: fixture-ask ... -> ask : fixture ask rule
# rule: fixture-allow ... -> allow : fixture allow rule
repo_owns core/guard.d/20-core base && return 0   # principle 8: yields to the repository's .harness.toml
case "$cmd" in
  fixture-deny*) deny "denied by core (ticket ${FIX_TICKET:-unset})" ;;
  fixture-ask*) ask "asked by core" ;;
  fixture-allow*) allow "allowed by core" ;;
esac
