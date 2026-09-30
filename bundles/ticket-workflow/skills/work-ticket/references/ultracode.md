# Execution mode for large tickets — ultracode (Workflow tool) opt-in

## Q8 — the only way ultracode gets used
The Workflow tool requires explicit user opt-in. Inside this skill that opt-in is the user
selecting **"ultracode workflow"** in Q8 (see `enquiries.md`). Never call Workflow otherwise.
`--mode ultracode|subagents|single` pre-answers Q8; `--no-subagents` = single.

Options (defaults: L → subagents, XL → ultracode pre-selected — the user still chooses):
- **ultracode workflow** — N implementer agents in parallel worktrees, orchestrated by a
  Workflow script. Best for XL with ≥ 3 file-disjoint sub-tickets.
- **sequential subagents** — today's Step 4 path: one worktree per task, subagents one at a
  time or a few in parallel via the Agent tool.
- **single agent** — no worktrees; the main thread does everything sequentially.

## If ultracode is chosen

1. `Skill: workflow-authoring` — load it first; author the script in the format it prescribes.
2. **Main thread prepares git state before the workflow**: create `$BR` (stacked: plus the
   empty `stack root` commit), then one worktree per sub-ticket exactly as in `subagents.md`
   (`../<repo>_$BR-sub-NN-<task>`; dependent parts start from their blocker's branch, so
   their group runs after the blocker's). Workflow agents never run `git worktree`,
   `git switch`, or `git push`.
3. Workflow shape (stay ≤ 15 agents; > 8 sub-tickets → group them by `parallel_group`):
   - **Phase "Implement"**: one agent per sub-ticket, in parallel per group, sequential
     across groups when `depends_on` requires. Brief = the subagent brief from `subagents.md`
     + sub-ticket key, worktree path, sub-branch, scope, acceptance criteria, paths, and:
     "no closing keywords (Closes/Fixes/Resolves/Implements KEY) in any commit message;
     commit as `<imperative summary>` — no ticket key in commit messages".
   - **Phase "Review"** (optional): one reviewer per parallel group, reading only that
     group's worktree diffs; returns findings, does not edit.
   - Return contract per agent: `{sub_ticket, sub_branch, commits, files, verification, unfinished}`.
4. Back in the main thread — by Q8b:
   - **single**: converge each sub-branch (`git merge --squash` → one commit per sub-ticket,
     `subagents.md`), `code-reviewer` on `origin/$BASE...HEAD`, then Steps 5–7: one push, one
     MR, handoff comment.
   - **stacked**: no convergence. `code-reviewer` per part, integration check in the ephemeral
     worktree (`subagents.md` → Publish), then SKILL Step 6b (push each branch, N+1 MRs,
     second-pass descriptions) and Step 7.

## Constraints that do not change inside a workflow
- The user-level guard hook is session-wide: it applies to every workflow agent (pushes of
  `-sub-` branches → ask; jira/glab writes → gated; closing keywords → deny).
- No Jira/GitLab writes from workflow agents; the main thread owns all of them.
- Workflow agents never push and never create MRs; the main thread owns every push and MR
  (single: one push, one MR; stacked: one push per branch, N+1 MRs). Humans merge everything.
  Ticket state human-only for human tickets (agent-created sub-tickets: In Progress only, via the main thread).

## First-run check
On the first ultracode run, confirm in the transcript that a deliberate `git push` attempt
from a workflow agent **inside its sub worktree** was escalated by the hook, and that Phase
"Implement" agents ran on {{ core.model_policy.execute }} (`CLAUDE_CODE_SUBAGENT_MODEL`).
