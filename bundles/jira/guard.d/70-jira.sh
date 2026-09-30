# shellcheck shell=bash

# Section 70 (bundle jira): Jira write governance.
# rule: jira set KEY issuelinks | create --field issuelinks= -> deny : use the governed link commands
# rule: jira link A TYPE B (both agent-labelled, type in HARNESS_JIRA_LINK_TYPES_RE) -> allow : otherwise deny
# rule: jira create without a provenance label (agent-drafted|agent-created) -> deny : every agent-created ticket is labelled
# rule: jira create with a provenance label -> allow : creates are promptless
# rule: jira label KEY add agent-* -> allow : governance labelling is free
# rule: jira set|comment|upload|label|transition KEY on agent-labelled tickets -> allow : promptless
# rule: jira transition KEY on a human ticket -> deny : ticket state is human-only (ask under WORK_TICKET_ALLOW_TRANSITION=1)
# rule: jira writes to human tickets -> ask : need an explicit user request
# ---- Jira writes: governance gate (work-ticket / create-ticket skills) -----------
# create (with provenance label) and `label KEY add agent-*`: promptless.
# set/comment/upload/label/link/transition on tickets carrying ANY agent-* label: promptless.
# Purely human tickets (no agent-* label): writes ask; transition DENIED (state is human-only).
# link / create --link: only between agent-labelled tickets (deny otherwise).
JIRA_PY="${WORK_TICKET_JIRA_PY:-$GUARD_DIR/../skills/jira/scripts/jira.py}"   # rendered skill next to the hooks dir
# Allowed link types, lowercased: HARNESS_JIRA_LINK_TYPES_RE (regex) wins, else
# HARNESS_JIRA_LINK_TYPES (comma-separated names, rendered from jira.link_types), else the default.
LINK_TYPES_RE="${HARNESS_JIRA_LINK_TYPES_RE:-}"
if [ -z "$LINK_TYPES_RE" ] && [ -n "${HARNESS_JIRA_LINK_TYPES:-}" ]; then
  LINK_TYPES_RE="^($(printf '%s' "$HARNESS_JIRA_LINK_TYPES" | LC_ALL=C tr '[:upper:]' '[:lower:]' \
    | sed -E 's/[][\.*^$+?(){}|\/]/\\&/g; s/^[[:space:]]+//; s/[[:space:]]+$//; s/[[:space:]]*,[[:space:]]*/|/g'))\$"
