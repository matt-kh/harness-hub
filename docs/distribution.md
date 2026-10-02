# Distribution

How harness-hub travels from upstream to an organisation to a workstation, and what a
release contains. Governed by [principle 4](../principles/04-install-as-a-platform.md) and
[principle 5](../principles/05-distributed-as-a-git-repo.md).

## The model

- The repository is the product. Installing it means taking a copy and owning it.
- Every channel is plain git: a remote, a mirror, or a `git bundle` file.
- There is no server, registry, daemon, language package or telemetry.

## Tiers

| Tier | What it is | How it is installed | How it is upgraded |
|---|---|---|---|
| Upstream | the public hub on GitHub, the reference | nothing; it is the source | maintainers tag releases |
| Org platform instance | a fork or mirror on the org's git host (GitLab, Gitea, a bare repo on a share), with org bundles and an org overlay | `git clone` of upstream, or `git clone FILE.bundle`, pushed to the org remote | `git fetch upstream --tags`, merge, push ([self-host runbook](runbooks/self-host.md)) |
| Workstation | one developer's clone plus gitignored `local/` | `bootstrap`, or a clone of a bundle file | `harness upgrade [--to TAG]` |

- A workstation can clone upstream directly; the org tier is optional.
- `local/` never moves between tiers. Org-wide values travel as the org overlay
  (`harness init --from`) or as committed org bundles in the org instance.

## Channels

| Channel | Use when | Command |
|---|---|---|
| git remote (upstream or org) | the machine can reach the git host | `git clone <remote> ~/harness-hub && ~/harness-hub/bootstrap` |
| bundle file | air-gapped, or the git host is unreachable | `git clone FILE.bundle ~/harness-hub`, or `harness bootstrap --from FILE.bundle` |
| mirror of tool downloads | tools must come from an internal artifact store | `HARNESS_TOOLS_MIRROR=<base url>` |
| carried tool archives | no artifact store either | `harness install <tool> --from FILE` |

## The release artifact

`harness pack` writes, into `--out DIR`:

```text
harness-hub-vX.Y.Z.bundle   the repository: branches, tags, history (git bundle)
tools/<asset>               optional: the tools/*.lock.json assets for each --tools platform
INSTALL.txt                 verify, clone, bootstrap
SHA256SUMS                  sha256 of every file above
```

- Without a release tag on `HEAD` (or `--tag`), the version in the file name is
  `v<VERSION>-g<short sha>`.
- On the target machine, with git, bash, python3 and jq only:

```sh
shasum -a 256 -c SHA256SUMS                                   # or: sha256sum -c SHA256SUMS
git clone harness-hub-vX.Y.Z.bundle ~/harness-hub
~/harness-hub/bootstrap --offline --no-install-tools
harness install gh --from tools/gh_<version>_linux_amd64.tar.gz      # per sidecar archive, if any
```

- From an existing hub, `harness bootstrap --from FILE.bundle` replaces the clone and
  bootstrap lines, and `harness verify FILE.bundle` replaces the checksum line.

### Excluded, always

- `local/` (refused by `pack`, and gitignored), `build/`, state files and backups.
- Credentials of any kind.
- Provider CLIs (Claude Code, Gemini CLI, Copilot CLI, Codex, OpenCode) and MCP server
  packages: install them per their vendor's instructions or from your own mirror.
- Uncommitted changes: `pack` refuses a dirty tree.

## Commands

| Command | What it does |
|---|---|
| `harness pack [--out DIR] [--tag TAG] [--tools os/arch,...]` | creates the bundle (branches and tags; with `--tag TAG` every tag and no branches, cloned with `git clone -b TAG`), runs `git bundle verify`, downloads and hash-checks sidecar tools for the listed platforms, writes `SHA256SUMS` and `INSTALL.txt` |
| `harness verify FILE.bundle` | `git bundle verify`, lists heads and tags, checks `SHA256SUMS` beside the file |
| `harness bootstrap --from FILE.bundle [--dest DIR] [--origin URL]` | verifies and clones the bundle (default destination `~/harness-hub`, which must be empty), checks out the newest tag if the bundle has no `HEAD`, sets `origin` to `URL` (default: the bundle file), then runs the clone's bootstrap with the remaining arguments |
| `harness upgrade [--to TAG] [--no-apply]` | fetches from `origin`, checks out the tag or fast-forwards, prints Migration notes, re-plans and applies |

Reference with every flag: [CLI reference](reference/cli.md). Contract:
[ARCHITECTURE §10](../ARCHITECTURE.md#10-distribution).

## Versioning

- Semver tags `vX.Y.Z`; the `VERSION` file matches the tag.
- Each release has a CHANGELOG section. A **Migration** paragraph is present whenever a config
  key, a default or a guard decision changes; `harness upgrade` prints every one between the
  applied version and the target.
- Before 1.0 a minor release may change config; deprecated keys warn for two minors, then
  error.
- Principle changes are listed under **Principles** and bump `principles_version` in
  [PRINCIPLES.md](../PRINCIPLES.md).

## Air-gapped flow

```text
  connected side                                   offline side
  ──────────────                                   ────────────
  git clone upstream (or org instance)
  harness pack --out rel --tag vX.Y.Z \
       --tools linux/amd64,darwin/arm64
        │
        ▼
  rel/ harness-hub-vX.Y.Z.bundle
       tools/gh_<v>_linux_amd64.tar.gz …  ──(USB / data diode / share)──►  shasum -a 256 -c SHA256SUMS
       SHA256SUMS, INSTALL.txt                                              git clone FILE.bundle ~/harness-hub
                                                                            ~/harness-hub/bootstrap --offline --no-install-tools
                                                                            harness install gh --from tools/<archive>
                                                                            harness doctor --offline

  later: pack the next tag the same way ──────────────────────────────►   git -C ~/harness-hub remote set-url origin NEW.bundle
                                                                            harness upgrade --to <next tag>
```

- Proxies, internal CAs, tool mirrors and the optional Jira MCP server offline:
  [air-gapped runbook](runbooks/air-gapped.md).

## Rejected on purpose

- A hosted service, registry or update server: it would be a dependency every site must reach.
- pip, npm or container images as the install format: they add a toolchain to every machine.
- Redistributing third-party binaries in git history: the lock files pin them instead.
- Telemetry of any kind.
