# Bundle: github

GitHub as SCM **and** tracker: the `gh` CLI (pinned, sha256-verified install into
`~/.local/bin`, no sudo), a PR-based workflow, GitHub Issues as tickets for `ticket-workflow`,
and the gh guard rules:

- `gh auth token`, `--show-token` and similar token output: **deny**
- closing keywords (`close|fix|resolve` forms + `#N`, `owner/repo#N`, issue URL) in commits,
  `gh pr create|edit|merge` and `gh api` payloads: **deny**
- `gh issue close|reopen` on a human issue: **deny**; on an agent-labelled one: allow
- `gh issue create` without a provenance label (`agent-drafted`, `agent-created`): **deny**
- `gh pr create` with `agent-worked`, edits to agent-labelled PRs/issues: promptless
- edits to human PRs/issues, cross-repo (fork) edits, `gh pr merge`, `gh pr review`,
  `gh repo edit`, `gh api` writes: **ask**

Config: `github.host` (default `github.com`, or your GHES host), `github.login`.
Manual steps: `install-gh`, `gh-auth`, `ssh-key`, `agent-labels` (full text below).

## Command conventions agents follow

- Always pass `-R owner/repo` literally; never `GH_REPO=…` (the guard cannot look the
  repo up and asks).
- PR bodies from a file (`-F`), never `--fill`.
- `gh api` is GET-only unless you confirm.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `gh auth login --web` hangs or the device code page never completes (common in **WSL2**, behind SSO proxies, or when no browser can be opened) | the device flow needs a browser that can reach github.com and return | use a PAT: *Settings → Developer settings → Personal access tokens → Tokens (classic)*, scopes `repo`, `read:org`, `workflow`, `admin:public_key`; then `gh auth login --hostname github.com --git-protocol ssh --with-token < token.txt` and delete `token.txt` |
| `gh auth status` OK but `git push` asks for a password | the remote is HTTPS | `git remote set-url origin git@github.com:owner/repo.git`; remotes stay SSH, `gh auth setup-git` is not needed |
| `ssh -T git@github.com` → `Permission denied (publickey)` | key not uploaded or not loaded | step `ssh-key`; `ssh-add ~/.ssh/id_ed25519`; on macOS add `UseKeychain yes` to `~/.ssh/config` |
| `gh ssh-key add` → HTTP 404 / needs scope | token lacks `admin:public_key` | `gh auth refresh -h github.com -s admin:public_key`, or add the key in the web UI |
| `gh pr create --draft` fails in a private repo | Draft PRs are not available for private repositories on the GitHub Free plan | the workflow falls back to a `[WIP]` title prefix plus an `agent-wip` label |
| Branch protection / rulesets cannot be configured | GitHub Free offers them for **public** repos only | the guard's default-branch deny is then the only protection; consider making the repo public or a paid plan |
| Stacked PRs: a part PR closed unexpectedly | its head branch was deleted **before** it merged | delete branches only after merge; GitHub auto-retargets PRs whose *base* is deleted after merge |
| PR workflows do not run on stacked part PRs | `on: pull_request: branches: [main]` filters by base branch | drop the filter, or add `'**'` and gate expensive jobs on `github.base_ref` |
| An issue closed itself on merge | a closing keyword slipped in through a human edit | mention `#N` instead; reopen the issue |
| Every write to someone else's repo asks | fork flow: the agent cannot label upstream PRs/issues | expected; delivery is a single PR from your fork |

Rotating the token: [runbook](../runbooks/rotate-github-token.md).

<!-- generated:begin source=bundles/github/bundle.toml -->
<!-- generated:end -->
