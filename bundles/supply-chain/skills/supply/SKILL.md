---
name: supply
description: >-
  Read-only software supply-chain client via the `supply` CLI: ecosystem detection, unpinned
  actions, images and dependencies, CI workflow hardening, vulnerability audits, SBOMs, and
  signature or provenance verification. Use when the user mentions dependencies, lockfiles,
  pinning, Dependabot or Renovate, GitHub Actions `uses:` by tag, Dockerfile digests, an SBOM,
  SLSA, provenance, cosign, Sigstore, attestations, a CVE, GHSA or OSV id, `npm audit` or
  `pip-audit`, or asks whether a checkout, image or artefact is safe to use. Never installs,
  signs or switches verification off.
model: {{ core.model_policy.execute }}
---

# Supply chain (read-only client)

Generic client for the software supply chain of a checkout, an image or a file.

**Step 0 — repository-level harness (principle 8).** This is a user-level skill. Read the
repository's declaration first:

```bash
harness repo owns supply-chain/skills/supply   # rc 0 = owned (prints why) → stop; rc 1 = carry on
```

If it is owned (by id or by its domain `security`), or the repository ships its own skill for
the same workflow, this skill yields: say so in one line, name the repository-level skill or
convention, and stop — nothing below runs and nothing is merged. If the repository owns the
*workflow* but not the client, stay available as the plain client underneath it. Never edit
the repository's harness to fit this skill. `harness repo` explains everything the
repository declares and any `.claude/skills|agents` name collisions.

## Tooling

