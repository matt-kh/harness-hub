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
## Summary

gdoc CLI for Google Docs / Drive / Sheets / Gmail with provenance-gated writes; drafts only, never sends

Ships the stdlib `gdoc` CLI and its skill (search, read, export, create, import/append/replace,
Sheets get/append/update, Gmail search/read/draft), guard section 80 (writes to human files ask,
`mark` asks always, `api` is GET-only, create and mail draft are promptless) and the Workspace
section of the instructions. Needs a one-time GCP OAuth **Desktop** client inside your
Workspace organisation that only a human (sometimes an admin) can create — six manual steps.

- **Depends on:** `core`
- **Stability:** stable
- **Domain / posture:** workspace / label-gated

## Components

Stable ids derived from the path, with their [taxonomy](../reference/taxonomy.md) facets (domain shown only where it differs from the bundle's). All bundles: [catalog](../catalog.md).

**Skills**

- `gdoc/skills/gdoc` — control: guide · function: client · posture: label-gated · model: execute

**Rules**

- `gdoc/rules/80-gdoc` — control: guide · function: govern

**Guard sections**

- `gdoc/guard.d/80-gdoc` — control: sensor · function: govern · decisions: deny 1 · ask 2 · allow 2

**Permission lists**

- `gdoc/permissions` — control: guide · function: govern · decisions: ask 1 · allow 12

**CLIs**

- `gdoc/bin/gdoc` — function: client · posture: label-gated

**Doctor checks** (function: setup · posture: read-only; table below): `gdoc/doctor/gdoc-auth`, `gdoc/doctor/gdoc-cli`, `gdoc/doctor/gdoc-client`, `gdoc/doctor/gdoc-modes`

**Manual steps** (function: setup; table below): `gdoc/steps/admin-trust`, `gdoc/steps/consent-screen`, `gdoc/steps/desktop-client`, `gdoc/steps/enable-apis`, `gdoc/steps/gcp-project`, `gdoc/steps/gdoc-login`

## Requirements

### Binaries

| binary | min version | install | optional | why |
|---|---|---|---|---|
| `python3` | 3.9 |  | no | The gdoc CLI is stdlib python (urllib OAuth + REST). |

### Configuration

| key | type | required | default | description |
|---|---|---|---|---|
| `google.domain` | string | yes |  | Your Workspace domain. Sign-in is restricted to it (OAuth `hd`, GDOC_HD) and the GCP project must live inside this organisation for an Internal consent screen. |

### Secrets (never in harness.toml)

| id | where | written by | mode | rotate |
|---|---|---|---|---|
| `gdoc_client` | `~/.config/gdoc/client_secret.json` | human (downloaded from the GCP console) | 0600 |  |
| `gdoc_token` | `~/.config/gdoc/token.json` | gdoc auth login | 0600 | docs/runbooks/rotate-google-oauth.md |

## Manual steps

<a id="gcp-project"></a>

### gcp-project — Create a GCP project inside your organisation

*once per account · needs browser · ~3 min*

**Why:** An **Internal** consent screen (no verification, no test-user cap, refresh tokens that do not expire after 7 days) is only offered to projects inside the {{ google.domain }} organisation.

**How:**

1. https://console.cloud.google.com/projectcreate
2. **Organisation** must show `{{ google.domain }}` (not "No organisation"). Name: e.g. `agent-harness-gdoc`.
3. If project creation is disabled for your account, that is an admin gate: ask IT for a project
   in the org, or for the `roles/resourcemanager.projectCreator` role.

**Verify:** `true` (exit 0)

<a id="enable-apis"></a>

### enable-apis — Enable the Drive, Docs, Sheets and Gmail APIs

*once per account · needs browser · ~2 min*

**Why:** Calls to an API that is not enabled fail with 403 accessNotConfigured (gdoc exit 2).

**How:**

**APIs & Services → Library** → search and **Enable** each: Google Drive API, Google Docs API, Google Sheets API, Gmail API. Wait about a minute after enabling.

**Verify:** `true` (exit 0)

<a id="consent-screen"></a>

### consent-screen — Configure the OAuth consent screen as Internal

*once per account · needs browser · ~2 min*

**Why:** Internal is the reason for step gcp-project: an External app in testing mode expires refresh tokens after 7 days.

**How:**

**APIs & Services → OAuth consent screen** (new console: **Google Auth Platform → Branding / Audience**):
- Audience **Internal**
- App name `gdoc (agent-harness)`; support and developer email: {{ identity.email }}
- Scopes: leave empty — the CLI requests `drive`, `gmail.readonly` and `gmail.compose` at sign-in.
  There is no send scope: gdoc cannot put mail on the wire.

**Verify:** `true` (exit 0)

<a id="desktop-client"></a>

### desktop-client — Create a Desktop OAuth client and install its JSON

*once per account · needs browser · ~2 min*

**Why:** gdoc uses the installed-app loopback flow; only **Desktop app** clients accept any 127.0.0.1 port. A Web client fails with redirect_uri_mismatch.

**How:**

**APIs & Services → Credentials → Create credentials → OAuth client ID → Application type: Desktop app**,
name `gdoc`, **Download JSON**. Then:
```
install -d -m 700 ~/.config/gdoc
install -m 600 ~/Downloads/client_secret*.json ~/.config/gdoc/client_secret.json
gdoc auth status
```

**Verify:** `test -s ~/.config/gdoc/client_secret.json` (exit 0)

<a id="gdoc-login"></a>

### gdoc-login — Sign in

*once per machine · needs browser · ~1 min*

**Why:** Writes ~/.config/gdoc/token.json; agents cannot do this (browser + Google sign-in).

**How:**

`gdoc auth login --hint {{ identity.email }}` — approve in the browser, then `gdoc whoami`.
WSL2: the browser may not open by itself; copy the printed URL into your Windows browser (it
can reach the WSL loopback listener). If it cannot: `gdoc auth login --no-browser`, approve,
and paste the whole `http://127.0.0.1:…/?state=…&code=…` URL from the address bar at the prompt.

**Verify:** `gdoc whoami` (exit 0)

<a id="admin-trust"></a>

### admin-trust — Admin allow-list (only if sign-in says 'blocked by your administrator')

*once per org · needs admin, browser · ~5 min*

**Why:** Tenants that mark Drive/Gmail as Restricted block unverified internal apps until a Workspace admin trusts them.

**How:**

A Workspace admin: **admin.google.com → Security → Access and data control → API controls → Manage Third-Party App Access → Configure new app → OAuth App Name or Client ID** → paste the client ID from `desktop-client` → scope it to your OU → **Trusted**.

**Verify:** `gdoc whoami` (exit 0)

## Doctor checks

| id | severity | offline | fix |
|---|---|---|---|
| `gdoc-cli` | fail | runs | `harness apply` |
| `gdoc-client` | warn | runs | [desktop-client](#desktop-client) |
| `gdoc-auth` | warn | skipped | [gdoc-login](#gdoc-login) |
| `gdoc-modes` | warn | runs | `chmod 700 ~/.config/gdoc && chmod 600 ~/.config/gdoc/*.json` |

## Guides and sensors

Guides steer the agent before it acts; sensors detect at or after the action. Pairing: **paired**.

| side | kind | ref | note |
|---|---|---|---|
| guide | rule | `rules/80-gdoc.md` | provenance-gated writes, drafts only for mail, no sharing |
| guide | skill | `skills/gdoc` | the gdoc CLI and its round-trip editing workflow |
| guide | permission | `permissions.toml` | read commands allowed, writes left to the guard |
| sensor | guard | `guard.d/80-gdoc.sh` | GET-only api, provenance check before writes, ask on mark and mail send |
| sensor | doctor | `doctor_checks` | CLI, OAuth client, auth and token file modes |
| sensor | test | `guard.d/tests.sh` | guard rows with a stubbed gdoc |
| sensor | test | `tests/run.sh` | this bundle's rows against core + gdoc only |

**Not covered:** The gdoc CLI itself has no unit suite; its write paths are covered by the guard rows.

## Uninstall

Kept on uninstall: `~/.config/gdoc/**`

Revoke access at https://myaccount.google.com/permissions if you leave the organisation.
<!-- generated:end -->
