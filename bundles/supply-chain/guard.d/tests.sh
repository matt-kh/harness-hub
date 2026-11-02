# shellcheck shell=bash
# Guard test rows for bundle supply-chain. Sourced by bundles/core/guard/tests/run.sh after lib.sh
# (helpers: t EXPECTED 'cmd' | tc EXPECTED CWD 'cmd' | tr 'reason-re' 'cmd' | decl … + r EXPECTED 'cmd'
# | tn EXPECTED 'stderr-re' CWD 'cmd').
# The venv markers and the allow-list come from the hook's environment: they are unset here and
# again at the end (rows of other bundles share this shell); rows set them per call.
unset VIRTUAL_ENV CONDA_PREFIX CONDA_DEFAULT_ENV PIPENV_ACTIVE SUPPLY_ALLOW_GLOBAL_RE SUPPLY_VENV_MARKERS

# ---- pass: project installs, verification and audit tools ------------------------------
t pass  '.venv/bin/pip install requests'
t pass  '/home/u/dev/shop/.venv/bin/pip install -r requirements.txt'
t pass  '.venv/bin/python -m pip install requests'
t pass  'uv sync'
t pass  'uv lock --upgrade-package requests'
t pass  'uv pip install requests'
t pass  'uv add requests'
t pass  'poetry add requests'
t pass  'poetry run pip install requests'
t pass  'pipx install ruff'
t pass  'pipx run ruff check .'
t pass  'source .venv/bin/activate && pip install requests'
t pass  '. .venv/bin/activate; pip install -e .'
t pass  'VIRTUAL_ENV=/home/u/dev/shop/.venv pip install requests'                   # marker in the command text
t pass  'pip install --target ./vendor requests'
t pass  'pip install --dry-run requests'
t pass  'pip download requests'
t pass  'pip list --outdated'
t pass  'pip-audit -r requirements.txt'
VIRTUAL_ENV=/home/u/dev/shop/.venv t pass 'pip install requests'                     # provider started from the venv
VIRTUAL_ENV=/home/u/dev/shop/.venv t pass 'python3 -m pip install requests'
CONDA_PREFIX=/home/u/miniconda3/envs/shop CONDA_DEFAULT_ENV=shop t pass 'pip install numpy'
CONDA_PREFIX=/home/u/conda/envs/shop CONDA_DEFAULT_ENV=shop t pass 'pip install requests'
SUPPLY_VENV_MARKERS='MYVENV' MYVENV=1 t pass 'pip install requests'                  # a custom marker
VIRTUAL_ENV=/home/u/dev/shop/.venv t pass 'pip install --index-url https://pypi.example.com/simple requests'
VIRTUAL_ENV=/home/u/dev/shop/.venv t pass 'pip install "git+https://github.com/octocat/hello-world@0123456789abcdef0123456789abcdef01234567"'
VIRTUAL_ENV=/home/u/dev/shop/.venv t pass 'pip install git+https://github.com/octocat/hello-world@v1.2.3'   # a tag: a supply pins finding, not a guard ask
VIRTUAL_ENV=/home/u/dev/shop/.venv t pass 'pip install git+ssh://git@github.com/octocat/hello-world@0123abc'   # userinfo is not a ref
VIRTUAL_ENV=/home/u/dev/shop/.venv t pass 'pip install https://downloads.example.com/x-1.0-py3-none-any.whl --hash sha256:0123'
t pass  'npm ci'
t pass  'npm install'
t pass  'npm i -D typescript'
t pass  'npm install lodash@4.17.21 @octocat/hello-world'
t pass  'npm install github:octocat/hello-world#0123456789abcdef0123456789abcdef01234567'
t pass  'npm audit --json'
t pass  'npm ls -g'
t pass  'pnpm install --frozen-lockfile'
t pass  'yarn install --immutable'
t pass  'yarn add -D typescript'
t pass  'go mod download'
t pass  'go mod tidy'
t pass  'go mod verify'
t pass  'go get example.com/mod@v1.2.3'
t pass  'go install example.com/tool@v1.2.3'
t pass  'go install ./cmd/tool'
t pass  'go env GOPRIVATE'
t pass  'GOPRIVATE=example.com/* go mod download'
t pass  'go env -w GOPRIVATE=example.com/*'
t pass  'cargo build --locked'
t pass  'cargo fetch'
t pass  'cargo add serde'
t pass  'cargo audit'
t pass  'cargo update -p serde'
t pass  'cargo install --list'
t pass  'cargo add --git https://github.com/octocat/hello-world --rev 0123abc'
t pass  'cargo add --git https://github.com/octocat/hello-world --tag v1.2.3'
t pass  'brew install jq'
t pass  'supply pins .'
t pass  'supply verify ghcr.io/octocat/hello-world:1.0 --identity release'
t pass  'cosign verify --certificate-identity-regexp "^https://github.com/octocat/" --certificate-oidc-issuer https://token.actions.githubusercontent.com ghcr.io/octocat/hello-world:1.0'
t pass  'cosign verify-blob --bundle x.sigstore.json x.tar.gz'
t pass  'cosign verify-attestation --type slsaprovenance --key cosign.pub ghcr.io/octocat/hello-world:1.0'
t pass  'cosign verify --insecure-ignore-tlog=false --key cosign.pub ghcr.io/octocat/hello-world:1.0'
t pass  'cosign tree ghcr.io/octocat/hello-world:1.0'
t pass  'cosign download sbom ghcr.io/octocat/hello-world:1.0'
t pass  'cosign triangulate ghcr.io/octocat/hello-world:1.0'
t pass  'cosign initialize'
t pass  'cosign public-key --key cosign.key'                                          # cosign reads the key itself
t pass  'cat cosign.pub'
t pass  'gh attestation verify x.tar.gz -R octocat/hello-world'
t pass  'gh attestation download oci://ghcr.io/octocat/hello-world:1.0 -o octocat'
t pass  'osv-scanner scan source -r .'
t pass  'syft scan dir:. -o spdx-json -q'
t pass  'grype dir:.'
t pass  'govulncheck ./...'
t pass  'sha256sum -c SHA256SUMS'
t pass  'curl -k https://localhost:8443/healthz'                                      # a bare insecure GET, nothing written
t pass  'curl -sk https://localhost:8443/healthz > /dev/null'
t pass  'curl -fsSL https://downloads.example.com/t.tgz -o /tmp/t.tgz'                # verified TLS
t pass  'curl --cacert /etc/ssl/certs/ca.pem https://downloads.example.com/t.tgz -o /tmp/t.tgz'
t pass  'wget -qO- --no-check-certificate https://localhost:8443/healthz'            # to stdout
t pass  'git config --global http.sslCAInfo /etc/ssl/certs/ca.pem'
t pass  'git config http.sslVerify true'
t pass  'git config --unset http.sslVerify'
t pass  'unset GIT_SSL_NO_VERIFY'
t pass  'grep -rn GIT_SSL_NO_VERIFY= docs/'                                            # mentioned, not assigned
t pass  'echo "never set GOINSECURE=x"'
t pass  'git commit -m "docs: never pass --trusted-host to pip"'
t pass  'npm config set cafile /etc/ssl/certs/ca.pem'
t pass  'npm config set registry https://registry.example.com/'
t pass  'npm ci --registry=https://registry.example.com/'
t pass  'pip config set global.index-url https://pypi.example.com/simple'
t pass  'pip config list'
t pass  'GOSUMDB=sum.golang.org go mod download'
t pass  'go env GOSUMDB'
t pass  'uv sync --index-url https://pypi.example.com/simple'
t pass  'pip config set global.cert /etc/ssl/certs/ca.pem'
SUPPLY_ALLOW_GLOBAL_RE='^(ripgrep|typescript)$' t pass 'npm i -g typescript'
SUPPLY_ALLOW_GLOBAL_RE='^(ripgrep|typescript)$' t pass 'cargo install ripgrep'
SUPPLY_ALLOW_GLOBAL_RE='^(ruff|black)$' t pass 'pip install ruff black'
SUPPLY_ALLOW_GLOBAL_RE='^(ruff|black)$' t pass 'pip install --user ruff'
SUPPLY_ALLOW_GLOBAL_RE='^typescript$' t pass 'yarn global add typescript'

