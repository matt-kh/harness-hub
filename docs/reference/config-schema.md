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
| `kubernetes` | object |  |  | **Deprecated**, use `k8s`. Renamed to [k8s]. |
| `providers` | table of object |  |  | Per-provider options, keyed by provider name. |
| `schema_version` | integer |  |  | Configuration schema version. Bumped only with a CHANGELOG Migration entry. |
| `trust.buckets` | array | `[]` |  | Trusted storage buckets. |
| `trust.domains` | array | `[]` |  | Trusted internal domains. |
| `trust.environment` | array | `[]` |  | Raw autoMode.environment lines. When non-empty they are used verbatim instead of the generated lines. |
| `trust.notes` | string | `""` |  | Free text rendered under 'User-specific' (one line per line). |
| `trust.source_control` | array | `[]` |  | Trusted source-control scopes, e.g. github.com/octocat/*. |
<!-- generated:end -->
