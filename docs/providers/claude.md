# Claude Code

**Tier: enforced.** The reference provider: the guard's neutral envelope *is* Claude Code's
PreToolUse format, every capability is native, and "ask" decisions become real prompts.

| | |
|---|---|
| Binary | `claude` |
| Home | `~/.claude` |
| Instructions | `~/.claude/CLAUDE.md`, managed blocks |
| Skills | `~/.claude/skills/<name>/` (Agent Skills layout, `SKILL.md`) |
| Sub-agents | `~/.claude/agents/<name>.md` (front-matter `model:` rendered from `core.model_policy`) |
| Settings | `~/.claude/settings.json`, json-merge of `hooks`, `permissions`, `env`, `autoMode` |
| Guard | `~/.claude/hooks/guard-bash.sh`, PreToolUse hook with matcher `Bash` |
| Event `prompt` | `UserPromptSubmit` in `settings.json`, behind `providers/claude/shim-event.sh` (output filter), timeout in seconds |
| Event `stop` | `Stop` in `settings.json`, behind `providers/claude/shim-event.sh` (output filter), timeout in seconds |
| MCP | `~/.claude.json` → `mcpServers` (user scope) |

## How the guard is wired

`settings.json` gets one PreToolUse entry whose command runs the concatenated guard. No shim:
the hook reads `{"tool_name":"Bash","tool_input":{"command":…},"cwd":…}` and answers
`hookSpecificOutput.permissionDecision` = `allow | ask | deny` with a reason, or prints
nothing to let Claude Code's own permission rules decide.

Hooks from the user level and from a repository's `.claude/settings.json` all run and the
most restrictive decision wins, so a repository hook cannot lift a hub deny; the hub's guard
yields from inside instead, by reading the repository's `.harness.toml`. Skills resolve the
other way (personal shadows project; use `skillOverrides`), sub-agents the expected way
(project wins). The full facts table: [repository-level harnesses](../repo-level.md#claude-code-what-stacks-what-shadows).

## Extra hook events

Bundle hook scripts for the neutral events `prompt` and `stop` (`[[provides.hooks]]`,
[ARCHITECTURE §5](../../ARCHITECTURE.md#5-guard)) are registered as `UserPromptSubmit` and
`Stop` entries without a matcher. Claude's payloads are the neutral envelope, but unlike the
guard the events run behind `shim-event.sh`, which filters both ways:

- stdin: the payload without `transcript_path` and `last_assistant_message`.
- stdout: Claude adds plain `UserPromptSubmit` stdout to the model's context and honours
  `decision`, `continue` and `reason`, so the shim passes on only `systemMessage` and, on
  `UserPromptSubmit`, `hookSpecificOutput.additionalContext` (with `hookEventName`), as
  exactly one JSON object or nothing. A hook that fails or prints anything else says nothing.

`Stop` does not run when you interrupt the agent.

## Quirks

- **Settings and instructions are read at session start**; the hook *file* is read on every
  call. After `harness apply`, start a new session to pick up new rules, skills and
  permissions (`/clear` does not reload them). Guard changes apply immediately.
- **"Always allow" answers are written into `settings.json` → `permissions`.** Those keys are
  hub-owned, so `harness plan` shows them as drift. Adopt the ones you want to keep with
  `harness sync --adopt` (they move into your private bundle's `permissions.toml`) before
  the next `apply`.
- **Auto mode** (`autoMode.environment`) is rendered from `[trust]` in your config: the
  source-control hosts and domains the classifier should treat as yours. Keep it factual; it
  is read by a classifier, not a human.
- Runtime state — `projects/`, `sessions/`, `plans/`, `plugins/`, `.credentials.json`,
  memory files, org-synced skills — is never read or written by the hub.
- Inside a session, type `! <command>` to run a sign-in or other interactive command
  yourself; the guard does not apply to your own `!` commands.
- Plugins cannot ship `CLAUDE.md` or rules, which is why the hub renders instead of packaging
  a plugin.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Every Bash command is denied with "jq not installed" | install `jq`; the guard fails closed without it |
| Guard not running at all (dangerous commands go straight to the permission prompt) | `harness doctor` → `core/guard-hook`; check `jq '.hooks.PreToolUse' ~/.claude/settings.json` and that the script is executable |
| `plan` shows `CONFLICT` on `settings.json` | you and the hub both set the same key; the plan keeps yours. `harness sync --adopt` or remove your copy |
| A new skill does not appear | restart the session; check `~/.claude/skills/<name>/SKILL.md` exists |

<!-- generated:begin source=providers/claude/provider.toml -->
**Verified against:** Claude Code 2.1.x, 2026-09-30 (local)

### Targets

| artifact | path | mode | details |
|---|---|---|---|
| instructions | `~/.claude/CLAUDE.md` | managed-block |  |
| skills | `~/.claude/skills/<name>` | dir |  |
| agents | `~/.claude/agents/<name>.md` | file |  |
| settings | `~/.claude/settings.json` | json-merge | owner_keys=hooks, permissions, env, autoMode |
| hooks | `~/.claude/hooks` | dir | event=PreToolUse; matcher=Bash; register=settings |
| permissions |  | settings | key=permissions |
| trust |  | settings | key=autoMode.environment |
| mcp | `~/.claude.json` | json-merge | key=mcpServers |

### Hook events

Neutral hook events beyond the guard this adapter registers for bundle `[[provides.hooks]]` ([ARCHITECTURE §5](../../ARCHITECTURE.md#5-guard)).

| neutral event | provider event | shim | timeout unit | note |
|---|---|---|---|---|
| `prompt` | `UserPromptSubmit` | `shim-event.sh` | seconds |  |
| `stop` | `Stop` | `shim-event.sh` | seconds | systemMessage only; does not run when you interrupt the agent |

### Capabilities

| capability | value |
|---|---|
| agents | native |
| ask | true |
| hook_enforced | true |
| instructions | native |
| mcp | native |
| permissions | native |
| skills | native |
<!-- generated:end -->
