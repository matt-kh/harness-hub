# GitHub provider (github.com, GitHub Issues as the tracker)

Used when preflight reports `provider: "github"`. Same procedure, same non-negotiables as
`SKILL.md`; this file only maps each step's commands. Section numbers match SKILL steps
(`§0` … `§7`). Nothing here calls `jira` — GitHub repos use GitHub Issues.

**Command rules (the guard hook reads the command text):**
- Always `-R OWNER/REPO` **literally** in the command (like literal Jira keys). Never `$REPO`,
  never `GH_REPO=…` (the hook cannot look the PR/issue up → it asks).
- Literal issue/PR numbers in every write (`gh issue edit 12`, `gh pr edit 34`).
- `gh pr create`: never `--fill`, `--fill-first`, `--fill-verbose` (`-f` is `--fill`); body
  always from a file with `-F` (`--body-file`); `-B` base, `-H` head (`user:branch` for forks).
- `gh api` is GET-only for this skill: never `-X/--method`, `-f/-F/--input` (any field
  auto-POSTs).
- Closing keywords are denied in commits, PR title/body and `gh api` payloads:
  `close|closes|closed|fix|fixes|fixed|resolve|resolves|resolved` + `#N`, `owner/repo#N` or an
  issues URL (case-insensitive). **Mention** `#N` instead — the issue timeline gets the
  cross-reference; the human closes the issue after merge.

## Command mapping

| Step | GitLab / Jira (SKILL.md) | GitHub |
|---|---|---|
| §0 auth | `jira whoami` + `glab auth status` | `gh auth status` only (no jira calls). Not authed → stop: user runs `! gh auth login --git-protocol ssh` |
| §0 preflight | `preflight.sh [<short> …]` | `preflight.sh <N> [<short> <short>-sub-01-x]` — issue first, then candidates |
| §0 ticket | `jira get KEY` | `bash scripts/issue-facts.sh N` (`issue`, `parent`, `sub_issues`, `perms`, `agent_labelled`); `Could not resolve to an Issue` → stop, wrong repo/number |
| §0 existing MRs | `glab mr list --search KEY --all -F json` | preflight `existing_prs` / `stack_detected` (or `gh pr list -R OWNER/REPO --state all --search N --json number,title,headRefName,baseRefName,state,isDraft,url`) |
| §1 parent / links | `jira get PARENT`, `jira links` | `issue-facts.sh` `parent`, `existing_children` |
| §1 attachments | `jira attachments/download` | images/files are links in the issue body/comments; private `user-attachments` need the browser → ask the user if one matters |
| §2 triage comment | Jira wiki `*bold*` | Markdown `**bold**`, same fields (template below) |
| §3 label gate | `jira label KEY add agent-worked` | label bootstrap + `gh issue edit N -R OWNER/REPO --add-label agent-worked` (below) |
| §3 comment | `jira comment KEY …` | `gh issue comment N -R OWNER/REPO -F "$SCRATCH/N-triage.md"` |
| §3b sub-tickets | `jira-facts.sh`, `jira create … --link "Issue split:KEY"` | `issue-facts.sh N` → `sub_tickets_available`; `gh issue create` + `--add-sub-issue` (below) |
| §3b In Progress | `jira transition CHILD` | none — GitHub issues have no In-Progress state; skip silently (Projects are out of scope) |
| §4 branch | `git fetch origin`; `git switch -c "$BR" "origin/$BASE"` | same (fork flow: `upstream/$BASE`, see Fork flow) |
| §5 checks | `ci.mr_pipeline`, `ci.checks` | same keys from the Actions parser; also `ci.pr_ci_on_ticket_base` for stacked parts |
| §6 title style | `glab mr list --merged -P 10` | `gh pr list -R OWNER/REPO --state merged -L 10 --json title` |
| §6a create | `glab mr create … --label agent-worked --squash-before-merge --remove-source-branch` | `gh pr create -R OWNER/REPO -H "$BR" -B "$BASE" -t … -F … -l agent-worked` (no per-PR squash/delete flags — see below) |
| §6 read-back | `glab mr view IID -F json` | `gh pr view "$BR" -R OWNER/REPO --json number,title,body,isDraft,labels,baseRefName,headRefName,milestone,url` |
| §6 CI exists | `glab api …/pipelines` | `gh pr checks N -R OWNER/REPO` (exit 8 = pending; "no checks reported" = no CI) |
| §6b/6c edit | `glab mr update IID …` | `gh pr edit N -R OWNER/REPO -F … / -B "$BR" / -t …`; Draft → `gh pr ready N -R OWNER/REPO` |
| §7 handoff | `jira comment KEY …` | `gh issue comment N -R OWNER/REPO -F "$SCRATCH/N-handoff.md"` |
| never | `glab mr merge/approve` | `gh pr merge`, `gh pr review --approve`, `gh issue close/reopen` on the parent (hook: ask/deny) |