# ---- ask: installs into the machine ------------------------------------------------------
t ask   'pip install requests'
t ask   'pip3 install requests'
t ask   'pip3.11 install -r requirements.txt'
t ask   'python3 -m pip install requests'
t ask   'python -m pip install --upgrade pip'
t ask   '/usr/bin/pip3 install requests'                                              # bypass: path-qualified
t ask   './pip install requests'
t ask   'sh -c "pip install requests"'                                                # bypass: wrapped
t ask   "bash -lc 'pip install requests'"
t ask   'env X=1 pip install requests'
t ask   'cd /tmp && pip install requests'
t ask   'echo requests | xargs pip install'
t ask   'command pip install requests'
t ask   'pip install poetry'                                                          # a runner name as the spec is no marker
t ask   'uv sync; pip install requests'                                               # the marker is per clause
t ask   'pip --disable-pip-version-check install requests'
VIRTUAL_ENV=/home/u/dev/shop/.venv t ask 'sudo pip install requests'                  # sudo asks inside a venv too
VIRTUAL_ENV=/home/u/dev/shop/.venv t ask 'pip install --user requests'
VIRTUAL_ENV=/home/u/dev/shop/.venv t ask 'pip install --break-system-packages requests'
t ask   'sudo -H pip3 install requests'
t ask   'sudo python3 -m pip install requests'
SUPPLY_ALLOW_GLOBAL_RE='^(ruff|black)$' t ask 'pip install ruff requests'             # every spec must match
SUPPLY_ALLOW_GLOBAL_RE='^(ruff|black)$' t ask 'sudo pip install ruff'                 # sudo is never allow-listed
SUPPLY_ALLOW_GLOBAL_RE='^(ruff|black)$' t ask 'pip install -r requirements.txt'
SUPPLY_VENV_MARKERS='MYVENV' VIRTUAL_ENV=/home/u/dev/shop/.venv t ask 'pip install requests'   # the list replaces the default
CONDA_PREFIX=/home/u/conda CONDA_DEFAULT_ENV=base t ask 'pip install requests'      # conda base is the machine's Python
CONDA_PREFIX=/home/u/conda t ask 'pip install requests'                             # no env name: treated as base
CONDA_PREFIX=/home/u/conda CONDA_DEFAULT_ENV=base tr 'start the agent from the activated venv' 'pip install requests'
t ask   'uv pip install --system requests'
t ask   'uv pip install --break-system-packages requests'
t ask   'sh -c "uv pip install --system requests"'                                    # bypass: wrapped
t ask   'env X=1 uv pip install --system ruff'
t ask   '/home/u/.local/bin/uv pip install --system requests'                         # bypass: path-qualified
VIRTUAL_ENV=/home/u/dev/shop/.venv t ask 'uv pip install --system requests'          # a venv does not lift --system
tr 'sudo, --system or --break-system-packages' 'uv pip install --system requests'
t ask   'npm install -g typescript'
t ask   'npm i -g typescript'
t ask   'npm -g install typescript'
t ask   'npm install --global typescript'
t ask   'npm install --location=global typescript'
t ask   'pnpm add -g typescript'
t ask   'yarn global add typescript'
t ask   'sh -c "npm i -g typescript"'                                                 # bypass: wrapped
t ask   '/usr/local/bin/npm i -g typescript'
t ask   'cd /tmp && npm i -g typescript'
SUPPLY_ALLOW_GLOBAL_RE='^(ripgrep|typescript)$' t ask 'npm i -g typescript ts-node'
t ask   'cargo install ripgrep'
t ask   'cargo install --locked ripgrep'
t ask   'env RUSTFLAGS=-g cargo install ripgrep'
t ask   'go install example.com/tool@latest'
t ask   'go install example.com/tool@main'
t ask   'go install "example.com/tool@HEAD"'
t ask   'sh -c "go install example.com/tool@master"'
tr 'run it inside the project'   'pip install requests'
tr 'start the agent from the activated venv' 'pip install requests'
tr 'allow_global_re'             'npm i -g typescript'
tr 'allow_global_re'             'cargo install ripgrep'
tr 'allow_global_re'             'yarn global add typescript'
tr 'allow_global_re'             'pip install --user requests'
tr 'system Python'               'sudo pip install requests'
tr 'npm i -D'                    'npm i -g typescript'
tr 'cargo run or cargo build'    'cargo install ripgrep'
tr 'pin a version'               'go install example.com/tool@latest'
# ---- ask: unpinned git and URL dependencies (inside a venv too) ---------------------------
export VIRTUAL_ENV=/home/u/dev/shop/.venv
t ask   'pip install git+https://github.com/octocat/hello-world'
t ask   'pip install git+https://github.com/octocat/hello-world@main'
t ask   'pip install "hello @ git+https://github.com/octocat/hello-world@HEAD"'
t ask   'pip install git+ssh://git@github.com/octocat/hello-world'                    # userinfo, no ref
t ask   'pip install https://downloads.example.com/x-1.0-py3-none-any.whl'
t ask   'pip install https://downloads.example.com/x-1.0.tar.gz'
t ask   'sh -c "pip install git+https://github.com/octocat/hello-world@develop"'       # bypass: wrapped
unset VIRTUAL_ENV
t ask   'npm install github:octocat/hello-world'
t ask   'npm install octocat/hello-world'
t ask   'npm install octocat/hello-world#main'
t ask   'npm i -D git+https://github.com/octocat/hello-world.git'
t ask   'npm install git://github.com/octocat/hello-world.git'
t ask   'npm install https://downloads.example.com/hello-1.0.0.tgz'
t ask   'pnpm add github:octocat/hello-world'
t ask   'yarn add octocat/hello-world'
t ask   'cd web && npm install github:octocat/hello-world'
t ask   'cargo add --git https://github.com/octocat/hello-world'
t ask   'cargo add --git https://github.com/octocat/hello-world --branch main'
t ask   'cargo add --git https://github.com/octocat/hello-world --branch main --rev 0123abc'
tr 'supply pins'                 'npm install github:octocat/hello-world'
tr 'supply pins'                 'cargo add --git https://github.com/octocat/hello-world'
VIRTUAL_ENV=/home/u/dev/shop/.venv tr 'supply pins' 'pip install git+https://github.com/octocat/hello-world'
# ---- ask: checksum database skipped, signing, unverified downloads ------------------------
t ask   'GONOSUMDB=example.com/private go mod download'
t ask   'GONOSUMCHECK=1 go get example.com/mod@v1.2.3'
t ask   'env GONOSUMDB=example.com/private go build ./...'
t ask   'cd /tmp && GONOSUMDB=example.com go mod tidy'
t ask   'cosign sign --yes ghcr.io/octocat/hello-world@sha256:0123'
t ask   'cosign sign-blob --bundle x.sigstore.json x.tar.gz'
t ask   'cosign attest --predicate sbom.json ghcr.io/octocat/hello-world@sha256:0123'
t ask   'cosign attest-blob --predicate p.json x.tar.gz'
t ask   'cosign upload blob -f x.tar.gz ghcr.io/octocat/x'
t ask   'cosign copy ghcr.io/octocat/a ghcr.io/octocat/b'
t ask   'cosign generate-key-pair'
t ask   'cosign import-key-pair --key key.pem'
t ask   'sh -c "cosign sign ghcr.io/octocat/hello-world@sha256:0123"'                 # bypass: wrapped
t ask   '/usr/local/bin/cosign sign ghcr.io/octocat/hello-world@sha256:0123'
t ask   'cosign -d sign ghcr.io/octocat/hello-world@sha256:0123'
t ask   'curl -k https://downloads.example.com/t.tgz -o /tmp/t.tgz'
t ask   'curl --insecure -O https://downloads.example.com/t.tgz'
t ask   'curl -fsSLk https://downloads.example.com/t.tgz -o t.tgz'
t ask   'curl -kLo t.tgz https://downloads.example.com/t.tgz'
t ask   'curl -k https://downloads.example.com/t.tgz > t.tgz'
t ask   'curl -sk https://downloads.example.com/t.tgz 2>/dev/null >t.tgz'
t ask   'curl -k --output /tmp/t.tgz https://downloads.example.com/t.tgz'
t ask   'wget --no-check-certificate https://downloads.example.com/t.tgz'
t ask   'wget --no-check-certificate -O /tmp/t.tgz https://downloads.example.com/t.tgz'
t ask   'sh -c "curl -k https://downloads.example.com/t.tgz -o t.tgz"'                # bypass: wrapped
t ask   '/usr/bin/curl -k -o t.tgz https://downloads.example.com/t.tgz'
tr 'GOPRIVATE'                   'GONOSUMDB=example.com/private go mod download'
tr 'hand the command to the user' 'cosign sign ghcr.io/octocat/hello-world@sha256:0123'
tr 'use the HTTPS URL'           'curl -k https://downloads.example.com/t.tgz -o /tmp/t.tgz'
tr 'ca-certificate'              'wget --no-check-certificate https://downloads.example.com/t.tgz'

