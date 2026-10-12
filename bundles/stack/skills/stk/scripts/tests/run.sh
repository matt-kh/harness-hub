#!/usr/bin/env bash
# Golden tests for stk.py. glab and gh are stubbed (stub.py, fixture per scenario); git is REAL:
# every case builds a sandbox — a bare origin, a main checkout `r` on the ticket branch feat-x,
# one worktree per sub branch (`r_<sub>`) and a server-side clone `srv` that performs the
# merges — with deterministic authors and dates and GIT_CONFIG_GLOBAL=/dev/null. Each scenario
# runs plan, status, check and sync --json in a fresh sandbox; then the invariants.
# Goldens normalise the sandbox path (SANDBOX), this directory (HERE) and every sha ([sha]).
# UPDATE=1 rewrites golden/. KEEP=1 keeps the sandboxes. Exits non-zero on any failure.
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
CLI="$here/../stk.py"
GOLD="$here/golden"
export GLAB="$here/glab-stub.sh" GH="$here/gh-stub.sh" GIT="$here/git-wrap.sh"
export HARNESS_CONFIG_JSON=/dev/null   # hermetic: never read a real build/config.json
unset HARNESS_STACK_LABEL HARNESS_STACK_PUSH HARNESS_STACK_UPDATE_METHOD HARNESS_STACK_LEAF_REFRESH \
      HARNESS_GITLAB_HOSTS_RE HARNESS_GITLAB_HOST WORK_TICKET_AGENT_LABEL_RE WORK_TICKET_LABEL \
      GH_REPO GITLAB_HOST GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_EDITOR GIT_SEQUENCE_EDITOR
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 GIT_TERMINAL_PROMPT=0 \
       GIT_AUTHOR_NAME=Dev GIT_AUTHOR_EMAIL=dev@example.com GIT_COMMITTER_NAME=Dev \
       GIT_COMMITTER_EMAIL=dev@example.com GIT_AUTHOR_DATE='2026-01-01T00:00:00Z' \
       GIT_COMMITTER_DATE='2026-01-01T00:00:00Z'
tmp=$(mktemp -d); tmp=$(cd "$tmp" && pwd -P)
fail=0; cases=0
mkdir -p "$GOLD"

# ------------------------------------------------------------------------- sandbox kit
q() { "$@" > /dev/null 2>&1 || { echo "setup failed: $*" >&2; return 1; }; }
commit() {  # commit DIR FILE CONTENT [MESSAGE]
  printf '%s\n' "$3" > "$1/$2" && q git -C "$1" add "$2" && q git -C "$1" commit -m "${4:-$2}"
}
sandbox() {  # sandbox D REMOTE-URL: origin, main checkout r on feat-x (pushed), srv clone
  local d=$1 url=$2
  q git init --bare -b main "$d/origin.git" || return 1
  q git init -b main "$d/r" || return 1
  q git -C "$d/r" config remote.origin.url "$url"
  q git -C "$d/r" config remote.origin.fetch '+refs/heads/*:refs/remotes/origin/*'
  q git -C "$d/r" config "url.$d/origin.git.insteadOf" "$url"
  commit "$d/r" README.md "base" "initial commit" || return 1
  q git -C "$d/r" push origin main
  q git -C "$d/r" switch -c feat-x
  q git -C "$d/r" commit --allow-empty -m "stack root: feat-x"
  q git -C "$d/r" push -u origin feat-x
  q git clone "$d/origin.git" "$d/srv"
}
part() {  # part D BRANCH PARENT FILE CONTENT: a sub branch in its own worktree, pushed
  local d=$1
  q git -C "$d/r" worktree add -b "$2" "$d/r_$2" "$3" || return 1
  commit "$d/r_$2" "$4" "$5" "$2: $4" || return 1
  q git -C "$d/r_$2" push -u origin "$2"
}
head_of() { git --git-dir "$1/origin.git" rev-parse "refs/heads/$2"; }
srv() {  # srv D squash|merge|ff BRANCH INTO [delete]: the server merges BRANCH into INTO
  local d=$1 how=$2 br=$3 into=$4
  q git -C "$d/srv" fetch origin || return 1
  q git -C "$d/srv" switch -C "$into" "origin/$into" || return 1
  case "$how" in
    squash) q git -C "$d/srv" merge --squash "origin/$br" && q git -C "$d/srv" commit -m "$br (squashed)" ;;
    merge)  q git -C "$d/srv" merge --no-ff -m "Merge branch '$br'" "origin/$br" ;;
    ff)     q git -C "$d/srv" merge --ff-only "origin/$br" ;;
  esac || return 1
  q git -C "$d/srv" push origin "$into" || return 1
  if [ "${5:-}" = delete ]; then q git -C "$d/srv" push origin --delete "$br"; fi
}
fetched() { q git -C "$1/r" fetch --prune origin; }   # the developer's last fetch
fixture() { cat > "$1/fixture.json"; }

