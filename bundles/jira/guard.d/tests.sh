# shellcheck shell=bash
# Guard test rows for bundle jira. Sourced by bundles/core/guard/tests/run.sh after lib.sh
# (helpers: t EXPECTED 'cmd' | tc EXPECTED CWD 'cmd' | tr 'reason-re' 'cmd' | g EXPECTED 'cmd' in a real dir).

# reads / passthrough
t pass  'jira get LBL-1'
t pass  'jira links LBL-1'
t pass  'jira api /rest/api/2/issueLinkType'
WORK_TICKET_KEY_IN_BRANCH=1 t pass 'git commit -m "LBL-1 fix parser"'   # key-prefixed subjects ask in section 75 otherwise
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
# state: a human-written ticket's transition is a human decision (main thread asks); agent-labelled
# tickets promptless; a ticket that cannot be checked (no literal key, failed lookup) denies
t ask   'jira transition HUM-1 "Start Work"'                    # #67: was deny
t allow 'jira transition LBL-1 "Start Work"'
t allow 'jira transition DRF-1 "Start Work"'
t allow 'jira transition CRE-1 "Start Work"'
t allow 'jira transition CRE-1 "In Progress" && jira transition CRE-2 "In Progress"'
t ask   'jira transition CRE-1 x && jira transition HUM-1 x'   # #67: was deny
t deny  'jira transition ERR-1 x'
t deny  'jira transition "$KEY" Done'
t deny  'jira transition'
t deny  'echo HUM-1 | xargs -I{} jira transition {} Done'
t ask   "jira transition 'HUM-1' Done"                           # #67 review: a quoted literal key is read as the key (was deny)
t deny  'jira comment LBL-1 x && jira transition "$KEY" Done'   # every transition clause needs a literal key
t ask   'jira transition HUM-1 Done 2>&1'                         # a redirection never cuts the clause
t ask   'sh -c "jira transition HUM-1 Done"'
t ask   'JIRA_DRY_RUN=1 jira transition HUM-1 Done'
t ask   'cd ~/dev/app && python3 scripts/jira.py transition HUM-1 Done'
t ask   '/opt/jira/bin/jira transition HUM-1 Done'
t allow 'cd ~/dev/app && jira transition LBL-1 Done 2>&1'
# a promptless write in the same command never makes a transition free
t ask   'jira label HUM-1 add agent-worked && jira transition HUM-1 Done'
t ask   "jira create PROJ Task \"x\" --field labels='[\"agent-drafted\"]' && jira transition HUM-1 Done"
t ask   'jira link LBL-1 Relates LBL-2 && jira transition HUM-1 Done'
t allow 'jira link LBL-1 Relates LBL-2 && jira transition LBL-1 Done'
t ask   'jira comment LBL-1 x && jira transition HUM-1 Done'
t deny  'jira transition HUM-1 Done && git push origin main'     # deferred: a later deny still wins
# hidden subcommands: quoted or escaped command words and $VAR verbs cannot be checked
t ask   'jira "transition" HUM-1 Done'
t ask   'jira "transition" LBL-1 Done'
t ask   'j\ira transition HUM-1 Done'
t ask   'jira tran\sition HUM-1 Done'
t ask   'jira "comment" HUM-1 x'
t ask   'jira "$VERB" HUM-1 Done'
t ask   'jira $(echo transition) HUM-1 Done'
t pass  'jira "get" LBL-1'                                        # a hidden read is still a read
t pass  'jira transitions HUM-1'
# caller: a subagent never transitions a ticket (principle 2: humans decide), before any lookup
T_AGENT_TYPE=Plan t ask   'jira transition HUM-1 Done'           # main thread of a session started with --agent
T_AGENT_TYPE=Plan t allow 'jira transition LBL-1 Done'
T_AGENT=''        t ask   'jira transition HUM-1 Done'           # agent_id "" = main thread
T_AGENT_NULL=1    t allow 'jira transition LBL-1 Done'           # agent_id null = main thread
T_AGENT=a1 t deny  'jira transition HUM-1 Done'
T_AGENT=a1 t deny  'jira transition LBL-1 Done'
T_AGENT=a1 t deny  'jira transition CRE-1 Done'
T_AGENT=a1 t deny  'jira transition DRF-1 Done'
T_AGENT=a1 t deny  'jira transition ERR-1 Done'
T_AGENT=a1 t deny  'jira transition "$KEY" Done'
T_AGENT=a1 t deny  'jira transition'
T_AGENT=a1 t deny  'sh -c "jira transition LBL-1 Done"'
T_AGENT=a1 t deny  'bash -lc "jira transition HUM-1 Done"'
T_AGENT=a1 t deny  'JIRA_DRY_RUN=1 jira transition LBL-1 Done'
T_AGENT=a1 t deny  'env JIRA_DRY_RUN=1 jira transition LBL-1 Done'
T_AGENT=a1 t deny  'cd ~/dev/app && jira transition LBL-1 Done'
T_AGENT=a1 t deny  'python3 scripts/jira.py transition LBL-1 Done'
T_AGENT=a1 t deny  'cd ~/dev/app && python3 /home/u/.claude/skills/jira/scripts/jira.py transition LBL-1 Done'
T_AGENT=a1 t deny  'jira comment LBL-1 x && jira transition LBL-1 Done'
T_AGENT=a1 t deny  'jira label LBL-1 add agent-worked && jira transition LBL-1 Done'
T_AGENT=a1 t deny  "jira create PROJ Task \"x\" --field labels='[\"agent-drafted\"]' && jira transition LBL-1 Done"
T_AGENT=a1 t deny  'jira link LBL-1 Relates LBL-2 && jira transition LBL-2 Done'
T_AGENT=a1 t deny  'echo LBL-1 | xargs -I{} jira transition {} Done'
T_AGENT=a1 t deny  'jira transition LBL-1 Done 2>&1'
T_AGENT=a1 t deny  'jira "transition" LBL-1 Done'
T_AGENT=a1 t deny  "jira 'transition' LBL-1 Done"
T_AGENT=a1 t deny  'j\ira transition LBL-1 Done'
T_AGENT=a1 t deny  'jira "$VERB" LBL-1 Done'
T_AGENT=a1 t deny  'jira `echo transition` LBL-1 Done'
T_AGENT=a1 t deny  "python3 'scripts/jira.py' transition LBL-1 Done"
# other writes keep their decisions in a subagent
T_AGENT=a1 t allow 'jira comment LBL-1 "hi"'
T_AGENT=a1 t ask   'jira comment HUM-1 "hi"'
T_AGENT=a1 t ask   'jira "comment" LBL-1 x'                       # a hidden non-transition write asks
T_AGENT=a1 t allow 'jira label HUM-1 add agent-worked'
T_AGENT=a1 t allow "jira create PROJ Task \"x\" --field labels='[\"agent-drafted\"]'"
T_AGENT=a1 t allow 'jira link LBL-1 Relates LBL-2'
T_AGENT=a1 t pass  'jira get HUM-1'
T_AGENT=a1 t pass  'jira transitions HUM-1'
T_AGENT=a1 t pass  'jira api /rest/api/2/issue/HUM-1/transitions'   # jira api is GET-only (the client refuses writes)
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
# #67 review C1: a key is a whole literal word; LBL-1/../HUM-2 (the client would put it in a REST
# path) never borrows LBL-1's labels
t deny  'jira transition LBL-1/../HUM-2 Done'
t ask   'jira comment LBL-1/../HUM-2 hi'
T_AGENT=a1 t ask 'jira comment LBL-1/../HUM-2 hi'
t ask   'jira set LBL-1/x labels []'
t ask   'jira label LBL-1/../HUM-2 add agent-worked'
t deny  'jira link LBL-1 Relates LBL-2/../HUM-1'
t deny  "jira create PROJ Task \"x\" --field labels='[\"agent-created\",\"agent-worked\"]' --link \"Issue split:LBL-1/../HUM-1\""
t ask   'jira comment LBL-1 a && jira comment "$KEY" b'          # every keyed clause needs a literal key (was allow)
# #67 review W1/S2: text that only mentions jira decides nothing (command position only)
t allow 'jira comment LBL-1 "Blocked: a human must run jira transition later"'
T_AGENT=a1 t allow 'jira comment LBL-1 "Ready; next: jira transition LBL-1 Done"'
T_AGENT=a1 t allow 'jira comment LBL-1 "x; jira transition HUM-1 Done"'
nl=$'\n'
T_AGENT=a1 t allow "jira comment LBL-1 \"\$(cat <<'X'${nl}Ready; next: jira transition LBL-1 Done (it's done)${nl}X${nl})\""
t allow "jira comment LBL-1 \"\$(cat <<'X'${nl}Ready; next: jira transition HUM-1 Done${nl}X${nl})\""
t allow 'jira comment LBL-1 "Use `jira get` to check"'
T_AGENT=a1 t allow 'jira comment LBL-1 "Use `jira get` to check"'
t pass  'ls -l $HOME/.local/bin/jira $HOME/x'
T_AGENT=a1 t pass 'ls -l $HOME/.local/bin/jira $HOME/x'
t pass  'git commit -m "Make jira transition a human decision"'
T_AGENT=a1 t pass 'git commit -m "Make jira transition a human decision"'
t pass  'grep -rn "jira transition" docs/'
t pass  "cat <<'X' > notes.txt${nl}jira transition HUM-1 Done${nl}X"
# ... but a command substitution, a shell fed the text, or an unquoted heredoc still runs it
t ask   'jira comment LBL-1 "$(jira transition HUM-1 Done)"'
T_AGENT=a1 t deny 'jira comment LBL-1 "$(jira transition LBL-1 Done)"'
t ask   'echo "jira transition HUM-1 Done" | sh'
T_AGENT=a1 t deny 'echo "jira transition LBL-1 Done" | bash'
t ask   "bash <<'X'${nl}jira transition HUM-1 Done${nl}X"
T_AGENT=a1 t deny "cat <<'X' | sh${nl}jira transition LBL-1 Done${nl}X"
T_AGENT=a1 t deny "cat <<X > f${nl}\$(jira transition LBL-1 Done)${nl}X"
T_AGENT=a1 t deny 'eval "jira transition LBL-1 Done"'
T_AGENT=a1 t deny 'find . -name x -exec jira transition LBL-1 Done \;'
T_AGENT=a1 t deny "python3 -c \"import os; os.system('jira transition LBL-1 Done')\""
t ask   "python3 -c \"import os; os.system('jira transition LBL-1 Done')\""
# #67 review W2: jira the guard cannot read (fed by xargs, a variable, an alias, $(which), a
# case-changed name) is a human decision: ask on the main thread, deny in a subagent
t ask   'echo transition LBL-1 Done | xargs jira'
T_AGENT=a1 t deny 'echo transition LBL-1 Done | xargs jira'
T_AGENT=a1 t deny 'xargs jira < args.txt'
t ask   '$(which jira) transition LBL-1 Done'
T_AGENT=a1 t deny '$(which jira) transition LBL-1 Done'
T_AGENT=a1 t deny '"$(command -v jira)" transition LBL-1 Done'
t ask   'J=jira; $J transition LBL-1 Done'
T_AGENT=a1 t deny 'J=jira; $J transition LBL-1 Done'
T_AGENT=a1 t deny 'alias j=jira; j transition LBL-1 Done'
t ask   'JIRA transition LBL-1 Done'
T_AGENT=a1 t deny 'JIRA transition LBL-1 Done'
T_AGENT=a1 t deny 'Jira transition LBL-1 Done'
T_AGENT=a1 t deny 'python3 /x/jira.PY transition LBL-1 Done'
T_AGENT=a1 t deny "\$'jira' transition LBL-1 Done"
T_AGENT=a1 t pass 'Jira get LBL-1'                                  # a hidden read stays a read
T_AGENT=a1 t pass 'command -v jira'
# #67 review S1: the literal-key deny comes before any check that can stop first
t deny  'jira link LBL-1 Relates ERR-1 && jira transition "$KEY" Done'
t deny  'jira label HUM-1 add agent-worked && jira transition "$KEY" Done'
# #67 review S3: jira set KEY status|resolution is a state change like a transition
t allow 'jira set LBL-1 status Done'
t ask   'jira set HUM-1 resolution Fixed'
t ask   'jira set HUM-1 Status Done'
t deny  'jira set "$K" status Done'
T_AGENT=a1 t deny  'jira set LBL-1 status Done'
T_AGENT=a1 t deny  'jira set HUM-1 resolution Fixed'
T_AGENT=a1 t allow 'jira set LBL-1 labels ["x"]'
tr 'use jira transition' 'jira set HUM-1 status Done'
# promptless writes no longer cover another write in the same command (were allow)
t ask   'jira link LBL-1 Relates LBL-2 && jira comment HUM-1 x'
t ask   "jira create PROJ Task \"x\" --field labels='[\"agent-drafted\"]' && jira comment HUM-1 x"
t ask   'jira label HUM-1 add agent-worked && jira comment HUM-2 x'
t allow 'jira link LBL-1 Relates LBL-2 && jira comment LBL-1 x'
# #67 re-review: the scanner fails closed — every substitution, here-string, pipeline into a shell
# and command-string wrapper is read, and a jira call written anywhere outside a known data
# position is a hidden call (main thread asks, a subagent is denied)
T_AGENT=a1 t deny 'echo ${x:-$(jira transition LBL-1 Done)}'                  # 1. ${…} bodies
T_AGENT=a1 t deny 'echo "${x:-$(jira transition LBL-1 Done)}"'
t ask   'echo ${x:-$(jira transition HUM-1 Done)}'
T_AGENT=a1 t deny 'cat <(jira transition LBL-1 Done)'                         # 2. process substitution
T_AGENT=a1 t deny 'diff <(jira get LBL-1) >(jira transition LBL-1 Done)'
t ask   'cat <(jira transition HUM-1 Done)'
T_AGENT=a1 t deny 'bash <<< "jira transition LBL-1 Done"'                    # 3. here-strings to a shell
T_AGENT=a1 t deny 'bash -x /dev/stdin <<< "jira transition LBL-1 Done"'
T_AGENT=a1 t deny 'tee >(sh) <<< "jira transition LBL-1 Done"'
t ask   'bash <<< "jira transition HUM-1 Done"'
T_AGENT=a1 t deny 'echo "jira transition LBL-1 Done" | cat | sh'             # 4. multi-stage pipes into a shell
T_AGENT=a1 t deny 'echo "jira transition LBL-1 Done" | tee /dev/null | bash'
t ask   'echo "jira transition HUM-1 Done" | cat | sh'
T_AGENT=a1 t deny "sh -c '\"\$@\"' _ jira transition LBL-1 Done"             # 5. sh -c with positional words
T_AGENT=a1 t deny "sh -c 'exec \"\$0\" \"\$@\"' jira transition LBL-1 Done"
T_AGENT=a1 t deny 'bash -c -- "jira transition LBL-1 Done"'
t ask   "sh -c '\"\$@\"' _ jira transition HUM-1 Done"
T_AGENT=a1 t deny 'python3 -X dev ~/.local/bin/jira transition LBL-1 Done'   # 6. python value options
T_AGENT=a1 t deny 'python3 -W ignore jira.py transition LBL-1 Done'
t ask   'python3 -X dev ~/.local/bin/jira transition HUM-1 Done'
T_AGENT=a1 t deny 'env -S "jira transition LBL-1 Done"'                       # 7. command-string wrappers
T_AGENT=a1 t deny 'watch -n1 "jira transition LBL-1 Done"'
T_AGENT=a1 t deny 'script -qc "jira transition LBL-1 Done" /dev/null'
T_AGENT=a1 t deny 'su -c "jira transition LBL-1 Done" me'
T_AGENT=a1 t deny 'parallel "jira transition {} Done" ::: LBL-1'
T_AGENT=a1 t deny "git -c alias.x='!jira transition LBL-1 Done' x"
T_AGENT=a1 t deny 'foo "jira transition LBL-1 Done"'                          # any command: fail closed
t ask   'script -qc "jira transition HUM-1 Done" /dev/null'
t ask   'su -c "jira transition LBL-1 Done" me'                               # hidden even when agent-labelled
T_AGENT=a1 t deny '=jira transition LBL-1 Done'                               # 8. zsh =cmd
t ask   '=jira transition HUM-1 Done'
# obfuscated client names (the prefilter strips quotes, backslashes and continuations; a state verb
# after a glob or $VAR command word is hidden)
T_AGENT=a1 t deny "ji\\${nl}ra transition LBL-1 Done"
# shellcheck disable=SC2088  # the tilde is part of the command under test
T_AGENT=a1 t deny '~/.local/bin/jir? transition LBL-1 Done'
T_AGENT=a1 t deny '/x/j[i]ra transition LBL-1 Done'
T_AGENT=a1 t deny 'J=ji; ${J}ra transition LBL-1 Done'
T_AGENT=a1 t deny 'J=ji; ${J}ra set LBL-1 status Done'
t ask   'J=ji; ${J}ra transition HUM-1 Done'
T_AGENT=a1 t deny "\$'\\x6aira' transition LBL-1 Done"                        # ANSI-C words are decoded
T_AGENT=a1 t deny "\$'j\\151ra' transition LBL-1 Done"
t ask   "\$'\\x6aira' comment LBL-1 x"
# data positions stay data (the false-positive wins of the scanner)
t pass  'echo "jira transition HUM-1 Done"'
t pass  'echo "jira transition HUM-1 Done" | grep jira'
T_AGENT=a1 t pass 'printf "%s\n" "jira transition LBL-1 Done" | tee notes.txt'
t pass  'git log --grep "jira transition"'
T_AGENT=a1 t pass 'rg "jira transition" docs/'
t pass  "cat <<'X' | grep x${nl}jira transition HUM-1 Done${nl}X"
T_AGENT=a1 t pass "tee notes.txt <<< 'jira transition LBL-1 Done'"
# repeated --field labels: the last one wins in Jira, so a second one could drop the provenance
t deny  "jira create PROJ Task s --field labels='[\"agent-drafted\"]' --field labels='[]'"
tr 'pass a single --field labels' "jira create PROJ Task s --field labels='[\"agent-drafted\"]' --field labels='[]'"
# the scanner fails closed (python3 missing, broken or timed out)
bpy=$(mktemp -d); printf '#!/bin/sh\nexit 3\n' > "$bpy/python3"; chmod +x "$bpy/python3"
PATH="$bpy:$PATH" t ask 'jira comment LBL-1 x'
PATH="$bpy:$PATH" T_AGENT=a1 t deny 'jira comment LBL-1 x'
PATH="$bpy:$PATH" tr 'jira guard scanner failed' 'jira comment LBL-1 x'
PATH="$bpy:$PATH" t pass 'git status'
rm -rf "$bpy"
# promptless jira writes wait for every later section (pending_allow, deferred asks)
if grep -q '^guard_section_gdoc_80_gdoc()' "$H"; then
  t deny 'jira comment LBL-1 x && gdoc api -X POST /x'
  t deny 'jira comment HUM-1 x && gdoc api -X POST /x'
