# shellcheck shell=bash

# Section 38 (bundle supply-chain): package managers, lockfiles, signatures and downloads.
# Verification is never switched off (deny); installs go into the project, not the machine, and
# what is added is pinned (ask, deferred so a later deny in 40/41/60 still wins).
# SUPPLY_ALLOW_GLOBAL_RE (guard.env, supply_chain.allow_global_re): ERE that EVERY spec of a
# global install (pip outside a venv, npm|pnpm -g, yarn global add, cargo install) must match for
# it to pass; empty = every global install asks.
# SUPPLY_VENV_MARKERS (guard.env, supply_chain.venv_markers): names of environment variables that
# mean "inside a venv" when set in the hook's own environment (the provider was started from an
# activated venv); empty keeps the default list. READER_RE comes from core section 20.
SUPPLY_GLOBAL_RE="${SUPPLY_ALLOW_GLOBAL_RE:-}"
SUPPLY_MARKERS="${SUPPLY_VENV_MARKERS:-VIRTUAL_ENV CONDA_PREFIX PIPENV_ACTIVE}"
# a client word at a clause start or after a separator, bare or path-qualified (/usr/bin/pip3,
# ./pip, .venv/bin/pip); `sudo pip`, `env pip` and `xargs pip` are plain words after a space.
SUPPLY_W='(^|[^[:alnum:]_./-])((\.{0,2}/)?([^[:space:]/]+/)*)?'
# where a variable assignment takes effect: the clause start, an `sh|bash -c` string, $( or `,
# after env/export/sudo/xargs/command/nohup/time (with their options) and other assignments
SUPPLY_ENV_RE='(^|[[:space:]]-[A-Za-z]*c[[:space:]]+|\$\(|`)["'"'"']?[[:space:]]*(([^[:space:]]*/)?(env|export|sudo|command|nohup|time|xargs)([[:space:]]+-[^[:space:]]+)*[[:space:]]+)*([A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*[[:space:]]+)*'
SUPPLY_PIP_RE="${SUPPLY_W}"'(pip[0-9.]*|python[0-9.]*[[:space:]]+-m[[:space:]]+pip)[[:space:]]([^;&|]*[[:space:]])?install([[:space:]]|$)'
SUPPLY_NPM_RE="${SUPPLY_W}"'(npm|pnpm|yarn)[[:space:]]([^;&|]*[[:space:]])?(install|i|in|add)([[:space:]]|$)'
SUPPLY_COSIGN_RE="${SUPPLY_W}"'cosign([[:space:]]+-[^[:space:]]+)*[[:space:]]+'
repo_owns supply-chain/guard.d/38-supply-chain security && return 0   # principle 8: the repository's .harness.toml owns this section or domain security
# rule: pip --trusted-host | pip -i|--index-url|--extra-index-url http:// | PIP_TRUSTED_HOST= | PIP_INDEX_URL=http:// -> deny : disables TLS verification; use the HTTPS index with PIP_CERT or REQUESTS_CA_BUNDLE pointing at your CA bundle instead, or ask the user
# rule: npm|pnpm|yarn config set strict-ssl false | --strict-ssl=false | NPM_CONFIG_STRICT_SSL=false | config set registry http:// -> deny : disables TLS verification; use cafile or NODE_EXTRA_CA_CERTS with the HTTPS registry instead, or ask the user
# rule: git -c http.sslVerify=false | git config ... http.sslVerify false | GIT_SSL_NO_VERIFY= -> deny : disables TLS verification; set http.sslCAInfo to your CA bundle instead, or ask the user
# rule: GOINSECURE= | GOFLAGS=...-insecure | go get -insecure | go env -w GOINSECURE|GONOSUMDB|GONOSUMCHECK|GOFLAGS=-insecure -> deny : disables module verification; use GOPRIVATE=<prefix> and keep go.sum verification instead
# rule: cosign verify* --insecure-ignore-tlog|--insecure-ignore-sct|--insecure-skip-verify|--allow-insecure-registry|--allow-http-registry -> deny : skips a verification check; run supply verify or cosign verify without the flag and report exit 2 as a finding instead
# rule: <reader> cosign.key | .sigstore/**/*.key -> deny : a signing key; use keyless signing (a human release step) or pass --key and let cosign read it instead
# rule: pip install outside a venv (no venv marker in the environment or the command) | pip install --user|--break-system-packages | sudo pip -> ask : installs into the machine; run it inside the project (uv sync, uv pip install, .venv/bin/pip install) instead; supply_chain.allow_global_re allow-lists tools
# rule: npm|pnpm install|i|add -g|--global|--location=global | yarn global add -> ask : installs into the machine; add it to the project (npm i -D, npx) instead; supply_chain.allow_global_re allow-lists tools
# rule: cargo install ... -> ask : installs into ~/.cargo/bin; use cargo run or cargo build in the checkout instead; supply_chain.allow_global_re allow-lists tools
# rule: go install ...@latest|@master|@main|@HEAD -> ask : unpinned; pin a version (m@v1.2.3) instead
# rule: pip install git+URL without @<sha> (or @main|master|develop|HEAD|latest) | pip install https://...whl|.tar.gz|.zip without --hash | npm|pnpm|yarn install|add github:O/R|O/R|git+URL|git://|https://...tgz without #<sha> | cargo install|add --git with --branch or without --rev|--tag -> ask : unpinned dependency; pin a commit or a released version instead; run supply pins to list every unpinned reference
# rule: GONOSUMDB=|GONOSUMCHECK= one-shot env prefix -> ask : skips go.sum verification; use GOPRIVATE=<prefix> instead
# rule: cosign sign|sign-blob|attest|attest-blob|upload|copy|generate-key-pair|import-key-pair -> ask : a human release step; hand the command to the user (supply verify and cosign verify stay available)
# rule: curl -k|--insecure ... -o|-O|--output|--remote-name|> FILE | wget --no-check-certificate (not to stdout) -> ask : an unverified file; use the HTTPS URL with --cacert (wget --ca-certificate) instead
supply_venv_active() {  # -> rc 0 when any SUPPLY_VENV_MARKERS name is set (non-empty) in the hook's environment
  local m
  for m in $SUPPLY_MARKERS; do
    case "$m" in ''|[0-9]*|*[!A-Za-z0-9_]*) continue ;; esac
    [ -z "${!m:-}" ] || return 0
  done
  return 1
}
supply_words() {  # TEXT -> its words, one per line, quotes dropped (no glob expansion, no subshell per word)
  printf '%s\n' "$1" | command tr "\"'[:space:]" '\n\n\n\n' | grep -v '^$'
}
supply_after() {  # CLAUSE VERB_ERE -> the text after the last VERB word of the clause
  printf '%s' "$1" | sed -E "s/^.*[[:space:]]($2)([[:space:]]|\$)/ /"
}
supply_allowed_global() {  # TEXT -> rc 0 when SUPPLY_ALLOW_GLOBAL_RE is set and every spec in TEXT matches it
  local w n=0
  [ -n "$SUPPLY_GLOBAL_RE" ] || return 1
  while IFS= read -r w; do
    case "$w" in ''|-*) continue ;; esac
    n=$((n+1))
    printf '%s' "$w" | grep -qE -- "$SUPPLY_GLOBAL_RE" 2>/dev/null || return 1
  done <<EOF
