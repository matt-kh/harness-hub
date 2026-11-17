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
tw_repo "$R/gh-trk"    "$GH_SSH"                                   "$L/tracker-jira"
tw_repo "$R/gl-trkbad" "https://gitlab.example.com/group/repo.git" "$L/tracker-bad"
mkdir -p "$R/norepo"
snap() { local d; for d in "$R"/*/; do printf '== %s\n' "$d"; git -C "$d" for-each-ref --format='%(refname) %(objectname)' 2>/dev/null
         git -C "$d" status --porcelain 2>/dev/null; git -C "$d" config --get-regexp '^remote\.' 2>/dev/null | wc -l; done; }
snap > "$tmp/repos.before"
# the gh-stack extension manifest gh writes on `gh extension install … --pin` (read for gh_stack.pinned)
mf="$HOME/.local/share/gh/extensions/gh-stack"; mkdir -p "$mf" "$tmp/xdg-unpinned/gh/extensions/gh-stack" "$tmp/gh-data-empty"
printf 'owner: github\nname: gh-stack\nhost: github.com\ntag: v0.3.0\nispinned: true\npath: %s\n' "$mf/gh-stack" > "$mf/manifest.yml"
sed 's/^ispinned: true$/ispinned: false/' "$mf/manifest.yml" > "$tmp/xdg-unpinned/gh/extensions/gh-stack/manifest.yml"

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
t gh-tracker-repo-jira   0 -                 "$R/gh-trk"    "$G" 7 feat-x
# issue.close_on_merge: default true (gh-admin-*); the knob off in the config or the guard's env,
# a jira tracker (gh-tracker-repo-jira), the fork flow (gh-fork), an origin fork with write access on
# the parent (gh-set-default: origin != base_repo) and an issue in another repository -> false
HARNESS_CONFIG_JSON="$FIXT/config-close-off.json" \
  t gh-close-on-merge-off 0 -                "$R/gh-block"  "$G" '#7' feat-x
HARNESS_GITHUB_CLOSE_ISSUE_ON_MERGE=false \
  t gh-close-on-merge-env-off 0 -            "$R/gh-block"  "$G" '#7' feat-x
t gh-close-other-repo    0 gh-close-other-repo "$R/gh-block"  "$G" other/repo#9 feat-x
# the guard's own guard.env off switch is final (last line wins, quotes stripped); a quoted true stays on
HARNESS_GUARD_ENV="$FIXT/guard-env-close-off.env" HARNESS_GITHUB_CLOSE_ISSUE_ON_MERGE=true \
  t gh-close-guard-env-off 0 -               "$R/gh-block"  "$G" '#7' feat-x
HARNESS_GUARD_ENV="$FIXT/guard-env-close-on.env" \
  t gh-close-guard-env-on 0 -                "$R/gh-block"  "$G" '#7' feat-x
# gh_stack: github/gh-stack at the configured version with a pinned manifest (ispinned: true in
# $HOME/.local/share) and two pages of stacks is the base fixture. Then: another version (with
# malformed stack entries dropped), another extension only, no extension at all, a third-party
# `gh stack`, a version that is not semver, the Stacks API answering 404 or another shape, the
# configured version from the environment (v prefix dropped), an unpinned manifest
# (XDG_DATA_HOME) and an unreadable one (GH_DATA_DIR without a manifest).
t gh-stack-other-version 0 gh-stack-other-version "$R/gh-cred" "$G" 7 feat-x
t gh-stack-absent        0 gh-stack-absent   "$R/gh-cred"   "$G" 7 feat-x
t gh-stack-none          0 gh-stack-none     "$R/gh-cred"   "$G" 7 feat-x
t gh-stack-third-party   0 gh-stack-third-party "$R/gh-cred" "$G" 7 feat-x
t gh-stack-raw-version   0 gh-stack-raw-version "$R/gh-cred" "$G" 7 feat-x
t gh-stack-repo-404      0 gh-stack-repo-404 "$R/gh-cred"   "$G" 7 feat-x
t gh-stack-bad-shape     0 gh-stack-bad-shape "$R/gh-cred"  "$G" 7 feat-x
HARNESS_GITHUB_STACK_EXT_VERSION=v0.2.1 \
  t gh-stack-pin-env     0 gh-stack-other-version "$R/gh-cred" "$G" 7 feat-x
XDG_DATA_HOME="$tmp/xdg-unpinned" \
  t gh-stack-unpinned    0 -                 "$R/gh-cred"   "$G" 7 feat-x
GH_DATA_DIR="$tmp/gh-data-empty" \
  t gh-stack-no-manifest 0 -                 "$R/gh-cred"   "$G" 7 feat-x

# ------------------------------------------------------------------------- gitlab-preflight.sh
B="$S/gitlab-preflight.sh"
YAML=json t gl-yaml      0 -                 "$R/gl"        "$B" feat-x feat-x-sub-01-api release/1.0
t gl-grep                0 -                 "$R/gl-block"  "$B" feat-x
YAML=json t gl-old-wildcard 0 gl-old-wildcard "$R/gl"       "$B" feat-x feat-x-sub-01-api
t gl-api-down            0 gl-api-down       "$R/gl-bare"   "$B" feat-x
t gl-no-ci-default-from-api 0 -              "$R/gl-bare"   "$B"
t gl-repo-owns           0 -                 "$R/gl-owns"   "$B"
t gl-repo-skill          0 -                 "$R/gl-skill"  "$B"
HARNESS_CONFIG_JSON="$FIXT/config-trackers.json" \
  t gl-tracker-config    0 -                 "$R/gl-bare"   "$B"
t gl-tracker-invalid     0 -                 "$R/gl-trkbad" "$B"

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
HARNESS_CONFIG_JSON="$FIXT/config-trackers.json" \
  t if-tracker-config    0 -                 "$R/gh-cred"   "$I" 7

# ------------------------------------------------------------------------- jira-facts.sh
J="$S/jira-facts.sh"
t jf-full                0 -                 "$R/norepo"    "$J" PROJ-123
t jf-relates-task        0 jf-relates-task   "$R/norepo"    "$J" PROJ-123
t jf-no-create           0 jf-no-create      "$R/norepo"    "$J" PROJ-123
t jf-no-link-types       0 jf-no-link-types  "$R/norepo"    "$J" PROJ-123
t jf-unreachable         0 jf-unreachable    "$R/norepo"    "$J" PROJ-123
t jf-usage               1 -                 "$R/norepo"    "$J"
t jf-tracker-repo        0 -                 "$R/gh-trk"    "$J" PROJ-123

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

# rf_remote_id / rf_tracker over remote URL shapes x declaration sources (one golden table):
# none (host heuristic), the user's ticket_workflow.trackers, .harness.toml [repo] tracker
# (valid, invalid). The declaration wins over the config, the config over the host.
tw_repo "$tmp/rt" "https://example.com/x.git" "$L/bare"
{
  while read -r shape url; do
    git -C "$tmp/rt" remote set-url origin "$url"
    for src in none config repo-jira repo-invalid; do
      cfg=/dev/null; rm -f "$tmp/rt/.harness.toml"
      case "$src" in
        config)       cfg="$FIXT/config-trackers.json" ;;
        repo-jira)    cfg="$FIXT/config-trackers.json"; cp "$L/tracker-jira/dot-harness.toml" "$tmp/rt/.harness.toml" ;;
        repo-invalid) cp "$L/tracker-bad/dot-harness.toml" "$tmp/rt/.harness.toml" ;;
      esac
      got=$(cd "$tmp/rt" && HARNESS_CONFIG_JSON=$cfg bash -c '. "$1"; rf_tracker "$(rf_root)"' _ "$rf" 2>&1)
      printf '%-22s | %-12s | %s\n' "$shape" "$src" "$got"
    done
  done <<EOF
scp-ssh                $GH_SSH
https-credentialed     $GH_CRED
ssh-port-443           ssh://git@ssh.github.com:443/owner/repo.git
https-www-no-suffix    https://www.github.com/owner/repo
https-mixed-case       https://GitLab.Example.com/group/repo.git
scp-ssh-subgroup       git@gitlab.example.com:group/sub/repo.git
ssh-custom-port        ssh://git@code.example.com:2222/group/repo.git
https-custom-port      https://code.example.com:8443/other/repo.git/
https-enterprise-host  https://github.example.com/owner/repo.git
local-path             /srv/git/repo.git
EOF
} > "$tmp/rf-tracker.txt"
rm -f "$tmp/rt/.harness.toml"
tw_norm "$tmp/rf-tracker.txt"; record rf-tracker "$tmp/rf-tracker.txt"

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
bad=$(grep -E '^gh ext(ension)?s? ' "$A" | grep -vE '^gh extension list$' | head -3)
ck "gh: never installs, upgrades, removes or runs an extension (only gh extension list)" [ -z "$bad" ]
bad=$(grep -E '^gh (label|pr|issue) (list|view)( |$)' "$A" | grep -v -- ' -R [^ ]*/' | head -3)
ck "gh: every label/pr/issue list|view carries -R owner/repo" [ -z "$bad" ]
bad=$(grep -E '^gh repo view' "$A" | grep -vE '^gh repo view [^ -][^ ]*/[^ ]+ --json ' | head -3)
ck "gh: every repo view names owner/repo and --json" [ -z "$bad" ]
bad=$(grep '^gh ' "$A" | grep -vE '^gh (auth status|api |repo view |repo set-default --view$|extension list$|label list|pr list |issue view )' | head -3)
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
