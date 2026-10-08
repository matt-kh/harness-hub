## Merge queue (mq)
- **Humans run the train.** `mq run` merges, so it is the human's command: hand them the
  `mq plan …` output and the exact `mq run …` line to run in their terminal; when an agent
  invokes it the guard asks. Agents use `mq check`, `mq plan`, `mq status` (all reads) and
  `mq sync`.
- **`mq sync` prepares agent-labelled MRs/PRs only** (an `agent-*` label): it fixes a `-sub-`
  part aimed at the default branch, rebases only the head of the queue server-side
  (`glab mr rebase` / `gh pr update-branch`), and marks the main MR/PR ready once every part
  merged. Unlabelled ones are listed with the command that labels them; `--include-human`
  lifts that filter and asks.
- After a server-side rebase, refresh the sub worktree with the printed
  `git -C ../<repo>_<sub> pull --rebase origin <sub>` — never `reset --hard`.
- mq never force-pushes: a chained part stops with the `git rebase --onto` and
  `git push --force-with-lease` commands for the human.
- `glab stack` is not used (experimental upstream); stacks are work-ticket's `-sub-NN` branches.

A repository's own instructions for the same action replace this block.
