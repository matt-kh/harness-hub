#!/usr/bin/env bash
# Bundle `core` tests: the full guard suite (every bundle's rows), drift of inlined helper
# copies, `bash -n` of every shell file in bundles/, the compat and config helpers, and build.sh
# determinism. Exit 1 on any failure.
set -uo pipefail
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
core=$(cd "$here/.." && pwd)
bundles=$(cd "$core/.." && pwd)
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
fail=0; cases=0
chk() { cases=$((cases + 1)); if [ "$1" = 0 ]; then echo "PASS $2"; else echo "FAIL $2"; fail=1; fi; }
ck() { local d=$1; shift; "$@"; chk $? "$d"; }  # ck DESC TEST...: run TEST, record it as case DESC

# 1. guard rows (all bundles, built into a private temp dir)
GUARD_BASH="$tmp/hooks/guard-bash.sh"
bash "$core/guard/build.sh" "$GUARD_BASH"; chk $? "build.sh builds the guard"
GUARD_BASH="$GUARD_BASH" bash "$core/guard/tests/run.sh" > "$tmp/guard.log" 2>&1; rc=$?
tail -1 "$tmp/guard.log"
ck "guard rows ($(tail -1 "$tmp/guard.log"))" [ "$rc" = 0 ]
[ "$rc" = 0 ] || grep -A1 '^FAIL' "$tmp/guard.log" | head -40

# 2. build determinism + ordering contract
bash "$core/guard/build.sh" "$tmp/b2.sh"
cmp -s "$GUARD_BASH" "$tmp/b2.sh"; chk $? "build.sh output is deterministic"
order=$(grep -o '^# ==== section [0-9][0-9]-[^ ]*' "$GUARD_BASH" | awk '{print $4}')
ck "sections are concatenated in basename order" [ "$order" = "$(printf '%s\n' "$order" | LC_ALL=C sort)" ]
bash -n "$GUARD_BASH"; chk $? "concatenated guard parses"
HARNESS_GUARD_BUNDLES=none bash "$core/guard/build.sh" "$tmp/core-only.sh"
ck "HARNESS_GUARD_BUNDLES=none keeps only core's sections" [ "$(grep -c '^# ==== section' "$tmp/core-only.sh")" = 2 ]
ck "every section is wrapped in a function and called (principle 8: sections may return)" \
  [ "$(grep -c '^guard_section_[A-Za-z0-9_]*() {$' "$GUARD_BASH")" = "$(grep -c '^# ==== section' "$GUARD_BASH")" ]
ck "the credential section never yields (no repo_owns line)" \
  [ -z "$(grep -E '^[[:space:]]*repo_owns ' "$core/guard.d/20-credentials.sh")" ]

# 3. inlined helper copies match their canonical source
python3 "$core/lib/sync_inline.py" --check "$bundles"; chk $? "inlined hn_timeout / harness_config / hcfg / hrepo / harness_repo copies are in sync"

# 4. every shell file parses (under /bin/bash too, which is 3.2 on macOS)
bad=""
while IFS= read -r f; do
  bash -n "$f" 2>"$tmp/n.err" || bad="$bad $f"
  if [ -x /bin/bash ] && [ "$(/bin/bash -c 'echo ${BASH_VERSINFO[0]}')" != "$(bash -c 'echo ${BASH_VERSINFO[0]}')" ]; then
    /bin/bash -n "$f" 2>>"$tmp/n.err" || bad="$bad $f(/bin/bash)"
  fi
done < <(find "$bundles" -type f \( -name '*.sh' \) -not -path '*/golden/*' | sort)
ck "bash -n on every *.sh${bad:+ —$bad}" [ -z "$bad" ]

