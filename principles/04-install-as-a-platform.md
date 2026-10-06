# Principle 4 — Installed as a platform, distributable air-gapped

Part of [PRINCIPLES.md](../PRINCIPLES.md). Read this before changing how the hub is
installed, upgraded, released or reached over the network.

## Statement

> Although it is a platform, the method of distribution should be as lightweight and
> versatile as possible to be distributed air-gapped. When distributed, it should be
> "installed" as a platform instead of an application, in the sense that this repo is what
> platform devs look to when they aspire to build a developer-friendly harness platform.

- Installing the hub means taking a copy of the repository and owning it. The copy is the
  platform: readable, forkable, extendable.
- Every install and upgrade path works without network access, given files carried across.

## Rationale

- An application hides its internals behind an installer; a platform invites its operators
  to read and extend it. Platform teams need the second.
- Regulated, defence, industrial and on-premises environments are often air-gapped. A
  harness that cannot reach them leaves their developers with ungoverned agents.
- A copy that is owned can be audited once and pinned; a hosted service cannot.

## What it means in this repo

- **The repository is the product.** There is no server, registry, daemon or language
  package. `bootstrap` runs from the clone; `local/` stays gitignored inside it.
- **Three tiers, all plain git** ([distribution](../docs/distribution.md)):
  - upstream: the public hub, the reference;
  - org platform instance: a fork or mirror on the org's own git host, with org bundles and
    an org overlay;
  - workstation: a clone plus `local/`.
- **Offline is first-class.**
  - `--offline` / `HARNESS_OFFLINE=1` skips every network check (`SKIP`, not `FAIL`).
  - `bootstrap --no-install-tools` and `harness install <tool> --from FILE` install pinned
    tools from carried archives, still sha256-verified.
  - `HARNESS_TOOLS_MIRROR` rewrites download URLs to an internal mirror; the hash check is
    unchanged.
  - A release is a single `git bundle` file plus optional tool archives and `SHA256SUMS`
    ([principle 5](05-distributed-as-a-git-repo.md)); the optional `.run` envelope carries
    them as one file (`sh FILE.run --check`, then `sh FILE.run --offline --no-install-tools`),
    and a newer `.run` upgrades the same clone offline.
- **Proxies and internal CAs** work through the standard variables (`HTTPS_PROXY`,
  `SSL_CERT_FILE`, `CURL_CA_BUNDLE`) ([air-gapped runbook](../docs/runbooks/air-gapped.md)).
- **Upgrades are git operations** (`harness upgrade [--to latest|TAG|BRANCH]`), with migration notes from
  the CHANGELOG and a plan before anything is written.

## What it rules out

- A hosted control plane, a license server, an update service or telemetry.
- An installer binary or package that hides the repository from its operator.
- Silent auto-update; every upgrade is an explicit `harness upgrade` with a plan.
- Install steps that need the internet without an offline alternative.
- Redistributing provider CLIs or MCP packages; the hub pins and verifies, it does not ship
  third-party binaries in its own history.

## How it is checked

| Check | Kind | Where |
|---|---|---|
| Bootstrap in a fresh home with `--offline` and fake CLIs; `plan` then shows `0 changes` | smoke | `tests/smoke/bootstrap.sh`, CI `smoke` job |
| Pack → verify → `bootstrap --from` into a temp home → `doctor --offline` | smoke | `tests/smoke/pack.sh` |
| Every outbound call is listed with its opt-out | review | [SECURITY.md](../SECURITY.md#outbound-network-calls) |
| Network doctor checks declare `offline_skip = true` | review | add-a-bundle checklist |

## Tensions and how they are resolved

- **With principle 3 (platform for everyone).** The public repo is on GitHub; many orgs cannot
  reach it. Resolution: the bundle file and the org mirror make GitHub one channel among
  several, not a dependency.
- **With principle 1 (lightweight).** Offline installs need tool archives. Resolution: they are
  sidecar files beside the bundle, described by the lock files already in the repo, never
  committed.
- **With freshness.** Air-gapped copies drift behind upstream. Resolution: tags, `VERSION` and
  CHANGELOG Migration paragraphs make a late upgrade mechanical; `harness upgrade` prints
  every migration between the applied version and the target.

## Examples

Compliant:

- A new tool installer that accepts `--from FILE` and verifies the lock's sha256.
- A doctor check that sets `offline_skip = true` because it calls `ssh -T`.
- Release notes that list the sidecar archives a site needs for its platforms.

Non-compliant:

- `bootstrap` that `curl | bash`-es a script from the internet.
- A feature that only works while signed in to a hosted account of the hub.
- An upgrade that rewrites provider homes without showing a plan.

## Open questions

- Signed releases: resolved in [principle 5](05-distributed-as-a-git-repo.md#open-questions)
  (build provenance verified online with `gh attestation verify`, `SHA256SUMS` offline,
  annotated tags, signed tags optional).
- A documented cadence for org instances to sync from upstream.
