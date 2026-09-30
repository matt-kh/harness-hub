#!/usr/bin/env bash
# Private-identifier gate: fail when tracked content, file names, commit messages or commit
# author/committer emails carry organisation- or person-specific identifiers.
#
# Two pattern sources:
#   public   tools/gate/patterns.public.txt (generic shapes: home dirs, IPs, emails, tokens…)
#   private  a denylist that never enters this repo, one case-insensitive ERE per line:
#              $GATE_PRIVATE_DENYLIST (contents, multi-line; CI passes a repository secret), else
#              ${HARNESS_GATE_PRIVATE:-$HARNESS_HOME/local/gate-denylist.txt}
#
# Usage: private-ids.sh [--ci] [--no-private] [--range A..B]
#                       [--staged | --files F... | --commit-msg-file F | --no-tree]
#   (default)            every tracked + untracked-not-ignored file, contents and names
#   --staged             files staged in the index (working-tree content; pre-commit stashes
#                        unstaged changes, so they are the same under the framework)
#   --files F...         only these files (remaining arguments)
#   --commit-msg-file F  commit-msg hook: the message in F plus the configured author email
#   --range A..B         also every commit in A..B: message, author email, committer email
#   --no-tree            skip file contents and names (use with --range)
#   --ci                 never print private text: private hits show as `private#<n>` and
#                        non-noreply emails are not echoed
#   --no-private         public patterns only
# Output: path:line: public:<id>: <text>   |   path:line: private#<n>[: <text> outside --ci]
#         file-name hits use line 0; commit hits use `commit:<sha7>` as the path.
# Exit: 0 clean, 1 hits, 2 usage/setup error.
#
# Suppression (public hits only; private hits are never suppressible):
#   tools/gate/allowlist.txt rows `path-ERE<TAB>line-ERE<TAB>reason`
#   inline `# gate-allow: <reason>` or `<!-- gate-allow: <reason> -->` on the offending line
#
# Portability: bash 3.2, POSIX grep -E / sed / awk only (no grep -P, no mapfile, no assoc arrays).
set -o pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
PUBLIC_FILE="$HERE/patterns.public.txt"
ALLOW_FILE="$HERE/allowlist.txt"

ci=false; use_private=true; mode=tree; range=""; msg_file=""; scan_tree=true
files=()
usage() { sed -n '2,33p' "$0" | sed 's/^# \{0,1\}//'; }
while [ $# -gt 0 ]; do
  case "$1" in
    --ci) ci=true ;;
    --no-private) use_private=false ;;
    --staged) mode=staged ;;
    --no-tree) scan_tree=false ;;
    --range) shift; [ $# -gt 0 ] || { echo "gate: --range needs A..B" >&2; exit 2; }; range=$1 ;;
    --range=*) range=${1#--range=} ;;
    --commit-msg-file) shift; [ $# -gt 0 ] || { echo "gate: --commit-msg-file needs a path" >&2; exit 2; }
      mode=msg; msg_file=$1 ;;
    --files) mode=files; shift; while [ $# -gt 0 ]; do files[${#files[@]}]=$1; shift; done; break ;;
    -h|--help) usage; exit 0 ;;
    *) echo "gate: unknown argument: $1 (see --help)" >&2; exit 2 ;;
  esac
  shift
done

command -v git >/dev/null 2>&1 || { echo "gate: git not found" >&2; exit 2; }
ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || ROOT=$(cd "$HERE/../.." && pwd)
cd "$ROOT" || exit 2
HARNESS_HOME=${HARNESS_HOME:-$(cd "$HERE/../.." && pwd)}

TMP=$(mktemp -d "${TMPDIR:-/tmp}/gate.XXXXXX") || exit 2
chmod 700 "$TMP"
trap 'rm -rf "$TMP"' EXIT
HITS="$TMP/hits"; : >"$HITS"

