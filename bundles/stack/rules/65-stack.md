## Stacked MRs/PRs (stk)
- **Humans merge, bottom-up, in the web UI**, in the order `stk plan --stack <BR>` prints
  (main MR/PR last). Agents never merge.
- **After every merge, and after amending a lower part, run `stk sync --stack <BR>`**: it
  retargets parts whose blocker merged (or that GitLab CE sent to the default branch),
  rebases each chain in its worktree with `git rebase --update-refs --onto`, pushes the
  rebased sub branches with `--force-with-lease`, refreshes at most one fan-in leaf
  server-side when the merge method needs it, and marks the main MR/PR ready once every
  part merged. It writes only to agent-labelled MRs/PRs; `--include-human` asks.
- A cascade conflict is aborted (`git rebase --abort`, every worktree as found) and reported
  with the commands; resolve it by hand. Never `reset --hard`, never `--force`.
- Parts that conflict share files: chain them instead of fanning them in.
- `glab stack` is not used (experimental upstream); stacks are work-ticket's `-sub-NN` branches.

A repository's own instructions for the same action replace this block.