Milestone: the issue's own milestone if it is still open (`preflight.milestones`), else none.
Never create milestones or labels other than the `agent-*` ones.

## §0 Preflight

```bash
gh auth status                                                   # non-zero → stop (auth)
bash ~/.claude/skills/work-ticket/scripts/preflight.sh 12 <short> <short>-sub-01-x
bash ~/.claude/skills/work-ticket/scripts/issue-facts.sh 12
```
Key facts: `base_repo` (where PRs and issues go), `default_branch`, `can_label`, `fork_flow`,
`draft_prs_available`, `project.delete_branch_on_merge`, `project.squash_merge_allowed`,
`protected_branches` (classic + rulesets; `default_branch_protection.status` 403 = private Free
repo or not admin — the guard hook is then the only default-branch protection), `mr_template`,
`pr_templates` (multiple → pick one with `-T NAME` only if the user asks; else fill the default),
`codeowners`, `contributing`, `labels`, `milestones`, `existing_prs`, `ci.*`.
`fork_flow: true` → **Fork flow** below (single delivery only). `auth_ok: false` → stop.

## §2 Triage comment (Markdown)

```markdown
[agent-triage] <date> <me> via Claude Code (work-ticket)
**Verified:** yes — <path:line evidence> | partial — <gap> | no
**Classification:** <bug|enhancement|task|chore> / severity <low|med|high> / scope <S|M|L> / feasibility <ok|risky — why>
**Affected areas:** OWNER/REPO — <paths>
**Plan:**
1. <task>
**Open questions:** <numbered, or "none">
**Repo/branch:** OWNER/REPO <default-branch> -> <short-name>
```

## §3 Label gate + label bootstrap

```bash
gh label list -R OWNER/REPO --json name --limit 300 | jq -e 'any(.[]; .name=="agent-worked")' >/dev/null || \
  gh label create agent-worked -R OWNER/REPO -c 7057ff -d "Worked by an AI agent (work-ticket skill)"   # hook: allow (agent-* label)
gh issue edit 12 -R OWNER/REPO --add-label agent-worked                                              # hook: allow (agent-* label only)
gh issue view 12 -R OWNER/REPO --json labels | jq -e '.labels | any(.name=="agent-worked")'          # read-back; failure → stop
gh issue comment 12 -R OWNER/REPO -F "$SCRATCH/12-triage.md"                                         # hook: allow (labelled)
```
Same bootstrap for `agent-created` (sub-issues) and `agent-wip` (Draft fallback), colour
`7057ff` / `fbca04`. `can_label: false` (fork flow) → **no label gate is possible**: post
nothing on the upstream issue by default (any write would prompt — it is a human issue); the
triage lives in the PR body instead.

## §3b Sub-issues (L/XL, Q7 = create)

```bash
bash ~/.claude/skills/work-ticket/scripts/issue-facts.sh 12     # sub_tickets_available = has_issues && can_label
gh issue create -R OWNER/REPO -t "[#12] <imperative task title>" -F "$SCRATCH/12-sub-01.md" \
  -l agent-created,agent-worked -a @me ${MILESTONE:+-m "$MILESTONE"}                         # hook: allow (provenance label)
gh issue create -R OWNER/REPO -t "[#12] <…>" -F "$SCRATCH/12-sub-02.md" -l agent-created,agent-worked -a @me
gh issue edit 12 -R OWNER/REPO --add-sub-issue 41 --add-sub-issue 42                        # hook: allow (parent agent-labelled)
bash ~/.claude/skills/work-ticket/scripts/issue-facts.sh 12 | jq '.existing_children'        # read-back: [41,42]
```
Batch the creates in one Bash call; take the new numbers from the printed URLs. Body: the
`decomposition.md` sub-ticket text in Markdown, with `Split from #12` (a mention, never a
keyword). Hard sibling deps: write `Depends on #41` in the body (no native link needed).
No state changes on children or parent.

## §6 PR body template

Repo template (`mr_template`) set → fill its headings; put the `#N` mention where it asks for
the issue. Otherwise:

```markdown
## Issue
#12 — <issue title>            <- a mention only; NEVER "Closes/Fixes/Resolves #12"

## Why
<problem, from the issue + verification evidence>

## What
<approach; behaviour-level, not a file list>

## Task list
- [x] <task>
- [ ] <task — only while Draft/WIP>

## Checks
| check | in PR workflow? | ran locally? | result |
|---|---|---|---|

## CI recommendations
<ONLY when a gap exists — wording below>

## Stack
<ONLY for stacked delivery (main PR) — table below>

## Agent notes
- Issue #12 labelled `agent-worked`; issue state unchanged — close it yourself after merge
  (this PR deliberately uses no closing keyword).
- Sub-issues: #41, #42 (`agent-created`) — or "none". Delivery: <single | stacked — M parts>.
- Squash/delete-branch: chosen by the human at merge (repo: squash <allowed|not>, auto-delete <on|off>).
- Harness: repo-level `CLAUDE.md` / `.claude/` updated in this PR: <paths — why> — or "none".
```

