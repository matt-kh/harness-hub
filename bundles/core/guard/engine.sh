#!/usr/bin/env bash
# Guard hook for agent shell commands (neutral envelope = Claude Code PreToolUse, matcher Bash).
# Rendered by harness-hub: engine.sh + bundles/*/guard.d/NN-*.sh (sorted by basename) +
# engine-flush.sh, concatenated into ONE file (see bundles/core/guard/build.sh).
# Section order (global numeric prefixes): 10 k8s definitions, 20 credentials, 25 k8s rules,
# 30 git, 40 GitLab/Jira closing keywords, 41 GitHub closing keywords, 50 glab, 60 gh,
# 70 jira, 80 gdoc, 90+ private bundles, then the flush. allow/ask/deny exit immediately,
# so an earlier section wins; gated rules use defer/pending_allow to let a later deny win.
#
# Purpose: catch cluster-mutating / destructive / team-visible commands however they
# are wrapped (`cd x && ...`, `sh -c "..."`, `xargs`, ...), which string-prefix
# permission rules cannot catch.
#
# Decisions (JSON permissionDecision):
#   ask   — escalate to an explicit user confirmation
#   allow — promptless: creates, labelling with agent-* labels, and EVERY write (incl.
#           transitions) to tickets / MRs that already carry any agent-* label
#   deny  — hard block (ticket state changes, closing keywords, unlabelled creates,
#           stacked-delivery violations: a -sub- MR aimed at master|main)
# Governance model (Jira + GitLab): guards apply ONLY to existing tickets/MRs that are purely
# human-written (no agent-* label). Agent-created or agent-labelled artefacts are written
# promptless. Exceptions kept as ask: MR merge/approve (humans merge — user decision).
# Stacked delivery (work-ticket L/XL): sub branches (<short>-sub-NN-<task>) are pushed by the
# main thread from the main checkout and get their own MR targeting the ticket branch; a push
# from inside a sub worktree (where subagents run) asks; sub MRs to master|main are denied.
# Ticket state stays human-only; humans merge MRs. Repo hooks still apply additively.
# Google Workspace (gdoc): the same model keyed on the Drive file property agent_provenance
# instead of a label — create and mail draft are promptless, import/append/replace/sheet
# writes are promptless only on files marked agent-* and ask otherwise (or on lookup
# failure / $VAR ids), mark asks always (it adopts a human file), mail send asks always.
# Kubernetes: kubeconfig reads/edits and Secret data output deny; mutations, exec-class, helm get
# values ask (reason carries context + [PROD]); '| k8s redact' lifts the Secret/helm gates.
# GitHub (gh, github.com): parity with GitLab + Jira, GitHub Issues being the tracker —
# gh pr create is promptless (same -sub- stacked rules as glab, head from -H or the current
# branch); gh issue create needs a provenance label (-l agent-drafted|agent-created, else deny);
# writes to PRs/issues carrying an agent-* label are promptless, human ones ask; gh issue
# close|reopen on a human issue denies (ask under WORK_TICKET_ALLOW_TRANSITION=1); cross-repo
# (fork) PR edits ask; merge/review and other team-visible actions ask; gh api writes ask (GET
# and read-only GraphQL queries pass); token output (gh auth token, --show-token, oauth_token)
# denies; GitHub closing keywords (close/fix/resolve + #N | owner/repo#N | issue URL) deny in
# commits, gh pr create|edit|merge and gh api. Lookups honour -R/--repo on the command line
# (before or after the verb) and run in the command's cwd. A GH_REPO=… prefix is invisible to
# the lookup (it would read the cwd repo), so gated writes with GH_REPO= ask — always pass -R.
# Credentials: reading credential files (kubeconfig, ~/.config/{jira,glab-cli,gdoc,gh},
# ~/.claude/{.credentials,remote-settings}.json, ~/.aws, ~/.ssh except *.pub, .env/.env.*)
# and dumping secret-bearing env vars (bare env/printenv, echo $*TOKEN*) deny.
# Git: pushing to a default branch (BASE_BRANCH_RE) denies — MR-based workflow.
# Fail CLOSED if jq is missing: every Bash command is denied until jq is installed.
#
# ---- Override env vars (read at run time) ------------------------------------------
# Repos opt in via their `.claude/settings.json` → "env": {...}. Hooks stack (a repo hook
# cannot un-deny a user-level deny), so these envs are the only way a repo switches off a
# user-level behaviour. Where a repo has its own equivalent skill/guard/convention, that
# repo-level behaviour replaces the user-level one completely (never merged).
#   WORK_TICKET_LABEL               Jira label granting promptless writes (agent-worked)
#   WORK_TICKET_CREATED_LABEL       provenance label of work-ticket sub-tickets (agent-created)
#   CREATE_TICKET_LABEL             provenance label of /create-ticket tickets (agent-drafted)
#   WORK_TICKET_AGENT_LABEL_RE      regex tagging a ticket/MR/Drive file as agent-owned (^agent-)
#   WORK_TICKET_LABELED_DECISION    decision for writes to agent-labelled tickets (allow|ask)
#   WORK_TICKET_BASE_BRANCH_RE      default/base branches (^(master|main)$): sub MRs never
#                                   target them and pushes to them deny
#   WORK_TICKET_ALLOW_DEFAULT_PUSH_RE  regex on the repo top-level path; when it matches, a push
#                                   to a default branch asks instead of denying (personal repos)
#   WORK_TICKET_ALLOW_TRANSITION=1  jira transition on a purely human ticket asks instead of
#                                   denying (repos whose own workflow transitions tickets)
#   WORK_TICKET_KEY_IN_BRANCH=1     reserved: declares that the repo puts ticket keys in branch
#                                   names/commits; accepted, no behavioural change today
#   WORK_TICKET_JIRA_PY / WORK_TICKET_GLAB / WORK_TICKET_GH / WORK_TICKET_GDOC_PY  client paths
#                                   (tests: stubs; WORK_TICKET_GH defaults to `gh` on PATH; the
#                                   python clients default to <hooks dir>/../skills/<skill>/scripts/)
#   HARNESS_JIRA_LINK_TYPES_RE      allowed `jira link` types, lowercased (jira.link_types)
#   HARNESS_CRED_EXTRA_RE           extra credential path regex, denied for readers like the
#                                   built-in list (credentials.extra_paths_re; empty = none)
#   HARNESS_TICKET_EXAMPLE          example key shown in reasons (core.ticket_example, PROJ-123)
#   HARNESS_GUARD_ENV               path of the env file parsed at start (default <hooks dir>/guard.env)
#   GUARD_KUBECTL / GUARD_GIT       kubectl / git binaries the hook shells out to (tests: stubs)
#   K8S_PROD_RE                     regex marking prod contexts/namespaces (same as the k8s CLI)
set -uo pipefail