$(supply_words "$1")
EOF
  [ "$n" -gt 0 ]
}
supply_git_ref_unpinned() {  # WORD (git+scheme://[user@]host/path[@ref][#frag]) -> rc 0 when no commit is pinned
  local u ref
  u=${1#*://}; u=${u%%#*}
  case "${u%%/*}" in *@*) u=${u#*@} ;; esac          # userinfo (git@host) is not a ref
  case "$u" in *@*) ref=${u##*@} ;; *) return 0 ;; esac
  printf '%s' "$ref" | grep -qE '^[0-9a-f]{7,40}$' && return 1
  case "$ref" in main|master|develop|HEAD|latest|'') return 0 ;; esac
  return 1                                           # a tag passes here; `supply pins` reports it
}
supply_npm_unpinned() {  # TEXT (words after install|add) -> rc 0 when a git/URL/shorthand spec has no #<sha>
  local w skip=0
  while IFS= read -r w; do
    if [ "$skip" = 1 ]; then skip=0; continue; fi
    case "$w" in
      --prefix|--registry|--cache|--userconfig|--tag|--workspace|-w|--filter|--dir|-C|--cwd) skip=1; continue ;;
      -*) continue ;;
    esac
    case "$w" in
      github:*|gitlab:*|bitbucket:*|gist:*|git+*|git://*|http://*.tgz|https://*.tgz|http://*.tar.gz|https://*.tar.gz) ;;
      *) printf '%s' "$w" | grep -qE '^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9_.-]+(#.*)?$' || continue ;;
    esac
    printf '%s' "$w" | grep -qE '#[0-9a-f]{7,40}$' || return 0
  done <<EOF
