# Runbook: rotate the GitHub token

Where it lives: `~/.config/gh/hosts.yml` (mode 600), written by `gh auth login`. The hub never
reads it and the guard denies agents reading it or printing it (`gh auth token` is denied).

When: the token expired, you suspect exposure, a machine was lost, or you leave the project.

## OAuth token (the default device-flow login)

```sh
gh auth logout --hostname github.com
gh auth login --hostname github.com --git-protocol ssh --web
gh auth status --hostname github.com
```

Then revoke the old authorisation: github.com → *Settings → Applications → Authorized OAuth
Apps → GitHub CLI → Revoke* (this revokes it on every machine; re-login on the others).

## Personal access token (the PAT fallback)

1. github.com → *Settings → Developer settings → Personal access tokens → Tokens (classic) →
   Generate new token*. Scopes: `repo`, `read:org`, `workflow`, `admin:public_key`. Set an
   expiry.
2. Save it to a temporary file with mode 600, then:
   `gh auth login --hostname github.com --git-protocol ssh --with-token < token.txt && rm token.txt`
3. Delete the old token on the same settings page.

For GitHub Enterprise Server, replace `github.com` with your `github.host`.

## Lost machine

Revoke first, from another device: the OAuth app authorisation (above) and the machine's SSH
key under *Settings → SSH and GPG keys*. Then check *Settings → Security log* for activity.

Verify: `harness doctor` shows `github/gh-auth` PASS.
