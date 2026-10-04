#!/usr/bin/env bash
# Bundle tests: this bundle's guard rows against a guard built from core + this bundle only
# (proves the sections do not depend on any other bundle), then every skill suite under
# skills/*/scripts/tests/run.sh. Exit 1 on any failure.
set -uo pipefail
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
bdir=$(cd "$here/.." && pwd); name=$(basename "$bdir")
core=$(cd "$bdir/../core" && pwd)
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
fail=0

if [ -f "$bdir/guard.d/tests.sh" ]; then
  HARNESS_GUARD_BUNDLES=$name bash "$core/guard/build.sh" "$tmp/hooks/guard-bash.sh" || fail=1
  GUARD_BASH="$tmp/hooks/guard-bash.sh" HARNESS_TEST_BUNDLES=$name \
    bash "$core/guard/tests/run.sh" > "$tmp/guard.log" 2>&1 || { fail=1; grep -A1 '^FAIL' "$tmp/guard.log"; }
  echo "guard ($name + core): $(tail -1 "$tmp/guard.log")"
fi
for t in "$bdir"/skills/*/scripts/tests/run.sh; do
  [ -f "$t" ] || continue
  bash "$t" > "$tmp/skill.log" 2>&1 || { fail=1; grep -E '^FAIL' "$tmp/skill.log" | head -20; }
  echo "$(basename "$(dirname "$(dirname "$(dirname "$t")")")"): $(tail -1 "$tmp/skill.log")"
done
# ---- principle 8: work-ticket preflight detects a repository-level workflow (lib/repo-facts.sh)
rf="$bdir/skills/work-ticket/scripts/lib/repo-facts.sh"
rp="$tmp/repo"; mkdir -p "$rp/.claude/skills/ship" "$rp/.claude/skills/look" "$rp/sub"
git -C "$rp" init -q 2>/dev/null || mkdir -p "$rp/.git"
printf -- '---\nname: look\ndescription: Look up Jira tickets and GitHub issues and read their fields.\n---\n' \
  > "$rp/.claude/skills/look/SKILL.md"
rf_case() {  # EXPECTED_OWNS EXPECTED_SKILL(set|empty) LABEL
  local got want="$1 $2"
  got=$(cd "$rp/sub" && bash -c '. "$1"; rf_load; printf "%s %s" "$repo_owns" "${repo_skill:+set}"' _ "$rf" 2>&1)
  [ -n "${got#* }" ] || got="${got}empty"
  if [ "$got" = "$want" ]; then
    echo "PASS  repo-facts: $3"
  else
    echo "FAIL  repo-facts: $3 (got '$got', want '$1 $2')"; fail=1
  fi
}
rf_case false empty "lookup-only repository skill, no declaration: carry on"
printf '%s\n' '[owns]' 'domains = ["delivery"]' > "$rp/.harness.toml"
rf_case true empty "[owns] domains = delivery: repo_owns"
printf '%s\n' '[owns]' 'components = ["ticket-workflow/skills/work-ticket"]' > "$rp/.harness.toml"
rf_case true empty "[owns] components = the skill id: repo_owns"
printf '%s\n' '[owns]' 'domains = ["tracker"]' > "$rp/.harness.toml"
rf_case false empty "another domain: not owned"
printf '%s\n' '[owns]' 'domains = ["delivery"] # inline comment' > "$rp/.harness.toml"
rf_case false empty "malformed declaration: fail open"
rm -f "$rp/.harness.toml"
printf -- '---\nname: ship\ndescription: >-\n  Work a ticket end to end: branch,\n  commits and a merge request.\nmodel: x\n---\nbody\n' \
  > "$rp/.claude/skills/ship/SKILL.md"
rf_case false set "folded description covering ticket -> MR: repo_skill (any name)"
printf -- '---\nname: ship\ndescription: Picks up an issue and opens a PR for it.\n---\n' > "$rp/.claude/skills/ship/SKILL.md"
rf_case false set "one-line description covering issue -> PR: repo_skill"
[ $fail -eq 0 ] && echo "all $name tests passed" || echo "$name tests FAILED"
exit $fail
