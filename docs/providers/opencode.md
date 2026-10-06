# OpenCode / Kilo

**Tier: advisory.** Instructions and skills only: no command hook, no managed permission lists,
MCP left to you. Useful when you run several agents side by side and want them to share the
same skills and rules.

| | |
|---|---|
| Binary | `opencode` (Kilo reads the same locations) |
| Home | `~/.config/opencode` |
| Instructions | `~/.config/opencode/AGENTS.md`, managed blocks |
| Skills | `~/.agents/skills/<name>/` (shared Agent Skills location) |
| Sub-agents | inlined as instruction sections |
| Guard | none (advisory) |
| MCP | not managed by the hub |

## Quirks

- OpenCode and Kilo also read `~/.claude/CLAUDE.md` and `~/.claude/skills` when present. If you
  enable both `claude` and `opencode`, the same rules may be loaded twice; that is harmless but
  wastes context. Enable only the provider you actually run, or accept the duplication.
- Kilo keeps its own `~/.kilo/skills`; the hub does not write there.
- Repository level: OpenCode and Kilo read `AGENTS.md` up the directory tree and
  `.agents/skills`, which the hub does not manage. There is no hook, so `.harness.toml`
  `[overrides]` has no effect here; `[owns]` is honoured by skills at preflight and the rules
  tell the agent the repository's text wins
  ([repository-level harnesses](../repo-level.md#other-providers)).

## Troubleshooting

| Symptom | Fix |
|---|---|
| Skills not found | check `~/.agents/skills/<name>/SKILL.md` exists; `harness apply --provider opencode` |
| Rules appear twice | see the first quirk above |

<!-- generated:begin source=providers/opencode/provider.toml -->
**Verified against:** verify on install (written to the published spec, 2026-09)

### Targets

| artifact | path | mode | details |
|---|---|---|---|
| instructions | `~/.config/opencode/AGENTS.md` | managed-block |  |
| skills | `~/.agents/skills/<name>` | dir | the cross-tool Agent Skills location, also read by Kilo |
| agents |  | inline | agent bodies become sections of AGENTS.md |
| settings |  | unsupported |  |
| hooks |  | unsupported | no command hook |
| permissions |  | unsupported |  |
| trust |  | unsupported |  |
| mcp |  | unsupported | configure MCP in opencode.json by hand for now |

### Capabilities

| capability | value |
|---|---|
| agents | inlined |
| ask | false |
| hook_enforced | false |
| instructions | native |
| mcp | none |
| notes | advisory only: no hook, no permission lists |
| permissions | none |
| skills | native |
<!-- generated:end -->
