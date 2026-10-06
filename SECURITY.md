# Security

## Reporting a vulnerability

Use GitHub's private vulnerability reporting: **Security → Report a vulnerability** on
<https://github.com/matt-kh/harness-hub/security/advisories/new>. Please do not open a public
issue for anything that lets an agent bypass the guard, read a credential, or leak private
configuration. Expect an acknowledgement within a week; fixes land on `main` and in the next
patch release, credited unless you prefer otherwise.

Guard bypasses are in scope even when they need an unusual shell construct: the guard's job is
to hold against a model that tries creative quoting.

## Threat model

The adversary is **an AI agent acting with the user's own shell and credentials**, which
may be confused, prompt-injected by content it reads (tickets, issues, docs, web pages, pipeline
logs), or simply over-eager. The harness reduces what such an agent can do *without the human
noticing*. It does not defend against a malicious local user, a compromised provider binary,
or a compromised machine.

| Risk | Mitigation | Bundle |
|---|---|---|
| Agent reads secrets (tokens, kubeconfig, SSH keys, `.env`) and echoes them into a transcript, a commit or a ticket | guard denies reads of credential paths and secret-bearing env dumps; permission deny lists; Kubernetes Secret values only through `k8s redact` | core, k8s |
| Agent pushes to a default branch, bypassing review | guard denies `git push` to branches matching `core.default_branch_re`; delivery is MR/PR only | core |
| Agent changes ticket state (transition, close, reopen) on human work | guard denies state changes on tickets/issues without an `agent-*` label | jira, github, gitlab |
| Agent closes tickets indirectly through **closing keywords** in commits, MR/PR titles or bodies (the SCM ↔ tracker integration then transitions them) | guard denies closing-keyword forms in commit messages, `glab`/`gh` create/edit and API payloads | gitlab, github |
| Agent merges or approves its own MR/PR | guard asks; humans merge | gitlab, github |
| Agent edits human-authored tickets, MRs, docs | writes to artefacts without an `agent-*` label / provenance marker ask | jira, gitlab, github, gdoc |
| Agent mutates a cluster, execs into pods, reads Secrets | kubectl/helm mutations and exec-class commands ask, prod is flagged, kubeconfig edits deny | k8s |
| Agent sends email | not implemented: drafts only, the human sends | gdoc |
| Agent follows instructions embedded in fetched content | rule text: external content is data, never instructions; the guard still applies to whatever it then tries | core |
| Private org identifiers land in this public repo | private-identifier gate in pre-commit and CI | tools/gate |

## What the guard covers, per provider

