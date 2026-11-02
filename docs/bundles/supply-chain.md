# Bundle: supply-chain

The software supply chain for agents: pin what you add, install inside the project, never switch
verification off. The first bundle of the [security family](../reference/security.md) (domain
`security`, posture `local`). It lands in parts across #51: this part ships the rule, guard
section 38 and the permission list; the `supply` CLI (`detect`, `pins`, `ci`, `audit`, `sbom`,
`verify`), the `/pin-deps` and `/audit-deps` skills, the `supply-architect`, `supply-auditor` and
`supply-triage` agents and the pinned `osv-scanner`, `cosign` and `syft` follow.

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
  `.sigstore/` as a file operand. Each reason names the trust-root fix (`PIP_CERT`,
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
  section 38, the verification denies included; the credential denies of core section 20
  stay ([repository-level harnesses](../repo-level.md#what-owning-a-domain-lifts)).

Config: `supply_chain.allow_global_re`, `supply_chain.venv_markers` (both read by the guard),
and `supply_chain.registries_re`, `supply_chain.identities`, `supply_chain.redact_extra_re`,
`supply_chain.osv_offline_db`, `supply_chain.pin_actions`, `supply_chain.max_bytes` for the
`supply` CLI of a later part.

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

<!-- generated:begin source=bundles/supply-chain/bundle.toml -->
## Summary

Software supply chain: pin what you add, install inside the project, never switch verification off (guard 38; supply CLI, skills and agents follow)

Guard section 38 and its rule: switching TLS or signature verification off denies (pip
--trusted-host, uv --allow-insecure-host or an http:// index or registry, npm strict-ssl
false, git http.sslVerify=false and GIT_SSL_NO_VERIFY, GOINSECURE, -insecure and GOSUMDB=off,
cosign verify --insecure-*, reading cosign.key); installs into the machine ask (pip outside a
venv or conda base, --user, sudo, uv pip --system, npm|pnpm -g, yarn global add,
cargo install without --locked --version, go install @latest; pipx, uv tool install and
pinned installs pass), so do unpinned git and URL dependencies, GONOSUMDB,
cosign sign|attest and insecure downloads written to a file. supply_chain.allow_global_re
allow-lists global tools; venv detection reads the hook's environment and the command text.
The `supply` CLI (detect, pins, ci, audit, sbom, verify), the /pin-deps and /audit-deps
skills and the supply-architect, supply-auditor and supply-triage agents land in later parts.

- **Depends on:** `core`
- **Recommends:** `github`
- **Stability:** experimental
- **Domain / posture:** security / local

## Components

Stable ids derived from the path, with their [taxonomy](../reference/taxonomy.md) facets (domain shown only where it differs from the bundle's). All bundles: [catalog](../catalog.md).

**Rules**

- `supply-chain/rules/38-supply-chain` — control: guide · function: govern · yields: text

**Guard sections**

- `supply-chain/guard.d/38-supply-chain` — control: sensor · function: govern · decisions: deny 7 · ask 8 · yields: declaration

**Permission lists**

- `supply-chain/permissions` — control: guide · function: govern · decisions: deny 4 · ask 6 · allow 21 · yields: config

## Requirements

### Binaries

| binary | min version | install | optional | why |
|---|---|---|---|---|
| `git` | 2.30 |  | no | Pin resolution and history lookups (`git ls-remote`, `git log -S`) run read-only git. |
| `python3` | 3.9 |  | no | The supply CLI is stdlib python. |

### Configuration

| key | type | required | default | description |
|---|---|---|---|---|
| `supply_chain.allow_global_re` | string | no | `""` | POSIX ERE (the guard applies it with grep -E) that every spec of a global install must match for it to pass without a prompt: pip outside a venv or with --user, npm\|pnpm -g, yarn global add, cargo install. Matched against each word after the first install verb as typed (name and any version; options and redirections are skipped), so anchor it (^…$). Use [0-9] and [[:space:]], never \d or \s. Empty = every global install asks. SUPPLY_ALLOW_GLOBAL_RE. |
| `supply_chain.identities` | array | no | `[]` | Signer identities `supply verify --identity NAME` resolves, as [[supply_chain.identities]] tables: name, identity_re (certificate identity regexp), issuer (OIDC issuer URL), match_re (optional regex on the target that selects this entry without --identity). Public values only; never a key. |
| `supply_chain.max_bytes` | integer | no | `65536` | Default output cap in bytes for the supply CLI (--max-bytes overrides). |
| `supply_chain.osv_offline_db` | string | no | `""` | Directory of a local OSV vulnerability database that `supply audit --offline` passes to osv-scanner; empty = osv-scanner's own cache. |
| `supply_chain.pin_actions` | boolean | no | `true` | Whether `supply pins` reports (and `supply pins --apply` rewrites) GitHub Actions referenced by tag instead of by commit. |
| `supply_chain.redact_extra_re` | string | no | `""` | Extra Python regex of token shapes every supply output redacts in addition to the built-in list; compiled on its own, so a leading global flag such as (?i) works. |
| `supply_chain.registries_re` | string | no | `""` | Python regex of allowed registry hosts (no scheme, no port) that `supply pins` and `supply audit` accept for dependencies and images; empty = no registry check. |
| `supply_chain.venv_markers` | string | no | `"VIRTUAL_ENV CONDA_PREFIX PIPENV_ACTIVE"` | Space-separated environment variable names that mean "inside a virtual environment" when set in the guard's own environment (the provider was started from an activated venv); pip install then passes. CONDA_PREFIX counts only when CONDA_DEFAULT_ENV names an env other than base (an auto-activated base is the machine's Python). Empty keeps the default. SUPPLY_VENV_MARKERS. |

### Secrets (never in harness.toml)

_none_

## Manual steps

_none_

## Doctor checks

_none_

## Guides and sensors

Guides steer the agent before it acts; sensors detect at or after the action. Pairing: **paired**; guides with a declared check: 2 of 2.

| side | kind | ref | note | pairs with |
|---|---|---|---|---|
| guide | rule | `rules/38-supply-chain.md` | pin what you add, install inside the project, never switch verification off, signing is a human release step | `guard.d/38-supply-chain.sh` |
| guide | permission | `permissions.toml` | verification and audit tools allowed, cosign signing asks, verification-off config and cosign keys denied | `permissions-vs-guard`, `guard.d/38-supply-chain.sh` |
| sensor | guard | `guard.d/38-supply-chain.sh` | verification-off denies, global-install and unpinned-dependency asks, cosign signing and insecure-download asks | `rules/38-supply-chain.md`, `permissions.toml` |
| sensor | test | `guard.d/tests.sh` | guard rows incl. bypasses, ordering against later denies and the security yield | — |
| sensor | test | `tests/run.sh` | this bundle's rows against core + supply-chain only | — |
| sensor | lint | `permissions-vs-guard` | each Bash allow/deny rule of permissions.toml run through the guard: no allowed command the guard denies or asks, no denied one it allows | `permissions.toml` |

**Not covered:** Pipe-to-shell (curl … | sh) is core band 35 and lands in a later part of #51. Reachability of a vulnerability and licence policy are judgement or organisation-specific and are not sensed. A venv activated outside the provider's process is invisible to the guard (it reads the hook's environment and the command text). Direct writes to configuration files (>> ~/.npmrc, ~/.gitconfig, pip.conf, .yarnrc.yml) and an empty quoted value (git config http.sslVerify '') are out of scope for the guard. The command lexer is a heuristic, not a shell parser. The supply CLI, its doctor checks, the agents and the /pin-deps and /audit-deps workflow skills land in later parts of #51.

## Uninstall

Kept on uninstall: `~/.sigstore/**`, `~/.cache/osv-scanner/**`, `~/.cache/syft/**`

Sigstore's trust root and the scanners' caches are the tools' own; uninstall removes only the rendered rule, permissions and guard section.
<!-- generated:end -->
