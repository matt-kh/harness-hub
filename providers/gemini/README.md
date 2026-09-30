# Provider: gemini (Gemini CLI)

**Verified against:** not yet verified live — written to the published hooks / skills / MCP
specification (2026-09). **Verify on install**: run `harness apply --providers gemini`, start
`gemini`, and try a denied command (for example reading a credential file) before relying on it.
The minimum version in `provider.toml` (0.26.0) is the first line with command hooks as far as
we know; older builds render fine but do not enforce the guard (`doctor` warns).

| artifact | where | how |
|---|---|---|
| instructions | `~/.gemini/GEMINI.md` | managed blocks |
| skills | `~/.gemini/skills/<name>/` | copied |
| agents | inlined into `GEMINI.md` | one `## Agent: <name>` block per agent |
| settings | `~/.gemini/settings.json` | json-merge, owner keys `hooks`, `mcpServers` |
| guard hook | `~/.gemini/hooks/{guard-bash.sh,guard.env,shim.sh}` | `hooks.BeforeTool[]` matcher `run_shell_command`, command `HARNESS_ASK_AS=<ask_as> bash ~/.gemini/hooks/shim.sh` |
| MCP | `~/.gemini/settings.json` `mcpServers.<name>` | json-merge of the active bundles' servers |
| permissions | — | not translated; the guard hook enforces the shell rules |

## Shim (`shim.sh`)

stdin `{tool_name:"run_shell_command", tool_input:{command}, cwd}` is translated to the guard's
neutral envelope; the guard's decision comes back as `{"decision":"allow"}` or
`{"decision":"deny","reason":…}`. Gemini has no "ask": a guard `ask` becomes
`[providers.gemini].ask_as` — `deny` (default; the reason tells the user to run the command
themselves) or `allow` (with a `systemMessage`). Other tools pass through (no output).
Malformed input, a missing guard or unreadable guard output fail closed (deny).

Fixtures: `tests/*.in.json` → `tests/*.out.json`, run by `tests/run.sh` (`harness test providers`).
