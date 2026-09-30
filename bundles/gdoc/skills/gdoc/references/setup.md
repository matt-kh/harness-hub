# `gdoc` one-time setup (human, ~10 minutes)

The agent cannot do any of this: it needs a browser, a Google sign-in and possibly a
Workspace admin. Do it once; after that `gdoc` refreshes its own token forever (an
**Internal** consent screen issues refresh tokens that do not expire after 7 days).

## 1. GCP project

1. <https://console.cloud.google.com/projectcreate> — create a project **inside the
   {{ google.domain }} organisation** (the Organisation field must say `{{ google.domain }}`, not "No
   organisation"). Name it e.g. `claude-code-gdoc`.
   *If project creation is disabled for your account, that is an admin gate — ask IT for a
   project in the org, or for the `roles/resourcemanager.projectCreator` role.*
2. **APIs & Services → Library** — enable all four:
   - Google Drive API
   - Google Docs API
   - Google Sheets API
   - Gmail API

## 2. OAuth consent screen

**APIs & Services → OAuth consent screen** (new console: *Google Auth Platform → Branding*):

- Audience: **Internal**. This is the important one — Internal needs no Google verification,
  has no test-user cap, and its refresh tokens do not expire after 7 days. Internal is only
  offered when the project is inside the {{ google.domain }} organisation (step 1).
- App name: `gdoc (claude-code)`; support email + developer email: your own address.
- Scopes: you can leave the list empty here; the CLI requests them at sign-in time —
  `drive` (covers Docs and Sheets), `gmail.readonly` (search/read mail) and `gmail.compose`
  (create drafts). gdoc has no send verb, so nothing it can do puts mail on the wire.

## 3. Desktop OAuth client

**APIs & Services → Credentials → Create credentials → OAuth client ID → Application type:
Desktop app**, name `gdoc`. Then **Download JSON**.

The type must be **Desktop app**, not Web application: `gdoc` uses the installed-app loopback
flow (`http://127.0.0.1:<random port>/`), which Desktop clients accept on any port without
registering a redirect URI. A "web" client is rejected with exit 2.

## 4. Install the client secret

```bash
install -d -m 700 ~/.config/gdoc
install -m 600 ~/Downloads/client_secret*.json ~/.config/gdoc/client_secret.json
gdoc auth status      # both files' presence and modes; exit 2 until you log in
```

## 5. Log in

```bash
gdoc auth login       # opens a browser; approve for {{ identity.email }}
gdoc whoami           # email, granted scopes, access-token expiry
```

`auth login` prints the authorisation URL to stderr before trying to open a browser. Under
WSL2 `webbrowser.open` often no-ops — copy the URL into your Windows browser; it can reach
the WSL loopback listener, so the flow completes normally.

If the Windows browser genuinely cannot reach WSL's `127.0.0.1`:

```bash
gdoc auth login --no-browser
# approve in the browser; the redirect page fails to load — that is expected
# copy the whole http://127.0.0.1:8765/?state=...&code=... URL from the address bar
# and paste it at the prompt (a bare code works too)
```

Other flags: `--hint {{ identity.email }}` pre-fills the account chooser;
`--scopes drive,gmail` (aliases: `docs`, `drive`, `sheets`, `gmail`, `gmail.readonly`,
`gmail.compose`, or full scope URLs) overrides the default scope set — re-run `auth login` with it if a call ever fails with a
scope error.

## 6. Admin trust (only if sign-in is blocked)

If the consent screen says the app is blocked by your administrator, Drive/Gmail are marked
*Restricted* in the tenant. A Workspace admin must allow-list the client:

**admin.google.com → Security → Access and data control → API controls → Manage Third-Party
App Access → Configure new app → OAuth App Name or Client ID** → paste the client ID from
step 3 → scope it to your OU → **Trusted**.

## Troubleshooting (exit code 2 = auth / connection / scope / API)

| Symptom | Cause | Fix |
|---|---|---|
| `No OAuth client at ~/.config/gdoc/client_secret.json` | step 4 not done | download the Desktop client JSON and `install -m 600 …` it |
| `is a 'web' OAuth client` | wrong client type | create an **OAuth client ID → Desktop app** and re-download |
| `Not signed in (no token.json)` | never logged in | `gdoc auth login` |
| `invalid_grant` on any command | refresh token revoked/expired, or the account password changed (Gmail scopes are revoked on password change) | `gdoc auth login` |
| `Google returned no refresh_token` | Google suppressed consent for an already-authorised app | revoke `gdoc (claude-code)` at <https://myaccount.google.com/permissions>, then `gdoc auth login` |
| `403 scope/API problem … enable the API` / `accessNotConfigured` | that API is not enabled in the project | enable it in step 1.2, wait ~1 min, retry |
| `403 … ACCESS_TOKEN_SCOPE_INSUFFICIENT` | token lacks the scope | `gdoc auth login --scopes drive,gmail` |
| `Access blocked: this app is blocked` in the browser | tenant marks Drive/Gmail Restricted | admin trust, step 6 |
| `Error 400: redirect_uri_mismatch` | client is a Web app, not Desktop | recreate as Desktop app |
| `Cannot reach oauth2.googleapis.com` | network/proxy | check the corporate proxy, retry |
| `404 on … no such file` | wrong id, or no access to that file | re-find it with `gdoc search`; ask the owner to share it |
| `no agent provenance marker` prompt on every write | human-owned file | `gdoc mark <ID> agent-worked` once (the prompt is intentional) |

Never `cat`, `echo` or paste the contents of `~/.config/gdoc/client_secret.json` or
`token.json` anywhere — `gdoc auth status` reports everything diagnosable about them
(existence, mode, scopes, expiry) without exposing a secret.
