#!/usr/bin/env bash
# run-shim-tests.sh SHIM DIR — fixture runner shared by every provider shim.
#
# For each DIR/NAME.in.json: pipe it through SHIM with HARNESS_GUARD pointing at a stub guard and
# HARNESS_HOOK at a stub event hook, compare the output (jq -S, or empty) with DIR/NAME.out.json.
# DIR/NAME.env may export extra variables (e.g. HARNESS_ASK_AS=allow). DIR/NAME.envelope.json,
# when present, is the neutral envelope the stub hook must have received (jq -S); an empty one
# means the hook must not have run. Prints one line per case and a summary line.
#
# Stub guard: decision from the command prefix (allow… deny… ask…; garbage… prints "not json").
# Stub hook (event shims): looks at the neutral prompt and cwd; prints "not json" on "garbage",
# two objects on "twice", systemMessage + additionalContext on "both", {"systemMessage":"stub
# message"} on "message", {"hookSpecificOutput":{"additionalContext":"stub ctx"}} on "context",
# nothing otherwise. Bash 3.2 compatible.
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
cat > "$tmp/hook.sh" <<'STUB'
#!/usr/bin/env bash
# stub event hook: records the envelope it received, answers from the prompt and cwd words
in=$(cat)
printf '%s' "$in" > "$HARNESS_HOOK_ENVELOPE"
text=$(printf '%s' "$in" | jq -r '[(.prompt // ""), (.cwd // "")] | map(tostring) | join(" ")' 2>/dev/null) || exit 0
case "$text" in
  *garbage*) echo 'not json' ;;
  *twice*)   echo '{"systemMessage":"one"}'; echo '{"systemMessage":"two"}' ;;
  *both*)    jq -cn '{systemMessage:"stub message", hookSpecificOutput:{additionalContext:"stub ctx"}}' ;;
  *message*) jq -cn '{systemMessage:"stub message"}' ;;
  *context*) jq -cn '{hookSpecificOutput:{additionalContext:"stub ctx"}}' ;;
esac
exit 0
STUB
pass=0; fail=0
for in_file in "$dir"/*.in.json; do
  [ -f "$in_file" ] || continue
  name=$(basename "$in_file" .in.json)
  want_file="$dir/$name.out.json"
  env_file="$dir/$name.envelope.json"
  rm -f "$tmp/envelope.json"
  got=$(
    # shellcheck disable=SC1090  # per-case fixture env (KEY=value lines)
    if [ -f "$dir/$name.env" ]; then set -a; . "$dir/$name.env"; set +a; fi
    HARNESS_GUARD="$tmp/guard.sh" HARNESS_HOOK="$tmp/hook.sh" HARNESS_HOOK_ENVELOPE="$tmp/envelope.json" \
      bash "$shim" < "$in_file"
  )
  rc=$?
  if [ -s "$want_file" ]; then
    want=$(jq -S . "$want_file")
    got_n=$(printf '%s' "$got" | jq -S . 2>/dev/null || printf 'INVALID: %s' "$got")
  else
    want=""; got_n=$got
  fi
  env_ok=1; env_want=""; env_got=""
  if [ -f "$env_file" ]; then
    if [ -s "$env_file" ]; then env_want=$(jq -S . "$env_file"); fi
    if [ -f "$tmp/envelope.json" ]; then
      env_got=$(jq -S . "$tmp/envelope.json" 2>/dev/null || printf 'INVALID: %s' "$(cat "$tmp/envelope.json")")
      [ -n "$env_got" ] || env_got="(empty envelope)"
    fi
    [ "$env_got" = "$env_want" ] || env_ok=0
  fi
  if [ $rc -eq 0 ] && [ "$got_n" = "$want" ] && [ $env_ok -eq 1 ]; then
    pass=$((pass+1)); printf 'ok    %s\n' "$name"
  else
    fail=$((fail+1)); printf 'FAIL  %s (rc=%s)\n  want: %s\n  got:  %s\n' "$name" "$rc" "$want" "$got_n"
    [ $env_ok -eq 1 ] || printf '  envelope want: %s\n  envelope got:  %s\n' "${env_want:-(hook not run)}" "${env_got:-(hook not run)}"
  fi
done
printf 'passed=%d failed=%d\n' "$pass" "$fail"
[ "$fail" -eq 0 ] && [ "$pass" -gt 0 ]
