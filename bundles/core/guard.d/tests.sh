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
# ---- repository-level declaration: .harness.toml (principle 8) ----------------------
# owned by id: the whole section is skipped (pass), from the root and from a subdirectory
decl '[owns]' 'components = ["core/guard.d/30-git"]'
r  pass  'git push origin master'
# shellcheck disable=SC2154  # rpd: the fixture repository, defined in guard/tests/lib.sh
tc pass  "$rpd/sub" 'git push origin master'
r  pass  'git push --force origin feat-x'                     # the section's asks yield too
GIT_STUB_BRANCH=master r pass 'git push'
r  deny  'cat ~/.ssh/id_rsa'                                  # credentials never yield
r  deny  'cat ~/.config/gh/hosts.yml'
# owned by domain
decl '[owns]' 'domains = ["scm"]'
r  pass  'git push origin master'
decl '[owns]' 'domains = ["tracker"]'
r  deny  'git push origin master'                             # another domain: unchanged
# bypass: owning the credential section, the permission list or domain base changes nothing
decl '[owns]' 'domains = ["base"]' 'components = ["core/guard.d/20-credentials", "core/permissions"]'
r  deny  'cat ~/.ssh/id_rsa'
r  deny  'cat ~/.config/jira'
r  deny  'cat .env'
r  deny  'printenv'
r  deny  'git push origin master'                             # base is not scm
decl '[owns]' 'components = ["core/guard.d/20-credentials", "core/guard.d/30-git"]'
r  deny  'cat ~/.aws/credentials'
r  pass  'git push origin master'
# overrides: allow-listed names from the file; the real environment wins; the file beats guard.env
decl '[overrides]' "WORK_TICKET_ALLOW_DEFAULT_PUSH_RE = \"^$rpd\$\""
r  ask   'git push origin master'
WORK_TICKET_ALLOW_DEFAULT_PUSH_RE='^/nowhere$' r deny 'git push origin master'
decl '[overrides]' "WORK_TICKET_ALLOW_DEFAULT_PUSH_RE = '^$rpd\$'"     # literal string form
r  ask   'git push origin master'
decl '[overrides]' 'WORK_TICKET_BASE_BRANCH_RE = "^(trunk)$"'
r  deny  'git push origin trunk'
r  pass  'git push origin master'
genv=$(mktemp); printf '%s\n' "WORK_TICKET_BASE_BRANCH_RE='^(release)\$'" > "$genv"
decl '[overrides]' 'WORK_TICKET_BASE_BRANCH_RE = "^(master)$"'
HARNESS_GUARD_ENV=$genv r deny 'git push origin master'      # .harness.toml beats guard.env
HARNESS_GUARD_ENV=$genv r pass 'git push origin release'
HARNESS_GUARD_ENV=$genv WORK_TICKET_BASE_BRANCH_RE='^(release)$' r deny 'git push origin release'   # env beats the file
HARNESS_GUARD_ENV=$genv WORK_TICKET_BASE_BRANCH_RE='^(release)$' r pass 'git push origin master'
rm -f "$genv"
decl '[overrides]' "WORK_TICKET_ALLOW_DEFAULT_PUSH_RE = \"^$rpd\$\""
WORK_TICKET_ALLOW_DEFAULT_PUSH_RE='' r deny 'git push origin master'   # set but empty in the environment still wins
# bypass: deny-listed and unknown names are ignored. The test lib exports the client paths
# (GUARD_GIT …) and the environment wins anyway, so these rows assert the engine's stderr note.
decl '[overrides]' 'HARNESS_CRED_EXTRA_RE = ""'
HARNESS_CRED_EXTRA_RE='/etc/org-vault/' tn deny 'HARNESS_CRED_EXTRA_RE is settable only from your own environment' "$rpd" 'cat /etc/org-vault/token'
decl '[overrides]' 'HARNESS_CRED_EXTRA_RE = "^$"' 'HARNESS_GUARD_ENV = "/dev/null"'
genv=$(mktemp); printf '%s\n' "HARNESS_CRED_EXTRA_RE='/etc/org-vault/'" > "$genv"
HARNESS_GUARD_ENV=$genv r deny 'cat /etc/org-vault/token'    # the file cannot replace a guard.env credential regex
HARNESS_GUARD_ENV=$genv tn deny 'HARNESS_GUARD_ENV is settable only from your own environment' "$rpd" 'cat /etc/org-vault/token'
rm -f "$genv"
decl '[overrides]' 'GUARD_GIT = "/bin/true"'
GIT_STUB_BRANCH=master tn deny 'GUARD_GIT is settable only from your own environment' "$rpd" 'git push'
decl '[overrides]' 'WORK_TICKET_FOO_PY = "/tmp/x"'                     # pattern: *_PY are client paths
tn deny 'WORK_TICKET_FOO_PY is settable only from your own environment' "$rpd" 'git push origin master'
decl '[overrides]' 'WORK_TICKET_CRED_RE = "x"'                         # pattern: *CRED*
tn deny 'WORK_TICKET_CRED_RE is settable only from your own environment' "$rpd" 'git push origin master'
decl '[overrides]' 'K8S_PROD_RE = "^$"'                                # only WORK_TICKET_* names
tn deny 'K8S_PROD_RE is not a repo override \(only allow-listed WORK_TICKET_' "$rpd" 'git push origin master'
decl '[overrides]' 'WORK_TICKET_LABEL = "x"'                           # WORK_TICKET_* but not allow-listed
tn deny 'WORK_TICKET_LABEL is not a repo override' "$rpd" 'git push origin master'
decl '[overrides]' 'BASH_ENV = "/tmp/x"' 'PATH = "/tmp"' 'WORK_TICKET_LABEL = "x"'
r  deny  'git push origin master'
# duplicate keys: the first one counts, the repeat is ignored with a note; [owns] takes arrays only
decl '[owns]' 'components = ["core/guard.d/30-git"]' 'components = []'
tn pass  'duplicate key components in \[owns\]; the first one counts' "$rpd" 'git push origin master'
decl '[owns]' 'components = []' 'components = ["core/guard.d/30-git"]'
r  deny  'git push origin master'
decl '[owns]' 'domains = "scm"'
tn deny  'domains must be a one-line array' "$rpd" 'git push origin master'
decl '[overrides]' "WORK_TICKET_ALLOW_DEFAULT_PUSH_RE = \"^$rpd\$\"" 'WORK_TICKET_ALLOW_DEFAULT_PUSH_RE = "^/nowhere$"'
r  ask   'git push origin master'
# notes are capped: five, then a count
decl '[owns]' 'a' 'b' 'c' 'd' 'e' 'f' 'g'
tn deny  '2 more lines ignored' "$rpd" 'git push origin master'
# ---- shell writes to .harness.toml ask, also when the repository owns 30-git (never-yields prelude)
t  ask   'printf "[owns]\n" > .harness.toml'
t  ask   'cd /home/u/dev/shop && printf x > .harness.toml'
t  ask   'echo x >> sub/.harness.toml'
t  ask   'echo x 2>/dev/null >"/home/u/dev/shop/.harness.toml"'
t  ask   'tee .harness.toml < /tmp/decl'
t  ask   'printf x | tee -a /home/u/dev/shop/.harness.toml >/dev/null'
t  ask   'cp /tmp/decl .harness.toml'
t  ask   'mv /tmp/decl ./.harness.toml'
t  ask   "sed -i 's/a/b/' .harness.toml"
t  ask   'perl -pi -e s/a/b/ .harness.toml'
t  ask   'dd if=/tmp/decl of=.harness.toml'
t  ask   'harness repo init --write'
t  ask   'bin/harness repo init /home/u/dev/shop --write'
t  ask   'sh -c "echo x > .harness.toml"'
t  ask   "bash -c 'printf x>.harness.toml'"
t  deny  'printf x > .harness.toml && git push origin master'        # a later deny still wins
t  pass  'cat .harness.toml'
t  pass  'harness repo'
t  pass  'harness repo init'
t  pass  'cp .harness.toml /tmp/decl.bak'
t  pass  'grep owns .harness.toml > /tmp/out'
t  pass  'echo x > .harness.toml.bak'
t  pass  'diff .harness.toml /tmp/decl'
decl '[owns]' 'domains = ["scm"]' 'components = ["core/guard.d/30-git"]'
r  ask   'printf x > .harness.toml'
r  ask   'cd sub && tee ../.harness.toml < /tmp/decl'
r  pass  'git push origin master'
# fail open: malformed lines, inline comments, oversized file, no .git above -> unchanged decisions
decl 'owns = [' '"core/guard.d/30-git"' ']'
r  deny  'git push origin master'
decl '[owns]' 'components = ["core/guard.d/30-git"] # trailing comment'
r  deny  'git push origin master'
decl '[owns]' 'components = [core/guard.d/30-git]'
r  deny  'git push origin master'
decl '[owns' 'components = ["core/guard.d/30-git"]'
r  deny  'git push origin master'
decl '[overrides]' "WORK_TICKET_ALLOW_DEFAULT_PUSH_RE = \"^$rpd\$\" # mine"
r  deny  'git push origin master'
decl '[overrides]' 'WORK_TICKET_ALLOW_DEFAULT_PUSH_RE = "a\\.b"'          # escapes are not in the subset
r  deny  'git push origin master'
decl '[owns]' 'components = ["core/guard.d/30-git"]'
awk 'BEGIN { for (i = 0; i < 398; i++) print "# padding" }' >> "$rpd/.harness.toml"
r  pass  'git push origin master'                             # exactly 400 lines: still parsed
printf '%s\n' '# line 401' >> "$rpd/.harness.toml"
tn deny  'ignored \(more than 400 lines' "$rpd" 'git push origin master'   # 401 lines: ignored as a whole
decl '[owns]' 'components = ["core/guard.d/30-git"]'
awk 'BEGIN { for (i = 0; i < 200; i++) print "# padding line of the oversized declaration ......................................" }' >> "$rpd/.harness.toml"
tn deny  'ignored \(larger than 16 KiB' "$rpd" 'git push origin master'    # 17 KiB in 202 lines: ignored as a whole
decl '[owns]' 'components = ["core/guard.d/30-git"]'
printf '{"tool_input":{"command":"git push origin master"}}' > "$rpd/in.json"
nocwd=$(cd "$rpd" && bash "$H" < in.json | jq -r '.hookSpecificOutput.permissionDecision // "pass"')
rm -f "$rpd/in.json"
if [ "$nocwd" = deny ]; then pass=$((pass+1)); echo "PASS deny  | no cwd in the hook input: no lookup from \$PWD"
else fail=$((fail+1)); echo "FAIL want=deny got=$nocwd | no cwd in the hook input: no lookup from \$PWD"; fi
nogit=$(mktemp -d); decl '[owns]' 'components = ["core/guard.d/30-git"]'; cp "$rpd/.harness.toml" "$nogit/"
tc deny "$nogit" 'git push origin master'                     # no .git above: not a repository
rm -rf "$nogit"
wt=$(mktemp -d); printf 'gitdir: /elsewhere/.git/worktrees/x\n' > "$wt/.git"; cp "$rpd/.harness.toml" "$wt/"
tc pass "$wt" 'git push origin master'                        # a linked worktree's .git file counts
rm -rf "$wt"
tc deny 'relative/dir' 'git push origin master'               # relative cwd: no lookup
decl
