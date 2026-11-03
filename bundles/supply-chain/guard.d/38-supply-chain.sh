# shellcheck shell=bash

# Section 38 (bundle supply-chain): package managers, lockfiles, signatures and downloads.
# Verification is never switched off (deny); installs go into the project or an isolated or
# pinned tool install, never into the machine, and what is added is pinned (ask, deferred so a
# later deny in 40/41/60 still wins).
# SUPPLY_ALLOW_GLOBAL_RE (guard.env, supply_chain.allow_global_re): ERE that EVERY spec of a
# global install (pip outside a venv or --user, npm|pnpm -g, yarn global add, cargo install)
# must match for it to pass; empty = every global install asks. Anchor it (^…$).
# SUPPLY_VENV_MARKERS (guard.env, supply_chain.venv_markers): names of environment variables that
# mean "inside a venv" when set in the hook's own environment (the provider was started from an
# activated venv); empty keeps the default list. CONDA_PREFIX counts only outside conda's base
# env (supply_conda_base).
#
# How a command is read: the raw command ($cmd, newlines kept) is lexed once by awk into clauses,
# split on ; & | newline ( ) ` and { } words, also inside quotes; quotes and backslashes are
# removed, comments and heredoc bodies dropped (unless a shell reads the heredoc), and the string
# of `sh|bash -c` or `eval` is a command of its own. Each output line is `T<tab>clause` (a
# command) or `Q<tab>clause` (a piece of a quoted argument, which inherits the exemption of its
# command). A command whose first word is a text tool (echo, printf, grep, rg, sed, awk, cat,
# head, tail, less, man, help, git log|grep|show|commit|diff) only mentions what it prints and is
# exempt, unless the line can run text as code ($( ` eval, sh -c, a pipe into a shell). Readers
# still count for the cosign key deny. `--help`, `-h` and `<tool> help` are reads (no asks).
SUPPLY_GLOBAL_RE="${SUPPLY_ALLOW_GLOBAL_RE:-}"
SUPPLY_MARKERS="${SUPPLY_VENV_MARKERS:-VIRTUAL_ENV CONDA_PREFIX PIPENV_ACTIVE}"
# a client word at a clause start or after a separator, bare or path-qualified (/usr/bin/pip3,
# ./pip, .venv/bin/pip); `sudo pip`, `env pip` and `xargs pip` are plain words after a space.
SUPPLY_W='(^|[^[:alnum:]_./-])((\.{0,2}/)?([^[:space:]/]+/)*)?'
SUPPLY_PIP_RE="${SUPPLY_W}"'(pip[0-9.]*|python[0-9.]*[[:space:]]+-m[[:space:]]+pip)[[:space:]]([^[:space:]]+[[:space:]]+)*install([[:space:]]|$)'
SUPPLY_NPM_RE="${SUPPLY_W}"'(npm|pnpm|yarn)[[:space:]]([^[:space:]]+[[:space:]]+)*(install|i|in|add)([[:space:]]|$)'
SUPPLY_COSIGN_RE="${SUPPLY_W}"'cosign([[:space:]]+-[^[:space:]]+)*[[:space:]]+'
SUPPLY_TAB='	'
# never-yields: reads the developer's own Sigstore signing key (principle 8 exemption; runs even when the repository owns security)
# rule: <reader> ~/.sigstore/**/*.key (any .sigstore/**/*.key, so cd ~ is no bypass) as a file operand (a grep|rg pattern is not) -> deny : the developer's signing key; pass --key and let cosign read it, or leave keyless signing to the human release step, instead
local supply_lex supply_pn supply_psf supply_pl supply_c0="" supply_c1=""
supply_cmd0() {  # CLAUSE -> supply_c0 = base name of the command word after keywords, wrappers and assignments; supply_c1 = the next word
  local w wrap=false
  supply_c0=""; supply_c1=""
  for w in $1; do
    if [ -n "$supply_c0" ]; then supply_c1=$w; return 0; fi
    case "$w" in
      '!'|then|do|else|elif|if|while|until|time) continue ;;
      env|export|declare|typeset|readonly|local|sudo|doas|command|builtin|nohup|xargs|nice|timeout|exec|stdbuf|setsid|ionice|chrt|unbuffer)
        wrap=true; continue ;;
      [A-Za-z_]*=*) continue ;;
      -*|[0-9]*) if $wrap; then continue; fi ;;
    esac
    supply_c0=${w##*/}
  done
  return 0
}
supply_reads_key() {  # KIND CLAUSE -> rc 0 when a reader takes a key file of KIND as a file operand: sigstore = .sigstore/**/*.key, cosign = cosign.key
  local w started=false pattern=false want=false kind=$1
  shift
  supply_cmd0 "$1"
  case "$supply_c0" in
    cat|tac|less|more|bat|head|tail|nl|yq|jq|sed|awk|cut|python|python3|perl|ruby|node|base64|xxd|od|strings|cp|scp|rsync|tee|vi|vim|nvim|nano|code|source|.) ;;
    grep|egrep|fgrep|rg|ag) pattern=true ;;
    *) return 1 ;;
  esac
  for w in $1; do
    if ! $started; then [ "${w##*/}" = "$supply_c0" ] && started=true; continue; fi
    if $want; then want=false; continue; fi            # the -e|-f value of grep: the pattern
    case "$w" in
      -e|-f|--regexp|--file) if $pattern; then pattern=false; want=true; fi; continue ;;
      -e*|--regexp=*) pattern=false; continue ;;
      -*) continue ;;
    esac
    if $pattern; then pattern=false; continue; fi      # the first operand of grep|rg is the pattern
    w=${w#<}
    case "$kind:$w" in sigstore:.sigstore/*.key|sigstore:*/.sigstore/*.key|cosign:cosign.key|cosign:*/cosign.key) return 0 ;; esac
  done
  return 1
}
# The lexer (see the header). POSIX awk only (BSD awk, mawk, gawk); one call per command.
supply_lex='
function emit(nk) { sub(/^[ \t]+/, "", cur); sub(/[ \t]+$/, "", cur); if (cur != "") print kind "\t" cur; cur = ""; kind = nk }
function shellctx() { return (cur ~ /(^|[ \/])(sh|bash|zsh|dash|ksh)( +-[A-Za-z]+)* +-[A-Za-z]*c +$/ || cur ~ /(^| )eval +$/) }
function isshell(  t) { t = cur; sub(/^[ \t]+/, "", t); return (t ~ /^([^ ]*\/)?(sh|bash|zsh|dash|ksh)( |$)/) }
BEGIN { RS = "\001" }
{
  s = $0; n = length(s); cur = ""; kind = "T"; q = ""; data = 0; bt = 0; hp = 0; i = 1
  while (i <= n) {
    c = substr(s, i, 1); d = substr(s, i + 1, 1); p = (i > 1) ? substr(s, i - 1, 1) : ""
    if (c == "\\") {
      if (q == sq) { i++; continue }
      if (d == "\n") { i += 2; continue }
      cur = cur d; i += 2; continue
    }
    if (q != "") {
      if (c == q) { q = ""; i++; continue }
      if (c == "\n" || c == ";" || c == "|" || (c == "&" && p != ">" && p != "<" && d != ">")) { emit(data ? "Q" : "T"); i++; continue }
      if (q == "\"" && c == "$" && d == "(") { emit("T"); i += 2; continue }
      if (q == "\"" && c == ")") { emit(data ? "Q" : "T"); i++; continue }
      if (q == "\"" && c == "`") { bt = !bt; emit((bt || !data) ? "T" : "Q"); i++; continue }
      if (c == "\t") c = " "
      cur = cur c; i++; continue
    }
    if (c == sq || c == "\"") {
      if (shellctx()) { emit("T"); data = 0 } else data = 1
      q = c; i++; continue
    }
    if (c == "#" && (cur == "" || cur ~ /[ \t]$/)) { while (i <= n && substr(s, i, 1) != "\n") i++; continue }
    if (c == "<" && d == "<") {
      if (substr(s, i + 2, 1) == "<") { cur = cur " <<< "; i += 3; continue }
      j = i + 2; hs = 0
      if (substr(s, j, 1) == "-") { hs = 1; j++ }
      while (substr(s, j, 1) == " " || substr(s, j, 1) == "\t") j++
      w = ""
      while (j <= n) { e = substr(s, j, 1); if (e ~ /[ \t\n;&|<>()]/) break; if (e != "\"" && e != sq && e != "\\") w = w e; j++ }
      if (w != "") { hp = 1; hw = w; hx = isshell() }
      i = j; continue
    }
    if (c == "\n") {
      emit("T"); i++
      if (hp) {
        hp = 0
        if (!hx) {
          while (i <= n) {
            k = index(substr(s, i), "\n")
            if (k == 0) { line = substr(s, i); i = n + 1 } else { line = substr(s, i, k - 1); i += k }
            if (hs) sub(/^\t+/, "", line)
            if (line == hw) break
          }
        }
      }
      continue
    }
    if (c == ";" || c == "(" || c == ")" || c == "`") { emit("T"); i++; continue }
    if (c == "|") { if (p == ">") { cur = cur c; i++; continue } emit("T"); i++; continue }
    if (c == "&") { if (p == ">" || p == "<" || d == ">") { cur = cur c; i++; continue } emit("T"); i++; continue }
    if ((c == "{" || c == "}") && (cur == "" || cur ~ /[ \t]$/) && (d == "" || d ~ /[ \t\n;]/)) { emit("T"); i++; continue }
    if (c == "\t") c = " "
    cur = cur c; i++
  }
  emit("T")
}'
supply_pn=${cmd//\\/}; supply_pn=${supply_pn//\"/}; supply_pn=${supply_pn//\'/}
case "$supply_pn" in *.sigstore/*)
  supply_psf=$-
  set -f
  while IFS= read -r supply_pl; do
    case "$supply_pl" in T"$SUPPLY_TAB"*.sigstore/*) ;; *) continue ;; esac
    supply_reads_key sigstore "${supply_pl#*"$SUPPLY_TAB"}" \
      && deny "reading a Sigstore signing key under ~/.sigstore (the developer's own credential; no repository declaration lifts this) — pass --key and let cosign read the key itself, or leave keyless signing to the human release step, instead"
  done <<EOF
$(printf '%s' "$cmd" | awk -v sq="'" "$supply_lex")
EOF
  case "$supply_psf" in *f*) ;; *) set +f ;; esac
;; esac
repo_owns supply-chain/guard.d/38-supply-chain security && return 0   # principle 8: the repository's .harness.toml owns this section or domain security
# rule: pip|uv --trusted-host (or a unique prefix such as --trusted) | uv --allow-insecure-host | pip|uv -i|--index[-url]|--extra-index[-url]|--default-index http:// | pip config set <section>.trusted-host | pip config set <section>.[extra-]index-url http:// | PIP_TRUSTED_HOST= | PIP_[EXTRA_]INDEX_URL=http:// | UV_INSECURE_HOST= | UV_[DEFAULT_|EXTRA_]INDEX[_URL]=http:// -> deny : disables TLS verification; use the HTTPS index with PIP_CERT or REQUESTS_CA_BUNDLE (uv: SSL_CERT_FILE) pointing at your CA bundle instead, or ask the user
# rule: npm|pnpm|yarn [config] set strict-ssl false | --strict-ssl=false | --no-strict-ssl | NPM_CONFIG_STRICT_SSL=false | [config] set registry http:// | --registry (or --reg) http:// | yarn config set enableStrictSsl false|npmRegistryServer http://|unsafeHttpWhitelist | YARN_ENABLE_STRICT_SSL=false | NODE_TLS_REJECT_UNAUTHORIZED=0 -> deny : disables TLS verification; use cafile or NODE_EXTRA_CA_CERTS with the HTTPS registry instead, or ask the user
# rule: git -c|--config http[.<url>].sslVerify=false|no|off|0|<empty> | git config ... http.sslVerify false | --config-env=http.sslVerify=… | GIT_CONFIG_KEY_<n>=http.sslVerify | GIT_SSL_NO_VERIFY= -> deny : disables TLS verification; set http.sslCAInfo to your CA bundle instead, or ask the user
# rule: GOINSECURE=<value> | GOFLAGS=...-insecure | go get -insecure | go env -w GONOSUMDB|GONOSUMCHECK=<value> -> deny : disables module verification; use GOPRIVATE=<prefix> and keep go.sum verification instead
# rule: GOSUMDB=off | go env -w GOSUMDB=off -> deny : switches the checksum database off for every module; use GOPRIVATE=<prefix> or a one-shot GONOSUMDB=<prefix> for private modules instead
# rule: cosign verify* --insecure-ignore-tlog|--insecure-ignore-sct|--insecure-skip-verify|--allow-insecure-registry|--allow-http-registry|--private-infrastructure[=true|t|1] -> deny : skips a verification check; run supply verify or cosign verify without the flag and report exit 2 as a finding instead
# rule: <reader> cosign.key as a file operand (a grep|rg pattern is not) -> deny : a signing key; use keyless signing (a human release step) or pass --key and let cosign read it instead
# rule: pip install outside a venv (no venv marker in the environment, no earlier activate clause, no runner, no venv pip as the command word; conda base is no venv) | --target|--prefix outside the checkout | --user | --break-system-packages | uv pip install --system | UV_SYSTEM_PYTHON=1 | sudo pip -> ask : installs into the machine; run it inside the project (uv sync, uv pip install, .venv/bin/pip install) instead; supply_chain.allow_global_re allow-lists tools
# rule: npm|pnpm install|i|add -g|--global|--location=global|-<flags with g> | yarn global add -> ask : installs into the machine; add it to the project (npm i -D, npx) instead; supply_chain.allow_global_re allow-lists tools
# rule: cargo install ... without both --locked and --version -> ask : an unpinned machine install; use cargo run or cargo build in the checkout, or pass --locked --version V, instead; supply_chain.allow_global_re allow-lists tools
# rule: go install ...@latest|@master|@main|@HEAD -> ask : unpinned; pin a version (m@v1.2.3) instead
# rule: pip install git+URL without @<sha> (or @main|master|develop|HEAD|latest) | pip install https://...whl|.tar.gz|.zip without --hash | npm|pnpm|yarn install|add github:O/R|O/R|git+URL|git:// without #<40-hex sha> | npm|pnpm|yarn install|add https://...tgz (a fragment is no pin) | cargo install|add --git with --branch, or with neither --rev nor --tag -> ask : unpinned dependency; pin a commit or a released version instead; run supply pins to list every unpinned reference
# rule: GONOSUMDB=<value>|GONOSUMCHECK=<value> one-shot env prefix -> ask : skips go.sum verification; use GOPRIVATE=<prefix> instead
# rule: cosign sign|sign-blob|attest|attest-blob|attach signature|sbom|attestation|upload|copy|clean|generate-key-pair|import-key-pair -> ask : a human release step (registry writes, keys); hand the command to the user (supply verify and cosign verify stay available)
# rule: curl -k|--insecure ... -o|-O|--output|--remote-name|--output-dir FILE (not - or /dev/null) | > FILE | ... piped into tar|unzip|tee|dd|cpio | wget --no-check-certificate (not to stdout) -> ask : an unverified file; use the HTTPS URL with --cacert (wget --ca-certificate) instead
local supply_n supply_clauses supply_line supply_kind clause supply_exempt=false supply_noexempt=false
local supply_read=false supply_c0="" supply_c1="" supply_rest supply_w supply_v supply_out supply_venv=false supply_activated=false
local supply_sf=$-
# ---- whole-command precheck (builtins only): most commands never reach the lexer ------------
supply_n=${cmd//\\/}; supply_n=${supply_n//\"/}; supply_n=${supply_n//\'/}
case "$supply_n" in
  *pip*|*uv*|*UV_*|*PIP_*|*[nN][pP][mM]*|*yarn*|*YARN_*|*NODE_TLS*|*[sS][sS][lL]*|*GO*|*go[[:space:]]*|*cosign*|*sigstore*|*cargo*|*curl*|*wget*) ;;
  *) return 0 ;;
esac
set -f                                                 # word loops below never glob; restored at the end
supply_conda_base() {  # -> rc 0 when the active conda env is base (or cannot be told apart from it)
  case "${CONDA_DEFAULT_ENV:-}" in ''|base|root) return 0 ;; esac
  [ "${CONDA_DEFAULT_ENV}" != "${CONDA_PREFIX:-}" ] || return 0      # base activated by path
  [ -z "${CONDA_EXE:-}" ] || [ "${CONDA_PREFIX:-}" != "${CONDA_EXE%/bin/*}" ] || return 0
  [ -z "${MAMBA_ROOT_PREFIX:-}" ] || [ "${CONDA_PREFIX:-}" != "${MAMBA_ROOT_PREFIX%/}" ] || return 0
  return 1
}
supply_venv_active() {  # -> rc 0 when any SUPPLY_VENV_MARKERS name is set (non-empty) in the hook's environment
  local m
  for m in $SUPPLY_MARKERS; do
    case "$m" in ''|[0-9]*|*[!A-Za-z0-9_]*) continue ;; esac
    [ -n "${!m:-}" ] || continue
    if [ "$m" = CONDA_PREFIX ] && supply_conda_base; then continue; fi
    return 0
  done
  return 1
}
supply_specs() {  # CLAUSE VERBS (|-separated) -> the words after the FIRST verb word, one per line, without redirections
  local w found=false skip=false
  for w in $1; do
    if ! $found; then
      case "|$2|" in *"|$w|"*) found=true ;; esac
      continue
    fi
    if $skip; then skip=false; continue; fi
    case "$w" in
      '<'|'>'|'>>'|[0-9]'>'|[0-9]'>>'|'&>'|'<<<') skip=true; continue ;;
      '<'*|'>'*|[0-9]'>'*|[0-9]'<'*|'&>'*) continue ;;
    esac
    printf '%s\n' "$w"
  done
}
supply_allowed_global() {  # SPECS (one per line) -> rc 0 when SUPPLY_ALLOW_GLOBAL_RE is set and every spec matches it
  local w n=0
  [ -n "$SUPPLY_GLOBAL_RE" ] || return 1
  while IFS= read -r w; do
    case "$w" in ''|-*) continue ;; esac
    n=$((n+1))
    printf '%s' "$w" | grep -qE -- "$SUPPLY_GLOBAL_RE" 2>/dev/null || return 1
  done <<EOF
$1
EOF
  [ "$n" -gt 0 ]
}
supply_git_ref_unpinned() {  # WORD (scheme://[user@]host/path[@ref][#frag]) -> rc 0 when no commit is pinned
  local u ref
  u=${1#*://}; u=${u%%#*}
  case "${u%%/*}" in *@*) u=${u#*@} ;; esac          # userinfo (git@host) is not a ref
  case "$u" in *@*) ref=${u##*@} ;; *) return 0 ;; esac
  printf '%s' "$ref" | grep -qE '^[0-9a-f]{7,40}$' && return 1
  case "$ref" in main|master|develop|HEAD|latest|'') return 0 ;; esac
  return 1                                           # a tag passes here; `supply pins` reports it
}
supply_npm_unpinned() {  # SPECS -> rc 0 for a tarball URL, or a git/shorthand spec without #<40-hex>
  local w skip=false
  while IFS= read -r w; do
    if $skip; then skip=false; continue; fi
    case "$w" in
      --prefix|--registry|--cache|--userconfig|--tag|--workspace|-w|--filter|--dir|-C|--cwd) skip=true; continue ;;
      -*|'') continue ;;
      http://*.tgz|https://*.tgz|http://*.tar.gz|https://*.tar.gz|http://*.tgz#*|https://*.tgz#*|http://*.tar.gz#*|https://*.tar.gz#*) return 0 ;;
      github:*|gitlab:*|bitbucket:*|gist:*|git+*|git://*) ;;
      *) printf '%s' "$w" | grep -qE '^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9_.-]+(#.*)?$' || continue ;;
    esac
    printf '%s' "$w" | grep -qE '#[0-9a-f]{40}$' || return 0
  done <<EOF
$1
EOF
  return 1
}
# shellcheck disable=SC2194  # case WORD in "$n"*): a unique-prefix match of the typed flag
supply_pip_tls() {  # CLAUSE -> rc 0 when a pip|uv option switches TLS verification off
  local w n v want=false
  for w in $1; do
    if $want; then case "$w" in http://*|*=http://*) return 0 ;; esac; want=false; continue; fi
    case "$w" in
      -i) want=true; continue ;;
      -ihttp://*) return 0 ;;
      --*) ;;
      *) continue ;;
    esac
    n=${w%%=*}; v=""; case "$w" in *=*) v=${w#*=} ;; esac
    case "$n" in --allow-insecure-host) return 0 ;; esac
    if [ "${#n}" -ge 4 ]; then case --trusted-host in "$n"*) return 0 ;; esac; fi
    case "$n" in
      --index|--default-index) ;;
      *) [ "${#n}" -ge 5 ] || continue
         case --index-url in "$n"*) ;; *) case --extra-index-url in "$n"*) ;; *) continue ;; esac ;; esac ;;
    esac
    if [ -n "$v" ]; then case "$v" in http://*|*=http://*) return 0 ;; esac; else want=true; fi
  done
  return 1
}
# shellcheck disable=SC2194  # case WORD in "$n"*): a unique-prefix match of the typed flag
supply_npm_tls() {  # CLAUSE -> rc 0 when an npm|pnpm|yarn flag switches TLS verification off
  local w n v want=""
  for w in $1; do
    if [ -n "$want" ]; then
      case "$want:$w" in ssl:false|ssl:0|ssl:no|reg:http://*) return 0 ;; esac
      want=""; continue
    fi
    case "$w" in --no-strict-ssl) return 0 ;; --*) ;; *) continue ;; esac
    n=${w%%=*}; v=""; case "$w" in *=*) v=${w#*=} ;; esac
    if [ "${#n}" -ge 10 ]; then
      case --strict-ssl in "$n"*)
        if [ -n "$v" ]; then case "$v" in false|0|no) return 0 ;; esac; else want=ssl; fi
        continue ;;
      esac
    fi
    if [ "${#n}" -ge 5 ]; then
      case --registry in "$n"*)
        if [ -n "$v" ]; then case "$v" in http://*) return 0 ;; esac; else want=reg; fi ;;
      esac
    fi
  done
  return 1
}
supply_local_path() {  # PATH -> rc 0 when PATH is relative without .. or inside the hook's cwd
  case "$1" in
    *..*|'~'*|'$'*|'') return 1 ;;
    /*) [ -n "${cwd:-}" ] || return 1
        case "$1" in "${cwd%/}"/*) return 0 ;; esac
        return 1 ;;
  esac
  return 0
}
supply_pip_local() {  # CLAUSE -> rc 0 for --dry-run, or when every --target|--prefix lies inside the project
  local w want=false seen=false
  for w in $1; do
    if $want; then want=false; supply_local_path "$w" || return 1; seen=true; continue; fi
    case "$w" in
      --dry-run) return 0 ;;
      --target=*|--prefix=*) supply_local_path "${w#*=}" || return 1; seen=true ;;
      --target|--prefix|-t) want=true ;;
    esac
  done
  $seen
}
supply_venv_pip() {  # CLAUSE -> rc 0 when the command word is a venv's pip|python (…/bin/pip, not a system path)
  local w
  supply_cmd0 "$1"
  case "$supply_c0" in pip*|python*) ;; *) return 1 ;; esac
  for w in $1; do
    case "${w##*/}" in "$supply_c0") ;; *) continue ;; esac
    case "$w" in
      */bin/"$supply_c0") ;;
      *) return 1 ;;
    esac
    case "$w" in /usr/*|/bin/*|/sbin/*|/opt/homebrew/*|*/.local/bin/*) return 1 ;; esac
    return 0
  done
  return 1
}
supply_clauses=$(printf '%s' "$cmd" | awk -v sq="'" "$supply_lex")
# no text-tool exemption when the line can run text as code
printf '%s' "$supply_n" | grep -qE '\$\(|`|(^|[^[:alnum:]_])eval([[:space:]]|$)|(^|[[:space:]/])(sh|bash|zsh|dash|ksh)([[:space:]]+-[A-Za-z]+)*[[:space:]]+-[A-Za-z]*c([[:space:]]|$)|\|[[:space:]]*(sudo[[:space:]]+)?([^[:space:]]*/)?(sh|bash|zsh|dash|ksh)([[:space:]]|$)' \
  && supply_noexempt=true