# >>> hn_timeout
hn_timeout() {  # SECS CMD [ARGS...]
  local s=$1; shift
  if command -v timeout >/dev/null 2>&1; then timeout "$s" "$@"
  elif command -v gtimeout >/dev/null 2>&1; then gtimeout "$s" "$@"
  else
    python3 -c 'import subprocess, sys
try:
    sys.exit(subprocess.call(sys.argv[2:], timeout=float(sys.argv[1])))
except subprocess.TimeoutExpired:
    sys.exit(124)
except OSError:
    sys.exit(127)' "$s" "$@"
  fi
}
# <<< hn_timeout

# ---- guard.env: rendered config (build/guard.env → <hooks dir>/guard.env) ----------
# Flat `KEY=value` lines; blank lines and `# comments` are skipped; a value may be wrapped in
# single quotes (POSIX style, `'\''` for a literal quote) or double quotes (no escapes). The
# file is PARSED, never sourced (no code runs from it). A variable that is already set in the
# environment WINS over the file, so repo-level `.claude/settings.json` env overrides keep
# working. Only keys with a known prefix are accepted (WORK_TICKET_ HARNESS_ K8S_ GUARD_ JIRA_
# GDOC_ CREATE_TICKET_), so the file can never inject BASH_ENV, LD_*, PATH and the like.
# HARNESS_GUARD_ENV overrides the path (tests point it at an empty file). Builtins only here:
# this runs before the jq check, which must still fail closed on a bare PATH.
_gs="${BASH_SOURCE[0]:-$0}"
case "$_gs" in */*) GUARD_DIR=${_gs%/*} ;; *) GUARD_DIR=. ;; esac
GUARD_DIR=$(cd "$GUARD_DIR" 2>/dev/null && pwd) || GUARD_DIR=.
_ge="${HARNESS_GUARD_ENV:-$GUARD_DIR/guard.env}"
if [ -r "$_ge" ]; then
  while IFS= read -r _gl || [ -n "$_gl" ]; do
    case "$_gl" in ''|'#'*) continue ;; esac
    _gk=${_gl%%=*}; _gv=${_gl#*=}
    [ "$_gk" != "$_gl" ] || continue
    case "$_gk" in ''|[0-9]*|*[!A-Za-z0-9_]*) continue ;; esac
    case "$_gk" in WORK_TICKET_*|HARNESS_*|K8S_*|GUARD_*|JIRA_*|GDOC_*|CREATE_TICKET_*) ;; *) continue ;; esac
    [ -z "${!_gk+x}" ] || continue
    case "$_gv" in
      \'*\') _gv=${_gv#\'}; _gv=${_gv%\'}; _gq="'\\''"; _gv=${_gv//"$_gq"/\'} ;;
      \"*\") _gv=${_gv#\"}; _gv=${_gv%\"} ;;
    esac
    export "$_gk=$_gv"
  done < "$_ge"
fi
unset _ge _gl _gk _gv _gq _gs

input=$(cat)
if command -v jq >/dev/null 2>&1; then
  # Fail closed on malformed input: valid JSON without a command passes, unparsable JSON denies.
  if ! cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // empty' 2>/dev/null); then
    printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"guard-bash(user): malformed hook input (not JSON) — denied (fail closed)"}}'
    exit 0
  fi
else
  printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"guard-bash(user): jq not installed — install jq; every Bash command is denied until then"}}'
  exit 0
fi
[ -n "$cmd" ] || exit 0
flat=$(printf '%s' "$cmd" | tr '\n' ' ' | tr -s ' ')
cwd=$(printf '%s' "$input" | jq -r '.cwd // empty' 2>/dev/null)
cwd_base=$(basename -- "${cwd:-/}")
in_sub_worktree=false; printf '%s' "$cwd_base" | grep -qE '_[^/]*-sub-' && in_sub_worktree=true

decide() {  # $1 = allow|ask|deny, $2 = reason
  jq -cn --arg d "$1" --arg reason "guard-bash(user): $2" \
    '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:$d,permissionDecisionReason:$reason}}'
  exit 0
}
ask()   { decide ask   "$1 — requires explicit user confirmation"; }
allow() { [ -z "${deferred:-}" ] || ask "$deferred"; decide allow "$1"; }   # never allow over a deferred ask
deny()  { decide deny  "$1"; }
# Deferred decisions: gated rules record the first ask reason instead of exiting, so a later deny
# in the same command still wins; allow() refuses to allow over it and the script end flushes it.
# Creates / clean write gates record pending_allow, emitted at the very end (after every section).
deferred=""; pending_allow=""
defer() { [ -n "$deferred" ] || deferred="$1"; }

# ---- Shared governance config -----------------------------------------------------
GOV_LABEL="${WORK_TICKET_LABEL:-agent-worked}"                 # Jira: grants promptless writes
CREATED_LABEL="${WORK_TICKET_CREATED_LABEL:-agent-created}"    # Jira: work-ticket sub-tickets
DRAFTED_LABEL="${CREATE_TICKET_LABEL:-agent-drafted}"          # Jira: create-ticket provenance (no rights)
AGENT_LABEL_RE="${WORK_TICKET_AGENT_LABEL_RE:-^agent-}"        # any agent-* label tags a ticket/MR as agent-owned → writes promptless
LABELED_DECISION="${WORK_TICKET_LABELED_DECISION:-allow}"
BASE_BRANCH_RE="${WORK_TICKET_BASE_BRANCH_RE:-^(master|main)$}"   # sub MRs must never target these
ALLOW_DEFAULT_PUSH_RE="${WORK_TICKET_ALLOW_DEFAULT_PUSH_RE:-}"   # repo top-level paths where a default-branch push asks
ALLOW_TRANSITION="${WORK_TICKET_ALLOW_TRANSITION:-}"            # =1: human-ticket transition asks instead of deny
# shellcheck disable=SC2034  # declared for the repo contract (header), read by no rule yet
KEY_IN_BRANCH="${WORK_TICKET_KEY_IN_BRANCH:-}"                  # reserved (no-op today)
KEY_RE='[A-Z][A-Z0-9_]*-[0-9]+'

# Normalised MR/PR/issue record used by gate_writes: {labels:[names], src, tgt, cross}
NORM_JQ='{labels: [(.labels // [])[] | if type == "object" then .name else . end], src: (.src // ""), tgt: (.tgt // ""), cross: (.cross // false)}'
# flag_val FLAGS_RE TEXT -> value of the first "--flag value" / "--flag=value" / "-f value" occurrence
flag_val() { printf '%s' "$2" | grep -oE -- "(^|[[:space:]])($1)[= ]+[\"']?[^\"' ]+" | head -1 | sed -E "s/^[[:space:]]*($1)[= ]+[\"']?//"; }
labels_have()     { printf '%s' "$1" | jq -e --arg l "$2" 'index($l) != null' >/dev/null 2>&1; }
labels_match_re() { printf '%s' "$1" | jq -e --arg re "$2" 'any(.[]; test($re))' >/dev/null 2>&1; }
labels_have_write() { labels_match_re "$1" "$AGENT_LABEL_RE"; }

# shell_words STR -> one word per line, quotes removed ('…', "…", \x). An unquoted '#' at word
# start ends the input (a shell comment: `gh pr edit #1 …` never passes 1 — gh would act on the
# current branch's PR); '<<' ends it too (the heredoc body follows in $flat); other redirections
# drop their target word. rc 1 on an unbalanced quote (callers then ask/deny, never allow).
shell_words() {
  local LC_ALL=C s="$1" n=${#1} i=0 c w="" inw=0 q="" drop=0
  while [ "$i" -lt "$n" ]; do
    c=${s:i:1}; i=$((i+1))
    if [ -n "$q" ]; then
      if [ "$c" = "$q" ]; then q=""
      elif [ "$q" = '"' ] && [ "$c" = '\' ] && [ "$i" -lt "$n" ]; then w+=${s:i:1}; i=$((i+1))
      else w+=$c; fi
      continue
    fi
    case "$c" in
      ' '|$'\t')
        if [ "$inw" = 1 ]; then
          if [ "$drop" = 1 ]; then drop=0; else printf '%s\n' "$w"; fi
          w=""; inw=0
        fi ;;
      "'"|'"') q=$c; inw=1 ;;
      '\') w+=${s:i:1}; i=$((i+1)); inw=1 ;;
      '#') if [ "$inw" = 1 ]; then w+=$c; else break; fi ;;
      '<'|'>')
        if [ "$c" = '<' ] && [ "${s:i:1}" = '<' ]; then inw=0; break; fi   # heredoc / herestring
        if [ "$inw" = 1 ]; then
          case "$w" in *[!0-9]*) printf '%s\n' "$w" ;; esac                  # '2>' : drop the fd number
          w=""; inw=0
        fi
        while [ "${s:i:1}" = '>' ]; do i=$((i+1)); done
        drop=1 ;;
      *) w+=$c; inw=1 ;;
    esac
  done
  [ -z "$q" ] || return 1
  if [ "$inw" = 1 ] && [ "$drop" = 0 ]; then printf '%s\n' "$w"; fi
  return 0
}

# sub_create_rules KIND SRC TGT — stacked delivery for MR/PR creates whose source/head is a -sub-
# branch: no target → deny, $VAR target → ask (deferred), target ∈ BASE_BRANCH_RE → deny.
sub_create_rules() {
  case "$2" in *-sub-*) ;; *) return 0 ;; esac
  [ -n "$3" ] || deny "sub $1 ($2) without a target/base branch — sub ${1}s target the ticket branch (or their blocker's sub branch), never the base"
  case "$3" in *'$'*) defer "sub $1 ($2) with a \$VAR target — use a literal branch name"; return 0 ;; esac
  if printf '%s' "$3" | grep -qE "$BASE_BRANCH_RE"; then
    deny "sub $1 ($2) must not target $3 — target the ticket branch (stacked delivery; humans merge bottom-up)"
  fi
  return 0
}

# gate_writes CLAUSE_RE FETCH_FN LABEL_FLAG_RE RETARGET_FLAG_RE STATE_VERB_RE BOOL_FLAG_RE KIND SIGIL
# Label gate for writes to existing MRs/PRs/issues (glab mr update|note|close, gh pr …, gh issue …).
# CLAUSE_RE matches up to and including the verb (an -R/--repo inside it scopes the lookup, as does
# one after the verb). Per clause: every positional ref is gated; $VAR refs ask; a clause whose only
# flags are LABEL_FLAG_RE with agent-* values is free; FETCH_FN REF REPO → normalised JSON (fail →
# ask); a -sub- src retargeted (RETARGET_FLAG_RE) to BASE_BRANCH_RE denies ($VAR → ask);
# cross-repository (fork) PRs ask; unlabelled refs ask — or deny for STATE_VERB_RE (ask under
# WORK_TICKET_ALLOW_TRANSITION=1). Asks are deferred; a clean gate records pending_allow.
gate_writes() {
  local cre="$1" fetch="$2" lre="$3" rre="$4" sre="$5" bre="$6" kind="$7" sig="$8"
  local n_cmds n_seen=0 clause head verb repo rest words tok f v i ref r mj ml msrc mcross rtgt labelonly hint
  local -a toks refs lbls
  printf '%s' "$flat" | grep -qE "$cre" || return 0
  n_cmds=$(printf '%s' "$flat" | grep -oE "$cre" | wc -l)
  while IFS= read -r clause; do
    [ -n "$clause" ] || continue
    n_seen=$((n_seen+1))
    head=$(printf '%s' "$clause" | grep -oE "^$cre" | head -1)
    verb=$(printf '%s' "$head" | awk '{print $NF}')
    repo=$(flag_val '-R|--repo' "$head")
    rest=${clause:${#head}}
    words=$(shell_words "$rest") || { defer "$kind $verb — could not parse the command line (unbalanced quotes)"; continue; }
    toks=(); [ -z "$words" ] || while IFS= read -r _w; do toks+=("$_w"); done <<<"$words"
    refs=(); lbls=(); rtgt=""; labelonly=true; i=0
    while [ "$i" -lt "${#toks[@]}" ]; do
      tok=${toks[i]}; i=$((i+1))
      case "$tok" in
        --*=*) f=${tok%%=*}; v=${tok#*=} ;;
        -?*)   f=$tok; v=""
               if [ -z "$bre" ] || ! printf '%s' "$f" | grep -qE "$bre"; then v=${toks[i]:-}; i=$((i+1)); fi ;;
        *)     refs+=("$tok"); continue ;;
      esac
      case "$f" in -R|--repo) repo=$v; continue ;; esac
      if [ -n "$lre" ] && printf '%s' "$f" | grep -qE "$lre"; then
        while IFS= read -r r; do [ -n "$r" ] && lbls+=("$r"); done <<<"$(printf '%s' "$v" | tr ',' '\n' | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
      else
        labelonly=false
      fi
      if [ -n "$rre" ] && printf '%s' "$f" | grep -qE "$rre"; then rtgt=$v; fi
    done
    [ "${#refs[@]}" -gt 0 ] || { defer "$kind $verb without an explicit ref — pass the number so its labels can be checked"; continue; }
    for ref in "${refs[@]}"; do
      case "$ref" in *'$'*) defer "$kind $verb on \$VAR — use a literal number"; continue 2 ;; esac
    done
    case "$repo" in *'$'*) defer "$kind $verb with a \$VAR repo — use a literal owner/repo"; continue ;; esac
    if $labelonly && [ "${#lbls[@]}" -gt 0 ] && ! printf '%s\n' "${lbls[@]}" | grep -vqE "$AGENT_LABEL_RE"; then
      continue   # labelling only with agent-* labels → free
    fi
    for ref in "${refs[@]}"; do
      r=${ref#\#}
      case "$kind" in
        "glab mr") hint="glab mr update $r --label $GOV_LABEL" ;;
        *)         hint="$kind edit $r --add-label $GOV_LABEL" ;;
      esac
      mj=$("$fetch" "$ref" "$repo") || { defer "$kind $verb $sig$r — could not read it ($kind view failed: auth/timeout/not found)"; continue; }
      ml=$(jq -c '.labels' <<<"$mj"); msrc=$(jq -r '.src' <<<"$mj"); mcross=$(jq -r '.cross' <<<"$mj")
      # retargeting a -sub- MR/PR to master|main is always wrong (auto-retarget misfire or a mistake)
      if [ -n "$rtgt" ] && printf '%s' "$msrc" | grep -q -- '-sub-'; then
        case "$rtgt" in *'$'*) defer "retarget of sub $kind $sig$r to a \$VAR — use a literal branch name"; continue ;; esac
        if printf '%s' "$rtgt" | grep -qE "$BASE_BRANCH_RE"; then
          deny "retarget of sub $kind $sig$r ($msrc) to $rtgt refused — sub MRs/PRs target the ticket branch; retarget there instead"
        fi
      fi
      if [ "$mcross" = true ]; then defer "$kind $verb $sig$r — cross-repository (fork) PR; edits there ask"; continue; fi
      if ! labels_match_re "$ml" "$AGENT_LABEL_RE"; then
        if [ -n "$sre" ] && printf '%s' "$verb" | grep -qE "$sre"; then
          if [ "$ALLOW_TRANSITION" = 1 ]; then
            defer "$kind $verb $sig$r — human issue; state change allowed in this repo by WORK_TICKET_ALLOW_TRANSITION=1"; continue
          fi
          deny "$kind $verb $sig$r refused — human-written issue state (close/reopen) is operated by humans only"
        fi
        defer "$kind $verb $sig$r — not agent-labelled (label it first: $hint)"
        continue
      fi
      [ "$LABELED_DECISION" = allow ] || defer "$kind $verb $sig$r (agent-labelled; WORK_TICKET_LABELED_DECISION=$LABELED_DECISION)"
    done
  done <<EOF
$(printf '%s' "$flat" | grep -oE "${cre}[^;&|]*")
EOF
  [ "$n_seen" -ge "$n_cmds" ] || defer "$kind mutation — could not parse every clause"
  pending_allow="$kind mutation(s) on agent-labelled ref(s)"
}
