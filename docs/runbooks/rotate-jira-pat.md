# Runbook: rotate the Jira personal access token

Where it lives: `~/.config/jira` (mode 600), a single line containing the token, written by
you. The `jira` CLI sends it as a Bearer token; the MCP server reads the same file by
reference at start-up. The hub never reads it; the guard denies agents reading it.

Applies to Jira **Server / Data Center** 8.14 and later (PAT support).

1. Jira → avatar → *Profile → Personal Access Tokens → Create token*. Name it after the
   machine; set an expiry (your admin may enforce one).
2. Replace the file without the token passing through your shell history:

   ```sh
   install -m 600 /dev/null ~/.config/jira.new
   ${EDITOR:-vi} ~/.config/jira.new          # paste the token, save
   mv ~/.config/jira.new ~/.config/jira
   jira whoami
   ```

3. Revoke the old token on the same profile page.
4. Restart agent sessions that use the Jira MCP server (it read the old token at start).

If `jira get` returns `403` for one project while `jira whoami` works, the token is fine
and your account lacks permission on that project — do not rotate for that.

Verify: `harness doctor` shows the jira auth check PASS.
