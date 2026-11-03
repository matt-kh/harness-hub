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
| GHA001 | warn | a step's `uses: OWNER/REPO@REF` where REF is a tag, a short sha or another name that may be a tag or a branch (`release-2024`); not reported when `supply_chain.pin_actions = false` | `uses: OWNER/REPO@<40-hex sha> # vX.Y.Z` |
| GHA002 | crit | `uses: OWNER/REPO@REF` where REF is certainly a branch: `main`, `master`, `develop`, `dev`, `trunk`, `head`, `latest`, `stable`, `next`, `nightly`, `edge`, or any ref containing `/` | pin the commit of a released tag |
| GHA003 | warn | `uses: docker://IMAGE` without `@sha256:` | `docker://IMAGE@sha256:<digest>`, the tag in a comment |
| CI006 | crit / warn | CI image (GitHub `container:`/`services:`, GitLab `image:`/`services:`): crit with no tag or `:latest`, warn with a tag and no digest | `IMAGE:TAG@sha256:<digest>` |
| CI008 | crit / warn | GitLab `include: project:` with no `ref:` or a branch `ref:` (one of the GHA002 branch names, or containing `/`) — crit; any other `ref:` that is not a 40-hex sha, such as a tag (warn); `component: …@~latest` or a non-version ref (warn; a branch name crit) | `ref: <sha>`; a released component version `@1.2.3` |
| CI009 | warn | GitLab `include: remote:` (or a URL include) | vendor the file, or include it from a project pinned to a sha |
| DKR001 | warn | Dockerfile `FROM IMAGE:TAG` without a digest (`scratch`, earlier stage names and `$ARG` images are skipped) | `FROM IMAGE:TAG@sha256:<digest>` |
| DKR002 | crit | `FROM IMAGE` with no tag, or `:latest` | a released tag plus its digest |
| DKR003 | crit / warn | compose `services.*.image`: crit with no tag or `:latest`, warn with a tag and no digest; a service with `build:` is skipped (the image is the local build's name) unless `pull_policy` is `always` or `missing` | `image: IMAGE:TAG@sha256:<digest>` |
| PIP001 | warn | a `requirements*.txt` line not pinned with `==` (or `===`) | `name==X.Y.Z`, ideally generated with hashes |
| PIP002 | crit / warn | a VCS requirement (`git+URL`) with no ref or a branch (crit) or a tag (warn; the ref is what follows the last `@` of the path, so `@refs/tags/v1.0` is a tag and `ssh://git@host/` is not a ref); a URL archive without `--hash` (warn); a pyproject git dependency without a rev | `git+URL@<sha>`, or a released version |
| PIP003 | info | pinned requirements without `--hash` (one finding per file) | `uv pip compile --generate-hashes` |
| PIP004 | info | `pyproject.toml` dependency ranges and no `uv.lock`, `poetry.lock`, `pdm.lock`, `Pipfile.lock` or hashed requirements file next to it | commit a lockfile |
| NPM001 | warn / info | `package.json` version ranges (`^`, `~`, `*`, `>=`, tags, and `npm:` aliases such as `npm:@scope/pkg@^1`): warn with no lockfile in the package's directory or a parent, info with one (one finding per file) | commit the lockfile, install with `npm ci` |
| NPM002 | crit / warn | a git dependency (`github:O/R`, `O/R`, `git+…`) with no `#ref` or a branch (crit; warn when a lockfile beside or above it pins the resolved commit) or a tag/semver range (warn); a tarball URL (warn) | a registry version, or `github:O/R#<sha>` |
| GO001 | warn | `go.mod` with `require` entries and no `go.sum` beside it | `go mod tidy`, commit `go.sum` |
| GO002 | warn | `go install\|run\|get MODULE@latest\|@main\|@master\|@HEAD` in a script, Dockerfile `RUN` or CI script | `go install MODULE@vX.Y.Z` |
| GO003 | info | `replace … => ./path` or `../path` | a released version; keep local paths out of release builds |
| CGO001 | crit / warn | Cargo git dependency without `rev`: crit with a branch or nothing, warn with a tag or when a `Cargo.lock` beside or above the manifest pins the resolved commit | `{ git = "URL", rev = "<sha>" }` |
| CGO002 | info | `cargo install X` without both `--version` and `--locked` (`--path` installs are skipped) | `cargo install X --version X.Y.Z --locked` |
| SH001 | crit | a download piped to an interpreter that reads its program from stdin: `curl\|wget … \| [sudo] sh\|bash\|python\|node\|…` with no `-c`/`-m`/`-e`/`-p` and no script file (`sh -s`, `bash -`, `python3 -` count), `bash <(curl …)`, `sh -c "$(curl …)"`, `eval "$(curl …)"`, `source <(curl …)`. The line is lexed: a pipe inside a quoted string (an `echo` of install instructions), `\| python -c …`, `\| python -m json.tool` and `\| python FILE` are not findings | download to a file, check its sha256 or signature, read it, then run it |
| SH002 | warn | `curl` (with `-o`, `-O`, `--output` or `>`) or `wget` as a command word — not inside a quoted string or a `case` pattern — writing a file with no `sha256sum`, `shasum -a 256`, `sha256:`, `--checksum`, `cosign verify`, `gh attestation verify`, `.sig` or `.sigstore` within the next 8 lines; Dockerfile `ADD URL` without `--checksum` | verify the download before use |
| REG001 | warn | an image registry host, a pip `--index-url`/`--extra-index-url` host or an `.npmrc` `registry=` host outside `supply_chain.registries_re` (only when the key is set) | use an allowed registry, or extend the allow-list after review |
| SUP001 | warn | the scan stopped at 20 000 files (`.git`, `node_modules`, `vendor`, `.venv`, `venv`, `target`, `dist`, `build`, `__pycache__`, `.tox`, files over 2 MB and symlinks whose target leaves DIR are always skipped) | narrow DIR, or `supply_chain.exclude_re` |
| SUP002 | warn | a directory the walk could not list, or a scanned file it could not read: nothing in it was checked, so the result is **not clean** | make it readable and rerun, or exclude it with `supply_chain.exclude_re` |

What is not checked in this version: YAML anchors and multi-document files, reusable workflows
(`jobs.<id>.uses`), GitLab `extends:`/`!reference`, `ARG`-resolved base images, Maven, Gradle,
NuGet and Ruby manifests, Helm chart dependencies (the `k8s` bundle) and Terraform providers.
Anything the line model cannot read is skipped, never guessed into a `crit`.

## `supply pins DIR --apply FILE`

FILE is `[{"file", "line", "old", "new"}]` with paths relative to DIR. An entry is applied only
when all of these hold, else **nothing** is written and the exit is 2 with one reason per entry:

- `file` is a regular file `supply pins` scans (never `.git`, never through a symlink — neither
  the file nor any parent directory may be one) and resolves inside DIR; no `..`, no NUL;
- `old` is the `ref` of a current finding on that `line` (re-scanned first), and occurs on the
  line exactly once as a whole token (no `[A-Za-z0-9_.:@/-]` right before or after it);
- `new` pins `old` without renaming it: an image keeps its repository and gains
  `@sha256:<64 hex>` (`GHA003`, `CI006`, `DKR*`); an action, a pip VCS URL or an npm git
  dependency keeps its name and gets a 40-hex commit sha (`OWNER/REPO@<sha>`,
  `git+URL@<sha>[#egg=…]`, `github:O/R#<sha>`); a GitLab project include gets a 40-hex `ref`,
  a component `@<sha>` or `@X.Y.Z`; `go install M@latest` gets `M@vX.Y.Z` or `M@<sha>`. Other
  rules (`CGO001`, URL archives, tarballs) are edited by hand.

Writes are all-or-nothing: every file is checked writable and staged beside itself, re-read
just before its rename (a file changed meanwhile aborts), and a failure part-way restores the
files already replaced. Mode, line endings and the rest of each line are kept byte for byte.
