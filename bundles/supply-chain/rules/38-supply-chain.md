## Software supply chain
- **Pin everything you add**: dependencies by exact version in a lockfile, GitHub Actions by
  commit, images by digest, downloads with a checksum. `supply pins` lists every unpinned
  reference; `/pin-deps` pins them as a diff for review.
- **Install inside the project, or as an isolated or pinned tool; never into the machine.**
  `uv sync`, `uv pip install`, `.venv/bin/pip install`, `npm ci`, `npm i -D`, `npx`,
  `cargo run`, and the tool installs `pipx install`, `uv tool install`, `go install m@v1.2.3`
  and `cargo install X --locked --version V` pass. `pip install` outside a venv (conda `base`
  counts as outside), `--user`, `--break-system-packages`, `uv pip install --system`, `sudo`,
  `npm|pnpm -g`, `yarn global add`, `cargo install` without `--locked --version` and
  `go install …@latest` **ask**; tools you install globally on purpose go in
  `supply_chain.allow_global_re`. The guard sees a venv only when the agent was started from
  it, an earlier `source …/bin/activate` clause activated it, or the command word is the
  venv's own `…/bin/pip`.
- **Never switch verification off.** `pip --trusted-host` or an `http://` index (flag,
  `pip config` or variable), `uv --allow-insecure-host`, npm/yarn `strict-ssl false` or an
  `http://` registry, `NODE_TLS_REJECT_UNAUTHORIZED=0`, `git -c http.sslVerify=false`,
  `GIT_SSL_NO_VERIFY`, `GOINSECURE`, `-insecure`, `GOSUMDB=off`, `go env -w GONOSUMDB` and
  `cosign verify --insecure-*` are **denied**, however they are spelled or wrapped. Fix the
  trust root instead: `PIP_CERT` / `REQUESTS_CA_BUNDLE`, `cafile` / `NODE_EXTRA_CA_CERTS`,
  `http.sslCAInfo`, `GOPRIVATE`, `curl --cacert`. A one-shot `GONOSUMDB=` and `curl -k` or
  `wget --no-check-certificate` writing a file (or piping into `tar`) **ask**.
- **Unpinned git and URL dependencies ask** (`pip install git+URL` without `@<sha>`, npm
  `github:` or `owner/repo` without `#<full sha>`, any npm tarball URL, `cargo --git` with
  `--branch` or with neither `--rev` nor `--tag`). A tag passes the guard but is still a
  `supply pins` finding.
- **Verify before you trust**: `supply verify` or `cosign verify` / `gh attestation verify`.
  A failed verification (exit 2) is a finding to report, never a reason for an `--insecure-*`
  flag. Signing (`cosign sign|attest|attach`, key generation) is a human release step: hand the
  command to the user; never read `cosign.key` or a key under `~/.sigstore/` (pass `--key` and
  let cosign read it).
- **CI workflows are code**: check them with `supply ci FILE…` (permissions,
  `pull_request_target`, script injection, unpinned actions) before proposing a change.
- **Vulnerabilities**: `supply audit`; `/audit-deps` applies patch and minor upgrades with the
  ecosystem's own tool and never crosses a major. Whether a finding is reachable is judgement:
  say so, never guess.
- Agents `supply-architect` (design), `supply-auditor` (review) and `supply-triage` (one
  finding) never edit, install or sign; they hand remediations to the human.

A repository's own instructions for the same action replace this block.
