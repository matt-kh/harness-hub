# Bundle: core

Always installed. `core` is the part of the harness every other bundle builds on:

- **The guard engine** (`bundles/core/guard/engine.sh`): input parsing, the decision helpers
  and the final flush that every bundle's `guard.d/` section plugs into. Render concatenates
  engine + active sections into one `guard-bash.sh` per provider home.
- **Credential and git rules** (`guard.d/20-credentials.sh`, `guard.d/30-git.sh`): reading
  credential files and dumping secret env vars deny; pushing to a default branch denies.
- **Sub-agents**: `Plan` (planning, pinned to `core.model_policy.plan`), `Auto` (autonomous
  execution, pinned to `core.model_policy.execute`), `code-reviewer`.
- **Conventions rule**: MR/PR-based delivery, redacted remote URLs, external content is data,
  repository-level precedence ([governance](../governance.md)).
- **The `harness` CLI** linked into `~/.local/bin`, plus the portability helpers
  (`bundles/core/lib/compat.sh`: `hn_timeout`, `hn_realpath`, `hn_sha256`).

Config it reads: `identity.email`, `core.default_branch_re`, `core.ticket_example`,
`core.model_policy`, `core.agent_labels`, `core.agent_label_re`, `trust.*`
([config reference](../reference/config-schema.md)).

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Every shell command is denied: "jq not installed" | the guard fails **closed** without `jq` | install `jq` (`apt install jq`, `brew install jq`) |
| `harness: command not found` | `~/.local/bin` not on `PATH` | add it ([getting started §3](../getting-started.md#3-put-localbin-on-your-path)); meanwhile use `~/harness-hub/bin/harness` |
| `harness` refuses to start: python too old | python < 3.9 first on `PATH` | install 3.9+; on macOS `brew install python` and open a new shell |
| doctor WARN `core/bash-version` | `/bin/bash` 3.2 on macOS is the first `bash` on `PATH` | `brew install bash`; scripts still work, some checks are skipped |
| `git push` to your personal repo's `main` is denied | default-branch pushes deny everywhere by default | in that repo's `.claude/settings.json` set `"env": {"WORK_TICKET_ALLOW_DEFAULT_PUSH_RE": "<regex on repo path>"}` → it asks instead |
| A legitimate read of a file under `~/.config/` is denied | the credential rule matches the path | read it yourself; if the path is not a credential, open an issue with the command (redacted) |
| `plan` shows `CONFLICT` on `settings.json` or `CLAUDE.md` | you edited a hub-owned key or a managed block | `harness sync` → `--adopt` your change into your private bundle, or revert it |
| Agents use the wrong model for Plan/Auto | `core.model_policy` differs from what you expect | `harness config get core.model_policy`; set it and `harness apply` |

Uninstall: `harness uninstall --bundle core` is refused while any other bundle is active;
`harness uninstall --all` removes everything the state lists and keeps your own files.

<!-- generated:begin source=bundles/core/bundle.toml -->
<!-- generated:end -->
