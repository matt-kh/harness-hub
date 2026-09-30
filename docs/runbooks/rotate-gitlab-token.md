# Runbook: rotate the GitLab token

Where it lives: `~/.config/glab-cli/config.yml` (mode 600), written by `glab auth login`. The
hub never reads it; the guard denies agents reading it.

When: the token expired (GitLab enforces a maximum lifetime on self-hosted instances too),
you suspect exposure, or a machine was lost.

1. GitLab → avatar → *Edit profile → Access tokens → Add new token*. Name it after the
   machine, set an expiry, scopes `api`, `read_user`, `write_repository` (for read-only use,
   `read_api` and `read_repository`).
2. In your own terminal:

   ```sh
   glab auth login --hostname <gitlab-host>      # choose "Token", paste it
   glab auth status --hostname <gitlab-host>
   ```

3. Revoke the old token on the same page (*Active personal access tokens → Revoke*).

Lost machine: revoke its token and remove its SSH key (*Preferences → SSH Keys*) from another
device.

Verify: `harness doctor` shows the gitlab auth check PASS.
