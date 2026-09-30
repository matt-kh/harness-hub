# Reference: secrets

Where every credential used by an active bundle lives, which tool writes it, the file mode it
should have and how to rotate it. Generated from every bundle's `[requires.secrets]`; do not edit
inside the generated region.

The hub never reads, copies or prints these files, and `harness.toml` must never contain a
secret: validation rejects keys named `*token*`, `*secret*`, `*password*`, `*bearer*` and long
high-entropy values. MCP servers receive tokens by **file reference** (`env_files`), resolved when
the provider starts the server; naming the path in config is not a leak.

<!-- generated:begin source=bundles/*/bundle.toml -->
| secret | bundle | where | written by | mode | rotate | notes |
|---|---|---|---|---|---|---|
| `gdoc_client` | gdoc | `~/.config/gdoc/client_secret.json` | human (downloaded from the GCP console) | 0600 |  | OAuth Desktop client. Not a bearer credential on its own; still never printed (`gdoc auth status` reports presence and mode). |
| `gdoc_token` | gdoc | `~/.config/gdoc/token.json` | gdoc auth login | 0600 | docs/runbooks/rotate-google-oauth.md | Refresh + access token. |
| `gh_token` | github | `~/.config/gh/hosts.yml` | gh auth login | 0600 | docs/runbooks/rotate-github-token.md | OAuth token / PAT stored by gh. The hub never reads or writes it; the guard denies agents reading it and `gh auth token`. |
| `glab_token` | gitlab | `~/.config/glab-cli/config.yml` | glab auth login | 0600 | docs/runbooks/rotate-gitlab-token.md | Personal access token stored by glab. The hub never reads it; the guard and the permission rules deny agents reading it. |
| `jira_pat` | jira | `~/.config/jira` | human (Jira profile → Personal Access Tokens) | 0600 | docs/runbooks/rotate-jira-token.md | Personal access token, one line. Read by the jira CLI and injected into jira-mcp at launch; never printed, never in harness.toml. The guard denies agents reading it. |
| `kubeconfig` | k8s | `~/.kube/config` | human / cluster admins (kubeconfig merge) | 0600 |  | Cluster credentials. Human-managed: the guard and the permission rules deny agents reading or editing it; contexts are listed with `k8s contexts` / `kubectl config get-contexts`. |
<!-- generated:end -->
