# Codex CLI

**Tier: advisory.** Codex gets the instructions, skills and MCP servers, but no command hook:
nothing technical stops a Codex session from running a command the guard would deny. Use
Codex's own strictest approval policy, and treat the rendered rules as guidance the model
follows, not enforcement.

| | |
|---|---|
| Binary | `codex` |
| Home | `~/.codex` |
| Instructions | `~/.codex/AGENTS.md`, managed blocks |
| Skills | `~/.codex/skills/<name>/` plus `[[skills]]` entries in `config.toml` |
| Sub-agents | inlined as instruction sections |
| Settings | `~/.codex/config.toml`, one fenced managed table block (`toml-block`) |
| Guard | none (advisory) |
| MCP | `[mcp_servers]` in the managed block of `config.toml` |

## Quirks

- `AGENTS.md` is an open convention several tools read; the managed-block model keeps your own
  sections intact.
- The hub edits `config.toml` only inside its fenced block. Keys you set elsewhere in the file
  are yours; if you set the same table the hub does, the plan shows `CONFLICT` and keeps yours.
- Codex's hook support is newer and not yet verified by this project. When it is, the adapter
  gains a shim and the tier changes; `harness status --matrix` always tells the truth for the
  version you have.
- Repository level: Codex reads `AGENTS.md` up the directory tree and `.agents/skills`, which
  the hub does not manage. There is no hook, so `.harness.toml` `[overrides]` has no effect
  here; `[owns]` is honoured by skills at preflight and the rules tell the agent the
  repository's text wins ([repository-level harnesses](../repo-level.md#other-providers)).

## Troubleshooting

| Symptom | Fix |
|---|---|
| Codex ran a command the guard denies on other providers | expected on the advisory tier; tighten Codex's approval policy |
| `config.toml` parse error after apply | a hand edit broke the fence markers; restore from `~/.local/state/harness/backups/<ts>/` and `harness apply` |

<!-- generated:begin source=providers/codex/provider.toml -->
**Verified against:** verify on install (written to the published spec, 2026-09)

### Targets

| artifact | path | mode | details |
|---|---|---|---|
| instructions | `~/.codex/AGENTS.md` | managed-block |  |
| skills | `~/.codex/skills/<name>` | dir | registers in ~/.codex/config.toml [[skills]] |
| agents |  | inline | agent bodies become sections of AGENTS.md |
| settings |  | unsupported | config.toml is only touched through managed TOML blocks |
| hooks |  | unsupported | no verified pre-tool hook contract; rely on approval policy + instructions |
| permissions |  | unsupported | use approval_policy / sandbox_mode in config.toml |
| trust |  | unsupported |  |
| mcp | `~/.codex/config.toml` | toml-block | table=mcp_servers |

### Capabilities

| capability | value |
|---|---|
| agents | inlined |
| ask | false |
| hook_enforced | false |
| instructions | native |
| mcp | native |
| notes | guard rules are advisory (instructions only); prefer a strict approval_policy |
| permissions | advisory |
| skills | native |
<!-- generated:end -->
