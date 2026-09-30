# Provider: claude (Claude Code)

**Verified against:** Claude Code 2.1.x on Linux/WSL2, 2026-09-30 (local). Minimum: 2.0.0.

| artifact | where | how |
|---|---|---|
| instructions | `~/.claude/CLAUDE.md` | managed blocks; your own text outside the blocks is kept |
| skills | `~/.claude/skills/<name>/` | copied (templated `*.md`, scripts verbatim) |
| agents | `~/.claude/agents/<name>.md` | copied, templated |
| settings | `~/.claude/settings.json` | json-merge, owner keys `hooks`, `permissions`, `env`, `autoMode` |
| permissions | `settings.json` `permissions.allow/ask/deny` | merged from every bundle's `permissions.toml`, de-duplicated, sorted |
| trust | `settings.json` `autoMode.environment` | rendered from `[trust]` (or `trust.environment` verbatim) |
| guard hook | `~/.claude/hooks/guard-bash.sh` + `guard.env` | `PreToolUse` / matcher `Bash`, command `bash <home>/.claude/hooks/guard-bash.sh` (no shim: the guard speaks Claude's envelope) |
| MCP | `~/.claude.json` `mcpServers.<name>` | json-merge of only the servers the active bundles define; every other key of the file is preserved |

## Quirks

- `~/.claude.json` is Claude Code's own runtime file. The harness parses it, replaces only its
  own `mcpServers.<name>` entries and writes it back atomically; close running sessions before
  `harness apply` if you changed MCP servers. Plan diffs for it show only the owned keys.
- Secrets for MCP servers are never written: a server with `env_files = { VAR = "~/path" }`
  becomes `bash -c 'export VAR="$(cat ~/path)"; exec <command> <args>'`.
- `settings.json` conflicts (a permission you placed in `deny` that a bundle wants in `allow`,
  a value you edited) are resolved in your favour and reported as `CONFLICT` by `plan` and as
  a `WARN` by `doctor`. `harness apply --adopt ~/.claude/settings.json` takes the rendered values.
- Extra settings under the owner keys come from `[providers.claude].settings`, e.g.
  `settings = { env = { CLAUDE_CODE_SUBAGENT_MODEL = "opus" } }`.
- Runtime state (`projects/`, `sessions/`, `plans/`, `plugins/`, `.credentials.json`, memory)
  is never read, listed or written.
