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
tr 'human-only' 'gh pr merge 100'
# gh pr update-branch: decided by the PR label gate (no longer an always-ask team action)
g allow 'gh pr update-branch 100'
g allow 'gh pr update-branch 110 --rebase'
g allow 'gh pr update-branch 110 -R o/r --rebase'
g ask   'gh pr update-branch 200'
g ask   'gh pr update-branch 120'                                  # fork PR
g ask   'gh pr update-branch'                                      # no ref: labels cannot be checked
g ask   'gh pr update-branch "$N"'
g ask   'GH_REPO=o/r gh pr update-branch 110'
g ask   'gh pr update-branch 110 && gh pr merge 110'               # merge stays human-only
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
# documented consequence: owning scm lifts the human-only merge ask and the issue-state deny
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
tr 'human-only.*ask the user instead' 'gh pr merge 100 --squash'
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
# closing keywords in forms 41 does not parse (backstop in 60, yields like 41)
g deny  'gh -Ro/r pr edit 100 -b "Closes #3"'
g deny  'gh pr -Ro/r edit 100 -b "Closes #3"'
g deny  'gh pr new -H feat-x -B main -t x -b "Fixes #3"'
decl '[owns]' 'domains = ["tracker"]'
r allow 'gh -Ro/r pr edit 100 -b "Closes #3"'                # yields with 41 when the repository owns tracker
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
