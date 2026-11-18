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
| `ssh_keys` | linux | `~/.ssh/* (except *.pub)` | human (ssh-keygen) | 0600 | ssh-keygen -t ed25519 a new key, install its .pub on each host yourself (ssh-copy-id -i KEY.pub HOST), then remove the old line from each host's authorized_keys | Your SSH private keys and agent setup. Never read or copied by the bundle: reading them is denied by core section 20, copying them off the machine by section 83 (never yields); the public *.pub files are fine. |
| `obs_keys` | obs | `~/.config/obs/*.key` | human (a Viewer-role API key or service-account token pasted from each backend's UI) | 0600 | docs/runbooks/rotate-obs-key.md | One key file per backend, named in obs.backends auth_file. The obs CLI sends it as SIGNOZ-API-KEY (SigNoz) or a bearer token (Grafana, Prometheus behind a proxy); `obs backends` reports presence and mode, never the content. |
| `talos_secrets_bundle` | provision | `<provision.infra_root>/…/secrets.yaml (from talosctl gen secrets), sops-encrypted before commit` | human (talosctl gen secrets once per cluster, then sops --encrypt) | 0600 | talosctl rotate-ca (the human's, per the Talos docs), then regenerate and re-encrypt the bundle | The Talos cluster secrets bundle (CA keys, tokens). Generated once, encrypted with sops before it enters the infrastructure repository; never plaintext in git, never printed. |
| `talosconfig` | provision | `~/.talos/config (or $TALOSCONFIG)` | human (talosctl gen config, then talosctl config merge) | 0600 | talosctl config new on a control-plane node with a fresh role, merge it yourself, then remove the old context | The Talos client config with its client key. Never read by agents: reading it and `talosctl kubeconfig -` are denied by guard section 85 and never yield; `talosctl config merge\|context\|…` is denied (human-managed). |
<!-- generated:end -->