- **`supply` CLI** (this skill's `scripts/supply.py`, on PATH) — scans a checkout offline and
  runs the pinned scanners and verifiers read-only. Every tool output is redacted.
- **Optional pinned tools** it drives when present: `osv-scanner` (audit), `syft` (SBOM),
  `cosign` (signatures), `gh attestation verify` (GitHub provenance). Missing ones are
  installed by the human (`harness install osv-scanner|cosign|syft`), never by you. Without
  osv-scanner, `supply audit` uses the ecosystem's own auditor when it is already installed
  (`npm audit`, `pip-audit` on fully hashed requirements files only, `cargo-audit`,
  `govulncheck`) and never lets it run code from the checkout (see
  `references/vuln-triage.md`).

```bash
# hook: allow
supply detect [DIR]                                   # ALWAYS first: ecosystems, manifests, lockfiles
supply pins [DIR] --json                              # unpinned actions, images, deps, downloads
supply pins [DIR] --apply "$SCRATCH/pins.json"        # exact token rewrites (/pin-deps prepares the file)
supply ci .github/workflows/*.yml .gitlab-ci.yml [--ignore RULE,...]
supply audit [DIR] [--lockfile F]... [--sbom F.cdx.json] [--offline]
supply sbom DIR|IMAGE [--format spdx-json|cyclonedx-json] [--out F [--force]]
supply sbom lint FILE                                 # offline shape check of an SBOM
supply verify IMAGE --identity NAME                   # keyless, a configured signer
supply verify IMAGE --identity '^RE$' --issuer URL    # keyless, explicit (anchored ^…$)
supply verify IMAGE|FILE --github OWNER[/REPO]        # gh attestation verify
supply verify IMAGE --attestation --type slsaprovenance1 --identity NAME
supply verify FILE --bundle F.sigstore.json --identity NAME
supply redact < file                                  # stdin filter
```

```bash
# hook: ask — NEVER run; a human release step, hand it to the user
cosign sign IMAGE
cosign attest --predicate F IMAGE
```

```bash
# hook: deny — NEVER run; verification off, fix the trust root instead
cosign verify --insecure-ignore-tlog IMAGE
pip install --trusted-host pypi.example.com x
```

Common flags: `--json|--md`, `--max-bytes N` (`supply_chain.max_bytes`, 65536), `--timeout S`
(120, per tool run; the tool and its children are killed when it runs out). `supply sbom lint
FILE`: a directory named `lint` is passed as `./lint`; a `verify` TARGET starting with `-` as
`./-name`.

## Contract & rules

- **Exit codes**: `0` clean · `1` a `crit` or `warn` finding (also a usage error) · `2` access,
  tool or config error (unreadable DIR, a needed tool missing, the tool failing or timing out
  or printing JSON of an unexpected shape, `verify` failing — reported as `unverifiable: <first
  stderr line>` — or listing nothing, a bad config regex or an unanchored identity regexp, a
  refused or failed `pins --apply`) · `3` unsupported (no auditor for any detected ecosystem,
  `ci` with no scannable file, `sbom lint` on a non-JSON file, `verify --offline` without
  `--trusted-root`, or `--github --offline` without `--bundle`). `detect` exits 0 on any
  readable DIR. No command prints a Python traceback.
- **"Unavailable" is not "clean".** `AUD001` (no auditor), `AUD003` (the auditor errored),
  `SUP002` (a directory or file that could not be read), `CI000`, exit 3 and a missing
  `cosign`/`syft`/`gh` (exit 2) are reported as gaps in the answer, with `harness install
  <tool>` for the human — never as a pass.
- **Verification failing is a finding.** `supply verify` exit 2 means the signature or
  provenance did not verify against the identity you asked for; report it. Never retry with
  `--insecure-*`, `--allow-*-registry`, a looser identity regexp or another issuer.
- **Banner** on stderr (all but `redact` and `sbom lint`):
  `supply: dir=<DIR> ecosystems=<list|none> tools=<installed|none>` (`dir=-` for an image, a
  file and `ci`). Quote it: it says what could and could not be checked.
- **JSON envelope** (stdout not a TTY, or `--json`): `{command, dir, ecosystems, tools,
  findings, data}`, sorted keys, no timestamp. A finding is `{id, severity crit|warn|info, file,
  line, message, fix}`; pin findings add `ref`, the exact token as written. Findings are sorted
  by file, line, id and message. Over `--max-bytes`, trailing items are dropped and
  `"truncated": {"items_dropped": N, "max_bytes": M}` says so: narrow DIR rather than raising
  the cap by default.
- **Severities come from the rubrics**, never from your judgement:
  `references/pinning.md` and `references/ci-hardening.md` list every rule id with its
  severity and fix. `data.auditors[]` is `{ecosystem, tool, status
  ok|partial|unavailable|error|offline, packages}` (`packages` = packages with at least one
  reported vulnerability; `partial` = some files audited, the rest `AUD001`).
- **`pins --apply FILE`**: FILE is `[{"file", "line", "old", "new"}]` (paths relative to DIR,
  `old` = the `ref` of a current finding on that line, `new` = the same name pinned by digest
  or 40-hex sha). Every `old` must occur exactly once on its line as a whole token, files must
  be regular files `supply pins` scans (no symlink, no `.git`), or nothing is written (exit 2,
  one reason per entry). Writes are all-or-nothing (staged, re-read before the rename, rolled
  back on a failure part-way); the rest of each line — comments, spacing, line endings — is
  kept byte for byte; then it re-scans and exits like `pins`. With
  `supply_chain.pin_actions = false`, action pins are skipped and listed in `data.skipped`.
  The rules are in `references/pinning.md`.
- **`supply ci --ignore RULE,…`** is the only way to silence a rule, and the reason goes in the
  MR/PR description. Never add an ignore comment to a workflow.
- **Config** (`[supply_chain]` in `local/harness.toml`, then `harness apply`):
  `identities` (`[[supply_chain.identities]]` name, identity_re, issuer, match_re — public
  values, never a key; `identity_re` anchored `^…$`), `registries_re` (allowed registry hosts; `REG001` outside it),
  `exclude_re` (paths to skip), `osv_offline_db`, `pin_actions`, `redact_extra_re`, `timeout`,
  `max_bytes`. The environment wins: `SUPPLY_REGISTRIES_RE`, `SUPPLY_EXCLUDE_RE`,
  `SUPPLY_REDACT_EXTRA_RE`, `SUPPLY_OSV_OFFLINE_DB`, `SUPPLY_TIMEOUT`, `SUPPLY_MAX_BYTES`.
- Guard-hook decisions (the hook wins over `permissions.allow` — do not route around it):

  | Command | Decision | Rationale |
  |---|---|---|
  | `supply <any subcommand>`, `cosign verify*`, `gh attestation verify`, `osv-scanner`, `syft`, `npm audit`, `pip-audit` | allow | read-only |
  | `pip install` outside a venv, `npm i -g`, `cargo install`, `go install …@latest` | **ask** | installs into the machine |
  | unpinned git or URL dependency (`pip install git+…`, `npm i github:…`, `cargo add --git` without `--rev`) | **ask** | pin a commit; `supply pins` lists them |
  | `cosign sign\|attest\|generate-key-pair` | **ask** | a human release step |
  | `--trusted-host`, `strict-ssl false`, `http.sslVerify=false`, `GOINSECURE`, `cosign verify --insecure-*` | **deny** | verification off |

## Procedure

**Step 1 — Orient.** `supply detect DIR` and read the banner: which ecosystems exist and which
tools can check them.

**Step 2 — Pins and CI.** `supply pins DIR --json`, then `supply ci` on each workflow file the
detect output lists. Pinning work goes to `/pin-deps`; never hand-edit a lockfile.

**Step 3 — Vulnerabilities.** `supply audit DIR --json`. Read `data.auditors` first: anything
`unavailable`, `error` or `offline` is a gap to report. Upgrades within the same major go to
`/audit-deps`; a hard case (is it reachable? which path pulls it in?) to `supply-triage`.

**Step 4 — Artefacts.** `supply sbom lint` on an SBOM the repository ships; `supply verify` on
the image or file the user will run, by the identity the release workflow signs with.

**Step 5 — Report.** Banner · findings grouped Critical / Warnings / Suggestions, each
`severity · path:line · rule id · fix` · what could not be checked (tools missing, `CI000`
files, exit 3) · the commands the human runs next (`harness install …`, signing).

## Never

- Never pass `--insecure-*`, `--allow-insecure-registry`, `--allow-http-registry`,
  `--trusted-host`, `strict-ssl false` or `http.sslVerify=false` to make a check pass.
- Never run `cosign sign|attest|generate-key-pair` or any publish: hand them to the user.
- Never install into the machine (`pip install` outside a venv, `--user`, `sudo`, `npm i -g`,
  `cargo install`) and never install a scanner yourself.
- Never hand-edit a lockfile: regenerate it with the ecosystem's tool (`/audit-deps`).
- Never report "unavailable" as "clean", or an exit 2 from `verify` as a pass.
- Never silence a `supply ci` rule without the reason in the MR/PR description.

## References

- `references/pinning.md` — pin rule ids (GHA, CI006, CI008, CI009, DKR, PIP, NPM, GO, CGO, SH,
  REG, SUP): severity, what matches, the fix.
- `references/ci-hardening.md` — CI rule ids (CI000–CI007): severity, what matches, the fix.
- `references/provenance.md` — signatures, attestations, SLSA levels and `supply verify`.
- `references/sbom.md` — SPDX and CycloneDX, `supply sbom`, the SBM rule ids.
- `references/vuln-triage.md` — from an OSV001/VUL001 finding to a fix, a mitigation or an
  accepted risk; the AUD ids.
- `references/threat-model.md` — the supply-chain threats these checks address and the ones
  they do not.
