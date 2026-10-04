# shellcheck shell=bash
# Guard test rows for bundle gitlab. Sourced by bundles/core/guard/tests/run.sh after lib.sh
# (helpers: t EXPECTED 'cmd' | tc EXPECTED CWD 'cmd' | tr 'reason-re' 'cmd' | g EXPECTED 'cmd' in a real dir).

# closing keywords + Jira key (40-gitlab-closing)
t deny  'git commit -m "Closes LBL-1 parser"'
t deny  'git commit -m "Implements LBL-1"'
t deny  'glab mr create --title x --description "Fixes: LBL-1" --label agent-worked'
# GitLab: create + agent labelling free; existing MR gated on its labels; merge human-only
t allow 'glab mr create --source-branch b --target-branch master --title "LBL-1 x" --label agent-worked --squash-before-merge --yes'
t allow 'glab mr create --title x --label "agent-worked,bug"'
t allow 'glab mr create --title x'
t allow 'glab mr create --title x --label bug'
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
t ask   'glab issue create --title x'
t ask   'glab api --method POST projects'
t pass  'glab api "projects/:id/milestones?include_parent_milestones=true"'
# sub MR creation: must target a ticket/sub branch, never master|main
t  deny  'glab mr create -s feat-x-sub-01-schema -b master --draft --label agent-worked --title "LBL-1 [part 1/3] schema" -y'
t  deny  'glab mr create --source-branch feat-x-sub-01-schema --target-branch=main --label agent-worked --title x -y'
t  deny  'glab mr create -s feat-x-sub-01-schema --label agent-worked --title x -y'
t  ask   'glab mr create -s feat-x-sub-01-schema -b "$BR" --label agent-worked --title x -y'
t  allow 'glab mr create -s feat-x-sub-01-schema -b feat-x --draft --label agent-worked --title "LBL-1 [part 1/3] schema" --description-file /tmp/d.md --squash-before-merge -y'
t  allow 'glab mr create -s feat-x-sub-03-ui -b feat-x-sub-02-api --draft --label agent-worked --title x -y'
t  allow 'glab mr create -s feat-x -b master --draft --label agent-worked --title "LBL-1 x" --squash-before-merge --remove-source-branch -y'
t  allow 'glab mr create -s feat-x-sub-01-schema -b feat-x --title x -y'
tc deny  '/home/u/dev/shop_feat-x-sub-01-schema' 'glab mr create -b feat-x --label agent-worked --title x -y'
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
t  ask   'glab mr create -s feat-x -b master --title x -y && glab mr update 200 --description y'
# ---- harness parameters: ticket example in reasons (core.ticket_example)
tr "e\.g\. 'PROJ-123 fix parser'"                           'git commit -m "Closes LBL-1 parser"'
HARNESS_TICKET_EXAMPLE=ABC-9 tr "e\.g\. 'ABC-9 fix parser'" 'git commit -m "Closes LBL-1 parser"'
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
