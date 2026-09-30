# Provider: codex (OpenAI Codex CLI)

**Verified against:** not yet verified live — written to the published `config.toml`
specification (2026-09). **Verify on install.**

**The guard is advisory on Codex.** v1 wires no pre-tool command hook, so the shell rules
reach Codex only as instructions. Use a strict `approval_policy` / `sandbox_mode` in
`~/.codex/config.toml`; `harness status --matrix` shows this gap.

| artifact | where | how |
|---|---|---|
| instructions | `~/.codex/AGENTS.md` | managed blocks |
| skills | `~/.codex/skills/<name>/` | copied, and listed in a managed `[[skills]]` block (`path`, `enabled = true`) in `~/.codex/config.toml` |
| agents | inlined into `AGENTS.md` | one `## Agent: <name>` block per agent |
| MCP | `~/.codex/config.toml` | managed `[mcp_servers.<name>]` block (`command`, `args`, `env`) |

## Managed TOML blocks

`config.toml` is edited only between `# harness:begin block=<id>` and
`# harness:end block=<id>` comment lines, always at the end of the file. The merged file is
re-parsed before it is written; if it would be invalid (for example you already define
`[mcp_servers.<same name>]`), your file is kept and `plan` reports a conflict.

If your Codex build expects a different table for skill registration (for example
`[[skills.config]]`), change `targets.skills.register.table` in `provider.toml`; recent builds
also discover `~/.codex/skills` without any registration.
