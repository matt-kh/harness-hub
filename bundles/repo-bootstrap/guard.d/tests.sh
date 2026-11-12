# shellcheck shell=bash
# Guard test rows for bundle repo-bootstrap. Sourced by bundles/core/guard/tests/run.sh after lib.sh
# (helpers: t EXPECTED 'cmd' | tr 'reason-re' 'cmd' | decl LINE... | r EXPECTED 'cmd').

# ---- Repository bootstrap (repoboot) -------------------------------------------------
# intake, plans, checks and renders pass (the permission rules allow them)
t pass  'repoboot questions --dir /home/u/dev/shop'
t pass  'repoboot questions --round 2 --json'
t pass  'repoboot answer repo.host=github repo.owner=o --accept-defaults'
t pass  'repoboot answer --infer --dir .'
t pass  'repoboot plan --dir /home/u/dev/shop --text'
t pass  'repoboot render --dir /home/u/dev/shop'
t pass  'repoboot render --force'
t pass  'repoboot check --fix'
t pass  'repoboot'
t pass  'repoboot --help'
t pass  'python3 ~/.claude/skills/bootstrap-repo/scripts/repoboot.py plan'
t pass  'grep -n apply repoboot.log'
t pass  'repoboot answer architecture.notes=apply'                  # the verb decides, not a word in a value
# apply asks, however it is wrapped
t ask   'repoboot apply'
t ask   'repoboot apply --dir /home/u/dev/shop --force'
t ask   '/home/u/.local/bin/repoboot apply'
t ask   'python3 ~/.claude/skills/bootstrap-repo/scripts/repoboot.py apply --json'
t ask   'HARNESS_REPO_BOOTSTRAP_PACK_DIRS=/home/u/packs repoboot apply'
t ask   'sh -c "repoboot apply --dir ."'
t ask   "bash -c 'repoboot apply'"
t ask   'cd /home/u/dev/shop && repoboot apply'
t ask   'repoboot plan && repoboot apply'
t ask   'echo . | xargs repoboot apply --dir'
t ask   '(repoboot apply)'
tr 'show the user `repoboot plan` first' 'repoboot apply'
# a later deny still wins
t deny  'repoboot apply && git push origin feat-x:main'

# ---- repository-level declaration: .harness.toml (principle 8) ----------------------
decl '[owns]' 'domains = ["scm"]'
r pass  'repoboot apply'
decl '[owns]' 'components = ["repo-bootstrap/guard.d/67-repo-bootstrap"]'
r pass  'repoboot apply --dir .'
decl '[owns]' 'domains = ["delivery"]'
r ask   'repoboot apply'                                            # section 67 is scm, not delivery
decl
