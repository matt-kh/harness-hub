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
| subagent deny (merge, state) | native | - | mapped (ask_as) | mapped (ask_as) | - |
| permission lists | native | advisory | advisory | advisory | none |
| instructions | native | native | native | native | native |
| skills | native | native | native | native | native |
| agents | native | inlined | native | inlined | inlined |
| mcp | native | native | native | native | none |
| extra hook events (prompt, stop) | prompt, stop | - | prompt, stop | prompt, stop | - |
<!-- generated:end -->

**subagent deny (merge, state)** — how the guard treats a human decision (merge, approve,
PR/MR, issue or ticket state) from a sub-agent, from `[capabilities] subagent_identity`
([ARCHITECTURE §5](../../ARCHITECTURE.md#5-guard)):

| value | meaning |
|---|---|
| `native` | the hook input identifies a sub-agent caller (`agent_id`): the guard denies it there and asks the main thread |
| `ask only` | the hook can ask but cannot tell the caller apart: every caller is asked |
| `mapped (ask_as)` | the hook cannot ask and cannot tell the caller apart: every caller gets `[providers.<name>].ask_as` (default deny) |
| `-` | no enforced hook: the rule is advisory (instructions only) |
