# Principle 3 — A platform for everyone

Part of [PRINCIPLES.md](../PRINCIPLES.md). Read this before adding a config key, a default,
an example value, a provider assumption or anything that names a real organisation.

## Statement

> This repo should be built from a platform developer's perspective, with the aim to serve
> developers in an organization. However, this repo is built to serve the public, hence it
> should be represented as a platform that serves the entire world.

- The author's stance is a platform team's: build once, roll out to many developers, keep
  everyone on the same governed baseline.
- The audience is anyone: any organisation, any size, any host, any supported provider. The
  public repo describes no particular organisation.

## Rationale

- Platform teams are where harnesses get built and maintained. Designing for them (overlays,
  forks, pinned releases, uniform doctor checks) gives individual developers the same
  benefits for free.
- A public platform earns trust by being generic. A single hard-coded hostname tells every
  other reader the repo is not for them, and may leak private information.
- Keeping org values out of the repo by construction is cheaper than reviewing them out.

## What it means in this repo

- **Org values live in config.** Public bundles reference `{{ section.key }}`; every
  organisation-specific value is a `[requires.config."<section>.<key>"]` with a description
  and a documentation-value `example`.
- **Documentation values only.** `example.com`, `PROJ-123`, `192.0.2.x`, `/home/u`,
  `111122223333`, `octocat`. The upstream maintainer's public login is the one named account.
- **Three places for org content**, from narrowest to widest:
  - `local/` on one workstation (gitignored: `local/harness.toml`, `local/bundles/<org>/`);
  - an org overlay, `local/harness.org.toml`, seeded by `harness init --from <path|url>`;
  - an org platform instance: a private fork or mirror with org bundles committed
    ([self-host runbook](../docs/runbooks/self-host.md)).
- **Many providers, honestly.** Claude Code, Gemini CLI, Copilot CLI, Codex and OpenCode,
  each with a stated tier (enforced, partial, advisory) in the
  [capability matrix](../docs/reference/capability-matrix.md). No feature is described as
  enforced where the provider cannot enforce it.
- **Many hosts.** GitHub and self-hosted GitLab; Jira Server/Data Center; any Kubernetes
  context; Google Workspace on any domain. Host names are config.
- **Portable.** Linux, WSL2 and macOS are supported; CI runs on Ubuntu and macOS.

## What it rules out

- Any organisation's hostname, project key, cluster name, account id, internal IP or work
  email in a tracked file, file name, commit message or author address.
- Defaults that only make sense for one organisation (a specific Jira field id, a specific
  cluster naming scheme). Those go in an org overlay or org bundle.
- Docs written as one person's setup ("my cluster", "our Jira").
- A provider assumption in a public bundle without an adapter capability behind it.

## How it is checked

| Check | Kind | Where |
|---|---|---|
| Public patterns and the private denylist over contents, names, messages, emails | gate | `tools/gate/private-ids.sh` (pre-commit and CI) |
| Commit identities are noreply addresses | gate | same script, `--range` |
| Templates reference only declared config keys | lint | `harness lint` |
| A missing key is a plan error, never a blank | engine | `harness plan` |
| Provider tiers are generated from adapters | docs | `harness docs check` |

- The gate's own documentation is [tools/gate/README.md](../tools/gate/README.md). Private hits
  cannot be suppressed; rename the value instead.

## Tensions and how they are resolved

- **With principle 2 (developer-first).** Real developers need their own hosts and fields.
  Resolution: the layering of config, overlay and private or org bundles. The workflow is
  public; the values are not.
- **With org platform instances.** A private fork legitimately commits its own hostnames.
  Resolution: that fork is a separate, private repo. Its gate denylist holds what must never
  leave the fork; contributions upstream go through the public gate
  ([self-host runbook](../docs/runbooks/self-host.md)).
- **With completeness.** Some features exist only for one vendor (Jira Server, not Cloud).
  Resolution: the config says so (`jira.kind`), docs state the limit, and the gap is open for
  contribution.

## Examples

Compliant:

- A bundle rule: "push to `{{ gitlab.host }}` over SSH".
- A test fixture using `gitlab.example.com` and `PROJ-123`.
- An org's cluster inventory in `local/bundles/<org>/references/clusters.md`.

Non-compliant:

- A default `jira.url` pointing at a real company.
- A screenshot or log excerpt that shows an internal hostname.
- A README line that says the hub is "for team X".

## Open questions

- Whether to ship a reference org overlay (fictional organisation) as a worked example.
- Localisation of user-facing messages; today they are English only.
