# Runbook: rotate an observability API key

Where it lives: `~/.config/obs/<name>.key` (directory mode 700, file mode 600), one line
containing the key, written by you; `<name>` is the backend's `auth_file` in
`[[obs.backends]]`. The `obs` CLI sends it as `SIGNOZ-API-KEY` (SigNoz) or as a bearer token
(Grafana service account, Prometheus behind an authenticating proxy). The hub never reads it;
the guard and the Read permission deny agents reading it, and an API key written on a command
line is denied.

1. Create the new key with the **Viewer** role:
   - SigNoz: *Settings → API Keys → New key* (role Viewer, set an expiry).
   - Grafana: *Administration → Users and access → Service accounts → <account> → Add service
     account token* (the account has the Viewer role).
   - Prometheus behind a proxy: the proxy's own token procedure.
2. Replace the file without the key passing through your shell history:

   ```sh
   install -d -m 700 ~/.config/obs
   install -m 600 /dev/null ~/.config/obs/<name>.key.new
   ${EDITOR:-vi} ~/.config/obs/<name>.key.new      # paste the key, save
   mv ~/.config/obs/<name>.key.new ~/.config/obs/<name>.key
   obs backends --probe --backend <name>
   ```

3. Revoke the old key in the same UI.

If one command answers `403` while `obs backends --probe` shows `auth ok`, the key is fine and
its role lacks access to that resource: do not rotate for that.

Verify: `harness doctor` shows the `obs-keys` and `obs-reach` checks PASS.
