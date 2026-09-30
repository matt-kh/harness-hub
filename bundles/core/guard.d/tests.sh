# shellcheck shell=bash
# Guard test rows for bundle core. Sourced by bundles/core/guard/tests/run.sh after lib.sh
# (helpers: t EXPECTED 'cmd' | tc EXPECTED CWD 'cmd' | tr 'reason-re' 'cmd' | g EXPECTED 'cmd' in a real dir).

# stacked delivery: sub pushes from the main checkout are intended; from a sub worktree → ask
t  pass  'git push -u origin feat-x-sub-01-schema'
tc ask   '/home/u/dev/shop_feat-x-sub-01-schema' 'git push -u origin feat-x-sub-01-schema'
tc pass  '/home/u/dev/shop' 'git push -u origin feat-x-sub-01-schema'
t  ask   'cd ../shop_feat-x-sub-01-schema && git push -u origin feat-x-sub-01-schema'
t  ask   'git push --all origin'
t  ask   'git push --force-with-lease origin feat-x-sub-02-api'
t  pass  'git commit --allow-empty -m "stack root: feat-x"'
# ---- credential files: reads deny, the skills' CLIs and metadata-only commands pass ----
t deny  'cat ~/.config/jira'
t deny  'cat /home/u/.config/jira'
t deny  'head -1 $HOME/.config/jira'
t deny  'grep -i token ~/.config/glab-cli/config.yml'
t deny  'yq .hosts "${HOME}/.config/glab-cli/config.yml"'
t deny  'python3 -c "print(open(\"/home/u/.config/gdoc/token.json\").read())"'
t deny  'jq . ~/.config/gdoc/client_secret.json'
t deny  'cat ~/.claude/.credentials.json'
t deny  'jq .env /home/u/.claude/remote-settings.json'
t deny  'cat ~/.aws/credentials'
t deny  'cd /tmp && cat $HOME/.aws/config'
t deny  'cat ~/.ssh/id_ed25519'
t deny  'cp ~/.ssh/id_rsa /tmp/k'
t deny  'cat ~/.ssh/id_rsa.pub ~/.ssh/id_rsa'
t deny  'cat .env'
t deny  'source ./.env && ./run.sh'
t deny  'grep DB_ ~/dev/shop/.env.production'
t deny  'cat "apps/api/.env.local"'
t deny  'bash -c "cat ~/.config/jira"'
t pass  'cat ~/.ssh/id_ed25519.pub'
t pass  'ssh-add -l'
t pass  'ls -la ~/.ssh/ ~/.config/gdoc/'
t pass  'cat ~/.config/jira-notes.md'
t pass  'source .venv/bin/activate'
t pass  'cat docs/dotenv.md'
t pass  'jira whoami'
t pass  'glab auth status'
t pass  'gdoc auth status'
t pass  'jira get LBL-1 | jq .labels'
t pass  'cat ~/.claude/settings.json | jq .permissions'
t deny  'cp .env.example .env.bak'
tr 'jira whoami'      'cat ~/.config/jira'
tr 'gdoc auth status' 'cat ~/.config/gdoc/token.json'
tr 'ssh-add -l'       'cat ~/.ssh/id_rsa'
# ---- secret env dumps -------------------------------------------------------------
t deny  'env'
t deny  'env | grep -i token'
t deny  'printenv'
t deny  'printenv | sort'
t deny  'printenv GITLAB_TOKEN'
t deny  'printenv HOME JIRA_PAT'
t deny  'echo $JIRA_TOKEN'
t deny  'echo "token=${GITLAB_TOKEN}"'
t deny  'printf "%s\n" "$aws_secret_access_key"'
t deny  'cd /tmp && echo $DB_PASSWORD'
t deny  'echo $OPENAI_API_KEY'
t pass  'env VAR=1 make test'
t pass  'env -u FOO python3 x.py'
t pass  'printenv PATH HOME'
t pass  'echo $PATH'
t pass  'echo "${#GITLAB_TOKEN}"'
t pass  'echo hello && ls'
t pass  '[ -n "${GITLAB_TOKEN:+x}" ] && echo set'
# ---- default-branch push: deny (MR-based workflow) --------------------------------
t deny  'git push origin master'
t deny  'git push -u origin main'
t deny  'git push origin HEAD:main'
t deny  'git push origin +HEAD:refs/heads/master'
t deny  'git push origin :master'
t deny  'cd ~/dev/shop && git push origin feat-x master'
t deny  'git -C ~/dev/shop push origin master'
t pass  'git push origin feat-x'
t pass  'git push -u origin HEAD:feat-x'
t pass  'git push -u origin "$BR"'
t pass  'git push'                                       # not a repo (stub: no branch) → no decision
GIT_STUB_BRANCH=master t deny  'git push'
GIT_STUB_BRANCH=main   t deny  'git push origin'
GIT_STUB_BRANCH=master t deny  'git push -u origin HEAD'
GIT_STUB_BRANCH=master t deny  'git -C ../other push'
GIT_STUB_BRANCH=feat-x t pass  'git push'
GIT_STUB_BRANCH=feat-x t pass  'git push -u origin HEAD'
GIT_STUB_BRANCH=master t pass  'git push origin feat-x'   # explicit feature refspec wins over the current branch
GIT_STUB_BRANCH=master t ask   'git push --all origin'
GIT_STUB_BRANCH=master t pass  'git push --tags'
t ask   'git push --force origin feat-x'
t ask   'git push -f origin feat-x'
t deny  'git push --force origin master'
WORK_TICKET_ALLOW_DEFAULT_PUSH_RE='^/home/u/dev/shop$' t ask  'git push origin master'
WORK_TICKET_ALLOW_DEFAULT_PUSH_RE='^/home/u/dev/shop$' GIT_STUB_BRANCH=main t ask 'git push'
WORK_TICKET_ALLOW_DEFAULT_PUSH_RE='^/home/u/personal/' GIT_STUB_TOPLEVEL=/home/u/personal/dots t ask 'git push origin master'
WORK_TICKET_ALLOW_DEFAULT_PUSH_RE='^/home/u/personal/' t deny 'git push origin master'
tr 'MR-based workflow — push a feature branch and open an MR' 'git push origin master'
WORK_TICKET_KEY_IN_BRANCH=1    t pass  'git push -u origin LBL-1-feature'
# ---- fail closed without jq: PATH holds only `cat` (all the hook needs before its jq check) ----
nojq=$(mktemp -d); ln -s "$(command -v cat)" "$nojq/cat"
out=$(printf '%s' '{"cwd":"/tmp","tool_input":{"command":"ls"}}' | PATH="$nojq" "$(command -v bash)" "$H")
rm -rf "$nojq"
if [ "$(jq -r '.hookSpecificOutput.permissionDecision' <<<"$out" 2>/dev/null)" = deny ] \
   && jq -r '.hookSpecificOutput.permissionDecisionReason' <<<"$out" | grep -q 'jq not installed'; then
  pass=$((pass+1)); echo "PASS deny  | jq missing → fail closed"