$(supply_words "$1")
EOF
  return 1
}
SUPPLY_GLOBAL_HINT="supply_chain.allow_global_re allow-lists global tools"
supply_venv=false; supply_venv_active && supply_venv=true
supply_activated=false
printf '%s' "$flat" | grep -qE '(^|[^[:alnum:]_])(source|\.)[[:space:]]+[^;&|]*/bin/activate[[:space:]]*(&&|;)' && supply_activated=true
while IFS= read -r clause; do
  [ -n "$clause" ] || continue
  # ---- deny: verification switched off -------------------------------------------------
  case "$clause" in *[pP][iI][pP]*|*uv*)
    if printf '%s' "$clause" | grep -qE "${SUPPLY_ENV_RE}(PIP_TRUSTED_HOST=|PIP_(EXTRA_)?INDEX_URL=[\"']?http://)" \
       || { printf '%s' "$clause" | grep -qE "${SUPPLY_W}(pip[0-9.]*|uv)[[:space:]]" \
            && printf '%s' "$clause" | grep -qE "[[:space:]](--trusted-host([[:space:]=]|\$)|(-i|--index-url|--extra-index-url)([[:space:]]+|=)[\"']?http://)"; }; then
      deny "pip --trusted-host / an http:// index / PIP_TRUSTED_HOST switches TLS verification off — use the HTTPS index with PIP_CERT or REQUESTS_CA_BUNDLE pointing at your CA bundle instead, or ask the user"
    fi
  ;; esac
  case "$clause" in *[nN][pP][mM]*|*yarn*)
    if printf '%s' "$clause" | grep -qiE "${SUPPLY_ENV_RE}npm_config_strict_ssl=[\"']?false" \
       || { printf '%s' "$clause" | grep -qE "${SUPPLY_W}(npm|pnpm|yarn)[[:space:]]" \
            && printf '%s' "$clause" | grep -qE "([[:space:]]config[[:space:]]+set[[:space:]]+[\"']?(strict-ssl[\"']?([[:space:]]+|=)[\"']?false|([^[:space:]=]*:)?registry[\"']?([[:space:]]+|=)[\"']?http://)|[[:space:]]--strict-ssl([[:space:]]+|=)false([[:space:]]|\$))"; }; then
      deny "npm/pnpm/yarn strict-ssl false or an http:// registry switches TLS verification off — set cafile or NODE_EXTRA_CA_CERTS to your CA bundle and keep the HTTPS registry instead, or ask the user"
    fi
  ;; esac
  case "$clause" in *GIT_SSL*|*[sS][sS][lL][vV][eE][rR][iI][fF][yY]*)
    if printf '%s' "$clause" | grep -qE "${SUPPLY_ENV_RE}GIT_SSL_NO_VERIFY=" \
       || printf '%s' "$clause" | grep -qiE "${SUPPLY_W}git[[:space:]]([^;&|]*[[:space:]])?-c[[:space:]]*[\"']?http\.([^[:space:]=]*\.)?sslverify[\"']?=[\"']?(false|no|off|0)([\"'[:space:]]|\$)" \
       || printf '%s' "$clause" | grep -qiE "${SUPPLY_W}git[[:space:]]([^;&|]*[[:space:]])?config[[:space:]]([^;&|]*[[:space:]])?[\"']?http\.([^[:space:]=]*\.)?sslverify[\"']?([[:space:]]+|=)[\"']?(false|no|off|0)([\"'[:space:]]|\$)"; then
      deny "git http.sslVerify=false / GIT_SSL_NO_VERIFY switches TLS verification off — set http.sslCAInfo to your CA bundle instead, or ask the user"
    fi
  ;; esac
  case "$clause" in *GOINSECURE*|*GOFLAGS*|*-insecure*|*GONOSUM*)
    if printf '%s' "$clause" | grep -qE "${SUPPLY_ENV_RE}(GOINSECURE=|GOFLAGS=[\"']?[^;&|]*-insecure)" \
       || printf '%s' "$clause" | grep -qE "${SUPPLY_W}go[[:space:]]+get[[:space:]]([^;&|]*[[:space:]])?-insecure([[:space:]=]|\$)" \
       || printf '%s' "$clause" | grep -qE "${SUPPLY_W}go[[:space:]]+env[[:space:]]([^;&|]*[[:space:]])?-w[[:space:]][^;&|]*((GOINSECURE|GONOSUMDB|GONOSUMCHECK)=|GOFLAGS=[\"']?[^;&|]*-insecure)"; then
      deny "GOINSECURE / -insecure / a persistent GONOSUMDB switches Go module verification off — use GOPRIVATE=<module prefix> for private modules and keep go.sum verification instead"
    fi
  ;; esac
  case "$clause" in *cosign*)
    if printf '%s' "$clause" | grep -qE "${SUPPLY_COSIGN_RE}verify[a-z-]*[[:space:]]" \
       && printf '%s' "$clause" | grep -qE "[[:space:]]--(insecure-ignore-tlog|insecure-ignore-sct|insecure-skip-verify|allow-insecure-registry|allow-http-registry)(=[\"']?(true|1)|[\"'[:space:]]|\$)"; then
      deny "cosign verify with --insecure-*/--allow-*-registry skips a verification check — run 'supply verify' or 'cosign verify' without the flag instead and report a failure (exit 2) as a finding"
    fi
  ;; esac
  case "$clause" in *cosign.key*|*.sigstore/*)
    if printf '%s' "$clause" | grep -qE "${READER_RE}(cosign\.key|\.sigstore/[^[:space:]]*\.key)([^A-Za-z0-9_.-]|\$)"; then
      deny "reading a cosign private key (cosign.key, ~/.sigstore/**/*.key) — use keyless signing in the human release step, or pass --key and let cosign read the key itself instead"
    fi
  ;; esac
  # ---- ask (deferred): installs into the machine --------------------------------------
  case "$clause" in *pip*)
    if printf '%s' "$clause" | grep -qE "$SUPPLY_PIP_RE"; then
      supply_rest=$(supply_after "$clause" install)
      if printf '%s' "$clause" | grep -qE "(^|[^[:alnum:]_./-])sudo[[:space:]]|[[:space:]]--break-system-packages([[:space:]=\"']|\$)"; then
        defer "pip install with sudo or --break-system-packages writes into the system Python — run it inside the project instead (uv sync, uv pip install, .venv/bin/pip install)"
      elif printf '%s' "$clause" | grep -qE "[[:space:]]--user([[:space:]\"']|\$)"; then
        supply_allowed_global "$supply_rest" \
          || defer "pip install --user installs into your home, outside the project — run it inside the project instead (uv sync, uv pip install, .venv/bin/pip install); $SUPPLY_GLOBAL_HINT"
      elif $supply_venv || $supply_activated \
           || printf '%s' "$clause" | grep -qE "(^|[^[:alnum:]_./-])(uv|pipx|poetry|pipenv|pdm|hatch)([[:space:]]+(run|exec|-[^[:space:]]+))*[[:space:]]+([^[:space:]]*/)?(pip[0-9.]*|python[0-9.]*|runpip)[[:space:]]" \
           || printf '%s' "$clause" | grep -qE "venv/bin/|\\\$\{?VIRTUAL_ENV\}?/|(^|[^A-Za-z0-9_])VIRTUAL_ENV=|[[:space:]](--target|--prefix|--dry-run)([[:space:]=]|\$)"; then
        :
      else
        supply_allowed_global "$supply_rest" \
          || defer "pip install outside a virtual environment installs into the machine — run it inside the project instead (uv sync, uv pip install, .venv/bin/pip install), or start the agent from the activated venv; $SUPPLY_GLOBAL_HINT"
      fi
      # unpinned git / URL requirements, inside a venv too
      while IFS= read -r supply_w; do
        case "$supply_w" in
          git+*://*) supply_git_ref_unpinned "$supply_w" && defer "unpinned dependency (git or URL reference without a commit) — pin a commit or a released version instead (pip: git+URL@<sha>, npm: #<sha>, cargo: --rev <sha>); run 'supply pins' to list every unpinned reference" ;;
          http://*.whl|https://*.whl|http://*.tar.gz|https://*.tar.gz|http://*.zip|https://*.zip)
            printf '%s' "$clause" | grep -qE "[[:space:]]--hash([[:space:]=]|\$)" || defer "unpinned dependency (git or URL reference without a commit) — pin a commit or a released version instead (pip: git+URL@<sha>, npm: #<sha>, cargo: --rev <sha>); run 'supply pins' to list every unpinned reference" ;;
        esac
      done <<EOF
