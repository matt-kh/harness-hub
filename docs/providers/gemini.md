# Gemini CLI

**Tier: partial.** The guard runs on every shell command through Gemini CLI's `BeforeTool`
hook, but Gemini has no "ask" answer: ask decisions are mapped by
`[providers.gemini].ask_as` (default `deny`, with a reason telling you to run the command
yourself).

| | |
|---|---|
| Binary | `gemini` |
| Home | `~/.gemini` |
| Instructions | `~/.gemini/GEMINI.md`, managed blocks |
| Skills | `~/.gemini/skills/<name>/` |
| Sub-agents | not a native concept: agent bodies are inlined as instruction sections |
| Settings | `~/.gemini/settings.json`, json-merge of `hooks` and `mcpServers` |
| Guard | `~/.gemini/hooks/guard-bash.sh` behind `providers/gemini/shim.sh`, event `BeforeTool`, matcher `run_shell_command` |
| Event `prompt` | `BeforeAgent` in `settings.json`, behind `providers/gemini/shim-prompt.sh`, timeout in milliseconds |
| Event `stop` | `AfterAgent` in `settings.json`, behind `providers/gemini/shim-stop.sh` (runs after every turn), timeout in milliseconds |
| MCP | `~/.gemini/settings.json` → `mcpServers` |

## How the guard is wired

The shim translates the envelopes ([ARCHITECTURE §5](../../ARCHITECTURE.md#5-guard)):

- stdin `{"tool_name":"run_shell_command","tool_input":{"command":…},"cwd":…}` → neutral
- `allow` → `{"decision":"allow"}`, `deny` → `{"decision":"deny","reason":…}`
- `ask` → per `ask_as`: `deny` (default, reason says "run it yourself") or `allow`
- unknown tool → pass through; malformed JSON → deny (fail closed)

## Extra hook events

Bundle hook scripts for the neutral events `prompt` and `stop` (`[[provides.hooks]]`,
[ARCHITECTURE §5](../../ARCHITECTURE.md#5-guard)) run behind `shim-prompt.sh` (`BeforeAgent`)
and `shim-stop.sh` (`AfterAgent`):

- stdin → the neutral envelope (`session_id`, `cwd`, and `prompt` or `stop_hook_active`);
  `transcript_path`, `prompt_response` and the timestamp are not passed on.
- Gemini parses hook stdout as exactly one JSON object and shows any other text as a message,
  so the shim prints the hook's `systemMessage` and, on `BeforeAgent` only, `additionalContext`
  (as `hookSpecificOutput` with `hookEventName`) in one object, or nothing; garbage, several
  objects or the output of a failing hook are dropped. `AfterAgent` passes `systemMessage`
  only (`additionalContext` is not verified there).
- The shims never emit `decision`, `continue` or `reason`: these hooks cannot block a turn.
- `AfterAgent` runs after every turn, not once per session; a hook that should speak once
  keeps its own marker.

## Quirks

- **Versions matter a lot.** Hooks and skills arrived in recent Gemini CLI releases; older
  builds silently ignore the `hooks` key, which means *no guard*. `harness doctor` checks the
  version against `min_version` in the adapter; `verified` in `providers/gemini/provider.toml`
  (shown below) records the version it was verified against.
- Permission lists are not translated (the `permissions` target is `unsupported`); the guard
  hook enforces the shell rules.
- Setting `ask_as = "allow"` trades safety for convenience: every command the guard would
  have asked about then runs without a prompt. Keep the default unless you understand the list
  in the [hook policy](../reference/hook-policy.md).
- Gemini reads `GEMINI.md` hierarchically (home, then project directories). Whether
  project settings stack hooks or pass environment to them is not covered by the hub; a
  repository's `.harness.toml` works regardless, because the guard reads it from the hook's
  cwd ([repository-level harnesses](../repo-level.md#other-providers)).

## Troubleshooting

| Symptom | Fix |
|---|---|
| Commands that should be denied run | `gemini --version` below the adapter's `min_version`, or `hooks` missing from `~/.gemini/settings.json` → upgrade Gemini CLI, `harness apply` |
| Everything the guard would ask about is refused | expected with `ask_as = "deny"`; run the command yourself, or set `ask_as` per the note above |
| `settings.json` edits by Gemini itself show as drift | `harness sync`, then `--adopt` what you want to keep |

<!-- generated:begin source=providers/gemini/provider.toml -->
**Verified against:** verify on install (written to the published spec, 2026-09)

### Targets

| artifact | path | mode | details |
|---|---|---|---|
| instructions | `~/.gemini/GEMINI.md` | managed-block |  |
| skills | `~/.gemini/skills/<name>` | dir |  |
| agents |  | inline | no sub-agent files; agent bodies become sections of GEMINI.md |
| settings | `~/.gemini/settings.json` | json-merge | owner_keys=hooks, mcpServers |
| hooks | `~/.gemini/hooks` | dir | event=BeforeTool; matcher=run_shell_command; shim=shim.sh; register=settings |
| permissions |  | unsupported | permission lists are not translated; the guard hook enforces shell rules |
| trust |  | unsupported |  |
| mcp | `~/.gemini/settings.json` | json-merge | key=mcpServers |

### Hook events

Neutral hook events beyond the guard this adapter registers for bundle `[[provides.hooks]]` ([ARCHITECTURE §5](../../ARCHITECTURE.md#5-guard)).

| neutral event | provider event | shim | timeout unit | note |
|---|---|---|---|---|
| `prompt` | `BeforeAgent` | `shim-prompt.sh` | milliseconds |  |
| `stop` | `AfterAgent` | `shim-stop.sh` | milliseconds | runs after every turn, not once per session |

### Capabilities

| capability | value |
|---|---|
| agents | inlined |
| ask | false |
| hook_enforced | true |
| instructions | native |
| mcp | native |
| notes | no 'ask' decision: guard asks map to [providers.gemini].ask_as (default deny) |
| permissions | advisory |
| skills | native |
<!-- generated:end -->
