# shellcheck shell=bash

# Section 20 (bundle core): credential files and secret-bearing environment output.
# rule: <reader> ~/.kube/* | $KUBECONFIG -> deny : kubeconfig holds cluster credentials; use 'kubectl config get-contexts' or 'k8s contexts' instead
# rule: <reader> tool credential files (~/.config/{jira,glab-cli,gdoc,gh}, agent credential json) -> deny : use the tool's own auth status command
# rule: <reader> .env / .env.* -> deny : secrets; ask the user for the variable names
# rule: <reader> ~/.aws/* | ~/.ssh/* (except *.pub) -> deny : private keys / cloud credentials; use 'ssh-add -l', the *.pub file or 'aws sts get-caller-identity' instead
# rule: <reader> path matching HARNESS_CRED_EXTRA_RE -> deny : org-specific credential paths; run the tool's own auth status command instead
# rule: env | printenv (no command) -> deny : dumps the whole environment; print named non-secret variables instead
# rule: printenv NAME | echo $NAME (NAME looks secret) -> deny : prints a secret; test presence with [ -n "${VAR:+x}" ] instead
# Never yields to a repository (principle 8): these files belong to the developer, not the repository —
# no repo_owns line here, and the engine refuses it too (REPO_NEVER_YIELDS).
# ---- Credentials: shared regexes (also used by 25-k8s-rules for kubeconfig paths) ----
HOME_RE='(~|\$HOME|\$\{HOME\}|/home/[^/ ]+|/root)'
KUBE_FILE_RE='(\$\{?KUBECONFIG\}?|'"$HOME_RE"'/\.kube/)'
TOOL_CRED_RE="$HOME_RE"'/(\.config/(jira|glab-cli|gdoc|gh)|\.claude/(\.credentials|remote-settings)\.json)([^A-Za-z0-9_-]|$)'
CLOUD_CRED_RE="$HOME_RE"'/\.(aws|ssh)([^A-Za-z0-9_-]|$)'
ENV_FILE_RE='(^|[[:space:]/"'"'"'=<])\.env(\.[A-Za-z0-9_.-]+)?([[:space:]"'"'"')]|$)'
CRED_EXTRA_RE="${HARNESS_CRED_EXTRA_RE:-}"                    # org-specific credential paths (regex)
CRED_FILE_RE="($KUBE_FILE_RE|$TOOL_CRED_RE|$CLOUD_CRED_RE|$ENV_FILE_RE${CRED_EXTRA_RE:+|$CRED_EXTRA_RE})"
SECRET_VAR_RE='(TOKEN|SECRET|PASSWORD|PASSWD|API_?KEY|(^|_)PAT(_|$))'   # matched case-insensitively on a variable name
READER_RE='\b(cat|tac|less|more|bat|head|tail|nl|yq|jq|grep|rg|sed|awk|cut|python3?|perl|ruby|node|base64|xxd|od|strings|cp|scp|rsync|tee|vim?|nvim|nano|code|source)\s+[^;&|]*'
# ---- Credentials: file reads and secret env dumps deny ------------------------------
# Clause-wise (split on ; & |, like READER_RE's [^;&|]*). The skills' CLIs (jira, glab, gdoc,
# k8s) open their own credential files internally; invoking them never matches here.
while IFS= read -r rawclause; do
  [ -n "$rawclause" ] || continue
  # spaces doubled so READER_RE's \s+ cannot swallow the boundary ENV_FILE_RE needs ('cat .env')
  clause=$(printf '%s' "$rawclause" | sed 's/[[:space:]]/& /g')
  if printf '%s' "$clause" | grep -qE "${READER_RE}${CRED_FILE_RE}"; then
    printf '%s' "$clause" | grep -qE "${READER_RE}${KUBE_FILE_RE}" && deny "reading kubeconfig (~/.kube/*, \$KUBECONFIG) holds cluster credentials — use 'kubectl config get-contexts' or 'k8s contexts'"
    printf '%s' "$clause" | grep -qE "${READER_RE}${TOOL_CRED_RE}" && deny "reading a credential file (~/.config/jira|glab-cli|gdoc|gh, ~/.claude/.credentials.json, ~/.claude/remote-settings.json) — check auth with 'jira whoami', 'glab auth status', 'gh auth status' or 'gdoc auth status' instead"
    printf '%s' "$clause" | grep -qE "${READER_RE}${ENV_FILE_RE}" && deny "reading a .env / .env.* file (secrets) — ask the user for the variable names or non-secret values you need"
    [ -n "$CRED_EXTRA_RE" ] && printf '%s' "$clause" | grep -qE "${READER_RE}(${CRED_EXTRA_RE})" && deny "reading a credential path configured in HARNESS_CRED_EXTRA_RE — check auth with the tool's own status command instead"
    # ~/.aws, ~/.ssh: public keys (~/.ssh/*.pub) are fine; anything else is a credential
    if printf '%s' "$clause" | grep -oE "${HOME_RE}/\.(aws|ssh)([^[:space:]\"')]*)" | grep -vqE '/\.ssh/[^/]+\.pub$'; then
      deny "reading ~/.aws or ~/.ssh (private keys / cloud credentials) — use 'ssh-add -l', 'cat ~/.ssh/*.pub' or 'aws sts get-caller-identity' instead"
    fi
  fi
  # bare env/printenv dumps the whole environment; printenv NAME / echo $NAME of a secret-named var
  printf '%s' "$clause" | grep -qE '^[[:space:]"'"'"'(`$]*(sudo[[:space:]]+|command[[:space:]]+)?(env|printenv)([[:space:]]+-[A-Za-z0-9-]+)*[[:space:]]*$' \
    && deny "dumping the environment (env/printenv without a command) may print tokens — print specific non-secret variables, or test presence with '[ -n \"\${VAR:+x}\" ]'"
  if printf '%s' "$clause" | grep -qE '^[[:space:]"'"'"'(`$]*(sudo[[:space:]]+)?printenv[[:space:]]'; then
    for v in $(printf '%s' "$clause" | sed -E 's/^.*printenv[[:space:]]+//'); do
      printf '%s' "$v" | grep -qiE "$SECRET_VAR_RE" && deny "printenv $v would print a secret — test presence with '[ -n \"\${$v:+x}\" ]' instead"
    done
  fi
  if printf '%s' "$clause" | grep -qE '(^|[[:space:](`"'"'"'])(echo|printf)([[:space:]]|$)'; then
    for v in $(printf '%s' "$clause" | grep -oE '\$\{?[A-Za-z_][A-Za-z0-9_]*' | tr -d '${'); do
      printf '%s' "$v" | grep -qiE "$SECRET_VAR_RE" && deny "echo/printf of \$$v would print a secret — test presence with '[ -n \"\${$v:+x}\" ]' or print its length with '\${#$v}'"
    done
  fi
done <<EOF
$(printf '%s' "$flat" | tr ';&|' '\n\n\n')
EOF
