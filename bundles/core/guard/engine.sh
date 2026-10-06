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
# ---- Repository-level declaration (principle 8: user-level by design) ----------------
# This hook is a user-level baseline. Hooks stack and the most restrictive decision wins, so a
# repository's own hook cannot lift a deny made here; instead the guard yields from inside. It
# resolves the repository root from the hook's cwd (first ancestor holding .git, no git call;
# not from the command's target: `git -C other push` is judged under the cwd's declaration) and
# parses <root>/.harness.toml (a TOML subset, at most 16 KiB and 400 lines; never sourced, fail
# open on anything else):
#   [owns] domains = [...] / components = [...]   every section whose taxonomy id or domain is
#                                   listed returns before deciding anything (pass: the provider and
#                                   the repository's own harness decide)
#   [overrides] NAME = "value"      only WORK_TICKET_* names declared by a `# repo-override:`
#                                   comment in some section (docs/reference/hook-policy.md#repo-overrides)
# Precedence per key: real environment (e.g. .claude/settings.json "env") > .harness.toml
# [overrides] > guard.env > the default below. Never repo-settable (client/engine paths, the
# credential regex; only the developer's own environment sets them): HARNESS_GUARD_ENV
# HARNESS_CRED_EXTRA_RE GUARD_GIT GUARD_KUBECTL WORK_TICKET_JIRA_PY WORK_TICKET_GLAB
# WORK_TICKET_GH WORK_TICKET_GDOC_PY, and every name matching *_PY, GUARD_*, HARNESS_*, *CRED*.
# Never yields (the developer's own credentials are not the repository's to lift):
# core/guard.d/20-credentials (REPO_NEVER_YIELDS below) and the rules a section places in a
# `# never-yields:` prelude above its repo_owns line: commands that print stored credentials
# (gh auth token, gh auth status --show-token, gh config get oauth_token, kubectl config view
# --raw) and shell writes to .harness.toml (ask: the agent never authorises itself).
#
# ---- Override env vars (read at run time) ------------------------------------------
# Set by the real environment (a repository's provider env, e.g. `.claude/settings.json` →
# "env": {...}), by .harness.toml [overrides] (allow-listed names only) or by guard.env.
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
#   WORK_TICKET_KEY_IN_BRANCH=1     the repo puts ticket keys in branch names/commit subjects:
#                                   section 75 (ticket-workflow) then lets key-named branches and
#                                   key-prefixed subjects pass instead of asking
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
_genv_keys=""
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
    _genv_keys="$_genv_keys $_gk"
  done < "$_ge"
fi
REPO_GENV_KEYS="${_genv_keys:-} "     # keys guard.env set: a .harness.toml override may replace them
GUARD_SELF="$GUARD_DIR/${_gs##*/}"    # this file (absolute): the `# repo-override:` allow-list is read from it
unset _ge _gl _gk _gv _gq _gs _genv_keys

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

