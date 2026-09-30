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
<!-- generated:end -->
