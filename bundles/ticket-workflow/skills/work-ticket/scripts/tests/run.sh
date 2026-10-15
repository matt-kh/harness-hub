#!/usr/bin/env bash
# Golden tests for the work-ticket scripts: preflight.sh (provider dispatch), github-preflight.sh,
# gitlab-preflight.sh, issue-facts.sh, jira-facts.sh and lib/repo-facts.sh.
# gh, glab and jira are fixture-routed stubs (bundles/ticket-workflow/tests/stubs); git is REAL:
# every fixture repository is a throw-away `git init` with fixed dates and an origin URL that is
# never contacted. PyYAML is pinned per case (YAML=json: the json-backed stand-in; default: hidden),
# so the structured and the grep CI branches both run whatever the host has installed.
# Goldens normalise the sandbox path (SANDBOX) and this directory (HERE).
# UPDATE=1 rewrites golden/ (review the diff); KEEP=1 keeps the sandbox. Exits non-zero on failure.
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
S=$(cd "$here/.." && pwd)
# shellcheck source=../../../../tests/stubs/lib.sh
. "$here/../../../../tests/stubs/lib.sh"
tw_init "$here"
L="$FIXT/repos"
R="$tmp/repos"

# ------------------------------------------------------------------------- fixture repositories
# Documentation values only. The credentialed URL proves that no credential reaches the output;
# it is assembled here so that no file carries a URL with a credential in it.
cred="x-access-token:test-access-token"
GH_SSH="git@github.com:owner/repo.git"
GH_CRED="https://${cred}@github.com/owner/repo.git"
tw_repo "$R/gh"        "$GH_SSH"                                   "$L/gh-yaml"
tw_repo "$R/gh-block"  "https://github.com/owner/repo.git"         "$L/gh-block"
tw_repo "$R/gh-bad"    "$GH_SSH"                                   "$L/gh-yaml"
printf '{ "name": "broken", "on": [push\n' > "$R/gh-bad/.github/workflows/broken.yml"   # unparseable, untracked: dirty_files 1
tw_repo "$R/gh-cred"   "$GH_CRED"                                  "$L/bare"
tw_repo "$R/gh-fork"   "git@github.com:dev/repo.git"               "$L/bare"
tw_repo "$R/gh-nohead" "ssh://git@github.com/owner/repo.git"      "$L/bare" nohead
tw_repo "$R/gh-owns"   "$GH_SSH"                                   "$L/owns"
tw_repo "$R/gh-skill"  "$GH_SSH"                                   "$L/skill"
tw_repo "$R/gl"        "git@gitlab.example.com:group/repo.git"     "$L/gl-yaml"
tw_repo "$R/gl-block"  "https://gitlab.example.com/group/repo.git" "$L/gl-block"
tw_repo "$R/gl-bare"   "https://gitlab.example.com/group/repo.git" "$L/bare" nohead
tw_repo "$R/gl-owns"   "https://gitlab.example.com/group/repo.git" "$L/owns"
tw_repo "$R/gl-skill"  "https://gitlab.example.com/group/repo.git" "$L/skill"
tw_repo "$R/code"      "ssh://git@code.example.com:2222/group/repo.git" "$L/bare"
mkdir -p "$R/norepo"
snap() { local d; for d in "$R"/*/; do printf '== %s\n' "$d"; git -C "$d" for-each-ref --format='%(refname) %(objectname)' 2>/dev/null
         git -C "$d" status --porcelain 2>/dev/null; git -C "$d" config --get-regexp '^remote\.' 2>/dev/null | wc -l; done; }
snap > "$tmp/repos.before"

# ------------------------------------------------------------------------- preflight.sh: dispatch
P="$S/preflight.sh"
t pf-github         0 -  "$R/gh-block" "$P" '#7' feat-x
t pf-gitlab-by-name 0 -  "$R/gl-block" "$P" feat-x
HARNESS_GITLAB_HOSTS_RE='^(code|git)\.example\.com$' \
  t pf-gitlab-hosts-re  0 - "$R/code" "$P"
HARNESS_GITLAB_HOST=code.example.com \
  t pf-gitlab-host-env  0 - "$R/code" "$P"
HARNESS_CONFIG_JSON="$FIXT/config-gitlab-host.json" \
  t pf-gitlab-host-config 0 - "$R/code" "$P"
t pf-unknown        1 -  "$R/code" "$P"
t pf-no-repo        1 -  "$R/norepo" "$P"

# ------------------------------------------------------------------------- github-preflight.sh
G="$S/github-preflight.sh"
YAML=json t gh-admin-public-yaml 0 - "$R/gh" "$G" '#7' feat-x feat-x-sub-01-api release/1.0
t gh-admin-public-grep   0 -                 "$R/gh-block"  "$G" '#7' feat-x feat-x-sub-01-api
t gh-read-private-free   0 gh-private-free   "$R/gh-cred"   "$G" 7 feat-x
t gh-fork                0 gh-fork           "$R/gh-fork"   "$G" 7 feat-x
t gh-set-default         0 gh-set-default    "$R/gh-fork"   "$G" owner/repo#7 feat-x
t gh-unauth              0 gh-unauth         "$R/gh-cred"   "$G" 7 feat-x
WORK_TICKET_GH=gh-not-installed \
  t gh-not-installed     0 -                 "$R/gh-cred"   "$G" 7 feat-x
t gh-repo-owns           0 -                 "$R/gh-owns"   "$G" 7
t gh-repo-skill          0 -                 "$R/gh-skill"  "$G" 7
YAML=json t gh-issue-url 0 -                 "$R/gh"        "$G" https://github.com/owner/repo/issues/7 feat-x
t gh-no-issue            0 -                 "$R/gh-cred"   "$G"
t gh-default-from-api    0 -                 "$R/gh-nohead" "$G" 7 feat-x
YAML=json t gh-unparseable-workflow 0 -      "$R/gh-bad"    "$G" 7 feat-x
t gh-protection-errors   0 gh-protection-errors "$R/gh-cred" "$G" 7 feat-x

# ------------------------------------------------------------------------- gitlab-preflight.sh
B="$S/gitlab-preflight.sh"
YAML=json t gl-yaml      0 -                 "$R/gl"        "$B" feat-x feat-x-sub-01-api release/1.0
t gl-grep                0 -                 "$R/gl-block"  "$B" feat-x
YAML=json t gl-old-wildcard 0 gl-old-wildcard "$R/gl"       "$B" feat-x feat-x-sub-01-api
t gl-api-down            0 gl-api-down       "$R/gl-bare"   "$B" feat-x
t gl-no-ci-default-from-api 0 -              "$R/gl-bare"   "$B"
t gl-repo-owns           0 -                 "$R/gl-owns"   "$B"
t gl-repo-skill          0 -                 "$R/gl-skill"  "$B"

# ------------------------------------------------------------------------- issue-facts.sh
I="$S/issue-facts.sh"
t if-number              0 -                 "$R/gh-cred"   "$I" 7
t if-hash                0 -                 "$R/gh-cred"   "$I" '#7'
t if-owner-repo          0 if-other-repo     "$R/gh-cred"   "$I" other/repo#9
t if-url                 0 if-other-repo     "$R/gh-cred"   "$I" https://github.com/other/repo/issues/9
t if-fork                0 gh-fork           "$R/gh-fork"   "$I" 7
t if-set-default         0 gh-set-default    "$R/gh-fork"   "$I" 7
t if-pull-request        0 if-pull-request   "$R/gh-cred"   "$I" 21
t if-unauth              0 gh-unauth         "$R/gh-cred"   "$I" 7
t if-not-a-ref           1 -                 "$R/gh-cred"   "$I" abc
t if-usage               1 -                 "$R/gh-cred"   "$I"

# ------------------------------------------------------------------------- jira-facts.sh
J="$S/jira-facts.sh"
t jf-full                0 -                 "$R/norepo"    "$J" PROJ-123
t jf-relates-task        0 jf-relates-task   "$R/norepo"    "$J" PROJ-123
t jf-no-create           0 jf-no-create      "$R/norepo"    "$J" PROJ-123
t jf-no-link-types       0 jf-no-link-types  "$R/norepo"    "$J" PROJ-123
t jf-unreachable         0 jf-unreachable    "$R/norepo"    "$J" PROJ-123
t jf-usage               1 -                 "$R/norepo"    "$J"

# ------------------------------------------------------------------------- lib/repo-facts.sh
# rf_host / rf_provider over remote URL shapes (one golden table)
rf="$S/lib/repo-facts.sh"
tw_repo "$tmp/rf" "https://example.com/x.git" "$L/bare"
{
  while read -r shape url; do
    git -C "$tmp/rf" remote set-url origin "$url"
    for env in "" "HARNESS_GITLAB_HOSTS_RE=^code[.]example[.]com$" "HARNESS_GITLAB_HOST=code.example.com"; do
      got=$(cd "$tmp/rf" && env ${env:+"$env"} bash -c '. "$1"; h=$(rf_host "$(rf_root)"); printf "%s -> %s" "$h" "$(rf_provider "$h")"' _ "$rf" 2>&1)
      printf '%-22s | %-46s | %s\n' "$shape" "${env:-(no gitlab config)}" "${got/%-> /-> (unknown)}"
    done
  done <<EOF
scp-ssh                $GH_SSH
https-credentialed     $GH_CRED
ssh-port-443           ssh://git@ssh.github.com:443/owner/repo.git
https-www-no-suffix    https://www.github.com/owner/repo
https-mixed-case       https://GitLab.Example.com/group/repo.git
scp-ssh-subgroup       git@gitlab.example.com:group/sub/repo.git
ssh-custom-port        ssh://git@code.example.com:2222/group/repo.git
https-custom-port      https://code.example.com:8443/group/repo.git
https-enterprise-host  https://github.example.com/owner/repo.git
EOF
} > "$tmp/rf-hosts.txt"
tw_norm "$tmp/rf-hosts.txt"; record rf-hosts "$tmp/rf-hosts.txt"

# repo_owns / repo_skill detection (principle 8), formerly in bundles/ticket-workflow/tests/run.sh
rp="$tmp/rf-repo"; mkdir -p "$rp/.claude/skills/ship" "$rp/.claude/skills/look" "$rp/sub"
git -C "$rp" init -q
printf -- '---\nname: look\ndescription: Look up Jira tickets and GitHub issues and read their fields.\n---\n' \
  > "$rp/.claude/skills/look/SKILL.md"
rf_case() {  # EXPECTED_OWNS EXPECTED_SKILL(set|empty) LABEL
  local got want="$1 $2"
  got=$(cd "$rp/sub" && bash -c '. "$1"; rf_load; printf "%s %s" "$repo_owns" "${repo_skill:+set}"' _ "$rf" 2>&1)
  [ -n "${got#* }" ] || got="${got}empty"
  if [ "$got" = "$want" ]; then chk 0 "repo-facts: $3"; else chk 1 "repo-facts: $3 (got '$got', want '$want')"; fi
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

# ------------------------------------------------------------------------- invariants
A="$tmp/calls.all"
bad=$(grep '^gh ' "$A" | grep -v '^gh api graphql -f query=query(' | grep -E -- ' (-f|-F|--field|--raw-field|--input|-X|--method)( |=|$)' | head -3)
ck "gh: no write flags (-f/-F/--input/-X) outside the read-only graphql query" [ -z "$bad" ]
bad=$(grep -E '^gh api graphql' "$A" | grep -iE 'mutation' | head -3)
ck "gh: the graphql call is never a mutation" [ -z "$bad" ]
bad=$(grep -E '^gh (label|pr|issue) (list|view)( |$)' "$A" | grep -v -- ' -R [^ ]*/' | head -3)
ck "gh: every label/pr/issue list|view carries -R owner/repo" [ -z "$bad" ]
bad=$(grep -E '^gh repo view' "$A" | grep -vE '^gh repo view [^ -][^ ]*/[^ ]+ --json ' | head -3)
ck "gh: every repo view names owner/repo and --json" [ -z "$bad" ]
bad=$(grep '^gh ' "$A" | grep -vE '^gh (auth status|api |repo view |repo set-default --view$|label list |pr list |issue view )' | head -3)
ck "gh: only read verbs" [ -z "$bad" ]
bad=$(grep '^glab ' "$A" | grep -vE '^glab api [^ -][^ ]*$' | head -3)
ck "glab: only plain GETs through glab api" [ -z "$bad" ]
bad=$(grep '^jira ' "$A" | grep -vE '^jira (whoami|api /rest/api/2/[^ ]+|get [A-Z][A-Z0-9]*-[0-9]+)$' | head -3)
ck "jira: only whoami, api GETs and get" [ -z "$bad" ]
bad=$(grep -rlE 'test-access-token|x-access-token|git@|://[^ /"]*@' "$tmp"/*.txt 2>/dev/null | head -3)
ck "no credential and no remote URL in any golden" [ -z "$bad" ]
snap > "$tmp/repos.after"
ck "fixture repositories unchanged (refs, status, remotes): the scripts are read-only" cmp -s "$tmp/repos.before" "$tmp/repos.after"

tw_finish work-ticket