A=feat-x-sub-01-api; B=feat-x-sub-02-ui; C=feat-x-sub-03-docs; L3=feat-x-sub-03-cli
glr() {  # glr IID SOURCE TARGET [extra json]: one GitLab MR fixture entry
  printf '"%s": {"title": "PROJ-123 %s", "source_branch": "%s", "target_branch": "%s"%s}' "$1" "$2" "$2" "$3" "${4:+, $4}"
}
ghr() {  # ghr NUMBER HEAD BASE [extra json]: one GitHub PR fixture entry
  printf '"%s": {"title": "PROJ-123 %s", "headRefName": "%s", "baseRefName": "%s"%s}' "$1" "$2" "$2" "$3" "${4:+, $4}"
}
main10() { printf '"10": {"title": "PROJ-123 feature x", "%s": true, "%s": "feat-x", "%s": "main"%s}' "$@"; }
glmain() { main10 draft source_branch target_branch ""; }
ghmain() { main10 isDraft headRefName baseRefName "${1:+, $1}"; }

chain3() {  # chain3 D URL: A <- B <- C, each in its own worktree
  sandbox "$1" "$2" && part "$1" "$A" feat-x api.txt "api v1" && part "$1" "$B" "$A" ui.txt "ui v1" \
    && part "$1" "$C" "$B" docs.txt "docs v1"
}
leaves3() {  # leaves3 D URL: A, B and L3 all off feat-x (fan-in)
  sandbox "$1" "$2" && part "$1" "$A" feat-x api.txt "api v1" && part "$1" "$B" feat-x ui.txt "ui v1" \
    && part "$1" "$L3" feat-x cli.txt "cli v1"
}
GLURL=git@gitlab.example.com:o/r.git
GHURL=git@github.com:o/r.git