else fail=$((fail+1)); printf 'FAIL jq missing → want deny JSON, got: %s\n' "$out"; fi
# ---- fail closed on malformed hook input; valid JSON without a command passes ----------
for _in in 'not json' '{"tool_input":' '"just a string"'; do
  out=$(printf '%s' "$_in" | bash "$H")
  if [ "$(jq -r '.hookSpecificOutput.permissionDecision' <<<"$out" 2>/dev/null)" = deny ] \
     && jq -r '.hookSpecificOutput.permissionDecisionReason' <<<"$out" | grep -q 'malformed hook input'; then
    pass=$((pass+1)); echo "PASS deny  | malformed input: $_in"
  else fail=$((fail+1)); printf 'FAIL malformed input %s → want deny JSON, got: %s\n' "$_in" "$out"; fi
done
for _in in '{}' '{"tool_input":{}}' ''; do
  out=$(printf '%s' "$_in" | bash "$H"); rc=$?
  if [ "$rc" = 0 ] && [ -z "$out" ]; then pass=$((pass+1)); echo "PASS pass  | no command: '$_in'"
  else fail=$((fail+1)); printf 'FAIL no command %s → want silent pass, got rc=%s %s\n' "$_in" "$rc" "$out"; fi
done
# ---- harness parameters: env overrides and the rendered guard.env ------------------
WORK_TICKET_BASE_BRANCH_RE='^(trunk)$' t deny 'git push origin trunk'
WORK_TICKET_BASE_BRANCH_RE='^(trunk)$' t pass 'git push origin master'
t pass  'cat /etc/org-vault/token'
HARNESS_CRED_EXTRA_RE='/etc/org-vault/' t deny 'cat /etc/org-vault/token'
HARNESS_CRED_EXTRA_RE='/etc/org-vault/' t pass 'ls /etc/org-vault/'
HARNESS_CRED_EXTRA_RE='/etc/org-vault/' tr 'HARNESS_CRED_EXTRA_RE' 'grep x /etc/org-vault/token'
# guard.env is parsed at start (never sourced); a variable already in the environment wins
genv=$(mktemp); printf '%s\n' '# rendered by harness' "WORK_TICKET_BASE_BRANCH_RE='^(trunk)\$'" 'HARNESS_CRED_EXTRA_RE="/etc/org-vault/"' > "$genv"
HARNESS_GUARD_ENV=$genv t deny 'git push origin trunk'
HARNESS_GUARD_ENV=$genv t pass 'git push origin master'
HARNESS_GUARD_ENV=$genv t deny 'cat /etc/org-vault/token'
HARNESS_GUARD_ENV=$genv WORK_TICKET_BASE_BRANCH_RE='^(master|main)$' t deny 'git push origin master'
HARNESS_GUARD_ENV=$genv WORK_TICKET_BASE_BRANCH_RE='^(master|main)$' t pass 'git push origin trunk'
rm -f "$genv"
