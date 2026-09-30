# shellcheck shell=bash
# Section 40 (fixture alpha)
# rule: alpha-deny ... -> deny : alpha fixture deny
case "$cmd" in
  alpha-deny*) deny "denied by alpha (${ALPHA_HOST:-unset})" ;;
esac
