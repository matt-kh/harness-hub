# shellcheck shell=bash
# Guard test rows for bundle jira. Sourced by bundles/core/guard/tests/run.sh after lib.sh
# (helpers: t EXPECTED 'cmd' | tc EXPECTED CWD 'cmd' | tr 'reason-re' 'cmd' | g EXPECTED 'cmd' in a real dir).

# reads / passthrough
t pass  'jira get LBL-1'
t pass  'jira links LBL-1'
t pass  'jira api /rest/api/2/issueLinkType'
t pass  'git commit -m "LBL-1 fix parser"'
t pass  'git push -u origin LBL-1-feature'
t pass  'glab mr view 100 -F json'
t pass  'glab mr list --search LBL-1'
# Jira write gate: existing tickets not yet agent-tagged → ask; tagged → allow
t ask   'jira comment HUM-1 "hi"'
t allow 'jira comment LBL-1 "hi"'
t allow 'jira comment LBL-1 a && jira comment LBL-2 b'
t ask   'jira comment LBL-1 a && jira comment HUM-1 b'
t ask   'jira comment "$KEY" x'
t ask   'jira comment ERR-1 x'
t allow 'jira comment DRF-1 x'                                          # any agent-* label → promptless
t ask   'jira upload HUM-1 /tmp/x.png'
t allow 'jira upload LBL-1 /tmp/x.png'
t allow 'jira set LBL-1 labels ["x"]'
t ask   'jira set HUM-1 labels ["x"]'
t ask   'cd ~/dev/app && python scripts/jira.py comment HUM-1 "x"'
# Jira labelling: agent-* labels are free; other labels follow the gate
t allow 'jira label HUM-1 add agent-worked'
t allow 'jira label DRF-1 add agent-worked'
t allow 'jira label HUM-1 add agent-worked agent-created'
t allow 'jira label HUM-1 add agent-worked && jira label HUM-2 add agent-worked'
t ask   'jira label HUM-1 add ready'
t allow 'jira label LBL-1 add ready'
t ask   'jira label HUM-1 remove agent-worked'
t allow 'jira label CRE-1 remove agent-worked'
t allow 'jira label LBL-1 remove ready'
t ask   'jira label HUM-1 add agent-worked && jira label HUM-2 add ready'
t ask   'jira label "$KEY" add agent-worked'
# Jira create: provenance label → allow; missing → deny
t deny  'jira create PROJ Task "x"'
t allow "jira create PROJ CR \"x\" --field labels='[\"agent-drafted\"]' --field customfield_20103='{\"value\":\"Bug Fix\"}'"
t allow "jira create PROJ \"SW Task\" \"x\" --field labels='[\"agent-drafted\"]' --field customfield_20205='{\"value\":\"Software\"}' --field customfield_20000=\"body\""
t allow "jira create PROJ Task \"x\" --field labels='[\"agent-created\",\"agent-worked\"]'"
t deny  "jira create PROJ Task \"x\" --field labels='[\"ready\"]'"
t deny  "jira create PROJ Task \"x\" --field labels='[\"agent-drafted\"]' && jira create PROJ Task \"y\""
t allow "jira create PROJ Task \"x\" --field labels='[\"agent-drafted\"]' && jira create PROJ Task \"y\" --field labels='[\"agent-drafted\"]'"
t allow "JIRA_DRY_RUN=1 jira create PROJ CR \"x\" --field labels='[\"agent-drafted\"]'"
t deny  'jira create PROJ Task "x" --field issuelinks=[]'
# create --link
t allow "jira create PROJ Task \"[LBL-1] x\" --field labels='[\"agent-created\",\"agent-worked\"]' --link \"Issue split:LBL-1\""
t deny  "jira create PROJ Task \"[HUM-1] x\" --field labels='[\"agent-created\",\"agent-worked\"]' --link \"Issue split:HUM-1\""
t deny  "jira create PROJ Task \"[LBL-1] x\" --field labels='[\"agent-worked\"]' --link \"Issue split:LBL-1\""
t deny  "jira create PROJ Task \"[LBL-1] x\" --link \"Issue split:LBL-1\""
# state: human-written tickets deny; agent-labelled tickets promptless
t deny  'jira transition HUM-1 "Start Work"'
t allow 'jira transition LBL-1 "Start Work"'
t allow 'jira transition DRF-1 "Start Work"'
t allow 'jira transition CRE-1 "Start Work"'
t allow 'jira transition CRE-1 "In Progress" && jira transition CRE-2 "In Progress"'
t deny  'jira transition CRE-1 x && jira transition HUM-1 x'
t deny  'jira transition ERR-1 x'
# links: between agent-worked tickets → allow; anything else → deny
t allow 'jira link LBL-1 "Issue split" LBL-2'
t allow 'jira link CRE-1 Blocks CRE-2'
t allow 'jira link DRF-1 Relates LBL-1'
t deny  'jira link LBL-1 "Issue split" HUM-1'
t deny  'jira link HUM-1 Relates LBL-1'
t deny  'jira link LBL-1 "Finish-to-Start Dependency" LBL-2'
t deny  'jira link LBL-1 Relates LBL-1'
t deny  'jira link "$A" Relates LBL-2'
t ask   'jira link LBL-1 Relates ERR-1'
t deny  'jira set LBL-1 issuelinks []'
# ---- repo overrides (repo .claude/settings.json env) -------------------------------
t deny  'jira transition HUM-1 "In Progress"'
WORK_TICKET_ALLOW_TRANSITION=1 t ask   'jira transition HUM-1 "In Progress"'
WORK_TICKET_ALLOW_TRANSITION=1 t allow 'jira transition LBL-1 "In Progress"'
WORK_TICKET_ALLOW_TRANSITION=1 t deny  'jira transition "$KEY" "In Progress"'
WORK_TICKET_ALLOW_TRANSITION=0 t deny  'jira transition HUM-1 "In Progress"'
# ---- harness parameters: link types (jira.link_types) and the client path default
HARNESS_JIRA_LINK_TYPES_RE='^(relates)$'    t deny  'jira link LBL-1 Blocks LBL-2'
HARNESS_JIRA_LINK_TYPES_RE='^(relates)$'    t allow 'jira link LBL-1 Relates LBL-2'
HARNESS_JIRA_LINK_TYPES_RE='^(depends on)$' t allow 'jira link LBL-1 "Depends on" LBL-2'
HARNESS_JIRA_LINK_TYPES_RE='^(relates)$'    tr 'allowed: \^\(relates\)\$' 'jira link LBL-1 Blocks LBL-2'
# without WORK_TICKET_JIRA_PY the guard uses <hooks dir>/../skills/jira/scripts/jira.py
lay=$(mktemp -d); mkdir -p "$lay/hooks" "$lay/skills/jira/scripts"
cp "$H" "$lay/hooks/guard-bash.sh"; cp "$STUBS/jira-stub.py" "$lay/skills/jira/scripts/jira.py"
WORK_TICKET_JIRA_PY= H="$lay/hooks/guard-bash.sh" t allow 'jira comment LBL-1 x'
WORK_TICKET_JIRA_PY= H="$lay/hooks/guard-bash.sh" t ask   'jira comment HUM-1 x'
rm -f "$lay/skills/jira/scripts/jira.py"
WORK_TICKET_JIRA_PY= H="$lay/hooks/guard-bash.sh" t ask   'jira comment LBL-1 x'   # client missing -> cannot verify -> ask
rm -rf "$lay"
# link types as a rendered list (HARNESS_JIRA_LINK_TYPES from jira.link_types); the regex form wins
HARNESS_JIRA_LINK_TYPES='Relates, Depends (on)' t allow 'jira link LBL-1 "Depends (on)" LBL-2'
HARNESS_JIRA_LINK_TYPES='Relates, Depends (on)' t deny  'jira link LBL-1 Blocks LBL-2'
HARNESS_JIRA_LINK_TYPES='Relates' HARNESS_JIRA_LINK_TYPES_RE='^(blocks)$' t allow 'jira link LBL-1 Blocks LBL-2'
