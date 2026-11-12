#!/usr/bin/env bash
# Golden tests for repoboot.py. gh, glab and harness are stubbed (stub.py answers GETs from a
# per-case fixture and logs every call); git is REAL: each case gets a sandbox with a bare
# `origin.git` that the SSH URL of the repository is redirected to (url.<bare>.insteadOf in a
# private GIT_CONFIG_GLOBAL), deterministic identity and dates, and REPOBOOT_TODAY.
# A case writes everything it observed (CLI output, stub log, git state) to one transcript that
# is compared with golden/<case>.txt after the sandbox path is replaced by SANDBOX.
# UPDATE=1 rewrites golden/. KEEP=1 keeps the sandboxes. Exits non-zero on any failure.
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
CLI="$here/../repoboot.py"
GOLD="$here/golden"
export GH="$here/gh-stub.sh" GLAB="$here/glab-stub.sh" HARNESS="$here/harness-stub.sh"
export HARNESS_CONFIG_JSON=/dev/null REPOBOOT_TODAY=2026-01-01
unset HARNESS_REPO_BOOTSTRAP_PACK_DIRS HARNESS_REPO_BOOTSTRAP_DEFAULT_VISIBILITY \
      HARNESS_REPO_BOOTSTRAP_DEFAULT_MERGE_METHOD HARNESS_REPO_BOOTSTRAP_REQUIRED_APPROVALS \
      HARNESS_REPO_BOOTSTRAP_DEFAULT_LICENSE HARNESS_REPO_BOOTSTRAP_GITHUB_OWNER \
      HARNESS_REPO_BOOTSTRAP_GITLAB_NAMESPACE HARNESS_REPO_BOOTSTRAP_GITLAB_REMOVE_SOURCE_BRANCH \
      HARNESS_GITLAB_HOST HARNESS_GITLAB_HOSTS_RE WORK_TICKET_LABEL GH_REPO GITLAB_HOST \
      GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE
export HARNESS_BUNDLES=core GIT_CONFIG_NOSYSTEM=1 GIT_TERMINAL_PROMPT=0 \
       GIT_AUTHOR_NAME=Dev GIT_AUTHOR_EMAIL=dev@example.com GIT_COMMITTER_NAME=Dev \
       GIT_COMMITTER_EMAIL=dev@example.com GIT_AUTHOR_DATE='2026-01-01T00:00:00Z' \
       GIT_COMMITTER_DATE='2026-01-01T00:00:00Z'
tmp=$(mktemp -d); tmp=$(cd "$tmp" && pwd -P)
fail=0; cases=0
mkdir -p "$GOLD"
TESTPACKS="$here/packs"
GHURL=git@github.com:o/r.git
GLURL=git@gitlab.example.com:grp/r.git

# ------------------------------------------------------------------------- sandbox kit
sandbox() {  # sandbox D URL: bare origin + global git config redirecting URL to it
  local d=$1
  mkdir -p "$d"
  git init -q --bare -b main "$d/origin.git"
  export GIT_CONFIG_GLOBAL="$d/gitconfig"
  git config --file "$d/gitconfig" "url.$d/origin.git.insteadOf" "$2"
  git config --file "$d/gitconfig" init.defaultBranch main
  export STUB_LOG="$d/stub.log" RB_FIXTURE="$d/fixture.json"
  : > "$STUB_LOG"; echo '{}' > "$RB_FIXTURE"
}
fixture() { cat > "$RB_FIXTURE"; }
rb() {  # rb ARGS...: run the CLI, transcript gets the command, its rc and its output
  echo "\$ repoboot $*"
  python3 "$CLI" "$@" --json 2>&1
  echo "[rc $?]"
}
rbt() {  # text output
  echo "\$ repoboot $* --text"
  python3 "$CLI" "$@" --text 2>&1
  echo "[rc $?]"
}
calls() { echo "--- stub calls"; cat "$STUB_LOG"; : > "$STUB_LOG"; }
gitstate() {  # gitstate DIR
  echo "--- git log"
  git -C "$1" log --format='%s' --name-status 2>&1
  echo "--- origin heads"
  git --git-dir "$(dirname "$1")/origin.git" for-each-ref --format='%(refname)' refs/heads 2>&1
}
seed() {  # seed D URL: an existing checkout with history on main, pushed to origin
  git init -q -b main "$1/r"
  git -C "$1/r" remote add origin "$2"
  printf 'old\n' > "$1/r/README.md"
  git -C "$1/r" add README.md && git -C "$1/r" commit -qm "initial"
  git -C "$1/r" push -q -u origin main 2>/dev/null
  git -C "$1/r" symbolic-ref refs/remotes/origin/HEAD refs/remotes/origin/main
}
GH_REPO_JSON='{"default_branch": "main", "visibility": "private", "delete_branch_on_merge": false,
  "allow_auto_merge": false, "allow_squash_merge": true, "allow_merge_commit": true, "allow_rebase_merge": true}'
