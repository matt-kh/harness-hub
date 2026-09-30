# Reference: provider capability matrix

What each provider adapter declares it can do — guard hook, permission lists, skills, sub-agents,
MCP — and the resulting tier (enforced / partial / advisory). Generated from
`providers/*/provider.toml` `[capabilities]`; do not edit inside the generated region.
`harness status --matrix` prints the same table for the providers installed on your machine.

Per-provider details and quirks: [claude](../providers/claude.md), [gemini](../providers/gemini.md),
[copilot](../providers/copilot.md), [codex](../providers/codex.md), [opencode](../providers/opencode.md).
What the tiers mean for security: [SECURITY.md](../../SECURITY.md#what-the-guard-covers-per-provider).

<!-- generated:begin source=providers/*/provider.toml -->
| capability | claude | codex | copilot | gemini | opencode |
|---|---|---|---|---|---|
| guard hook | enforced | advisory | enforced | enforced | advisory |
| ask decision | native | - | mapped (ask_as) | mapped (ask_as) | - |
| permission lists | native | advisory | advisory | advisory | none |
| instructions | native | native | native | native | native |
| skills | native | native | native | native | native |
| agents | native | inlined | native | inlined | inlined |
| mcp | native | native | native | native | none |
<!-- generated:end -->
