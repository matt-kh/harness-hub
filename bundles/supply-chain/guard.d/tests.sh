# shellcheck shell=bash
# Guard test rows for bundle supply-chain. Sourced by bundles/core/guard/tests/run.sh after lib.sh
# (helpers: t EXPECTED 'cmd' | tc EXPECTED CWD 'cmd' | tr 'reason-re' 'cmd' | decl … + r EXPECTED 'cmd'
# | tn EXPECTED 'stderr-re' CWD 'cmd').
# The venv markers and the allow-list come from the hook's environment: they are unset here and
# again at the end (rows of other bundles share this shell); rows set them per call.
unset VIRTUAL_ENV CONDA_PREFIX CONDA_DEFAULT_ENV CONDA_EXE MAMBA_ROOT_PREFIX PIPENV_ACTIVE SUPPLY_ALLOW_GLOBAL_RE SUPPLY_VENV_MARKERS

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

# ---- review fixes: compound and multi-line commands (C1) ----------------------------------
t deny  $'cd /tmp\nGIT_SSL_NO_VERIFY=1 git clone https://git.example.com/x.git'
t deny  $'cd /tmp\nexport GIT_SSL_NO_VERIFY=1\ngit clone https://git.example.com/x.git'
t deny  'if true; then GIT_SSL_NO_VERIFY=1 git clone x; fi'
t deny  '{ GIT_SSL_NO_VERIFY=1 git clone x; }'
t deny  '( GIT_SSL_NO_VERIFY=1 git clone x )'
t deny  'for r in a; do GIT_SSL_NO_VERIFY=1 git clone x; done'
t deny  '! GIT_SSL_NO_VERIFY=1 git clone x'
t deny  'nice GIT_SSL_NO_VERIFY=1 git clone x'
t deny  'nice -n 5 env GIT_SSL_NO_VERIFY=1 git clone x'
t deny  'timeout 5 env GIT_SSL_NO_VERIFY=1 git clone x'
t deny  'exec env GIT_SSL_NO_VERIFY=1 git clone x'
t deny  'eval GIT_SSL_NO_VERIFY=1 git clone x'
t deny  'stdbuf -oL env GIT_SSL_NO_VERIFY=1 git clone x'
t deny  'setsid env GIT_SSL_NO_VERIFY=1 git clone x'
t deny  'doas env GIT_SSL_NO_VERIFY=1 git clone x'
t deny  'declare -x GIT_SSL_NO_VERIFY=1'
t deny  'typeset -x GIT_SSL_NO_VERIFY=1'
t deny  'readonly GIT_SSL_NO_VERIFY=1'
t deny  'f() { local GIT_SSL_NO_VERIFY=1; git clone x; }; f'
t deny  'A="x y" GIT_SSL_NO_VERIFY=1 git clone x'                                     # a quoted earlier assignment
t deny  'echo $(GIT_SSL_NO_VERIFY=1 git ls-remote x)'
t deny  'echo `GOINSECURE=example.com go get example.com/mod`'
t deny  $'sh -c "cd /tmp\nGIT_SSL_NO_VERIFY=1 git pull"'
t ask   $'cd /tmp\npip install requests'
t ask   '( cd /tmp && pip install requests )'
# ---- review fixes: quoted or escaped command words and flags (C2) -------------------------
t deny  "'pip' install --trusted-host h requests"
t deny  '"npm" config set strict-ssl false'
t deny  'g\it -c http.sslVerify=false clone x'
t deny  'c\osign verify --insecure-ignore-tlog --key cosign.pub ghcr.io/octocat/x'
t deny  "pip install '--trusted-host' h requests"
t deny  'pip install --trusted-host"=h" requests'
t deny  'pip install --trus\ted-host h requests'
t ask   "'cosign' sign ghcr.io/octocat/x@sha256:0123"
t ask   'cargo "install" ripgrep'
t ask   'p\ip install requests'
# ---- review fixes: alternative spellings (C3) ---------------------------------------------
t deny  'pip install --trusted h requests'
t deny  'pip install --trusted=h requests'
t deny  'pip install --index http://pypi.example.com/simple requests'
t deny  'pip install --extra-index http://pypi.example.com/simple requests'
t deny  'pip install -ihttp://pypi.example.com/simple requests'
t deny  'npm install --no-strict-ssl'
t deny  'npm set strict-ssl false'
t deny  'npm install --reg http://registry.example.com/ lodash'
t deny  'git clone --config http.sslVerify=false https://git.example.com/x.git'
t deny  'git clone --config=http.sslVerify=false https://git.example.com/x.git'
t deny  'git -c http.sslVerify= fetch'
t deny  'git -c http.sslverify=OFF fetch'
t deny  'git -c http.https://git.example.com/.sslVerify=no fetch'
t deny  'GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=http.sslVerify GIT_CONFIG_VALUE_0=false git fetch'
t deny  'git --config-env=http.sslVerify=NOVERIFY fetch'
t ask   'npm i -gD typescript'
t ask   'npm i -dg typescript'
t pass  'git -c http.sslVerify fetch'                                                  # no value = true
t pass  'git -c http.sslVerify=true fetch'
t pass  'npm install --strict-peer-deps'
# ---- review fixes: allow-list specs from the first verb, redirections dropped (C4) --------
SUPPLY_ALLOW_GLOBAL_RE='^(black|ruff|typescript)$' t ask  'pip install evil install black'
SUPPLY_ALLOW_GLOBAL_RE='^(black|ruff|typescript)$' t ask  'npm i -g evil i typescript'
SUPPLY_ALLOW_GLOBAL_RE='^(black|ruff|typescript)$' t ask  'npm i -g evil add typescript'
SUPPLY_ALLOW_GLOBAL_RE='^(black|ruff|typescript)$' t ask  'yarn global add evil add typescript'
SUPPLY_ALLOW_GLOBAL_RE='^(black|ruff|typescript)$' t ask  'cargo install evil install black'
SUPPLY_ALLOW_GLOBAL_RE='^(black|ruff|typescript)$' t pass 'pip install black 2>&1'
SUPPLY_ALLOW_GLOBAL_RE='^(black|ruff|typescript)$' t pass 'pip install black > /tmp/pip.log'
SUPPLY_ALLOW_GLOBAL_RE='^(black|ruff|typescript)$' t pass 'npm i -g typescript 2>/dev/null'
# ---- review fixes: text that only mentions a command (W1) ---------------------------------
t pass  'echo "run: pip install --trusted-host h x"'
t pass  'printf "%s\n" "GIT_SSL_NO_VERIFY=1 git clone x"'
t pass  'grep -rn "npm config set strict-ssl false" docs/'
t pass  'rg -n "cosign sign" docs/'
t pass  'sed -n "/GOINSECURE=/p" docs/notes.md'
t pass  'git log -S "GIT_SSL_NO_VERIFY=1" --oneline'
t pass  'git commit -m "docs: never run pip install --trusted-host; GIT_SSL_NO_VERIFY=1 is denied"'
t pass  $'git commit -m "docs: guard notes\n\nGIT_SSL_NO_VERIFY=1 git clone is denied"'
t pass  'man pip'
t pass  'help export'
t pass  'pip install --help'
t pass  'pip help install'
t pass  'npm help install'
t pass  'cargo install -h'
t pass  'grep -rn "cosign.key" docs/'
t pass  'rg -l cosign.key .'
t pass  $'cat > notes.md <<EOF\nGIT_SSL_NO_VERIFY=1 git clone x\npip install --trusted-host h x\nEOF'
t pass  $'cat <<"EOF"\nnpm i -g typescript\nEOF'
t deny  $'cat <<EOF\nnotes\nEOF\nGIT_SSL_NO_VERIFY=1 git clone x'                     # after the heredoc body
t deny  $'bash <<EOF\nGIT_SSL_NO_VERIFY=1 git clone x\nEOF'                            # a shell reads the heredoc
t deny  'echo "GIT_SSL_NO_VERIFY=1 git clone x" | sh'                                  # pipe into a shell: no exemption ...
t deny  'eval "$(echo GIT_SSL_NO_VERIFY=1) git clone x"'
t deny  'cat cosign.key'
t deny  'grep -e x keys/cosign.key'                                                    # a file operand of grep
t deny  'rg pattern ~/.sigstore/keys/release.key'
t deny  'cat < cosign.key'
t deny  'sudo cat cosign.key'
t ask   'echo requests | xargs pip install'                                            # xargs runs pip: not a text tool
tr 'keyless'                     'grep -e x keys/cosign.key'
tr 'no repository declaration lifts this.*pass --key and let cosign read the key itself' 'cat /home/u/.sigstore/keys/release.key'
# ---- review fixes: curl/wget output (W2) --------------------------------------------------
t pass  'curl -k https://localhost:8443/healthz -o /dev/null'
t pass  'curl -k https://localhost:8443/healthz -o -'
t pass  'curl -k https://localhost:8443/healthz -o-'
t pass  'curl -k https://localhost:8443/healthz --output /dev/null'
t pass  'curl -k https://localhost:8443/healthz > /dev/null 2>&1'
t pass  'curl -sk -w "%{http_code}" -o /dev/null https://localhost:8443/healthz'
t pass  'wget --no-check-certificate -O /dev/null https://localhost:8443/healthz'
t pass  'curl -k https://localhost:8443/healthz | jq .'
t ask   'curl -k https://downloads.example.com/t.tgz | tar xz'
t ask   'curl -sk https://downloads.example.com/t.tgz | sudo tar -xzf - -C /opt'
t ask   'curl -k https://downloads.example.com/t.txt | tee t.txt'
t ask   'wget --no-check-certificate -qO- https://downloads.example.com/t.tgz | tar xz'
t ask   'curl -k https://downloads.example.com/t.tgz &> t.tgz'
tr 'use the HTTPS URL'           'curl -k https://downloads.example.com/t.tgz | tar xz'
# ---- review fixes: venv markers (W4) ------------------------------------------------------
t ask   'VIRTUAL_ENV=/home/u/dev/shop/.venv pip install requests'                     # an assignment is no venv
t ask   'pip install --target venv/bin/ requests --prefix /usr'                        # text after the command word is no marker
t ask   'pip install --target /usr/lib/python3/dist-packages requests'
t ask   'pip install --prefix ~/.local requests'
t ask   'pip install --target ../../outside requests'
t pass  'pip install --target ./vendor requests'
t pass  'pip install --prefix=build/prefix requests'
tc pass /home/u/dev/shop 'pip install --target /home/u/dev/shop/vendor requests'      # inside the cwd
t ask   'pip install requests; source .venv/bin/activate'                              # activate counts only for later clauses
t ask   'source .venv/bin/activate && deactivate && pip install requests'              # deactivate cancels it
t ask   'echo .venv/bin/pip; pip install requests'
t ask   'pip install requests .venv/bin/pip'
t pass  '$VIRTUAL_ENV/bin/pip install requests'
t pass  '/home/u/dev/shop/.venv/bin/python3 -m pip install requests'
t ask   '/usr/local/bin/pip3 install requests'
# shellcheck disable=SC2088  # the tilde is part of the command under test
t ask   '~/.local/bin/pip install requests'
# ---- review fixes: conda base (W5) --------------------------------------------------------
CONDA_PREFIX=/home/u/conda CONDA_DEFAULT_ENV=root t ask 'pip install requests'
CONDA_PREFIX=/home/u/conda CONDA_DEFAULT_ENV=/home/u/conda t ask 'pip install requests'   # base activated by path
CONDA_PREFIX=/home/u/conda CONDA_DEFAULT_ENV=tools CONDA_EXE=/home/u/conda/bin/conda t ask 'pip install requests'
CONDA_PREFIX=/home/u/mamba CONDA_DEFAULT_ENV=tools MAMBA_ROOT_PREFIX=/home/u/mamba t ask 'pip install requests'
CONDA_PREFIX=/home/u/conda/envs/shop CONDA_DEFAULT_ENV=shop CONDA_EXE=/home/u/conda/bin/conda t pass 'pip install requests'
# ---- review fixes: verification gaps (W6) -------------------------------------------------
t deny  'NODE_TLS_REJECT_UNAUTHORIZED=0 npm ci'
t deny  'env X=1 NODE_TLS_REJECT_UNAUTHORIZED=0 node build.js'
t deny  'export NODE_TLS_REJECT_UNAUTHORIZED=0'
t pass  'NODE_TLS_REJECT_UNAUTHORIZED=1 npm ci'
tr 'NODE_EXTRA_CA_CERTS'         'NODE_TLS_REJECT_UNAUTHORIZED=0 npm ci'
t deny  'cosign verify --insecure-ignore-tlog=True --key cosign.pub ghcr.io/octocat/x'
t deny  'cosign verify --insecure-ignore-tlog=t --key cosign.pub ghcr.io/octocat/x'
t deny  'cosign verify --private-infrastructure --key cosign.pub ghcr.io/octocat/x'
t deny  '/usr/local/bin/cosign verify-blob --private-infrastructure=true --bundle b.json x'
t pass  'cosign verify --private-infrastructure=false --key cosign.pub ghcr.io/octocat/x'
t ask   'cosign attach signature --signature sig ghcr.io/octocat/x'
t ask   'cosign attach sbom --sbom sbom.json ghcr.io/octocat/x'
t ask   'sh -c "cosign attach attestation --attestation a.json ghcr.io/octocat/x"'
t ask   'cosign clean ghcr.io/octocat/x'
t deny  'pip config set install.index-url http://pypi.example.com/simple'
t deny  'pip config set download.trusted-host pypi.example.com'
t deny  'pip config --user set global.extra-index-url http://pypi.example.com/simple'
t deny  'yarn config set enableStrictSsl false'
t deny  'yarn config set npmRegistryServer http://registry.example.com'
t deny  'yarn config set unsafeHttpWhitelist registry.example.com'
t deny  'YARN_ENABLE_STRICT_SSL=false yarn install'
t deny  'sh -c "yarn config set enableStrictSsl false"'
t deny  'uv pip install --index http://pypi.example.com/simple requests'
t deny  'uv sync --default-index http://pypi.example.com/simple'
t deny  'uv add --index internal=http://pypi.example.com/simple requests'
t deny  'uv lock --index-url http://pypi.example.com/simple'
t deny  'uv pip install --extra-index-url http://pypi.example.com/simple requests'
t deny  'UV_INDEX_URL=http://pypi.example.com/simple uv sync'
t deny  'UV_DEFAULT_INDEX=http://pypi.example.com/simple uv sync'
t deny  'env UV_INDEX=internal=http://pypi.example.com/simple uv lock'
t deny  'UV_EXTRA_INDEX_URL=http://pypi.example.com/simple uv sync'
t pass  'uv sync --default-index https://pypi.example.com/simple'
t ask   'UV_SYSTEM_PYTHON=1 uv pip install requests'
t ask   'env UV_SYSTEM_PYTHON=true uv pip install requests'
VIRTUAL_ENV=/home/u/dev/shop/.venv t ask 'UV_SYSTEM_PYTHON=1 uv pip install requests'
# ---- review fixes: isolated or pinned tool installs pass (S1), empty values (S2) ----------
t pass  'uv tool install ruff'
t pass  'pipx install ruff==0.6.9'
t pass  'cargo install ripgrep --locked --version 14.1.0'
t pass  'cargo install --locked --version=14.1.0 ripgrep'
t pass  'cargo install --vers 14.1.0 --locked ripgrep'
t ask   'cargo install ripgrep --version 14.1.0'                                       # without --locked
t ask   'cargo install ripgrep --locked'                                               # without --version
tr 'pass --locked --version V'   'cargo install ripgrep --locked'
t pass  'GOINSECURE= go build ./...'
t pass  'go env -w GOINSECURE='
t pass  'GONOSUMDB= go mod download'
t pass  'go env -w GONOSUMDB='
# ---- review fixes: tarball URLs are never pinned by a fragment (S6) -----------------------
t ask   'npm install https://downloads.example.com/hello-1.0.0.tgz#0123456789abcdef0123456789abcdef01234567'
t ask   'npm install github:octocat/hello-world#0123abc'                              # a short sha is no pin
t pass  'npm install git+https://github.com/octocat/hello-world.git#0123456789abcdef0123456789abcdef01234567'
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
r pass  'cat ./cosign.key'                                                            # the checkout's key yields with the domain
r pass  'grep -rn ".sigstore/keys/release.key" docs/'                                 # a grep pattern, not a file operand
r pass  'cosign public-key --key ~/.sigstore/keys/release.key'                        # cosign reads the key itself
r deny  'cat /home/u/.sigstore/keys/release.key'                                      # never yields: the ~/.sigstore prelude
r deny  'cp ~/.sigstore/keys/release.key /tmp/k'
r deny  'base64 $HOME/.sigstore/keys/release.key'
r deny  'sudo cat ${HOME}/.sigstore/keys/release.key'
r deny  'cat < ~/.sigstore/keys/release.key'
r deny  'rg pattern ~/.sigstore/keys/release.key'                                     # a file operand of rg
r deny  'sh -c "head -c 64 ~/.sigstore/keys/release.key"'
r deny  'cat ~/.sig""store/keys/release.key'                                          # bypass: quotes inside the word
r deny  'cat ~/.sig\store/keys/release.key'                                            # bypass: a backslash inside the word
r deny  'cd ~ && cat .sigstore/keys/release.key'                                      # bypass: relative to the home
r deny  'echo ok; python3 /home/u/.sigstore/x.key'
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
unset VIRTUAL_ENV CONDA_PREFIX CONDA_DEFAULT_ENV CONDA_EXE MAMBA_ROOT_PREFIX PIPENV_ACTIVE SUPPLY_ALLOW_GLOBAL_RE SUPPLY_VENV_MARKERS
