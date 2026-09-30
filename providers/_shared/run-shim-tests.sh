#!/usr/bin/env bash
# run-shim-tests.sh SHIM DIR — fixture runner shared by every provider shim.
#
# For each DIR/NAME.in.json: pipe it through SHIM with HARNESS_GUARD pointing at a stub guard,
# compare the output (jq -S, or empty) with DIR/NAME.out.json. DIR/NAME.env may export extra
# variables (e.g. HARNESS_ASK_AS=allow). Prints one line per case and a summary line.
# Bash 3.2 compatible.
set -u
shim=$1; dir=$2
tmp=$(mktemp -d "${TMPDIR:-/tmp}/harness-shim.XXXXXX")
trap 'rm -rf "$tmp"' EXIT
cat > "$tmp/guard.sh" <<'STUB'
#!/usr/bin/env bash
# stub guard: decision from the command prefix
in=$(cat)
cmd=$(printf '%s' "$in" | jq -r '.tool_input.command // empty' 2>/dev/null) || exit 0
emit() { jq -cn --arg d "$1" --arg r "stub: $1" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:$d,permissionDecisionReason:$r}}'; exit 0; }
case "$cmd" in
  allow*) emit allow ;;
  deny*)  emit deny ;;
  ask*)   emit ask ;;
  garbage*) echo 'not json'; exit 0 ;;
esac
exit 0
STUB
pass=0; fail=0
for in_file in "$dir"/*.in.json; do
  [ -f "$in_file" ] || continue
  name=$(basename "$in_file" .in.json)
  want_file="$dir/$name.out.json"
  got=$(
    # shellcheck disable=SC1090  # per-case fixture env (KEY=value lines)
    if [ -f "$dir/$name.env" ]; then set -a; . "$dir/$name.env"; set +a; fi
    HARNESS_GUARD="$tmp/guard.sh" bash "$shim" < "$in_file"
  )
  rc=$?
  if [ -s "$want_file" ]; then
    want=$(jq -S . "$want_file")
    got_n=$(printf '%s' "$got" | jq -S . 2>/dev/null || printf 'INVALID: %s' "$got")
  else
    want=""; got_n=$got
  fi
  if [ $rc -eq 0 ] && [ "$got_n" = "$want" ]; then
    pass=$((pass+1)); printf 'ok    %s\n' "$name"
  else
    fail=$((fail+1)); printf 'FAIL  %s (rc=%s)\n  want: %s\n  got:  %s\n' "$name" "$rc" "$want" "$got_n"
  fi
done
printf 'passed=%d failed=%d\n' "$pass" "$fail"
[ "$fail" -eq 0 ] && [ "$pass" -gt 0 ]
