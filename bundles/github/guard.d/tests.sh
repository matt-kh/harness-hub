# shellcheck shell=bash
# Guard test rows for bundle github. Sourced by bundles/core/guard/tests/run.sh after lib.sh
# (helpers: t EXPECTED 'cmd' | tc EXPECTED CWD 'cmd' | tr 'reason-re' 'cmd' | g EXPECTED 'cmd' in a real dir).

# ---- GitHub (gh) -------------------------------------------------------------------
# lookups cd into the command's cwd, so gh write-gate rows run in an existing directory
# reads / passthrough
t pass  'gh pr view 100 --json title'
t pass  'gh pr list --state open'
t pass  'gh issue view 3 --comments'
t pass  'gh auth status'
t pass  'gh repo set-default o/r'
t pass  'gh config get git_protocol'
t pass  'gh api repos/o/r/pulls'
t pass  'gh api repos/o/r/pulls/1 --jq .title'
t pass  'gh api -X GET search/issues -f q=x'
t pass  'gh api --method GET repos/o/r/issues -F per_page=100'
t pass  "gh api graphql -f query='{ viewer { login } }'"
t pass  "gh api graphql -f query='query { repository(owner:\"o\", name:\"r\") { id } }'"
t pass  'gh api -X GET search/issues -f q=x && gh api repos/o/r'
t pass  'ls ~/.config/gh/'
# gh api writes ask
t ask   'gh api -X POST repos/o/r/issues -f title=x'
t ask   'gh api -XPOST repos/o/r/labels'
t ask   'gh api --method=patch repos/o/r'
t ask   'gh api -X DELETE repos/o/r/git/refs/heads/x'
t ask   'gh api repos/o/r/issues -f title=x'
t ask   'gh api repos/o/r/issues --input -'
t ask   'gh api repos/o/r && gh api repos/o/r/labels -f name=x'
t ask   "gh api graphql -f query='mutation { addStar(input:{starrableId:\"x\"}) { clientMutationId } }'"
t ask   'gh api graphql -F query=@q.graphql'
t ask   'gh api graphql -f query="$(cat q.graphql)"'
t ask   "gh api graphql -f query='query A { viewer { login } }' -f operationName=A"
t deny  'gh api repos/o/r/issues/3/comments -f body="Fixes #3"'
# token / credential denies
t deny  'gh auth token'
t deny  'GH_TOKEN=$(gh auth token) make release'
t deny  'gh auth status --show-token'
t deny  'gh auth status -h github.com -t'
t deny  'gh config get oauth_token -h github.com'
t deny  'cat ~/.config/gh/hosts.yml'
t deny  'grep oauth ~/.config/gh/hosts.yml'
tr 'gh auth status' 'cat ~/.config/gh/hosts.yml'
tr 'gh auth token prints' 'gh auth token'
# team-visible asks
t ask   'gh pr merge 100 --squash'
t ask   'gh -R o/r pr merge 100'
t ask   'gh pr review 100 --approve'
t ask   'gh issue delete 1 --yes'
t ask   'gh issue transfer 1 o/other'
t ask   'gh issue develop 1 --checkout'
t ask   'gh repo fork o/r --remote'
t ask   'gh repo sync'
t ask   'gh repo edit --delete-branch-on-merge'
t ask   'gh label edit bug --color ff0000'
t ask   'gh workflow run ci.yml'
t ask   'gh run cancel 123'
t ask   'gh secret set TOKEN'
t ask   'gh gist create notes.md'
t ask   'gh auth switch'
t ask   'gh alias set co "pr checkout"'
t ask   'gh extension install owner/gh-x'
t ask   'gh release create v1.0.0'
tr 'human decision' 'gh pr merge 100'
# gh pr update-branch: decided by the PR label gate (no longer an always-ask team action)
g allow 'gh pr update-branch 100'
g allow 'gh pr update-branch 110 --rebase'
g allow 'gh pr update-branch 110 -R o/r --rebase'
g ask   'gh pr update-branch 200'
g ask   'gh pr update-branch 120'                                  # fork PR
g ask   'gh pr update-branch'                                      # no ref: labels cannot be checked
g ask   'gh pr update-branch "$N"'
g ask   'GH_REPO=o/r gh pr update-branch 110'
g ask   'gh pr update-branch 110 && gh pr merge 110'               # merge stays a human decision (ask)
g ask   'sh -c "gh pr update-branch 200"'
# label create (positional name)
t allow 'gh label create agent-worked -c 7057ff -d "Worked by an AI agent"'
t allow 'gh label create -R o/r agent-drafted --force'
t ask   'gh label create bug'
t ask   'gh label create "$L"'
# pr create
t  allow 'gh pr create -H feat-x -B main -t "x" -b "body" -l agent-worked'
t  allow 'gh pr create -H feat-x-sub-01-schema -B feat-x -t x -l agent-worked'
t  allow 'gh pr create -R up/r -H me:feat-x-sub-01-schema -B feat-x -t x'
t  deny  'gh pr create --head=feat-x-sub-01-schema --base=master -t x'
t  deny  'gh pr create -H me:feat-x-sub-01-schema -B main -t x'
t  deny  'gh pr create -H feat-x-sub-01-schema -t x'
t  deny  'gh pr create -f -H feat-x-sub-01-schema -B main'            # -f is --fill (boolean)
t  ask   'gh pr create -H feat-x-sub-01-schema -B "$BR" -t x'
t  ask   'gh pr create -H "$BR" -B main -t x'
tc deny  '/home/u/dev/shop_feat-x-sub-01-schema' 'gh pr create -B feat-x -t x'
tc allow '/home/u/dev/shop_feat-x-sub-01-schema' 'gh pr create -H feat-x-sub-01-schema -B feat-x -t x'
GIT_STUB_BRANCH=feat-x-sub-01-schema t deny  'gh pr create -B main -t x'
GIT_STUB_BRANCH=feat-x-sub-01-schema t allow 'gh pr create -B feat-x -t x'
GIT_STUB_BRANCH=feat-x               t allow 'gh pr create -B main -t x'
t  deny  'gh pr create -H feat-x -B main -t a && gh pr create -H feat-x-sub-01-schema -B main -t b'
t  pass  'gh pr create --web -H feat-x-sub-01-schema'
t  pass  'gh pr create --dry-run -H feat-x-sub-01-schema -B main'
t  deny  'gh pr create -H feat-x -B main -t x -b "Fixes #3"'
t  allow 'gh pr create -H feat-x -B main -t x -b "part of #3, see #4"'
t  allow $'gh pr create -H feat-x -B main -t x -F - <<\'EOF\'\nit\'s done\nEOF'
tr 'target the ticket branch' 'gh pr create -H a-sub-01-x -B main'
# pr create: --fill* and the title convention (github.pr_title_forbid_re)
t  ask   'gh pr create -R o/r -H f -B main --fill'
t  ask   'gh pr create -R o/r -H f -B main --fill-first'
t  ask   'gh pr create -R o/r -H f -B main --fill-verbose -l agent-worked'
t  ask   'gh pr create -R o/r -f -H f -B main'
t  ask   'gh pr create -R o/r -H f -B main -t "Fix login #42" -F b.md'
t  ask   'gh pr create -R o/r -H f -B main --title="Login form (#42)" -F b.md'
t  allow 'gh pr create -R o/r -H f -B main -t "Fix login" -F b.md'
t  allow 'gh pr create -R o/r -H f -B main --title="Fix login" -F b.md -l agent-worked'
t  allow 'gh pr create -R o/r -H f -B main -t "Fix login" -b "-f is not --fill, see #42"'
HARNESS_GITHUB_PR_TITLE_FORBID_RE='' t allow 'gh pr create -R o/r -H f -B main -t "Login form #42" -F b.md'
HARNESS_GITHUB_PR_TITLE_FORBID_RE='#[0-9]+|WIP' t ask 'gh pr create -R o/r -H f -B main -t "WIP login" -F b.md'
t  ask   'gh pr create -R o/r -H f -B main -t "$TITLE" -F b.md'
t  ask   'gh pr create -R o/r -H f -B main -t "`git log -1 --format=%s`" -F b.md'
t  pass  'gh pr create -R o/r --web --fill'                                  # --web creates nothing here
t  deny  'gh pr create -R o/r -H f-sub-01-x -B main -t "Login form #42"'     # a deny still wins over the title ask
# bypass attempts
t  ask   'sh -c "gh pr create -R o/r -H f -B main --fill"'
t  ask   'cd x && gh pr create -R o/r -H f -B main -t "Login form #42" -F b.md'
t  ask   'gh pr create -R o/r -H f -B main -t ok -F b.md; gh pr create -R o/r -H g -B main --fill'
tr 'pr create --fill' 'sh -c "gh pr create -R o/r -H f -B main --fill"'
tr 'pr_title_forbid_re' 'gh pr create -R o/r -H f -B main -t "Login form #42" -F b.md'
tr 'body-file' 'gh pr create -R o/r -H f -B main --fill'
# guard.env: an empty github.pr_title_forbid_re is omitted from guard.env → disabled when the file lists the bundle
genv=$(mktemp); printf '%s\n' "HARNESS_BUNDLES='core github'" > "$genv"
HARNESS_GUARD_ENV=$genv t allow 'gh pr create -R o/r -H f -B main -t "Login form #42" -F b.md'
HARNESS_GUARD_ENV=$genv t ask   'gh pr create -R o/r -H f -B main --fill'
rm -f "$genv"
# pr write gate
g allow 'gh pr edit 100 -b "new"'
g ask   'gh pr edit 200 -b new'
g allow 'gh pr edit 200 --add-label agent-worked'
g allow 'gh pr edit 200 -R o/r --add-label agent-worked'
g ask   'gh pr edit 200 --add-label agent-worked --title x'
g allow 'gh pr comment "#100" -b hi'
g allow 'gh pr comment feat-x -b hi'
g allow 'gh pr comment https://github.com/o/r/pull/100 -b hi'
g allow 'gh pr comment 100 --edit-last -b hi'
g ask   'gh pr comment -b hi'
g ask   'gh pr comment #100 -b hi'                  # unquoted # is a shell comment → no ref
g ask   'gh pr comment "$N" -b hi'
g ask   'gh pr comment 300 -b hi'
t ask   'gh pr comment 100 -b hi'                   # cwd does not exist → lookup fails → ask
g allow 'gh pr ready --undo 110'
g allow 'gh -R o/r pr comment 100 -b hi'
g allow 'gh pr -R o/r close 100 -d'
g ask   'gh pr close 200'
g ask   'gh pr reopen 200'
g ask   'gh pr comment 120 -b hi'                   # cross-repository (fork) PR
g deny  'gh pr edit 110 -B main'
g deny  'gh pr edit 210 --base main'
g allow 'gh pr edit 110 --base feat-x'
g ask   'gh pr edit 210 -B feat-x'
g allow 'gh pr edit 100 -B main'
g ask   'gh pr comment 100 -b x && gh pr comment 200 -b y'
g deny  'gh pr comment 200 -b x && gh pr edit 110 -B main'
g deny  'gh pr merge 100 -b "Closes #3"'
g deny  'gh pr edit 100 -b "Resolves o/r#3"'
g ask   'GH_REPO=o/r gh pr comment 100 -b hi'
# issue create: provenance label required
t allow 'gh issue create -t x -b y -l agent-drafted'
t allow 'gh issue create -R o/r -t x -l bug,agent-drafted'
t allow 'gh issue create -t x -l bug -l agent-created'
t allow 'gh issue create --label=agent-drafted -t x'
t deny  'gh issue create -t x -l bug'
t deny  'gh issue create -t x'
t deny  'gh issue create -t agent-drafted -l bug'
t deny  'gh issue create -t a -l agent-drafted && gh issue create -t b'
t pass  'gh issue create --web'
tr 'provenance label' 'gh issue create -t x'
# issue write gate
g allow 'gh issue edit 1 2 --add-label bug'
g ask   'gh issue edit 1 3 --add-label bug'
g allow 'gh issue edit 3 --add-label agent-worked'
g allow 'gh issue edit 3 4 --add-label agent-worked,agent-drafted'
g allow 'gh issue edit 1 --add-sub-issue 5'
g allow 'gh issue edit -R o/r 1 --add-label x'
g allow 'gh issue comment 1 -b hi'
g allow 'gh issue comment 2 -b hi'
g allow 'gh issue comment "#1" -b hi'
g allow 'gh issue comment https://github.com/o/r/issues/1 -b hi'
g ask   'gh issue comment 3 -b hi'
g ask   'gh issue comment 4 -b hi'
g ask   'gh issue comment 9 -b hi'
g allow 'gh issue close 1 -c "done" -r completed'
g ask   'gh issue close 3'                                  # #67: human issue state asks on the main thread (was deny)
g ask   'gh issue reopen 3'                                 # #67: was deny
g ask   'gh issue comment 3 -b x && gh issue close 3'       # #67: was deny
g ask   'gh issue close 9'
g ask   'gh issue close "$N"'
WORK_TICKET_ALLOW_TRANSITION=1 g ask 'gh issue close 3'     # #67: the override no longer changes GitHub issue state (ask either way)
g ask   'gh issue close 3 --add-label agent-worked'          # labelling flags never make a state change free
g ask   'gh issue comment 3 -b "fixes #3 landed"'
g allow 'gh issue comment 1 -b "fixes #3 landed"'
# GitHub closing keywords in commits
t deny  'git commit -m "Fixes #12"'
t deny  'git commit -m "Resolves: o/r#7"'
t deny  'git commit -m "closed https://github.com/o/r/issues/7"'
t pass  'git commit -m "see #12"'
t pass  'git commit -m "implements #12"'
t pass  'git commit -m "prefix #12 cleanup"'
tr 'GitHub close the issue' 'git commit -m "Fixes #12"'
tr 'side effect \(denied even on request\)' 'git commit -m "Fixes #12"'
# ---- repository-level declaration: .harness.toml (principle 8) ----------------------
decl '[overrides]' 'WORK_TICKET_ALLOW_TRANSITION = "1"'
r ask   'gh issue close 3'                                    # #67: ask with or without the override
WORK_TICKET_ALLOW_TRANSITION=0 r ask 'gh issue close 3'      # #67: was deny; the override no longer matters for GitHub issues
decl '[overrides]' 'WORK_TICKET_LABELED_DECISION = "ask"'
r ask   'gh issue comment 1 -b hi'
decl '[overrides]' 'WORK_TICKET_GH = "/bin/true"'           # bypass: client paths are never repo-settable
# shellcheck disable=SC2154  # rpd: the fixture repository, defined in guard/tests/lib.sh
tn ask 'WORK_TICKET_GH is settable only from your own environment' "$rpd" 'gh issue close 3'   # #67: was deny (human issue state now asks)
decl '[owns]' 'domains = ["scm"]'
r pass  'gh issue close 3'
r pass  'gh issue create --title x'
r deny  'git commit -m "Fixes #12"'                           # 41-github-closing is tracker: unchanged
decl '[owns]' 'domains = ["tracker"]'
r pass  'git commit -m "Fixes #12"'
r ask   'gh issue close 3'                                    # #67: was deny
decl '[owns]' 'components = ["github/guard.d/41-github-closing"]'
r ask   'gh issue close 3'                                    # #67: was deny; 60-github still runs on 41's shared definitions
r ask   'gh pr merge 100'
# never yields: commands that print the developer's stored credential (prelude above repo_owns)
decl '[owns]' 'domains = ["scm", "kubernetes", "tracker", "workspace"]'
r deny  'gh auth token'
r deny  'gh auth status --show-token'
r deny  'gh auth status -t'
r deny  'gh config get oauth_token'
r deny  'cd sub && gh auth token'                              # bypass: wrapped
r deny  'sh -c "gh auth token | cat"'
decl '[owns]' 'components = ["github/guard.d/60-github"]'
r deny  'gh auth token'
r pass  'gh auth status'
# documented consequence: owning scm lifts the merge ask and the issue-state ask
decl '[owns]' 'domains = ["scm", "kubernetes", "tracker", "workspace"]'
r pass  'gh pr merge 100'
r pass  'gh issue close 3'
# yielding comes first (principle 8): an owned scm domain passes a subagent's human decisions too
decl '[owns]' 'domains = ["scm"]'
T_AGENT=a1 r pass 'gh pr merge 100'
T_AGENT=a1 r pass 'gh issue close 3'
T_AGENT=a1 r pass 'gh api -X PUT repos/o/r/pulls/1/merge'
T_AGENT=a1 r deny 'gh auth token'                             # never yields, in a subagent too
decl
# runtime deny/ask messages carry the # rule: alternative (lint guard-messages)
tr 'matching gh subcommand' 'gh api -X POST repos/o/r/issues -f title=x'
tr 'matching gh subcommand' 'gh api repos/o/r/issues --input -'
tr 'pass the query inline' 'gh api graphql -F query=@q.graphql'
tr 'literal inline query' 'gh api graphql -f query="$(cat q.graphql)"'
tr 'drop operationName' "gh api graphql -f query='query A { viewer { login } }' -f operationName=A"
tr 'human decision.*ask the user instead' 'gh pr merge 100 --squash'
# ---- humans decide (#67): merge, review and PR/issue state ----------------------------
# main thread: merge/review ask on any ref; state asks on a human ref, an agent-labelled ref keeps allow
g ask   'gh pr merge 100'
g ask   'gh pr merge 200'
g ask   'gh pr review 100 --approve'
g ask   'gh pr review 200 --comment -b x'
g ask   'gh pr close 200'
g ask   'gh pr reopen 200'
g ask   'gh pr ready 200'
g ask   'gh pr ready --undo 200'
g ask   'gh issue close 3'
g ask   'gh issue reopen 3'
g allow 'gh pr close 100'
g allow 'gh pr reopen 100'
g allow 'gh pr ready 100'
g allow 'gh issue close 1'
g allow 'gh issue reopen 1'
T_AGENT=''        g ask   'gh pr merge 100'                  # agent_id "" = main thread
T_AGENT_NULL=1    g allow 'gh pr close 100'                  # agent_id null = main thread
T_AGENT_TYPE=Plan g ask   'gh pr merge 100'                  # main thread under --agent
T_AGENT_TYPE=Plan g allow 'gh issue close 1'
# subagent: every merge, review, state change and raw API write denies (human and agent-labelled refs)
T_AGENT=a1 g deny 'gh pr merge 100'
T_AGENT=a1 g deny 'gh pr merge 200'
T_AGENT=a1 g deny 'gh pr review 100 --approve'
T_AGENT=a1 g deny 'gh pr review 200 --comment -b x'
T_AGENT=a1 g deny 'gh pr close 100'
T_AGENT=a1 g deny 'gh pr close 200'
T_AGENT=a1 g deny 'gh pr reopen 100'
T_AGENT=a1 g deny 'gh pr reopen 200'
T_AGENT=a1 g deny 'gh pr ready 100'
T_AGENT=a1 g deny 'gh pr ready 200'
T_AGENT=a1 g deny 'gh pr ready --undo 110'
T_AGENT=a1 g deny 'gh pr close 120'                          # fork PR
T_AGENT=a1 g deny 'gh pr close "$N"'                         # denied before any lookup
T_AGENT=a1 g deny 'gh pr close'
T_AGENT=a1 g deny 'gh issue close 1'
T_AGENT=a1 g deny 'gh issue close 3'
T_AGENT=a1 g deny 'gh issue reopen 1'
T_AGENT=a1 g deny 'gh issue reopen 3'
T_AGENT=a1 g deny 'gh issue close 9'
T_AGENT=a1 g deny 'gh api -X PUT repos/o/r/pulls/1/merge'
T_AGENT=a1 g deny 'gh api repos/o/r/issues/3 -f state=closed'
T_AGENT=a1 g deny 'gh api repos/o/r/issues --input -'
T_AGENT=a1 g deny "gh api graphql -f query='mutation { mergePullRequest(input:{pullRequestId:\"x\"}) { clientMutationId } }'"
T_AGENT=a1 g deny 'GH_REPO=o/r gh pr close 100'
# subagent: everything else is unchanged
T_AGENT=a1 g allow 'gh pr comment 100 -b hi'
T_AGENT=a1 g allow 'gh pr edit 100 -b new'
T_AGENT=a1 g allow 'gh pr update-branch 110 --rebase'
T_AGENT=a1 g ask   'gh pr comment 200 -b hi'
T_AGENT=a1 g allow 'gh issue comment 1 -b hi'
T_AGENT=a1 g allow 'gh issue edit 3 --add-label agent-worked'
T_AGENT=a1 g pass  'gh pr view 100 --json title'
T_AGENT=a1 g pass  'gh api repos/o/r/pulls'
T_AGENT=a1 g pass  "gh api graphql -f query='{ viewer { login } }'"
T_AGENT=a1 t ask   'gh release create v1.0.0'
T_AGENT=a1 g allow 'gh pr create -H feat-x -B main -t x -l agent-worked'
# subagent bypass attempts: still denied
T_AGENT=a1 g deny 'sh -c "gh pr merge 100"'
T_AGENT=a1 g deny 'GH_TOKEN=x gh pr merge 100'
T_AGENT=a1 g deny 'cd sub && gh pr merge 100'
T_AGENT=a1 g deny 'gh -R o/r pr merge 100'
T_AGENT=a1 g deny 'gh pr -R o/r close 100'
T_AGENT=a1 g deny 'gh pr update-branch 110 && gh pr merge 110'
T_AGENT=a1 g deny 'gh pr comment 100 -b x; gh issue close 1'
T_AGENT=a1 g deny "bash -c 'gh issue reopen 1'"
T_AGENT=a1 g deny 'echo 100 | xargs gh pr merge'
# closing keywords: unchanged (section 41), on either caller
g deny  'gh pr merge 100 -b "Closes #3"'
T_AGENT=a1 g deny 'gh pr merge 100 -b "Closes #3"'
# reasons: the subagent deny hands the command back; the main-thread ask names the alternative
T_AGENT=a1 tr 'hand the command back to the main thread' 'gh pr merge 100'
T_AGENT=a1 tr 'hand the command back to the main thread' 'gh issue close 1'
T_AGENT=a1 tr 'hand the command back to the main thread' 'gh api -X PUT repos/o/r/pulls/1/merge'
tr 'explicit request.*ask the user' 'gh pr merge 200'
tr 'use an agent-\* name, or ask the user' 'gh label create bug'
# ---- humans decide (#67), review hardening: hidden forms of the same calls --------------
# fd duplications no longer cut a clause short (C1)
T_AGENT=a1 g deny  'gh api repos/o/r/pulls/1/merge 2>&1 -X PUT'
T_AGENT=a1 g deny  'gh api repos/o/r/issues/3 >&2 -f state=closed'
T_AGENT=a1 g deny  'gh pr close 100 2>&1'
T_AGENT=a1 g deny  'gh pr comment 100 -b x &>/dev/null; gh pr merge 100'
g deny  'gh pr edit 110 2>&1 --base main'                      # stacked-delivery deny no longer bypassed
g deny  'gh pr edit 110 >&2 -B main'
g allow 'gh pr comment 100 -b hi 2>&1'
g ask   'gh api repos/o/r/pulls/1/merge 2>&1 -X PUT'
# quoted / escaped command words (W1)
T_AGENT=a1 g deny  'gh "pr" merge 100'
T_AGENT=a1 g deny  'gh pr "merge" 100'
T_AGENT=a1 g deny  'g\h pr merge 100'
T_AGENT=a1 g deny  "gh 'issue' close 1"
T_AGENT=a1 g deny  'gh "api" -X PUT repos/o/r/pulls/1/merge'
g ask   'gh "pr" merge 100'
g ask   'gh "pr" comment 100 -b hi'                          # cannot be checked: asks on the main thread
g allow 'gh pr comment 100 -b "run \"gh pr view\" first"'        # quoted command words inside text are not hidden words
g pass  'gh api "repos/o/r/pulls"'
# $VAR / $(…) in the noun or verb slot (W2)
T_AGENT=a1 g deny  'a=merge; gh pr $a 100'
T_AGENT=a1 g deny  'gh pr ${x:-merge} 100'
T_AGENT=a1 g deny  'gh $(echo pr) merge 100'
T_AGENT=a1 g deny  'gh pr `echo close` 100'
g ask   'a=merge; gh pr $a 100'
g pass  'gh pr view "$N" --json title'
g pass  'gh api "repos/$R/pulls"'
# attached repo flag (W3)
T_AGENT=a1 g deny  'gh -Ro/r pr merge 100'
T_AGENT=a1 g deny  'gh pr -Ro/r merge 100'
T_AGENT=a1 g deny  'gh pr -Ro/r close 100'
T_AGENT=a1 g deny  'gh pr --repo=o/r ready 100'
T_AGENT=a1 g deny  'gh -R o/r api -X PUT repos/o/r/pulls/1/merge'
g ask   'gh -Ro/r pr merge 100'
g allow 'gh pr -Ro/r close 100'
g ask   'gh pr close -Ro/r 200'
g allow 'gh pr comment 100 -Ro/r -b hi'                      # attached -R no longer swallows the next flag
# closing keywords with an attached repo flag or the new alias (section 41 since #76)
g deny  'gh -Ro/r pr edit 100 -b "Closes #3"'
g deny  'gh pr -Ro/r edit 100 -b "Closes #3"'
g deny  'gh -R=o/r pr edit 100 -b "Fixes #3"'
g deny  'gh --repo=o/r pr merge 100 -b "Resolves #3"'
g deny  'gh pr new -H feat-x -B main -t x -b "Fixes #3"'
g deny  'gh -Ro/r pr new -H feat-x -B main -t x -b "Closes o/r#3"'
T_AGENT=a1 g deny 'gh -Ro/r pr edit 100 -b "Closes #3"'
tr 'would let GitHub close the issue' 'gh pr new -H feat-x -B main -t x -b "Fixes #3"'
# #76: a repository that owns scm (not tracker) skips 60 but keeps the closing-keyword deny of 41
decl '[owns]' 'domains = ["scm"]'
r deny  'gh -Ro/r pr edit 100 -b "Closes #3"'
r deny  'gh pr -Ro/r edit 100 -b "Closes #3"'
r deny  'gh pr new -H feat-x -B main -t x -b "Fixes #3"'
r deny  'gh --repo=o/r pr merge 100 -b "Resolves #3"'
r pass  'gh -Ro/r pr edit 100 -b "part of #3"'
r deny  'gh "pr" edit 100 -b "Closes #3"'                     # quoted noun: 60 (which asks) is skipped, 41 denies
r deny  'gh pr "edit" 100 -b "Closes #3"'
r deny  'p=pr; gh $p edit 100 -b "Closes #3"'                 # $VAR noun
r deny  'v=edit; gh pr $v 100 -b "Closes #3"'                 # $VAR verb
r deny  'gh pr -R o/r -R o/r edit 100 -b "Closes #3"'         # repeated repo flag
r deny  'gh -R o/r --repo o/r pr edit 100 -b "Closes #3"'
r pass  'gh pr -R list; echo "Closes #3"'                     # a bare -R is no repo flag
r pass  'gh "pr" view 100'                                    # no closing keyword: 41 does not care
decl '[owns]' 'domains = ["tracker"]'
r allow 'gh -Ro/r pr edit 100 -b "Closes #3"'                # yields with 41 when the repository owns tracker
r allow 'gh pr new -H feat-x -B feat-y -t x -b "Fixes #3"'
decl
# deletes and transfers are human decisions (W6)
T_AGENT=a1 g deny  'gh issue delete 1 --yes'
T_AGENT=a1 g deny  'gh issue transfer 1 o/other'
g ask   'gh issue delete 3 --yes'
g ask   'gh issue transfer 3 o/other'
# create aliases: gh pr new / gh issue new follow the create rules
g deny  'gh issue new -t x'
g allow 'gh issue new -t x -l agent-drafted'
g deny  'gh pr new -H feat-x-sub-01-schema -B main -t x'
g allow 'gh pr new -H feat-x-sub-01-schema -B feat-x -t x'
# attached short values in creates
g deny  'gh pr create -Hfeat-x-sub-01-schema -Bmain -t x'
g allow 'gh pr create -Hfeat-x-sub-01-schema -Bfeat-x -t x'
g deny  'gh pr create -Ro/r -H feat-x-sub-01-schema -B main -t x'
g allow 'gh issue create -t x -lagent-drafted'
# reasons
T_AGENT=a1 tr 'hand the command back to the main thread' 'gh "pr" merge 100'
tr 'write the gh subcommand unquoted' 'gh "pr" merge 100'
tr 'write the subcommand literally' 'a=merge; gh pr $a 100'
T_AGENT=a1 tr 'hand the command back to the main thread' 'gh issue delete 1 --yes'
# ---- closing an issue from the PR to the default branch (issue 80, part 01) ------------
# allowed only where the repository's tracker is GitHub Issues (declared here; part 02 below
# resolves an undeclared one from ticket_workflow.trackers and the host), the knob
# github.close_issue_on_merge is on (default) and every #N is agent-worked (stub: 1 agent-worked,
# 2 agent-drafted, 3 bug, 9 unknown; PR 100 -> main, 110 sub -> feat-x, 120 fork)
decl '[repo]' 'tracker = "github-issues"'
r allow 'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1"'
r allow 'gh pr new -R o/r -H feat-x -B main -t x -b "Closes #1"'
r allow 'gh pr create -Ro/r -H feat-x -B main -t x -b "Fixes #1"'
r allow 'gh pr create --repo=o/r -H feat-x --base=main -t x -b "Resolves: #1"'
r allow 'gh -R o/r pr create -H feat-x -B main -t x -b "closes #1, part of #3"'
r deny  'gh -R o/r pr create -H feat-x -B master -t x -b "closes #1, part of #3"'   # master matches BASE_BRANCH_RE but the default branch is main
GH_STUB_DEFAULT_BRANCH=develop r allow 'gh pr create -R o/r -H feat-x -B develop -t x -b "Closes #1"'
GH_STUB_DEFAULT_BRANCH=develop r deny  'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1"'
GH_STUB_DEFAULT_BRANCH=develop r deny  'gh pr edit 100 -b "Closes #1"'                 # PR 100 targets main, not the default
r allow 'gh pr create -H feat-x -Bmain -t x -b "Closes #1" -l agent-worked'
r allow 'gh pr edit 100 -b "Closes #1"'
r allow 'gh pr edit 100 -R o/r -B main -b "Closes #1"'
r allow 'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1" 2>&1'
GIT_STUB_BRANCH=feat-x r allow 'gh pr create -B main -t x -b "Closes #1"'      # head from the current branch
r deny  'gh pr edit 110 -b "Closes #1"'                                        # sub PR
r deny  'gh pr edit 120 -b "Closes #1"'                                        # fork PR
r deny  'gh pr edit 300 -b "Closes #1"'                                        # unreadable PR
r deny  'gh pr edit 100 -B feat-y -b "Closes #1"'                              # retargeted away from the default branch
r deny  'gh pr edit "$N" -b "Closes #1"'
r deny  'gh pr edit -b "Closes #1"'                                            # no PR number
# the knob switches the allow off
HARNESS_GITHUB_CLOSE_ISSUE_ON_MERGE=false r deny 'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1"'
HARNESS_GITHUB_CLOSE_ISSUE_ON_MERGE=false r deny 'gh pr new -R o/r -H feat-x -B main -t x -b "Closes #1"'
HARNESS_GITHUB_CLOSE_ISSUE_ON_MERGE=false r deny 'gh pr edit 100 -b "Closes #1"'
HARNESS_GITHUB_CLOSE_ISSUE_ON_MERGE=0     r deny 'gh pr edit 100 -b "Closes #1"'   # anything but exactly true is off
HARNESS_GITHUB_CLOSE_ISSUE_ON_MERGE=true  r allow 'gh pr edit 100 -b "Closes #1"'
genv=$(mktemp); printf '%s\n' "HARNESS_GITHUB_CLOSE_ISSUE_ON_MERGE=false" > "$genv"
HARNESS_GUARD_ENV=$genv r deny 'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1"'
HARNESS_GUARD_ENV=$genv HARNESS_GITHUB_CLOSE_ISSUE_ON_MERGE=true r deny 'gh pr edit 100 -b "Closes #1"'   # guard.env false is final
printf '%s\n' "HARNESS_GITHUB_CLOSE_ISSUE_ON_MERGE='true'" > "$genv"
HARNESS_GUARD_ENV=$genv r allow 'gh pr edit 100 -b "Closes #1"'
HARNESS_GUARD_ENV=$genv HARNESS_GITHUB_CLOSE_ISSUE_ON_MERGE=false r deny 'gh pr edit 100 -b "Closes #1"'  # the environment may switch it off
rm -f "$genv"
# base and head
r deny  'gh pr create -R o/r -H feat-x -B feat-y -t x -b "Closes #1"'
r deny  'gh pr create -R o/r -H feat-x -t x -b "Closes #1"'                     # no -B
r deny  'gh pr create -R o/r -H feat-x -B "$BASE" -t x -b "Closes #1"'
r deny  'gh pr create -R o/r -H x-sub-01-y -B main -t x -b "Closes #1"'
r deny  'gh pr create -R o/r -H me:feat-x -B main -t x -b "Closes #1"'
r deny  'gh pr create -R o/r -H "$BR" -B main -t x -b "Closes #1"'
r deny  'gh pr create -R "$R" -H feat-x -B main -t x -b "Closes #1"'
r deny  'gh pr create -B main -t x -b "Closes #1"'                             # head unknown (not a repo)
# the issues
r deny  'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #2"'            # agent-drafted
r deny  'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #3"'            # human
r deny  'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #9"'            # unknown
r deny  'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1, closes #3"'
r deny  'gh pr create -R o/r -H feat-x -B main -t x -b "Closes o/r#1"'
r deny  'gh pr create -R o/r -H feat-x -B main -t x -b "Closes https://github.com/o/r/issues/1"'
r deny  'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1 fixes #11 fixes #12 fixes #13 fixes #14 fixes #15 fixes #16 fixes #17 fixes #18 fixes #19 fixes #20"'
# bypass attempts
r deny  'gh "pr" create -R o/r -H feat-x -B main -t x -b "Closes #1"'
r deny  'gh pr "create" -R o/r -H feat-x -B main -t x -b "Closes #1"'
r deny  'g\h pr create -R o/r -H feat-x -B main -t x -b "Closes #1"'
r deny  'p=pr; gh $p create -R o/r -H feat-x -B main -t x -b "Closes #1"'
r deny  'v=create; gh pr $v -R o/r -H feat-x -B main -t x -b "Closes #1"'
r deny  'GH_REPO=o/r gh pr create -H feat-x -B main -t x -b "Closes #1"'
r deny  'echo "Closes #1"; gh pr create -R o/r -H feat-x -B main -t x'
r deny  'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1" && git commit -m "Fixes #1"'
r deny  'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1" && git commit -m "wip"'
r deny  'gh pr merge 100 -b "Closes #1"'
r deny  'gh api repos/o/r/issues/1/comments -f body="Fixes #1"'
r deny  'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1" && gh pr create -R o/r -H g -B feat-y -t y'
r deny  'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1" && gh pr edit 110 -b "Closes #1"'
r deny  'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1" && gh pr merge 100'
r ask   'gh pr create -R o/r -H feat-x -B main -t x -b "done; closes #1"'      # a quoted ; is body text for 41 (clauses cut on unquoted ; & | only); 60's own cut is not quote-aware and asks
r deny  'gh pr create -R o/r -H feat-x -B main -t x -b done; closes #1'        # unquoted: the ref is another command
r deny  $'gh pr create -R o/r -H feat-x -B main -t x -b ok\ngh pr edit 110 -b "Closes #1"'
r deny  'sh -c "gh \"pr\" create -R o/r -H feat-x -B main -t x -b \"Closes #1\""'
r pass  'gh pr create -R o/r -H feat-x -B main -t x -b "part of #3" --web'
# hardening (review of part 01): every probe below allowed before; each must deny
# C1 clauses are cut on unquoted ; & | only (a quoted separator hides nothing), and a repeated
# -B/-H/-R/-t/-b/-F denies (gh keeps the last one)
r deny  'gh pr create -R o/r -H feat-x -B main -b "Closes #1" -t ";" -B feat-y'
r deny  "gh pr create -R o/r -H feat-x -B main -b \"Closes #1\" -t ';' -R victim/repo"
r deny  'gh pr create -R o/r -H feat-x -B main -b "Closes #1" -t "|" -H x-sub-01-y'
r deny  'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1" -t";" -B feat-y'
r deny  'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1" --title=";" -B feat-y'
r deny  'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1" -t "a;"'
r deny  'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1" -t "#" -B feat-y'
r deny  'gh pr create -R o/r -H feat-x -B main -B feat-y -t x -b "Closes #1"'
r deny  $'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1" -B main\t-B feat-y'
r deny  'gh pr edit 100 -b "Closes #1" -t ";" -R o/victim'
r deny  'gh pr edit 100 -b "Closes #1" -t ";" -B feat-y'
r deny  'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1" -- -B feat-y'
r deny  'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1" -t "x"'           # repeated -t
r deny  'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1" --frobnicate'     # unknown flag
r deny  'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1" -B=main'          # repeated -B, even with the same value
r deny  'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1" 100'              # create takes no positional
r deny  'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1 (#2)" -l {a,b}'     # unquoted brace expansion
r deny  'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1" -l *'             # unquoted glob
r allow 'gh pr create -R o/r -H feat-x -B=main -t x -b "Closes #1"'                  # pflag reads -B=main as main
r ask   'gh pr create -R o/r -H feat-x -B main -t "x; y | z" -b "Closes #1 & more" -l agent-worked 2>/dev/null'   # 41 passes it, 60 asks (see above)
r allow 'gh pr create -R o/r -H feat-x -B main -t "x" -b "Closes #1 and more" -l agent-worked 2>/dev/null'
# C2 a multi-line command: the next line's words would read as flags
r deny  $'gh pr create -R o/victim -H feat-x -B main -t x -b "Closes #1"\necho -R o/worked'
r deny  $'gh pr create -R o/r -H feat-x -B feat-y -t x -b "Closes #1"\necho -B main'
r deny  $'gh pr edit -b "Closes #1"\necho 100'
r deny  $'gh pr edit 100 -b "Closes #1\nmore text"'
T_CWD=$rpd tr 'one line and pass a long body with -F file' $'gh pr edit -b "Closes #1"\necho 100'
# C3 clusters of short flags expand the way gh reads them
r deny  'gh pr create -R o/r -H feat-x -B main -dB feat-y -t x -b "Closes #1"'
r deny  'gh pr create -R o/r -H feat-x -B main -wB feat-y -t x -b "Closes #1"'
r deny  'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1" -wB feat-y'
r deny  'gh pr create -R o/r -H feat-x -B main -dR victim/repo -t x -b "Closes #1"'
r deny  'gh pr create -R o/r -B main -H feat-x -dH x-sub-01-y -t x -b "Closes #1"'
r deny  'gh pr create -R o/r -H feat-x -B main -dxB feat-y -t x -b "Closes #1"'      # unknown flag in a cluster
r allow 'gh pr create -R o/r -H feat-x -dB main -t x -b "Closes #1"'                 # -d -B main
# C4 cd/pushd/popd: the lookups read the hook's cwd, not where gh runs
r deny  'cd /tmp/other && gh pr create -H feat-x -B main -t x -b "Closes #1"'
r deny  'pushd /tmp/other; gh pr create -H feat-x -B main -t x -b "Closes #1"'
r deny  '( cd /tmp/other; gh pr create -H feat-x -B main -t x -b "Closes #1" )'
r deny  '(cd /tmp/other && gh pr edit 100 -b "Closes #1")'
r deny  'popd && gh pr edit 100 -b "Closes #1"'
T_CWD=$rpd tr 'without cd' 'cd /tmp/other && gh pr create -H feat-x -B main -t x -b "Closes #1"'
# C5 GH_REPO / GH_HOST set any way
r deny  'printf -v GH_REPO o/victim; export GH_REPO; gh pr create -H feat-x -B main -t x -b "Closes #1"'
r deny  'export "GH_REPO=o/victim"; gh pr create -H feat-x -B main -t x -b "Closes #1"'
r deny  'export GH_REPO\=o/victim; gh pr create -H feat-x -B main -t x -b "Closes #1"'
r deny  'GH_HOST=ghe.example.com gh pr create -H feat-x -B main -t x -b "Closes #1"'
r deny  'declare -x GH_HOST=ghe.example.com; gh pr edit 100 -b "Closes #1"'
T_CWD=$rpd tr 'GH_REPO/GH_HOST hide the repository' 'export "GH_REPO=o/victim"; gh pr create -H feat-x -B main -t x -b "Closes #1"'
# S4 only a top-level gh clause qualifies: never inside sh -c, eval, xargs, $(…) or backticks
r deny  'eval '\''gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1"'\'''
r deny  'bash -c '\''gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1"'\'''
r deny  'sh -c "gh pr create -R o/r -H feat-x -B main -t x -b \"Closes #1\" -B feat-y"'
r deny  'sh -c "gh pr create -R o/r -H feat-x -B main -t x -b \"Closes #1\" -R o/victim"'
r deny  'echo 100 | xargs gh pr edit -b "Closes #1"'
r deny  'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1" | xargs gh pr edit 110 -B main'
r deny  'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1 $(gh pr edit 110 -B main)"'
r deny  'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1 `gh pr edit 110 -B main`"'
r deny  'x=$(gh pr edit 100 -b "Closes #1")'
r deny  'env gh pr edit 100 -b "Closes #1"'
r deny  'gh pr create -R o/r -H feat-x -B main -t x -F - <<<"Closes #3"'
r deny  'gh pr create -R o/r -H feat-x -B main -t x --body-file <(echo "Closes #3")'
r deny  'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1" & gh pr edit 110 -B main'
r deny  'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1"; gh pr view 100'
r deny  'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1"; echo done'
T_CWD=$rpd tr 'inside bash cannot be checked; run it as its own top-level command' 'bash -c '\''gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1"'\'''
# W3a -R must name the cwd checkout's github.com origin (GIT_STUB_REMOTE; default https://github.com/o/r.git)
GIT_STUB_REMOTE=git@github.com:o/r.git r allow 'gh pr edit 100 -b "Closes #1"'         # scp-style ssh remote
r deny  'gh pr create -R other/repo -H feat-x -B main -t x -b "Closes #1"'
r deny  'gh pr edit 100 -R other/repo -b "Closes #1"'
r allow 'gh pr create -R O/R -H feat-x -B main -t x -b "Closes #1"'                   # owner/repo compare case-insensitively
r allow 'gh pr create -R github.com/o/r -H feat-x -B main -t x -b "Closes #1"'
r deny  'gh pr create -R ghe.example.com/o/r -H feat-x -B main -t x -b "Closes #1"'
GIT_STUB_REMOTE=https://github.com/o/r r allow 'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1"'
GIT_STUB_REMOTE=ssh://git@ssh.github.com:443/o/r.git r allow 'gh pr edit 100 -b "Closes #1"'
GIT_STUB_REMOTE=git@github.com:o/victim.git r deny 'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1"'
GIT_STUB_REMOTE=git@gitlab.example.com:o/r.git r deny 'gh pr edit 100 -b "Closes #1"'     # not github.com
GIT_STUB_REMOTE=none r deny 'gh pr edit 100 -b "Closes #1"'                               # no origin
T_CWD=$rpd tr 'is not this checkout.s origin \(o/r\)' 'gh pr create -R other/repo -H feat-x -B main -t x -b "Closes #1"'
# W3b the base is the repository's defaultBranchRef (rows with GH_STUB_DEFAULT_BRANCH above)
T_CWD=$rpd tr 'not the default branch main' 'gh pr create -R o/r -H feat-x -B master -t x -b "Closes #1"'
# W5 a keyword or ref hidden by quotes or escapes never qualifies
r deny  'gh pr create -R o/r -H feat-x -B main -t x -b Closes\ \#1'
r deny  'gh pr create -R o/r -H feat-x -B main -t x -b Closes\ \#1 -B feat-y'
r deny  'gh pr create -R o/r -H feat-x -B main -t x -b "Closes "#3'
r deny  'gh pr create -R o/r -H feat-x -B main -t x -b Clo"ses #3"'
r deny  'git commit -m Fixes\ \#1'
T_CWD=$rpd tr 'written with quotes or escapes' 'gh pr create -R o/r -H feat-x -B main -t x -b "Closes "#3'
# subagent: the create behaves as on the main thread; the edit follows 60's label gate
T_AGENT=a1 r allow 'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1"'
T_AGENT=a1 r allow 'gh pr edit 100 -b "Closes #1"'
T_AGENT=a1 r deny  'gh pr create -R o/r -H feat-x -B feat-y -t x -b "Closes #1"'
T_AGENT=a1 r deny  'gh pr merge 100 -b "Closes #1"'
# reasons
T_CWD=$rpd tr 'pass -B <default branch> explicitly' 'gh pr create -R o/r -H feat-x -t x -b "Closes #1"'
T_CWD=$rpd tr 'not labelled agent-worked' 'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #3"'
T_CWD=$rpd tr 'sub PR .* main PR to the default branch instead' 'gh pr edit 110 -b "Closes #1"'
T_CWD=$rpd tr 'only a bare #N' 'gh pr create -R o/r -H feat-x -B main -t x -b "Closes o/r#1"'
T_CWD=$rpd tr 'runs echo next to gh pr create\|edit; run gh pr create\|edit as its own command' 'echo "Closes #1"; gh pr create -R o/r -H feat-x -B main -t x'
T_CWD=$rpd tr 'outside the -t/-b text of gh pr create\|edit' 'gh pr create -R o/r -H feat-x -B main -t x -b ok -l "Closes #1"'
HARNESS_GITHUB_CLOSE_ISSUE_ON_MERGE=false T_CWD=$rpd tr 'close_issue_on_merge is off; mention #N instead' 'gh pr edit 100 -b "Closes #1"'
# tracker jira or an invalid declared value: the deny is unchanged
decl '[repo]' 'tracker = "jira"'
r deny  'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1"'
r deny  'gh pr edit 100 -b "Closes #1"'
decl '[repo]' 'tracker = "gitlab"'
r deny  'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1"'
decl '[owns]' 'domains = ["scm"]'
r pass  'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1"'           # part 02: undeclared tracker on github.com resolves to github-issues; 60 is owned
r deny  'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #3"'
decl '[repo]' 'tracker = "github-issues"' '[owns]' 'domains = ["scm"]'
r pass  'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1"'           # 41 allows, 60 is owned: the provider decides
r deny  'gh pr create -R o/r -H feat-x -B feat-y -t x -b "Closes #1"'          # owns scm keeps 41 deciding
decl '[repo]' 'tracker = "github-issues"' '[owns]' 'domains = ["tracker"]'
r allow 'gh pr create -R o/r -H feat-x -B feat-y -t x -b "Closes #2"'          # owns tracker: 41 yields
# ---- an undeclared repository's tracker (issue 80, part 02) ----------------------------
# resolved like work-ticket's rf_tracker: .harness.toml [repo] tracker > the first
# ticket_workflow.trackers entry (HARNESS_TICKET_TRACKERS) whose match ERE hits the origin remote
# id > the host (github.com -> github-issues). The allow path still needs a github.com origin
# (part 01's origin check), so a config entry naming github-issues on another host denies.
decl
r allow 'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1"'            # no decl + github.com + no trackers: host
r allow 'gh pr edit 100 -b "Closes #1"'
g allow 'gh pr edit 100 -b "Closes #1"'
GIT_STUB_REMOTE=git@github.com:o/r.git r allow 'gh pr edit 100 -b "Closes #1"'
HARNESS_TICKET_TRACKERS='[]' r allow 'gh pr edit 100 -b "Closes #1"'
HARNESS_TICKET_TRACKERS='' r allow 'gh pr edit 100 -b "Closes #1"'              # empty = no entries
r deny  'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #3"'            # the other part-01 gates still apply
r deny  'gh pr create -R o/r -H feat-x -B feat-y -t x -b "Closes #1"'
r deny  'git commit -m "Fixes #1"'
# a config entry decides: the first match wins, case-insensitively
HARNESS_TICKET_TRACKERS='[{"match":"^github\\.com/o/","tracker":"jira","project":"PROJ"}]' r deny 'gh pr edit 100 -b "Closes #1"'
HARNESS_TICKET_TRACKERS='[{"match":"^GitHub\\.com/O/R$","tracker":"jira"}]' r deny 'gh pr edit 100 -b "Closes #1"'
HARNESS_TICKET_TRACKERS='[{"match":"^github\\.com/other/","tracker":"jira"}]' r allow 'gh pr edit 100 -b "Closes #1"'   # no match: host
HARNESS_TICKET_TRACKERS='[{"match":"^github\\.com/o/r$","tracker":"github-issues"},{"match":"^github\\.com/","tracker":"jira"}]' r allow 'gh pr edit 100 -b "Closes #1"'
HARNESS_TICKET_TRACKERS='[{"match":"^github\\.com/","tracker":"jira"},{"match":"^github\\.com/o/r$","tracker":"github-issues"}]' r deny 'gh pr edit 100 -b "Closes #1"'
HARNESS_TICKET_TRACKERS='[{"match":"o/r","tracker":"trello"}]' r deny 'gh pr edit 100 -b "Closes #1"'                     # matching entry, invalid tracker
HARNESS_TICKET_TRACKERS='[{"tracker":"jira"},{"match":"o/r","tracker":"github-issues"}]' r deny 'gh pr edit 100 -b "Closes #1"'    # no match: invalid entry (review W2)
HARNESS_TICKET_TRACKERS='[{"match":"","tracker":"jira"}]' r deny 'gh pr edit 100 -b "Closes #1"'
# an invalid ERE denies (stricter than rf_tracker, which skips it: a mistyped jira entry must not allow; review W2)
HARNESS_TICKET_TRACKERS='[{"match":"(","tracker":"jira"}]' r deny 'gh pr edit 100 -b "Closes #1"'
HARNESS_TICKET_TRACKERS='[{"match":"(","tracker":"github-issues"},{"match":"o/r","tracker":"jira"}]' r deny 'gh pr edit 100 -b "Closes #1"'
HARNESS_TICKET_TRACKERS='[{"match":"^github\\.com/o/r$","tracker":"github-issues"},{"match":"(","tracker":"jira"}]' r allow 'gh pr edit 100 -b "Closes #1"'   # an earlier match decides first
HARNESS_TICKET_TRACKERS='[{"match":"(","tracker":"jira"}]' T_CWD=$rpd tr 'match is empty or not a valid ERE; fix it in harness.toml \(harness doctor' 'gh pr edit 100 -b "Closes #1"'
# a NUL inside match or tracker would shift the fields (review S1); several JSON documents in one value (review S2)
HARNESS_TICKET_TRACKERS='[{"match":"^x\u0000github-issues\u0000.*","tracker":"jira"}]' r deny 'gh pr edit 100 -b "Closes #1"'
HARNESS_TICKET_TRACKERS='[{"match":"o/r","tracker":"github-issues\u0000"}]' r deny 'gh pr edit 100 -b "Closes #1"'
HARNESS_TICKET_TRACKERS='[{"match":"o/r","tracker":7}]' r deny 'gh pr edit 100 -b "Closes #1"'
HARNESS_TICKET_TRACKERS='[] [{"match":"o/r","tracker":"jira"}]' r deny 'gh pr edit 100 -b "Closes #1"'
HARNESS_TICKET_TRACKERS='[{"match":"o/r","tracker":"github-issues"}] []' r deny 'gh pr edit 100 -b "Closes #1"'
HARNESS_TICKET_TRACKERS='[{"match":"o/r","tracker":"github-issues"}]' r allow 'gh pr edit 100 -b "Closes #1"'
# a malformed HARNESS_TICKET_TRACKERS denies
HARNESS_TICKET_TRACKERS='not json' r deny 'gh pr edit 100 -b "Closes #1"'
HARNESS_TICKET_TRACKERS='{"match":"o/r","tracker":"github-issues"}' r deny 'gh pr edit 100 -b "Closes #1"'
HARNESS_TICKET_TRACKERS='[{"match":"o/r","tracker":"github-issues"}' r deny 'gh pr edit 100 -b "Closes #1"'
HARNESS_TICKET_TRACKERS='[1]' r deny 'gh pr edit 100 -b "Closes #1"'
HARNESS_TICKET_TRACKERS='not json' T_CWD=$rpd tr 'ticket_workflow.trackers \(HARNESS_TICKET_TRACKERS\) is not a JSON list' 'gh pr edit 100 -b "Closes #1"'
# no remote, git failing or hanging, another host: deny
GIT_STUB_REMOTE=none r deny 'gh pr edit 100 -b "Closes #1"'
GUARD_GIT=false r deny 'gh pr edit 100 -b "Closes #1"'
GIT_STUB_REMOTE=hang r deny 'gh pr edit 100 -b "Closes #1"'                     # the 5 s git timeout fires
GIT_STUB_REMOTE=none T_CWD=$rpd tr 'has no origin remote \(or git did not answer\)' 'gh pr edit 100 -b "Closes #1"'
GIT_STUB_REMOTE=none HARNESS_TICKET_TRACKERS='[{"match":".*","tracker":"github-issues"}]' r deny 'gh pr edit 100 -b "Closes #1"'   # no id: config not consulted
GIT_STUB_REMOTE=git@gitlab.example.com:o/r.git r deny 'gh pr edit 100 -b "Closes #1"'
GIT_STUB_REMOTE=git@gitlab.example.com:o/r.git T_CWD=$rpd tr 'no GitHub Issues tracker for gitlab.example.com/o/r' 'gh pr edit 100 -b "Closes #1"'
GIT_STUB_REMOTE=git@gitlab.example.com:o/r.git HARNESS_TICKET_TRACKERS='[{"match":"^gitlab\\.example\\.com/","tracker":"github-issues"}]' r deny 'gh pr edit 100 -b "Closes #1"'
GIT_STUB_REMOTE=git@gitlab.example.com:o/r.git HARNESS_TICKET_TRACKERS='[{"match":"^gitlab\\.example\\.com/","tracker":"github-issues"}]' T_CWD=$rpd tr 'covers github.com repositories only' 'gh pr edit 100 -b "Closes #1"'
GIT_STUB_REMOTE=https://ghe.example.com/o/r.git HARNESS_TICKET_TRACKERS='[{"match":"^ghe\\.example\\.com/","tracker":"github-issues"}]' r deny 'gh pr edit 100 -b "Closes #1"'
HARNESS_TICKET_TRACKERS='[{"match":"^github\\.com/o/","tracker":"jira"}]' T_CWD=$rpd tr 'first ticket_workflow.trackers entry matching github.com/o/r names a tracker other than github-issues' 'gh pr edit 100 -b "Closes #1"'
# the rendered guard.env carries the trackers (single-quoted one-line JSON)
genv=$(mktemp); printf '%s\n' "HARNESS_TICKET_TRACKERS='[{\"match\":\"^github\\\\.com/o/\",\"tracker\":\"jira\"}]'" > "$genv"
HARNESS_GUARD_ENV=$genv r deny 'gh pr edit 100 -b "Closes #1"'
# the environment cannot undo guard.env's list: both are checked (review W1)
HARNESS_GUARD_ENV=$genv HARNESS_TICKET_TRACKERS='[]' r deny 'gh pr edit 100 -b "Closes #1"'
HARNESS_GUARD_ENV=$genv HARNESS_TICKET_TRACKERS='' r deny 'gh pr edit 100 -b "Closes #1"'
HARNESS_GUARD_ENV=$genv HARNESS_TICKET_TRACKERS='[{"match":"^github\\.com/o/r$","tracker":"github-issues"}]' r deny 'gh pr edit 100 -b "Closes #1"'
HN_GENV_TICKET_TRACKERS='[{"match":"o/r","tracker":"jira"}]' r allow 'gh pr edit 100 -b "Closes #1"'   # engine.sh initialises it: not injectable from the environment
printf '%s\n' "HARNESS_TICKET_TRACKERS='[{\"match\":\"^github\\\\.com/o/r\$\",\"tracker\":\"github-issues\"}]'" > "$genv"
HARNESS_GUARD_ENV=$genv r allow 'gh pr edit 100 -b "Closes #1"'
HARNESS_GUARD_ENV=$genv HARNESS_TICKET_TRACKERS='[{"match":"o/r","tracker":"jira"}]' r deny 'gh pr edit 100 -b "Closes #1"'   # the environment may only add a deny
HARNESS_GUARD_ENV=$genv HARNESS_TICKET_TRACKERS='[]' r allow 'gh pr edit 100 -b "Closes #1"'
printf '%s\n' "HARNESS_TICKET_TRACKERS='not json'" > "$genv"
HARNESS_GUARD_ENV=$genv HARNESS_TICKET_TRACKERS='[]' r deny 'gh pr edit 100 -b "Closes #1"'                # a malformed guard.env list denies
rm -f "$genv"
# the remote id must be exactly github.com/<owner>/<repo> (review S3)
GIT_STUB_REMOTE=https://github.com/o/r.git.git r deny 'gh pr edit 100 -b "Closes #1"'
GIT_STUB_REMOTE=https://github.com/o/r/extra r deny 'gh pr edit 100 -b "Closes #1"'
GIT_STUB_REMOTE=https://github.com/o/r.git.git T_CWD=$rpd tr 'no github.com/<owner>/<repo> origin remote' 'gh pr edit 100 -b "Closes #1"'
GIT_STUB_REMOTE=https://github.com/O/R.git r allow 'gh pr edit 100 -b "Closes #1"'               # owner/repo compare case-insensitively
# a .harness.toml tracker the guard cannot read denies; a [repo] table without one falls through (review C1)
decl '[repo]' 'tracker = "jira"  # our Jira'
r deny  'gh pr edit 100 -b "Closes #1"'
T_CWD=$rpd tr 'declares a tracker the guard cannot read .* write one plain line tracker = "github-issues" or tracker = "jira" under \[repo\], without a trailing comment' 'gh pr edit 100 -b "Closes #1"'
decl 'repo.tracker = "jira"'
r deny  'gh pr edit 100 -b "Closes #1"'
decl 'repo . "tracker" = "jira"'
r deny  'gh pr edit 100 -b "Closes #1"'
decl 'repo = { tracker = "jira" }'
r deny  'gh pr edit 100 -b "Closes #1"'
decl '[repo] # tracker' 'tracker = "jira"'
r deny  'gh pr edit 100 -b "Closes #1"'
decl '[repo]' '"tracker" = "jira"'
r deny  'gh pr edit 100 -b "Closes #1"'
decl '[repo]' "tracker = 'jira' # x"
r deny  'gh pr edit 100 -b "Closes #1"'
decl '[repo]' 'tracker = """jira"""'
r deny  'gh pr edit 100 -b "Closes #1"'
decl '[repo]' 'tracker = ["jira"]'
r deny  'gh pr edit 100 -b "Closes #1"'
decl '[repo]' 'tracker = "github-issues"' 'tracker = "jira"'
r deny  'gh pr edit 100 -b "Closes #1"'                                         # more than one tracker line
decl '[repo]' 'tracker = "github-issues"  # ours'
r deny  'gh pr edit 100 -b "Closes #1"'                                         # unreadable even when it names github-issues
decl '[other]' 'tracker = "jira"'
r deny  'gh pr edit 100 -b "Closes #1"'                                         # a tracker line outside [repo]: conservative
decl '[repo]' 'project = "PROJ"'
r allow 'gh pr edit 100 -b "Closes #1"'                                         # [repo] without a tracker: config and host decide
decl '[repo] # the declaration' 'project = "PROJ"'
r allow 'gh pr edit 100 -b "Closes #1"'
decl '[owns]' 'components = []' '# tracker = "jira"'
r allow 'gh pr edit 100 -b "Closes #1"'                                         # a commented-out line declares nothing
decl '[repo]' "tracker = 'github-issues'"
r allow 'gh pr edit 100 -b "Closes #1"'                                         # single-quoted plain line is readable
big=(); _bi=0; while [ "$_bi" -lt 401 ]; do big+=("# filler $_bi"); _bi=$((_bi+1)); done
decl '[repo]' 'tracker = "jira"' "${big[@]}"
r deny  'gh pr edit 100 -b "Closes #1"'                                         # a file the engine ignores (over 400 lines) still denies
decl '[repo]' 'tracker = "github-issues"' "${big[@]}"
r deny  'gh pr edit 100 -b "Closes #1"'
unset big _bi
decl
# a declaration beats config and host
decl '[repo]' 'tracker = "jira"'
r deny  'gh pr edit 100 -b "Closes #1"'                                         # jira declared on github.com
HARNESS_TICKET_TRACKERS='[{"match":"o/r","tracker":"github-issues"}]' r deny 'gh pr edit 100 -b "Closes #1"'
T_CWD=$rpd tr 'declares a \[repo\] tracker other than "github-issues"' 'gh pr edit 100 -b "Closes #1"'
decl '[repo]' 'tracker = "gitlab"'
HARNESS_TICKET_TRACKERS='[{"match":"o/r","tracker":"github-issues"}]' r deny 'gh pr edit 100 -b "Closes #1"'   # an invalid declared value
decl '[repo]' 'tracker = "github-issues"'
HARNESS_TICKET_TRACKERS='[{"match":"o/r","tracker":"jira"}]' r allow 'gh pr edit 100 -b "Closes #1"'
HARNESS_TICKET_TRACKERS='not json' r allow 'gh pr edit 100 -b "Closes #1"'      # declared: the config is never read
decl
# lookups: no git or gh call from 41 without a closing keyword; exactly one origin read with one
lk() {  # WANT-REMOTE-READS WANT-GH-API-CALLS (after the row just run)
  local nr na
  nr=$(grep -c '^remote get-url origin$' "$gsl" 2>/dev/null | command tr -d ' '); na=$(grep -c '^api ' "$hsl" 2>/dev/null | command tr -d ' ')
  if [ "${nr:-0}" = "$1" ] && [ "${na:-0}" = "$2" ]; then pass=$((pass+1)); echo "PASS lookups remote=$nr api=$na"
  else fail=$((fail+1)); echo "FAIL lookups: remote get-url origin x${nr:-0} (want $1), gh api x${na:-0} (want $2)"; fi
  : > "$gsl"; : > "$hsl"
}
gsl=$(mktemp); hsl=$(mktemp)
GIT_STUB_LOG=$gsl GH_STUB_LOG=$hsl r pass 'gh pr view 100 --json title'; lk 0 0
GIT_STUB_LOG=$gsl GH_STUB_LOG=$hsl r allow 'gh pr edit 100 -b "part of #1"'; lk 0 0
GIT_STUB_LOG=$gsl GH_STUB_LOG=$hsl r pass 'git commit -m "see #1"'; lk 0 0
GIT_STUB_LOG=$gsl GH_STUB_LOG=$hsl r allow 'gh pr edit 100 -b "Closes #1"'; lk 1 1
decl '[repo]' 'tracker = "jira"'
GIT_STUB_LOG=$gsl GH_STUB_LOG=$hsl r deny 'gh pr edit 100 -b "Closes #1"'; lk 0 0      # a declared jira denies before any lookup
decl 'repo.tracker = "jira"'
GIT_STUB_LOG=$gsl GH_STUB_LOG=$hsl r deny 'gh pr edit 100 -b "Closes #1"'; lk 0 0      # so does an unreadable one
decl
rm -f "$gsl" "$hsl"
# 41 inlines rf_remote_id's normalisation (ticket-workflow repo-facts.sh) between rf_remote_norm
# markers: the copies must match byte for byte, so this bundle's own run catches drift (review S5;
# bundles/ticket-workflow/tests/run.sh checks the same)
rfn() { sed -n '/^# >>> rf_remote_norm/,/^# <<< rf_remote_norm$/p' "$1"; }
_hub=$(cd "$GUARD_TESTS_DIR/../../.." && pwd)
_rf="$_hub/ticket-workflow/skills/work-ticket/scripts/lib/repo-facts.sh"; _g41="$_hub/github/guard.d/41-github-closing.sh"
if [ -f "$_rf" ] && [ -n "$(rfn "$_rf")" ] && [ "$(rfn "$_rf")" = "$(rfn "$_g41")" ]; then
  pass=$((pass+1)); echo "PASS rf_remote_norm: 41-github-closing.sh matches repo-facts.sh"