# ------------------------------------------------------------------- GitLab scenarios
squash_chain() {  # A squash-merged into feat-x (branch kept); B still targets A
  local d=$1
  chain3 "$d" "$GLURL" || return 1
  local s; s=$(head_of "$d" "$A"); srv "$d" squash "$A" feat-x && fetched "$d" || return 1
  fixture "$d" <<EOF
{"mrs": {$(glmain), $(glr 11 "$A" feat-x "\"state\": \"merged\", \"sha\": \"$s\""),
 $(glr 12 "$B" "$A" "${2:-}"), $(glr 13 "$C" "$B")}}
EOF
}
setup_gl_chain_bottom_merged_squash() { squash_chain "$1"; }
setup_gl_chain_bottom_merged_merge() {
  local d=$1
  chain3 "$d" "$GLURL" || return 1
  local s; s=$(head_of "$d" "$A"); srv "$d" merge "$A" feat-x && fetched "$d" || return 1
  fixture "$d" <<EOF
{"project": {"merge_method": "merge", "squash_option": "default_off"},
 "mrs": {$(glmain), $(glr 11 "$A" feat-x "\"state\": \"merged\", \"sha\": \"$s\", \"squash\": false"),
 $(glr 12 "$B" "$A"), $(glr 13 "$C" "$B")}}
EOF
}
setup_gl_chain_base_moved() {  # chain A <- B; leaf L3 squash-merged: feat-x advanced
  local d=$1
  sandbox "$d" "$GLURL" && part "$d" "$A" feat-x api.txt "api v1" && part "$d" "$B" "$A" ui.txt "ui v1" \
    && part "$d" "$L3" feat-x cli.txt "cli v1" || return 1
  local s; s=$(head_of "$d" "$L3"); srv "$d" squash "$L3" feat-x && fetched "$d" || return 1
  fixture "$d" <<EOF
{"mrs": {$(glmain), $(glr 11 "$A" feat-x), $(glr 12 "$B" "$A"),
 $(glr 13 "$L3" feat-x "\"state\": \"merged\", \"sha\": \"$s\"")}}
EOF
}
amended_chain() {  # A amended in its worktree and lease-pushed; B and C still sit on the old A
  local d=$1 content=${2:-api v2}
  chain3 "$d" "$GLURL" || return 1
  printf '%s\n' "$content" > "$d/r_$A/api.txt"
  q git -C "$d/r_$A" commit -a --amend -m "$A: api.txt (amended)" && q git -C "$d/r_$A" push --force-with-lease origin "$A" \
    && fetched "$d" || return 1
  fixture "$d" <<EOF
{"mrs": {$(glmain), $(glr 11 "$A" feat-x), $(glr 12 "$B" "$A"), $(glr 13 "$C" "$B")}}
EOF
}
setup_gl_chain_amend() { amended_chain "$1"; }
setup_gl_chain_conflict() {  # B edits A's file; A is then amended on the same line
  local d=$1
  sandbox "$d" "$GLURL" && part "$d" "$A" feat-x api.txt "api v1" || return 1
  q git -C "$d/r" worktree add -b "$B" "$d/r_$B" "$A" && commit "$d/r_$B" api.txt "api v1 + ui hook" "$B: api.txt" \
    && q git -C "$d/r_$B" push -u origin "$B" || return 1
  printf 'api v2\n' > "$d/r_$A/api.txt"
  q git -C "$d/r_$A" commit -a --amend -m "$A: api.txt (amended)" && q git -C "$d/r_$A" push --force-with-lease origin "$A" \
    && fetched "$d" || return 1
  fixture "$d" <<EOF
{"mrs": {$(glmain), $(glr 11 "$A" feat-x), $(glr 12 "$B" "$A")}}
EOF
}
setup_gl_dirty_worktree() { amended_chain "$1" && printf 'scratch\n' > "$1/r_$C/notes.tmp"; }
setup_gl_branch_checked_out_elsewhere() {  # chain A <- B <- C, feat-x advanced: A and B are detached and re-attached
  local d=$1
  chain3 "$d" "$GLURL" || return 1
  q git -C "$d/srv" fetch origin && q git -C "$d/srv" switch -C feat-x origin/feat-x \
    && commit "$d/srv" hotfix.txt "fix" "hotfix on feat-x" && q git -C "$d/srv" push origin feat-x && fetched "$d" || return 1
  fixture "$d" <<EOF
{"mrs": {$(glmain), $(glr 11 "$A" feat-x), $(glr 12 "$B" "$A"), $(glr 13 "$C" "$B")}}
EOF
}
setup_gl_branch_checked_out_elsewhere_dirty() {  # same, but A's worktree has a local edit
  setup_gl_branch_checked_out_elsewhere "$1" && printf 'wip\n' >> "$1/r_$A/api.txt"
}
setup_gl_no_worktree() { squash_chain "$1" && q git -C "$1/r" worktree remove "$1/r_$C"; }
setup_gl_misfire() {  # A squash-merged and its branch deleted: GitLab CE retargeted B to main
  local d=$1
  sandbox "$d" "$GLURL" && part "$d" "$A" feat-x api.txt "api v1" && part "$d" "$B" "$A" ui.txt "ui v1" || return 1
  local s; s=$(head_of "$d" "$A"); srv "$d" squash "$A" feat-x delete && fetched "$d" || return 1
  fixture "$d" <<EOF
{"mrs": {$(glmain), $(glr 11 "$A" feat-x "\"state\": \"merged\", \"sha\": \"$s\""), $(glr 12 "$B" main)}}
EOF
}
fanin_behind() {  # fan-in A, B, L3; A merged (how=$2): B and L3 are behind feat-x
  local d=$1 how=$2 method=$3
  leaves3 "$d" "$GLURL" || return 1
  local s; s=$(head_of "$d" "$A"); srv "$d" "$how" "$A" feat-x && fetched "$d" || return 1
  fixture "$d" <<EOF
{"project": {"merge_method": "$method", "squash_option": "default_off"},
 "mrs": {$(glmain), $(glr 11 "$A" feat-x "\"state\": \"merged\", \"sha\": \"$s\""), $(glr 12 "$B" feat-x), $(glr 13 "$L3" feat-x)}}
EOF
}
setup_gl_fanin_leaf_behind_merge() { fanin_behind "$1" merge merge; }
setup_gl_fanin_leaf_behind_ff() {
  local d=$1
  leaves3 "$d" "$GLURL" || return 1
  local s; s=$(head_of "$d" "$A"); srv "$d" ff "$A" feat-x && fetched "$d" || return 1
  fixture "$d" <<EOF
{"project": {"merge_method": "ff", "squash_option": "default_off"},
 "mrs": {$(glmain), $(glr 11 "$A" feat-x "\"state\": \"merged\", \"sha\": \"$s\""), $(glr 12 "$B" feat-x), $(glr 13 "$L3" feat-x)}}
EOF
}
setup_gl_leaf_conflict() {  # fan-in A and B both edit shared.txt; A merged: B conflicts
  local d=$1
  sandbox "$d" "$GLURL" && part "$d" "$A" feat-x shared.txt "from api" && part "$d" "$B" feat-x shared.txt "from ui" || return 1
  local s; s=$(head_of "$d" "$A"); srv "$d" squash "$A" feat-x && fetched "$d" || return 1
  fixture "$d" <<EOF
{"mrs": {$(glmain), $(glr 11 "$A" feat-x "\"state\": \"merged\", \"sha\": \"$s\""),
 $(glr 12 "$B" feat-x "\"has_conflicts\": true, \"detailed_merge_status\": \"conflict\"")}}
EOF
}
setup_gl_all_merged_undraft() {
  local d=$1
  sandbox "$d" "$GLURL" && part "$d" "$A" feat-x api.txt "api v1" && part "$d" "$B" feat-x ui.txt "ui v1" || return 1
  local sa sb; sa=$(head_of "$d" "$A"); sb=$(head_of "$d" "$B")
  srv "$d" squash "$A" feat-x && srv "$d" squash "$B" feat-x && fetched "$d" || return 1
  fixture "$d" <<EOF
{"mrs": {$(glmain), $(glr 11 "$A" feat-x "\"state\": \"merged\", \"sha\": \"$sa\""),
 $(glr 12 "$B" feat-x "\"state\": \"merged\", \"sha\": \"$sb\"")}}
EOF
}
setup_gl_unlabelled() { squash_chain "$1" '"labels": []'; }
setup_gl_no_push() { squash_chain "$1"; }

