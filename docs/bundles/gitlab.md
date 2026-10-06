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
## Summary

GitLab via glab: MR-based workflow, agent-label write gates, stacked-MR rules, Jira closing-keyword deny

Wires `glab` into the guard: MR creates are promptless (sub MRs must target the ticket branch),
edits to agent-labelled MRs are promptless, human MRs ask, merge/approve and other team-visible
actions ask, `glab api` writes ask. Closing keywords with a ticket key (`Closes KEY`) are denied
in commits, MR text and API payloads because GitLab's Jira integration would transition the
ticket (section 40). Adds the GitLab section of the instructions and glab read permissions.

- **Depends on:** `core`
- **Recommends:** `jira`, `ticket-workflow`
- **Stability:** stable
- **Domain / posture:** scm / label-gated

## Components

Stable ids derived from the path, with their [taxonomy](../reference/taxonomy.md) facets (domain shown only where it differs from the bundle's). All bundles: [catalog](../catalog.md).

**Rules**

- `gitlab/rules/50-gitlab` — control: guide · function: govern · yields: text

**Guard sections**

- `gitlab/guard.d/40-gitlab-closing` — control: sensor · domain: tracker · function: govern · decisions: deny 1 · yields: declaration
- `gitlab/guard.d/50-gitlab` — control: sensor · function: govern · decisions: ask 6 · allow 3 · yields: declaration

**Permission lists**

- `gitlab/permissions` — control: guide · function: govern · decisions: ask 11 · allow 13 · yields: config

**Doctor checks** (function: setup · posture: read-only; table below): `gitlab/doctor/gitlab-ssh`, `gitlab/doctor/glab-auth`, `gitlab/doctor/glab-binary`, `gitlab/doctor/glab-token-mode`

**Manual steps** (function: setup; table below): `gitlab/steps/gitlab-agent-labels`, `gitlab/steps/gitlab-ssh-key`, `gitlab/steps/glab-auth`, `gitlab/steps/install-glab`

## Requirements

### Binaries

| binary | min version | install | optional | why |
|---|---|---|---|---|
| `glab` | 1.40.0 |  | no | MR reads, gated MR writes, auth status; the work-ticket GitLab preflight. |
| `ssh` | 0 |  | yes | git remotes stay SSH; glab never gets git credentials. |

### Configuration

| key | type | required | default | description |
|---|---|---|---|---|
| `gitlab.host` | string | yes |  | Your GitLab host (self-managed hostname or gitlab.com). Used for auth, the instructions and work-ticket provider detection. |
| `gitlab.hosts_re` | string | no | `""` | Optional regex of extra GitLab hosts for work-ticket provider detection (HARNESS_GITLAB_HOSTS_RE). Empty = gitlab.host plus any host containing 'gitlab'. |
| `gitlab.mr_title_re` | string | no | `"^[A-Z][A-Z0-9_]*-[0-9]+ "` | ERE an MR title must match (ticket key first); empty disables the check. HARNESS_GITLAB_MR_TITLE_RE. |
| `gitlab.personal_repo_re` | string | no | `""` | Regex on a repo's top-level path; where it matches, a push to the default branch asks instead of denying (personal repos). Repos can also set WORK_TICKET_ALLOW_DEFAULT_PUSH_RE themselves. |

### Secrets (never in harness.toml)

| id | where | written by | mode | rotate |
|---|---|---|---|---|
| `glab_token` | `~/.config/glab-cli/config.yml` | glab auth login | 0600 | docs/runbooks/rotate-gitlab-token.md |

## Manual steps

<a id="install-glab"></a>

### install-glab — Install the GitLab CLI (glab)

*once per machine · needs nothing but a terminal · ~2 min*

**Why:** The guard, the instructions and /work-ticket drive GitLab through glab.

**How:**

- macOS: `brew install glab`
- Debian/Ubuntu/WSL: download the `.deb` for your arch from
  https://gitlab.com/gitlab-org/cli/-/releases and `sudo apt-get install ./glab_*.deb`
- No root: extract the release tarball's `bin/glab` into `~/.local/bin/`.
Minimum version 1.40.

**Verify:** `glab --version` (exit 0)

<a id="glab-auth"></a>

### glab-auth — Authenticate glab to {{ gitlab.host }}

*once per account · needs browser · ~3 min*

**Why:** Agents never run `glab auth login`; the token is yours and stays in ~/.config/glab-cli/config.yml.

**How:**

1. Create a personal access token: https://{{ gitlab.host }}/-/user_settings/personal_access_tokens
   (older GitLab: **Preferences → Access Tokens**) with scopes `api` and `read_user`, an expiry
   date you will remember.
2. In a terminal (inside Claude Code type `! ` first):
   `glab auth login --hostname {{ gitlab.host }}` → choose **Token**, paste it; git protocol **SSH**.
3. Self-managed GitLab with a private CA: `glab config set skip_tls_verify false --host {{ gitlab.host }}`
   stays false — add the CA to the system trust store instead.

**Verify:** `glab auth status --hostname {{ gitlab.host }}` (exit 0)

<a id="gitlab-ssh-key"></a>

### gitlab-ssh-key — Register an SSH key with {{ gitlab.host }}

*once per machine · needs browser · ~2 min*

**Why:** Clones and pushes use SSH remotes; the token is only for the API.

**How:**

`ssh-keygen -t ed25519 -C "{{ identity.email }}" -f ~/.ssh/id_ed25519` (skip if you have one), then
https://{{ gitlab.host }}/-/user_settings/ssh_keys → **Add new key** → paste `~/.ssh/id_ed25519.pub`.

**Verify:** `ssh -o BatchMode=yes -o ConnectTimeout=10 -T git@{{ gitlab.host }} 2>&1 | grep -qi 'welcome to gitlab'` (exit 0)

<a id="gitlab-agent-labels"></a>

### gitlab-agent-labels — Create the agent-* labels in the groups you work in (optional)

*once per org · needs nothing but a terminal · ~2 min*

**Why:** Promptless MR edits are keyed on an agent-* label; group-level labels avoid creating them per project.

**How:**

Per project the agent may create them itself (`glab label create -n {{ core.agent_labels.worked }}` is
promptless). Group owners can instead add `{{ core.agent_labels.worked }}`, `{{ core.agent_labels.created }}`
and `{{ core.agent_labels.drafted }}` once under **Group → Manage → Labels**.

**Verify:** `true` (exit 0)

## Doctor checks

| id | severity | offline | fix |
|---|---|---|---|
| `glab-binary` | fail | runs | [install-glab](#install-glab) |
| `glab-auth` | fail | skipped | [glab-auth](#glab-auth) |
| `gitlab-ssh` | warn | skipped | [gitlab-ssh-key](#gitlab-ssh-key) |
| `glab-token-mode` | warn | runs | `chmod 600 ~/.config/glab-cli/config.yml` |

## Guides and sensors

Guides steer the agent before it acts; sensors detect at or after the action. Pairing: **paired**.

| side | kind | ref | note |
|---|---|---|---|
| guide | rule | `rules/50-gitlab.md` | MR-based delivery, ticket keys mentioned never closed, stacked sub MRs |
| guide | permission | `permissions.toml` | read-only glab commands allowed |
| sensor | guard | `guard.d/40-gitlab-closing.sh` | denies closing keywords with a ticket key |
| sensor | guard | `guard.d/50-gitlab.sh` | API writes, merges/approvals, stacked MR targets, label-gated edits; MR creates with --fill or --related-issue, or a -t title not matching gitlab.mr_title_re, ask |
| sensor | doctor | `doctor_checks` | glab binary, auth, SSH and token file mode |
| sensor | test | `guard.d/tests.sh` | guard rows with a stubbed glab |
| sensor | test | `tests/run.sh` | this bundle's rows against core + gitlab only |

**Not covered:** `--squash-before-merge` / `--remove-source-branch` and description sections are guides only (project defaults may already squash); an MR created without -t is not title-checked.

## Uninstall

Kept on uninstall: `~/.config/glab-cli/**`

glab and its token are yours; uninstall removes only the rendered rules, guard sections and permissions.
<!-- generated:end -->