**Title**: the repo's observed style (`gh pr list -R OWNER/REPO --state merged -L 10 --json
title`), **without** `#N` (the squash-merge subject is the PR title and the harness keeps
ticket refs out of commit subjects; the `## Issue` mention carries the link). Sub PRs:
`[part N/M] <task>`. Never a closing keyword.

**CI recommendations (Actions wording)** — only the ones that apply:
- `ci.mr_pipeline == false`: "No workflow runs on `pull_request`, so the checks above ran once
  locally before push. Recommended, **not implemented in this PR**: add a workflow with
  `on: pull_request` running pre-commit (`pre-commit/action`)."
- `ci.pr_ci_on_ticket_base == false` (stacked): "Workflows trigger on `pull_request` only for
  base `<branches>` (`on.pull_request.branches`), so the part PRs targeting `<BR>` run **no
  CI** — their checks ran locally per part. Recommended, **not implemented here**: drop the
  `branches` filter or add `'**'` to it, and gate expensive jobs with
  `if: github.base_ref == github.event.repository.default_branch`."
- `ci.per_branch_heavy == true`: "`on.push` has no `branches` filter, so every pushed branch
  runs `<per_branch_heavy_jobs>`; each stacked part pays that. Recommended: `on.push.branches:
  [<default>]` or `branches-ignore: ['**-sub-*']`."
- `ci.mr_heavy_jobs` non-empty (stacked): "`<jobs>` run on every PR regardless of base.
  Recommended: `if: github.base_ref == github.event.repository.default_branch` on them."
- `ci.paths_filters` present: note which parts will skip which workflows.
Never edit `.github/workflows/*` from this skill.

## §6a Single delivery

```bash
git push -u origin "$BR"                                                       # the ONLY push
# label bootstrap as in §3 (agent-worked; agent-wip too when the Draft fallback applies)
gh pr create -R OWNER/REPO -H "$BR" -B "$BASE" -t "<title>" -F "$SCRATCH/12-pr.md" \
  -l agent-worked ${MILESTONE:+-m "$MILESTONE"} ${DRAFT:+--draft}               # hook: allow
gh pr view "$BR" -R OWNER/REPO --json number,title,isDraft,labels,baseRefName,milestone,url
gh pr view "$BR" -R OWNER/REPO --json title,body | jq -r '.title, .body' | \
  grep -nEi '\b(clos(e|es|ed|ing)|fix(es|ed|ing)?|resolv(e|es|ed|ing)|implement(s|ed|ing)?):?\s+[A-Z]+-[0-9]+|\b(close[sd]?|fix(e[sd])?|resolve[sd]?):?\s+(([[:alnum:]_.-]+/[[:alnum:]_.-]+)?#[0-9]+|https?://github\.com/[^/ ]+/[^/ ]+/issues/[0-9]+)' \
  && echo "FIX: closing keyword — gh pr edit"
gh pr checks 34 -R OWNER/REPO                                                    # CI present?
```
Squash / delete-branch have no per-PR flags on GitHub: report `project.squash_merge_allowed`
and `project.delete_branch_on_merge` in Q11 and the handoff; the human picks at merge. Turning
on the repo setting is `gh repo edit` (hook: ask) — suggest it, don't run it.

## Draft fallback

`draft_prs_available: false` (private repo on the Free plan) → no `--draft`. Instead:
title prefix `[WIP] `, labels `-l agent-worked,agent-wip` (create `agent-wip` with
`gh label create agent-wip -R OWNER/REPO -c fbca04 -d "Work in progress (agent)"` if missing —
hook: allow). Later, when ready:
`gh pr edit 34 -R OWNER/REPO -t "<title without [WIP]>" --remove-label agent-wip` (hook: allow,
agent-labelled). With real Drafts: `gh pr ready 34 -R OWNER/REPO`.

## §6b Stacked delivery (owned repos only — never fork flow)

