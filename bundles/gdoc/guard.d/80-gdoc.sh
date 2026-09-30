# shellcheck shell=bash

# Section 80 (bundle gdoc): Google Workspace governance keyed on the Drive property agent_provenance.
# rule: gdoc api -X|--method|-d|--data -> deny : api is GET-only
# rule: gdoc mark ID -> ask : adopts a human file
# rule: gdoc import|append|replace|sheet append|update on an agent-marked file -> allow : human files / lookup failure ask
# rule: gdoc create | gdoc mail draft -> allow : create stamps provenance; nothing is sent
# rule: gdoc mail send -> ask : outward and irreversible
# ---- Google Workspace (gdoc): governance gate ------------------------------------
# create (script stamps properties.agent_provenance=agent-created) and mail draft: promptless.
# import/append/replace/sheet append|update on files whose Drive property agent_provenance
# matches ^agent-: promptless. Human files (no marker) / lookup failure: ask. mark: ask
# (adopting a human file). mail send: not a gdoc verb any more (the agent never sends mail);
# kept as ask so it is still gated if the verb ever reappears. api is GET-only by construction.
GDOC_PY="${WORK_TICKET_GDOC_PY:-$GUARD_DIR/../skills/gdoc/scripts/gdoc.py}"   # rendered skill next to the hooks dir
GDOC_ID_RE='^[A-Za-z0-9_-]{20,}$'
GDOC_WRITE_RE='\bgdoc(\.py)?\s+(import|append|replace|sheet\s+(append|update))\b'
fetch_prov() {  # ID -> properties.agent_provenance ("" if none); rc 1 on failure
  local o; o=$(hn_timeout 8 python3 "$GDOC_PY" meta "$1" 2>/dev/null) || return 1
  [ -n "$o" ] || return 1
  printf '%s' "$o" | jq -e '.id' >/dev/null 2>&1 || return 1
  printf '%s' "$o" | jq -r '.properties.agent_provenance // ""' 2>/dev/null
}
gdoc_id() {  # TOKEN -> bare Drive id from a literal id or docs/drive URL; empty otherwise
  local t; t=$(printf '%s' "$1" | tr -d "\"'")
  case "$t" in
    *google.com/*/d/*)           t=$(printf '%s' "$t" | sed -E 's#.*/d/([A-Za-z0-9_-]+).*#\1#') ;;
    *google.com/drive/folders/*) t=$(printf '%s' "$t" | sed -E 's#.*/folders/([A-Za-z0-9_-]+).*#\1#') ;;
  esac
  printf '%s' "$t" | grep -qE "$GDOC_ID_RE" && printf '%s' "$t"
}
if printf '%s' "$flat" | grep -qE '\bgdoc(\.py)?\s+(create|import|append|replace|mark|sheet\s+(append|update)|mail\s+(draft|send)|api)\b'; then
  printf '%s' "$flat" | grep -qE '\bgdoc(\.py)?\s+mail\s+send\b' && ask "gdoc mail send — sends email (outward, irreversible)"
  printf '%s' "$flat" | grep -qE '\bgdoc(\.py)?\s+api\b[^;&|]*(^|[[:space:]])(-X|--method|-d|--data)([= ]|$)' && deny "gdoc api is GET-only (no -X/--method/--data)"
  if printf '%s' "$flat" | grep -qE '\bgdoc(\.py)?\s+mark\b'; then
    mtok=$(printf '%s' "$flat" | grep -oE '\bgdoc(\.py)?\s+mark\s+[^;&| ]+' | head -1 | awk '{print $3}')
    printf '%s' "$mtok" | grep -q '\$' && ask "gdoc mark on \$VAR — use a literal file id/URL"
    mid=$(gdoc_id "$mtok"); [ -n "$mid" ] || ask "gdoc mark without a literal file id/URL"
    ask "gdoc mark $mid — changes the file's provenance (later writes run promptless)"
  fi
  if printf '%s' "$flat" | grep -qE "$GDOC_WRITE_RE"; then
    n_cmds=$(printf '%s' "$flat" | grep -oE "$GDOC_WRITE_RE" | wc -l)
    n_seen=0
    while IFS= read -r clause; do
      [ -n "$clause" ] || continue
      n_seen=$((n_seen+1))
      rest=$(printf '%s' "$clause" | sed -E 's/^gdoc(\.py)?[[:space:]]+(sheet[[:space:]]+)?[a-z]+[[:space:]]*//')
      ref=""; skip=0
      for tok in $rest; do
        if [ $skip -eq 1 ]; then skip=0; continue; fi
        case "$tok" in
          --force|--match-case|--json) ;;   # boolean flags
          -*=*) ;;                           # --flag=value
          -*) skip=1 ;;                      # --flag value
          *) ref="$tok"; break ;;
        esac
      done
      [ -n "$ref" ] || ask "gdoc write without a file id — pass the Doc/Sheet id or URL first"
      printf '%s' "$ref" | grep -q '\$' && ask "gdoc write on \$VAR — use a literal id/URL"
      fid=$(gdoc_id "$ref"); [ -n "$fid" ] || ask "gdoc write — '$ref' is not a literal Drive id/URL"
      prov=$(fetch_prov "$fid") || ask "gdoc write to $fid — could not read its provenance (gdoc meta failed: auth/timeout/no access)"
      printf '%s' "$prov" | grep -qE "$AGENT_LABEL_RE" || ask "gdoc write to $fid — no agent provenance marker (human file; adopt with: gdoc mark $fid agent-worked)"
    done <<EOF
$(printf '%s' "$flat" | grep -oE '\bgdoc(\.py)?\s+(import|append|replace|sheet\s+(append|update))\s+[^;&|]*')
EOF
    [ "$n_seen" -ge "$n_cmds" ] || ask "gdoc write — could not parse every clause"
    allow "gdoc write(s) on agent-marked file(s)"
  fi
  printf '%s' "$flat" | grep -qE '\bgdoc(\.py)?\s+create\b' && allow "gdoc create (script stamps agent_provenance=agent-created)"
  printf '%s' "$flat" | grep -qE '\bgdoc(\.py)?\s+mail\s+draft\b' && allow "gdoc mail draft (nothing is sent; mail send asks)"
fi
