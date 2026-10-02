# Bundle: jira

Jira **Server / Data Center** (8.x and later) for agents: the stdlib `jira` CLI, a read-only
MCP server, and the Jira write gate.

- Reads are free: `jira get`, `jira search`, `jira fields PROJ`, sprints, versions, links.
- Creates need a provenance label; writes to tickets carrying an `agent-*` label are
  promptless; writes to purely human tickets **ask**; state transitions on human tickets are
  **denied** (`WORK_TICKET_ALLOW_TRANSITION=1` per repo turns that into ask).
- The MCP server (`mcp-atlassian` through `uvx`) runs with `READ_ONLY_MODE=true` and receives
  the token by file reference, never inline.
- Plain text in comments and descriptions (Jira wiki markup), never Cloud's ADF.

Config: `jira.url`, `jira.kind` (`server`; Cloud is not implemented), `jira.link_types`,
`jira.fields.<PROJECT>` (custom field ids, discovered with `jira fields PROJ`),
`jira.issue_types`, `jira.mcp.enabled`.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `jira whoami` exits 2 | no token file, token expired, or server unreachable | create a PAT (below) and save it to `~/.config/jira` with mode 600 |
| **You are on Jira Cloud** (`*.atlassian.net`) | Cloud uses API tokens with Basic auth and ADF bodies; this bundle speaks the Server REST API with Bearer PATs | not supported in v1; set `jira.kind = "cloud"` only once a Cloud adapter exists |
| No *Personal Access Tokens* entry in your profile | Jira Server older than 8.14, or PATs disabled by the admin | upgrade, or ask the admin to enable PATs; basic auth is deliberately not supported |
| `403 Permission denied` on one project, other projects fine | the token is valid; your account lacks *Browse* on that project | ask the project admin; this is not a bad-token case, do not rotate |
| `customfield_…` errors on create | field ids differ per instance and project | `jira fields PROJ`, copy the ids into `[jira.fields.PROJ]`, `harness apply` |
| Every create is denied | no provenance label on the command | expected; the skills add `agent-drafted` / `agent-created` |
| Ticket transitioned itself after an MR merged | closing keyword in a commit or MR text via the GitLab/GitHub integration | see [governance §4](../governance.md#4-closing-keywords-are-denied) |
| MCP server fails to start | `uvx` missing or PyPI unreachable | install `uv`; behind a proxy set `HTTPS_PROXY`; or set `jira.mcp.enabled = false` and use the CLI |
| TLS errors against an internal CA | the server's CA is not in python's trust store | `export SSL_CERT_FILE=/path/to/ca-bundle.pem` in your shell profile |

Creating the PAT: Jira → your avatar → **Profile** → **Personal Access Tokens** → **Create
token**, name it after this machine, set an expiry; copy it once into `~/.config/jira`
(`install -m 600 /dev/null ~/.config/jira` first, then paste with your editor). Rotation:
[runbook](../runbooks/rotate-jira-pat.md).

<!-- generated:begin source=bundles/jira/bundle.toml -->
## Summary

Jira Server client (jira CLI + skill), read-only jira-mcp server, Jira write governance in the guard

Ships the stdlib `jira` CLI and its skill (read/search/update tickets, sprints, versions,
transitions, attachments, links), the read-only `mcp-atlassian` server wired with the token
read from ~/.config/jira at launch (never stored in a provider config), and guard section 70:
creates need a provenance label, writes to agent-labelled tickets are promptless, writes to
human tickets ask and their transitions are denied, native links only between agent-labelled
tickets. Jira Server / Data Center 8.x with personal access tokens; Cloud is not implemented.

- **Depends on:** `core`
- **Recommends:** `ticket-workflow`, `gitlab`
- **Stability:** stable
- **Domain / posture:** tracker / label-gated

## Components

Stable ids derived from the path, with their [taxonomy](../reference/taxonomy.md) facets (domain shown only where it differs from the bundle's). All bundles: [catalog](../catalog.md).

**Skills**

- `jira/skills/jira` — control: guide · function: client · posture: label-gated · model: execute

**Rules**

- `jira/rules/70-jira` — control: guide · function: govern

**Guard sections**

- `jira/guard.d/70-jira` — control: sensor · function: govern · decisions: deny 3 · ask 1 · allow 4

**Permission lists**

- `jira/permissions` — control: guide · function: govern · decisions: allow 12

**MCP servers**

- `jira/mcp/jira-mcp` — function: client · posture: read-only

**CLIs**

- `jira/bin/jira` — function: client · posture: label-gated

**Doctor checks** (function: setup · posture: read-only; table below): `jira/doctor/jira-auth`, `jira/doctor/jira-cli`, `jira/doctor/jira-token-file`, `jira/doctor/uvx`

**Manual steps** (function: setup; table below): `jira/steps/install-uv`, `jira/steps/jira-fields`, `jira/steps/jira-pat`

## Requirements

### Binaries

| binary | min version | install | optional | why |
|---|---|---|---|---|
| `python3` | 3.9 |  | no | The jira CLI is stdlib python. |
| `uvx` | 0 |  | yes | Runs the read-only mcp-atlassian server (only when jira.mcp.enabled). |

### Configuration

| key | type | required | default | description |
|---|---|---|---|---|
| `jira.fields` | object | no | `{}` | Friendly custom-field names per project, from `jira fields PROJ`: [jira.fields.PROJ] story_points = "customfield_…". Lower-case keys at the top level apply to every project. Used by the jira CLI and create-ticket; ids are never guessed. |
| `jira.get_exclude` | array | no | `[]` | Friendly field names (from jira.fields) that `jira get` should not surface; they still resolve for set/create. HARNESS_JIRA_GET_EXCLUDE (comma-separated) overrides. |
| `jira.issue_types` | array | no | `[]` | Optional per-org issue-type rules for create-ticket: [[jira.issue_types]] name, standalone, requires, requires_without_facts, body_field, hint. Empty = generic (Epic requires epic_name). |
| `jira.kind` | string | no | `"server"` | Jira flavour. Only `server` (Server / Data Center 8.x, PAT bearer auth, plain-text bodies) is implemented. |
| `jira.link_types` | array | no | `["relates", "blocks", "issue split"]` | Link type names (case-insensitive) the guard permits for `jira link` / `create --link` (HARNESS_JIRA_LINK_TYPES). |
| `jira.mcp.enabled` | boolean | no | `true` | Register the read-only jira-mcp server (uvx mcp-atlassian, READ_ONLY_MODE=true). |
| `jira.url` | string | yes |  | Base URL of your Jira Server, no trailing slash. The CLI exits 2 with 'not configured' until it is set. |

### Secrets (never in harness.toml)

| id | where | written by | mode | rotate |
|---|---|---|---|---|
| `jira_pat` | `~/.config/jira` | human (Jira profile → Personal Access Tokens) | 0600 | docs/runbooks/rotate-jira-token.md |

## Manual steps

<a id="jira-pat"></a>

### jira-pat — Create a Jira personal access token and store it in ~/.config/jira

*once per account · needs browser · ~3 min*

**Why:** The CLI and the MCP server authenticate with a PAT (Bearer). Agents never create or read it.

**How:**

1. Open {{ jira.url }}/secure/ViewProfile.jspa → **Personal Access Tokens** → **Create token**
   (Jira Server / Data Center 8.14+). Name it `agent-harness`, set an expiry, **Create**, copy it.
2. Store it — plain, one line, private (paste when `cat` waits, then Ctrl-D):
   ```
   install -d -m 700 ~/.config
   ( umask 077; cat > ~/.config/jira )
   chmod 600 ~/.config/jira
   ```
3. Check: `jira whoami` prints your account name. Exit 2 means a bad token or an unreachable
   server (VPN?).

**Verify:** `jira whoami` (exit 0)

<a id="jira-fields"></a>

### jira-fields — Record your projects' custom field ids in harness.toml (optional)

*once per org · needs nothing but a terminal · ~5 min*

**Why:** Friendly field names (`jira set KEY "Story Points" 3`) and create-ticket's Problem Description / Category / Epic Name fields need the org's customfield ids; nothing is guessed.

**How:**

For each project you work in: `jira fields PROJ` lists `customfield_… -> Name`. Copy the ones
you use into `local/harness.toml`:
```
[jira.fields.PROJ]
story_points = "customfield_…"
epic_link = "customfield_…"
problem_description = "customfield_…"
```
then `harness apply`. Org admins can ship the table in the org overlay (`harness init --from`).

**Verify:** `true` (exit 0)

<a id="install-uv"></a>

### install-uv — Install uv (for the read-only jira-mcp server)

*once per machine · needs nothing but a terminal · ~1 min*

**Why:** jira-mcp runs `uvx mcp-atlassian`. Skip this and set jira.mcp.enabled = false if you only want the CLI.

**How:**

`curl -LsSf https://astral.sh/uv/install.sh | sh` (or `brew install uv`, or `pipx install uv`), then open a new shell.

**Verify:** `uvx --version` (exit 0)

## Doctor checks

| id | severity | offline | fix |
|---|---|---|---|
| `jira-cli` | fail | runs | `harness apply` |
| `jira-token-file` | fail | runs | [jira-pat](#jira-pat) |
| `jira-auth` | fail | skipped | [jira-pat](#jira-pat) |
| `uvx` | warn | runs | [install-uv](#install-uv) |

## Guides and sensors

Guides steer the agent before it acts; sensors detect at or after the action. Pairing: **paired**.

| side | kind | ref | note |
|---|---|---|---|
| guide | rule | `rules/70-jira.md` | reads free, writes gated by agent-* labels, transitions human-only |
| guide | skill | `skills/jira` | the jira CLI for Jira Server: search, fields, comments, labels |
| guide | permission | `permissions.toml` | read commands allowed; writes left to the guard |
| sensor | guard | `guard.d/70-jira.sh` | label-gated writes, provenance label on create, transitions denied on human tickets |
| sensor | doctor | `doctor_checks` | CLI, token file mode, auth and uvx for the MCP server |
| sensor | test | `guard.d/tests.sh` | guard rows with a stubbed jira |
| sensor | test | `tests/run.sh` | this bundle's rows against core + jira only |
| sensor | test | `skills/jira/scripts/tests/run.sh` | the jira CLI offline: config resolution and dry-run writes |

**Not covered:** The optional MCP server runs with READ_ONLY_MODE=true; no sensor inspects MCP calls.

## Uninstall

Kept on uninstall: `~/.config/jira`

The token file is yours; revoke it in Jira (profile → Personal Access Tokens) when you leave.
<!-- generated:end -->
