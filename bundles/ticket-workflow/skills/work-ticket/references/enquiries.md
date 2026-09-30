# Enquiries & size rubric

All enquiries use AskUserQuestion. Ask **only** when the "skip when" condition is false;
otherwise take the default silently and state it in one line. Never ask what preflight,
`jira get`, or `glab` can discover.

## Size rubric (computed at the end of Step 2a)

| signal | source | L | XL (hard) |
|---|---|---|---|
| issue type | `jira get .type` | — | `Epic` |
| story points | `jira get .storyPoints` | 8 | ≥ 13 |
| tasks in the triage plan | Step 2a | 6–9 | ≥ 10 |
| files / distinct top-level modules touched | Grep/Glob evidence | ≥ 15 files or ≥ 4 modules | ≥ 30 files |
| layers touched (DB migration, API, UI, infra/helm/k8s, CI, docs) | evidence | ≥ 3 | — |
| repos touched | ticket text + evidence | > 1 (each repo is its own run) | — |
| ticket text | description | > 2000 chars or ≥ 5 enumerated items (+1 L signal) | — |

- Any XL signal → **XL**. ≥ 2 L signals → **L**. Exactly 1 L signal → **Q6**. Else **S/M**.
- Humans already split it (`jira links KEY` shows ≥ 3 "split to"/"is blocked by" children) →
  treat as L for planning but **never create new sub-tickets**; list the existing children.
- `--size S|M|L|XL`, or the user calling it big/huge in the prompt, overrides the score.
- Only **L/XL** trigger Step 2b ({{ core.model_policy.plan }} planning), Q7 and Q8.

## Checklist

| id | checkpoint | question | options (default **bold**) | skip when |
|---|---|---|---|---|
| Q0 | Step 0 | Working tree has changes unrelated to KEY | **Stash them** (`git stash push -m KEY`) / Abort | `dirty_files == 0`, or the changes are for this ticket |
| Q1 | Step 0 | Ticket is assigned to <X>, not you | **Proceed (don't reassign)** / Stop | assignee is me or empty |
| Q2 | Step 0 | MR(s) for KEY already exist (!N, state; stack detected when any source matches `-sub-`) | **Sync stack** (rebase/retarget open parts after merges, mark main Ready when all merged — shown only when a stack exists) / **Continue on its branch** / New branch + MR / Stop | `glab mr list --search KEY --all` empty (GitHub: preflight `existing_prs` empty) |
| Q3 | Step 0 | **Base/target branch for the main MR** — always asked | **`<default>` (recommended)** / Other → user types the branch name | `--base` given |
| Q4 | Step 1 | Ticket not found in this repo | **Stop (wrong repo / clarify)** / Proceed as new code (Verified: no) | outcome Verified or Partial |
| Q5 | Step 2a | Blocking open questions (listed) | **Label + post questions, wait** / Proceed with stated assumptions | no blocking questions |
| Q6 | Step 2a | Size is borderline (one L signal: <signal>) | **Treat as normal (M)** / Treat as large (L) | score clearly S/M or L/XL, or `--size` |
| Q7 | after 2b | Create N sub-tickets? (table: title, paths, group) | **Create N** (`Task`, `agent-created`+`agent-worked`, Issue split from KEY) / Task list only | S/M; `jira-facts.sh` says `sub_tickets_available=false`; human-split |
| Q8 | after Q7 | Execution mode | **Sequential subagents** (default L) / **ultracode workflow** (default XL) / Single agent | S/M (automatic worktrees); `--mode` / `--no-subagents`; < 2 parallelisable tasks |
| Q8b | after Q7 | Delivery for this L/XL ticket (N parts) | **Stacked MRs** — N Draft/Ready sub MRs into `<short>` + 1 main MR into `<base>`; N+1 branch pushes; humans merge bottom-up; CI: <cost line> / **Single MR** — parts squash-merged locally; 1 push, 1 MR, 1 pipeline set | S/M; `--delivery`; N < 2 (→ single); GitHub `fork_flow` (→ single) |
| Q9 | Step 6 | MR readiness is ambiguous | **Ready** / Draft | discoverable: any unchecked task → Draft; all done + no open questions → Ready |
| Q10 | Step 6 | Ticket has a sprint but no exact milestone match | **Omit milestone** / Use `<closest active title>` | no sprint (PROJ), or exact match; GitHub: never asked — milestone (exact match) or none (the issue's milestone if it is in preflight `milestones`) |
| Q11 | Step 6 | Push + open MR(s) — single: branch, target, title, description, labels, draft; stacked: every branch to push, N+1 MR titles/targets/draft flags and the CI cost line | **Push & create** / Stop | never — this is the push consent |

### Q8b default logic
- `ci.per_branch_heavy == false` and N ≥ 3 → **Stacked** is the default. Cost line:
  `+N MR pipelines` (shop: "each runs the full suite incl. the `docker` build — see CI
  recommendations").
- `ci.per_branch_heavy == true` → **Single** is the default; the stacked option must spell out
  the multiplied cost: `N+1 branch pipelines, each: <ci.per_branch_heavy_jobs names + why>`
  (e.g. a repo whose branch pipeline runs a ~90 min build + multi-arch image push + a review env).
  Stacked requires the explicit pick.
- N == 2 → **Single** default (still asked unless `--delivery`).
- `protected_branches.sub_pattern_matches == true` (or a `matches` entry true for the ticket
  branch) → append to the stacked option: "WARNING: protected-branch rule `<pattern>` matches
  — Developers cannot merge into `<short>`; a Maintainer must."
- Vet `per_branch_heavy_jobs` against the CI file before quoting (the heuristic flags
  `timeout ≥ 60 min` too, e.g. a slow linter).

Promptless by hook design (no enquiry, no prompt): the label gate (`jira label … add
agent-worked`), batched sub-ticket creates, GitLab `agent-worked` label creation, `glab mr
create --label agent-worked` (sub MRs: only when `-b` is a ticket/sub branch), edits to
agent-labelled tickets/MRs incl. `--description-file`, `--ready`, `--target-branch <ticket
branch>`, sub-ticket transitions, and `git push` of sub branches from the main checkout.
Still hook-prompted: MR merge/approve, `git push --force-with-lease` during stack sync, any
write to a purely human ticket or MR (no agent-* label). Denied: transitions on human tickets;
a sub MR created against or retargeted to `master|main`. Never ask about ticket state transitions on the parent — the answer is always no.

## Wording rules
- One question per checkpoint; bundle Q0–Q3 into a single AskUserQuestion call when several
  apply at Step 0, and Q7+Q8 into one call.
- Options carry the consequence in the description (e.g. "starts a ~90-min build in <repo>").
- If the user's prompt already answers a question (e.g. "branch from release/1.12"), don't ask.