GL_PROJ_JSON='{"default_branch": "main", "visibility": "private", "empty_repo": false, "merge_method": "merge",
  "squash_option": "default_off", "only_allow_merge_if_pipeline_succeeds": false,
  "only_allow_merge_if_all_discussions_are_resolved": false, "remove_source_branch_after_merge": true}'
GH_ANSWERS="repo.host=github repo.owner=o repo.name=r architecture.kind=service architecture.languages=python
  workflow.codeowners=@o/team quality.ci_jobs=lint,test"
GL_ANSWERS="repo.host=gitlab repo.owner=grp repo.name=r repo.server=gitlab.example.com architecture.kind=library
  workflow.tracker=jira workflow.tracker_project=PROJ"

# ------------------------------------------------------------------------- cases
case_local_new() {
  local d=$1; sandbox "$d" "$GHURL"
  rbt questions --dir "$d/r" --round 1
  rb answer --dir "$d/r" repo.host=local architecture.kind=docs repo.license=MIT "repo.license_holder=Example Ltd" --accept-defaults
  rbt plan --dir "$d/r"
  rb apply --dir "$d/r"
  gitstate "$d/r"
  echo "--- README.md"; cat "$d/r/README.md"
  echo "--- .repo-standard.toml"; cat "$d/r/.repo-standard.toml"
  rbt check --dir "$d/r"
  calls
}
case_gh_new() {  # pack questions in round 2, full create + configure, ruleset body
  local d=$1; sandbox "$d" "$GHURL"; export HARNESS_REPO_BOOTSTRAP_PACK_DIRS="$TESTPACKS"
  # shellcheck disable=SC2086
  rb answer --dir "$d/r" $GH_ANSWERS
  rbt questions --dir "$d/r"
  rb answer --dir "$d/r" pack.python-svc.python_version=3.13 --accept-defaults
  rb plan --dir "$d/r"
  calls
  rb apply --dir "$d/r"
  calls
  gitstate "$d/r"
  for f in pyproject.toml src/r/__init__.py .pre-commit-config.yaml .github/workflows/ci.yml \
           .github/pull_request_template.md .github/CODEOWNERS; do echo "--- $f"; cat "$d/r/$f"; done
  unset HARNESS_REPO_BOOTSTRAP_PACK_DIRS
}
case_gh_new_ruleset_403() {  # GitHub Free private repository: the ruleset is a warning
  local d=$1; sandbox "$d" "$GHURL"
  fixture <<'EOF'
{"gh": {"writes": {"POST repos/o/r/rulesets": {"rc": 1, "err": "gh: Upgrade to GitHub Pro or make this repository public to enable this feature. (HTTP 403)"}}}}
EOF
  rb answer --dir "$d/r" repo.host=github repo.owner=o repo.name=r architecture.kind=docs workflow.required_approvals=0 --accept-defaults
  rbt apply --dir "$d/r"
  calls
}
case_gh_exists_nonempty() {  # create refused: clone it instead
  local d=$1; sandbox "$d" "$GHURL"
  fixture <<EOF
{"gh": {"get": {"repos/o/r": $GH_REPO_JSON, "repos/o/r/branches?per_page=1": [{"name": "main"}]}}}
EOF
  rb answer --dir "$d/r" repo.host=github repo.owner=o repo.name=r architecture.kind=docs --accept-defaults
  rbt plan --dir "$d/r"
  rbt apply --dir "$d/r"
  calls
  ls -A "$d/r"
}
case_gh_push_refused() {  # the API says empty, the remote has a branch: nothing is pushed or configured
  local d=$1; sandbox "$d" "$GHURL"
  git init -q -b other "$d/x" && git -C "$d/x" commit -q --allow-empty -m x && git -C "$d/x" push -q "$d/origin.git" other
  fixture <<EOF
{"gh": {"get": {"repos/o/r": $GH_REPO_JSON, "repos/o/r/branches?per_page=1": []}}}
EOF
  rb answer --dir "$d/r" repo.host=github repo.owner=o repo.name=r architecture.kind=docs --accept-defaults
  rbt apply --dir "$d/r"
  calls
  gitstate "$d/r"
  echo "--- the human empties the remote; apply resumes after the initial commit"
  git --git-dir "$d/origin.git" update-ref -d refs/heads/other
  rbt apply --dir "$d/r"
  calls
  gitstate "$d/r"
}
case_gh_existing_drift() {  # retrofit: infer, check --fix, render refused on main, render on a branch
  local d=$1; sandbox "$d" "$GHURL"; seed "$d" "$GHURL"
  fixture <<EOF
{"gh": {"get": {"repos/o/r": $GH_REPO_JSON, "repos/o/r/branches?per_page=1": [{"name": "main"}],
  "repos/o/r/rules/branches/main": [], "repos/o/r/branches/main/protection": {"__status": 404}},
  "labels": ["bug", "agent-worked"]}}
EOF
  rb answer --dir "$d/r" --infer
  rb answer --dir "$d/r" architecture.kind=docs --accept-defaults
  rbt check --dir "$d/r" --fix
  rbt render --dir "$d/r"
  git -C "$d/r" switch -q -c repo-standard
  rbt render --dir "$d/r"
  rbt render --dir "$d/r" --force
  rb plan --dir "$d/r"
  calls
}
case_gl_new() {
  local d=$1; sandbox "$d" "$GLURL"
  # shellcheck disable=SC2086
  rb answer --dir "$d/r" $GL_ANSWERS --accept-defaults
  rbt plan --dir "$d/r"
  calls
  rb apply --dir "$d/r"
  calls
  gitstate "$d/r"
  for f in .gitlab-ci.yml .gitlab/merge_request_templates/Default.md README.md; do echo "--- $f"; cat "$d/r/$f"; done
}
case_gl_new_stack() {  # the stack bundle turns the remove-source-branch default off
  local d=$1; sandbox "$d" "$GLURL"; export HARNESS_BUNDLES=core,gitlab,stack
  # shellcheck disable=SC2086
  rb answer --dir "$d/r" $GL_ANSWERS workflow.required_approvals=0 --accept-defaults
  rbt plan --dir "$d/r"
  calls
  export HARNESS_BUNDLES=core
}
case_gl_existing_drift() {
  local d=$1; sandbox "$d" "$GLURL"; seed "$d" "$GLURL"
  export HARNESS_GITLAB_HOST=gitlab.example.com
  fixture <<EOF
{"glab": {"get": {"projects/grp%2Fr": $GL_PROJ_JSON,
  "projects/grp%2Fr/protected_branches/main": {"name": "main", "allow_force_push": false,
    "push_access_levels": [{"access_level": 40}], "merge_access_levels": [{"access_level": 40}]},
  "projects/grp%2Fr/labels?per_page=100": [{"name": "agent-worked"}, {"name": "agent-created"}]}}}
EOF
  rb answer --dir "$d/r" --infer
  rb answer --dir "$d/r" architecture.kind=library workflow.tracker=none --accept-defaults
  rbt check --dir "$d/r" --fix
  git -C "$d/r" switch -q -c repo-standard
  rbt apply --dir "$d/r"
  calls
  unset HARNESS_GITLAB_HOST
}
case_hardening() {  # review findings: path escapes, option-like answers, origin mismatch, keyword-prefixed variables
  local d=$1; sandbox "$d" "$GHURL"; export HARNESS_REPO_BOOTSTRAP_PACK_DIRS="$here/packs-hostile"
  rb answer --dir "$d/r" repo.host=local architecture.kind=docs --accept-defaults
  for t in ./.harness.toml ./.git/hooks/pre-commit .GIT/config a/../../escape ./.repo-standard.toml; do
    rb answer --dir "$d/r" "pack.evil.target=$t"
    rb render --dir "$d/r"
  done
  rb answer --dir "$d/r" pack.evil.target=ok.txt
  rb render --dir "$d/r"
  echo "--- ok.txt"; cat "$d/r/ok.txt"
  ls -A "$d/r"
  unset HARNESS_REPO_BOOTSTRAP_PACK_DIRS
  rb answer --dir "$d/r2" workflow.default_branch=--force
  rb answer --dir "$d/r2" repo.owner=../x
  rb answer --dir "$d/r2" repo.owner=-R
  rb answer --dir "$d/r2" repo.name=.git
  seed "$d" "$GHURL"
  rb answer --dir "$d/r" repo.host=github repo.owner=someone-else repo.name=r architecture.kind=docs --accept-defaults
  rbt plan --dir "$d/r"
  rbt check --dir "$d/r"
  calls
}
case_uncovered_and_errors() {  # no pack for go; bad answers are refused with the choices
  local d=$1; sandbox "$d" "$GHURL"
  rb answer --dir "$d/r" repo.host=bitbucket
  rb answer --dir "$d/r" no.such=1
  rb answer --dir "$d/r" workflow.required_approvals=two
  rb answer --dir "$d/r" repo.host=local architecture.kind=service architecture.languages=go,python
  rbt plan --dir "$d/r"
  rb answer --dir "$d/r" --accept-defaults
  rbt plan --dir "$d/r"
  export HARNESS_REPO_BOOTSTRAP_PACK_DIRS="$d/nope"
  rb questions --dir "$d/r"
  unset HARNESS_REPO_BOOTSTRAP_PACK_DIRS
  export HARNESS_REPO_BOOTSTRAP_DEFAULT_MERGE_METHOD=octopus
  rb questions --dir "$d/r"
  unset HARNESS_REPO_BOOTSTRAP_DEFAULT_MERGE_METHOD
}

