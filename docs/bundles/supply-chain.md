# Bundle: supply-chain

The software supply chain for agents: pin what you add, install inside the project, never switch
verification off. The first bundle of the [security family](../reference/security.md) (domain
`security`, posture `local`). It lands in parts across #51: the rule, guard section 38, the
permission list, the read-only `supply` CLI with its client skill (`detect`, `pins`, `ci`,
`audit`, `sbom`, `verify`, `redact`), the pinned, optional `osv-scanner`, `cosign` and `syft`
(`harness install TOOL`; bootstrap never fetches them unasked), the `/pin-deps` and
`/audit-deps` workflow skills and the `supply-architect`, `supply-auditor` and `supply-triage`
agents.

- `/pin-deps [DIR] [--actions|--images|--deps] [--no-apply]` turns `supply pins` findings into
  pins: a tag is resolved read-only to the commit or digest it points at today (`git
  ls-remote`, `gh api` GET, `crane digest` or `docker buildx imagetools inspect` when
  installed), written with `supply pins --apply` (which keeps an action's tag as its comment,
  ` # v4`) and checked by `supply pins` again. A branch,
  `latest` or a missing ref is a version choice: the latest release is listed as a suggestion,
  applied only when the user accepts. Unresolved values stay unresolved — a sha, digest or
  checksum is never guessed. A GitLab include with no `ref:` is left to the human. A
  repository whose Renovate or Dependabot pins is reported first.
- `/audit-deps [DIR] [--offline] [--fix patch|minor|none]` upgrades each `OSV001`/`VUL001`
  package to its lowest fixed release (never a pre-release) with the ecosystem's lockfile tool,
  run so that nothing from the checkout executes and no toolchain or interpreter is downloaded:
  `UV_PYTHON_DOWNLOADS=never uv lock --upgrade-package NAME==X.Y.Z --no-build`; `npm install
  NAME@SPEC --package-lock-only --ignore-scripts` (SPEC keeps the manifest's `^`, `~` or exact
  prefix) or `npm update NAME --package-lock-only --ignore-scripts`; `pnpm update NAME@X.Y.Z
  --lockfile-only --ignore-pnpmfile --ignore-scripts` with package-manager switching off, and
  only without a `.pnpmfile.cjs` or a `packageManager` version other than the installed pnpm;
  `cargo update -p NAME --precise X.Y.Z` only without a `rust-toolchain` file or a
  `.cargo/config*` that names a credential provider or a rustc wrapper; `GOTOOLCHAIN=local go
  get`. Poetry, and every case above that does not hold, is a manual change for the human. It
  never crosses a major (for `0.x`, a `0.MINOR`; a `0.0.x` package never upgrades), checks each
  new locked version against the `--fix` limit (an overshoot is reverted and reported), and
  re-runs `supply audit`. It never runs the project's tests: it names the test command and
  reports the upgrade as untested. The report separates what the diff fixed, what needs a major
  upgrade or a manual change, what has no fix, what an open Dependabot or Renovate pull request
  already covers, and the ecosystems whose auditor was `unavailable`, `offline` or `error`
  (an osv-scanner `--offline` audit is `ok` with `"offline": true`).
- Agents, all read-only (`Read, Grep, Glob, Bash`, no `permissionMode`): `supply-architect`
  (plan model; current and target posture, a phased plan with a sensor per change, a decision
  record), `supply-auditor` (Critical / Warnings / Suggestions / Not verified, severities only
  from the rubrics; the bundle's review-agent sensor) and `supply-triage` (one vulnerability,
  failed verification or suspicious dependency to its root cause; stops after three unresolved
  hypotheses). They never install, edit, sign or push; a command the guard would ask or deny on
  becomes a finding for the human.
- Neither skill commits or pushes: the diff is the user's to review.