fi
[ -n "$LINK_TYPES_RE" ] || LINK_TYPES_RE='^(issue split|relates|blocks)$'
# fetch_labels KEY -> JSON array of Jira labels; rc 1 on failure
fetch_labels() {
  local o; o=$(hn_timeout 5 python3 "$JIRA_PY" get "$1" 2>/dev/null) || return 1
  [ -n "$o" ] || return 1
  printf '%s' "$o" | jq -c '.labels // []' 2>/dev/null || return 1
}
if printf '%s' "$flat" | grep -qE '\bjira(\.py)?\s+(set|create|transition|upload|comment|label|link)\b'; then
  # -- raw issuelinks writes are not governed -> deny, point at the governed commands
  printf '%s' "$flat" | grep -qE "\bjira(\.py)?\s+set\s+${KEY_RE}\s+[\"']?issuelinks\b" && deny "issuelinks field rewrite — use 'jira link FROM TYPE TO' (governed)"
  printf '%s' "$flat" | grep -qE -- "--field[= ]+[\"']?issuelinks=" && deny "issuelinks in jira create — use --link TYPE:KEY (governed)"

  # -- jira link A TYPE B: two distinct literal keys, allowed type, both agent-worked → allow
  if printf '%s' "$flat" | grep -qE '\bjira(\.py)?\s+link\b'; then
    clause=$(printf '%s' "$flat" | grep -oE '\bjira(\.py)?\s+link\s+[^;&|]*' | head -1)
    lkeys=$(printf '%s' "$clause" | grep -oE "$KEY_RE" | sort -u)
    [ "$(printf '%s\n' "$lkeys" | grep -c .)" -eq 2 ] || deny "jira link needs exactly two distinct literal ticket keys (no \$VARS)"
    ltype=$(printf '%s' "$clause" | sed -E "s/.*(^|[^[:alnum:]_])link[[:space:]]+${KEY_RE}[[:space:]]+//; s/[[:space:]]+${KEY_RE}.*$//; s/^[\"']//; s/[\"']$//" | tr 'A-Z' 'a-z')
    printf '%s' "$ltype" | grep -qE "$LINK_TYPES_RE" || deny "jira link type '$ltype' not permitted (allowed: $LINK_TYPES_RE)"
    for k in $lkeys; do
      lb=$(fetch_labels "$k") || ask "jira link — could not verify labels on $k"
      labels_have_write "$lb" || deny "linking to a human ticket is not permitted ($k has no agent-* label)"
    done
    allow "jira link $(printf '%s' "$lkeys" | tr '\n' ' ')— both tickets are agent-labelled"
  fi

  # -- jira create ... --link TYPE:KEY: must carry both governance labels; targets agent-worked
  if printf '%s' "$flat" | grep -qE '\bjira(\.py)?\s+create\b' && printf '%s' "$flat" | grep -qE -- '--link\b'; then
    lblflag=$(printf '%s' "$flat" | grep -oE -- "--field[= ]+[\"']?labels=[^ ]*" | head -1)
    { printf '%s' "$lblflag" | grep -q "$CREATED_LABEL" && printf '%s' "$lblflag" | grep -q "$GOV_LABEL"; } \
      || deny "jira create --link without labels $CREATED_LABEL + $GOV_LABEL would create an unlabelled linked ticket"
    for k in $(printf '%s' "$flat" | grep -oE -- "--link[= ]+[\"']?[^:\"']+:${KEY_RE}" | grep -oE "${KEY_RE}$" | sort -u); do
      lb=$(fetch_labels "$k") || ask "jira create --link — could not verify labels on $k"
      labels_have_write "$lb" || deny "linking to a human ticket is not permitted ($k lacks $GOV_LABEL)"
    done
  fi
  # -- every agent-created ticket carries a provenance label: agent-drafted (create-ticket) or
  #    agent-created (work-ticket sub-tickets). Count creates vs labelled creates so a batch
  #    cannot smuggle an unlabelled one. Labelled creates run promptless.
  if printf '%s' "$flat" | grep -qE '\bjira(\.py)?\s+create\b'; then
    n_create=$(printf '%s' "$flat" | grep -oE '\bjira(\.py)?\s+create\b' | wc -l)
    n_prov=$(printf '%s' "$flat" | grep -oE -- "--field[= ]+[\"']?labels=[\"']?\[[^] ]*\"(${DRAFTED_LABEL}|${CREATED_LABEL})\"" | wc -l)
    [ "$n_prov" -ge "$n_create" ] \
      || deny "jira create without a provenance label — pass --field labels='[\"${DRAFTED_LABEL}\"]' (create-ticket) or '[\"${CREATED_LABEL}\",\"${GOV_LABEL}\"]' (work-ticket sub-tickets)"
    allow "jira create carrying a provenance label ($n_create ticket(s))"
  fi

  # -- jira label KEY add agent-*: the tagging itself is free. Anything else → key gate below.
  if printf '%s' "$flat" | grep -qE '\bjira(\.py)?\s+label\b'; then
    n_label=$(printf '%s' "$flat" | grep -oE '\bjira(\.py)?\s+label\b' | wc -l)
    n_free=0; n_parsed=0
    while IFS= read -r lc; do
      [ -n "$lc" ] || continue
      n_parsed=$((n_parsed+1))
      act=$(printf '%s' "$lc" | awk '{print $4}')
      lbl_list=$(printf '%s' "$lc" | cut -d' ' -f5- | tr -d "\"'" | tr ' ,' '\n\n' | grep -v '^$')
      if [ "$act" = add ] && [ -n "$lbl_list" ] && ! printf '%s\n' "$lbl_list" | grep -vqE "$AGENT_LABEL_RE"; then
        n_free=$((n_free+1))
      fi
    done <<EOF
$(printf '%s' "$flat" | grep -oE "\bjira(\.py)?\s+label\s+${KEY_RE}\s+(add|remove)\s+[^;&|]*")
EOF
    [ "$n_parsed" -ge "$n_label" ] || ask "jira label — could not parse every clause (use: jira label KEY add|remove LABEL…, literal keys)"
    [ "$n_free" -ge "$n_label" ] && allow "jira governance labelling (agent-* labels only)"
  fi

  keys=$(printf '%s' "$flat" | grep -oE "\bjira(\.py)?\s+(set|upload|comment|transition|label)\s+${KEY_RE}" | grep -oE "${KEY_RE}$" | sort -u)
  is_transition=false; printf '%s' "$flat" | grep -qE '\bjira(\.py)?\s+transition\b' && is_transition=true
  if [ -z "$keys" ]; then
    $is_transition && deny "jira transition without an identifiable ticket key — ticket state is human-only"
    ask "jira write (could not identify the ticket key)"
  fi

  all_gov=true
  for k in $keys; do
    lb=$(fetch_labels "$k") || {
      $is_transition && deny "jira transition on $k — could not verify labels; ticket state is human-only"
      ask "jira write to $k — could not verify its labels (jira get failed: timeout/auth/403)"
    }
    labels_have_write "$lb" || all_gov=false
  done
  klist=$(printf '%s' "$keys" | tr '\n' ' ')

  if $all_gov; then
    [ "$LABELED_DECISION" = "allow" ] && allow "jira write to ${klist}— ticket(s) carry an agent-* label"
    ask "jira write to $klist(ticket(s) carry an agent-* label)"
  fi
  $is_transition && [ "$ALLOW_TRANSITION" = 1 ] && ask "jira transition on $klist — human ticket; transition allowed in this repo by WORK_TICKET_ALLOW_TRANSITION=1"
  $is_transition && deny "jira transition on $klist refused — human-written ticket state (move/close/reopen) is operated by humans only"
  ask "ticket(s) $klist not all agent-labelled — writes to human tickets need an explicit user request; label first (jira label KEY add $GOV_LABEL)"
fi