norm() { sed -e "s#$1#SANDBOX#g" -e "s#$here#HERE#g" -e "s#$(dirname "$here")#SCRIPTS#g" -e 's#/tmp/repoboot-body-[A-Za-z0-9_]*\.json#BODYFILE#g'; }
run_case() {
  local name=$1 d="$tmp/$1"
  cases=$((cases + 1))
  ( "case_${name//-/_}" "$d" ) > "$tmp/$name.raw" 2>&1
  norm "$d" < "$tmp/$name.raw" > "$tmp/$name.txt"
  if [ "${UPDATE:-}" = 1 ]; then cp "$tmp/$name.txt" "$GOLD/$name.txt"; echo "UPDATED $name"; return; fi
  if [ ! -f "$GOLD/$name.txt" ]; then echo "FAIL $name (no golden — run UPDATE=1)"; fail=1; return; fi
  if diff -u "$GOLD/$name.txt" "$tmp/$name.txt" > "$tmp/$name.diff"; then echo "PASS $name"
  else echo "FAIL $name"; head -60 "$tmp/$name.diff"; fail=1; fi
}

for c in local-new gh-new gh-new-ruleset-403 gh-exists-nonempty gh-push-refused gh-existing-drift \
         gl-new gl-new-stack gl-existing-drift uncovered-and-errors hardening; do
  run_case "$c"
