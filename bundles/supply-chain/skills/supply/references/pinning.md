# Pinning rubric (`supply pins`)

Every rule `supply pins DIR` reports, with the severity the CLI assigns and the fix. Agents take
severities from this table; they never invent one. A finding with a `ref` names the exact token
to replace; `/pin-deps` resolves the pinned value read-only and applies it with
`supply pins --apply`.

Why pin: a tag, a branch, a version range or an unverified download is a pointer someone else
can move. A commit sha, an image digest, an exact version with a hash, or a checksum is a value
you reviewed. Pins make an upgrade a visible diff (Dependabot and Renovate keep them current).

| Rule | Severity | Matches | Fix |
|---|---|---|---|
| GHA001 | warn | a step's `uses: OWNER/REPO@TAG` (or a short sha); not reported when `supply_chain.pin_actions = false` | `uses: OWNER/REPO@<40-hex sha> # vX.Y.Z` |
| GHA002 | crit | `uses: OWNER/REPO@main` or any ref that is not a tag or a sha | pin the commit of a released tag |
| GHA003 | warn | `uses: docker://IMAGE` without `@sha256:` | `docker://IMAGE@sha256:<digest>`, the tag in a comment |
| CI006 | crit / warn | CI image (GitHub `container:`/`services:`, GitLab `image:`/`services:`): crit with no tag or `:latest`, warn with a tag and no digest | `IMAGE:TAG@sha256:<digest>` |
| CI008 | crit / warn | GitLab `include: project:` with no `ref:` (crit) or a `ref:` that is not a 40-hex sha (warn); `component: …@~latest` or a branch (warn) | `ref: <sha>`; a released component version `@1.2.3` |
| CI009 | warn | GitLab `include: remote:` (or a URL include) | vendor the file, or include it from a project pinned to a sha |
| DKR001 | warn | Dockerfile `FROM IMAGE:TAG` without a digest (`scratch`, earlier stage names and `$ARG` images are skipped) | `FROM IMAGE:TAG@sha256:<digest>` |
| DKR002 | crit | `FROM IMAGE` with no tag, or `:latest` | a released tag plus its digest |
| DKR003 | crit / warn | compose `services.*.image`: crit with no tag or `:latest`, warn with a tag and no digest | `image: IMAGE:TAG@sha256:<digest>` |
| PIP001 | warn | a `requirements*.txt` line not pinned with `==` (or `===`) | `name==X.Y.Z`, ideally generated with hashes |
| PIP002 | crit / warn | a VCS requirement (`git+URL`) with no ref or a branch (crit) or a tag (warn); a URL archive without `--hash` (warn); a pyproject git dependency without a rev | `git+URL@<sha>`, or a released version |
| PIP003 | info | pinned requirements without `--hash` (one finding per file) | `uv pip compile --generate-hashes` |
| PIP004 | info | `pyproject.toml` dependency ranges and no `uv.lock`, `poetry.lock`, `pdm.lock`, `Pipfile.lock` or hashed requirements file next to it | commit a lockfile |
| NPM001 | warn / info | `package.json` version ranges (`^`, `~`, `*`, `>=`, tags): warn with no lockfile in the package's directory or a parent, info with one (one finding per file) | commit the lockfile, install with `npm ci` |
| NPM002 | crit / warn | a git dependency (`github:O/R`, `O/R`, `git+…`) with no `#ref` or a branch (crit) or a tag/semver range (warn); a tarball URL (warn) | a registry version, or `github:O/R#<sha>` |
| GO001 | warn | `go.mod` with `require` entries and no `go.sum` beside it | `go mod tidy`, commit `go.sum` |
| GO002 | warn | `go install\|run\|get MODULE@latest\|@main\|@master\|@HEAD` in a script, Dockerfile `RUN` or CI script | `go install MODULE@vX.Y.Z` |
| GO003 | info | `replace … => ./path` or `../path` | a released version; keep local paths out of release builds |
| CGO001 | crit / warn | Cargo git dependency without `rev` (crit with a branch or nothing, warn with a tag) | `{ git = "URL", rev = "<sha>" }` |
| CGO002 | info | `cargo install X` without both `--version` and `--locked` (`--path` installs are skipped) | `cargo install X --version X.Y.Z --locked` |
| SH001 | crit | a download piped to an interpreter: `curl\|wget … \| [sudo] sh\|bash\|python\|node\|…`, `bash <(curl …)`, `sh -c "$(curl …)"`, `eval "$(curl …)"`, `source <(curl …)` | download to a file, check its sha256 or signature, read it, then run it |
| SH002 | warn | `curl -o\|-O\|--output\|>` or `wget` writing a file with no `sha256sum`, `shasum -a 256`, `sha256:`, `--checksum`, `cosign verify`, `gh attestation verify`, `.sig` or `.sigstore` within the next 8 lines; Dockerfile `ADD URL` without `--checksum` | verify the download before use |
| REG001 | warn | an image registry host, a pip `--index-url`/`--extra-index-url` host or an `.npmrc` `registry=` host outside `supply_chain.registries_re` (only when the key is set) | use an allowed registry, or extend the allow-list after review |
| SUP001 | warn | the scan stopped at 20 000 files (`.git`, `node_modules`, `vendor`, `.venv`, `venv`, `target`, `dist`, `build`, `__pycache__`, `.tox` and files over 2 MB are always skipped) | narrow DIR, or `supply_chain.exclude_re` |

What is not checked in this version: YAML anchors and multi-document files, reusable workflows
(`jobs.<id>.uses`), GitLab `extends:`/`!reference`, `ARG`-resolved base images, Maven, Gradle,
NuGet and Ruby manifests, Helm chart dependencies (the `k8s` bundle) and Terraform providers.
Anything the line model cannot read is skipped, never guessed into a `crit`.