- Switching TLS or signature verification off is **denied**: `pip|uv --trusted-host` (also a
  unique prefix such as `--trusted`), `uv --allow-insecure-host`, an `http://` index (`-i`,
  `--index[-url]`, `--extra-index[-url]`, `--default-index`, `pip config set
  <section>.trusted-host|index-url`, `PIP_TRUSTED_HOST`, `PIP_*INDEX_URL`, `UV_INSECURE_HOST`,
  `UV_*INDEX*`), npm/pnpm/yarn `strict-ssl false` (`config set`, `set`, `--strict-ssl=false`,
  `--no-strict-ssl`, `npm_config_strict_ssl`), an `http://` registry (`config set registry`,
  `--registry`, `--reg`), yarn `enableStrictSsl false` / `npmRegistryServer http://` /
  `unsafeHttpWhitelist` / `YARN_ENABLE_STRICT_SSL=false`, `NODE_TLS_REJECT_UNAUTHORIZED=0`,
  git `-c|--config http[.<url>].sslVerify=false|no|off|0|<empty>`, `git config http.sslVerify
  false`, `--config-env`, `GIT_CONFIG_KEY_<n>=http.sslVerify`, `GIT_SSL_NO_VERIFY`,
  `GOINSECURE=<value>`, `GOFLAGS=-insecure`, `go get -insecure`, `go env -w
  GONOSUMDB|GONOSUMCHECK=<value>`, `GOSUMDB=off`, `cosign verify* --insecure-*|--allow-*-registry|
  --private-infrastructure` (any true value), and a reader taking `cosign.key` or a key under
  `~/.sigstore/` (any `.sigstore/**/*.key`, so `cd ~` is no bypass) as a file operand. Each reason names the trust-root fix (`PIP_CERT`,
  `NODE_EXTRA_CA_CERTS`, `http.sslCAInfo`, `GOPRIVATE`).
- Installing into the machine **asks**: `pip install` outside a venv, with `--user`,
  `--break-system-packages`, `sudo`, or `--target|--prefix` outside the checkout; `uv pip
  install --system|--break-system-packages` and `UV_SYSTEM_PYTHON=1`; `npm|pnpm -g` (also
  `-gD`); `yarn global add`; `cargo install` without both `--locked` and `--version`;
  `go install …@latest|@main`. Isolated or pinned tool installs pass: `pipx install`,
  `uv tool install`, `go install m@v1.2.3`, `cargo install X --locked --version V`. Tools you
  install globally on purpose go in `supply_chain.allow_global_re`: an anchored ERE (`^…$`)
  every spec after the first install verb must match (redirections such as `2>&1` are not
  specs).
- Unpinned git and URL dependencies **ask** (`pip install git+URL` without a commit,
  `npm install github:owner/repo` or `owner/repo` without `#<40-hex sha>`, any npm tarball URL
  (a fragment is no pin), `cargo add --git` with `--branch` or with neither `--rev` nor
  `--tag`); so do a one-shot `GONOSUMDB=<value>`, `cosign sign|attest|attach|upload|copy|clean|
  generate-key-pair` (a human release step) and `curl -k` or `wget --no-check-certificate`
  writing a file or piping into `tar|unzip|tee|dd|cpio`. An insecure `curl -k` to stdout,
  `-o -` or `-o /dev/null` passes.
- How commands are read: newlines, `;`, `&&`, `|`, subshells, `{ }`, `if/for/while` bodies,
  `$( )`, backticks and `sh -c` / `eval` strings are separate commands; quotes and backslashes
  are removed first (`'pip'`, `g\it`); wrappers (`env`, `sudo`, `nice -n 5`, `timeout 5`,
  `exec`, `declare -x`, `readonly`, …) do not hide an assignment. A command that only prints
  or searches text (`echo`, `printf`, `grep`, `rg`, `sed`, `awk`, `cat`, `head`, `tail`,
  `less`, `man`, `help`, `git log|grep|show|commit|diff`) is exempt unless the line runs text
  as code (`$( )`, backticks, `eval`, `sh -c`, a pipe into a shell); heredoc bodies are data
  unless a shell reads them; `--help`, `-h` and `<tool> help` are reads.
