# Provider: opencode (OpenCode and Kilo)

**Verified against:** not yet verified live — written to the published instruction and skill
locations (2026-09). Kilo reads the same locations. **Verify on install.**

Skills + instructions only in v1: there is **no hook and no permission list**, so every guard
rule is advisory here (`harness status --matrix`).

| artifact | where | how |
|---|---|---|
| instructions | `~/.config/opencode/AGENTS.md` | managed blocks |
| skills | `~/.agents/skills/<name>/` | copied (the cross-tool Agent Skills location) |
| agents | inlined into `AGENTS.md` | one `## Agent: <name>` block per agent |
| MCP | — | configure MCP servers in `opencode.json` by hand for now |

OpenCode also reads `~/.claude/CLAUDE.md` and `~/.claude/skills`; if you render both the
`claude` and `opencode` providers you may see the same skill twice — keep one of them.
