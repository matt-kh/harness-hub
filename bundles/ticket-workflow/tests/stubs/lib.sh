# shellcheck shell=bash
# Shared kit for the ticket-workflow skill suites (sourced by skills/*/scripts/tests/run.sh).
#
#   tw_init SUITE_DIR    hermetic environment and sandbox: LC_ALL=C, an empty HOME, no harness
#                        config, deterministic git identity and dates, GIT_CONFIG_GLOBAL=/dev/null,
#                        and PATH = bin/{gh,glab,jira} stubs + a private bin of the system tools
#                        the scripts use (so a real gh/glab/jira is never reachable, and a host
#                        without `timeout` runs the python fallback exactly as the scripts do)
#   tw_repo DIR URL [LAYOUT_DIR] [nohead]
#                        a throw-away git repository with `origin` = URL (never contacted),
#                        origin/main and origin/HEAD (unless nohead); LAYOUT_DIR is copied in and
#                        committed, top-level `dot-X` entries become `.X`
#   t NAME EXIT SCENARIO REPO SCRIPT ARGS...
#                        run SCRIPT in REPO (a directory) with the stubs routed by
#                        fixtures/scenarios/SCENARIO.json (`-` = base fixtures only); YAML=json
#                        pins the PyYAML branch (json-backed stand-in), anything else hides PyYAML;
#                        the golden is `# exit / # stderr / # stdout / # calls:`
#   record NAME FILE     compare FILE with golden/NAME.txt (UPDATE=1 rewrites it)
#   chk RC LABEL / ck LABEL TEST...    one assertion
#   tw_finish SUITE      clean up (KEEP=1 keeps the sandbox), print the summary, exit
# Every stub call lands in $tmp/calls.all for the suite's invariants; a call with no route
# fails its case.
tw_stubs=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

tw_init() {
  here=$1; GOLD="$here/golden"; FIXT="$here/fixtures"
  unset WORK_TICKET_GH HARNESS_GITLAB_HOSTS_RE HARNESS_GITLAB_HOST HARNESS_GITHUB_HOST HARNESS_HOME \
        HARNESS_JIRA_FIELDS_PROBLEM_DESCRIPTION_ID GH_REPO GH_HOST GH_TOKEN GITHUB_TOKEN GITLAB_HOST \
        GITLAB_TOKEN PYTHONPATH PYTHONHOME GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE TW_FIXTURE
  export LC_ALL=C TZ=UTC HARNESS_CONFIG_JSON=/dev/null PYTHONDONTWRITEBYTECODE=1
  export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 GIT_TERMINAL_PROMPT=0 \
         GIT_AUTHOR_NAME=Dev GIT_AUTHOR_EMAIL=dev@example.com GIT_COMMITTER_NAME=Dev \
         GIT_COMMITTER_EMAIL=dev@example.com GIT_AUTHOR_DATE='2026-01-01T00:00:00Z' \
         GIT_COMMITTER_DATE='2026-01-01T00:00:00Z'
  tmp=$(mktemp -d); tmp=$(cd "$tmp" && pwd -P)
  export HOME="$tmp/home" GIT_CEILING_DIRECTORIES="$tmp"
  mkdir -p "$HOME" "$tmp/sysbin" "$GOLD"
  SYSBIN="$tmp/sysbin"
  local b p
  for b in bash sh env git jq python3 sed awk grep tr cut head tail wc find sort xargs mktemp rm cat \
           dirname basename ls mkdir cp mv diff cmp uname; do
    p=$(command -v "$b") || { echo "FAIL setup: $b not on PATH"; exit 1; }
    ln -s "$p" "$SYSBIN/$b"
  done
  for b in timeout gtimeout; do   # optional, exactly like the scripts' hn_timeout
    if p=$(command -v "$b" 2>/dev/null); then ln -s "$p" "$SYSBIN/$b"; fi
  done
  export PATH="$tw_stubs/bin:$SYSBIN" TW_FIXTURES="$FIXT"
  : > "$tmp/calls.all"
  fail=0; cases=0
}

tw_q() { "$@" > /dev/null 2>&1 || { echo "FAIL setup: $*"; exit 1; }; }

