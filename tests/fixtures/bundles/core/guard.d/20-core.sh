# shellcheck shell=bash
# Section 20 (fixture core)
# rule: fixture-deny ... -> deny : fixture deny rule
# rule: fixture-ask ... -> ask : fixture ask rule
# rule: fixture-allow ... -> allow : fixture allow rule
case "$cmd" in
  fixture-deny*) deny "denied by core (ticket ${FIX_TICKET:-unset})" ;;
  fixture-ask*) ask "asked by core" ;;
  fixture-allow*) allow "allowed by core" ;;
esac
