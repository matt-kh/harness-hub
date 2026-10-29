# shellcheck shell=bash
# Guard test rows for bundle lessons. Sourced by bundles/core/guard/tests/run.sh after lib.sh
# (helpers: t EXPECTED 'cmd' | tr 'reason-re' 'cmd' | decl LINE... | r EXPECTED 'cmd').

# ---- Lessons: human decisions ----------------------------------------------------
# what /retro and the workflow gate run: left to the permission rules
t pass  'harness lessons new --domain base --scope invariant --situation "x" --guide-ref core/rules/00-conventions --sensor-ref core/guard.d/20-credentials --evidence "journal:x"'
t pass  'harness lessons note base-001 --used --helped'
t pass  'harness lessons index'
t pass  'harness lessons journal --ack'
t pass  'harness lessons journal --json'
t pass  'harness lessons list --stale --json'
t pass  'harness lessons review --session s1 --json'
t pass  'harness lessons show base-001'
t pass  'harness lessons stats'
t pass  'harness --config /home/u/h.toml lessons review'
t pass  'harness lessons note base-001 --note "confirm later"'          # a word in a value, not the verb
t pass  'grep -n confirm /home/u/.local/state/harness/lessons/INDEX.md'
t pass  'harness lessons confirmed'                                    # not the verb
# the human decisions ask, however they are wrapped
t ask   'harness lessons confirm base-001'
t ask   'harness lessons retire base-001 --reason "stale"'
t ask   'harness lessons propose base-001 --out /tmp/p --repo octocat/hub'
t ask   'harness lessons propose base-001 --out /tmp/p --mark'
t ask   'harness --config /home/u/h.toml lessons confirm base-001'
t ask   '/home/u/harness-hub/bin/harness lessons confirm base-001'
t ask   'bin/harness lessons retire base-001'
t ask   'python3 -m harness lessons propose base-001 --out /tmp/p'
t ask   "bash -c 'harness lessons confirm base-001'"
t ask   'sh -c "harness lessons retire base-001"'
t ask   'echo base-001 | xargs harness lessons confirm'
t ask   'cd /tmp && harness lessons confirm base-001'
t ask   'HARNESS_CONFIG=/home/u/h.toml harness lessons confirm base-001'
t ask   'harness lessons index && harness lessons confirm base-001'
t ask   '(harness lessons retire base-001)'
tr 'human decision on a lesson.*run it yourself, or ask the user' 'harness lessons confirm base-001'
tr 'human decision on a lesson' 'harness lessons retire base-001'
tr 'human decision on a lesson' 'harness lessons propose base-001 --out /tmp/p'
# a later deny still wins over the deferred ask
t deny  'harness lessons confirm base-001 && git push origin feat-x:main'

# ---- repository-level declaration: .harness.toml (principle 8) ----------------------
decl '[owns]' 'components = ["lessons/guard.d/15-lessons"]'
r pass  'harness lessons confirm base-001'
decl '[owns]' 'domains = ["delivery"]'
r ask   'harness lessons confirm base-001'                             # section 15 is base, not delivery
decl
