# Reference: security

How the hub frames security engineering, so that every security bundle has the same shape as
the rest of the hub. This page is the design reference for the security bundle family; the
hub's own threat model and vulnerability reporting are in [SECURITY.md](../../SECURITY.md).

A security bundle lets the agent do three things, the same three the
[SRE track](../roadmap.md#sre-track) names for reliability work:

- **architect** — `plan` agents that design a posture and never edit (pinning policy, signing
  and provenance strategy, threat models);
- **develop** — `workflow` skills and `client` CLIs whose output is a change in the
  repository (pins, lockfiles, SBOMs, CI hardening, policy as config), delivered as an MR/PR;
- **operate** — `review` agents that assess a checkout, an image or a pipeline, and
  `investigate` agents that take one finding (an advisory, a failed verification) to a root
  cause and a remediation for the human.

## What a user-level harness can do

The agent runs in the developer's shell with the developer's credentials. The hub can steer
what the agent does there (rules, skills), sense it before and after it happens (guard rows,
doctor checks, test suites, review agents) and land every fix as a reviewed repository change.
That is the whole reach of a security bundle.

Out of scope by construction:

- exploitation, payload development, detection evasion and red-team tooling;
- active scanning of hosts, networks or services the developer does not own;
- anything that must hold *against* a repository or its contributors: branch protection,
  required signatures, mandatory CI checks and admission policy are server-side controls
  ([principle 8](../../principles/08-user-level-by-design.md): a rule that must hold against a
  repository belongs server-side, not in a user-level harness).

## Disciplines

| Discipline | Domain | Architect (`plan`) | Develop (`workflow`, `client`) | Operate (`review`, `investigate`) | Posture | Covered today / planned | Out of scope here |
|---|---|---|---|---|---|---|---|
| Software supply chain | `security` | `supply-architect` | `/pin-deps`, `/audit-deps`, `supply` CLI | `supply-auditor`, `supply-triage` | local | planned: `supply-chain` (38) | publishing, signing with the developer's key, registry administration |
| Secrets and credential management | `base` | — | `secrets` CLI | `secrets scan` | read-only | `core/guard.d/20-credentials`; planned: `secrets` (22) | vault administration, rotating someone else's credential |
| Application security | `security` | `appsec-architect` | `/draft-threat-model` | `appsec-reviewer` | read-only | `core/agents/code-reviewer`; candidate: `appsec` (39) | pip-installed SAST (rejected), DAST against targets you do not own |
| Infrastructure and cloud posture | the system's own (`kubernetes`, `infrastructure`) | `infra-architect` | chart, overlay and IaC changes | `k8s-auditor`; planned `iac-reviewer` | read-only | `k8s`; planned: `iac`, `cloud`, `containers`, `hosts` | live remediation, `[PROD]` mutations |
| Identity and access | the system's own; `security` for a cross-system review | — | `iam` CLI | `iam-auditor` | read-only | planned: `k8s rbac`, `iac` IAM diff; candidate: `iam` (43) | creating tokens, keys or role bindings (human-only) |
| Vulnerability management | `security` | — | `supply audit`; `vuln` CLI | `supply-triage`; `vuln-triage` | read-only | planned: `supply-chain`; candidate: `vuln` (42) | exploitability proofs |
| Detection and response | `operations` | — | `incident timeline`, `/postmortem` | `/triage` (`k8s-triage`, `obs-triage`) | label-gated | `obs`; planned: `incident` | SIEM, EDR, paging, containment actions |
| Data protection and privacy | `security` | — | the shared `redact` block | `privacy-reviewer` | read-only | the `redact` block in every CLI; candidate: `privacy` (44) | data-loss prevention, legal assessments |
| Governance, risk and compliance | `security` | — | `compliance check` | `compliance-reviewer` | read-only | policy as config in every bundle; candidate: `compliance` (46) | audits, certification, attestations as a service |

Names in the table that do not exist yet are proposals reserved in the
[roadmap](../roadmap.md#security-track); nothing is renamed to fit once it ships.

### Software supply chain

Everything between a dependency's publisher and the artefact the repository ships: lockfiles
and pins (dependencies by exact version, GitHub Actions by commit, images by digest), CI
workflow hardening, SBOMs, signatures and provenance (Sigstore, in-toto, SLSA, GitHub artifact
attestations), and known vulnerabilities in what is locked. The agent installs inside the
project, never into the machine, and never switches verification off. First bundle of the
family: `supply-chain`.

### Secrets and credential management

Where credentials live and how they are kept out of transcripts, commits and tickets. The
credential denies are the one thing in the hub that never yields to a repository, which is why
this discipline stays in `base` (see [which domain](#which-domain-security-or-the-systems-own)).
Today: `core/guard.d/20-credentials` and the shared `redact` block; planned: the `secrets`
bundle (decrypt-to-stdout denies, `secrets scan`).

### Application security

Design-level and code-level security of the repository's own code: trust boundaries, threat
models, input handling, authentication and authorisation paths. The review is an agent with a
fixed checklist in the `code-reviewer` contract; a threat model is a rendered document with a
golden ([principle 9](../../principles/09-deterministic-by-construction.md)). A pip-installed
SAST scanner stays rejected ([principle 1](../../principles/01-lightweight.md)); the thorough
scan belongs in CI.

### Infrastructure and cloud posture

A posture review of one system stays in that system's bundle and domain: pod security, RBAC
and image hygiene are `k8s-auditor` with the rubric in
`bundles/k8s/skills/k8s/references/security-audit.md`; IaC and cloud reviews go to the planned
`iac` and `cloud` bundles. A security bundle points at them and reuses the rubric shape; it
does not duplicate them.

### Identity and access

Who and what can act where: SCM permissions, cloud IAM, Kubernetes RBAC, service accounts and
tokens. Per-system reads stay in their bundles; a cross-system `iam-auditor` that correlates
them is a candidate. Creating tokens, keys or role bindings is human-only.

### Vulnerability management

Known vulnerabilities in dependencies and images, normalised into one finding shape, triaged
(fixed version, direct or transitive, reachable in this code) and fixed as an upgrade in an
MR/PR. It starts inside `supply audit`; a separate `vuln` bundle earns its place only once
image scanning (`containers`) and dependency audits need one ignore and VEX format.

### Detection and response

A security incident is an incident: the `incident` workflow with a security severity, the
signals from `obs`, the cluster from `k8s`. No separate security bundle; containment actions
are handed to the human like every other remediation.

### Data protection and privacy

Personal and sensitive data in schemas, migrations, logs and fixtures. Every CLI already
prints through the shared `redact` block; a `privacy-reviewer` (personal data in schemas and
logs, retention, test data) is a candidate.

### Governance, risk and compliance

Policy is configuration: allowed registries, expected signing identities, licence policy and
severity thresholds are `[requires.config]` keys or an organisation overlay consumed by the
other bundles ([principle 3](../../principles/03-platform-for-everyone.md)). A `compliance`
bundle would only render evidence from those bundles' outputs, deterministically.

## Which domain: `security` or the system's own

The domain of a component is its **subject**, not its motive.

- **`security`** — components whose subject is a security artefact or finding that spans
  systems: lockfiles and pins, SBOMs, signatures and attestations, advisories, CI policy,
  threat models.
- **The system's own domain** — a posture review of one system. `k8s-auditor` stays
  `kubernetes`; a future `iac-reviewer` is `infrastructure`.
- **`base`** — credentials. The credential denies never yield
  ([principle 8](../../principles/08-user-level-by-design.md)), and a repository that declares
  `[owns] domains = ["security"]` must not lift them; keeping the `secrets` bundle in `base`
  makes that structural.

A repository that owns `security` takes over every component in the family (their guard
sections pass, their skills yield); the developer's credential denies stay in force.

## Crosswalk: NIST CSF functions to hub facets

| CSF function | Hub facet | Components |
|---|---|---|
| Govern | function `govern` | rules, guard sections, permission lists; policy as `[requires.config]` |
| Identify | function `review`, `client` | `supply-auditor`, `k8s-auditor`; `supply detect`, `supply pins` |
| Protect | function `govern` + `workflow` | guard rows on unpinned and unverified installs; `/pin-deps` |
| Detect | control = sensor (derived) | guard rows, doctor checks, test suites, review agents |
| Respond | function `investigate` + the `incident` workflow | `supply-triage`, `/triage` |
| Recover | domain `operations` | `incident`, `dr-auditor` |

The eight `function` values and the derived `control` facet cover every CSF function, so the
family needs no new `function` or `posture` value.

## Invariants of every security bundle

- **Reads and local scans are free.** Detection, audits, SBOM generation and verification run
  without a prompt.
- **Mutations ask or deny, with the alternative.** Signing, attesting, publishing and key
  operations ask: they are human release steps. Every `ask` and `deny` reason says what to do
  instead.
- **Verification is never switched off.** Flags and variables that disable TLS, signature,
  checksum or checksum-database verification deny; the reason names the trust-root fix (CA
  bundle, key, `GOPRIVATE`) instead.
- **Findings have a fixed shape and every remediation lands as a repository change.** Reviews
  use the `code-reviewer` contract (Critical / Warnings / Suggestions, each with evidence, a
  path and the fix); investigations use the `k8s-triage` contract (Summary · Evidence · Root
  cause · Remediation for the human · Not verified · Next). Fixes go through an MR/PR.
- **Output is redacted.** Scanner and tool output passes through the shared `redact` block
  (`bundles/core/lib/redact.py`, inlined with `sync_inline.py`).
- **Third-party scanners are optional and pinned.** A scanner is an optional
  `[requires.binaries]` entry installed by `harness install <tool>` from a
  `tools/<tool>.lock.json` with a sha256 per OS and architecture; never pip, npm or a
  download piped to a shell ([principle 1](../../principles/01-lightweight.md)). Ecosystem
  auditors already on the machine are used when present and never installed.
- **Organisation policy is configuration.** Registries, signing identities, licence policy
  and thresholds are config keys with documentation-value examples, or an org overlay; never
  hard-coded ([principle 3](../../principles/03-platform-for-everyone.md)).
- **Everything yields to the repository**, except the developer's own credential denies
  ([principle 8](../../principles/08-user-level-by-design.md)): Step 0 in every skill,
  `repo_owns … security` first in every guard section, the baseline sentence in every agent.

## The family

| Bundle | Guard band | Config section | Env prefix | Architect / develop / operate | Status |
|---|---|---|---|---|---|
| `supply-chain` | `38` | `supply_chain.*` | `SUPPLY_` | `supply-architect` / `/pin-deps`, `/audit-deps`, `supply` / `supply-auditor`, `supply-triage` | planned (#51); supersedes `toolchain` |
| `appsec` | `39` | `appsec.*` | `APPSEC_` | `appsec-architect` / `/draft-threat-model` / `appsec-reviewer` | candidate |
| `vuln` | `42` | `vuln.*` | `VULN_` | — / `vuln` CLI / `vuln-triage` | candidate, after `supply-chain` and `containers` |
| `iam` | `43` | `iam.*` | `IAM_` | — / `iam` CLI / `iam-auditor` | candidate |
| `privacy` | `44` | `privacy.*` | `PRIVACY_` | — / — / `privacy-reviewer` | candidate |
| `compliance` | `46` | `compliance.*` | `COMPLIANCE_` | — / `compliance check` / `compliance-reviewer` | candidate |

Related bundles outside the family keep their own bands and domains: `secrets` (`22`, `base`),
`containers` (`36`, `infrastructure`), `release` (`45`, `scm`), `ci` (`55`, `scm`). Bands
`47`–`49` and `85` stay free.

An env prefix is added to the guard's accepted list (`bundles/core/guard/engine.sh`, the
`case "$_gk"` line, and `GUARD_ENV_PREFIXES_FALLBACK` in `lib/harness/lint.py`, which a unit
test keeps equal) in the PR that ships the bundle's guard section. A bundle whose guard reads
no environment needs none.

## Writing a security bundle

The general checklist is CONTRIBUTING ["Adding a bundle"](../../CONTRIBUTING.md#adding-a-bundle);
these points are specific to security bundles.

- **Rule, guard row or review agent.** A rule says what the agent should prefer and why (pin,
  verify, use the CLI). A guard row is the mechanical sensor for what the rule forbids or
  wants a human to see. A review agent is the inferential sensor for what no regular
  expression sees: reachability, design weaknesses, whether an exception is justified.
- **Deny reasons for a verification bypass** name the trust-root fix, for example:

  ```text
  # rule: <tool> --insecure | -k | GIT_SSL_NO_VERIFY=1 | PIP_TRUSTED_HOST=... | GOINSECURE=... -> deny : disables TLS, signature or checksum verification; fix the trust root (CA bundle, key, GOPRIVATE) or pin the expected digest instead
  ```

- **Test rows.** Every `deny` and `ask` gets a row, a `tr` row for its reason, and bypass
  rows: `env VAR=… cmd`, `sh -c "…"`, `cd x && …`, `xargs`, a path-qualified binary, split
  quoting. Add a `pass` row for the legitimate alternative (`--cacert FILE`, the venv form)
  and a row proving the section passes when the repository owns `security`.
- **Severities come from a rubric, not from the agent.** Copy the shape of
  `bundles/k8s/skills/k8s/references/security-audit.md` §1: finding · severity · why, raised
  one level in `[PROD]` where a production target exists.
- **Scanner output is normalised by a script with goldens**
  ([principle 9](../../principles/09-deterministic-by-construction.md)); the agent never
  re-types findings and never treats "scanner unavailable" as "clean".

## Related

- [SECURITY.md](../../SECURITY.md) — the hub's own threat model and reporting
- [Governance](../governance.md) — the rules every bundle follows
- [Roadmap: Security track](../roadmap.md#security-track) — bands, names and delivery order
- [Taxonomy](taxonomy.md) — domain, function and posture values
- [Secrets](secrets.md) — where every credential lives
- [Repository-level harnesses](../repo-level.md) — what owning a domain lifts
