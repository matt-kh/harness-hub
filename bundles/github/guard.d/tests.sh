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
# allowed only where the repository declares [repo] tracker = "github-issues", the knob
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
# tracker jira, an invalid value or no declaration: the deny is unchanged
decl '[repo]' 'tracker = "jira"'
r deny  'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1"'
r deny  'gh pr edit 100 -b "Closes #1"'
decl '[repo]' 'tracker = "gitlab"'
r deny  'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1"'
decl '[owns]' 'domains = ["scm"]'
r deny  'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1"'
decl '[repo]' 'tracker = "github-issues"' '[owns]' 'domains = ["scm"]'
r pass  'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1"'           # 41 allows, 60 is owned: the provider decides
r deny  'gh pr create -R o/r -H feat-x -B feat-y -t x -b "Closes #1"'          # owns scm keeps 41 deciding
decl '[repo]' 'tracker = "github-issues"' '[owns]' 'domains = ["tracker"]'
r allow 'gh pr create -R o/r -H feat-x -B feat-y -t x -b "Closes #2"'          # owns tracker: 41 yields
decl
r deny  'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1"'
g deny  'gh pr edit 100 -b "Closes #1"'
tr 'declare \[repo\] tracker = "github-issues"' 'gh pr create -R o/r -H feat-x -B main -t x -b "Closes #1"'
