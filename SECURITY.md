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
| `harness upgrade` | `git fetch` of this repository's remote | skip upgrade; pin with `--to TAG` |
| `harness init --from <git url>` | `git clone`/`fetch` of the org overlay you name | pass a local path |
| `harness doctor` (online checks) | runs **your** CLIs' own status commands: `gh auth status`, `glab auth status`, `jira whoami`, `gdoc auth status`, `kubectl version`, `ssh -T git@<host>` — they contact the hosts in your config | `--offline` (or `HARNESS_OFFLINE=1`) skips every network check |
| `harness steps --pending` | the same verify commands as doctor | `--offline` |

Bundles' skills and CLIs (jira, gdoc, k8s) talk to the services you configured when an agent
or you run them; they are part of your workflow, not of the hub. The optional Jira MCP
server is started by the provider through `uvx`, which downloads the package from PyPI on
first use.

## Supported versions

Security fixes go to the latest minor release. Run `harness upgrade` to get them.