# ---- load patterns ------------------------------------------------------------------
pub_id=(); pub_re=(); pub_ex=()
cur_id=""; cur_ex=""
while IFS= read -r line || [ -n "$line" ]; do
  case "$line" in
    '# id:'*) cur_id=$(printf '%s' "${line#\# id:}" | sed 's/^ *//; s/ *$//') ;;
    '# except:'*) cur_ex=$(printf '%s' "${line#\# except:}" | sed 's/^ *//') ;;
    '#'*|'') ;;
    *) n=${#pub_re[@]}
       pub_re[n]=$line; pub_id[n]=${cur_id:-p$((n + 1))}; pub_ex[n]=$cur_ex
       cur_id=""; cur_ex="" ;;
  esac
done <"$PUBLIC_FILE"

PRIV="$TMP/private"; : >"$PRIV"
if $use_private; then
  if [ -n "${GATE_PRIVATE_DENYLIST:-}" ]; then
    printf '%s\n' "$GATE_PRIVATE_DENYLIST" >"$PRIV"
  else
    pf=${HARNESS_GATE_PRIVATE:-$HARNESS_HOME/local/gate-denylist.txt}
    [ -r "$pf" ] && cat "$pf" >"$PRIV"
  fi
fi
priv_re=()
while IFS= read -r line || [ -n "$line" ]; do
  line=$(printf '%s' "$line" | tr -d '\r')
  case "$line" in '#'*|'') continue ;; esac
  priv_re[${#priv_re[@]}]=$line
done <"$PRIV"
if [ ${#priv_re[@]} -eq 0 ]; then
  if $use_private; then echo "gate: private list unavailable — public patterns only" >&2; fi
fi

# a pattern grep cannot compile would silently match nothing: refuse to run instead
valid_ere() { printf 'x\n' | grep -qE -e "$1" 2>/dev/null; [ $? -ne 2 ]; }
i=0; while [ $i -lt ${#pub_re[@]} ]; do
  valid_ere "${pub_re[i]}" || { echo "gate: public pattern ${pub_id[i]} is not a valid ERE" >&2; exit 2; }
  i=$((i + 1)); done
i=0; while [ $i -lt ${#priv_re[@]} ]; do
  valid_ere "${priv_re[i]}" || { echo "gate: private#$((i + 1)) is not a valid ERE" >&2; exit 2; }
  i=$((i + 1)); done

allow_path=(); allow_line=()
if [ -r "$ALLOW_FILE" ]; then
  tab=$(printf '\t')
  while IFS="$tab" read -r a b c || [ -n "$a" ]; do
    case "$a" in '#'*|'') continue ;; esac
    [ -n "$b" ] && [ -n "$c" ] || { echo "gate: allowlist row without line-ERE/reason: $a" >&2; exit 2; }
    allow_path[${#allow_path[@]}]=$a; allow_line[${#allow_line[@]}]=$b
  done <"$ALLOW_FILE"
fi

# ---- helpers ------------------------------------------------------------------------
trim() {  # strip the boundary characters the portable patterns may capture
  printf '%s' "$1" | sed 's/^[^A-Za-z0-9/.@_+%-]//; s/[^A-Za-z0-9/._%+-]$//'
}
allowlisted() {  # $1 path, $2 text of the line (or the path/address itself)
  local i=0
  while [ $i -lt ${#allow_path[@]} ]; do
    if printf '%s\n' "$1" | grep -qE -e "${allow_path[i]}" &&
       printf '%s\n' "$2" | grep -qE -e "${allow_line[i]}"; then return 0; fi
    i=$((i + 1))
  done
  return 1
}
inline_allowed() { printf '%s\n' "$1" | grep -qE 'gate-allow:[[:space:]]*[^[:space:]-]'; }
gate_file() {  # the gate's own pattern files necessarily contain the public shapes
  case "$1" in tools/gate/patterns.public.txt|tools/gate/allowlist.txt) return 0 ;; esac
  return 1
}
emit_public() { printf '%s:%s: public:%s: %s\n' "$1" "$2" "$3" "$4" >>"$HITS"; }
emit_private() {
  if $ci; then printf '%s:%s: private#%s\n' "$1" "$2" "$3" >>"$HITS"
  else printf '%s:%s: private#%s: %s\n' "$1" "$2" "$3" "$4" >>"$HITS"; fi
}

# scan_list LISTFILE LABEL_MODE : grep every pattern over the NUL-separated file list.
# LABEL_MODE=file  → report path:line;  anything else is used as a literal label prefix.
scan_contents() {
  local list=$1 label=$2 i out f rest n m text
  [ -s "$list" ] || return 0
  i=0
  while [ $i -lt ${#pub_re[@]} ]; do
    out="$TMP/out"
    xargs -0 grep -HnoIE -e "${pub_re[i]}" -- /dev/null <"$list" >"$out" 2>/dev/null
    while IFS= read -r l; do
      f=${l%%:*}; rest=${l#*:}; n=${rest%%:*}; m=${rest#*:}
      [ "$label" = file ] && gate_file "$f" && continue
      if [ -n "${pub_ex[i]}" ] && printf '%s\n' "$(trim "$m")" | grep -qE -e "${pub_ex[i]}"; then continue; fi
      text=$(sed -n "${n}p" "$f")
      inline_allowed "$text" && continue
      if [ "$label" = file ]; then allowlisted "$f" "$text" && continue; emit_public "$f" "$n" "${pub_id[i]}" "$(trim "$m")"
      else emit_public "$label" "$n" "${pub_id[i]}" "$(trim "$m")"; fi
    done <"$out"
    i=$((i + 1))
  done
  i=0
  while [ $i -lt ${#priv_re[@]} ]; do
    out="$TMP/out"
    xargs -0 grep -HnoIiE -e "${priv_re[i]}" -- /dev/null <"$list" >"$out" 2>/dev/null
    while IFS= read -r l; do
      f=${l%%:*}; rest=${l#*:}; n=${rest%%:*}; m=${rest#*:}
      if [ "$label" = file ]; then emit_private "$f" "$n" "$((i + 1))" "$m"
      else emit_private "$label" "$n" "$((i + 1))" "$m"; fi
    done <"$out"
    i=$((i + 1))
  done
}

scan_names() {  # $1 newline-separated path list
  local names=$1 i out n m p
  [ -s "$names" ] || return 0
  i=0
  while [ $i -lt ${#pub_re[@]} ]; do
    grep -noE -e "${pub_re[i]}" "$names" >"$TMP/nout" 2>/dev/null
    while IFS= read -r l; do
      n=${l%%:*}; m=${l#*:}; p=$(sed -n "${n}p" "$names")
      if [ -n "${pub_ex[i]}" ] && printf '%s\n' "$(trim "$m")" | grep -qE -e "${pub_ex[i]}"; then continue; fi
      allowlisted "$p" "$p" && continue
      emit_public "$p" 0 "${pub_id[i]}" "$(trim "$m") (file name)"
    done <"$TMP/nout"
    i=$((i + 1))
  done
  i=0
  while [ $i -lt ${#priv_re[@]} ]; do
    grep -noiE -e "${priv_re[i]}" "$names" >"$TMP/nout" 2>/dev/null
    while IFS= read -r l; do
      n=${l%%:*}; m=${l#*:}; p=$(sed -n "${n}p" "$names")
      if $ci; then emit_private "file name #$n" 0 "$((i + 1))" ""; else emit_private "$p" 0 "$((i + 1))" "$m (file name)"; fi
    done <"$TMP/nout"
    i=$((i + 1))
  done
}

check_email() {  # $1 label, $2 role (author|committer), $3 address
  local label=$1 role=$2 addr=$3 i=0 hit=false
  while [ $i -lt ${#priv_re[@]} ]; do
    if printf '%s\n' "$addr" | grep -qiE -e "${priv_re[i]}"; then
      emit_private "$label" "$role-email" "$((i + 1))" "$addr"; hit=true
    fi
    i=$((i + 1))
  done
  $hit && return 0
  printf '%s\n' "$addr" | grep -qE 'users\.noreply\.github\.com$' && return 0
  allowlisted "@email" "$addr" && return 0
  if $ci; then printf '%s:%s-email: not a users.noreply.github.com address\n' "$label" "$role" >>"$HITS"
  else printf '%s:%s-email: not a users.noreply.github.com address: %s\n' "$label" "$role" "$addr" >>"$HITS"; fi
}

scan_message_file() {  # $1 file, $2 label
  printf '%s\0' "$1" >"$TMP/msglist"
  scan_contents "$TMP/msglist" "$2"
}

# ---- file set -----------------------------------------------------------------------
LIST="$TMP/list"; NAMES="$TMP/names"; : >"$LIST"; : >"$NAMES"
add_file() { [ -f "$1" ] && [ ! -L "$1" ] || return 0; printf '%s\0' "$1" >>"$LIST"; printf '%s\n' "$1" >>"$NAMES"; }
case "$mode" in
  tree)
    git ls-files -z --cached --others --exclude-standard >"$TMP/all" 2>/dev/null
    while IFS= read -r -d '' f; do add_file "$f"; done <"$TMP/all" ;;
  staged)
    git diff --cached --name-only -z --diff-filter=ACMR >"$TMP/all" 2>/dev/null
    while IFS= read -r -d '' f; do add_file "$f"; done <"$TMP/all" ;;
  files)
    for f in ${files[@]+"${files[@]}"}; do add_file "${f#./}"; done ;;
  msg) scan_tree=false ;;
esac
# the list/names temp files may contain duplicates from --cached + --others; harmless.

if $scan_tree; then
  scan_contents "$LIST" file
  scan_names "$NAMES"
fi

# ---- commit message hook --------------------------------------------------------------
if [ "$mode" = msg ]; then
  [ -r "$msg_file" ] || { echo "gate: cannot read $msg_file" >&2; exit 2; }
  sed 's/^#.*//' "$msg_file" >"$TMP/msg"          # git strips comment lines by default
  scan_message_file "$TMP/msg" "commit-msg"
  ident=$(git var GIT_AUTHOR_IDENT 2>/dev/null | sed -n 's/.*<\([^>]*\)>.*/\1/p')
  [ -n "$ident" ] && check_email "commit-msg" author "$ident"
fi

# ---- commit range -------------------------------------------------------------------
if [ -n "$range" ]; then
  a=${range%%..*}; b=${range#*..}; [ "$b" = "$range" ] && b=HEAD; [ -n "$b" ] || b=HEAD
  if printf '%s' "$a" | grep -qE '^0+$' || [ -z "$a" ]; then
    revs=$(git rev-list "$b" 2>/dev/null)
  elif git cat-file -e "$a^{commit}" 2>/dev/null; then
    revs=$(git rev-list "$a..$b" 2>/dev/null)
  else
    echo "gate: range start $a not in this clone — checking $b only" >&2
    revs=$(git rev-parse "$b" 2>/dev/null)
  fi
  for c in $revs; do
    s=$(printf '%s' "$c" | cut -c1-7)
    git log -1 --format=%B "$c" >"$TMP/msg"
    scan_message_file "$TMP/msg" "commit:$s"
    check_email "commit:$s" author "$(git log -1 --format=%ae "$c")"
    check_email "commit:$s" committer "$(git log -1 --format=%ce "$c")"
  done
fi

# ---- report -------------------------------------------------------------------------
if [ -s "$HITS" ]; then
  sort -u "$HITS"
  echo "gate: $(sort -u "$HITS" | wc -l | tr -d ' ') hit(s). Public hits: rename to a documentation value, or add" >&2
  echo "      '# gate-allow: <reason>' / a tools/gate/allowlist.txt row. Private hits: rename; never allowlist." >&2
  exit 1
fi
echo "gate: clean (public ${#pub_re[@]} patterns, private ${#priv_re[@]} patterns)" >&2
exit 0