supply_venv_active && supply_venv=true
while IFS= read -r supply_line; do
  [ -n "$supply_line" ] || continue
  supply_kind=${supply_line%%"$SUPPLY_TAB"*}; clause=${supply_line#*"$SUPPLY_TAB"}
  if [ "$supply_kind" = T ]; then
    supply_cmd0 "$clause"
    supply_exempt=false
    if ! $supply_noexempt; then
      case "$supply_c0" in
        echo|printf|grep|egrep|fgrep|rg|ag|sed|awk|man|less|cat|head|tail|help) supply_exempt=true ;;
        git) case "$supply_c1" in log|grep|show|commit|diff) supply_exempt=true ;; esac ;;
      esac
    fi
    supply_read=false
    case " $clause " in *' --help '*|*' -h '*) supply_read=true ;; esac
    [ "$supply_c1" = help ] && supply_read=true
    # an activate clause counts for the clauses after it; deactivate cancels it
    case "$supply_c0" in
      source|.) case "$clause" in */bin/activate|*/bin/activate' '*) supply_activated=true; continue ;; esac ;;
      deactivate) supply_activated=false; continue ;;
    esac
    # ---- deny: a cosign.key read (cat is a reader even though it is a text tool; ~/.sigstore keys: prelude)
    case "$clause" in *cosign.key*)
      if supply_reads_key cosign "$clause"; then
        deny "reading a cosign private key (cosign.key) — use keyless signing in the human release step, or pass --key and let cosign read the key itself instead"
      fi
    ;; esac
  fi
  $supply_exempt && continue
  # ---- deny: verification switched off -------------------------------------------------------
  case "$clause" in *[pP][iI][pP]*|*uv*|*UV_*)
    if printf '%s' "$clause" | grep -qE "(^|[[:space:]])((PIP_TRUSTED_HOST|UV_INSECURE_HOST)=[^[:space:]]|(PIP_(EXTRA_)?INDEX_URL|UV_(INDEX_URL|DEFAULT_INDEX|INDEX|EXTRA_INDEX_URL))=[^[:space:]]*http://)" \
       || { printf '%s' "$clause" | grep -qE "${SUPPLY_W}(pip[0-9.]*|uv)[[:space:]]" && supply_pip_tls "$clause"; } \
       || printf '%s' "$clause" | grep -qE "${SUPPLY_W}pip[0-9.]*[[:space:]]+config[[:space:]]([^[:space:]]+[[:space:]]+)*set[[:space:]]+[a-z]+\.(trusted-host([[:space:]]+|=)[^[:space:]]|(extra-)?index-url([[:space:]]+|=)http://)"; then
      deny "pip --trusted-host / uv --allow-insecure-host / an http:// index (flag, pip config, PIP_* or UV_* variable) switches TLS verification off — use the HTTPS index with PIP_CERT or REQUESTS_CA_BUNDLE (uv: SSL_CERT_FILE) pointing at your CA bundle instead, or ask the user"
    fi
  ;; esac
  case "$clause" in *[nN][pP][mM]*|*yarn*|*YARN_*|*NODE_TLS*)
    if printf '%s' "$clause" | grep -qiE "(^|[[:space:]])(npm_config_strict_ssl=(false|0|no)|yarn_enable_strict_ssl=(false|0)|node_tls_reject_unauthorized=0)([[:space:]]|\$)" \
       || { printf '%s' "$clause" | grep -qE "${SUPPLY_W}(npm|pnpm|yarn)[[:space:]]" \
            && { supply_npm_tls "$clause" \
                 || printf '%s' "$clause" | grep -qiE "(^|[[:space:]])((config|c)[[:space:]]+)?set[[:space:]]+(strict-ssl([[:space:]]+|=)(false|0|no)|enablestrictssl([[:space:]]+|=)(false|0)|([^[:space:]=]*:)?registry([[:space:]]+|=)http://|npmregistryserver([[:space:]]+|=)http://|unsafehttpwhitelist([[:space:]]+|=)[^[:space:]])"; }; }; then
      deny "npm/pnpm/yarn strict-ssl false, an http:// registry or NODE_TLS_REJECT_UNAUTHORIZED=0 switches TLS verification off — set cafile or NODE_EXTRA_CA_CERTS to your CA bundle and keep the HTTPS registry instead, or ask the user"
    fi
  ;; esac
  case "$clause" in *[sS][sS][lL]*)
    if printf '%s' "$clause" | grep -qiE "(^|[[:space:]])(GIT_SSL_NO_VERIFY=|GIT_CONFIG_KEY_[0-9]+=http\.([^[:space:]]*\.)?sslverify([[:space:]]|\$))" \
       || { printf '%s' "$clause" | grep -qE "${SUPPLY_W}git[[:space:]]" \
            && { printf '%s' "$clause" | grep -qiE "(^|[[:space:]])(-c[[:space:]]*|--config([[:space:]]+|=))http\.([^[:space:]]*\.)?sslverify=(false|no|off|0)?([[:space:]]|\$)" \
                 || printf '%s' "$clause" | grep -qiE "(^|[[:space:]])--config-env([[:space:]]+|=)http\.([^[:space:]]*\.)?sslverify=" \
                 || printf '%s' "$clause" | grep -qiE "(^|[[:space:]])config[[:space:]]([^[:space:]]+[[:space:]]+)*http\.([^[:space:]]*\.)?sslverify([[:space:]]+|=)(false|no|off|0)([[:space:]]|\$)"; }; }; then
      deny "git http.sslVerify=false / GIT_SSL_NO_VERIFY switches TLS verification off — set http.sslCAInfo to your CA bundle instead, or ask the user"
    fi
  ;; esac
  case "$clause" in *GO*|*-insecure*)
    if printf '%s' "$clause" | grep -qE "(^|[[:space:]])(GOINSECURE=[^[:space:]]|GOFLAGS=[^;&|]*-insecure)" \
       || printf '%s' "$clause" | grep -qE "${SUPPLY_W}go[[:space:]]+get[[:space:]]([^[:space:]]+[[:space:]]+)*-insecure([[:space:]=]|\$)" \
       || printf '%s' "$clause" | grep -qE "${SUPPLY_W}go[[:space:]]+env[[:space:]]([^[:space:]]+[[:space:]]+)*-w[[:space:]]([^[:space:]]+[[:space:]]+)*(GONOSUMDB|GONOSUMCHECK)=[^[:space:]]"; then
      deny "GOINSECURE / -insecure / a persistent GONOSUMDB switches Go module verification off — use GOPRIVATE=<module prefix> for private modules and keep go.sum verification instead"
    fi
  ;; esac
  case "$clause" in *GOSUMDB*)
    if printf '%s' "$clause" | grep -qE "(^|[[:space:]])GOSUMDB=off([[:space:]]|\$)"; then
      deny "GOSUMDB=off switches the Go checksum database off for every module — use GOPRIVATE=<module prefix> or a one-shot GONOSUMDB=<module prefix> for private modules instead"
    fi
  ;; esac
  case "$clause" in *cosign*)
    if printf '%s' "$clause" | grep -qE "${SUPPLY_COSIGN_RE}verify[a-z-]*([[:space:]]|\$)" \
       && printf '%s' "$clause" | grep -qiE "[[:space:]]--(insecure-ignore-tlog|insecure-ignore-sct|insecure-skip-verify|allow-insecure-registry|allow-http-registry|private-infrastructure)(=(true|t|1))?([[:space:]]|\$)"; then
      deny "cosign verify with --insecure-*/--allow-*-registry/--private-infrastructure skips a verification check — run 'supply verify' or 'cosign verify' without the flag instead and report a failure (exit 2) as a finding"
    fi
  ;; esac
  $supply_read && continue
  # ---- ask (deferred): installs into the machine ---------------------------------------------
  case "$clause" in *pip*)
    if printf '%s' "$clause" | grep -qE "$SUPPLY_PIP_RE"; then
      supply_rest=$(supply_specs "$clause" install)
      if printf '%s' "$clause" | grep -qiE "(^|[^[:alnum:]_./-])sudo[[:space:]]|[[:space:]]--(break-system-packages|system)([[:space:]=]|\$)|(^|[[:space:]])UV_SYSTEM_PYTHON=(1|true|yes)([[:space:]]|\$)"; then
        defer "pip install with sudo, --system or --break-system-packages writes into the system Python — run it inside the project instead (uv sync, uv pip install, .venv/bin/pip install)"
      elif printf '%s' "$clause" | grep -qE "[[:space:]]--user([[:space:]]|\$)"; then
        supply_allowed_global "$supply_rest" \
          || defer "pip install --user installs into your home, outside the project — run it inside the project instead (uv sync, uv pip install, .venv/bin/pip install); supply_chain.allow_global_re allow-lists global tools"
      elif $supply_venv || $supply_activated || supply_venv_pip "$clause" || supply_pip_local "$clause" \
           || printf '%s' "$clause" | grep -qE "(^|[^[:alnum:]_./-])(uv|pipx|poetry|pipenv|pdm|hatch)([[:space:]]+(run|exec|-[^[:space:]]+))*[[:space:]]+([^[:space:]]*/)?(pip[0-9.]*|python[0-9.]*|runpip)[[:space:]]"; then
        :
      else
        supply_allowed_global "$supply_rest" \
          || defer "pip install outside a virtual environment installs into the machine — run it inside the project instead (uv sync, uv pip install, .venv/bin/pip install), or start the agent from the activated venv; supply_chain.allow_global_re allow-lists global tools"
      fi
      # unpinned git / URL requirements, inside a venv too
      while IFS= read -r supply_w; do
        case "$supply_w" in
          *git+*://*) supply_git_ref_unpinned "${supply_w#*git+}" && defer "unpinned dependency (git or URL reference without a commit) — pin a commit or a released version instead (pip: git+URL@<sha>, npm: #<sha>, cargo: --rev <sha>); run 'supply pins' to list every unpinned reference" ;;
          http://*.whl|https://*.whl|http://*.tar.gz|https://*.tar.gz|http://*.zip|https://*.zip)
            printf '%s' "$clause" | grep -qE "[[:space:]]--hash([[:space:]=]|\$)" || defer "unpinned dependency (git or URL reference without a commit) — pin a commit or a released version instead (pip: git+URL@<sha>, npm: #<sha>, cargo: --rev <sha>); run 'supply pins' to list every unpinned reference" ;;
        esac
      done <<EOF
