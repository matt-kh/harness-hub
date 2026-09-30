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

## Troubleshooting

| Symptom | Fix |
|---|---|
| Skills not found | check `~/.agents/skills/<name>/SKILL.md` exists; `harness apply --provider opencode` |
| Rules appear twice | see the first quirk above |

<!-- generated:begin source=providers/opencode/provider.toml -->
<!-- generated:end -->