# ------------------------------------------------------------------- GitHub scenarios
gh_squash_chain() {  # gh_squash_chain D BASE-OF-B delete|keep [extra json for B] [repo json]
  local d=$1
  sandbox "$d" "$GHURL" && part "$d" "$A" feat-x api.txt "api v1" && part "$d" "$B" "$A" ui.txt "ui v1" \
    && part "$d" "$C" "$B" docs.txt "docs v1" || return 1
  local s; s=$(head_of "$d" "$A"); srv "$d" squash "$A" feat-x "$3" && fetched "$d" || return 1
  fixture "$d" <<EOF
{${5:-}"prs": {$(ghmain), $(ghr 11 "$A" feat-x "\"state\": \"MERGED\", \"headRefOid\": \"$s\""),
 $(ghr 12 "$B" "$2" "${4:-}"), $(ghr 13 "$C" "$B")}}
EOF
}
setup_gh_chain_retargeted_by_github() { gh_squash_chain "$1" feat-x delete; }
setup_gh_chain_squash() { gh_squash_chain "$1" "$A" keep "" '"repo": {"deleteBranchOnMerge": false}, '; }
setup_gh_unlabelled() { gh_squash_chain "$1" "$A" keep '"labels": []' '"repo": {"deleteBranchOnMerge": false}, '; }
setup_gh_leaf_behind() {  # strict ruleset on feat-x; A squash-merged: B and L3 are behind
  local d=$1
  leaves3 "$d" "$GHURL" || return 1
  local s; s=$(head_of "$d" "$A"); srv "$d" squash "$A" feat-x delete && fetched "$d" || return 1
  fixture "$d" <<EOF
{"rules": {"feat-x": [{"type": "required_status_checks", "parameters": {"strict_required_status_checks_policy": true}}]},
 "prs": {$(ghmain), $(ghr 11 "$A" feat-x "\"state\": \"MERGED\", \"headRefOid\": \"$s\""),
 $(ghr 12 "$B" feat-x "\"mergeStateStatus\": \"BEHIND\""), $(ghr 13 "$L3" feat-x "\"mergeStateStatus\": \"BEHIND\"")}}
EOF
}
setup_gh_fork() {  # a fork PR on a sub branch name is listed, never stacked
  local d=$1
  sandbox "$d" "$GHURL" && part "$d" "$A" feat-x api.txt "api v1" && part "$d" "$B" feat-x ui.txt "ui v1" || return 1
  fetched "$d"
  fixture "$d" <<EOF
{"prs": {$(ghmain "\"labels\": [\"agent-worked\", \"stack\"]"), $(ghr 11 "$A" feat-x "\"labels\": [\"agent-worked\", \"stack\"]"),
 $(ghr 12 "$B" feat-x "\"isCrossRepository\": true, \"labels\": [\"stack\"]")}}
EOF
}
setup_gh_draft_main() {
  local d=$1
  sandbox "$d" "$GHURL" && part "$d" "$A" feat-x api.txt "api v1" || return 1
  local s; s=$(head_of "$d" "$A"); srv "$d" squash "$A" feat-x delete && fetched "$d" || return 1
  fixture "$d" <<EOF
{"prs": {$(ghmain), $(ghr 11 "$A" feat-x "\"state\": \"MERGED\", \"headRefOid\": \"$s\"")}}
EOF
}

# ------------------------------------------------------------------------- the harness
snap_wt() {  # every worktree: path, HEAD (branch or detached sha) and porcelain status
  local wt
  git -C "$1/r" worktree list --porcelain | sed -n 's/^worktree //p' | while IFS= read -r wt; do
    printf '== %s %s\n' "$wt" "$(git -C "$wt" symbolic-ref -q HEAD || git -C "$wt" rev-parse HEAD)"
    git -C "$wt" status --porcelain
  done
}
snap_refs() { git -C "$1/r" for-each-ref --format='%(refname) %(objectname)' refs/heads; }
snap_origin() { git --git-dir "$1/origin.git" for-each-ref --format='%(refname:short) %(objectname)' refs/heads; }