$supply_rest
EOF
    fi
  ;; esac
  case "$clause" in *npm*|*yarn*)
    if printf '%s' "$clause" | grep -qE "$SUPPLY_NPM_RE"; then
      supply_rest=$(supply_specs "$clause" 'install|i|in|add')
      if printf '%s' "$clause" | grep -qE "${SUPPLY_W}(npm|pnpm)[[:space:]]" \
         && printf '%s' "$clause" | grep -qE "[[:space:]](-[A-Za-z]*g[A-Za-z]*|--global(=true)?|--location([[:space:]]+|=)global)([[:space:]]|\$)"; then
        supply_allowed_global "$supply_rest" \
          || defer "global npm/pnpm install puts the package into the machine — add it to the project instead (npm i -D, then npx); supply_chain.allow_global_re allow-lists global tools"
      fi
      supply_npm_unpinned "$supply_rest" && defer "unpinned dependency (git or URL reference without a commit) — pin a commit or a released version instead (pip: git+URL@<sha>, npm: #<sha>, cargo: --rev <sha>); run 'supply pins' to list every unpinned reference"
    fi
  ;; esac
  case "$clause" in *yarn*)
    if printf '%s' "$clause" | grep -qE "${SUPPLY_W}yarn[[:space:]]+global[[:space:]]+add([[:space:]]|\$)"; then
      supply_allowed_global "$(supply_specs "$clause" add)" \
        || defer "yarn global add puts the package into the machine — add it to the project instead (yarn add -D, then yarn run); supply_chain.allow_global_re allow-lists global tools"
    fi
  ;; esac
  case "$clause" in *cargo*)
    if printf '%s' "$clause" | grep -qE "${SUPPLY_W}cargo[[:space:]]([^[:space:]]+[[:space:]]+)*install([[:space:]]|\$)" \
       && ! printf '%s' "$clause" | grep -qE "[[:space:]]--list([[:space:]]|\$)" \
       && ! { printf '%s' "$clause" | grep -qE "[[:space:]]--locked([[:space:]]|\$)" \
              && printf '%s' "$clause" | grep -qE "[[:space:]]--vers(ion)?([[:space:]]+|=)[^-[:space:]]"; }; then
      supply_allowed_global "$(supply_specs "$clause" install)" \
        || defer "cargo install without --locked and --version puts an unpinned binary into ~/.cargo/bin — use cargo run or cargo build in the checkout, or pass --locked --version V, instead; supply_chain.allow_global_re allow-lists global tools"
    fi
    if printf '%s' "$clause" | grep -qE "${SUPPLY_W}cargo[[:space:]]([^[:space:]]+[[:space:]]+)*(install|add)[[:space:]]([^[:space:]]+[[:space:]]+)*--git([[:space:]=]|\$)"; then
      if printf '%s' "$clause" | grep -qE "[[:space:]]--branch([[:space:]=]|\$)" \
         || ! printf '%s' "$clause" | grep -qE "[[:space:]]--(rev|tag)([[:space:]=]|\$)"; then
        defer "unpinned dependency (git or URL reference without a commit) — pin a commit or a released version instead (pip: git+URL@<sha>, npm: #<sha>, cargo: --rev <sha>); run 'supply pins' to list every unpinned reference"
      fi
    fi
  ;; esac
  case "$clause" in *go*install*@*)
    if printf '%s' "$clause" | grep -qE "${SUPPLY_W}go[[:space:]]+install[[:space:]]([^[:space:]]+[[:space:]]+)*[^[:space:]]*@(latest|master|main|HEAD)([[:space:]]|\$)"; then
      defer "go install of @latest or a branch installs an unpinned version — pin a version instead (go install example.com/tool@v1.2.3)"
    fi
  ;; esac
  # ---- ask (deferred): checksum database skipped, signing, unverified downloads ---------------
  case "$clause" in *GONOSUM*)
    if printf '%s' "$clause" | grep -qE "(^|[[:space:]])(GONOSUMDB|GONOSUMCHECK)=[^[:space:]]"; then
      defer "GONOSUMDB / GONOSUMCHECK skips go.sum verification against the checksum database — use GOPRIVATE=<module prefix> for private modules instead"
    fi
  ;; esac
  case "$clause" in *cosign*)
    if printf '%s' "$clause" | grep -qE "${SUPPLY_COSIGN_RE}(sign|sign-blob|attest|attest-blob|attach[[:space:]]+(signature|sbom|attestation)|upload|copy|clean|generate-key-pair|import-key-pair)([[:space:]]|\$)"; then
      defer "cosign signing, attesting, attaching, uploading, cleaning and key generation are a human release step — hand the command to the user; 'supply verify' and 'cosign verify' stay available"
    fi
  ;; esac
  case "$clause" in *curl*)
    if printf '%s' "$clause" | grep -qE "${SUPPLY_W}curl[[:space:]]" \
       && printf '%s' "$clause" | grep -qE "(^|[[:space:]])(-[A-Za-z]*k[A-Za-z]*|--insecure)([[:space:]]|\$)"; then
      supply_out=false; supply_v=false
      for supply_w in $clause; do
        if $supply_v; then
          case "$supply_w" in -|/dev/null|/dev/stdout|/dev/stderr) ;; *) supply_out=true ;; esac
          supply_v=false; continue
        fi
        case "$supply_w" in
          --output|'>'|'>>'|1'>'|1'>>'|'&>') supply_v=true ;;
          --output=*) case "${supply_w#*=}" in -|/dev/null|/dev/stdout|/dev/stderr) ;; *) supply_out=true ;; esac ;;
          '>'*|1'>'*|'&>'*) case "${supply_w##*>}" in /dev/null|/dev/stdout|/dev/stderr) ;; *) supply_out=true ;; esac ;;
          -O|--remote-name|--remote-name-all|--output-dir|--output-dir=*) supply_out=true ;;
          --*) ;;
          -*o) supply_v=true ;;                          # -o or a cluster ending in o: the next word is the file
          -*o*) case "${supply_w#*o}" in -|/dev/null) ;; *) supply_out=true ;; esac ;;
          -*O*) supply_out=true ;;
        esac
      done
      # piped into an extractor or a file writer
      printf '%s' "$supply_n" | grep -qE "curl[^;&|]*[[:space:]](-[A-Za-z]*k[A-Za-z]*|--insecure)([[:space:]][^;&|]*)?\|[[:space:]]*(sudo[[:space:]]+)?([^[:space:]]*/)?(tar|bsdtar|unzip|tee|dd|cpio)([[:space:]]|\$)" \
        && supply_out=true
      $supply_out && defer "curl -k/--insecure writes an unverified file — use the HTTPS URL with --cacert <CA bundle> instead"
    fi
  ;; esac
  case "$clause" in *wget*)
    if printf '%s' "$clause" | grep -qE "${SUPPLY_W}wget[[:space:]]([^[:space:]]+[[:space:]]+)*--no-check-certificate([[:space:]]|\$)"; then
      if ! printf '%s' "$clause" | grep -qE "(^|[[:space:]])(-[A-Za-z]*O[[:space:]]*(-|/dev/null)|--output-document([[:space:]]+|=)(-|/dev/null)|--spider)([[:space:]]|\$)" \
         || printf '%s' "$supply_n" | grep -qE "wget[^;&|]*--no-check-certificate[^;&|]*\|[[:space:]]*(sudo[[:space:]]+)?([^[:space:]]*/)?(tar|bsdtar|unzip|tee|dd|cpio)([[:space:]]|\$)"; then
        defer "wget --no-check-certificate writes an unverified file — use the HTTPS URL with --ca-certificate <CA bundle> instead"
      fi
    fi
  ;; esac
done <<EOF
$supply_clauses
EOF
case "$supply_sf" in *f*) ;; *) set +f ;; esac
