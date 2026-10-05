# Getting started

From nothing to a governed agent session in about fifteen minutes, most of it spent in
browser sign-ins that only you can do. Works on Linux, WSL2 and macOS.

## 1. Prerequisites

| | Linux | WSL2 (Ubuntu) | macOS |
|---|---|---|---|
| git, curl | distro packages | `sudo apt install git curl` | Xcode Command Line Tools (`xcode-select --install`) |
| python ≥ 3.9 | distro `python3` | `sudo apt install python3` | `/usr/bin/python3` (3.9+) or `brew install python` |
| jq | `apt/dnf install jq` | `sudo apt install jq` | `brew install jq` |
| bash ≥ 4 (recommended) | already | already | `brew install bash` — scripts parse under `/bin/bash` 3.2, but some checks need 4 |
| an agent CLI | Claude Code, Gemini CLI, Copilot CLI, Codex or OpenCode — install per the vendor's instructions | same | same |

WSL2 notes: keep the clone on the Linux filesystem (`~/…`), not under `/mnt/c` — Windows
mounts are case-insensitive and slow, and file modes do not stick. Browser sign-ins open (or
print a URL for) your Windows browser.

Native Windows is not supported.

## 2. Clone and bootstrap

```sh
git clone git@github.com:matt-kh/harness-hub.git ~/harness-hub && ~/harness-hub/bootstrap
```

No SSH key for GitHub yet? Clone over HTTPS once (`https://github.com/matt-kh/harness-hub.git`);
the `github` bundle's `ssh-key` step sets up SSH afterwards.

`bootstrap` runs these stages; each is safe to interrupt and re-run:

1. **Preflight** — checks bash, python, jq, git; detects OS/arch and WSL; notices whether
   `~/.local/bin` is on your `PATH` (see step 3 below).
2. **Config** — if `local/harness.toml` does not exist, `init` asks for your email and shows
   the bundle checklist:

   ```text
   Select bundles (toggle with number, Enter to continue):
    [x] 1 core             guard hook, harness CLI, Plan/Auto/code-reviewer, conventions  (required)
    [x] 2 github           gh, PR workflow, Issues tracker                  detected: gh 2.63
    [ ] 3 gitlab           glab, MR workflow, agent-* labels                detected: glab 1.51
    [ ] 4 jira             Jira Server PAT + CLI + read-only MCP
    [ ] 5 k8s              read-only k8s CLI + triage/audit agents          detected: kubectl
    [ ] 6 gdoc             gdoc CLI (needs a GCP OAuth client)
    [x] 7 ticket-workflow  work-ticket / create-ticket                      (recommended by 2)
   >
   ```

   then the same for providers (installed CLIs pre-ticked). It writes `local/harness.toml`
   with a commented section per bundle and offers to open it in `$EDITOR`. Fill in the keys
   the chosen bundles need (`github.login`, `jira.url`, …); validation loops until the file
   is valid. `harness config explain <key>` describes any key.
3. **Resolve** — adds dependencies, asks about recommended bundles, stops with a clear
   sentence on conflicts (for example `ticket-workflow` without any tracker).
4. **Existing files** — if a provider directory already has instructions, skills or settings
   the hub did not write, you choose per path: keep (default), adopt (back up and replace) or
   diff. Instruction files get managed blocks appended; your own text stays.
5. **Plan** — a table of `create | update | skip | conflict` per path, with diffs.
   `--dry-run` stops here.
6. **Apply** — backs up every file it modifies to `~/.local/state/harness/backups/<timestamp>/`,
   writes the files, installs missing pinned tools into `~/.local/bin`, registers MCP servers
   and records everything in `<provider home>/.harness-state.json`.
7. **Doctor and hand-off** — runs `harness doctor` and prints the manual steps still pending,
   grouped into "no browser", "browser" and "needs an admin".

Non-interactive, for CI or a dotfiles script:

```sh
~/harness-hub/bootstrap --bundles core,github,ticket-workflow --providers claude --yes
~/harness-hub/bootstrap --profile github-dev --yes --offline     # no network checks
```

### From a bundle file (air-gapped)

No route to GitHub or your org's git host? Install from a release bundle file: one
`git bundle` with the whole hub, optional tool archives and `SHA256SUMS`
([distribution](distribution.md)).

One file, if you have the `.run` envelope (it carries the bundle, the tool archives and
`SHA256SUMS`):