norm() {  # norm FILE D: sandbox path, this directory and shas never reach a golden
  python3 - "$1" "$2" "$here" <<'PY'
import re, sys
p, d, here = sys.argv[1:4]
t = open(p).read().replace(d, "SANDBOX").replace(here, "HERE")
t = re.sub(r"\b[0-9a-f]{40}\b", "[sha]", t)
t = re.sub(r"\b(?=[0-9a-f]*[0-9])[0-9a-f]{7,12}\b", "[sha]", t)
open(p, "w").write(t)
PY
}

record() {  # record NAME FILE
  local name=$1 g=$2
  cases=$((cases + 1))
  if [ "${UPDATE:-0}" = 1 ]; then cp "$g" "$GOLD/$name.txt"; echo "UPDATED $name"; return; fi
  if [ ! -f "$GOLD/$name.txt" ]; then echo "FAIL $name (no golden — run UPDATE=1)"; fail=1; return; fi
  if diff -u "$GOLD/$name.txt" "$g" > "$tmp/$name.diff"; then echo "PASS $name"
  else echo "FAIL $name"; head -40 "$tmp/$name.diff"; fail=1; fi
}

t() {  # t NAME SETUP EXPECTED-EXIT ARGS...   (env assignments go before t)
  local name=$1 setup=$2 exp=$3 d rc g; shift 3
  d="$tmp/sb/$name"; mkdir -p "$d"
  if ! "setup_$(printf '%s' "$setup" | tr '-' '_')" "$d" > "$d/setup.log" 2>&1; then
    echo "FAIL $name: sandbox setup"; cat "$d/setup.log"; fail=1; cases=$((cases + 1)); return
  fi
  snap_wt "$d" > "$d/wt.before"; snap_refs "$d" > "$d/refs.before"; snap_origin "$d" > "$d/origin.before"
  (cd "$d/r" && STK_SCENARIO=$setup STK_FIXTURE="$d/fixture.json" STK_ORIGIN="$d/origin.git" \
     STUB_LOG="$d/calls.log" python3 "$CLI" "$@") > "$d/out" 2> "$d/err"; rc=$?
  snap_wt "$d" > "$d/wt.after"; snap_refs "$d" > "$d/refs.after"; snap_origin "$d" > "$d/origin.after"
  : >> "$d/calls.log"; cp "$d/calls.log" "$tmp/$name.log"; cp "$d/out" "$tmp/$name.out"
  [ "$rc" = "$exp" ] || { echo "FAIL $name: exit $rc, expected $exp"; cat "$d/err"; fail=1; }
  g="$tmp/$name.txt"
  {
    echo "# exit=$rc"; echo "# stderr:"; cat "$d/err"; echo "# stdout:"; cat "$d/out"
    echo "# worktrees: $(cmp -s "$d/wt.before" "$d/wt.after" && echo unchanged || echo changed)"
    echo "# origin branches:"
    python3 - "$d/origin.before" "$d/origin.after" <<'PY'
import sys
def load(p):
    return dict(l.split() for l in open(p) if l.strip())
b, a = load(sys.argv[1]), load(sys.argv[2])
for k in sorted(set(b) | set(a)):
    print("  %s %s" % (k, "pushed" if b.get(k) != a.get(k) else "unchanged"))
PY
  } > "$g"
  norm "$g" "$d"
  record "$name" "$g"
  for f in wt.before wt.after refs.before refs.after; do cp "$d/$f" "$tmp/$name.$f"; done
}

scen() {  # scen SCENARIO "<plan status check sync exits>" SELECTION...
  local s=$1 e_plan e_status e_check e_sync
  read -r e_plan e_status e_check e_sync <<<"$2"
  shift 2
  t "$s.plan"   "$s" "$e_plan"   plan   "$@" --json
  t "$s.status" "$s" "$e_status" status "$@" --json
  t "$s.check"  "$s" "$e_check"  check  "$@" --json
  t "$s.sync"   "$s" "$e_sync"   sync   "$@" --json
}

