# shellcheck shell=bash
# Guard test rows for bundle ticket-workflow. Sourced by bundles/core/guard/tests/run.sh after lib.sh
# (helpers: t EXPECTED 'cmd' | tc EXPECTED CWD 'cmd' | tr 'reason-re' 'cmd' | g EXPECTED 'cmd' in a real dir).

# key-free branch names (75-ticket-workflow)
t ask   'git switch -c PROJ-123-fix-parser'
t ask   'git switch --create=PROJ-123-x'
t ask   'git checkout -b PROJ-123-fix-parser'
t ask   'git checkout -B feat/PROJ-123'
t ask   'git branch PROJ-123-x main'
t ask   'git branch -m old-name PROJ-123-x'
t ask   'git worktree add ../shop_PROJ-123-x -b PROJ-123-x'
t ask   'git -C ../shop switch -c PROJ-123-x'
t ask   'git checkout -b "fix/#42-login"'
t ask   'sh -c "git switch -c PROJ-1-x"'                          # bypass: wrapped in sh -c
t ask   'cd ../shop && git checkout -b PROJ-1-x'                   # bypass: chained after cd
t pass  'git switch -c fix-parser'
t pass  'git checkout -b fix-parser'
t pass  'git switch -c v2-1-bump'                                  # lowercase look-alike, not a key
t pass  'git branch -d PROJ-123-x'                                 # deleting is not naming
t pass  'git branch --list "PROJ-*"'
t pass  'git switch PROJ-123-x'                                    # switching to an existing branch
t pass  'git checkout -b "$BR"'                                    # $VAR names are not resolvable
t pass  'git push -u origin fix-parser'
WORK_TICKET_KEY_IN_BRANCH=1 t pass 'git switch -c PROJ-123-fix-parser'
WORK_TICKET_KEY_IN_BRANCH=1 t pass 'git checkout -b "fix/#42-login"'
tr 'short-name'                     'git switch -c PROJ-123-x'
tr 'WORK_TICKET_KEY_IN_BRANCH=1'    'git checkout -b PROJ-123-x'
# key-free commit subjects
t ask   'git commit -m "PROJ-123 fix parser"'
t ask   'git commit -am "PROJ-123 fix parser"'
t ask   'git commit --message="PROJ-123 fix parser"'
t ask   'git commit --message "PROJ-123: fix parser" -m "body"'
t ask   'git -c user.name=u commit -m "PROJ-123 fix parser"'
t ask   'cd ../shop && git commit -m "PROJ-9 x"'                   # bypass: chained after cd
t ask   'sh -c "git commit -m PROJ-9-x"'                            # bypass: wrapped in sh -c
t pass  'git commit -m "fix parser"'
t pass  'git commit -m "v2-1 bump"'
t pass  'git commit -m "fix parser" -m "PROJ-123 context"'         # keys belong in the body
t pass  'git commit -m "fix parser (see PROJ-123)"'
t pass  'git commit -F /tmp/msg.txt'
t pass  'git commit -m "$MSG"'
t pass  'git commit --amend --no-edit'
WORK_TICKET_KEY_IN_BRANCH=1 t pass 'git commit -m "PROJ-123 fix parser"'
tr 'mention the key in the body or MR' 'git commit -m "PROJ-123 fix parser"'
# a deny in the same command still wins over the deferred ask
t deny  'git switch -c PROJ-1-x && git push origin main'
# sub worktree paths: ../<repo>_<branch>
GIT_STUB_TOPLEVEL=/home/u/dev/shop t pass 'git worktree add ../shop_feat-x-sub-01-schema -b feat-x-sub-01-schema'
GIT_STUB_TOPLEVEL=/home/u/dev/shop t pass 'git worktree add -b feat-x-sub-01-schema /home/u/dev/shop_feat-x-sub-01-schema feat-x'
GIT_STUB_TOPLEVEL=/home/u/dev/shop t ask  'git worktree add /tmp/wt -b feat-x-sub-01-schema'
GIT_STUB_TOPLEVEL=/home/u/dev/shop t ask  'git worktree add ../feat-x-sub-01-schema -b feat-x-sub-01-schema'
GIT_STUB_TOPLEVEL=/home/u/dev/shop t ask  'cd /tmp && git worktree add wt -b feat-x-sub-01-schema'
GIT_STUB_TOPLEVEL=/home/u/dev/shop t pass 'git worktree add /tmp/wt -b feat-x'          # not a sub branch
GIT_STUB_TOPLEVEL=/home/u/dev/shop t pass 'git worktree add "$WT" -b feat-x-sub-01-schema'
t pass  'git worktree add /tmp/wt -b feat-x-sub-01-schema'          # git lookup fails: no decision
GIT_STUB_TOPLEVEL=/home/u/dev/shop tr 'use \.\./shop_feat-x-sub-01-schema instead' 'git worktree add /tmp/wt -b feat-x-sub-01-schema'
# squash delivery of -sub- parts
t ask   'git merge --no-ff feat-x-sub-01-schema'
t ask   'git merge --ff-only feat-x-sub-01-schema'
t ask   'git merge --ff feat-x-sub-01-schema'
t ask   'git merge feat-x-sub-01-schema'
t ask   'git merge -m "merge part" feat-x-sub-01-schema'
t ask   'git checkout feat-x && git merge --no-ff feat-x-sub-02-api'    # bypass: chained
t pass  'git merge --squash feat-x-sub-01-schema'
t pass  'git merge --no-ff feat-x'
t pass  'git merge --abort'
t pass  'git merge "$SUB"'
tr 'git merge --squash' 'git merge --no-ff feat-x-sub-01-schema'