# 4b. macOS portability traps the Linux job cannot see (guard/test rows are exempt: they quote
#     commands). BSD sed/awk have no \s \S \b \B \w \W \< \> (they match the literal letter; use
#     [[:space:]] etc.), and macOS ctype treats bytes >= 0x80 as identifier chars in UTF-8, so
#     "$var—" names a different, unset variable (set -u aborts): write "${var}—".
src=$(find "$bundles" -type f -name '*.sh' -not -name tests.sh -not -path '*/tests/*' -not -path '*/golden/*' | sort)
# shellcheck disable=SC2086
gnu_esc=$(printf '%s\n' $src | xargs grep -nE '(sed|awk)[^|]*\\[sSbBwW<>]' 2>/dev/null)
ck "no GNU-only regex escapes in sed/awk${gnu_esc:+ — $gnu_esc}" [ -z "$gnu_esc" ]
# shellcheck disable=SC2086
var_mb=$(printf '%s\n' $src | LC_ALL=C xargs grep -nE '\$[A-Za-z_][A-Za-z0-9_]*[^[:print:][:space:]]' 2>/dev/null)
ck "no \$var directly followed by a non-ASCII byte${var_mb:+ — $var_mb}" [ -z "$var_mb" ]

# 5. compat helpers
# shellcheck source=../lib/compat.sh
. "$core/lib/compat.sh"
hn_timeout 1 sleep 5; r=$?; ck "hn_timeout returns 124 on timeout" [ "$r" = 124 ]
hn_timeout 5 true; chk $? "hn_timeout passes the exit code through"
mkdir -p "$tmp/nopath"; ln -s "$(command -v python3)" "$tmp/nopath/python3"; ln -s "$(command -v sleep)" "$tmp/nopath/sleep"
( export PATH="$tmp/nopath"; hn_timeout 1 sleep 5 ); r=$?; ck "hn_timeout python fallback (no timeout/gtimeout on PATH)" [ "$r" = 124 ]
printf 'abc' > "$tmp/abc"
ck "hn_sha256" [ "$(hn_sha256 "$tmp/abc")" = ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad ]
ln -s "$tmp/abc" "$tmp/link"
ck "hn_realpath resolves symlinks" [ "$(hn_realpath "$tmp/link")" = "$(cd "$tmp" && pwd -P)/abc" ]

# 6. config helpers
printf '{"a":{"b":"x","n":2,"t":{"k":"v"}}}' > "$tmp/c.json"
ck "harness_config.py get string" [ "$(HARNESS_CONFIG_JSON="$tmp/c.json" python3 "$core/lib/harness_config.py" get a.b)" = x ]
ck "harness_config.py get table as JSON" [ "$(HARNESS_CONFIG_JSON="$tmp/c.json" python3 "$core/lib/harness_config.py" get a.t)" = '{"k": "v"}' ]
ck "harness_config.py default when the file is missing" [ "$(HARNESS_CONFIG_JSON=/nonexistent python3 "$core/lib/harness_config.py" get a.b dflt)" = dflt ]
# shellcheck source=../lib/harness_config.sh
. "$core/lib/harness_config.sh"
ck "hcfg number" [ "$(HARNESS_CONFIG_JSON="$tmp/c.json" hcfg a.n)" = 2 ]
ck "hcfg default" [ "$(HARNESS_CONFIG_JSON="$tmp/c.json" hcfg a.missing d)" = d ]
ck "hcfg prints nothing without file or default" [ -z "$(HARNESS_CONFIG_JSON=/nonexistent hcfg a.b)" ]

