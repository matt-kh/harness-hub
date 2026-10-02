#!/usr/bin/env bash
# Bootstrap smoke test: a newcomer's first run in a throw-away HOME with fake provider CLIs.
#
#   HOME=$(mktemp -d) PATH=tests/fakes/bin:$PATH
#   ./bootstrap --bundles core --providers claude --yes --offline --config tests/fixtures/harness.ci.toml
#
# Asserts: settings.json parses and carries the guard hook entry, the user's own settings and
# CLAUDE.md text survive, the hook is executable and fails closed, `doctor --offline` exits 0,
# a second `apply` is `Plan: 0 changes`, and nothing is written outside the managed paths.
# Set HARNESS_BUNDLES_ROOT to run it against another bundle tree (e.g. tests/fixtures/bundles).
set -eu
here=$(cd "$(dirname "$0")/../.." && pwd)
cfg="$here/tests/fixtures/harness.ci.toml"
# macOS $TMPDIR ends in "/": strip it so no "//" reaches paths the engine normalises
tmpdir=${TMPDIR:-/tmp}
tmp=$(mktemp -d "${tmpdir%/}/harness-smoke.XXXXXX")
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/home"
HOME="$(cd "$tmp/home" && pwd)"; export HOME   # normalised: hook commands embed $HOME
unset XDG_STATE_HOME XDG_DATA_HOME XDG_CONFIG_HOME XDG_CACHE_HOME HARNESS_CONFIG 2>/dev/null || true
# build products of the fixture config stay in the temp dir; the live <hub>/build/config.json
# (read by rendered skills) must come out of this run byte-identical
export HARNESS_BUILD_DIR="$tmp/build"
live_cfg="$here/build/config.json"
live_sum=""
[ -f "$live_cfg" ] && live_sum=$(cksum < "$live_cfg")
export PATH="$here/tests/fakes/bin:$PATH"
failures=0
fail() { echo "FAIL: $*" >&2; failures=$((failures+1)); }
die() { echo "FAIL: $*" >&2; exit 1; }
step() { echo "== $*"; }

# a newcomer who already uses Claude Code: their settings and notes must survive
mkdir -p "$HOME/.claude"
printf '{\n  "theme": "dark",\n  "permissions": {"allow": ["Bash(ls:*)"]}\n}\n' > "$HOME/.claude/settings.json"
printf '# My own notes\n\nKeep this line.\n' > "$HOME/.claude/CLAUDE.md"
before="$tmp/before.txt"; after="$tmp/after.txt"
(cd "$HOME" && find . -mindepth 1 | LC_ALL=C sort) > "$before"

step "bootstrap"
"$here/bootstrap" --bundles core --providers claude --yes --offline --config "$cfg" > "$tmp/bootstrap.log" 2>&1 \
  || { cat "$tmp/bootstrap.log"; die "bootstrap exited non-zero"; }

s="$HOME/.claude/settings.json"
step "settings.json"
jq -e . "$s" >/dev/null || fail "settings.json does not parse"
jq -e --arg g "$HOME/.claude/hooks/guard-bash.sh" \
  '[.hooks.PreToolUse[] | select(.matcher == "Bash") | .hooks[] | select(.command == ("bash " + $g))] | length == 1' "$s" >/dev/null \
  || fail "settings.json lacks the PreToolUse guard entry"
jq -e '.theme == "dark"' "$s" >/dev/null || fail "user key 'theme' was not preserved"
jq -e '.permissions.allow | index("Bash(ls:*)") != null' "$s" >/dev/null || fail "user permission was not preserved"
grep -q 'Keep this line.' "$HOME/.claude/CLAUDE.md" || fail "user text in CLAUDE.md was not preserved"

step "hook"
g="$HOME/.claude/hooks/guard-bash.sh"
[ -x "$g" ] || die "guard-bash.sh missing or not executable"
[ -f "$HOME/.claude/hooks/guard.env" ] || fail "guard.env missing"
out=$(printf 'not json' | bash "$g")
printf '%s' "$out" | jq -e '.hookSpecificOutput.permissionDecision == "deny"' >/dev/null \
  || fail "guard does not fail closed on malformed input (got: $out)"
if [ -z "${HARNESS_BUNDLES_ROOT:-}" ]; then
  out=$(printf '%s' '{"tool_name":"Bash","tool_input":{"command":"cat ~/.config/jira"},"cwd":"/tmp"}' | bash "$g")
  printf '%s' "$out" | jq -e '.hookSpecificOutput.permissionDecision == "deny"' >/dev/null \
    || fail "guard does not deny a credential read (got: $out)"
fi

step "doctor --offline"
"$here/bin/harness" doctor --offline --config "$cfg" > "$tmp/doctor.log" 2>&1 \
  || { cat "$tmp/doctor.log"; fail "doctor --offline exited non-zero"; }

step "second apply is a no-op"
"$here/bin/harness" apply --yes --config "$cfg" > "$tmp/apply2.log" 2>&1 || { cat "$tmp/apply2.log"; fail "second apply failed"; }
grep -q '^Plan: 0 changes' "$tmp/apply2.log" || { cat "$tmp/apply2.log"; fail "second apply is not '0 changes'"; }

step "nothing written outside managed paths"
(cd "$HOME" && find . -mindepth 1 | LC_ALL=C sort) > "$after"
bad=$(LC_ALL=C comm -13 "$before" "$after" | grep -vE '^\./(\.claude(/(CLAUDE\.md|settings\.json|\.harness-state\.json|hooks|hooks/.*|skills|skills/.*|agents|agents/.*))?|\.claude\.json|\.local|\.local/(bin|bin/.*|state|state/harness|state/harness/.*|share|share/harness|share/harness/.*))$' || true)
[ -z "$bad" ] || fail "unexpected paths written: $(printf '%s' "$bad" | tr '\n' ' ')"

step "live build products untouched"
[ -f "$tmp/build/config.json" ] || fail "fixture build products did not land in HARNESS_BUILD_DIR"
if [ -n "$live_sum" ]; then
  [ "$(cksum < "$live_cfg")" = "$live_sum" ] || fail "$live_cfg changed during the smoke run"
fi

[ "$failures" -eq 0 ] || die "$failures check(s) failed"
echo "smoke bootstrap: ok"
