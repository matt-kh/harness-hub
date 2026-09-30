# shellcheck shell=bash
# Guard test rows for bundle gdoc. Sourced by bundles/core/guard/tests/run.sh after lib.sh
# (helpers: t EXPECTED 'cmd' | tc EXPECTED CWD 'cmd' | tr 'reason-re' 'cmd' | g EXPECTED 'cmd' in a real dir).

# ---- gdoc: reads → passthrough (permissions.allow covers them)
t pass  'gdoc whoami'
t pass  'gdoc search "quarterly report"'
t pass  'gdoc list --folder HUM1111111111111111111'
t pass  'gdoc meta AGT1111111111111111111'
t pass  'gdoc get https://docs.google.com/document/d/HUM1111111111111111111/edit'
t pass  'gdoc export HUM1111111111111111111 --md /tmp/x.md'
t pass  'gdoc comments HUM1111111111111111111'
t pass  'gdoc sheet get HUM1111111111111111111 "Sheet1!A1:C9"'
t pass  'gdoc mail search "newer_than:1d" 3'
t pass  'gdoc mail get 18f0abc'
t pass  'gdoc api "https://www.googleapis.com/drive/v3/about?fields=user"'
t pass  'gdoc auth status'
t pass  'gdoc auth login'
# gdoc writes gated on the Drive property agent_provenance (AGT/MRK marked, HUM/ZZZ not, ERR fails)
t allow 'gdoc append AGT1111111111111111111 "text"'
t allow 'gdoc append MRK1111111111111111111 "text" --heading "Notes"'
t allow 'gdoc append https://docs.google.com/document/d/AGT1111111111111111111/edit?tab=t.0 "text"'
t allow 'gdoc append --from /tmp/x.md AGT1111111111111111111'
t ask   'gdoc append HUM1111111111111111111 "text"'
t ask   'gdoc append ZZZ1111111111111111111 "text"'
t ask   'gdoc append ERR1111111111111111111 "text"'
t ask   'gdoc append "$DOC" "text"'
t ask   'gdoc append short-id "text"'
t ask   'gdoc append --heading "x" "$DOC"'
t ask   'gdoc append --heading "x"'
t allow 'gdoc import AGT1111111111111111111 /tmp/x.md --force'
t ask   'gdoc import HUM1111111111111111111 /tmp/x.md'
t ask   'gdoc import ERR1111111111111111111 /tmp/x.md'
t allow 'gdoc replace AGT1111111111111111111 "a" "b" --match-case'
t allow 'gdoc replace --tab t.0 MRK1111111111111111111 a b'
t ask   'gdoc replace HUM1111111111111111111 a b'
t allow 'gdoc append AGT1111111111111111111 a && gdoc replace AGT2222222222222222222 x y'
t ask   'gdoc append AGT1111111111111111111 a && gdoc append HUM1111111111111111111 b'
t allow "gdoc sheet append AGT1111111111111111111 'Sheet1!A:C' '[[\"a\",\"b\"]]'"
t allow "gdoc sheet update MRK1111111111111111111 'Sheet1!A1' '[[\"x\"]]'"
t ask   "gdoc sheet update HUM1111111111111111111 'Sheet1!A1' '[[\"x\"]]'"
t allow 'python3 ~/.claude/skills/gdoc/scripts/gdoc.py append AGT1111111111111111111 "x"'
t ask   'cd ~/x && python3 ~/.claude/skills/gdoc/scripts/gdoc.py append HUM1111111111111111111 "x"'
# gdoc create / mark / mail / api
t allow 'gdoc create "Design notes" --from /tmp/x.md --folder HUM1111111111111111111'
t allow 'GDOC_DRY_RUN=1 gdoc create "x" --from /tmp/x.md'
t allow 'gdoc create "x" --from /tmp/x.md && gdoc append AGT1111111111111111111 "y"'
t ask   'gdoc create "x" --from /tmp/x.md && gdoc append HUM1111111111111111111 "y"'
t ask   'gdoc mark HUM1111111111111111111 agent-worked'
t ask   'gdoc mark AGT1111111111111111111 none'
t ask   'gdoc mark https://docs.google.com/document/d/HUM1111111111111111111/edit agent-worked'
t ask   'gdoc mark "$DOC" agent-worked'
t allow 'gdoc mail draft --to a@example.com --subject s --body b'
t ask   'gdoc mail send r123abc'
t ask   'gdoc mail draft --to a@example.com --subject s --body b && gdoc mail send r123'
t deny  'gdoc api -X POST https://www.googleapis.com/drive/v3/files'
t deny  'gdoc api --method=POST https://www.googleapis.com/drive/v3/files'
t deny  "gdoc api -d '{}' https://www.googleapis.com/drive/v3/files"
# ---- harness parameters: without WORK_TICKET_GDOC_PY the guard uses <hooks dir>/../skills/gdoc/scripts/gdoc.py
lay=$(mktemp -d); mkdir -p "$lay/hooks" "$lay/skills/gdoc/scripts"
cp "$H" "$lay/hooks/guard-bash.sh"; cp "$STUBS/gdoc-stub.py" "$lay/skills/gdoc/scripts/gdoc.py"
WORK_TICKET_GDOC_PY='' H="$lay/hooks/guard-bash.sh" t allow 'gdoc append AGT1111111111111111111 "text"'
WORK_TICKET_GDOC_PY='' H="$lay/hooks/guard-bash.sh" t ask   'gdoc append HUM1111111111111111111 "text"'
rm -rf "$lay"
