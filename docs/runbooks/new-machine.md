# Runbook: new machine

Goal: a fresh laptop or VM running your full harness in about fifteen minutes. Assumes you
already use harness-hub elsewhere and keep `local/` in a private git repository (recommended);
if not, bootstrap creates a new config and you fill it in.

## 1. Base tools

Install git, curl, python ≥ 3.9, jq and your agent CLIs ([getting started §1](../getting-started.md#1-prerequisites)).
On macOS also `brew install bash`.

## 2. SSH key first

Clones and pushes use SSH everywhere, so create a key once per machine:

```sh
ssh-keygen -t ed25519 -C "you@example.com" -f ~/.ssh/id_ed25519
```

Add `~/.ssh/id_ed25519.pub` to each SCM (GitHub *Settings → SSH and GPG keys*, GitLab
*Preferences → SSH Keys*). The `github` bundle can upload it for you later (`ssh-key` step).

## 3. Clone the hub and your private overlay

```sh
git clone git@github.com:matt-kh/harness-hub.git ~/harness-hub
# if you keep local/ in a private repo (it is gitignored by the hub):
git clone <your-private-remote>/harness-local.git ~/harness-hub/local
chmod 700 ~/harness-hub/local
```

If you commit to the hub from this machine, set the noreply address in the clone
(`git config user.email "<id>+<login>@users.noreply.github.com"`) and check that GitHub
*Settings → Emails* has **Keep my email addresses private** and **Block command line pushes
that expose my email** enabled (once per account, needed before merging through the web UI;
see [CONTRIBUTING](../../CONTRIBUTING.md#development-loop)).

No private repo? Copy `local/harness.toml` (and `local/bundles/`, `local/gate-denylist.txt`)
from the old machine over SSH. It contains no secrets by design.

Machine-specific differences (another kubeconfig context, a different editor) go in
`local/harness.user.toml`, so the shared file stays identical everywhere.

## 4. Bootstrap

```sh
~/harness-hub/bootstrap
```

With an existing config it skips the questions, validates, shows the plan and applies it.
Review the plan: on a fresh machine every row should be `create`.

## 5. PATH, then doctor

Add `~/.local/bin` to your `PATH` if bootstrap said so
([getting started §3](../getting-started.md#3-put-localbin-on-your-path)), open a new shell:

```sh
harness doctor
harness steps --pending
```

## 6. Per-machine manual steps

Credentials are per machine and are never copied by the hub. Typically pending:

| Bundle | Steps | Minutes |
|---|---|---|
| github | `install-gh`, `gh-auth`, `ssh-key` | 5 |
| gitlab | `glab auth login` | 2 |
| jira | new PAT into `~/.config/jira` (create a new token per machine; don't copy the old one) | 2 |
| gdoc | `gdoc-login` only — the GCP project and OAuth client are per account and already exist; copy `client_secret.json` from your password manager or re-download it from the console | 2 |
| k8s | kubeconfig contexts from your cluster login tool | varies |

Run each sign-in in your own terminal. Re-run `harness doctor` until it reports 0 FAIL.

## 7. Smoke test

Start a session and ask the agent to read `~/.config/gh/hosts.yml`: the guard must deny it
(enforced and partial providers). Then retire the old machine's tokens:
[GitHub](rotate-github-token.md), [GitLab](rotate-gitlab-token.md), [Jira](rotate-jira-pat.md),
[Google](rotate-google-oauth.md).
