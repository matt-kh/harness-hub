# shellcheck shell=bash
# Guard test rows for bundle gitlab. Sourced by bundles/core/guard/tests/run.sh after lib.sh
# (helpers: t EXPECTED 'cmd' | tc EXPECTED CWD 'cmd' | tr 'reason-re' 'cmd' | g EXPECTED 'cmd' in a real dir).

# closing keywords + Jira key (40-gitlab-closing)
t deny  'git commit -m "Closes LBL-1 parser"'
t deny  'git commit -m "Implements LBL-1"'
t deny  'glab mr create --title "LBL-1 x" --description "Fixes: LBL-1" --label agent-worked'
# GitLab: create + agent labelling free; existing MR gated on its labels; merge human-only
t allow 'glab mr create --source-branch b --target-branch master --title "LBL-1 x" --label agent-worked --squash-before-merge --yes'
t allow 'glab mr create --title "LBL-1 x" --label "agent-worked,bug"'
t allow 'glab mr create --title "LBL-1 x"'
t allow 'glab mr create --title "LBL-1 x" --label bug'
t allow 'glab label create -n agent-worked -c "#7057ff" -d "Worked by an AI agent"'
t ask   'glab label create -n bug'
t allow 'glab mr update 100 --description "new"'
t ask   'glab mr update 200 --description "new"'
t allow 'glab mr update 200 --label agent-worked'                       # tagging an untagged MR is free
t ask   'glab mr update 200 --label agent-worked --description "x"'     # not a pure labelling
t allow 'glab mr note 100 -m "hi"'
t ask   'glab mr note 200 -m "hi"'
t ask   'glab mr note 300 -m "hi"'
t ask   'glab mr note -m "hi"'
t ask   'glab mr update "$IID" --description x'
t allow 'glab mr close 100'
t ask   'glab mr merge 100'
t ask   'glab mr approve 100'
t ask   'glab issue create --title "LBL-1 x"'
t ask   'glab api --method POST projects'
t pass  'glab api "projects/:id/milestones?include_parent_milestones=true"'
# sub MR creation: must target a ticket/sub branch, never master|main
t  deny  'glab mr create -s feat-x-sub-01-schema -b master --draft --label agent-worked --title "LBL-1 [part 1/3] schema" -y'
t  deny  'glab mr create --source-branch feat-x-sub-01-schema --target-branch=main --label agent-worked --title "LBL-1 x" -y'
t  deny  'glab mr create -s feat-x-sub-01-schema --label agent-worked --title "LBL-1 x" -y'
t  ask   'glab mr create -s feat-x-sub-01-schema -b "$BR" --label agent-worked --title "LBL-1 x" -y'
t  allow 'glab mr create -s feat-x-sub-01-schema -b feat-x --draft --label agent-worked --title "LBL-1 [part 1/3] schema" --description-file /tmp/d.md --squash-before-merge -y'
t  allow 'glab mr create -s feat-x-sub-03-ui -b feat-x-sub-02-api --draft --label agent-worked --title "LBL-1 x" -y'
t  allow 'glab mr create -s feat-x -b master --draft --label agent-worked --title "LBL-1 x" --squash-before-merge --remove-source-branch -y'
t  allow 'glab mr create -s feat-x-sub-01-schema -b feat-x --title "LBL-1 x" -y'
tc deny  '/home/u/dev/shop_feat-x-sub-01-schema' 'glab mr create -b feat-x --label agent-worked --title "LBL-1 x" -y'
t  deny  'glab mr create -s feat-x-sub-01-schema -b feat-x --label agent-worked --description "Closes LBL-1"'
# retarget / stack sync
t  deny  'glab mr update 110 --target-branch master'
t  deny  'glab mr update 110 --target-branch=main'
t  deny  'glab mr update 210 --target-branch master'
t  allow 'glab mr update 110 --target-branch feat-x'
t  allow 'glab mr update 110 --description-file /tmp/x.md && glab mr update 100 --description-file /tmp/y.md'
t  allow 'glab mr update 110 --ready'
t  ask   'glab mr update 210 --target-branch feat-x'
t  allow 'glab mr update 100 --target-branch main'
# ---- refactor regressions (shared gate / per-clause parsing) ----------------------
t  deny  'glab mr create -s feat-x -b master --title a -y && glab mr create -s feat-x-sub-01-schema -b master --title b -y'
t  pass  'glab api projects/1/labels | grep -F agent'          # payload check is per api clause now
t  ask   'glab api projects/1 && glab api -X POST projects/1/labels'
t  ask   'glab mr create -s feat-x -b master --title "LBL-1 x" -y && glab mr update 200 --description y'
# ---- harness parameters: ticket example in reasons (core.ticket_example)
tr "e\.g\. 'PROJ-123 fix parser'"                           'git commit -m "Closes LBL-1 parser"'
HARNESS_TICKET_EXAMPLE=ABC-9 tr "e\.g\. 'ABC-9 fix parser'" 'git commit -m "Closes LBL-1 parser"'
# ---- MR title convention (gitlab.mr_title_re), --fill and --related-issue
t  ask   'glab mr create --fill -y'
t  ask   'glab mr create -f --label agent-worked -y'
t  ask   'glab mr create -s f -b main -t "fix parser"'
t  allow 'glab mr create -s f -b main -t "PROJ-123 fix parser" --label agent-worked'
t  allow 'glab mr create -s f -b main --title="PROJ-123 fix parser" --label agent-worked'
t  ask   'glab mr create -s f -b main --title="fix parser" --label agent-worked'
t  ask   'glab mr create -s f -b main --draft -t "PROJ-123" --label agent-worked'          # key without a summary
HARNESS_GITLAB_MR_TITLE_RE='' t allow 'glab mr create -s f -b main -t "fix parser"'
HARNESS_GITLAB_MR_TITLE_RE='^\[[a-z]+\] ' t allow 'glab mr create -s f -b main -t "[api] fix parser" --label agent-worked'
HARNESS_GITLAB_MR_TITLE_RE='^\[[a-z]+\] ' t ask   'glab mr create -s f -b main -t "PROJ-123 fix parser"'
t  ask   'glab mr create -s f -b main --related-issue 7'
t  ask   'glab mr create -s f -b main -t "PROJ-123 x" --related-issue=7'
t  ask   'glab mr create -s f -b main -t "$TITLE"'
t  ask   'glab mr create -s f -b main -t "$(git log -1 --format=%s)"'
t  ask   'glab mr create -s f -b main -t "`git log -1 --format=%s`"'
t  allow 'glab mr create -s f -b main --label agent-worked'                              # no -t: title comes from the commit, not checked
t  allow 'glab mr create -s f -b main -d "-f is not --fill" -t "PROJ-123 x"'                # flag-like values are not flags
t  deny  'glab mr create -s f-sub-01-x -b main -t "fix parser"'                          # a deny still wins over the title ask
# bypass attempts
t  ask   'cd x && glab mr create -s f -b main -t "oops"'
t  ask   'glab mr create -s f -b main -t "PROJ-123 ok" -y; glab mr create -s g -b main -t "oops"'
t  ask   'sh -c "glab mr create -s f -b main --fill"'
t  ask   'bash -c "cd x && glab mr create -s f -b main -t oops"'
tr 'mr create --fill' 'sh -c "glab mr create -s f -b main --fill"'
tr "title 'oops'" "bash -c 'cd x && glab mr create -s f -b main -t oops'"
tr 'mr_title_re' 'glab mr create -s f -b main -t "fix parser"'
tr "e\.g\. 'PROJ-123 fix parser'" 'glab mr create -s f -b main -t "fix parser"'
tr 'description-file' 'glab mr create --fill -y'
# guard.env: an empty gitlab.mr_title_re is omitted from guard.env → disabled when the file lists the bundle
genv=$(mktemp); printf '%s\n' "HARNESS_BUNDLES='core gitlab'" > "$genv"
HARNESS_GUARD_ENV=$genv t allow 'glab mr create -s f -b main -t "fix parser"'
HARNESS_GUARD_ENV=$genv t ask  'glab mr create -s f -b main --fill'
printf '%s\n' "HARNESS_BUNDLES='core gitlab'" "HARNESS_GITLAB_MR_TITLE_RE='^(PROJ|OPS)-[0-9]+ '" > "$genv"
HARNESS_GUARD_ENV=$genv t ask  'glab mr create -s f -b main -t "ABC-1 fix parser"'
HARNESS_GUARD_ENV=$genv t allow 'glab mr create -s f -b main -t "OPS-1 fix parser"'
rm -f "$genv"

# ---- repository-level declaration: .harness.toml (principle 8) ----------------------
decl '[overrides]' 'WORK_TICKET_LABELED_DECISION = "ask"'
r ask   'glab mr note 100 -m "hi"'
WORK_TICKET_LABELED_DECISION=allow r allow 'glab mr note 100 -m "hi"'   # the real environment wins
decl '[overrides]' 'WORK_TICKET_GLAB = "/bin/true"'         # bypass: client paths are never repo-settable
r ask   'glab mr note 200 -m "hi"'
decl '[owns]' 'domains = ["scm"]'
r pass  'glab mr merge 100'
r pass  'glab mr note 200 -m "hi"'
r deny  'git commit -m "Closes LBL-1 parser"'                 # 40-gitlab-closing is tracker: unchanged
decl '[owns]' 'domains = ["tracker"]'
r pass  'git commit -m "Closes LBL-1 parser"'
r ask   'glab mr merge 100'
decl