# ---- deny: verification switched off ------------------------------------------------------
t deny  'pip install --trusted-host pypi.example.com requests'
t deny  'pip install -i http://pypi.example.com/simple requests'
t deny  'pip install --index-url=http://pypi.example.com/simple requests'
t deny  'pip install --extra-index-url http://pypi.example.com/simple requests'
t deny  'uv pip install --index-url http://pypi.example.com/simple requests'
t deny  'PIP_TRUSTED_HOST=pypi.example.com pip install requests'
t deny  'PIP_INDEX_URL=http://pypi.example.com/simple pip install requests'
t deny  'export PIP_TRUSTED_HOST=pypi.example.com'
VIRTUAL_ENV=/home/u/dev/shop/.venv t deny 'pip install --trusted-host h requests'    # a venv lifts the install ask, never this
t deny  '.venv/bin/pip install --trusted-host pypi.example.com requests'
t deny  'pip config set global.trusted-host pypi.example.com'
t deny  'pip config --global set global.trusted-host pypi.example.com'
t deny  'pip3 config set install.trusted-host pypi.example.com'
t deny  'python3 -m pip config set global.index-url http://pypi.example.com/simple'
t deny  '/usr/bin/pip3 config --user set global.index-url http://pypi.example.com/simple'   # bypass: path-qualified
t deny  'sh -c "pip config set global.trusted-host pypi.example.com"'                       # bypass: wrapped
t deny  'uv pip install --allow-insecure-host pypi.example.com requests'
t deny  'uv sync --allow-insecure-host=pypi.example.com'
t deny  'uv lock --trusted-host pypi.example.com'
t deny  'UV_INSECURE_HOST=pypi.example.com uv sync'
t deny  'env X=1 UV_INSECURE_HOST=pypi.example.com uv lock'
t deny  'sh -c "uv add --allow-insecure-host pypi.example.com requests"'
t deny  '/home/u/.local/bin/uv sync --allow-insecure-host pypi.example.com'
t deny  'npm install --registry=http://registry.example.com/ lodash'
t deny  'npm ci --registry http://registry.example.com/'
t deny  'env X=1 yarn add lodash --registry http://registry.example.com/'
t deny  'sh -c "pnpm add lodash --registry=http://registry.example.com/"'
t deny  '/usr/local/bin/npm i --registry http://registry.example.com/ lodash'
t deny  'GOSUMDB=off go mod download'
t deny  'env GOSUMDB=off go get example.com/mod@v1.2.3'
t deny  'export GOSUMDB=off'
t deny  'sh -c "GOSUMDB=off go mod download"'
t deny  'go env -w GOSUMDB=off'
t deny  '/usr/local/go/bin/go env -w GOSUMDB=off'
t deny  'npm config set strict-ssl false'
t deny  'npm config set strict-ssl=false'
t deny  'yarn config set strict-ssl false'
t deny  'pnpm config set strict-ssl false'
t deny  'npm install --strict-ssl=false'
t deny  'NPM_CONFIG_STRICT_SSL=false npm ci'
t deny  'npm_config_strict_ssl=false npm ci'
t deny  'npm config set registry http://registry.example.com/'
t deny  'npm config set @octocat:registry http://registry.example.com/'
t deny  'git -c http.sslVerify=false fetch'
t deny  'git -c "http.sslVerify=false" clone https://git.example.com/octocat/hello-world.git'
t deny  'git -c http.https://git.example.com/.sslVerify=false fetch'
t deny  'git config http.sslVerify false'
t deny  'git config --global http.sslverify false'
t deny  'git config --global --bool http.sslVerify false'
t deny  'GIT_SSL_NO_VERIFY=1 git pull'
t deny  'env GIT_SSL_NO_VERIFY=1 git pull'
t deny  'export GIT_SSL_NO_VERIFY=true'
t deny  'cd /tmp && GIT_SSL_NO_VERIFY=1 git pull'
t deny  'sh -c "GIT_SSL_NO_VERIFY=1 git pull"'
t deny  "bash -lc 'git -c http.sslVerify=false fetch'"
t deny  '/usr/bin/git -c http.sslVerify=false fetch'
t deny  'echo x | xargs env GIT_SSL_NO_VERIFY=1 git pull'
t deny  'GOINSECURE=example.com go get example.com/mod'
t deny  'sh -c "GOINSECURE=example.com go mod download"'
t deny  'GOFLAGS=-insecure go get example.com/mod'
t deny  'go get -insecure example.com/mod'
t deny  'go env -w GOINSECURE=example.com'
t deny  'go env -w GONOSUMDB=example.com'
t deny  'go env -w GONOSUMCHECK=1'
t deny  'go env -w GOFLAGS=-insecure'
t deny  'cosign verify --insecure-ignore-tlog --key cosign.pub ghcr.io/octocat/hello-world:1.0'
t deny  'cosign verify --insecure-ignore-tlog=true --key cosign.pub ghcr.io/octocat/hello-world:1.0'
t deny  'cosign verify-blob --insecure-ignore-sct --bundle b.json x.tar.gz'
t deny  'cosign verify-attestation --allow-insecure-registry --key cosign.pub registry.example.com/x'
t deny  'cosign verify --allow-http-registry --key cosign.pub registry.example.com/x'
t deny  'cosign verify --insecure-skip-verify --key cosign.pub ghcr.io/octocat/hello-world:1.0'
t deny  'sh -c "cosign verify --insecure-ignore-tlog --key cosign.pub ghcr.io/octocat/x"'
t deny  'cat cosign.key'
t deny  'base64 keys/cosign.key'
t deny  'cp ~/.sigstore/keys/release.key /tmp/k'
t deny  'sh -c "head -c 64 cosign.key"'
tr 'PIP_CERT'                    'pip install --trusted-host pypi.example.com requests'
tr 'use the HTTPS index'         'pip install -i http://pypi.example.com/simple requests'
tr 'NODE_EXTRA_CA_CERTS'         'npm config set strict-ssl false'
tr 'http.sslCAInfo'              'git -c http.sslVerify=false fetch'
tr 'http.sslCAInfo'              'GIT_SSL_NO_VERIFY=1 git pull'
tr 'GOPRIVATE'                   'GOINSECURE=example.com go get example.com/mod'
tr 'without the flag'            'cosign verify --insecure-ignore-tlog --key cosign.pub ghcr.io/octocat/hello-world:1.0'
tr 'keyless'                     'cat cosign.key'
tr 'uv --allow-insecure-host'    'UV_INSECURE_HOST=pypi.example.com uv sync'
tr 'PIP_CERT'                    'pip config set global.trusted-host pypi.example.com'
tr 'NODE_EXTRA_CA_CERTS'         'npm install --registry=http://registry.example.com/ lodash'
tr 'GONOSUMDB=<module prefix>'   'GOSUMDB=off go mod download'