- Venv detection: a name from `supply_chain.venv_markers` set in the guard's own environment
  (the provider was started from an activated venv; `CONDA_PREFIX` counts only outside conda's
  base env: not when `CONDA_DEFAULT_ENV` is empty, `base`, `root` or the prefix itself, nor when
  the prefix is `${CONDA_EXE%/bin/*}` or `$MAMBA_ROOT_PREFIX`), an earlier
  `source …/bin/activate` clause (a later `deactivate` cancels it), a runner (`uv`, `poetry`,
  `pipenv`, `pdm`, `hatch`, `pipx run`), a venv's `…/bin/pip|python` as the command word,
  `--dry-run`, or `--target|--prefix` inside the checkout. A `VIRTUAL_ENV=` assignment on the
  command line is not a marker.
- A repository that owns the `security` domain in its `.harness.toml` lifts every rule of
  section 38, the verification denies and the read deny on its own `cosign.key` included,
  except the read deny on keys under `~/.sigstore/`: that is the developer's own signing key
  and sits in a `# never-yields:` prelude above the `repo_owns` line, like the credential
  denies of core section 20 ([repository-level
  harnesses](../repo-level.md#what-owning-a-domain-lifts)).

Config: `supply_chain.allow_global_re`, `supply_chain.venv_markers` (both read by the guard),
and `supply_chain.registries_re`, `supply_chain.identities`, `supply_chain.redact_extra_re`,
`supply_chain.exclude_re`, `supply_chain.osv_offline_db`, `supply_chain.pin_actions`,
`supply_chain.timeout`, `supply_chain.max_bytes` for the `supply` CLI.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `pip install` asks although I work in a venv | the agent was started outside the venv, so the guard's environment has no `VIRTUAL_ENV` | start the agent from the activated venv, or run `.venv/bin/pip install …` / `uv pip install …`; add your tool's variable to `supply_chain.venv_markers` and run `harness apply` |
| `pip install` asks in conda's `base` env | an auto-activated `base` is the machine's Python, so `CONDA_PREFIX` with `CONDA_DEFAULT_ENV=base` (or unset) is no venv marker | create and activate a project env (`conda create -n shop`, `conda activate shop`) before starting the agent, or use `uv` / `.venv/bin/pip` |
| `pip install` passes outside any venv | a marker from `supply_chain.venv_markers` is set in the agent's environment (a leftover `VIRTUAL_ENV`, a custom marker) | unset it before starting the agent, or narrow `supply_chain.venv_markers` and run `harness apply` |
| A global tool install asks every time (`npm i -g`, `cargo install`, `pip install --user`) | global installs ask by design | prefer an isolated or pinned install (`pipx install`, `uv tool install`, `cargo install X --locked --version V`), or add the tool to `supply_chain.allow_global_re` (an anchored ERE every spec after the install verb must match, e.g. `^(ripgrep\|typescript)$`) and run `harness apply` |
| `sudo pip install` asks although the tool is allow-listed | `sudo` and `--break-system-packages` are never allow-listed | install into the project, or hand the command to the user |
| `pip install git+https://…@v1.2.3` passes but `supply pins` flags it | a tag passes the guard; a tag can move, so the pin check still reports it | pin the commit (`@<sha>`) |
| A command is denied with `switches TLS verification off` | `--trusted-host`, `--allow-insecure-host`, an `http://` index or registry (flag or config), `strict-ssl false`, `http.sslVerify=false`, `GIT_SSL_NO_VERIFY`, `GOINSECURE` | fix the trust root instead: `PIP_CERT` / `REQUESTS_CA_BUNDLE`, npm `cafile` / `NODE_EXTRA_CA_CERTS`, `git config http.sslCAInfo`, `GOPRIVATE`; or ask the user |
| `cosign verify … --insecure-ignore-tlog` is denied | skipping the transparency log or SCT check is a verification bypass | run `cosign verify` without the flag; a failure (exit 2) is a finding to report |
| `curl -k … -o FILE` or `curl -k … \| tar x` asks | an unverified download written to disk | `curl --cacert <CA bundle> … -o FILE`; `-o /dev/null` and stdout pass |
| `VIRTUAL_ENV=… pip install` asks | an assignment does not activate the venv (pip still runs from `PATH`) | run `.venv/bin/pip install …` or `uv pip install …` |
| `echo`/`grep` of a guarded command is denied | the line also runs text as code (`$( )`, backticks, `eval`, `sh -c`, a pipe into a shell), so the text exemption is off | split the command, or drop the code-running part |
| `GOSUMDB=off` is denied | the checksum database is switched off for every module | `GOPRIVATE=<module prefix>`, or a one-shot `GONOSUMDB=<module prefix>` (asks) |
| `GONOSUMDB=… go mod download` asks | the checksum database is skipped for those modules | set `GOPRIVATE=<module prefix>` for private modules |
| `supply audit` says `unavailable` / doctor WARNs `bin-supply-chain-osv-scanner` | osv-scanner is optional and bootstrap does not install it | `harness install osv-scanner` (manual step `install-supply-tools`; air-gapped: `--from FILE`) |
| `supply audit --offline` exits 2 `no offline version of the OSV database` | osv-scanner reads its offline databases from `DIR/osv-scalibr/<Ecosystem>/all.zip` and the CLI never downloads them | download them once by hand (`OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY=DIR osv-scanner scan source --offline-vulnerabilities --download-offline-databases -r .`; `-r .` downloads databases only for the ecosystems found in that directory, so run it in each repository you audit offline) and set `supply_chain.osv_offline_db = "DIR"`, or drop `--offline` |
| `supply verify IMAGE --offline` exits 3 | cosign 3.1.4 deprecated `--offline` and reads an image's signatures from its registry; nothing keeps it offline | verify a downloaded file: `supply verify FILE --bundle F --trusted-root F --offline`, or `supply verify IMAGE --github OWNER/REPO --bundle F --trusted-root F --offline`; else drop `--offline` |
| `supply verify IMAGE --bundle F` exits 1 | cosign 3 reads an image's signatures from its registry; `--bundle` is for a file | drop `--bundle`, or use `--github OWNER/REPO --bundle F` |

<!-- generated:begin source=bundles/supply-chain/bundle.toml -->
## Summary

Software supply chain: pin what you add, install inside the project, never switch verification off (guard 38, the supply CLI, /pin-deps, /audit-deps and three read-only agents)

Guard section 38 and its rule: switching TLS or signature verification off denies (pip
--trusted-host, uv --allow-insecure-host or an http:// index or registry, npm strict-ssl
false, git http.sslVerify=false and GIT_SSL_NO_VERIFY, GOINSECURE, -insecure and GOSUMDB=off,
cosign verify --insecure-*, reading cosign.key or ~/.sigstore keys, the latter never lifted by a
repository declaration); installs into the machine ask (pip outside a
venv or conda base, --user, sudo, uv pip --system, npm|pnpm -g, yarn global add,
cargo install without --locked --version, go install @latest; pipx, uv tool install and
pinned installs pass), so do unpinned git and URL dependencies, GONOSUMDB,
cosign sign|attest and insecure downloads written to a file. supply_chain.allow_global_re
allow-lists global tools; venv detection reads the hook's environment and the command text.
The read-only `supply` CLI and client skill: detect (ecosystems, manifests, lockfiles), pins
(unpinned actions, images, dependencies and unverified downloads, with an exact-token
--apply), ci (workflow hardening), audit (osv-scanner, else npm audit, pip-audit, cargo-audit,
govulncheck), sbom (syft) and sbom lint, verify (cosign, gh attestation verify) and redact.
Pinned, sha256-verified osv-scanner, cosign and syft are optional (`harness install TOOL`;
bootstrap never fetches them unasked; `harness pack --tools-optional` ships them air-gapped).
Workflow skills /pin-deps (resolve tags to commit shas and digests read-only, apply them with
supply pins --apply, re-run supply pins) and /audit-deps (upgrade vulnerable dependencies within
the same major with the ecosystem's lockfile tool, re-run supply audit); neither commits or
pushes. Read-only agents supply-architect (design, plan model), supply-auditor (review) and
supply-triage (one finding to its root cause).

- **Depends on:** `core`
- **Recommends:** `github`
- **Stability:** experimental
- **Domain / posture:** security / local

## Components

Stable ids derived from the path, with their [taxonomy](../reference/taxonomy.md) facets (domain shown only where it differs from the bundle's). All bundles: [catalog](../catalog.md).

**Skills**

- `supply-chain/skills/audit-deps` — control: guide · function: workflow · posture: local · model: execute · yields: declaration
- `supply-chain/skills/pin-deps` — control: guide · function: workflow · posture: local · model: execute · yields: declaration
- `supply-chain/skills/supply` — control: guide · function: client · posture: read-only · model: execute · yields: declaration

**Agents**

- `supply-chain/agents/supply-architect` — control: guide · function: plan · posture: read-only · model: plan · yields: name
- `supply-chain/agents/supply-auditor` — control: guide + sensor (inferential) · function: review · posture: read-only · model: execute · yields: name
- `supply-chain/agents/supply-triage` — control: guide · function: investigate · posture: read-only · model: execute · yields: name

**Rules**

- `supply-chain/rules/38-supply-chain` — control: guide · function: govern · yields: text

**Guard sections**

- `supply-chain/guard.d/38-supply-chain` — control: sensor · function: govern · decisions: deny 8 · ask 8 · yields: declaration

**Permission lists**

- `supply-chain/permissions` — control: guide · function: govern · decisions: deny 4 · ask 6 · allow 21 · yields: config

**CLIs**

- `supply-chain/bin/supply` — function: client · posture: read-only · yields: n/a

**Doctor checks** (function: setup · posture: read-only; table below): `supply-chain/doctor/supply-cli`, `supply-chain/doctor/supply-config`, `supply-chain/doctor/supply-detect`

**Manual steps** (function: setup; table below): `supply-chain/steps/configure-identities`, `supply-chain/steps/install-supply-tools`

## Requirements

### Binaries

| binary | min version | install | optional | why |
|---|---|---|---|---|
| `cargo-audit` | 0 |  | yes | `supply audit` fallback for Cargo.lock when osv-scanner is absent (the binary, never `cargo audit`); used only when already installed. |
| `cosign` | 3.1.4 | `harness install cosign` | yes | `supply verify` of image signatures, attestations and Sigstore-bundled files (verify* only; signing is the human's release step). Pinned in tools/cosign.lock.json; min_version = the version supply was checked against. |
| `gh` | 2.49.0 | `harness install gh` | yes | `supply verify --github` runs `gh attestation verify` (gh 2.49 or newer). |
| `git` | 2.30 |  | no | Pin resolution and history lookups (`git ls-remote`, `git log -S`) run read-only git. |
| `govulncheck` | 0 |  | yes | `supply audit` fallback for Go modules when osv-scanner is absent; used only when already installed. |
| `npm` | 0 |  | yes | `supply audit` fallback for npm lockfiles (`npm audit --json`) when osv-scanner is absent; used only when already installed. |
| `osv-scanner` | 2.7.0 | `harness install osv-scanner` | yes | `supply audit` for every ecosystem and for SBOMs (scan source --all-packages); without it the ecosystem's own auditor, if installed. Pinned in tools/osv-scanner.lock.json; min_version = the version supply was checked against. |
| `pip-audit` | 0 |  | yes | `supply audit` fallback for fully hashed requirements files when osv-scanner is absent; used only when already installed. |
| `python3` | 3.9 |  | no | The supply CLI is stdlib python. |
| `syft` | 1.55.0 | `harness install syft` | yes | `supply sbom` (dir: or registry:, never the docker daemon). Pinned in tools/syft.lock.json; min_version = the version supply was checked against. |

### Configuration

| key | type | required | default | description |
|---|---|---|---|---|
| `supply_chain.allow_global_re` | string | no | `""` | POSIX ERE (the guard applies it with grep -E) that every spec of a global install must match for it to pass without a prompt: pip outside a venv or with --user, npm\|pnpm -g, yarn global add, cargo install. Matched against each word after the first install verb as typed (name and any version; options and redirections are skipped), so anchor it (^…$). Use [0-9] and [[:space:]], never \d or \s. Empty = every global install asks. SUPPLY_ALLOW_GLOBAL_RE. |
| `supply_chain.exclude_re` | string | no | `""` | Python regex matched against paths relative to DIR that the supply CLI skips (detect, pins, audit, sbom), on top of .git, node_modules, vendor, .venv, venv, target, dist, build, __pycache__ and .tox. Empty = skip nothing more. SUPPLY_EXCLUDE_RE. |
| `supply_chain.identities` | array | no | `[]` | Signer identities `supply verify --identity NAME` resolves, as [[supply_chain.identities]] tables: name, identity_re (certificate identity regexp), issuer (OIDC issuer URL), match_re (optional regex on the target that selects this entry without --identity). Public values only; never a key. |
| `supply_chain.max_bytes` | integer | no | `65536` | Default output cap in bytes for the supply CLI (--max-bytes overrides). |
| `supply_chain.osv_offline_db` | string | no | `""` | Directory osv-scanner keeps its offline vulnerability databases under, for `supply audit --offline` (passed as OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY; osv-scanner 2.7.0 reads DIR/osv-scalibr/<Ecosystem>/all.zip); empty = osv-scanner's default, the user cache directory (~/.cache on Linux, ~/Library/Caches on macOS). SUPPLY_OSV_OFFLINE_DB. |
| `supply_chain.pin_actions` | boolean | no | `true` | Whether `supply pins` reports (and `supply pins --apply` rewrites) GitHub Actions referenced by tag instead of by commit. |
| `supply_chain.redact_extra_re` | string | no | `""` | Extra Python regex of token shapes every supply output redacts in addition to the built-in list; compiled on its own, so a leading global flag such as (?i) works. |
| `supply_chain.registries_re` | string | no | `""` | Python regex of allowed registry hosts (no scheme, no port) that `supply pins` and `supply audit` accept for dependencies and images; empty = no registry check. |
| `supply_chain.timeout` | integer | no | `120` | Seconds the supply CLI waits for one tool run (osv-scanner, an auditor, syft, cosign, gh) before exit 2 (--timeout overrides). SUPPLY_TIMEOUT. |
| `supply_chain.venv_markers` | string | no | `"VIRTUAL_ENV CONDA_PREFIX PIPENV_ACTIVE"` | Space-separated environment variable names that mean "inside a virtual environment" when set in the guard's own environment (the provider was started from an activated venv); pip install then passes. CONDA_PREFIX counts only when CONDA_DEFAULT_ENV names an env other than base (an auto-activated base is the machine's Python). Empty keeps the default. SUPPLY_VENV_MARKERS. |

### Secrets (never in harness.toml)

_none_

## Manual steps

<a id="install-supply-tools"></a>

### install-supply-tools — Install the pinned supply-chain scanners you want (osv-scanner, cosign, syft)

*once per machine · needs nothing but a terminal · ~3 min*

**Why:** The supply CLI runs osv-scanner for audit, cosign for verify and syft for sbom; they are optional, so bootstrap never downloads them unasked, and a missing one makes its verb report unavailable, never clean.

**How:**

Install the ones you use; each download is checked against the sha256 in `tools/<tool>.lock.json`
and lands in `~/.local/bin`:
```
harness install osv-scanner
harness install cosign
harness install syft
```
Air-gapped: fetch the asset named in the lock file on a connected machine (or ship it with
`harness pack --tools linux/amd64 --tools-optional`), then `harness install osv-scanner --from FILE`
(the sha256 check still applies). `HARNESS_TOOLS_MIRROR` redirects the download to a mirror.
Remove them with `harness uninstall --purge-tools`.

**Verify:** `command -v osv-scanner >/dev/null || command -v cosign >/dev/null || command -v syft >/dev/null` (exit 0)

<a id="configure-identities"></a>

### configure-identities — Name the signers `supply verify` trusts in local/harness.toml

*once per machine · needs nothing but a terminal · ~5 min*

**Why:** Keyless verification is only as strong as the identity it checks: without a configured signer, `supply verify` exits 2 and names this step instead of accepting any certificate.

**How:**

Add a `[supply_chain]` block to `local/harness.toml` (documentation values shown; public values
only, never a key):
```
[supply_chain]
registries_re = '^(ghcr\.io|registry\.example\.com)$'
# osv_offline_db = "/srv/osv-db"   # for `supply audit --offline`

[[supply_chain.identities]]
name = "release"
identity_re = '^https://github\.com/octocat/hello-world/\.github/workflows/release\.yml@refs/tags/v.*$'
issuer = "https://token.actions.githubusercontent.com"
match_re = '^ghcr\.io/octocat/'
```
Anchor every `identity_re` as `^…$`, name the workflow file and restrict the ref. Then run
`harness apply` and `supply verify IMAGE --identity release`.

**Verify:** `jq -e '(.supply_chain.identities // []) | length > 0' "$HARNESS_CONFIG_JSON" >/dev/null` (exit 0)

## Doctor checks

| id | severity | offline | fix |
|---|---|---|---|
| `supply-cli` | fail | runs | `harness apply` |
| `supply-detect` | warn | runs | `harness apply` |
| `supply-config` | warn | runs | [configure-identities](#configure-identities) |

## Guides and sensors

Guides steer the agent before it acts; sensors detect at or after the action. Pairing: **paired**; guides with a declared check: 8 of 8.

| side | kind | ref | note | pairs with |
|---|---|---|---|---|
| guide | rule | `rules/38-supply-chain.md` | pin what you add, install inside the project, never switch verification off, signing is a human release step | `guard.d/38-supply-chain.sh` |
| guide | skill | `skills/supply` | the supply CLI: detect, pins (with --apply), ci, audit, sbom, verify, redact; severities from the reference rubrics; the optional pinned osv-scanner, cosign and syft behind audit, verify and sbom | `skills/supply/scripts/tests/run.sh`, `doctor_checks` |
| guide | skill | `skills/pin-deps` | pin tags to commit shas and digests resolved read-only, supply pins --apply, supply pins again as the check; never guesses a value, never commits | `skills/supply/scripts/tests/run.sh`, `guard.d/38-supply-chain.sh`, `skill-description`, `yields` |
| guide | skill | `skills/audit-deps` | in-major upgrades with the ecosystem's lockfile tool, supply audit again as the check; majors, no-fix and unavailable ecosystems go to the human | `skills/supply/scripts/tests/run.sh`, `guard.d/38-supply-chain.sh`, `skill-description`, `yields` |
| guide | permission | `permissions.toml` | verification and audit tools allowed, cosign signing asks, verification-off config and cosign keys denied | `permissions-vs-guard`, `guard.d/38-supply-chain.sh` |
| guide | agent | `agents/supply-architect.md` | design-only supply-chain posture: pinning, update flow, SBOM, provenance and SLSA target, CI hardening, vulnerability SLAs | `guard.d/38-supply-chain.sh`, `agent-tools` |
| guide | agent | `agents/supply-auditor.md` | read-only posture review in the Critical / Warnings / Suggestions / Not verified contract, severities from the rubrics | `guard.d/38-supply-chain.sh`, `agent-tools` |
| guide | agent | `agents/supply-triage.md` | read-only investigation of one vulnerability, failed verification or suspicious dependency; stops after three unresolved hypotheses | `guard.d/38-supply-chain.sh`, `agent-tools` |
| sensor | guard | `guard.d/38-supply-chain.sh` | verification-off denies, global-install and unpinned-dependency asks, cosign signing and insecure-download asks | `rules/38-supply-chain.md`, `skills/pin-deps`, `skills/audit-deps`, `permissions.toml`, `agents/supply-architect.md`, `agents/supply-auditor.md`, `agents/supply-triage.md` |
| sensor | test | `guard.d/tests.sh` | guard rows incl. bypasses, ordering against later denies and the security yield | — |
| sensor | test | `tests/run.sh` | this bundle's rows against core + supply-chain only | — |
| sensor | test | `skills/supply/scripts/tests/run.sh` | the supply CLI against stub tools and fixture checkouts: goldens per verb, byte-exact --apply, redaction, stub-log invariants (verify only, no fix, no docker), a rubric row per rule id, two identical runs | `skills/supply`, `skills/pin-deps`, `skills/audit-deps` |
| sensor | doctor | `doctor_checks` | the supply CLI on PATH, an offline detect, every signer identity_re anchored as supply requires (warn, fix configure-identities); osv-scanner, cosign and syft missing or older than the verified version WARN through the generic per-binary check (fix harness install TOOL) | `skills/supply` |
| sensor | lint | `permissions-vs-guard` | each Bash allow/deny rule of permissions.toml run through the guard: no allowed command the guard denies or asks, no denied one it allows | `permissions.toml` |
| sensor | review-agent | `agents/supply-auditor.md` | evidence-cited supply-chain review of a checkout, independent of /pin-deps and /audit-deps | — |
| sensor | lint | `agent-tools` | read-only agents set no permissionMode, list no write tools and name the model policy | `agents/supply-architect.md`, `agents/supply-auditor.md`, `agents/supply-triage.md` |
| sensor | lint | `skill-description` | pin-deps and audit-deps: trigger phrase, NOT for scope, argument-hint | `skills/pin-deps`, `skills/audit-deps` |
| sensor | lint | `yields` | the skills' Step 0, the agents' baseline sentence and the rule's repository sentence | `skills/pin-deps`, `skills/audit-deps` |

**Not covered:** Pipe-to-shell (curl … | sh) as a command is core band 35 and lands in a later part of #51 (supply pins and supply ci already report it in files as SH001). Reachability of a vulnerability, major-upgrade safety and licence policy are judgement or organisation-specific and are not sensed. A venv activated outside the provider's process is invisible to the guard (it reads the hook's environment and the command text). Direct writes to configuration files (>> ~/.npmrc, ~/.gitconfig, pip.conf, .yarnrc.yml) and an empty quoted value (git config http.sslVerify '') are out of scope for the guard. The command lexer is a heuristic, not a shell parser. The CLI's own tool runs are not shell commands and are not guarded; the suite's stub log and dry-run log are the read-only proof. YAML is read with a line model: anchors, multi-document files, reusable workflows and extends are not checked. The real-tool argv is pinned by the stub suite and was checked once against osv-scanner 2.7.0, cosign 3.1.4 and syft 1.55.0 (audit online and --offline, sbom, verify-blob online and --offline); `supply verify IMAGE --offline` with cosign is refused (exit 3), since nothing keeps cosign 3.1.4 offline for an image; the JSON shapes of `cosign verify`/`verify-attestation` on an image and of `gh attestation verify` are checked against fixtures only. Whether a pinned lock is still the latest upstream release is not sensed; bumping a lock is a human PR. Whether a resolved pin or an in-major upgrade is the right one, and the agents' findings and designs, are judgement: /pin-deps and /audit-deps are checked by re-running supply pins and supply audit; their rules against running the checkout's tests, build or scripts and against a tool downloading a toolchain or interpreter are instruction only (the guard does not see an upgrade command's side effects). The agents' read-only stance is sensed by the guard for the shell commands it asks or denies on; against `supply pins --apply` and `supply sbom --out`, which the guard allows as supply subcommands, it is instruction only, with no sensor.

## Uninstall

Kept on uninstall: `~/.sigstore/**`, `~/.cache/osv-scalibr/**`, `~/.cache/osv-scanner/**`, `~/.cache/syft/**`, `~/Library/Caches/osv-scalibr/**`

Sigstore's trust root (~/.sigstore) and the scanners' caches (osv-scanner 2.7.0's offline databases under the user cache directory's osv-scalibr/, syft's cache) are the tools' own; uninstall removes the rendered rule, permissions and guard section, and `harness uninstall --purge-tools` the binaries `harness install` placed.
<!-- generated:end -->
