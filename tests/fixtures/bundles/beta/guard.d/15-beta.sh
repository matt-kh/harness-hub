# shellcheck shell=bash
# Section 15 (fixture beta): sorts before core's 20 and after nothing else.
case "$cmd" in
  beta-ask*) ask "asked by beta" ;;
esac