# ---- ordering: asks are deferred, so a later (or earlier) deny still wins -----------------
t deny  'npm i -g typescript && git push origin main'                                 # 30 denies first
if grep -q '^guard_section_github_41_github_closing()' "$H"; then                     # only when the github bundle is built in
  t deny 'pip install requests; git commit -m "Closes #1"'                            # 41 denies after 38 deferred
fi
t deny  'cargo install ripgrep; GIT_SSL_NO_VERIFY=1 git pull'                         # a deny later in 38 wins over its ask
t deny  'cat ~/.ssh/id_rsa; pip install requests'                                     # core 20 first

# ---- repository-level declaration: .harness.toml (principle 8) ---------------------------
decl '[owns]' 'domains = ["security"]'
r pass  'pip install requests'                                                        # the repository's harness decides
r pass  'cosign sign ghcr.io/octocat/hello-world@sha256:0123'
r pass  'git -c http.sslVerify=false fetch'                                           # documented: owning security lifts the denies
r pass  'cat cosign.key'                                                              # a repository artefact, not a developer credential
r deny  'cat ~/.ssh/id_rsa'                                                           # never yields: core 20
decl '[owns]' 'components = ["supply-chain/guard.d/38-supply-chain"]'
r pass  'npm i -g typescript'
r pass  'GOINSECURE=example.com go get example.com/mod'
decl '[owns]' 'domains = ["kubernetes", "scm"]'                                       # another domain: no yield
r ask   'pip install requests'
r deny  'git -c http.sslVerify=false fetch'
decl '[overrides]' 'SUPPLY_ALLOW_GLOBAL_RE = ".*"'                                    # bypass: not a repo override
r ask   'npm i -g typescript'
# shellcheck disable=SC2154  # rpd: the fixture repository, defined in guard/tests/lib.sh
tn ask  'SUPPLY_ALLOW_GLOBAL_RE is not a repo override' "$rpd" 'npm i -g typescript'
decl
# ---- SUPPLY_ALLOW_GLOBAL_RE from the rendered guard.env (the parser accepts SUPPLY_ keys) --
_sge=$(mktemp); printf '%s\n' "SUPPLY_ALLOW_GLOBAL_RE='^typescript\$'" "SUPPLY_VENV_MARKERS='MYVENV'" > "$_sge"
HARNESS_GUARD_ENV=$_sge t pass 'npm i -g typescript'
HARNESS_GUARD_ENV=$_sge t ask  'npm i -g ts-node'
HARNESS_GUARD_ENV=$_sge SUPPLY_ALLOW_GLOBAL_RE='' t ask 'npm i -g typescript'        # the environment wins (empty = off)
HARNESS_GUARD_ENV=$_sge MYVENV=1 t pass 'pip install requests'
HARNESS_GUARD_ENV=$_sge VIRTUAL_ENV=/home/u/dev/shop/.venv t ask 'pip install requests'   # guard.env replaced the marker list
t ask   'npm i -g typescript'                                                         # unset and no guard.env key: every global install asks
rm -f "$_sge"
unset VIRTUAL_ENV CONDA_PREFIX CONDA_DEFAULT_ENV PIPENV_ACTIVE SUPPLY_ALLOW_GLOBAL_RE SUPPLY_VENV_MARKERS