# 7. repository declaration helpers (principle 8): bash and python answer the same
# shellcheck source=../lib/harness_repo.sh
. "$core/lib/harness_repo.sh"
hr_py() { python3 "$core/lib/harness_repo.py" "$@"; }
rr="$tmp/rrepo"; mkdir -p "$rr/.git" "$rr/a/b" "$tmp/wt" "$tmp/out"
printf 'gitdir: /elsewhere/.git/worktrees/x\n' > "$tmp/wt/.git"
ck "hrepo_root from a nested directory" [ "$(hrepo_root "$rr/a/b")" = "$rr" ]
ck "hrepo_root accepts a linked worktree's .git file" [ "$(hrepo_root "$tmp/wt")" = "$tmp/wt" ]
hrepo_root "$tmp/out" >/dev/null; r=$?; ck "hrepo_root fails outside a checkout" [ "$r" = 1 ]
hrepo_root relative/dir >/dev/null; r=$?; ck "hrepo_root refuses a relative directory" [ "$r" = 1 ]
ck "harness_repo.py root agrees" [ "$(hr_py root "$rr/a/b")" = "$rr" ]
hrepo_file "$rr" >/dev/null; r=$?; ck "hrepo_file fails without .harness.toml" [ "$r" = 1 ]
printf '%s\n' '# a comment' '[repo]' 'name = "shop"' '[owns]' 'domains = ["scm", '"'"'tracker'"'"']' \
  'components = ["core/guard.d/30-git", "core/guard.d/20-credentials"]' '[overrides]' \
  "WORK_TICKET_ALLOW_DEFAULT_PUSH_RE = '^/home/u/dev/shop\$'" 'bad line' 'X = "a\\b"' > "$rr/.harness.toml"
ck "hrepo_file finds the declaration" [ "$(hrepo_file "$rr/a")" = "$rr/.harness.toml" ]
ck "hrepo_get string" [ "$(hrepo_get "$rr/.harness.toml" repo name)" = shop ]
ck "hrepo_get array, mixed quotes" [ "$(hrepo_get "$rr/.harness.toml" owns domains | tr '\n' ' ')" = "scm tracker " ]
ck "hrepo_get literal string keeps \$" [ "$(hrepo_get "$rr/.harness.toml" overrides WORK_TICKET_ALLOW_DEFAULT_PUSH_RE)" = '^/home/u/dev/shop$' ]
hrepo_get "$rr/.harness.toml" overrides X >/dev/null; r=$?; ck "hrepo_get refuses escapes (not in the subset)" [ "$r" = 1 ]
hrepo_owns core/guard.d/30-git scm "$rr/a"; chk $? "hrepo_owns by id"
hrepo_owns jira/guard.d/70-jira tracker "$rr"; chk $? "hrepo_owns by domain"
hrepo_owns k8s/guard.d/25-k8s-rules kubernetes "$rr"; r=$?; ck "hrepo_owns: other domain is not owned" [ "$r" = 1 ]
hrepo_owns core/guard.d/20-credentials base "$rr"; r=$?; ck "hrepo_owns: credentials never yield, even when listed" [ "$r" = 1 ]
par=""
for q in "core/guard.d/30-git scm" "jira/guard.d/70-jira tracker" "k8s/guard.d/25-k8s-rules kubernetes" \
         "core/guard.d/20-credentials base" "core/permissions base"; do
  # shellcheck disable=SC2086
  hrepo_owns $q "$rr"; a=$?; hr_py owns $q "$rr"; b=$?
  [ "$a" = "$b" ] || par="$par [$q: sh=$a py=$b]"
done
for q in "repo name" "owns domains" "owns components" "overrides WORK_TICKET_ALLOW_DEFAULT_PUSH_RE" "overrides X" "nope x"; do
  # shellcheck disable=SC2086
  a=$(hrepo_get "$rr/.harness.toml" $q); ra=$?; b=$(hr_py get $q "$rr"); rb=$?
  [ "$a" = "$b" ] && [ "$ra" = "$rb" ] || par="$par [get $q: sh=$ra '$a' py=$rb '$b']"
done
ck "bash and python helpers agree${par:+ —$par}" [ -z "$par" ]
# W2/W3 parity: a plain string in [owns] counts for no reader; a repeated key: the first one wins
printf '%s\n' '[repo]' 'name = "first"' 'name = "second"' '[owns]' 'domains = "scm"' \
  'components = ["core/guard.d/30-git"]' 'components = ["jira/guard.d/70-jira"]' > "$rr/.harness.toml"
par=""
for q in "core/guard.d/30-git scm" "jira/guard.d/70-jira tracker" "github/guard.d/60-github scm"; do
  # shellcheck disable=SC2086
  hrepo_owns $q "$rr"; a=$?; hr_py owns $q "$rr"; b=$?
  [ "$a" = "$b" ] || par="$par [$q: sh=$a py=$b]"
