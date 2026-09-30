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
| Settings | `~/.gemini/settings.json`, json-merge of `hooks`, `mcpServers` and tool exclusions |
| Guard | `~/.gemini/hooks/guard-bash.sh` behind `providers/gemini/shim.sh`, event `BeforeTool`, matcher `run_shell_command` |
| MCP | `~/.gemini/settings.json` → `mcpServers` |

## How the guard is wired

The shim translates the envelopes ([ARCHITECTURE §5](../../ARCHITECTURE.md#5-guard)):

- stdin `{"tool_name":"run_shell_command","tool_input":{"command":…},"cwd":…}` → neutral
- `allow` → `{"decision":"allow"}`, `deny` → `{"decision":"deny","reason":…}`
- `ask` → per `ask_as`: `deny` (default, reason says "run it yourself") or `allow`
- unknown tool → pass through; malformed JSON → deny (fail closed)

## Quirks

- **Versions matter a lot.** Hooks and skills arrived in recent Gemini CLI releases; older
  builds silently ignore the `hooks` key, which means *no guard*. `harness doctor` checks the
  version against `min_version` in the adapter; the adapter README records the version it was
  verified against.
- Permission lists translate only partly: denies become tool exclusions, asks become advisory
  instruction text.
- Setting `ask_as = "allow"` trades safety for convenience: every command the guard would
  have asked about then runs without a prompt. Keep the default unless you understand the list
  in the [hook policy](../reference/hook-policy.md).
- Gemini reads `GEMINI.md` hierarchically (home, then project directories); repo-level files
  still take precedence as for every provider.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Commands that should be denied run | `gemini --version` below the adapter's `min_version`, or `hooks` missing from `~/.gemini/settings.json` → upgrade Gemini CLI, `harness apply` |
| Everything the guard would ask about is refused | expected with `ask_as = "deny"`; run the command yourself, or set `ask_as` per the note above |
| `settings.json` edits by Gemini itself show as drift | `harness sync`, then `--adopt` what you want to keep |

<!-- generated:begin source=providers/gemini/provider.toml -->
<!-- generated:end -->