#    scenario                           plan status check sync   selection
scen gl-chain-bottom-merged-squash      "0 1 0 0"   --stack feat-x
scen gl-chain-bottom-merged-merge       "0 1 0 0"   --stack feat-x
scen gl-chain-base-moved                "0 1 0 0"   --stack feat-x
scen gl-chain-amend                     "0 0 0 0"   --stack feat-x
scen gl-chain-conflict                  "0 0 0 1"   --stack feat-x
scen gl-dirty-worktree                  "1 0 0 1"   --stack feat-x
scen gl-branch-checked-out-elsewhere    "0 0 0 0"   --stack feat-x
t gl-branch-checked-out-elsewhere.sync-lower-dirty gl-branch-checked-out-elsewhere-dirty 1 sync --stack feat-x --json
scen gl-no-worktree                     "1 1 0 1"   --stack feat-x
scen gl-misfire                         "0 1 0 0"   --stack feat-x
scen gl-fanin-leaf-behind-merge         "0 1 0 0"   --stack feat-x
scen gl-fanin-leaf-behind-ff            "1 1 0 1"   --stack feat-x
t gl-fanin-leaf-behind-ff.sync-skip-ci gl-fanin-leaf-behind-ff 1 sync --stack feat-x --skip-ci --json
HARNESS_STACK_LEAF_REFRESH=never t gl-fanin-leaf-behind-ff.sync-never gl-fanin-leaf-behind-ff 1 sync --stack feat-x --json
scen gl-leaf-conflict                   "1 1 0 1"   --stack feat-x
scen gl-all-merged-undraft              "0 1 0 0"   --stack feat-x --with-main
scen gl-unlabelled                      "1 1 0 1"   --stack feat-x
t gl-unlabelled.sync-include-human gl-unlabelled 0 sync --stack feat-x --include-human --json
scen gl-no-push                         "1 1 0 1"   --stack feat-x --no-push
HARNESS_STACK_PUSH=false t gl-no-push.sync-config gl-no-push 1 sync --stack feat-x --json
t gl-chain-bottom-merged-squash.sync-ref gl-chain-bottom-merged-squash 0 sync 12 --json
t gl-chain-bottom-merged-squash.plan-text gl-chain-bottom-merged-squash 0 plan --stack feat-x --text
t gl-fanin-leaf-behind-ff.check-fix gl-fanin-leaf-behind-ff 0 check --fix --stack feat-x --json

scen gh-chain-retargeted-by-github      "0 1 0 0"   --stack feat-x
scen gh-chain-squash                    "0 1 0 0"   --stack feat-x
scen gh-leaf-behind                     "1 1 0 1"   --stack feat-x
HARNESS_STACK_UPDATE_METHOD=merge t gh-leaf-behind.sync-merge gh-leaf-behind 1 sync --stack feat-x --json
scen gh-fork                            "1 0 0 1"   --label stack
scen gh-unlabelled                      "1 1 0 1"   --stack feat-x
t gh-unlabelled.sync-include-human gh-unlabelled 0 sync --stack feat-x --include-human --json
scen gh-draft-main                      "0 1 0 0"   --stack feat-x
t gh-chain-squash.check-fix gh-chain-squash 0 check --fix --stack feat-x --json

