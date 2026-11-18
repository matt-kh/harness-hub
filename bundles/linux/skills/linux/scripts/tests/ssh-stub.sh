#!/usr/bin/env bash
# ssh stub for the lx CLI tests. Answers from tests/fixtures/<alias>/<cmd>.txt only — no
# network, no key, no real host. Every invocation is appended to $STUB_LOG as one line of
# shell-quoted argv (`printf %q`) so run.sh can assert the call invariants.
#
#   alias unreachable  -> "Connection timed out", exit 255
#   alias denied       -> "Permission denied (publickey).", exit 255
#   alias hostkey      -> "Host key verification failed.", exit 255
#   no fixture         -> "stub: no fixture for <alias>/<cmd>", exit 255
set -u
here=$(cd "$(dirname "$0")" && pwd)
if [ -n "${STUB_LOG:-}" ]; then
  { printf 'ssh'; for a in "$@"; do printf ' %q' "$a"; done; printf '\n'; } >> "$STUB_LOG"
fi
alias='' script='' seen=0
for a in "$@"; do
  if [ "$seen" = 1 ]; then alias=$a; seen=2; continue; fi
  if [ "$seen" = 2 ]; then script=$a; seen=3; continue; fi
  [ "$a" = "--" ] && seen=1
done
[ -n "$alias" ] || { echo "stub: no -- ALIAS in argv" >&2; exit 255; }
case "$alias" in
  unreachable) echo "ssh: connect to host 192.0.2.99 port 22: Connection timed out" >&2; exit 255 ;;
  denied) echo "deploy@192.0.2.98: Permission denied (publickey)." >&2; exit 255 ;;
  hostkey) echo "Host key verification failed." >&2; exit 255 ;;
esac
cmd=$(printf '%s\n' "$script" | sed -n "s/^echo '@@lxcmd \([a-z]*\)'.*/\1/p" | head -1)
f="$here/fixtures/$alias/$cmd.txt"
[ -f "$f" ] || { echo "stub: no fixture for $alias/$cmd" >&2; exit 255; }
cat "$f"
