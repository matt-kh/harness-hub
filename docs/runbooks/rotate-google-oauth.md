# Runbook: rotate Google OAuth credentials (gdoc)

Two files, both mode 600, both never read by the hub and denied to agents:

| File | What | Written by |
|---|---|---|
| `~/.config/gdoc/client_secret.json` | the Desktop OAuth client of your GCP project | you (downloaded from the console) |
| `~/.config/gdoc/token.json` | refresh + access token for your account | `gdoc auth login` |

## Rotate the user token (common)

When: `invalid_grant`, a password change (Gmail scopes are revoked on password change), a lost
machine, or suspected exposure.

1. Revoke: <https://myaccount.google.com/permissions> → the gdoc app → *Remove access*
   (this signs out every machine).
2. `gdoc auth login` on each machine you still use; `gdoc whoami` to verify.

## Rotate the OAuth client (rare)

When: the client secret was exposed, or the GCP project is being replaced.

1. GCP console → *APIs & Services → Credentials* → your Desktop client → *Add secret* (or
   create a new **Desktop app** client), download the JSON.
2. `install -m 600 ~/Downloads/client_secret*.json ~/.config/gdoc/client_secret.json`
3. Delete the old secret (or client) in the console.
4. `gdoc auth login`; if your tenant restricts apps, the admin must trust the **new client ID**
   again (the gdoc bundle's `admin-trust` step).

Verify: `harness doctor` shows `gdoc/gdoc-auth` PASS.
