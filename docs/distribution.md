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
| Upstream | the public hub on GitHub, the reference | nothing; it is the source | maintainers push a release tag; the `release` workflow publishes it |
| Org platform instance | a fork or mirror on the org's git host (GitLab, Gitea, a bare repo on a share), with org bundles and an org overlay | `git clone` of upstream, or `git clone FILE.bundle`, pushed to the org remote | `git fetch upstream --tags`, merge, push ([self-host runbook](runbooks/self-host.md)) |
| Workstation | one developer's clone plus gitignored `local/` | `bootstrap`, a clone of a bundle file, or `sh FILE.run` | `harness upgrade [--to latest\|TAG\|BRANCH]`, or a newer `.run` |

- A workstation can clone upstream directly; the org tier is optional.
- `local/` never moves between tiers. Org-wide values travel as the org overlay
  (`harness init --from`) or as committed org bundles in the org instance.

## Channels

| Channel | Use when | Command |
|---|---|---|
| git remote (upstream or org) | the machine can reach the git host | `git clone <remote> ~/harness-hub && ~/harness-hub/bootstrap` |
| bundle file | air-gapped, or the git host is unreachable | `git clone FILE.bundle ~/harness-hub`, or `harness bootstrap --from FILE.bundle` |
| one file | air-gapped, and one file is easier to carry and check than a directory | `sh harness-hub-vX.Y.Z.run --check`, then `sh harness-hub-vX.Y.Z.run --offline --no-install-tools` |
| mirror of tool downloads | tools must come from an internal artifact store | `HARNESS_TOOLS_MIRROR=<base url>` |
| carried tool archives | no artifact store either | `harness install <tool> --from FILE` |

## The release artifact

`harness pack` writes, into `--out DIR`:

```text
harness-hub-vX.Y.Z.bundle   the repository: branches, tags, history (git bundle)
tools/<asset>               optional: the tools/*.lock.json assets for each --tools platform
INSTALL.txt                 verify, clone, bootstrap
SHA256SUMS                  sha256 of every file above (plus the .run line when it is written)
harness-hub-vX.Y.Z.run      optional envelope (--self-extract): a POSIX sh header + an uncompressed
                            tar of the files above; the bundle inside is the release
```

- The `.run` is a carrier, not a second format: its header (the tracked
  `lib/harness/selfextract-header.sh`) checks the payload size and sha256 and every
  `SHA256SUMS` line, then clones the bundle inside. The payload tar is deterministic for the
  same files (sorted names, owner 0, fixed modes, mtime of the released commit or
  `SOURCE_DATE_EPOCH`), and so is the header. The git bundle itself is not guaranteed to be
  byte-identical between builds (even with the same git version), so two builds of one tag
  can differ; `SHA256SUMS` and the build provenance identify a specific build.
- `.run` flags: `--check` (verify only), `--list`, `--extract DIR` (unpack, then follow
  `INSTALL.txt`), `--dest DIR` (default `~/harness-hub`), `--release-dir DIR` (default
  `~/.local/share/harness/releases/<version>/`, where the files stay so `origin` remains
  fetchable offline and `tools/` stays at hand for `harness install --from`). Every other
  argument goes to the clone's `bootstrap`. Run against an existing hub clone (`--dest`), it
  fetches the tags, points `origin` at the new bundle and runs `harness upgrade --to <tag>`
  with the remaining arguments instead, dropping bootstrap-only flags such as
  `--no-install-tools` or `--bundles X` (it prints which). A dev-build `.run` (no tag) only
  installs: against an existing clone it refuses and asks for `--dest NEW_DIR`.

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
- With the `.run` only: `sh harness-hub-vX.Y.Z.run --check`, then
  `sh harness-hub-vX.Y.Z.run --offline --no-install-tools`.
- Published releases also carry GitHub build provenance: `gh attestation verify FILE -R
  matt-kh/harness-hub` checks it online; `SHA256SUMS` is the offline check.

### Excluded, always

