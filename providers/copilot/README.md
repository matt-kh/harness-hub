# Provider: copilot (GitHub Copilot CLI)

**Verified against:** not yet verified live — written to the published Copilot CLI hooks,
skills, agents and MCP specification (2026-09). **Verify on install** with a denied command
before relying on the guard.

| artifact | where | how |
|---|---|---|
| instructions | `~/.copilot/copilot-instructions.md` | managed blocks |
| skills | `~/.copilot/skills/<name>/` | copied |
| agents | `~/.copilot/agents/<name>.md` | copied, templated |
| guard hook | `~/.copilot/hooks/{guard-bash.sh,guard.env,shim.sh}` + `hooks/harness.json` | `{"version":1,"hooks":{"preToolUse":[{"type":"command","bash":"HARNESS_ASK_AS=<ask_as> bash ~/.copilot/hooks/shim.sh","timeoutSec":10}]}}` |
| MCP | `~/.copilot/mcp-config.json` `mcpServers.<name>` | json-merge; entries get `type = "local"`, `tools = ["*"]` |
| permissions | — | use `copilot --allow-tool/--deny-tool`; the guard hook enforces the shell rules |

## Shim (`shim.sh`)

stdin `{toolName:"bash", toolArgs:"<JSON string>", cwd}`: `toolArgs` is decoded, its
`command` handed to the guard in the neutral envelope. Output: `{"permissionDecision":"allow"}`
or `{"permissionDecision":"deny","permissionDecisionReason":…}`. There is no "ask": a guard
`ask` becomes `[providers.copilot].ask_as` (`deny` by default). Tools other than
`bash`/`shell` pass through; malformed input or `toolArgs` fail closed (deny).

Fixtures: `tests/*.in.json` → `tests/*.out.json`, run by `tests/run.sh`.