fi
# ---- repo overrides (repo .claude/settings.json env) -------------------------------
# WORK_TICKET_ALLOW_TRANSITION is a deprecated no-op since #67: every row decides as without it
t ask   'jira transition HUM-1 "In Progress"'                     # #67: was deny
WORK_TICKET_ALLOW_TRANSITION=1 t ask   'jira transition HUM-1 "In Progress"'   # #67: no-op alias
WORK_TICKET_ALLOW_TRANSITION=1 t allow 'jira transition LBL-1 "In Progress"'   # #67: no-op alias
WORK_TICKET_ALLOW_TRANSITION=1 t deny  'jira transition "$KEY" "In Progress"'  # #67: no-op alias
WORK_TICKET_ALLOW_TRANSITION=1 t deny  'jira transition ERR-1 "In Progress"'   # #67: no-op alias
WORK_TICKET_ALLOW_TRANSITION=0 t ask   'jira transition HUM-1 "In Progress"'   # #67: was deny; no-op alias
WORK_TICKET_ALLOW_TRANSITION=0 t allow 'jira transition LBL-1 "In Progress"'   # #67: no-op alias
WORK_TICKET_ALLOW_TRANSITION=1 T_AGENT=a1 t deny 'jira transition HUM-1 "In Progress"'   # #67: no-op alias in a subagent too
# ---- harness parameters: link types (jira.link_types) and the client path default
HARNESS_JIRA_LINK_TYPES_RE='^(relates)$'    t deny  'jira link LBL-1 Blocks LBL-2'
HARNESS_JIRA_LINK_TYPES_RE='^(relates)$'    t allow 'jira link LBL-1 Relates LBL-2'
HARNESS_JIRA_LINK_TYPES_RE='^(depends on)$' t allow 'jira link LBL-1 "Depends on" LBL-2'
HARNESS_JIRA_LINK_TYPES_RE='^(relates)$'    tr 'allowed: \^\(relates\)\$' 'jira link LBL-1 Blocks LBL-2'
# without WORK_TICKET_JIRA_PY the guard uses <hooks dir>/../skills/jira/scripts/jira.py
lay=$(mktemp -d); mkdir -p "$lay/hooks" "$lay/skills/jira/scripts"
cp "$H" "$lay/hooks/guard-bash.sh"; cp "$STUBS/jira-stub.py" "$lay/skills/jira/scripts/jira.py"
WORK_TICKET_JIRA_PY='' H="$lay/hooks/guard-bash.sh" t allow 'jira comment LBL-1 x'
WORK_TICKET_JIRA_PY='' H="$lay/hooks/guard-bash.sh" t ask   'jira comment HUM-1 x'
rm -f "$lay/skills/jira/scripts/jira.py"
WORK_TICKET_JIRA_PY='' H="$lay/hooks/guard-bash.sh" t ask   'jira comment LBL-1 x'   # client missing -> cannot verify -> ask
rm -rf "$lay"
# link types as a rendered list (HARNESS_JIRA_LINK_TYPES from jira.link_types); the regex form wins
HARNESS_JIRA_LINK_TYPES='Relates, Depends (on)' t allow 'jira link LBL-1 "Depends (on)" LBL-2'
HARNESS_JIRA_LINK_TYPES='Relates, Depends (on)' t deny  'jira link LBL-1 Blocks LBL-2'
HARNESS_JIRA_LINK_TYPES='Relates' HARNESS_JIRA_LINK_TYPES_RE='^(blocks)$' t allow 'jira link LBL-1 Blocks LBL-2'
# ---- repository-level declaration: .harness.toml (principle 8) ----------------------
decl '[overrides]' 'WORK_TICKET_ALLOW_TRANSITION = "1"'
r ask   'jira transition HUM-1 "In Progress"'                 # #67: no-op alias (ask with or without it)
r allow 'jira transition LBL-1 "In Progress"'
r deny  'jira transition "$KEY" "In Progress"'                # #67: no-op alias
T_AGENT=a1 r deny 'jira transition HUM-1 "In Progress"'       # #67: no-op alias in a subagent too
WORK_TICKET_ALLOW_TRANSITION=0 r ask 'jira transition HUM-1 "In Progress"'    # #67: was deny; no-op alias
decl '[overrides]' 'WORK_TICKET_LABELED_DECISION = "ask"'
r ask   'jira comment LBL-1 "hi"'
decl '[overrides]' 'WORK_TICKET_JIRA_PY = "/bin/true"'      # bypass: client paths are never repo-settable
# shellcheck disable=SC2154  # rpd: the fixture repository, defined in guard/tests/lib.sh
tn ask 'WORK_TICKET_JIRA_PY is settable only from your own environment' "$rpd" 'jira transition HUM-1 "In Progress"'   # #67: was deny (the stub's human ticket now asks; /bin/true would deny)
decl '[owns]' 'domains = ["tracker"]'
r pass  'jira transition HUM-1 "In Progress"'                 # the repository owns the tracker: its harness decides
T_AGENT=a1 r pass 'jira transition LBL-2 Done'                # principle 8 first: owned in a subagent too
T_AGENT=a1 r pass 'jira transition HUM-1 Done'
T_AGENT=a1 r pass 'jira "transition" HUM-1 Done'
r pass  'jira create PROJ Task "x"'
r pass  'jira comment HUM-1 "hi"'
decl '[owns]' 'components = ["jira/guard.d/70-jira"]'
r pass  'jira transition HUM-1 "In Progress"'
decl '[owns]' 'domains = ["scm"]'
r ask   'jira transition HUM-1 "In Progress"'                 # another domain: unchanged (#67: was deny)
T_AGENT=a1 r deny 'jira transition HUM-1 "In Progress"'
decl
# runtime deny/ask messages carry the # rule: alternative (lint guard-messages)
tr "use 'jira link FROM TYPE TO' with literal keys" 'jira link "$A" Relates LBL-2'
tr 'use one of the allowed types instead' 'jira link LBL-1 "Finish-to-Start Dependency" LBL-2'
tr "check 'jira whoami', or ask the user" 'jira link LBL-1 Relates ERR-1'
tr 'ask the user to link it, or label it first' 'jira link HUM-1 Relates LBL-1'
tr 'pass --field labels=' "jira create PROJ Task \"[LBL-1] x\" --link \"Issue split:LBL-1\""
tr 'ask the user to transition it' 'jira transition HUM-1 "Start Work"'
tr "run it only on the user's explicit request \(they confirm it\), or ask the user to transition it in Jira instead" 'jira transition HUM-1 Done'
tr 'requires explicit user confirmation' 'jira transition HUM-1 Done'
tr 'type the key literally' 'jira transition "$KEY" Done'
tr 'could not verify labels' 'jira transition ERR-1 Done'
tr 'write it literally' 'jira "transition" HUM-1 Done'
tr 'write it literally' 'jira "$VERB" HUM-1 Done'
tr 'write the jira subcommand literally and unquoted instead' 'jira "comment" HUM-1 x'
T_AGENT=a1 tr 'hand the command back to the main thread' 'jira transition HUM-1 Done'
T_AGENT=a1 tr 'hand the command back to the main thread' 'jira transition LBL-1 Done'
T_AGENT=a1 tr 'changes ticket state, a human decision' 'jira transition "$KEY" Done'
T_AGENT=a1 tr 'hand the command back to the main thread' 'jira "transition" LBL-1 Done'
tr 'use a literal key like PROJ-123' 'jira comment "$KEY" x'
tr "check 'jira whoami', or ask the user" 'jira comment ERR-1 x'
tr 'ask the user, or label first' 'jira comment HUM-1 "hi"'