done

# ------------------------------------------------------------------------- invariants
ck() { local what=$1; shift; cases=$((cases + 1)); if "$@"; then echo "PASS $what"; else echo "FAIL $what"; fail=1; fi; }
ck "plan never writes (gh-new)" sh -c "sed -n '/repoboot plan/,/repoboot apply/p' '$tmp/gh-new.txt' | grep -vqE '^gh (repo create|label create|api -X)'"
ck "a blocked plan writes nothing" sh -c "! grep -qE '^gh (repo create|api -X|label create)' '$tmp/gh-exists-nonempty.txt'"
ck "a non-empty remote is never pushed to" sh -c "sed '/human empties/q' '$tmp/gh-push-refused.txt' > '$tmp/refused' && grep -q 'the remote is not empty' '$tmp/refused' && ! grep -qE '^gh api -X' '$tmp/refused'"
ck "repoboot never writes .harness.toml" sh -c "! find '$tmp' -name .harness.toml | grep -q ."
ck "repoboot never force-pushes" sh -c "! grep -qE 'push .*(--force|-f )' '$tmp'/*.txt"

[ "${KEEP:-}" = 1 ] && echo "sandboxes kept in $tmp" || rm -rf "$tmp"
[ "${UPDATE:-}" = 1 ] && { echo "goldens updated ($cases)"; exit 0; }
if [ $fail -eq 0 ]; then echo "all $cases repoboot tests passed"; else echo "repoboot tests FAILED"; fi
exit $fail