done
for q in "repo name" "owns domains" "owns components"; do
  # shellcheck disable=SC2086
  a=$(hrepo_get "$rr/.harness.toml" $q); ra=$?; b=$(hr_py get $q "$rr"); rb=$?
  [ "$a" = "$b" ] && [ "$ra" = "$rb" ] || par="$par [get $q: sh=$ra '$a' py=$rb '$b']"
done
ck "scalar [owns] values and repeated keys: bash and python agree${par:+ —$par}" [ -z "$par" ]
ck "a repeated key: the first one counts" [ "$(hrepo_get "$rr/.harness.toml" repo name)" = first ]
hrepo_owns github/guard.d/60-github scm "$rr"; r=$?; ck "domains = \"scm\" (not an array) owns nothing" [ "$r" = 1 ]
# size caps: 16 KiB and 400 lines (bash, python and the guard engine)
printf '%s\n' '[owns]' 'components = ["core/guard.d/30-git"]' > "$rr/.harness.toml"
awk 'BEGIN { for (i = 0; i < 398; i++) print "# padding" }' >> "$rr/.harness.toml"
hrepo_owns core/guard.d/30-git scm "$rr"; r=$?; hr_py owns core/guard.d/30-git scm "$rr"; r2=$?
ck "a 400-line declaration is read (bash and python)" [ "$r$r2" = 00 ]
printf '%s\n' '# line 401' >> "$rr/.harness.toml"
hrepo_owns core/guard.d/30-git scm "$rr"; r=$?; hr_py owns core/guard.d/30-git scm "$rr"; r2=$?
ck "a 401-line declaration is ignored (bash and python)" [ "$r$r2" = 11 ]
printf '%s\n' '[owns]' 'components = ["core/guard.d/30-git"]' > "$rr/.harness.toml"
awk 'BEGIN { for (i = 0; i < 200; i++) print "# padding line of the oversized declaration ......................................" }' >> "$rr/.harness.toml"
hrepo_owns core/guard.d/30-git scm "$rr"; r=$?; hr_py owns core/guard.d/30-git scm "$rr"; r2=$?
ck "a declaration over 16 KiB is ignored (bash and python)" [ "$r$r2" = 11 ]
# timing: the guard parses a full-size declaration (16 KiB, 400 lines) well inside the hook budget
{ printf '%s\n' '[owns]' 'components = ["core/guard.d/30-git"]' '[overrides]'
  awk 'BEGIN { for (i = 0; i < 397; i++) printf "WORK_TICKET_X%03d = \"%s\"\n", i, "abcdefghijklmnopqr" }'
} > "$rr/.harness.toml"
sz=$(($(wc -c < "$rr/.harness.toml"))); nl=$(($(wc -l < "$rr/.harness.toml")))
ck "timing fixture is at the caps (${sz} bytes, ${nl} lines)" [ "$sz" -le 16384 ] && [ "$sz" -gt 15000 ] && [ "$nl" = 400 ]
t0=$(date +%s)
d=$(jq -cn --arg cwd "$rr" '{cwd:$cwd,tool_input:{command:"git push origin master"}}' \
    | HARNESS_GUARD_ENV=/dev/null bash "$GUARD_BASH" 2>/dev/null | jq -r '.hookSpecificOutput.permissionDecision // "pass"')
t1=$(date +%s)
ck "the guard parses a 16 KiB / 400-line declaration in <= 2 s ($((t1 - t0)) s) and honours it" [ $((t1 - t0)) -le 2 ] && [ "$d" = pass ]
t0=$(date +%s); hrepo_owns core/guard.d/30-git scm "$rr"; r=$?; t1=$(date +%s)
ck "hrepo_owns reads it in <= 2 s ($((t1 - t0)) s)" [ $((t1 - t0)) -le 2 ] && [ "$r" = 0 ]

echo "----"
if [ $fail -eq 0 ]; then echo "all core tests passed ($cases cases)"; else echo "core tests FAILED"; fi
exit $fail
