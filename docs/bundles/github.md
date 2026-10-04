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
## Summary

GitHub CLI, PR-based workflow, GitHub Issues as the tracker, gh governance rules

Installs `gh` (checksum-verified, no sudo), wires the guard rules for gh (token output deny,
GitHub closing-keyword deny, human-issue state deny, merge/review ask, API writes ask, label
gate on PR/issue writes, stacked-PR rules) and adds the GitHub section of the instructions and
the gh read permissions. The ticket-workflow skills drive GitHub Issues → PRs when this bundle
is active.

- **Depends on:** `core`
- **Recommends:** `ticket-workflow`
- **Stability:** stable
- **Domain / posture:** scm / label-gated

## Components

Stable ids derived from the path, with their [taxonomy](../reference/taxonomy.md) facets (domain shown only where it differs from the bundle's). All bundles: [catalog](../catalog.md).

**Rules**

- `github/rules/60-github` — control: guide · function: govern

**Guard sections**

- `github/guard.d/41-github-closing` — control: sensor · domain: tracker · function: govern · decisions: deny 1
- `github/guard.d/60-github` — control: sensor · function: govern · decisions: deny 2 · ask 2 · allow 3

**Permission lists**

- `github/permissions` — control: guide · function: govern · decisions: deny 1 · ask 75 · allow 32

**Installers**

- `github/install/gh` — function: setup

**Doctor checks** (function: setup · posture: read-only; table below): `github/doctor/gh-auth`, `github/doctor/gh-binary`, `github/doctor/gh-ssh`, `github/doctor/gh-token-mode`

**Manual steps** (function: setup; table below): `github/steps/agent-labels`, `github/steps/gh-auth`, `github/steps/install-gh`, `github/steps/ssh-key`

## Requirements

### Binaries

| binary | min version | install | optional | why |
|---|---|---|---|---|
| `gh` | 2.60.0 | `harness install gh` | no | PR/issue reads, gated writes, auth status; the work-ticket GitHub preflight. |
| `ssh` | 0 |  | yes | git remotes stay SSH; gh never gets git credentials. |

### Configuration

| key | type | required | default | description |
|---|---|---|---|---|
| `github.host` | string | no | `"github.com"` | GitHub host: github.com or your GHES hostname. |
| `github.login` | string | yes |  | Your GitHub login. Shown in the instructions; repos you own are trusted in the provider's auto-mode trust text. |

### Secrets (never in harness.toml)

| id | where | written by | mode | rotate |
|---|---|---|---|---|
| `gh_token` | `~/.config/gh/hosts.yml` | gh auth login | 0600 | docs/runbooks/rotate-github-token.md |

## Manual steps

<a id="install-gh"></a>

### install-gh — Install the GitHub CLI

*once per machine · needs nothing but a terminal · ~1 min*

**Why:** No sudo is assumed; the hub installs a pinned, sha256-verified release into ~/.local/bin.

**How:**

Run: `harness install gh`
Air-gapped: download `gh_<ver>_<os>_<arch>.tar.gz` (macOS: `.zip`) of the version in
`tools/gh.lock.json` on a connected machine, then
`harness install gh --from /path/to/gh_<ver>_<os>_<arch>.tar.gz`.
Package managers work too (`brew install gh`, the official apt repo) — any gh >= 2.60 on PATH.

**Verify:** `gh --version` (exit 0)

<a id="gh-auth"></a>

### gh-auth — Authenticate gh (browser device flow, PAT fallback)

*once per account · needs browser · ~3 min*

**Why:** Agents never run `gh auth login`; the token is yours and stays in ~/.config/gh/hosts.yml.

**How:**

1. In a terminal (inside Claude Code type `! ` first):
   `gh auth login --hostname {{ github.host }} --git-protocol ssh --web`
2. Choose **SSH** as the git protocol, then **Login with a web browser**; copy the one-time code,
   open the URL, paste it, **Authorize**.
3. If the device flow fails (SSO, proxy, WSL without a browser): create a classic PAT at
   https://{{ github.host }}/settings/tokens → **Generate new token (classic)** with scopes
   `repo`, `read:org`, `workflow`, `admin:public_key`, save it to a file, run
   `gh auth login --hostname {{ github.host }} --git-protocol ssh --with-token < token.txt`
   and delete the file.
4. `gh auth setup-git` is NOT needed — remotes are SSH.

**Verify:** `gh auth status --hostname {{ github.host }}` (exit 0, output matches `Logged in to`)

<a id="ssh-key"></a>

### ssh-key — Register an SSH key with GitHub

*once per machine · needs browser · ~2 min*

**Why:** Clones and pushes use SSH; gh has the admin:public_key scope only so it can upload the key.

**How:**

`ssh-keygen -t ed25519 -C "{{ identity.email }}" -f ~/.ssh/id_ed25519` (accept the defaults; skip
if you already have a key), then `gh ssh-key add ~/.ssh/id_ed25519.pub --title "$(hostname)"`.
Without that scope: {{ github.host }} → **Settings → SSH and GPG keys → New SSH key** → paste
`~/.ssh/id_ed25519.pub`.

**Verify:** `ssh -o BatchMode=yes -o ConnectTimeout=10 -T git@{{ github.host }} 2>&1 | grep -q 'successfully authenticated'` (exit 0)

<a id="agent-labels"></a>

### agent-labels — Create the agent-* labels in repos you will work in (optional, per repo)

*once per org · needs nothing but a terminal · ~1 min*

**Why:** The label gate needs the labels to exist; the skills create them on first use (`gh label create agent-*` is promptless), org-wide defaults avoid even that.

**How:**

Per repo: `gh label create {{ core.agent_labels.worked }} -R owner/repo -c 7057ff -d 'Worked by an AI agent'`
(and `{{ core.agent_labels.created }}`, `{{ core.agent_labels.drafted }}`). Org admins can add them to the
organisation's default repository labels instead.

**Verify:** `true` (exit 0)

## Doctor checks

| id | severity | offline | fix |
|---|---|---|---|
| `gh-binary` | fail | runs | [install-gh](#install-gh) |
| `gh-auth` | fail | skipped | [gh-auth](#gh-auth) |
| `gh-ssh` | warn | skipped | [ssh-key](#ssh-key) |
| `gh-token-mode` | warn | runs | `chmod 600 ~/.config/gh/hosts.yml` |

## Guides and sensors

Guides steer the agent before it acts; sensors detect at or after the action. Pairing: **paired**.

| side | kind | ref | note |
|---|---|---|---|
| guide | rule | `rules/60-github.md` | PR-based delivery, issue state is human-only, -R owner/repo on every call |
| guide | permission | `permissions.toml` | read-only gh commands allowed; token printing denied |
| sensor | guard | `guard.d/41-github-closing.sh` | denies closing keywords that would change issue state |
| sensor | guard | `guard.d/60-github.sh` | token printing, API writes, merges/reviews, provenance labels, stacked PR targets |
| sensor | doctor | `doctor_checks` | gh binary, auth, SSH and token file mode |
| sensor | test | `guard.d/tests.sh` | guard rows with a stubbed gh |
| sensor | test | `tests/run.sh` | this bundle's rows against core + github only |

**Not covered:** Forks: the guard cannot read labels on a fork, so edits there ask instead of being label-gated. The github-closing guard section enforces rule text that lives in rules/60-github.md.

## Uninstall

Kept on uninstall: `~/.config/gh/**`

Removes ~/.local/bin/gh only if the hub state records that the hub installed it.
<!-- generated:end -->