```bash
git push -u origin "$BR"; for s in <sub branches in order>; do git push -u origin "$s"; done
# main PR first — Draft (or [WIP]) until every part is merged
gh pr create -R OWNER/REPO -H "$BR" -B "$BASE" --draft -t "<summary>" -F "$SCRATCH/12-pr.md" -l agent-worked
git rev-list --count "$TARGET..$BR-sub-01-<task>"                                 # ≥ 1 before every create
gh pr create -R OWNER/REPO -H "$BR-sub-01-<task>" -B "$TARGET" -t "[part 1/M] <task>" \
  -F "$SCRATCH/12-sub-01.md" -l agent-worked ${UNFINISHED:+--draft}              # -B = ticket/sub branch; base → denied
# second pass: numbers known → regenerate Stack table + sub headers
gh pr list -R OWNER/REPO --state all --limit 100 --json number,headRefName,baseRefName,isDraft,state,url \
  | jq --arg br "$BR" '[.[] | select(.headRefName==$br or (.headRefName|startswith($br+"-sub-")))]' > "$SCRATCH/12-stack.json"
gh pr edit 34 -R OWNER/REPO -F "$SCRATCH/12-pr.md" && gh pr edit 35 -R OWNER/REPO -F "$SCRATCH/12-sub-01.md"   # hook: allow
```
**Stack mechanics on GitHub** (differs from GitLab CE):
- Sub PRs target the ticket branch `$BR` (fan-in) or their blocker's sub branch (chain).
- When a part merges **and its head branch is deleted**, GitHub retargets the PRs based on it
  onto the merged PR's base — exactly what a chain needs. If the branch is *not* deleted, the
  dependent keeps targeting the stale branch. So: tell the human to click **"Delete branch"**
  after merging each part (or rely on `delete_branch_on_merge: true`; suggest enabling it).
- **Never delete a sub branch before its PR merges** — GitHub closes the PR.
- `## Stack` table: same columns as `mr-description.md` with `#35` numbers, sub-issue column
  `#41` (or `part N`), target `feat-x` (never `main`), main PR row `#34 (this)`.
- Sub PR header: `> **Stack — part N of M** for #12 · main PR #34 · prev #35 · next #37`
  `> **Merge after:** #35 · **Target:** \`<BR>\` (never \`main\`) · click "Delete branch" after merging.`

## §6c Stack sync

```bash
gh pr list -R OWNER/REPO --state all --limit 100 --json number,headRefName,baseRefName,state,mergedAt,headRefOid > "$SCRATCH/12-stack.json"
git fetch origin --prune
# per MERGED part P with open dependents (squash-merge rewrote P's commits):
git rebase --onto "origin/$BR" "<P.headRefOid>" "<child-sub>"
git push --force-with-lease origin "<child-sub>"                                  # hook: ask — expected
gh pr edit 37 -R OWNER/REPO -B "$BR"          # only if GitHub did not auto-retarget (branch not deleted); → main is DENIED
# all parts merged → gh pr ready 34 -R OWNER/REPO   (or remove [WIP] + agent-wip); regenerate Stack; §7
```

## Fork flow (`fork_flow: true` — viewerPermission READ/TRIAGE on `base_repo`)

- **Single delivery only** (no stack: sub branches cannot live in upstream). Q8b is not asked.
- Fork once: `gh repo fork OWNER/REPO --remote --remote-name fork` (hook: **ask** — creates a
  repo on the user's account). `origin` stays upstream; the fork is the `fork` remote.
- Branch from upstream: `git fetch origin && git switch -c "$BR" "origin/$BASE"`.
- Read `contributing` (CONTRIBUTING.md): DCO sign-off (`git commit -s`), CLA, commit style,
  required issue link wording — follow it (still never a closing keyword).
- Push: `git push -u fork "$BR"`.
- Create: `gh pr create -R OWNER/REPO -H <me>:"$BR" -B "$BASE" -t "<title>" -F "$SCRATCH/12-pr.md"`
  — **no `-l`** (no permission); `--draft` per Q9 (upstream's `draft_prs_available`), never the
  `[WIP]` label fallback.
- Every later edit or comment on that PR or on the upstream issue **asks** (not agent-labelled,
  someone else's repo) — batch them and expect the prompt.
- First-time contributors: upstream Actions need a maintainer's **"Approve and run"** before
  CI starts — say so in the handoff; `gh pr checks` will show nothing until then.

## §7 Handoff

Owned repo (issue agent-labelled):
```bash
gh issue comment 12 -R OWNER/REPO -F "$SCRATCH/12-handoff.md"      # hook: allow (labelled)
```
```markdown
PR opened: <url> (`<BR>` -> `<BASE>`). Merge is by a maintainer — the agent never merges.
CI on PR: <yes — <workflows> | no — checks ran locally once, see PR>.
Issue state unchanged — **close the issue yourself after merge** (we never use closing keywords).
Sub-issues: #41, #42 (agent-created; close them with this issue).   <- only if any
```
Stacked: list the parts in merge order (`#35 [part 1/M] <task> -> <BR>` …), "click Delete
branch after each merge so dependents retarget", main PR last. Fork flow: no issue comment
unless the user asks (it would prompt); the handoff goes in the final message, plus the
"Approve and run" note.
