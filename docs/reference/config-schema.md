# Reference: config schema

Every key `local/harness.toml` accepts, with its type, default, description, the bundles that
need it and deprecation status. Generated from `schema/harness-config.schema.json` compiled with
every bundle's `[requires.config]`; do not edit inside the generated region.

Layering and precedence: [concepts](../concepts.md#config-the-single-source-of-truth). Explain one
key on your machine, including which layer set it: `harness config explain <key>`.

<!-- generated:begin source=schema/harness-config.schema.json -->
Environment override for any key: `HARNESS_<SECTION>_<KEY>` (e.g. `HARNESS_JIRA_URL`).

| key | type | default | bundle | description |
|---|---|---|---|---|
| `core.agent_label_re` | string | `"^agent-"` | core | Any label / Drive marker matching this regex tags an artefact as agent-owned (WORK_TICKET_AGENT_LABEL_RE). |
| `core.agent_labels.created` | string |  |  |  |
| `core.agent_labels.drafted` | string |  |  |  |
| `core.agent_labels.worked` | string |  |  |  |
| `core.default_branch_re` | string | `"^(master\|main)$"` | core | Default/base branch regex: pushes to it are denied, sub MRs/PRs never target it (WORK_TICKET_BASE_BRANCH_RE). |
| `core.model_policy.execute` | string |  |  |  |
| `core.model_policy.plan` | string |  |  |  |
| `core.ticket_example` | string | `"PROJ-123"` | core | Example ticket key used in guard reasons, instructions and skill docs. |
| `credentials.extra_paths_re` | string | `""` | core | Extra ERE of credential paths the guard denies for readers (cat, grep, jq, cp, ...), on top of the built-in list (HARNESS_CRED_EXTRA_RE). Empty = none. |
| `doctor.warn_only` | array | `[]` |  | Doctor check ids downgraded from FAIL to WARN. |
| `github.host` | string | `"github.com"` | github | GitHub host: github.com or your GHES hostname. |
| `github.login` | string |  | github | Your GitHub login. Shown in the instructions; repos you own are trusted in the provider's auto-mode trust text. |
| `github.pr_title_forbid_re` | string | `"#[0-9]+"` | github | ERE a PR title must NOT match (issue refs belong in the body); empty disables. HARNESS_GITHUB_PR_TITLE_FORBID_RE. |
| `gitlab.host` | string |  | gitlab | Your GitLab host (self-managed hostname or gitlab.com). Used for auth, the instructions and work-ticket provider detection. |
| `gitlab.hosts_re` | string | `""` | gitlab | Optional regex of extra GitLab hosts for work-ticket provider detection (HARNESS_GITLAB_HOSTS_RE). Empty = gitlab.host plus any host containing 'gitlab'. |
| `gitlab.mr_title_re` | string | `"^[A-Z][A-Z0-9_]*-[0-9]+ "` | gitlab | ERE an MR title must match (ticket key first); empty disables the check. HARNESS_GITLAB_MR_TITLE_RE. |
| `gitlab.personal_repo_re` | string | `""` | gitlab | Regex on a repo's top-level path; where it matches, a push to the default branch asks instead of denying (personal repos). Repos can also set WORK_TICKET_ALLOW_DEFAULT_PUSH_RE themselves. |
| `google.domain` | string |  | gdoc | Your Workspace domain. Sign-in is restricted to it (OAuth `hd`, GDOC_HD) and the GCP project must live inside this organisation for an Internal consent screen. |
| `harness` | object |  |  | **Deprecated**, use `hub`. Renamed to [hub]. |
| `hub.bundle_paths` | array |  |  | Extra directories containing bundles (relative to the config file). <config dir>/bundles is always searched. |
| `hub.bundles` | array |  |  | Active bundles. Dependencies (depends_on) are added automatically. |
| `hub.profile` | string |  |  | Named selection from profiles/<name>.toml; explicit bundles/providers lists win. |
| `hub.providers` | array |  |  | Agent providers to render into. |
| `identity.email` | string |  | core | Your work email; shown in the instructions and used as the OAuth account hint. Never used as a commit author by the hub. |
| `identity.name` | string |  |  | Display name (optional). |
| `jira.fields` | table of tables | `{}` | jira | Friendly custom-field names per project, from `jira fields PROJ`: [jira.fields.PROJ] story_points = "customfield_…". Lower-case keys at the top level apply to every project. Used by the jira CLI and create-ticket; ids are never guessed. |
| `jira.get_exclude` | array | `[]` | jira | Friendly field names (from jira.fields) that `jira get` should not surface; they still resolve for set/create. HARNESS_JIRA_GET_EXCLUDE (comma-separated) overrides. |
| `jira.issue_types` | array | `[]` | jira | Optional per-org issue-type rules for create-ticket: [[jira.issue_types]] name, standalone, requires, requires_without_facts, body_field, hint. Empty = generic (Epic requires epic_name). |
| `jira.kind` | string | `"server"` | jira | Jira flavour. Only `server` (Server / Data Center 8.x, PAT bearer auth, plain-text bodies) is implemented. |
| `jira.link_types` | array | `["relates", "blocks", "issue split"]` | jira | Link type names (case-insensitive) the guard permits for `jira link` / `create --link` (HARNESS_JIRA_LINK_TYPES). |
| `jira.mcp.enabled` | boolean | `true` | jira | Register the read-only jira-mcp server (uvx mcp-atlassian, READ_ONLY_MODE=true). |
| `jira.url` | string |  | jira | Base URL of your Jira Server, no trailing slash. The CLI exits 2 with 'not configured' until it is set. |
| `k8s.broken_contexts` | array | `[]` | k8s | Contexts known to be broken (Unauthorized, TLS SAN mismatch); documentation for the org notes and doctor, never used to skip a context silently. |
| `k8s.clusters_doc` | string | `"~/.local/state/harness/k8s/clusters.md"` | k8s | File `k8s contexts --write` regenerates (a relative path is under HARNESS_HOME, e.g. a private bundle's references/). K8S_CLUSTERS_MD. |
| `k8s.gitops_repo_match` | string | `""` | k8s | Substring of an Application's repoURL that marks it as that checkout. Empty = the basename of k8s.gitops_root. K8S_GITOPS_REPO_MATCH. |
| `k8s.gitops_root` | string | `""` | k8s | Local checkout of your GitOps repo; `k8s argocd` maps spec.source.path into it. Empty = the local-path check is skipped. K8S_GITOPS_ROOT. |
| `k8s.known_broken_contexts` | array |  |  | **Deprecated**, use `k8s.broken_contexts`. |
| `k8s.prod_re` | string | `"(^\|[-_./:])(prod\|production)([-_./:]\|$)"` | k8s | Case-insensitive ERE on context and namespace names marking production ([PROD] banner; remediations become suggestions only). K8S_PROD_RE. |
| `k8s.redact_extra_re` | string | `""` | k8s | Extra Python regex of token shapes masked on top of the built-in list, applied by `k8s redact`, the log tails of `k8s pod`/`k8s workload` and `helm --values`; event and container status messages are not redacted. K8S_REDACT_EXTRA_RE. |
| `kubernetes` | object |  |  | **Deprecated**, use `k8s`. Renamed to [k8s]. |
| `lessons.correction_re` | string | `"^(no([,.!]\|$\| (that\|this\|it\|you\|i\|not\|wait\|stop)([ ,.!']\|$))\|nope\|wrong\|incorrect\|that'?s not\|not what i\|i (said\|asked\|meant\|told you\|wanted)\|you (didn'?t\|did not\|ignored\|missed\|forgot\|broke\|changed)\|undo\|revert (that\|this\|it)\|redo\|try again\|again[,.!]?$\|still (wrong\|broken\|failing\|not))"` | core | POSIX ERE, applied case-insensitively (grep -Eiq) to a prompt, that classifies it as a correction when lessons.prompt_signals is on. Only the class name is recorded, never the prompt (HARNESS_LESSONS_CORRECTION_RE). |
| `lessons.dir` | string | `""` | core | Directory of the private lessons library that `harness lessons` reads and writes (one <domain>-NNN.md record per lesson plus INDEX.md). Empty = ~/.local/state/harness/lessons (under $XDG_STATE_HOME when set). The CLI refuses a directory under the hub checkout or inside any git checkout: lessons stay on the workstation and never enter a repository. |
| `lessons.dissatisfaction_re` | string | `"(frustrat\|annoy\|unacceptable\|stop (doing\|that)\|why (did\|do\|are) you\|don'?t (do (that\|this)\|ever)\|you keep\|this is (wrong\|bad\|useless))"` | core | POSIX ERE, applied case-insensitively (grep -Eiq) to a prompt, that classifies it as dissatisfaction when lessons.prompt_signals is on. Only the class name is recorded, never the prompt (HARNESS_LESSONS_DISSATISFACTION_RE). |
| `lessons.index_max` | integer | `40` | core | Most lessons INDEX.md lists overall (confirmed, recurring and proposed first); the rest are counted, never listed. |
| `lessons.index_max_candidates` | integer | `5` | core | Most unconfirmed candidate lessons INDEX.md lists per domain (newest update first); the rest appear as "N more candidates", so a run of bad retros cannot flood the index. |
| `lessons.journal` | boolean | `false` | core | Opt-in guard journal: on every guard ask or deny, append one line to ~/.local/state/harness/journal/<date>.log with the timestamp, provider, session id, kind (guard-ask \| guard-deny), rule site (section function and line), guard id and repository basename, and point ~/.local/state/harness/retro/current at the session. Never recorded: command text, prompt text, paths, reasons. Stays on the workstation (HARNESS_LESSONS_JOURNAL). |
| `lessons.max_age_days` | integer | `90` | core | Days without an update after which a lesson is shown stale in INDEX.md and `harness lessons list --stale`; `harness lessons index --prune` retires stale candidates. |
| `lessons.promote_after` | integer | `3` | core | Objective recurrences (`harness lessons note --recurred` with a journal: evidence ref) after which a candidate lesson becomes recurring, which `harness lessons propose` accepts like a confirmed one. |
| `lessons.prompt_signals` | boolean | `false` | core | Opt-in prompt signals (hook shipped by the lessons bundle): a prompt matching lessons.correction_re or lessons.dissatisfaction_re adds one journal line whose kind is the class name (correction \| dissatisfaction) and whose other fields are the timestamp, provider, session id, guard id and repository basename. Never recorded: prompt text, command text, paths (HARNESS_LESSONS_PROMPT_SIGNALS). |
| `lessons.review.corrections` | integer | `2` | core | `harness lessons review` is due when one session has at least this many correction journal lines. 0 disables this criterion. |
| `lessons.review.denies` | integer | `3` | core | `harness lessons review` is due when one session has at least this many guard-deny journal lines. 0 disables this criterion. |
| `lessons.review.dissatisfaction` | integer | `1` | core | `harness lessons review` is due when one session has at least this many dissatisfaction journal lines. 0 disables this criterion. |
| `obs.backends` | array | `[]` | obs | Observability backends, as [[obs.backends]] tables: name, kind (signoz \| prometheus \| grafana), url, auth_file (a key file under ~/.config/obs, mode 0600; optional for prometheus). Never the key itself. |
| `obs.default` | string | `""` | obs | Backend name `obs` uses without --backend. Empty = the first entry of obs.backends. |
| `obs.hosts_re` | string | `""` | obs | POSIX ERE (the guard applies it with grep -E) matching your backends' host names (no scheme, no port); raw curl/wget/http/xh to a matching host asks (guard section 32). Use [0-9], [A-Za-z0-9_] and [[:space:]], never \d, \w, \s or (?…): `obs backends` and doctor check it with grep -E and flag Python-only syntax. Empty = those rows are off; doctor warns when backends exist. OBS_HOSTS_RE. |
| `obs.log_tail` | integer | `200` | obs | Default number of lines `obs logs` returns (--limit overrides). |
| `obs.max_bytes` | integer | `65536` | obs | Default output cap in bytes (--max-bytes overrides); `dashboards --export` refuses larger files. |
| `obs.prod_re` | string | `"(^\|[-_./:])(prod\|production)([-_./:]\|$)"` | obs | Case-insensitive ERE on backend names and hosts marking production ([PROD] banner; remediations become suggestions only). OBS_PROD_RE. |
| `obs.redact_extra_re` | string | `""` | obs | Extra Python regex of token shapes every obs output redacts in addition to the built-in list; compiled on its own, so a leading global flag such as (?i) works. OBS_REDACT_EXTRA_RE. |
| `providers` | table of object |  |  | Per-provider options, keyed by provider name. |
| `schema_version` | integer |  |  | Configuration schema version. Bumped only with a CHANGELOG Migration entry. |
| `stack.label` | string | `"stack"` | stack | Label that selects stacks when neither refs nor --stack are given (the stacks of open MRs/PRs carrying it). HARNESS_STACK_LABEL. |
| `stack.leaf_refresh` | string | `"auto"` | stack | auto: `stk sync` rebases at most one fan-in leaf server-side per run, and only when the merge method needs an up-to-date source (GitLab ff / rebase_merge, a GitHub "up to date" rule); never: report it only. HARNESS_STACK_LEAF_REFRESH. |
| `stack.push` | boolean | `true` | stack | `stk sync` pushes the rebased sub branches with --force-with-lease; false rebases locally and prints the push commands (like --no-push). HARNESS_STACK_PUSH (true\|false). |
| `stack.update_method` | string | `"rebase"` | stack | GitHub leaf refresh: `gh pr update-branch --rebase` (rebase) or a merge commit from the base (merge). GitLab always rebases (`glab mr rebase`). HARNESS_STACK_UPDATE_METHOD. |
| `ticket_workflow.trackers` | array | `[]` | ticket-workflow | Which tracker each repository uses, by origin remote: [[ticket_workflow.trackers]] match (ERE on <host>/<path>, case-insensitive), tracker (github-issues or jira), project (jira only: create-ticket's default project). First match wins; a repository's .harness.toml [repo] tracker wins over it; no match = the host decides (github.com -> github-issues, GitLab -> jira). |
| `trust.buckets` | array | `[]` |  | Trusted storage buckets. |
| `trust.domains` | array | `[]` |  | Trusted internal domains. |
| `trust.environment` | array | `[]` |  | Raw autoMode.environment lines. When non-empty they are used verbatim instead of the generated lines. |
| `trust.notes` | string | `""` |  | Free text rendered under 'User-specific' (one line per line). |
| `trust.source_control` | array | `[]` |  | Trusted source-control scopes, e.g. github.com/octocat/*. |
<!-- generated:end -->
