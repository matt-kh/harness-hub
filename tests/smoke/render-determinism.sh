#!/usr/bin/env bash
# Render determinism: two renders of the same config into two directories are identical
# (sorted keys, LF endings, no timestamps). Also renders every provider once.
set -eu
here=$(cd "$(dirname "$0")/../.." && pwd)
cfg="$here/tests/fixtures/harness.ci.toml"
# macOS $TMPDIR ends in "/": strip it so no "//" reaches paths the engine normalises
tmpdir=${TMPDIR:-/tmp}
tmp=$(mktemp -d "${tmpdir%/}/harness-render.XXXXXX")
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/home"
HOME="$(cd "$tmp/home" && pwd)"; export HOME   # normalised: hook commands embed $HOME
unset XDG_STATE_HOME XDG_DATA_HOME HARNESS_CONFIG 2>/dev/null || true
all=claude,gemini,copilot,codex,opencode
"$here/bin/harness" render --config "$cfg" --providers "$all" --out "$tmp/a" > /dev/null
"$here/bin/harness" render --config "$cfg" --providers "$all" --out "$tmp/b" > /dev/null
diff -r "$tmp/a" "$tmp/b" > "$tmp/diff.txt" || { cat "$tmp/diff.txt"; echo "FAIL: renders differ" >&2; exit 1; }
n=$(find "$tmp/a" -type f | wc -l | tr -d ' ')
[ "$n" -gt 0 ] || { echo "FAIL: nothing rendered" >&2; exit 1; }
if grep -rlI $'\r' "$tmp/a" >/dev/null 2>&1; then echo "FAIL: CRLF in rendered files" >&2; exit 1; fi
echo "smoke render-determinism: ok ($n files identical)"
