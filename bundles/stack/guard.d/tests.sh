# shellcheck shell=bash
# Guard test rows for bundle stack. Sourced by bundles/core/guard/tests/run.sh after lib.sh
# (helpers: t EXPECTED 'cmd' | tr 'reason-re' 'cmd' | decl LINE... | r EXPECTED 'cmd').

# ---- Stack sync (stk) --------------------------------------------------------------
# reads pass (the permission rules allow them)
t pass  'stk plan --stack feat-x'
t pass  'stk plan 12 13 --json'
t pass  'stk status --stack feat-x --with-main'
t pass  'stk check'
t pass  'stk check --fix -R o/r'
t pass  'stk --help'
t pass  'stk'
t pass  'python3 ~/.claude/skills/stk/scripts/stk.py plan --label stack'
t pass  'grep -n sync stk.log'
t pass  'stk plan --stack feat-x --include-human'                 # a read, even with the flag
# sync: label-gated inside the CLI
t allow 'stk sync 110'
t allow 'stk sync --stack feat-x'
t allow 'stk sync --stack feat-x --no-push --json'
t allow 'stk sync 110 --skip-ci'
t allow 'HARNESS_STACK_PUSH=false stk sync --stack feat-x'
t allow '/home/u/.local/bin/stk sync --stack feat-x'
# lifting the label gate asks, however it is wrapped
t ask   'stk sync 110 --include-human'
t ask   'stk sync --stack feat-x --include-human --no-push'
t ask   'sh -c "stk sync 110 --include-human"'
t ask   "bash -c 'stk sync --stack feat-x --include-human'"
t ask   'echo 110 | xargs stk sync --include-human'
t ask   'cd ../shop && stk sync 110 --include-human'
t ask   'HARNESS_STACK_LABEL=x stk sync --include-human'
t ask   'python3 ~/.claude/skills/stk/scripts/stk.py sync --stack feat-x --include-human'
t ask   'stk plan --stack feat-x && stk sync --stack feat-x --include-human'
t ask   '(stk sync 110 --include-human)'
tr 'agent-\* label.*glab mr update N --label agent-worked' 'stk sync 110 --include-human'
# compound commands get no allow; a later deny still wins
t pass  'cd ../shop && stk sync 110'                              # compound: the permission rules decide
t pass  'stk sync 110; echo done'
t deny  'stk sync 110 && git push origin feat-x:main'
t deny  'stk sync 110 --include-human && git push origin feat-x:main'

# ---- repository-level declaration: .harness.toml (principle 8) ----------------------
decl '[owns]' 'domains = ["scm"]'
r pass  'stk sync 110 --include-human'
r pass  'stk sync 110'
decl '[owns]' 'components = ["stack/guard.d/65-stack"]'
r pass  'stk sync --stack feat-x --include-human'
decl '[owns]' 'domains = ["delivery"]'
r ask   'stk sync 110 --include-human'                             # section 65 is scm, not delivery
r allow 'stk sync 110'
decl