tw_repo() {
  local d=$1 url=$2 layout=${3:-} f
  tw_q mkdir -p "$d"
  tw_q git -C "$d" init -q
  tw_q git -C "$d" symbolic-ref HEAD refs/heads/main
  if [ -n "$layout" ]; then
    tw_q cp -R "$layout/." "$d/"
    for f in "$d"/dot-*; do
      [ -e "$f" ] || continue
      tw_q mv "$f" "$d/.${f##*/dot-}"
    done
  fi
  printf 'fixture repository\n' > "$d/README.md"
  tw_q git -C "$d" add -A
  tw_q git -C "$d" commit -q -m "fixture"
  tw_q git -C "$d" remote add origin "$url"
  tw_q git -C "$d" update-ref refs/remotes/origin/main HEAD
  [ "${4:-}" = nohead ] || tw_q git -C "$d" symbolic-ref refs/remotes/origin/HEAD refs/remotes/origin/main
}

tw_norm() {  # FILE: the sandbox, this suite and the stubs never reach a golden
  python3 - "$1" "$tmp" "$here" "$tw_stubs" <<'PY'
import sys
p, tmp, here, stubs = sys.argv[1:5]
t = open(p).read().replace(tmp, "SANDBOX").replace(here, "HERE").replace(stubs, "STUBS")
open(p, "w").write(t)
PY
}

record() {
  local name=$1 g=$2
  cases=$((cases + 1))
  if [ "${UPDATE:-0}" = 1 ]; then cp "$g" "$GOLD/$name.txt"; echo "UPDATED $name"; return; fi
  if [ ! -f "$GOLD/$name.txt" ]; then echo "FAIL $name (no golden; run UPDATE=1 and review the diff)"; fail=1; return; fi
  if diff -u "$GOLD/$name.txt" "$g" > "$tmp/$name.diff"; then echo "PASS $name"
  else echo "FAIL $name"; head -40 "$tmp/$name.diff"; fail=1; fi
}

t() {
  local name=$1 exp=$2 scen=$3 dir=$4 script=$5 rc fx="" g d="$tmp/run/$1"; shift 5
  mkdir -p "$d"
  if [ "$scen" != - ]; then
    fx="$FIXT/scenarios/$scen.json"
    [ -f "$fx" ] || { echo "FAIL $name: no scenario $fx"; fail=1; cases=$((cases + 1)); return; }
  fi
  : > "$d/calls"; : > "$d/miss"
  (cd "$dir" && TW_FIXTURE=$fx STUB_LOG="$d/calls" STUB_MISS="$d/miss" \
     PYTHONPATH="$tw_stubs/pymod/yaml-${YAML:-absent}" bash "$script" "$@") > "$d/out" 2> "$d/err"; rc=$?
  cat "$d/calls" >> "$tmp/calls.all"
  cp "$d/out" "$tmp/$name.out"
  [ "$rc" = "$exp" ] || { echo "FAIL $name: exit $rc, expected $exp"; cat "$d/err"; fail=1; }
  if [ -s "$d/miss" ]; then echo "FAIL $name: unrouted stub call(s):"; sed 's/^/  /' "$d/miss"; fail=1; fi
  if ! jq -e -s 'length == 1 and (.[0] | type == "object")' "$d/out" > /dev/null 2>&1; then
    echo "FAIL $name: stdout is not exactly one JSON object"; fail=1
  fi
  g="$tmp/$name.txt"
  { echo "# exit=$rc"; echo "# stderr:"; cat "$d/err"; echo "# stdout:"; cat "$d/out"
    echo "# calls:"; cat "$d/calls"; } > "$g"
  tw_norm "$g"
  record "$name" "$g"
}

chk() {
  cases=$((cases + 1))
  if [ "$1" = 0 ]; then echo "PASS $2"; else echo "FAIL $2"; fail=1; fi
}
ck() { local l=$1; shift; "$@"; chk $? "$l"; }

tw_finish() {
  if [ "${KEEP:-0}" = 1 ]; then echo "artifacts in $tmp"; else rm -rf "$tmp"; fi
  if [ $fail -eq 0 ]; then echo "all $1 tests passed ($cases cases)"; else echo "$1 tests FAILED"; fi
  exit $fail
}
