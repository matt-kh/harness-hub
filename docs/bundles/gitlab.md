# Bundle: gitlab

GitLab (self-hosted or gitlab.com) through `glab`, with MR-based delivery and the gitlab guard
rules:

- closing keywords in commit messages and `glab mr create|update` titles/descriptions:
  **deny** — GitLab's Jira integration (and its own issue closing) transitions tickets on
  them
- `glab mr create` with an `agent-*` label, edits to agent-labelled MRs: promptless
- edits to human MRs: **ask**; `glab mr merge|approve`: **ask** (humans merge)
- stacked delivery: sub MRs (`<short>-sub-NN-<task>` branches) must target the ticket branch;
  a sub MR aimed at the default branch is **denied**
- `glab api` GETs pass; writes **ask**

MRs are created with `--squash-before-merge --remove-source-branch` and a title that starts
with the ticket key; the key is mentioned, never used with a closing keyword.

Config: `gitlab.host`, `gitlab.personal_repo_re` (top-level paths where a default-branch push
asks instead of denying). Git remotes stay SSH.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `glab auth status` → 401 | token expired or revoked | [rotate the token](../runbooks/rotate-gitlab-token.md) |
| `glab` talks to gitlab.com instead of your server | host not set for the repo | `glab auth login --hostname <gitlab-host>`; run commands inside a clone whose remote is on that host, or pass `-R group/project` |
| `glab auth login` in a browser-less shell | no OAuth browser | choose **Token** and paste a PAT with scopes `api`, `read_user`, `write_repository` (`read_api` is enough for read-only use) |
| **"You cannot create more than N projects"** when forking or creating a project | your account's personal project limit (often 5 on self-hosted instances) | ask an admin to raise it, or create the project in a group namespace you can write to |
| Sub MR options (delete source branch) cannot be changed with `glab mr update --remove-source-branch=false` | glab only sends `true`; sub MRs inherit the project default | `glab api -X PUT projects/<id>/merge_requests/<iid> -f remove_source_branch=false` (asks) |
| After merging the bottom of a stack, the next MR retargets the default branch | GitLab auto-retargets to the *default* branch, not the ticket branch | retarget it back to the ticket branch before merging |
| A Jira ticket moved to Done on merge | a closing keyword in a human-edited MR description | mention the key instead; move the ticket back by hand |
| `git push` over HTTPS prompts for a password | HTTPS remote | `git remote set-url origin git@<gitlab-host>:group/project.git` and add your SSH key under *Preferences → SSH Keys* |
| An empty pipeline list on the main MR of a stack | `rules: changes:` skip MRs without file changes | expected for an empty stack root |

<!-- generated:begin source=bundles/gitlab/bundle.toml -->
<!-- generated:end -->
