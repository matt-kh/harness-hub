# Bundle: gdoc

Google Workspace for agents through the stdlib `gdoc` CLI: read, search, export and write
Google Docs, Drive files and Sheets; search and read Gmail; create **drafts**. Writes follow a
provenance model keyed on the Drive file property `agent_provenance`:

- `create` stamps `agent_provenance=agent-created` and is promptless, as is `mail draft`.
- `import`, `append`, `replace`, `sheet append|update` are promptless only on files carrying an
  `agent-*` marker; on human files (or when the lookup fails) they **ask**.
- `mark` (adopting a human file) always **asks**.
- Sending mail is **not implemented**. Sharing, permissions, delete/trash and Calendar are not
  implemented on purpose. `gdoc api` is GET-only.

The one-time setup needs a browser, a Google sign-in and possibly a Workspace admin: create a
GCP project inside your organisation, enable four APIs, configure an **Internal** consent
screen, create a **Desktop** OAuth client, sign in, and (only if blocked) have an admin trust
the client. Manual steps: `gcp-project`, `enable-apis`, `consent-screen`, `desktop-client`,
`gdoc-login`, `admin-trust` (full click paths below). About ten minutes.

Config: `google.domain` (your Workspace domain), `google.account`, `google.scopes`,
`google.provenance_property`.

## Troubleshooting

`gdoc` exits 2 for auth, connection, scope and API problems.

| Symptom | Cause | Fix |
|---|---|---|
| `Error 400: redirect_uri_mismatch` | the OAuth client is a **Web application** | create a new client of type **Desktop app** and install its JSON; Desktop clients accept any loopback port |
| `is a 'web' OAuth client` | same as above, caught before the browser opens | same |
| The consent screen offers only **External** | the GCP project is not inside your Workspace organisation | recreate the project with *Organisation* = your domain (step `gcp-project`); External testing apps expire refresh tokens after 7 days |
| `invalid_grant` on any command | refresh token revoked, or your password changed (Gmail scopes are revoked on password change) | `gdoc auth login` |
| `Google returned no refresh_token` | Google skipped consent for an already-authorised app | revoke the app at <https://myaccount.google.com/permissions>, then `gdoc auth login` |
| `403 accessNotConfigured` / "enable the API" | one of the four APIs is not enabled in the project | step `enable-apis`; wait a minute; retry |
| `403 ACCESS_TOKEN_SCOPE_INSUFFICIENT` | the token lacks a scope | `gdoc auth login --scopes drive,gmail` |
| "Access blocked: this app is blocked" in the browser | the tenant marks Drive/Gmail as Restricted | step `admin-trust` (a Workspace admin) |
| In **WSL2** the browser never opens | `webbrowser.open` is a no-op there | copy the printed URL into your Windows browser; if it cannot reach WSL's loopback, `gdoc auth login --no-browser` and paste the redirect URL back |
| `Cannot reach oauth2.googleapis.com` | proxy or network | set `HTTPS_PROXY`, retry |
| `404 … no such file` | wrong id, or not shared with you | `gdoc search`; ask the owner to share |
| Every write prompts | the file is human-owned | intentional; `gdoc mark <ID> agent-worked` once if you want to hand it to the agent |
| Rich edits lost comments | `export --md` → edit → `import` replaces the whole document | use `append`/`replace` for surgical changes; `import` refuses while comments are open unless `--force` |

Never paste the contents of `~/.config/gdoc/client_secret.json` or `token.json` anywhere;
`gdoc auth status` reports everything diagnosable about them. Rotation:
[runbook](../runbooks/rotate-google-oauth.md).

<!-- generated:begin source=bundles/gdoc/bundle.toml -->
<!-- generated:end -->