$(supply_words "$supply_rest")
EOF
    fi
  ;; esac
  case "$clause" in *npm*|*yarn*)
    if printf '%s' "$clause" | grep -qE "$SUPPLY_NPM_RE"; then
      supply_rest=$(supply_after "$clause" 'install|i|in|add')
      if printf '%s' "$clause" | grep -qE "${SUPPLY_W}(npm|pnpm)[[:space:]]" \
         && printf '%s' "$clause" | grep -qE "[[:space:]](-g|--global(=true)?|--location([[:space:]]+|=)global)([[:space:]\"']|\$)"; then
        supply_allowed_global "$supply_rest" \
          || defer "global npm/pnpm install puts the package into the machine — add it to the project instead (npm i -D, then npx); $SUPPLY_GLOBAL_HINT"
      fi
      supply_npm_unpinned "$supply_rest" && defer "unpinned dependency (git or URL reference without a commit) — pin a commit or a released version instead (pip: git+URL@<sha>, npm: #<sha>, cargo: --rev <sha>); run 'supply pins' to list every unpinned reference"
    fi
  ;; esac
  case "$clause" in *yarn*)
    if printf '%s' "$clause" | grep -qE "${SUPPLY_W}yarn[[:space:]]+global[[:space:]]+add([[:space:]]|\$)"; then
      supply_allowed_global "$(supply_after "$clause" add)" \
        || defer "yarn global add puts the package into the machine — add it to the project instead (yarn add -D, then yarn run); $SUPPLY_GLOBAL_HINT"
    fi
  ;; esac
  case "$clause" in *cargo*)
    if printf '%s' "$clause" | grep -qE "${SUPPLY_W}cargo[[:space:]]([^;&|]*[[:space:]])?install([[:space:]]|\$)" \
       && ! printf '%s' "$clause" | grep -qE "[[:space:]]--list([[:space:]]|\$)"; then
      supply_allowed_global "$(supply_after "$clause" install)" \
        || defer "cargo install puts a binary into ~/.cargo/bin — use cargo run or cargo build in the checkout instead; $SUPPLY_GLOBAL_HINT"
    fi
  ;; esac
  case "$clause" in *cargo*)
    if printf '%s' "$clause" | grep -qE "${SUPPLY_W}cargo[[:space:]]([^;&|]*[[:space:]])?(install|add)[[:space:]]([^;&|]*[[:space:]])?--git([[:space:]=]|\$)"; then
      if printf '%s' "$clause" | grep -qE "[[:space:]]--branch([[:space:]=]|\$)" \
         || ! printf '%s' "$clause" | grep -qE "[[:space:]]--(rev|tag)([[:space:]=]|\$)"; then
        defer "unpinned dependency (git or URL reference without a commit) — pin a commit or a released version instead (pip: git+URL@<sha>, npm: #<sha>, cargo: --rev <sha>); run 'supply pins' to list every unpinned reference"
      fi
    fi
  ;; esac
  case "$clause" in *go*install*@*)
    if printf '%s' "$clause" | grep -qE "${SUPPLY_W}go[[:space:]]+install[[:space:]][^;&|]*@(latest|master|main|HEAD)([[:space:]\"']|\$)"; then
      defer "go install of @latest or a branch installs an unpinned version — pin a version instead (go install example.com/tool@v1.2.3)"
    fi
  ;; esac
  # ---- ask (deferred): checksum database skipped, signing, unverified downloads ---------
  case "$clause" in *GONOSUM*)
    if printf '%s' "$clause" | grep -qE "${SUPPLY_ENV_RE}(GONOSUMDB|GONOSUMCHECK)="; then
      defer "GONOSUMDB / GONOSUMCHECK skips go.sum verification against the checksum database — use GOPRIVATE=<module prefix> for private modules instead"
    fi
  ;; esac
  case "$clause" in *cosign*)
    if printf '%s' "$clause" | grep -qE "${SUPPLY_COSIGN_RE}(sign|sign-blob|attest|attest-blob|upload|copy|generate-key-pair|import-key-pair)([[:space:]]|\$)"; then
      defer "cosign signing, attesting, uploading and key generation are a human release step — hand the command to the user; 'supply verify' and 'cosign verify' stay available"
    fi
  ;; esac
  case "$clause" in *curl*)
    if printf '%s' "$clause" | grep -qE "${SUPPLY_W}curl[[:space:]]" \
       && printf '%s' "$clause" | grep -qE "(^|[[:space:]])(-[A-Za-z]*k[A-Za-z]*|--insecure)([[:space:]]|\$)"; then
      supply_out=false
      printf '%s' "$clause" | grep -qE "(^|[[:space:]])(-[A-Za-z]*[oO][A-Za-z]*|--output|--remote-name|--remote-name-all|--output-dir)([[:space:]=]|\$)" && supply_out=true
      # a stdout redirection to anything but /dev/null|stdout|stderr (no pipe: pipefail + grep -q)
      supply_redir=$(printf '%s' "$clause" | grep -oE '(^|[^0-9&>])>>?[[:space:]]*[^&[:space:]>]+' | sed -E 's/^[^>]*>+[[:space:]]*//')
      while IFS= read -r supply_w; do
        case "$supply_w" in ''|/dev/null|/dev/stdout|/dev/stderr) ;; *) supply_out=true ;; esac
      done <<EOF2
$supply_redir
EOF2
      $supply_out && defer "curl -k/--insecure writes an unverified file — use the HTTPS URL with --cacert <CA bundle> instead"
    fi
  ;; esac
  case "$clause" in *wget*)
    if printf '%s' "$clause" | grep -qE "${SUPPLY_W}wget[[:space:]]([^;&|]*[[:space:]])?--no-check-certificate([[:space:]]|\$)" \
       && ! printf '%s' "$clause" | grep -qE "(^|[[:space:]])(-[A-Za-z]*O[[:space:]]*-|--output-document([[:space:]]+|=)-|--spider)([[:space:]]|\$)"; then
      defer "wget --no-check-certificate writes an unverified file — use the HTTPS URL with --ca-certificate <CA bundle> instead"
    fi
  ;; esac
done <<EOF
$(printf '%s' "$flat" | command tr ';&|' '\n\n\n')
EOF
unset supply_venv supply_activated supply_rest supply_w supply_out supply_redir