else
  fail=$((fail+1)); echo "FAIL rf_remote_norm: the block in $_g41 differs from $_rf (or one is missing); copy it over from repo-facts.sh"
fi
unset _hub _rf _g41
# ---- gh stack (the gh-stack extension, #86): merge is a human decision, link is label-gated ----
# merge: main thread asks, a subagent is denied (any spelling)
t ask   'gh stack merge 42 --yes'
t ask   'gh stack merge'
T_AGENT=a1 t deny 'gh stack merge 42 --yes'
T_AGENT=a1 t deny 'gh stack merge --yes --squash'
tr 'human decision' 'gh stack merge 42 --yes'
T_AGENT=a1 tr 'hand the command back to the main thread' 'gh stack merge 42 --yes'
# gtr (lib.sh): tr in the real gh directory of `g` (the stacks and PR lookups cd into the cwd)
# merge label gate (#106, agent-worked since #112): the main thread merges agent-worked -sub- parts of a ticket-branch stack
# without a second confirmation (stub stacks: 30 feat-x [110 merged, 111], 31 feat-x [110 111 112(bug)],
# 32 main [210], 33 feat-x [110 120(fork)], 34 feat-x [110 100(main PR)])
g allow 'gh stack merge 30 --yes'                                    # stack number, merged part skipped
g allow 'gh stack merge 30 -y --squash'
g allow 'gh stack merge 30 --merge-method rebase'
g allow 'gh stack merge 30 --merge-method=merge --yes'
g allow 'GH_STACK_NO_UPDATE_NOTIFIER=1 gh stack merge 30 --yes'
g allow 'gh stack merge 111 --yes'                                   # PR number: range up to 111 skips 112
g ask   'gh stack merge 110'                                       # 110 already merged: nothing open in the range
GIT_STUB_BRANCH=feat-x-sub-01-schema g allow 'gh stack merge --yes'  # current branch's stack (30)
gtr 'agent-worked' 'gh stack merge 30 --yes'
g ask   'gh stack merge 31 --yes'                                    # 112 is not agent-worked
g ask   'gh stack merge 112 --yes'
g ask   'gh stack merge --yes'                                       # current branch 111 -> stack 31, whole
g ask   'gh stack merge 32 --yes'                                    # default-branch base
g ask   'gh stack merge 33 --yes'                                    # fork PR
g ask   'gh stack merge 34 --yes'                                    # main PR is not a -sub- part
g ask   'gh stack merge 120'
g ask   'gh stack merge 42 --yes'                                    # neither stack nor PR in a stack
gtr 'not labelled agent-worked' 'gh stack merge 31 --yes'
gtr 'default branch' 'gh stack merge 32 --yes'
gtr 'no open PR' 'gh stack merge 110'
gtr 'human decision' 'gh stack merge 31 --yes'
# bypass attempts: every other form keeps the ask (subagents stay denied)
g ask   'gh stack merge 30 31 --yes'
g ask   'gh stack merge 30 --admin'
g ask   'gh stack merge 30 --merge-method fast'
g ask   'gh stack merge "30" --yes'
g ask   "gh stack merge '30'"
g ask   'gh "stack" merge 30'
g ask   'gh stack "merge" 30'
g ask   'gh -R o/r stack merge 30'
g ask   'gh stack -R o/r merge 30'
g ask   'GH_REPO=o/r gh stack merge 30'
g ask   'cd sub && gh stack merge 30'
g ask   'gh stack merge 30 && gh stack merge 32'
g ask   'gh stack merge 30; gh pr list'
g ask   'gh stack view && gh stack merge 30'
g ask   'sh -c "gh stack merge 30"'
g ask   'echo 30 | xargs gh stack merge'
g ask   'gh stack merge $N'
g ask   'gh stack merge $(echo 30)'
g ask   'gh extension exec stack merge 30'
g ask   'gh-stack merge 30'
g ask   'gs merge 30'
g ask   'gh stack merge 30 > /tmp/x'
g ask   $'gh stack merge\n30'                                       # review C1: line 1 merges the current stack
g ask   $'gh stack merge --yes\n30'
g ask   $'gh stack merge\n111'
g ask   $'GH_STACK_NO_UPDATE_NOTIFIER=1 gh stack merge\n30'
g ask   $'gh stack merge 30\r'
gtr 'more than one line' $'gh stack merge\n30'
GH_STUB_STACKS_FAIL=1 g ask 'gh stack merge 111'                     # only a definite 404 means "not a stack"
GH_STUB_STACKS_FAIL=1 gtr 'could not be looked up' 'gh stack merge 111'
g allow 'gh stack merge 30 # 31'                                     # bash drops the comment too
g ask   'gh stack merge feat-x-sub-02-ui'                            # a branch name
g ask   'gh stack merge https://github.com/o/r/pull/111'             # a PR URL
g ask   'gh stack merge 030'
T_AGENT=a1 g deny 'gh stack merge 30 --yes'
T_AGENT=a1 g deny 'gh stack merge 111'
WORK_TICKET_LABELED_DECISION=ask g ask 'gh stack merge 30 --yes'
# agent-worked only: a part labelled with another agent-* label keeps the ask (stub stack 35: feat-x [110, 113 agent-created])
g ask   'gh stack merge 35 --yes'
g ask   'gh stack merge 113 --yes'
gtr 'not labelled agent-worked' 'gh stack merge 35 --yes'
# gh pr merge label gate: the main thread merges an open agent-worked PR into a branch that is not the
# default branch without a second confirmation (stub: 110 -> feat-x, 111 -> feat-x-sub-01-schema,
# 115 -> release, 116 -> trunk; 100/200/210/120 -> main; 113 agent-created; 114 merged; 112 bug)
g allow 'gh pr merge 110'
g allow 'gh pr merge 110 --squash'
g allow 'gh pr merge 111 -s'
g allow 'gh pr merge 115 --merge'
g allow 'gh pr merge 115 -r'
g allow 'gh pr merge 110 -R o/r --squash'
g allow 'gh pr merge -R o/r 110'
g allow 'gh pr merge 110 --repo=o/r'
g allow 'gh -R o/r pr merge 110 --squash'
g allow 'gh pr -R o/r merge 110'
gtr 'agent-worked PR #110 into feat-x' 'gh pr merge 110 --squash'
# into the default branch: asks, whatever the labels
g ask   'gh pr merge 100 --squash'
gtr 'merges into the default branch main' 'gh pr merge 100 --squash'
GH_STUB_DEFAULT_BRANCH=trunk g ask 'gh pr merge 116 --squash'                  # the repository's own default branch
GH_STUB_DEFAULT_BRANCH=trunk gtr 'default branch trunk' 'gh pr merge 116'
GH_STUB_DEFAULT_BRANCH=trunk g allow 'gh pr merge 110'
WORK_TICKET_BASE_BRANCH_RE='^(release)$' g ask 'gh pr merge 115'                # a declared base branch
# not agent-worked, fork, closed, unreadable
g ask   'gh pr merge 112'
gtr 'not labelled agent-worked' 'gh pr merge 113'
g ask   'gh pr merge 120'
gtr 'not open' 'gh pr merge 114'
g ask   'gh pr merge 999'
GH_STUB_REPO_FAIL=1 g ask 'gh pr merge 110'
GH_STUB_REPO_FAIL=1 gtr 'default branch could not be read' 'gh pr merge 110'
# bypass attempts and unchecked flags keep the ask (subagents stay denied)
g ask   'gh pr merge 110 --admin'
g ask   'gh pr merge 110 --auto'
g ask   'gh pr merge 110 -d'
g ask   'gh pr merge 110 --delete-branch'
g ask   'gh pr merge 110 -t subject'
g ask   'gh pr merge 110 -b body'
g ask   'gh pr merge 110 -F body.md'
g ask   'gh pr merge 110 --match-head-commit abc'
g ask   'gh pr merge 110 111'
g ask   'gh pr merge'                                                         # no number: the current branch
g ask   'gh pr merge feat-x-sub-01-schema'
g ask   'gh pr merge https://github.com/o/r/pull/110'
g ask   'gh pr merge #110'
g ask   'gh pr merge 110 -R o/r -R x/y'
g ask   'gh pr merge 110 -R github.com/o/r'
g ask   'gh pr merge "110"'
g ask   'gh "pr" merge 110'
g ask   'GH_REPO=o/r gh pr merge 110'
g ask   'cd sub && gh pr merge 110'
g ask   'gh pr merge 110 && gh pr merge 100'
g ask   'gh pr view 110; gh pr merge 110'
g ask   'sh -c "gh pr merge 110"'
g ask   'echo 110 | xargs gh pr merge'
g ask   'gh pr merge $N'
g ask   'gh pr merge $(echo 110)'
g ask   'gh pr merge 110 > /tmp/x'
g ask   $'gh pr merge\n110'
g ask   $'gh pr merge 110\r'
gtr 'more than one line' $'gh pr merge\n110'
g ask   'gh pr merge 110 --squash # comment'
T_AGENT=a1 g deny 'gh pr merge 110'
T_AGENT=a1 g deny 'gh pr merge 115 --squash'
WORK_TICKET_LABELED_DECISION=ask g ask 'gh pr merge 110'
g ask   'gh pr review 110 --approve'                                         # review stays a human decision
# review C1: the guard reads the raw line; $flat would drop `2>&1` with the digits before it (o/r2 -> o/r)
g ask   'gh pr merge 110 --repo=o/r2>&1'
g ask   'gh pr merge 110 -R o/r2>&-'
g ask   'gh pr merge 110 -R o/r2<&0'
g ask   'gh pr merge 110 2>&1'
g ask   'gh stack merge 30 --yes 2>&1'
g ask   'gh pr merge 110 -R x/y'                                              # another repository: its PR is looked up there
# review W4: -R must be a plain owner/repo
g ask   'gh pr merge 110 -R o/r*'
g ask   'gh pr merge 110 -R o/{r,x}'
g ask   'gh pr merge 110 -R ~x/r'
g ask   'gh pr merge 110 -R o/../r'
g ask   'gh pr merge 110 -R o'
g allow $'gh\tpr\tmerge\t110'                                               # tabs: same words for bash and the guard
WORK_TICKET_LABEL=agent-done g ask 'gh pr merge 110'                          # the governance label override applies
# reads and navigation pass
t pass  'gh stack view --json'
t pass  'gh stack view --short'
t pass  'gh stack up'
t pass  'gh stack down 2'
t pass  'gh stack checkout 7'
t pass  'gh stack trunk'
t pass  'gh stack --help'
T_AGENT=a1 g pass 'gh stack view --json'
T_AGENT=a1 g pass 'gh stack switch'
# link: literal numbers of agent-labelled -sub- PRs onto the ticket branch
g allow 'gh stack link --base feat-x 110 111'
# the exact forms work-ticket documents (github.md §6b "Native stack (gh-stack)", SKILL.md 6b/6c)
g allow 'GH_STACK_NO_UPDATE_NOTIFIER=1 gh stack link --base feat-x 110 111'
T_AGENT=a1 g allow 'GH_STACK_NO_UPDATE_NOTIFIER=1 gh stack link --base feat-x 110 111'
g ask   'GH_STACK_NO_UPDATE_NOTIFIER=1 gh stack link --base "$BR" 110 111'   # why the text says: type the branch literally
g deny  'GH_STACK_NO_UPDATE_NOTIFIER=1 gh stack link --base feat-x 100 110 111'   # main PR stays outside
g deny  'GH_STACK_NO_UPDATE_NOTIFIER=1 gh stack link --base feat-x feat-x-sub-01-schema feat-x-sub-02-ui'
g ask   'GH_STACK_NO_UPDATE_NOTIFIER=1 gh stack link --base feat-x --open 110 111'
t pass  "gh api \"repos/o/r/stacks?pull_request=110\" --jq 'map({number, base: .base.ref, open, prs: [.pull_requests[].number]})'"
T_AGENT=a1 t pass "gh api \"repos/o/r/stacks?pull_request=110\" --jq 'map({number, base: .base.ref, open, prs: [.pull_requests[].number]})'"
t ask   "gh api \"repos/o/r/stacks?pull_request=110\" --jq '.[] | {number}'"   # a | inside --jq is split as a pipe: unbalanced quotes ask (why the text uses map())
t ask   'gh extension install github/gh-stack --pin v0.3.0'               # the user's manual step, never the agent
T_AGENT=a1 g deny 'GH_STACK_NO_UPDATE_NOTIFIER=1 gh stack merge'
g allow 'gh stack link --base=feat-x 110'
g ask   'gh stack link --base feat-x --remote origin --no-atomic 110 111'   # --remote: lookup reads gh's default repo
g allow 'gh stack link --base feat-x --no-atomic 110 111'
T_AGENT=a1 g allow 'gh stack link --base feat-x 110 111'
WORK_TICKET_LABELED_DECISION=ask g ask 'gh stack link --base feat-x 110 111'
g deny  'gh stack link --base main 110 111'
g deny  'gh stack link --base master 110'
g deny  'gh stack link 110 111'                                       # no --base: the default branch
g deny  'gh stack link --base feat-x-sub-01-schema 111'               # a part is not the base
g deny  'gh stack link --base feat-x feat-x-sub-01-schema 111'        # branch name: push + unlabelled PR
g deny  'gh stack link --base feat-x 100 110 111'                     # the main PR stays outside
g deny  'gh stack link --base feat-y 110 111'                         # another ticket's parts
g ask   'gh stack link --base feat-x 110 210'                         # unlabelled -sub- PR
g ask   'gh stack link --base feat-x 120'                             # fork PR: asks before any other check
g ask   'gh stack link --base feat-x "$N"'
g ask   'gh stack link --base "$BR" 110 111'
g ask   'gh stack link --base feat-x https://github.com/o/r/pull/110'
g ask   'gh stack link --base feat-x 110 999'                         # lookup fails
g ask   'gh stack link --base feat-x -x 110'                          # unknown flag
g ask   'gh stack link --base feat-x'                                 # no PR numbers
g ask   'GH_REPO=o/r gh stack link --base feat-x 110 111'
g ask   'gh stack link --base feat-x --open 110 111'
T_AGENT=a1 g deny 'gh stack link --base feat-x --open 110 111'
T_AGENT=a1 g ask  'gh stack link --base feat-x 110 210'
# shellcheck disable=SC2154  # ghd: the real gh directory, defined in guard/tests/lib.sh
T_CWD=$ghd/$T_REPO tr 'gh pr edit 210 --add-label agent-worked' 'gh stack link --base feat-x 110 210'
tr 'pass --base <ticket branch>' 'gh stack link 110 111'
T_CWD=$ghd/$T_REPO tr 'main PR stays outside the stack' 'gh stack link --base feat-x 100 110'
tr 'gh pr create -H BR -B BLOCKER' 'gh stack link --base feat-x feat-x-sub-01-schema'
tr 'gh pr ready N' 'gh stack link --base feat-x --open 110 111'
# push|submit|sync|…: deny on the default branch, else ask naming the alternative
GIT_STUB_BRANCH=main g deny 'gh stack push'
GIT_STUB_BRANCH=main g deny 'gh stack submit --auto'
GIT_STUB_BRANCH=master g deny 'gh stack sync'
GH_STUB_STACK=main g deny 'gh stack push'                             # trunk from gh stack view --json
GH_STUB_STACK=main GIT_STUB_BRANCH=feat-x-sub-02-ui g deny 'gh stack sync --prune'
GH_STUB_STACK=main g deny 'gh stack submit'
GIT_STUB_BRANCH=feat-x-sub-02-ui GH_STUB_STACK=feat-x g ask 'gh stack push'
GIT_STUB_BRANCH=feat-x-sub-02-ui GH_STUB_STACK=feat-x g ask 'gh stack submit --auto'
GIT_STUB_BRANCH=feat-x-sub-02-ui GH_STUB_STACK=feat-x g ask 'gh stack sync'
GIT_STUB_BRANCH=feat-x-sub-02-ui g ask 'gh stack rebase --upstack'    # no stack lookup: ask
g ask   'gh stack modify'
g ask   'gh stack unstack 7'
g ask   'gh stack add -Am "main" feat-x-sub-03-docs'                  # a message is no branch
g deny  'gh stack init feat-x-sub-01-schema'                          # trunk defaults to the default branch
g deny  'gh stack init --base main feat-x-sub-01-schema'
g deny  'gh stack init -b main feat-x-sub-01-schema'
g ask   'gh stack init --base feat-x feat-x-sub-01-schema'
g deny  'gh stack rebase main'
g ask   'gh stack submit --base "$BR"'
T_AGENT=a1 g deny 'gh stack submit --auto --open'
GIT_STUB_BRANCH=feat-x-sub-02-ui GH_STUB_STACK=feat-x g ask 'gh stack submit --auto --open'
GIT_STUB_BRANCH=feat-x-sub-02-ui GH_STUB_STACK=feat-x tr 'stk sync --stack BR' 'gh stack sync'
GIT_STUB_BRANCH=main tr 'never sit on the default branch' 'gh stack push'
# alias, unknown verbs, other extensions
g ask   'gh stack alias'
g ask   'gh stack alias gst'
g ask   'gh stack frobnicate'
g ask   'gh extension exec other-ext run'
tr 'type gh stack VERB' 'gh stack alias'
# bypass attempts: hidden or wrapped merges stay human decisions
g ask   'gh "stack" merge 42'
T_AGENT=a1 g deny 'gh "stack" merge 42'
T_AGENT=a1 g deny 'gh stack "merge" 42'
T_AGENT=a1 g deny 'gh stack $V 42'
g ask   'gh stack $V 42'
T_AGENT=a1 g deny 'sh -c "gh stack merge 42"'
T_AGENT=a1 g deny 'cd sub && gh stack merge --yes'
T_AGENT=a1 g deny 'echo 42 | xargs gh stack merge --yes'
T_AGENT=a1 g deny 'gh extension exec stack merge --yes'
T_AGENT=a1 g deny 'gh ext exec stack merge --yes'
T_AGENT=a1 g deny 'gh-stack merge --yes'
T_AGENT=a1 g deny '/home/u/.local/share/gh/extensions/gh-stack/gh-stack merge'
T_AGENT=a1 g deny 'gh-stack "merge" --yes'
T_AGENT=a1 g deny 'gh-stack $V'
T_AGENT=a1 g deny 'gh stack --yes merge'
g ask   'gh extension exec stack merge'
g ask   'gh-stack merge'
g ask   'gh-stack alias'
g deny  'gh-stack link 110 111'
g allow 'gh extension exec stack link --base feat-x 110 111'
g allow 'gh-stack link --base feat-x 110 111'
GIT_STUB_BRANCH=main g deny 'gh-stack push'
g deny  'sh -c "gh stack link --base main 110"'
g pass  'gh-stack view --json'
g pass  'echo github/gh-stack; git clone https://github.com/github/gh-stack /tmp/x'
# ---- gh stack, security review of part 1 (#86) ------------------------------------------
# C1: flags before the verb (value flags skip their value; any other flag is a human decision)
T_AGENT=a1 g deny 'gh stack -R o/r merge'
T_AGENT=a1 g deny 'gh stack --remote o/r merge --yes'
T_AGENT=a1 g deny 'gh stack -x 1 merge'
T_AGENT=a1 g deny 'gh-stack -R o/r merge'
T_AGENT=a1 g deny 'gh stack --method squash merge'
T_AGENT=a1 g deny 'gh stack --merge-method squash merge --yes'
T_AGENT=a1 g deny 'gh stack -x push'                                   # unknown pre-verb flag
g ask   'gh stack -R o/r merge'
g ask   'gh stack --method squash merge'
g ask   'gh stack -x 1 view'                                           # a flag before the verb asks even on a read
GIT_STUB_BRANCH=main g deny 'gh stack --remote o/r push'
g deny  'gh stack -b main push'
g deny  'gh stack --base main submit'
g deny  'gh stack --base=main sync'
GIT_STUB_BRANCH=feat-x-sub-02-ui GH_STUB_STACK=feat-x g ask 'gh stack --remote origin push'
g pass  'gh stack --help'
g pass  'gh stack -h'
g pass  'gh stack --version'
T_AGENT=a1 g deny 'gh stack "--yes" merge'
T_AGENT=a1 g deny 'sh -c "gh stack -R o/r merge"'
T_AGENT=a1 tr 'put the verb first' 'gh stack -x 1 view'
# C1: a non-word verb asks unless gh-stack is a path/URL argument
g ask   'gh stack /tmp/x'
T_AGENT=a1 g deny 'gh-stack ./x'
g pass  'git clone https://github.com/github/gh-stack /tmp/x'
g pass  'cp ./bin/gh-stack /tmp/x'
# W1: gh extension exec with -- or flags; any other extension is a human decision
T_AGENT=a1 g deny 'gh ext exec -- stack merge'
T_AGENT=a1 g deny 'gh ext exec -R o/r stack merge'
T_AGENT=a1 g deny 'gh extension exec other-ext run'
T_AGENT=a1 g deny 'gh extension exec "stack" merge'
g ask   'gh extension exec other-ext run'
g ask   'gh ext exec -- stack merge'
GIT_STUB_BRANCH=main g deny 'gh ext exec -- stack push'
GIT_STUB_BRANCH=main g ask  'gh extension exec "stack" push'           # hidden extension name: human decision
g allow 'gh ext exec -- stack link --base feat-x 110 111'
T_AGENT=a1 tr 'hand the command back to the main thread' 'gh extension exec other-ext run'
# W2: unknown verbs (case-sensitive, as cobra) and alias are human decisions; delete = unstack
T_AGENT=a1 g deny 'gh stack MERGE'
T_AGENT=a1 g deny 'gh stack frobnicate'
T_AGENT=a1 g deny 'gh stack alias'
T_AGENT=a1 g deny 'gh stack alias gst'
g ask   'gh stack MERGE'
GIT_STUB_BRANCH=main g deny 'gh stack delete 7'
GIT_STUB_BRANCH=feat-x-sub-02-ui g ask 'gh stack delete --local'
# W3: --remote on link asks (the lookup reads gh's default repository)
g ask   'gh stack link --base feat-x --remote upstream 110 111'
g ask   'gh stack link --base feat-x --remote=origin 110'
# W4: the real view --json schema; origin/ and refs/heads/ are stripped
GH_STUB_STACK=origin/main g deny 'gh stack push'
GH_STUB_STACK=refs/heads/master g deny 'gh stack sync'
GH_STUB_STACK=main GIT_STUB_BRANCH=feat-x-sub-02-ui g deny 'gh stack rebase'   # trunk and the bottom layer's base
g deny  'gh stack link --base origin/main 110'
g deny  'gh stack link --base refs/heads/main 110'
g deny  'gh stack init --base refs/remotes/origin/main feat-x-sub-01-schema'
GH_STUB_STACK=feat-x GIT_STUB_BRANCH=feat-x-sub-02-ui g ask 'gh stack push'
# W5: an earlier checkout of the default branch, or gh stack trunk|bottom, on the same line
GIT_STUB_BRANCH=feat-x-sub-02-ui g deny 'git checkout main && gh stack push'
GIT_STUB_BRANCH=feat-x-sub-02-ui g deny 'git switch master; gh stack sync'
GIT_STUB_BRANCH=feat-x-sub-02-ui g deny 'git -C . checkout -q main && gh stack submit'
GIT_STUB_BRANCH=feat-x-sub-02-ui g deny 'gh stack trunk && gh stack push'
GIT_STUB_BRANCH=feat-x-sub-02-ui g deny 'gh stack bottom; gh stack rebase'
GIT_STUB_BRANCH=feat-x-sub-02-ui g ask  'git checkout feat-x-sub-02-ui && gh stack push'
GIT_STUB_BRANCH=feat-x-sub-02-ui g ask  'gh stack push && git checkout main'   # after the clause: not moved yet
# W6: --open on any verb
T_AGENT=a1 g deny 'gh stack sync --open'
T_AGENT=a1 g deny 'gh stack submit --open=true'
GIT_STUB_BRANCH=feat-x-sub-02-ui GH_STUB_STACK=feat-x T_AGENT=a1 g ask 'gh stack submit --open=false'
# S1: link with an attached -bBRANCH
g allow 'gh stack link -bfeat-x 110 111'
g deny  'gh stack link -bmain 110 111'
# S2: gh.exe and gh-stack.exe
T_AGENT=a1 g deny 'gh.exe stack merge'
T_AGENT=a1 g deny 'gh-stack.exe merge --yes'
GIT_STUB_BRANCH=main g deny 'gh.exe stack push'
g allow 'gh-stack.exe link --base feat-x 110 111'
# S3: the gs wrapper from gh stack alias
T_AGENT=a1 g deny 'gs merge --yes'
g ask   'gs merge'
GIT_STUB_BRANCH=main g deny 'gs push'
g deny  'gs link 110 111'
g allow 'gs link --base feat-x 110 111'
g pass  'gs -sDEVICE=pdfwrite -o out.pdf in.ps'                       # ghostscript
g pass  'gs -q -o merge.pdf a.pdf'
# S4: link after cd/pushd, with GH_HOST= or a gh-level -R/--repo
g ask   'cd ../other && gh stack link --base feat-x 110 111'
g ask   'pushd ../other; gh stack link --base feat-x 110 111'
g ask   'GH_HOST=ghe.example.com gh stack link --base feat-x 110 111'
g ask   'gh -R o/r stack link --base feat-x 110 111'
g ask   'gh --repo=o/r stack link --base feat-x 110 111'
g deny  'cd ../other && gh stack link --base main 110'                 # a deny still wins
# gh-stack counts only at a command-word position, never as an argument of another command
g ask   'gh extension install github/gh-stack --pin v0.3.0'             # keeps the extension-install ask
T_AGENT=a1 g ask 'gh extension install github/gh-stack --pin v0.3.0'
tr 'gh team-visible action' 'gh extension install github/gh-stack --pin v0.3.0'
T_AGENT=a1 tr 'gh team-visible action' 'gh extension install github/gh-stack --pin v0.3.0'
T_AGENT=a1 g ask 'gh extension upgrade github/gh-stack --force'
T_AGENT=a1 g pass 'gh extension browse github/gh-stack --debug'
g pass  'gh repo clone github/gh-stack /tmp/x'
T_AGENT=a1 g pass 'gh repo clone github/gh-stack /tmp/x'
g pass  'gh api repos/github/gh-stack/readme'
T_AGENT=a1 g pass 'gh api repos/github/gh-stack/readme'
g pass  'echo gh-stack push'
g ask   '/home/u/.local/share/gh/extensions/gh-stack/gh-stack push'
GIT_STUB_BRANCH=main g deny '/home/u/.local/share/gh/extensions/gh-stack/gh-stack push'
GIT_STUB_BRANCH=main g deny 'sudo -E gh-stack push'
GIT_STUB_BRANCH=main g deny 'FOO=1 gh-stack sync'
GIT_STUB_BRANCH=main g deny 'git log -1 | xargs -I{} gh-stack push'
GIT_STUB_BRANCH=main g deny 'bash -c "gh-stack submit"'
GIT_STUB_BRANCH=main g deny 'if true; then gh-stack push; fi'
GIT_STUB_BRANCH=main g deny 'gs push'
g pass  'echo gs push'
# a repository that owns scm owns gh stack too
decl '[owns]' 'domains = ["scm"]'
r pass  'gh stack merge 42 --yes'
r pass  'gh stack link 110 111'
decl