# ---- Repository-level declaration: <repo root>/.harness.toml (principle 8) ------------
# See the header. Fail open everywhere: an unreadable, oversized (> 16 KiB or > 400 lines) or
# malformed file (or line) changes nothing and prints one note on stderr per ignored line (at
# most 5, then a count).
REPO_NEVER_YIELDS='core/guard.d/20-credentials'
REPO_OVERRIDE_DENY='HARNESS_GUARD_ENV HARNESS_CRED_EXTRA_RE GUARD_GIT GUARD_KUBECTL WORK_TICKET_JIRA_PY WORK_TICKET_GLAB WORK_TICKET_GH WORK_TICKET_GDOC_PY'
REPO_ROOT=""; REPO_DECL=""; REPO_OWNS_IDS=""; REPO_OWNS_DOMAINS=""; REPO_SET=""; REPO_OVERRIDE_NAMES=""; REPO_NOTES=0
# >>> hrepo
hrepo_root() {  # [DIR] -> first ancestor holding .git (dir or worktree file); rc 1 outside a checkout
  local d="${1:-$PWD}" n=0
  case "$d" in /*) ;; *) return 1 ;; esac
  while [ -n "$d" ] && [ "$n" -lt 64 ]; do
    if [ -e "$d/.git" ]; then printf '%s\n' "$d"; return 0; fi
    d=${d%/*}; n=$((n+1))
  done
  return 1
}
hrepo_file() {  # [DIR] -> <root>/.harness.toml; rc 1 when absent
  local r; r=$(hrepo_root "${1:-}") || return 1
  [ -f "$r/.harness.toml" ] && [ -r "$r/.harness.toml" ] || return 1
  printf '%s\n' "$r/.harness.toml"
}
hrepo_trim_to() {  # VAR STR -> VAR = STR without surrounding whitespace (printf -v: no subshell per line)
  local _hs="$2"
  _hs="${_hs#"${_hs%%[![:space:]]*}"}"
  printf -v "$1" '%s' "${_hs%"${_hs##*[![:space:]]}"}"
}
hrepo_unquote_to() {  # VAR STR -> VAR = x for "x" | 'x'; rc 1 on anything else (no escapes in the subset)
  local _hv
  case "$2" in
    \"*\") _hv=${2#\"}; _hv=${_hv%\"}; case "$_hv" in *[\"\\]*) return 1 ;; esac ;;
    \'*\') _hv=${2#\'}; _hv=${_hv%\'}; case "$_hv" in *\'*) return 1 ;; esac ;;
    *) return 1 ;;
  esac
  printf -v "$1" '%s' "$_hv"
}
hrepo_get() {  # FILE SECTION KEY -> value(s), one per line; rc 1 when absent (first occurrence wins)
  local f="$1" want="$2" key="$3" sec="" line k v item rest out="" n=0 found=1 nl='
'
  [ -f "$f" ] && [ -r "$f" ] || return 1
  [ "$(($(wc -c < "$f")))" -le 16384 ] || return 1
  while IFS= read -r line || [ -n "$line" ]; do
    n=$((n+1)); [ "$n" -le 400 ] || return 1
    hrepo_trim_to line "$line"
    case "$line" in
      ''|'#'*) continue ;;
      '['*']') hrepo_trim_to sec "${line#\[}"; hrepo_trim_to sec "${sec%\]}"; continue ;;
      '['*) sec=""; continue ;;
    esac
    [ "$found" = 1 ] && [ "$sec" = "$want" ] || continue
    hrepo_trim_to k "${line%%=*}"
    [ "$k" != "$line" ] && [ "$k" = "$key" ] || continue
    hrepo_trim_to v "${line#*=}"
    case "$v" in
      '['*']')
        rest=${v#\[}; rest=${rest%\]}
        while [ -n "$rest" ]; do
          item=${rest%%,*}
          if [ "$item" = "$rest" ]; then rest=""; else rest=${rest#*,}; fi
          hrepo_trim_to item "$item"; [ -n "$item" ] || continue
          hrepo_unquote_to item "$item" || continue
          out="$out$item$nl"
        done ;;
      *) [ "$want" != owns ] || continue          # [owns] keys are arrays only
         hrepo_unquote_to v "$v" || continue; out="$v$nl" ;;
    esac
    found=0
  done < "$f"
  [ "$found" = 1 ] || printf '%s' "$out"
  return $found
}
hrepo_owns() {  # ID DOMAIN [DIR] -> rc 0 when the repository declares the component or its domain
  local f v nl='
'
  case "$1" in core/guard.d/20-credentials|core/permissions) return 1 ;; esac   # never yield
  f=$(hrepo_file "${3:-}") || return 1
  # no pipes: callers run under `set -o pipefail`, where an early `grep -q` exit is a SIGPIPE failure
  v=$(hrepo_get "$f" owns components 2>/dev/null)
  case "$nl$v$nl" in *"$nl$1$nl"*) return 0 ;; esac
  [ -n "${2:-}" ] || return 1
  v=$(hrepo_get "$f" owns domains 2>/dev/null)
  case "$nl$v$nl" in *"$nl$2$nl"*) return 0 ;; esac
  return 1
}
# <<< hrepo
repo_note() {  # LINE WHY -> one stderr note per ignored line; at most 5 per run, then a count
  REPO_NOTES=$((REPO_NOTES+1))
  [ "$REPO_NOTES" -le 5 ] || return 0
  echo "guard-bash(user): ${REPO_DECL:-.harness.toml}:$1 ignored ($2)" >&2
}
repo_override_names() {  # -> REPO_OVERRIDE_NAMES: every `# repo-override: NAME` of this guard, space-delimited
  [ -z "$REPO_OVERRIDE_NAMES" ] || return 0
  REPO_OVERRIDE_NAMES=" $(grep -oE '^# repo-override: [A-Z][A-Z0-9_]* ' "$GUARD_SELF" 2>/dev/null | awk '{print $3}' | sort -u | tr '\n' ' ')"
}
# Parse [owns] and [overrides] into locals first and apply them only after the whole file was
# read: a file over 16 KiB or 400 lines is ignored as a whole. No subshell per line (the hook
# has a time budget; a slow parse would time out and fail open). Overrides: allow-listed
# WORK_TICKET_* names only, exported unless the real environment set them.
repo_load_decl() {
  local sec="" n=0 line k v item rest list seen=" " ids="" doms="" sets="" kv nl='
'
  [ -n "${cwd:-}" ] || return 0                       # no cwd in the hook input: no lookup
  REPO_ROOT=$(hrepo_root "$cwd") || { REPO_ROOT=""; return 0; }
  [ -f "$REPO_ROOT/.harness.toml" ] && [ -r "$REPO_ROOT/.harness.toml" ] || return 0
  REPO_DECL="$REPO_ROOT/.harness.toml"
  if [ "$(($(wc -c < "$REPO_DECL")))" -gt 16384 ]; then
    echo "guard-bash(user): $REPO_DECL ignored (larger than 16 KiB; keep the declaration short)" >&2; REPO_DECL=""; return 0
  fi
  while IFS= read -r line || [ -n "$line" ]; do
    n=$((n+1))
    if [ "$n" -gt 400 ]; then
      echo "guard-bash(user): $REPO_DECL ignored (more than 400 lines; keep the declaration short)" >&2; REPO_DECL=""; return 0
    fi
    hrepo_trim_to line "$line"
    case "$line" in
      ''|'#'*) continue ;;
      '['*']') hrepo_trim_to sec "${line#\[}"; hrepo_trim_to sec "${sec%\]}"; continue ;;
      '['*) repo_note "$n" "unterminated section header"; sec=""; continue ;;
    esac
    hrepo_trim_to k "${line%%=*}"; hrepo_trim_to v "${line#*=}"
    if [ "$k" = "$line" ] || [ -z "$k" ]; then repo_note "$n" "not key = value"; continue; fi
    case "$k" in *[!A-Za-z0-9_]*) repo_note "$n" "bad key"; continue ;; esac
    case "$sec" in owns|overrides) ;; *) continue ;; esac
    case "$seen" in *" $sec.$k "*) repo_note "$n" "duplicate key $k in [$sec]; the first one counts"; continue ;; esac
    case "$sec" in
      owns)
        case "$v" in '['*']') ;; *) repo_note "$n" "$k must be a one-line array of strings (no inline comments)"; continue ;; esac
        case "$k" in domains|components) ;; *) repo_note "$n" "unknown [owns] key $k (domains, components)"; continue ;; esac
        rest=${v#\[}; rest=${rest%\]}; list=""
        while [ -n "$rest" ]; do
          item=${rest%%,*}
          if [ "$item" = "$rest" ]; then rest=""; else rest=${rest#*,}; fi
          hrepo_trim_to item "$item"; [ -n "$item" ] || continue
          hrepo_unquote_to item "$item" || { repo_note "$n" "unquoted or escaped array item"; continue; }
          case "$item" in ''|*[!A-Za-z0-9./_-]*) repo_note "$n" "bad id or domain '$item'"; continue ;; esac
          list="$list $item"
        done
        seen="$seen$sec.$k "
        if [ "$k" = domains ]; then doms="$doms$list"; else ids="$ids$list"; fi ;;
      overrides)
        hrepo_unquote_to v "$v" || { repo_note "$n" "$k must be a quoted string (no inline comments or escapes)"; continue; }
        seen="$seen$sec.$k "
        case " $REPO_OVERRIDE_DENY " in *" $k "*) repo_note "$n" "$k is settable only from your own environment, never from a repository"; continue ;; esac
        case "$k" in *_PY|GUARD_*|HARNESS_*|*CRED*) repo_note "$n" "$k is settable only from your own environment, never from a repository"; continue ;; esac
        case "$k" in WORK_TICKET_*) ;; *) repo_note "$n" "$k is not a repo override (only allow-listed WORK_TICKET_* names; see docs/reference/hook-policy.md#repo-overrides)"; continue ;; esac
        repo_override_names
        case "$REPO_OVERRIDE_NAMES" in *" $k "*) ;; *) repo_note "$n" "$k is not a repo override (see docs/reference/hook-policy.md#repo-overrides)"; continue ;; esac
        sets="$sets$k=$v$nl" ;;
    esac
  done < "$REPO_DECL"
  [ "$REPO_NOTES" -le 5 ] || echo "guard-bash(user): $REPO_DECL: $((REPO_NOTES-5)) more lines ignored (run 'harness repo' for the full list)" >&2
  REPO_OWNS_IDS=$ids; REPO_OWNS_DOMAINS=$doms
  # the real environment wins; a value that came from guard.env is replaced
  while [ -n "$sets" ]; do
    kv=${sets%%"$nl"*}; sets=${sets#*"$nl"}
    k=${kv%%=*}; v=${kv#*=}
    if [ -z "${!k+x}" ] || [ "${REPO_GENV_KEYS#* $k }" != "$REPO_GENV_KEYS" ]; then
      export "$k=$v"; REPO_SET="$REPO_SET $k"
    fi
  done
  return 0
}
repo_owns() {  # ID DOMAIN -> rc 0 when the repository declares the component or its domain (never credentials)
  [ -n "$REPO_DECL" ] || return 1
  case " $REPO_NEVER_YIELDS " in *" $1 "*) return 1 ;; esac
  case "$REPO_OWNS_IDS " in *" $1 "*) return 0 ;; esac
  case "$REPO_OWNS_DOMAINS " in *" $2 "*) return 0 ;; esac
  return 1
}
repo_load_decl

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
# shellcheck disable=SC2034  # read by section 75 (ticket-workflow) when that bundle is active
KEY_IN_BRANCH="${WORK_TICKET_KEY_IN_BRANCH:-}"                  # =1: key-named branches / key-prefixed subjects pass
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
  if printf '%s' "$3" | grep -qE -e "$BASE_BRANCH_RE"; then
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
        if printf '%s' "$rtgt" | grep -qE -e "$BASE_BRANCH_RE"; then
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
