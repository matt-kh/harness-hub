## Repository bootstrap (repoboot)
- **Bootstrap new repositories with `/bootstrap-repo`** (`repoboot`), local or on GitHub/GitLab,
  never by hand. The steps:
  1. Run the standard intake (`repoboot questions`): at most two rounds of questions, only for
     what is still open.
  2. Record the answers in `.repo-standard.toml` (`repoboot answer`).
  3. Show the user `repoboot plan`.
  4. Run `repoboot apply`; the guard asks first.
- `apply` pushes for the first time only into an empty remote, after checking with
  `git ls-remote`. Every other push to a default branch stays denied. If the remote already
  has branches, clone it and retrofit it instead.
- **Existing repositories**: `repoboot check --fix` reports where the repository differs from
  the standard.
  - Render file changes on a branch (`repoboot render`) and deliver them through an MR/PR.
  - Fix remote settings, protection and labels with `repoboot apply` (it asks), only after
    the user has seen the plan.
- Architecture-specific layouts come from packs (`repo_bootstrap.pack_dirs`). When no pack
  covers an answer, say so and offer to write one. Never improvise files outside a pack.
- `repoboot` never writes `.harness.toml`. Give the user the draft from the plan to review
  and commit.

A repository's own instructions for the same action replace this block.