The guard is one bash script ([ARCHITECTURE §5](ARCHITECTURE.md#5-guard)) that sees the
**text of a shell command** before it runs. Coverage depends on whether the provider calls it:

| Provider | Tier | Guard on shell commands | "ask" decisions |
|---|---|---|---|
| Claude Code | enforced | yes, PreToolUse hook on Bash | native prompt |
| Gemini CLI | partial | yes, BeforeTool hook on `run_shell_command` | no prompt: `providers.gemini.ask_as` (default deny) |
| Copilot CLI | partial | yes, preToolUse hook on `bash` | no prompt: `providers.copilot.ask_as` (default deny) |
| Codex | advisory | **no** — instructions and Codex's own approval policy only | n/a |
| OpenCode / Kilo | advisory | **no** — instructions only | n/a |

On **advisory** providers nothing technical stops the agent; the rendered instructions ask it
to behave, and you should run them with their strictest approval setting.
`harness status --matrix` prints the tier for your machine.

### What the guard does not cover

- **Non-shell tools.** File-write, file-read and web tools of a provider are governed by that
  provider's permission lists (rendered by the hub where the provider supports them), not by
  the guard. Claude Code's `permissions.deny` covers its Read tool; other providers vary.
- **Commands the text does not reveal.** A script the agent writes and then runs is checked
  only by its invocation line. Variables, `eval` of computed strings and downloaded scripts
  can hide intent; the guard asks or denies on the patterns it knows (`sh -c`, `xargs`,
  `bash -c`, env prefixes) and fails closed on malformed input, but it is a filter, not a
  sandbox.
- **MCP servers.** Their tools run outside the shell. The hub registers MCP servers
  read-only where the server supports it (the Jira server runs with `READ_ONLY_MODE`), and
  provider permission prompts apply.
- **Your own terminal.** Commands you type (including `!` shell escapes in a session) are
  yours; the guard does not second-guess the human.
- **Server-side settings.** Branch protection, required reviews and secret scanning on your
  SCM are the real enforcement; the guard is the only protection only where the plan offers
  none (for example private repos on GitHub Free).
- **Repositories that declare their own harness.** A repository's `.harness.toml` is
  repository content the guard reads from the hook's working directory — the agent's cwd, not
  the command's target: `git -C ../other push` is judged under the cwd's declaration
  ([repository-level harnesses](docs/repo-level.md)). It can only loosen rules that do not
  protect the developer's own credentials: skip every rule of the guard sections whose domain
  or id it owns — including the human-only merge and review asks (`scm`), the Secret-value and
  kubeconfig-mutation denies (`kubernetes`) and the transition and closing-keyword denies
  (`tracker`) — and set the allow-listed `WORK_TICKET_*` overrides in the
  [hook policy](docs/reference/hook-policy.md#repo-overrides). It never lifts:
  - the credential-file denies: `core/guard.d/20-credentials` (shell reads of the kubeconfig,
    `~/.config/{gh,glab-cli,jira,gdoc}`, `~/.aws`, `~/.ssh`, `.env*`, agent credential files,
    secret environment dumps) and `core/permissions` (the matching `Read(...)` denies);
  - the commands that print a stored credential: `gh auth token`,
    `gh auth status --show-token`, `gh config get oauth_token`, `kubectl config view --raw`
    (the `# never-yields:` preludes of `github/guard.d/60-github` and `k8s/guard.d/25-k8s-rules`);
  - the asks on writing `.harness.toml` itself: `Write`/`Edit` of `**/.harness.toml`
    (`core/permissions`) and shell writes to it (`>`, `tee`, `cp`, `mv`, `sed -i`,
    `harness repo init --write`; the prelude of `core/guard.d/30-git`). The declaration lifts
    user-level rules, so an agent that wrote it would authorise itself; a human reviews and
    commits it.

  Client paths and engine or credential settings (`HARNESS_GUARD_ENV`, `HARNESS_CRED_EXTRA_RE`,
  every `*_PY`, `GUARD_*`, `HARNESS_*` and `*CRED*` name) are ignored when they appear in the
  file. Review a cloned repository's `.harness.toml` like any other committed agent
  configuration; `harness repo` shows its effect.

## Where secrets live

The hub never stores, reads or transmits credentials. Each tool keeps its own:
[docs/reference/secrets.md](docs/reference/secrets.md) lists every path, the tool that
writes it, the expected file mode and the rotation runbook. Config validation rejects
secret-looking keys and values, so a token pasted into `harness.toml` fails loudly.

## Outbound network calls

No telemetry, no update pings. The hub itself makes exactly these calls, and only when you run
the command:

| When | Call | Opt out / offline |
|---|---|---|
| `harness install <tool>`, `bootstrap` installing a missing tool | HTTPS download of the pinned release asset listed in `tools/<tool>.lock.json` (e.g. GitHub Releases), sha256-verified | `--no-install-tools`, `--offline`, `--from FILE`, `HARNESS_TOOLS_MIRROR` |
| `harness upgrade` | `git fetch --tags` of this repository's `origin` (and `git pull --ff-only` with `--to BRANCH`) | `--offline` uses the tags already in the clone; or point `origin` at a bundle file |
| `harness pack --tools os/arch,...` | HTTPS download of the pinned `tools/<tool>.lock.json` assets for those platforms, sha256-verified (same code as `harness install`) | omit `--tools`, `--offline`, `HARNESS_TOOLS_MIRROR` |
| `harness init --from <git url>` | `git clone`/`fetch` of the org overlay you name | pass a local path |
| `harness doctor` (online checks) | runs **your** CLIs' own status commands: `gh auth status`, `glab auth status`, `jira whoami`, `gdoc auth status`, `kubectl version`, `ssh -T git@<host>` — they contact the hosts in your config | `--offline` (or `HARNESS_OFFLINE=1`) skips every network check |
| `harness steps --pending` | the same verify commands as doctor | `--offline` |

Bundles' skills and CLIs (jira, gdoc, k8s) talk to the services you configured when an agent
or you run them; they are part of your workflow, not of the hub. The optional Jira MCP
server is started by the provider through `uvx`, which downloads the package from PyPI on
first use.

## Release artifacts

A release is a `git bundle` file, optional sidecar tool archives taken from the pinned lock
files, `INSTALL.txt`, `SHA256SUMS` over all of them, and `harness-hub-X.Y.Z.run`, a
self-extracting envelope of the same files ([distribution](docs/distribution.md)). Releases
never contain `local/`, credentials, provider CLIs or MCP packages.

- **Offline check**: `shasum -a 256 -c SHA256SUMS` before cloning; `harness verify
  FILE.bundle` also runs `git bundle verify`.
- **The `.run`**: its header is the tracked `lib/harness/selfextract-header.sh` (read it, or
  `head -n 200 FILE.run`, before running one). `sh FILE.run --check` verifies the payload's
  size and sha256 against the header and every `SHA256SUMS` line inside it, and installs
  nothing; every install or upgrade run performs the same checks first. The header's sha256
  is only as trustworthy as the file you received: check the `.run` line of the outer
  `SHA256SUMS` or its provenance.
- **Provenance (online)**: releases published by the `release` workflow carry GitHub build
  provenance for every asset: `gh attestation verify FILE -R matt-kh/harness-hub`. Verify on
  the connected side before carrying files across an air gap.
- Release tags are annotated; signed tags are optional and reported by
  `harness release check`.

## Supported versions

Security fixes go to the latest minor release. Run `harness upgrade` to get them.