# ------------------------------------------------------------------------- invariants
chk() {  # chk <condition-exit> <label>
  cases=$((cases + 1))
  if [ "$1" = 0 ]; then echo "PASS $2"; else echo "FAIL $2"; fail=1; fi
}
ck() { local l=$1; shift; "$@"; chk $? "$l"; }   # ck <label> <test...>
same() { cmp -s "$tmp/$1.wt.before" "$tmp/$1.wt.after" && cmp -s "$tmp/$1.refs.before" "$tmp/$1.refs.after"; }
cat "$tmp"/*.log > "$tmp/all.calls" 2>/dev/null
WRITE_RE='^(glab mr (rebase|update)|gh pr (update-branch|edit|ready)|glab api -X|gh api -X|git .*(push|rebase|switch|fetch|reset|branch|worktree (add|remove)))( |$)'

bad=$(grep -E '^git .* push( |$)' "$tmp/all.calls" | grep -E -- ' (--force|-f|--force=[^ ]*)( |$)| \+' | head -3)
ck "no --force, -f or +ref push ever" [ -z "$bad" ]
bad=$(grep -E '^git .* push( |$)' "$tmp/all.calls" | grep -v -- ' push --force-with-lease origin ' | head -3)
ck "every push is git push --force-with-lease origin …" [ -z "$bad" ]
bad=$(grep -E '^git .* push --force-with-lease origin ' "$tmp/all.calls" | sed 's/.* origin //' | tr ' ' '\n' | grep -vE -- '-sub-[0-9]+-' | head -3)
ck "every pushed ref is a -sub-NN- branch" [ -z "$bad" ]
ck "the suite pushed at least one cascade" grep -qE '^git .* push --force-with-lease origin ' "$tmp/all.calls"
ck "never reset --hard or rebase --continue" [ -z "$(grep -E 'reset --hard|rebase --continue' "$tmp/all.calls")" ]
bad=""
for f in "$tmp"/*.plan*.log "$tmp"/*.status.log "$tmp"/*.check*.log; do
  [ -f "$f" ] || continue
  grep -qE "$WRITE_RE" "$f" && bad="$bad $(basename "$f")"
done
ck "plan, status and check issue reads only (no server write, no fetch, push, rebase or switch)" [ -z "$bad" ]
bad=""
for f in "$tmp"/*.sync*.log; do
  n=$(grep -cE '^(glab mr rebase|gh pr update-branch) ' "$f")
  [ "$n" -le 1 ] || bad="$bad $(basename "$f")"
done
ck "at most one leaf refresh per invocation" [ -z "$bad" ]
ck "the suite refreshed a leaf" grep -q '^glab mr rebase 12$' "$tmp/gl-fanin-leaf-behind-ff.sync.log"
for c in gl-unlabelled.sync gh-unlabelled.sync; do
  bad=$(grep -E "$WRITE_RE" "$tmp/$c.log" | grep -vE '^git -C [^ ]+ fetch origin$')
  ck "$c: nothing written for an unlabelled part (no retarget, rebase or push)" [ -z "$bad" ]
done
ck "include-human pushes the unlabelled part" grep -q "push --force-with-lease origin $B $C" "$tmp/gl-unlabelled.sync-include-human.log"
for c in gl-chain-conflict.sync gl-dirty-worktree.sync gl-branch-checked-out-elsewhere.sync-lower-dirty gl-unlabelled.sync gl-no-worktree.sync; do
  ck "$c: every worktree and local branch exactly as found" same "$c"
done
ck "a conflicting cascade runs rebase --abort" grep -qE '^git -C [^ ]+ rebase --abort$' "$tmp/gl-chain-conflict.sync.log"
ck "a conflicting cascade pushes nothing" [ -z "$(grep -E ' push ' "$tmp/gl-chain-conflict.sync.log")" ]
ck "lower chain branches checked out elsewhere are detached, then re-attached" \
  grep -qE "^git -C [^ ]+r_$A switch $A\$" "$tmp/gl-branch-checked-out-elsewhere.sync.log"
ck "after the cascade every worktree is back on its branch" cmp -s "$tmp/gl-branch-checked-out-elsewhere.sync.wt.before" \
  "$tmp/gl-branch-checked-out-elsewhere.sync.wt.after"
ck "the cascade moved every chain branch" [ -z "$(grep -Fx -f "$tmp/gl-branch-checked-out-elsewhere.sync.refs.before" \
  "$tmp/gl-branch-checked-out-elsewhere.sync.refs.after" | grep -- '-sub-')" ]
ck "rebase runs with --update-refs --onto" grep -qE "^git -C [^ ]+r_$C rebase --update-refs --onto origin/feat-x [0-9a-f]{40} $C\$" \
  "$tmp/gl-chain-bottom-merged-squash.sync.log"
ck "squash: retarget the dependent to the ticket branch" grep -q "^glab mr update 12 --target-branch feat-x$" "$tmp/gl-chain-bottom-merged-squash.sync.log"
ck "merge method merge: retarget only, no cascade" [ -z "$(grep -E ' (rebase|push) ' "$tmp/gl-chain-bottom-merged-merge.sync.log")" ]
ck "misfire: the part aimed at main is retargeted" grep -q "^glab mr update 12 --target-branch feat-x$" "$tmp/gl-misfire.sync.log"
ck "leaf behind under merge: no refresh" [ -z "$(grep -E '^glab mr rebase' "$tmp/gl-fanin-leaf-behind-merge.sync.log")" ]
ck "--skip-ci reaches glab mr rebase" grep -q '^glab mr rebase 12 --skip-ci$' "$tmp/gl-fanin-leaf-behind-ff.sync-skip-ci.log"
ck "leaf_refresh = never refreshes nothing" [ -z "$(grep -E '^glab mr rebase' "$tmp/gl-fanin-leaf-behind-ff.sync-never.log")" ]
ck "leaf conflict: hint to chain the parts" grep -q 'share files: chain them' "$tmp/gl-leaf-conflict.sync.out"
ck "all merged: the main MR is marked ready" grep -q '^glab mr update 10 --ready$' "$tmp/gl-all-merged-undraft.sync.log"
ck "--no-push rebases but never pushes" [ -z "$(grep -E ' push ' "$tmp/gl-no-push.sync.log" "$tmp/gl-no-push.sync-config.log")" ]
ck "--no-push prints the lease push" grep -q 'push --force-with-lease origin' "$tmp/gl-no-push.sync.out"
ck "no worktree: the commands include git worktree add" grep -q 'git worktree add' "$tmp/gl-no-worktree.sync.out"
ck "GitHub: no retarget when GitHub already did it" [ -z "$(grep -E '^gh pr edit' "$tmp/gh-chain-retargeted-by-github.sync.log")" ]
ck "GitHub: retarget when the head branch was kept" grep -q '^gh pr edit 12 -R o/r -B feat-x$' "$tmp/gh-chain-squash.sync.log"
ck "GitHub: leaf refresh with --rebase" grep -q '^gh pr update-branch 12 -R o/r --rebase$' "$tmp/gh-leaf-behind.sync.log"
ck "GitHub: update_method = merge drops --rebase" grep -q '^gh pr update-branch 12 -R o/r$' "$tmp/gh-leaf-behind.sync-merge.log"
ck "GitHub: all merged marks the main PR ready" grep -q '^gh pr ready 10 -R o/r$' "$tmp/gh-draft-main.sync.log"
ck "GitHub: a fork PR is reported, never touched" [ -z "$(grep -E '^gh pr (edit|ready|update-branch) 12' "$tmp/gh-fork.sync.log")" ]
bad=$(grep '^gh pr ' "$tmp/all.calls" | grep -v -- ' -R o/r' | head -3)
ck "every gh pr call carries -R" [ -z "$bad" ]
bad=$(grep -E '^gh (repo view|api) ' "$tmp/all.calls" | grep -vE ' (repos/)?o/r( |/|$)' | head -3)
ck "every gh repo/api call names the repository" [ -z "$bad" ]
for b in "$B" "$C"; do
  n=$(git --git-dir "$tmp/sb/gl-chain-bottom-merged-squash.sync/origin.git" rev-list --count "feat-x..$b")
  ck "squash cascade: origin $b carries only its own commits on top of feat-x ($n)" [ "$n" = "$( [ "$b" = "$B" ] && echo 1 || echo 2)" ]
done

# ------------------------------------------------------------ harness parameters
p() {  # p NAME SETUP ARGS... -> runs stk in a fresh sandbox, output in $tmp/NAME.{out,err}, rc in $prc
  local name=$1 setup=$2 d; shift 2
  d="$tmp/sb/$name"; mkdir -p "$d"
  "setup_$(printf '%s' "$setup" | tr '-' '_')" "$d" > "$d/setup.log" 2>&1
  (cd "$d/r" && STK_SCENARIO=$setup STK_FIXTURE="$d/fixture.json" STK_ORIGIN="$d/origin.git" \
     STUB_LOG="$d/calls.log" python3 "$CLI" "$@") > "$tmp/$name.out" 2> "$tmp/$name.err"; prc=$?
}
printf '{"stack":{"label":"from-config"}}' > "$tmp/cfg.json"
HARNESS_CONFIG_JSON="$tmp/cfg.json" p p-cfg gh-fork plan --json
grep -q '"label": "from-config"' "$tmp/p-cfg.out"; chk $? "stack.label from the harness config selects the label"
HARNESS_CONFIG_JSON="$tmp/cfg.json" HARNESS_STACK_LABEL=stack p p-env gh-fork plan --json
grep -q '"label": "stack"' "$tmp/p-env.out"; chk $? "HARNESS_STACK_LABEL in the environment wins over the config"
HARNESS_STACK_LEAF_REFRESH=sometimes p p-bad gl-misfire plan --json
[ "$prc" = 1 ] && grep -q 'use one of: auto, never' "$tmp/p-bad.err"; chk $? "an invalid stack.leaf_refresh names the choices"
HARNESS_STACK_PUSH=maybe p p-badb gl-misfire plan --json
[ "$prc" = 1 ] && grep -q 'not a boolean' "$tmp/p-badb.err"; chk $? "an invalid stack.push says it is not a boolean"
HARNESS_GITLAB_HOSTS_RE='^nomatch$' p p-host gl-misfire plan --stack feat-x --json
grep -q '"provider": "gitlab"' "$tmp/p-host.out"; chk $? "a gitlab.* host is GitLab without a hosts regex match"
p p-refs-both gl-misfire plan 12 --stack feat-x
[ "$prc" = 1 ] && grep -q 'not several' "$tmp/p-refs-both.err"; chk $? "refs and --stack together exit 1"
p p-main gl-misfire plan --with-main
[ "$prc" = 1 ] && grep -q 'needs --stack' "$tmp/p-main.err"; chk $? "--with-main without --stack exits 1"

python3 "$CLI" > "$tmp/usage.out" 2>&1; rc=$?
[ "$rc" = 1 ] && grep -q "Deliberately NOT implemented" "$tmp/usage.out"; chk $? "bare stk prints usage, exit 1"
python3 "$CLI" --help > "$tmp/help.out" 2>&1; rc=$?
[ "$rc" = 0 ] && grep -q "Exit codes" "$tmp/help.out"; chk $? "stk --help exits 0"
python3 "$CLI" run --stack feat-x > "$tmp/run.out" 2>&1; rc=$?
[ "$rc" = 1 ] && grep -q "Unknown verb 'run'" "$tmp/run.out"; chk $? "there is no run verb (exit 1)"
python3 "$CLI" sync -h > "$tmp/h.out" 2>&1; rc=$?
[ "$rc" = 0 ] && grep -q -- "--no-push" "$tmp/h.out"; chk $? "stk sync -h works"

if [ "${KEEP:-0}" = 1 ]; then echo "artifacts in $tmp"; else rm -rf "$tmp"; fi
if [ $fail -eq 0 ]; then echo "all stk tests passed ($cases cases)"; else echo "stk tests FAILED"; fi
exit $fail