```sh
sh harness-hub-X.Y.Z.run --check                             # payload and SHA256SUMS
sh harness-hub-X.Y.Z.run --offline --no-install-tools        # clone to ~/harness-hub, bootstrap
```

Or from the bundle file and its directory:

```sh
cd /media/usb/rel && shasum -a 256 -c SHA256SUMS           # or: sha256sum -c SHA256SUMS
git clone harness-hub-X.Y.Z.bundle ~/harness-hub
~/harness-hub/bootstrap --offline --no-install-tools
harness install gh --from tools/gh_<version>_linux_amd64.tar.gz   # for each archive you need
```

- The clone's `origin` is the bundle file; upgrades fetch from a newer file, or run a newer
  `.run` with the same `--dest` ([air-gapped runbook](runbooks/air-gapped.md#upgrading-offline)).
- With a hub already installed, `harness bootstrap --from FILE.bundle --dest DIR` clones and
  bootstraps in one step, and `harness verify FILE.bundle` checks the file.
- Your organisation runs its own instance? Clone that instead and follow its onboarding line
  ([self-host runbook](runbooks/self-host.md#7-write-the-onboarding-one-liner)).

## 3. Put `~/.local/bin` on your PATH

`harness`, `gh` (if installed by the hub), and the bundle CLIs (`jira`, `k8s`, `gdoc`) land in
`~/.local/bin`. If `command -v harness` prints nothing, add the line for your shell and open a
new terminal:

```sh
# bash (Linux, WSL2): ~/.bashrc
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc

# zsh (Linux, WSL2): ~/.zshrc
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc

# zsh on macOS (login shells read ~/.zprofile)
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zprofile
```

Until then, call it by path: `~/harness-hub/bin/harness`.

## 4. First doctor

```sh
harness doctor
```

```text
PASS core/guard-hook        ~/.claude/hooks/guard-bash.sh executable, registered in settings.json
PASS core/jq                jq 1.7
FAIL github/gh-auth         gh is not logged in to github.com
     → manual step github#gh-auth: Authenticate gh   (docs/bundles/github.md#gh-auth)
WARN github/gh-ssh          ssh -T git@github.com did not authenticate
     → manual step github#ssh-key: Register an SSH key with GitHub   (docs/bundles/github.md#ssh-key)
1 FAIL, 1 WARN
```

Every FAIL and WARN names the manual step that fixes it and the doc anchor with the full
instructions. `--offline` skips checks that need the network, `--json` is for scripts, and
`[doctor].warn_only = ["<check-id>"]` in your config downgrades a check you have decided to
live with.

## 5. Do the manual steps

```sh
harness steps --pending          # only the steps whose verify command still fails
harness steps --bundle gdoc      # every step of one bundle, done or not
```

Each step says why it is needed, exactly what to click or type, and the command that
verifies it. Agents cannot do these for you: they need a browser, your password, or an admin.
Run sign-in commands **in your own terminal** (inside Claude Code, prefix with `! ` to run a
line yourself). Re-run `harness doctor` after each; the per-bundle pages list them all:
[core](bundles/core.md), [github](bundles/github.md), [gitlab](bundles/gitlab.md),
[jira](bundles/jira.md), [ticket-workflow](bundles/ticket-workflow.md), [k8s](bundles/k8s.md),
[gdoc](bundles/gdoc.md).

## 6. First agent session

Start your agent in any repository:

```sh
cd ~/src/some-repo && claude        # or: gemini, copilot, codex, opencode
```

Things to try, to see the harness working:

- Ask it to `cat ~/.config/gh/hosts.yml`. On enforced and partial providers the guard denies
  it with a reason; on advisory providers the instructions tell the agent not to.
- Ask it to push to `main`: denied, with a pointer to the MR/PR workflow.
- With `ticket-workflow` and a tracker: "work on PROJ-123" (or "#12") runs the governed
  ticket → branch → MR/PR flow; it labels what it touches `agent-worked`, mentions the ticket
  and never closes it.

Repository-level configuration always wins: if a repo ships its own `CLAUDE.md`, `.claude/`
settings, skills or guard for the same concern, that repo's behaviour replaces the
user-level one for sessions in it (see [concepts](concepts.md#precedence)).

## Next

- [Concepts](concepts.md) — what `render`, `plan`, `apply` and `sync` do to your files.
- [Governance](governance.md) — the rules and the reasoning behind them.
- [Upgrade runbook](runbooks/upgrade.md) — staying current.
- Already have a hand-built harness? [Migrate it](runbooks/migrate-existing-harness.md).
