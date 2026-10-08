# shellcheck shell=bash
# Guard test rows for bundle merge-queue. Sourced by bundles/core/guard/tests/run.sh after lib.sh
# (helpers: t EXPECTED 'cmd' | tr 'reason-re' 'cmd' | decl LINE... | r EXPECTED 'cmd').

# ---- Merge queue (mq) --------------------------------------------------------------
# reads pass (the permission rules allow them)
t pass  'mq plan --stack feat-x'
t pass  'mq plan 12 13 --json'
t pass  'mq status --stack feat-x --with-main'
t pass  'mq check'
t pass  'mq check --fix -R o/r'
t pass  'mq --help'
t pass  'mq'
t pass  'python3 ~/.claude/skills/mq/scripts/mq.py plan --label merge-queue'
t pass  'grep -n run mq.log'
# the train is human-only
t ask   'mq run --stack feat-x'
t ask   'mq run 12 13 14'
t ask   'mq merge 12'
t ask   'mq enqueue 12'
t ask   'mq train --stack feat-x'
t ask   'sh -c "mq run --stack feat-x"'
t ask   "bash -c 'mq run 12'"
t ask   'echo 12 | xargs mq run'
t ask   'cd ../shop && mq run 12'
t ask   'HARNESS_MQ_POLL_SECONDS=5 mq run 12'
t ask   'python3 ~/.claude/skills/mq/scripts/mq.py run 12'
t ask   '/home/u/.local/bin/mq run 12'
t ask   'mq plan --stack feat-x && mq run --stack feat-x'
t ask   'mq sync --stack feat-x; mq run --stack feat-x'
t ask   '(mq run 12)'
tr 'human-only.*mq plan.*mq run. in their terminal' 'mq run 12'
# sync: label-gated inside the CLI
t allow 'mq sync --stack feat-x'
t allow 'mq sync 110 --skip-ci'
t allow 'mq sync --stack feat-x --with-main --json'
t allow 'HARNESS_MQ_LABEL=x mq sync'
t ask   'mq sync --stack feat-x --include-human'
t ask   'mq sync 110 --include-human --skip-ci'
tr 'agent-\* label.*glab mr update N --label agent-worked' 'mq sync 110 --include-human'
t pass  'cd ../shop && mq sync 110'                         # compound: no allow, the permission rules decide
t deny  'mq sync 110 && git push origin feat-x:main'        # a later deny still wins
t ask   'mq sync 110 && mq run 110'

# ---- repository-level declaration: .harness.toml (principle 8) ----------------------
decl '[owns]' 'domains = ["scm"]'
r pass  'mq run 12'
r pass  'mq sync --include-human'
decl '[owns]' 'components = ["merge-queue/guard.d/65-merge-queue"]'
r pass  'mq run 12'
decl '[owns]' 'domains = ["delivery"]'
r ask   'mq run 12'                                          # section 65 is scm, not delivery
decl