- `local/` (refused by `pack`, and gitignored), `build/`, state files and backups.
- Credentials of any kind.
- Provider CLIs (Claude Code, Gemini CLI, Copilot CLI, Codex, OpenCode) and MCP server
  packages: install them per their vendor's instructions or from your own mirror.
- Uncommitted changes: `pack` refuses a dirty tree.

## Commands

| Command | What it does |
|---|---|
| `harness pack [--out DIR] [--tag TAG] [--tools os/arch,...] [--self-extract]` | creates the bundle (branches and tags; with `--tag TAG` every tag and no branches, cloned with `git clone -b TAG`), runs `git bundle verify`, downloads and hash-checks sidecar tools for the listed platforms, writes `SHA256SUMS` and `INSTALL.txt`; `--self-extract` adds the `.run` |
| `harness verify FILE.bundle` / `FILE.run` | `git bundle verify` and the heads and tags, or `sh FILE.run --check`; then `SHA256SUMS` beside the file |
| `harness bootstrap --from FILE.bundle [--dest DIR] [--origin URL]` | verifies and clones the bundle (default destination `~/harness-hub`, which must be empty), checks out the newest tag if the bundle has no `HEAD`, sets `origin` to `URL` (default: the bundle file), then runs the clone's bootstrap with the remaining arguments |
| `harness upgrade [--to latest\|TAG\|BRANCH] [--no-apply]` | fetches tags from `origin` and checks out the newest release tag (default; pre-releases skipped), the given tag, or fast-forwards the given branch; prints Migration notes, re-plans, applies and runs `doctor` |
| `harness release check [TAG]` / `release notes TAG` | maintainers: the release preflight (SemVer tag, annotated, `VERSION`, CHANGELOG section, no `local/`, clean tree, on `origin/main`) and the release notes; used by the `release` workflow |

Reference with every flag: [CLI reference](reference/cli.md). Contract:
[ARCHITECTURE §10](../ARCHITECTURE.md#10-distribution).

## Versioning

- [SemVer 2.0.0](https://semver.org/spec/v2.0.0.html): annotated tags `vX.Y.Z` on `main`;
  the `VERSION` file matches the tag without the `v`. Pushing the tag is the release: the
  `release` workflow checks it, runs CI, packs it and publishes a GitHub Release of the same
  name. Tag names that are not SemVer 2.0.0 release nothing.
- Pre-releases `vX.Y.Z-rc.N` publish a GitHub pre-release; `harness upgrade` without `--to`
  skips them (pass `--to vX.Y.Z-rc.N`). Instances that tag their own builds
  (`vX.Y.Z-acme.N`) are pre-releases by this rule and upgrade with an explicit `--to TAG`.
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
       --tools linux/amd64,darwin/arm64 --self-extract
  (or download a published release)
        │
        ▼
  rel/ harness-hub-vX.Y.Z.bundle
       tools/gh_<v>_linux_amd64.tar.gz …  ──(USB / data diode / share)──►  shasum -a 256 -c SHA256SUMS
       SHA256SUMS, INSTALL.txt                                              git clone FILE.bundle ~/harness-hub
                                                                            ~/harness-hub/bootstrap --offline --no-install-tools
                                                                            harness install gh --from tools/<archive>
                                                                            harness doctor --offline

  or one file: harness-hub-vX.Y.Z.run ────────────────────────────────►   sh FILE.run --check
                                                                            sh FILE.run --offline --no-install-tools

  later: pack the next tag the same way ──────────────────────────────►   git -C ~/harness-hub remote set-url origin NEW.bundle
                                                                            harness upgrade --to <next tag>
         or carry the newer .run ────────────────────────────────────►   sh NEW.run --yes --offline   (same --dest = upgrade)
```

- Proxies, internal CAs, tool mirrors and the optional Jira MCP server offline:
  [air-gapped runbook](runbooks/air-gapped.md).

## Rejected on purpose

- A hosted service, registry or update server: it would be a dependency every site must reach.
- pip, npm or container images as the install format: they add a toolchain to every machine.
- Redistributing third-party binaries in git history: the lock files pin them instead.
- Telemetry of any kind.
