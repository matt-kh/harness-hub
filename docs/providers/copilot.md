# GitHub Copilot CLI

**Tier: partial.** The guard runs on shell commands through Copilot CLI's `preToolUse` hook;
Copilot can deny but not ask, so ask decisions follow `[providers.copilot].ask_as` (default
`deny`).

| | |
|---|---|
| Binary | `copilot` |
| Home | `~/.copilot` |
| Instructions | `~/.copilot/copilot-instructions.md`, managed blocks |
| Skills | `~/.copilot/skills/<name>/` |
| Sub-agents | `~/.copilot/agents/` |
| Hooks | `~/.copilot/hooks/harness.json` → `providers/copilot/shim.sh` → guard |
| MCP | `~/.copilot/mcp-config.json` |

## How the guard is wired

- stdin `{"toolName":"bash","toolArgs":"<JSON string>"}` — note `toolArgs` is a JSON
  **string** that the shim parses a second time to find the command.
- `deny` → `{"permissionDecision":"deny","permissionDecisionReason":…}`; `allow` and
  pass-through print nothing; `ask` → per `ask_as`.
- Unknown tool → pass through; malformed JSON (outer or inner) → deny.

## Quirks

- Copilot CLI requires a GitHub account with a Copilot entitlement; organisation policy can
  disable the CLI or specific models. That is outside the hub's control.
- The hook file format is young and versioned by the CLI; the adapter README states the
  version it was verified against, and the weekly provider-drift workflow opens an issue when
  a newer release appears.
- Copilot's own tool approvals still apply on top of the guard.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Guard never fires | `~/.copilot/hooks/harness.json` missing or CLI too old → `harness doctor --provider copilot`, upgrade, `harness apply` |
| Every command denied with a parse error | the CLI changed its hook payload; open a [provider-change issue](https://github.com/matt-kh/harness-hub/issues/new?template=provider-change.yml) with a redacted sample |

<!-- generated:begin source=providers/copilot/provider.toml -->
<!-- generated:end -->
