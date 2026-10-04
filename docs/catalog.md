# Catalog

Every bundle, component, provider and profile this hub ships, with its stable id and its
[taxonomy](reference/taxonomy.md) facets. The same list on the command line: `harness catalog`
(`--kind`, `--bundle`, `--domain`, `--json`). Private bundles are listed there, never here.

<!-- generated:begin source=bundles/*/bundle.toml#catalog -->
## Bundles

**Reach:** selected in `[hub].bundles` or through a profile; rendered into every active provider.

| id | domain | posture | functions | stability | summary |
|---|---|---|---|---|---|
| [`core`](bundles/core.md#components) | base | local | govern, plan, execute, review, setup | stable | Guard engine, credential and git rules, conventions, Plan / Auto / code-reviewer agents |
| [`gdoc`](bundles/gdoc.md#components) | workspace | label-gated | govern, client, setup | beta | gdoc CLI for Google Docs / Drive / Sheets / Gmail with provenance-gated writes; drafts only, never sends |
| [`github`](bundles/github.md#components) | scm | label-gated | govern, setup | stable | GitHub CLI, PR-based workflow, GitHub Issues as the tracker, gh governance rules |
| [`gitlab`](bundles/gitlab.md#components) | scm | label-gated | govern, setup | stable | GitLab via glab: MR-based workflow, agent-label write gates, stacked-MR rules, Jira closing-keyword deny |
| [`jira`](bundles/jira.md#components) | tracker | label-gated | govern, client, setup | stable | Jira Server client (jira CLI + skill), read-only jira-mcp server, Jira write governance in the guard |
| [`k8s`](bundles/k8s.md#components) | kubernetes | read-only | govern, client, investigate, plan, review, setup | stable | Read-only Kubernetes client (k8s CLI + skill), triage / audit / architect agents, kubeconfig and Secret guards |
| [`ticket-workflow`](bundles/ticket-workflow.md#components) | delivery | label-gated | govern, workflow, setup | beta | /work-ticket (ticket → governed MR/PR, stacked delivery) and /create-ticket (one drafted ticket or issue) |

## Skills

**Reach:** native on claude, codex, copilot, gemini, opencode.

| id | control | domain | function | posture | model | summary |
|---|---|---|---|---|---|---|
| `gdoc/skills/gdoc` | guide | workspace | client | label-gated | execute | Read, write and search the user's corporate Google Workspace ({{ google.domain }}) — Google Docs, Drive, Sheets and Gmail — with the `gdoc` CLI. |
| `jira/skills/jira` | guide | tracker | client | label-gated | execute | Interact with the org's self-hosted Jira Server ({{ jira.url }}) — read/search/update tickets, sprints, versions, transitions, attachments, comments. |
| `k8s/skills/k8s` | guide | kubernetes | client | read-only | execute | Read-only Kubernetes operator client for every context in the user's kubeconfig via the `k8s` CLI and explicit-context kubectl. |
| `ticket-workflow/skills/create-ticket` | guide | delivery | workflow | label-gated | execute | Create ONE Jira ticket (self-hosted Jira Server 8.x) from the user's free-text ask in any project they can create in (discovered, never hardcoded). |
| `ticket-workflow/skills/work-ticket` | guide | delivery | workflow | label-gated | execute | Governed Jira-ticket → GitLab-MR workflow for any repo. |

## Agents

**Reach:** native on claude, copilot; inlined on codex, gemini, opencode.

| id | control | domain | function | posture | model | summary |
|---|---|---|---|---|---|---|
| `core/agents/Auto` | guide | base | execute | local | execute | Execution agent pinned to {{ core.model_policy.execute }} — the auto-mode counterpart to Plan. |
| `core/agents/Plan` | guide | base | plan | read-only | plan | Software architect agent for designing implementation plans. |
| `core/agents/code-reviewer` | sensor (inferential) | base | review | read-only | execute | Expert code review specialist. |
| `k8s/agents/infra-architect` | guide | kubernetes | plan | read-only | plan | Use this agent for expert guidance on infrastructure design, platform architecture, or DevOps strategy — advisory/planning only. |
| `k8s/agents/k8s-auditor` | guide | kubernetes | review | read-only | execute | Read-only Kubernetes posture review of a context or namespace — pod security, PSA labels, RBAC, Secret hygiene, certificate expiry, capacity headroom, deprecat… |
| `k8s/agents/k8s-triage` | guide | kubernetes | investigate | read-only | execute | Read-only Kubernetes incident triage. |

## Rules

**Reach:** native on claude, codex, copilot, gemini, opencode.

| id | control | domain | summary |
|---|---|---|---|
| `core/rules/00-conventions` | guide | base | Global conventions |
| `k8s/rules/10-k8s` | guide | kubernetes | Kubernetes |
| `gitlab/rules/50-gitlab` | guide | scm | GitLab ({{ gitlab.host }}) |
| `github/rules/60-github` | guide | scm | GitHub ({{ github.host }}) |
| `jira/rules/70-jira` | guide | tracker | Jira ({{ jira.url }}) |
| `ticket-workflow/rules/75-ticket-workflow` | guide | delivery | Ticket workflow |
| `gdoc/rules/80-gdoc` | guide | workspace | Google Workspace ({{ google.domain }}) |

## Guard sections

**Reach:** enforced on claude; partial on copilot, gemini; advisory on codex, opencode.

| id | control | domain | decisions | note |
|---|---|---|---|---|
| [`k8s/guard.d/10-k8s`](reference/hook-policy.md) | sensor | kubernetes | helper (no rules) | kubectl/helm clause parsing shared by the rules section |
| [`core/guard.d/20-credentials`](reference/hook-policy.md) | sensor | base | deny 7 | denies credential file reads and secret env dumps before they run |
| [`k8s/guard.d/25-k8s-rules`](reference/hook-policy.md) | sensor | kubernetes | deny 4 · ask 7 | kubeconfig, Secret data, cluster, release, GitOps and IaC mutations |
| [`core/guard.d/30-git`](reference/hook-policy.md) | sensor | scm | deny 1 · ask 5 | denies default-branch pushes; asks on force-push and destructive git |
| [`gitlab/guard.d/40-gitlab-closing`](reference/hook-policy.md) | sensor | tracker | deny 1 | denies closing keywords with a ticket key |
| [`github/guard.d/41-github-closing`](reference/hook-policy.md) | sensor | tracker | deny 1 | denies closing keywords that would change issue state |
| [`gitlab/guard.d/50-gitlab`](reference/hook-policy.md) | sensor | scm | ask 2 · allow 3 | API writes, merges/approvals, stacked MR targets, label-gated edits |
| [`github/guard.d/60-github`](reference/hook-policy.md) | sensor | scm | deny 2 · ask 2 · allow 3 | token printing, API writes, merges/reviews, provenance labels, stacked PR targets |
| [`jira/guard.d/70-jira`](reference/hook-policy.md) | sensor | tracker | deny 3 · ask 1 · allow 4 | label-gated writes, provenance label on create, transitions denied on human tickets |
| [`gdoc/guard.d/80-gdoc`](reference/hook-policy.md) | sensor | workspace | deny 1 · ask 2 · allow 2 | GET-only api, provenance check before writes, ask on mark and mail send |

## Permission lists

**Reach:** native on claude; advisory on codex, copilot, gemini; none on opencode.

| id | control | domain | decisions | note |
|---|---|---|---|---|
| `core/permissions` | guide | base | deny 11 · allow 1 | denies reads of credential files in the provider's own permission system |
| `gdoc/permissions` | guide | workspace | ask 1 · allow 12 | read commands allowed, writes left to the guard |
| `github/permissions` | guide | scm | deny 1 · ask 75 · allow 32 | read-only gh commands allowed; token printing denied |
| `gitlab/permissions` | guide | scm | ask 11 · allow 13 | read-only glab commands allowed |
| `jira/permissions` | guide | tracker | allow 12 | read commands allowed; writes left to the guard |
| `k8s/permissions` | guide | kubernetes | deny 12 · ask 45 · allow 42 | read-only kubectl/helm allowed |
| `ticket-workflow/permissions` |  | delivery | empty (no rules) |  |

## MCP servers

**Reach:** native on claude, codex, copilot, gemini; none on opencode.

| id | domain | posture | note |
|---|---|---|---|
| `jira/mcp/jira-mcp` | tracker | read-only | runs `uvx mcp-atlassian` |

## CLIs

**Reach:** provider-independent: linked into `~/.local/bin`, callable by every provider and by you.

| id | domain | posture | target |
|---|---|---|---|
| `gdoc/bin/gdoc` | workspace | label-gated | `skills/gdoc/scripts/gdoc.py` |
| `jira/bin/jira` | tracker | label-gated | `skills/jira/scripts/jira.py` |
| `k8s/bin/k8s` | kubernetes | read-only | `skills/k8s/scripts/k8s.py` |

## Installers

**Reach:** provider-independent: run by `harness install <tool>`.

| id | domain | script |
|---|---|---|
| `github/install/gh` | scm | `install/gh.sh` |

## Doctor checks

**Reach:** provider-independent: run by `harness doctor`.

| id | control | domain | title |
|---|---|---|---|
| [`core/doctor/bash-version`](bundles/core.md#doctor-checks) | sensor | base | bash >= 4 on PATH |
| [`core/doctor/guard-denies-credentials`](bundles/core.md#doctor-checks) | sensor | base | Guard denies reading a credential file |
| [`core/doctor/guard-hook`](bundles/core.md#doctor-checks) | sensor | base | Guard hook rendered, non-empty, executable and parses |
| [`core/doctor/jq`](bundles/core.md#doctor-checks) | sensor | base | jq installed |
| [`core/doctor/local-bin-path`](bundles/core.md#doctor-checks) | sensor | base | ~/.local/bin on PATH |
| [`core/doctor/python3`](bundles/core.md#doctor-checks) | sensor | base | python3 >= 3.9 |
| [`gdoc/doctor/gdoc-auth`](bundles/gdoc.md#doctor-checks) | sensor | workspace | gdoc signed in |
| [`gdoc/doctor/gdoc-cli`](bundles/gdoc.md#doctor-checks) | sensor | workspace | gdoc CLI on PATH |
| [`gdoc/doctor/gdoc-client`](bundles/gdoc.md#doctor-checks) | sensor | workspace | OAuth Desktop client installed |
| [`gdoc/doctor/gdoc-modes`](bundles/gdoc.md#doctor-checks) | sensor | workspace | ~/.config/gdoc is 0700 and its files 0600 |
| [`github/doctor/gh-auth`](bundles/github.md#doctor-checks) | sensor | scm | gh authenticated to {{ github.host }} |
| [`github/doctor/gh-binary`](bundles/github.md#doctor-checks) | sensor | scm | gh installed |
| [`github/doctor/gh-ssh`](bundles/github.md#doctor-checks) | sensor | scm | SSH to {{ github.host }} works |
| [`github/doctor/gh-token-mode`](bundles/github.md#doctor-checks) | sensor | scm | gh hosts.yml is private (0600) |
| [`gitlab/doctor/gitlab-ssh`](bundles/gitlab.md#doctor-checks) | sensor | scm | SSH to {{ gitlab.host }} works |
| [`gitlab/doctor/glab-auth`](bundles/gitlab.md#doctor-checks) | sensor | scm | glab authenticated to {{ gitlab.host }} |
| [`gitlab/doctor/glab-binary`](bundles/gitlab.md#doctor-checks) | sensor | scm | glab installed |
| [`gitlab/doctor/glab-token-mode`](bundles/gitlab.md#doctor-checks) | sensor | scm | glab config is private (0600) |
| [`jira/doctor/jira-auth`](bundles/jira.md#doctor-checks) | sensor | tracker | jira whoami succeeds against {{ jira.url }} |
| [`jira/doctor/jira-cli`](bundles/jira.md#doctor-checks) | sensor | tracker | jira CLI on PATH |
| [`jira/doctor/jira-token-file`](bundles/jira.md#doctor-checks) | sensor | tracker | ~/.config/jira present and private (0600) |
| [`jira/doctor/uvx`](bundles/jira.md#doctor-checks) | sensor | tracker | uvx available for jira-mcp |
| [`k8s/doctor/clusters-doc`](bundles/k8s.md#doctor-checks) | sensor | kubernetes | clusters doc generated |
| [`k8s/doctor/helm-binary`](bundles/k8s.md#doctor-checks) | sensor | kubernetes | helm installed |
| [`k8s/doctor/k8s-cli`](bundles/k8s.md#doctor-checks) | sensor | kubernetes | k8s CLI on PATH |
| [`k8s/doctor/kube-contexts`](bundles/k8s.md#doctor-checks) | sensor | kubernetes | kubeconfig has at least one context |
| [`k8s/doctor/kubectl-binary`](bundles/k8s.md#doctor-checks) | sensor | kubernetes | kubectl installed |
| [`ticket-workflow/doctor/ticket-workflow-scm`](bundles/ticket-workflow.md#doctor-checks) | sensor | delivery | An SCM CLI is on PATH (glab or gh) |
| [`ticket-workflow/doctor/ticket-workflow-skills`](bundles/ticket-workflow.md#doctor-checks) | sensor | delivery | work-ticket and create-ticket skills rendered |
| [`ticket-workflow/doctor/ticket-workflow-tracker`](bundles/ticket-workflow.md#doctor-checks) | sensor | delivery | A tracker CLI is on PATH (jira or gh) |

## Manual steps

**Reach:** provider-independent: done once by a human; `harness steps --pending` lists the open ones.

| id | domain | title |
|---|---|---|
| [`core/steps/bash4`](bundles/core.md#bash4) | base | Use bash >= 4 (macOS ships 3.2) |
| [`core/steps/install-jq`](bundles/core.md#install-jq) | base | Install jq (the guard fails closed without it) |
| [`core/steps/local-bin-path`](bundles/core.md#local-bin-path) | base | Put ~/.local/bin on your PATH |
| [`gdoc/steps/admin-trust`](bundles/gdoc.md#admin-trust) | workspace | Admin allow-list (only if sign-in says 'blocked by your administrator') |
| [`gdoc/steps/consent-screen`](bundles/gdoc.md#consent-screen) | workspace | Configure the OAuth consent screen as Internal |
| [`gdoc/steps/desktop-client`](bundles/gdoc.md#desktop-client) | workspace | Create a Desktop OAuth client and install its JSON |
| [`gdoc/steps/enable-apis`](bundles/gdoc.md#enable-apis) | workspace | Enable the Drive, Docs, Sheets and Gmail APIs |
| [`gdoc/steps/gcp-project`](bundles/gdoc.md#gcp-project) | workspace | Create a GCP project inside your organisation |
| [`gdoc/steps/gdoc-login`](bundles/gdoc.md#gdoc-login) | workspace | Sign in |
| [`github/steps/agent-labels`](bundles/github.md#agent-labels) | scm | Create the agent-* labels in repos you will work in (optional, per repo) |
| [`github/steps/gh-auth`](bundles/github.md#gh-auth) | scm | Authenticate gh (browser device flow, PAT fallback) |
| [`github/steps/install-gh`](bundles/github.md#install-gh) | scm | Install the GitHub CLI |
| [`github/steps/ssh-key`](bundles/github.md#ssh-key) | scm | Register an SSH key with GitHub |
| [`gitlab/steps/gitlab-agent-labels`](bundles/gitlab.md#gitlab-agent-labels) | scm | Create the agent-* labels in the groups you work in (optional) |
| [`gitlab/steps/gitlab-ssh-key`](bundles/gitlab.md#gitlab-ssh-key) | scm | Register an SSH key with {{ gitlab.host }} |
| [`gitlab/steps/glab-auth`](bundles/gitlab.md#glab-auth) | scm | Authenticate glab to {{ gitlab.host }} |
| [`gitlab/steps/install-glab`](bundles/gitlab.md#install-glab) | scm | Install the GitLab CLI (glab) |
| [`jira/steps/install-uv`](bundles/jira.md#install-uv) | tracker | Install uv (for the read-only jira-mcp server) |
| [`jira/steps/jira-fields`](bundles/jira.md#jira-fields) | tracker | Record your projects' custom field ids in harness.toml (optional) |
| [`jira/steps/jira-pat`](bundles/jira.md#jira-pat) | tracker | Create a Jira personal access token and store it in ~/.config/jira |
| [`k8s/steps/clusters-doc`](bundles/k8s.md#clusters-doc) | kubernetes | Generate the clusters doc |
| [`k8s/steps/gitops-checkout`](bundles/k8s.md#gitops-checkout) | kubernetes | Clone your GitOps repo and set k8s.gitops_root (optional) |
| [`k8s/steps/install-kubectl`](bundles/k8s.md#install-kubectl) | kubernetes | Install kubectl (and helm) |
| [`k8s/steps/kubeconfig-contexts`](bundles/k8s.md#kubeconfig-contexts) | kubernetes | Merge your clusters' kubeconfig contexts (human-managed) |
| [`ticket-workflow/steps/repo-overrides`](bundles/ticket-workflow.md#repo-overrides) | delivery | Know the per-repo opt-outs (read once) |

## Providers

**Reach:** the tier: enforced (guard hook with ask), partial (guard hook, ask mapped), advisory (no hook).

| id | tier | summary |
|---|---|---|
| [`providers/claude`](providers/claude.md) | enforced | Claude Code CLI |
| [`providers/codex`](providers/codex.md) | advisory | OpenAI Codex CLI |
| [`providers/copilot`](providers/copilot.md) | partial | GitHub Copilot CLI |
| [`providers/gemini`](providers/gemini.md) | partial | Gemini CLI |
| [`providers/opencode`](providers/opencode.md) | advisory | OpenCode / Kilo |

## Profiles

**Reach:** a named bundle and provider selection: `[hub].profile` or `harness bootstrap --profile`.

| id | domains | posture | bundles | providers | summary |
|---|---|---|---|---|---|
| `profiles/github-dev` | base, scm, delivery | label-gated | core, github, ticket-workflow | claude | GitHub SCM + Issues, ticket workflow, Claude Code |
| `profiles/gitlab-jira` | base, scm, tracker, delivery | label-gated | core, gitlab, jira, ticket-workflow | claude | GitLab MRs + Jira tickets, ticket workflow, Claude Code |
| `profiles/minimal` | base | local | core | claude | core only, Claude Code |
| `profiles/platform-engineer` | base, scm, tracker, delivery, kubernetes, workspace | label-gated | core, gitlab, github, jira, ticket-workflow, k8s, gdoc | claude, gemini | GitLab + GitHub + Jira + k8s + gdoc, Claude Code and Gemini CLI |
<!-- generated:end -->

## Posture by domain

<!-- generated:begin source=bundles/*/bundle.toml#posture -->
Skills, agents, CLIs and MCP servers by domain and posture (the strongest effect without a human prompt, weakest first).

| domain | read-only | local | label-gated |
|---|---|---|---|
| base | `core/agents/Plan`, `core/agents/code-reviewer` | `core/agents/Auto` | — |
| scm | — | — | — |
| tracker | `jira/mcp/jira-mcp` | — | `jira/bin/jira`, `jira/skills/jira` |
| delivery | — | — | `ticket-workflow/skills/create-ticket`, `ticket-workflow/skills/work-ticket` |
| kubernetes | `k8s/agents/infra-architect`, `k8s/agents/k8s-auditor`, `k8s/agents/k8s-triage`, `k8s/bin/k8s`, `k8s/skills/k8s` | — | — |
| workspace | — | — | `gdoc/bin/gdoc`, `gdoc/skills/gdoc` |
<!-- generated:end -->

Posture says what a component does without a prompt; which writes stay with a human whatever
the posture is in [governance §9 "Who does what"](governance.md#9-who-does-what).
