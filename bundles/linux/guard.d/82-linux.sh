# shellcheck shell=bash

# Section 82 (bundle linux): Linux host definitions only — the clause lexer, ssh / scp / rsync
# option parsing, remote-command splitting and its read-only allow-list, block-device target
# detection and the prod matcher. The rules live in 83-linux-rules.sh, which calls these.
# (definitions only: no rules in this section; they are shared by 83-linux-rules.sh)
#
# How a command is read: the raw command ($cmd, newlines kept) is lexed once by awk into clauses
# split on ; & && || | newline ( ) { } — never inside quotes, so `ssh h 'ls; reboot'` stays one
# clause with its remote command intact. `$( )`, backticks, `<( )` and `>( )` are lexed again as
# clauses of their own (and stay in their parent's text); heredoc bodies are dropped unless a
# shell reads them (then each line is a clause), and kept as data lines (kind H when the heredoc
# writes a file: a `>` or tee; kind B otherwise). Each output line is `K<tab>text`: T a command,
# P a command whose output is piped on. A newline inside quotes becomes \002. The string of
# `sh|bash … -c` / `su -c` and the words of `eval` are lexed again (at most 8 times), so
# `sh -c "dd … of=/dev/sda"` is judged like the bare command.
# Words come from the engine's shell_words (quotes removed); the command word skips `!`,
# keywords, assignments and the wrappers sudo, doas, env, command, builtin, exec, nohup, nice,
# ionice, stdbuf, setsid, unbuffer, chrt, flock, timeout and xargs (xargs without -I/-J appends
# arguments from stdin: LXA).
# LINUX_PROD_RE (guard.env, linux.prod_re): case-insensitive ERE on the host alias marking
# production; reasons then carry [PROD].
LINUX_PROD="${LINUX_PROD_RE:-(^|[-_./:])(prod|production)([-_./:]|\$)}"
LINUX_TABC='	'
# words worth lexing for (on the command without quotes and backslashes, case-insensitive)
LINUX_PRE_RE='(^|[^[:alnum:]_.-])(ssh|scp|sftp|rsync|sshpass|ssh-copy-id|dd|wipefs|[sgc]?fdisk|sgdisk|parted|mkfs(\.[a-z0-9]+)?|mke2fs|mkswap|blkdiscard|cryptsetup|pv(create|remove|move)|vg(create|remove|reduce)|lv(create|remove|reduce|resize)|zpool|zfs|mdadm|nft|ufw|netplan|nmcli|ip|ip6?tables(-[a-z]+)?)([^[:alnum:]_-]|$)|/dev/|stricthostkeychecking|knownhostsfile'
# host-key checking switched off, in any spelling (-o X=Y, -oX=Y, -o "X Y", ssh_config lines)
LINUX_HKC_RE='stricthostkeychecking[[:space:]]*(=|[[:space:]])[[:space:]]*["'"'"']?(no|off|false)(["'"'"'[:space:];&|)]|$)'
LINUX_UKH_RE='userknownhostsfile[[:space:]]*(=|[[:space:]])[[:space:]]*["'"'"']?/dev/null(["'"'"'[:space:];&|)]|$)'
# sshpass embedded in another command's string (GIT_SSH_COMMAND='sshpass -p … ssh', rsync -e)
LINUX_SSHPASS_RE='(^|[^[:alnum:]_.-])sshpass[[:space:]]+-[pfedP]'
# device paths that are no target (reads, sinks, terminals)
LINUX_DEV_OK_RE='^/dev/(null|zero|full|random|urandom|stdin|stdout|stderr|tty[0-9]*|pts/[0-9]+|fd/[0-9]+)$'
# a redirection into /dev/<x> (echo … > /dev/sdb, cat x.iso >> /dev/sdb)
LINUX_REDIR_DEV_RE='>>?[|]?[[:space:]]*["'"'"']?/dev/[^[:space:]"'"'"';&|)<>]+'
# a private key under ~/.ssh (HOME_RE comes from core section 20)
LINUX_SSH_DIR_RE="^${HOME_RE}/\\.ssh(/|\$)"

LINUX_LEX='
function out(k, t) { gsub(/\n/, "\002", t); sub(/^[ \t\002]+/, "", t); sub(/[ \t\002]+$/, "", t); if (t != "") print k "\t" t }
function pclose(s, i, n,   depth, q, c) {
  depth = 1; q = ""
  while (i <= n) {
    c = substr(s, i, 1)
    if (q == sq) { if (c == sq) q = ""; i++; continue }
    if (c == "\\") { i += 2; continue }
    if (q == "\"") { if (c == "\"") q = ""; i++; continue }
    if (c == sq || c == "\"") { q = c; i++; continue }
    if (c == "(") depth++
    else if (c == ")") { depth--; if (!depth) return i }
    i++
  }
  return n + 1
}
function bclose(s, i, n,   c) { while (i <= n) { c = substr(s, i, 1); if (c == "\\") { i += 2; continue } if (c == "`") return i; i++ } return n + 1 }
function shellword(t) { return (t ~ /^[ \t]*((sudo|doas|env|command|exec|nohup|time|[A-Za-z_][A-Za-z0-9_]*=[^ \t]*)[ \t]+)*([^ \t]*\/)?(sh|bash|zsh|dash|ksh|ash|mksh)([ \t]|$)/) }
function lex(s, lvl,   n, i, c, d, p, q, cur, j, e, w, hs, hp, hw, hx, hk, hb, line, k) {
  if (lvl > 6) return
  n = length(s); cur = ""; q = ""; hp = 0; hb = ""; i = 1
  while (i <= n) {
    c = substr(s, i, 1); d = substr(s, i + 1, 1); p = (i > 1) ? substr(s, i - 1, 1) : ""
    if (q == sq) { cur = cur c; if (c == sq) q = ""; i++; continue }
    if (c == "\\") { if (d == "\n" && q == "") { cur = cur " "; i += 2; continue } cur = cur c d; i += 2; continue }
    if (c == "$" && d == "(") { j = pclose(s, i + 2, n); lex(substr(s, i + 2, j - i - 2), lvl + 1); cur = cur substr(s, i, j - i + 1); i = j + 1; continue }
    if (c == "`") { j = bclose(s, i + 1, n); lex(substr(s, i + 1, j - i - 1), lvl + 1); cur = cur substr(s, i, j - i + 1); i = j + 1; continue }
    if (q == "\"") { cur = cur c; if (c == "\"") q = ""; i++; continue }
    if (c == sq || c == "\"") { q = c; cur = cur c; i++; continue }
    if ((c == "<" || c == ">") && d == "(") { j = pclose(s, i + 2, n); lex(substr(s, i + 2, j - i - 2), lvl + 1); cur = cur substr(s, i, j - i + 1); i = j + 1; continue }
    if (c == "#" && (cur == "" || cur ~ /[ \t]$/)) { while (i <= n && substr(s, i, 1) != "\n") i++; continue }
    if (c == "<" && d == "<") {
      if (substr(s, i + 2, 1) == "<") { cur = cur "<<<"; i += 3; continue }
      j = i + 2; hs = 0
      if (substr(s, j, 1) == "-") { hs = 1; j++ }
      while (substr(s, j, 1) == " " || substr(s, j, 1) == "\t") j++
      w = ""
      while (j <= n) { e = substr(s, j, 1); if (e ~ /[ \t\n;&|<>()]/) break; if (e != "\"" && e != sq && e != "\\") w = w e; j++ }
      if (w != "") { hp = 1; hw = w; hx = shellword(cur); hk = (cur ~ />/ || cur ~ /(^|[ \t\/])tee([ \t]|$)/) ? "H" : "B" }
      cur = cur " <<" w; i = j; continue
    }
    if (c == "\n") {
      out("T", cur); cur = ""; i++
      if (hp) {
        hp = 0
        if (hx) hb = hw
        else {
          while (i <= n) {
            k = index(substr(s, i), "\n")
            if (k == 0) { line = substr(s, i); i = n + 1 } else { line = substr(s, i, k - 1); i += k }
            if (hs) sub(/^\t+/, "", line)
            if (line == hw) break
            out(hk, line)
          }
        }
      }
      if (hb != "") {
        k = index(substr(s, i), "\n"); line = (k == 0) ? substr(s, i) : substr(s, i, k - 1)
        sub(/^\t+/, "", line)
        if (line == hb) { hb = ""; i = (k == 0) ? n + 1 : i + k }
      }
      continue
    }
    if (c == ";") { out("T", cur); cur = ""; i++; continue }
    if (c == "|") {
      if (p == ">") { cur = cur c; i++; continue }
      if (d == "|") { out("T", cur); cur = ""; i += 2; continue }
      out("P", cur); cur = ""; i += (d == "&") ? 2 : 1; continue
    }
    if (c == "&") {
      if (p == ">" || p == "<" || d == ">") { cur = cur c; i++; continue }
      out("T", cur); cur = ""; i += (d == "&") ? 2 : 1; continue
    }
    if (c == "(" || c == ")") { out("T", cur); cur = ""; i++; continue }
    if ((c == "{" || c == "}") && (cur == "" || cur ~ /[ \t]$/) && (d == "" || d ~ /[ \t\n;]/)) { out("T", cur); cur = ""; i++; continue }
    if (c == "\t") c = " "
    cur = cur c; i++
  }
  out("T", cur)
}
BEGIN { RS = "\001" }
{ s = $0; gsub(/\002/, "\n", s); lex(s, 0) }
'
# Remote command splitter: one clause per line, or `!<tab>why` for a construct that is never
# read-only (command substitution, an expansion outside single quotes, a redirection other than
# 2>/dev/null or 2>&1, a heredoc, process substitution, a subshell, unbalanced quotes). Splits on
# ; & && || | |& newline (and \002) outside quotes.
LINUX_RSPLIT='
function emit() { sub(/^[ \t]+/, "", cur); sub(/[ \t]+$/, "", cur); if (cur != "") print cur; cur = "" }
function bad(w) { print "!\t" w; done = 1 }
function devnull(j) {   # j = first char after > or >>: rc 1 (and i past it) for [ ]/dev/null
  while (substr(s, j, 1) == " ") j++
  if (substr(s, j, 9) == "/dev/null" && (j + 9 > n || substr(s, j + 9, 1) ~ /[ \t;&|\n\002]/)) { i = j + 9; return 1 }
  return 0
}
BEGIN { RS = "\001" }
{
  s = $0; n = length(s); cur = ""; q = ""; i = 1; done = 0
  while (i <= n && !done) {
    c = substr(s, i, 1); d = substr(s, i + 1, 1)
    if (q == sq) { cur = cur c; if (c == sq) q = ""; i++; continue }
    if (c == "\\") { cur = cur c d; i += 2; continue }
    if (c == "`") { bad("command substitution"); break }
    if (c == "$") { bad("an expansion ($…) the remote shell evaluates"); break }
    if (q == "\"") { cur = cur c; if (c == "\"") q = ""; i++; continue }
    if (c == sq || c == "\"") { q = c; cur = cur c; i++; continue }
    if (c == "&" && d == ">") { j = i + 2; if (substr(s, j, 1) == ">") j++; if (devnull(j)) continue; bad("a redirection (>)"); break }
    if (c == ">") {
      if (d == "&" && substr(s, i + 2, 1) ~ /[0-9-]/) { if (cur ~ /(^|[ \t])[0-9]+$/) sub(/[0-9]+$/, "", cur); cur = cur " "; i += 3; continue }
      j = i + 1; if (d == ">") j++
      if (devnull(j)) { if (cur ~ /(^|[ \t])[0-9]+$/) sub(/[0-9]+$/, "", cur); cur = cur " "; continue }
      bad("a redirection (>)"); break
    }
    if (c == "<" && d == "<") { bad("a heredoc"); break }
    if (c == "<" && d == "(") { bad("process substitution"); break }
    if (c == "(" || c == ")") { bad("a subshell"); break }
    if (c == "\n" || c == "\002" || c == ";") { emit(); i++; continue }
    if (c == "|" || c == "&") { emit(); i += (d == "|" || d == "&") ? 2 : 1; continue }
    if (c == "\t") c = " "
    cur = cur c; i++
  }
  if (!done && q != "") bad("unbalanced quotes")
  if (!done) emit()
}
'

linux_lex_into() {  # TEXT -> append its lexed lines (K<tab>text) to LQ
  local _ll
  while IFS= read -r _ll; do [ -n "$_ll" ] && LQ+=("$_ll"); done <<EOF
$(printf '%s' "$1" | LC_ALL=C awk -v sq="'" "$LINUX_LEX")
EOF
  return 0
}
linux_words() {  # CLAUSE -> LW = its words (quotes removed); rc 1 on unbalanced quotes
  local _lw _w
  LW=()
  _lw=$(shell_words "$1") || return 1
  [ -z "$_lw" ] || while IFS= read -r _w; do LW+=("$_w"); done <<<"$_lw"
  return 0
}
linux_cmd0() {  # LW -> LI = index of the command word (past keywords, assignments, wrappers), LC = its basename ("" when none),
  # LXA = true when xargs appends arguments to it (no -I/-J), LXI = true when xargs replaces a placeholder
  local i=0 n=${#LW[@]} w b wrap="" skip=0 td=0 xi=false xa=false
  LI=$n; LC=""; LXA=false; LXI=false
  while [ "$i" -lt "$n" ]; do
    w=${LW[i]}; i=$((i+1))
    if [ "$skip" -gt 0 ]; then skip=$((skip-1)); continue; fi
    case "$w" in '!'|then|do|else|elif|if|while|until|time|'{'|'}') continue ;; esac
    if [ -n "$wrap" ]; then
      case "$w" in
        --) continue ;;
        -?*)
          case "$wrap:$w" in
            command:-v|command:-V) return 0 ;;
            sudo:-[ugCDprtUTh]|doas:-[uC]|env:-[uCS]|nice:-n|ionice:-[cnp]|timeout:-[sk]|exec:-a|chrt:-p|flock:-[wE]) skip=1 ;;
            xargs:-[nPLsdaEe]) skip=1 ;;
            xargs:-I|xargs:-J) skip=1; xi=true ;;
            xargs:-I*|xargs:-i*|xargs:--replace*|xargs:-J*) xi=true ;;
          esac
          continue ;;
      esac
    fi
    case "$w" in
      [A-Za-z_]*=*) b=${w%%=*}; case "$b" in *[!A-Za-z0-9_]*) ;; *) continue ;; esac ;;
    esac
    if [ "$td" = 1 ]; then td=0; continue; fi      # the duration of timeout, the priority of chrt, the lock file of flock
    b=${w##*/}
    case "$b" in
      sudo|doas|env|command|builtin|exec|nohup|nice|ionice|stdbuf|setsid|unbuffer|xargs|timeout|chrt|flock)
        wrap=$b
        case "$b" in xargs) xa=true ;; timeout|chrt|flock) td=1 ;; esac
        continue ;;
    esac
    LI=$((i-1)); LC=$b
    if $xa; then if $xi; then LXI=true; else LXA=true; fi; fi
    return 0
  done
  return 0
}
linux_scan() {  # -> LQ = the lexed clauses of $cmd, sh -c / su -c / eval strings appended; rc 1 when no linux word appears
  local n i=0 k t j w e=0
  LQ=()
  n=${cmd//\\/}; n=${n//\"/}; n=${n//\'/}
  printf '%s' "$n" | grep -qiE "$LINUX_PRE_RE" || return 1
  linux_lex_into "$cmd"
  while [ "$i" -lt "${#LQ[@]}" ]; do
    k=${LQ[i]%%"$LINUX_TABC"*}; t=${LQ[i]#*"$LINUX_TABC"}; i=$((i+1))
    case "$k" in T|P) ;; *) continue ;; esac
    [ "$e" -lt 8 ] || break
    linux_words "$t" || continue
    linux_cmd0
    case "$LC" in
      sh|bash|zsh|dash|ksh|ash|mksh|su)
        j=$((LI+1))
        while [ "$j" -lt "${#LW[@]}" ]; do
          w=${LW[j]}; j=$((j+1))
          case "$w" in
            --) break ;;
            -c|--command|--command=*|-[!-]*c*)
              case "$w" in --command=*) linux_lex_into "${w#--command=}"; e=$((e+1)); break ;; esac
              [ "$j" -lt "${#LW[@]}" ] && { linux_lex_into "${LW[j]}"; e=$((e+1)); }
              break ;;
          esac
        done ;;
      eval) [ $((LI+1)) -lt "${#LW[@]}" ] && { linux_lex_into "${LW[*]:$((LI+1))}"; e=$((e+1)); } ;;
    esac
  done
  return 0
}
linux_sflag() {  # LETTERS WORD -> rc 0 when WORD is a short-option cluster (-abc, not --x) holding one of LETTERS
  case "$2" in --*|-) return 1 ;; -*) case "${2#-}" in *["$1"]*) return 0 ;; esac ;; esac
  return 1
}
linux_pos() {  # VALUE_FLAGS_ERE WORD... -> LP = the positional words (flags, and the next word of a VALUE_FLAGS flag, skipped)
  local vre="^($1)\$" w skip=false dd=false
  shift; LP=()
  for w in "$@"; do
    if $skip; then skip=false; continue; fi
    if $dd; then LP+=("$w"); continue; fi
    case "$w" in
      --) dd=true ;;
      --*=*) ;;
      -?*) [[ $w =~ $vre ]] && skip=true ;;
      *) LP+=("$w") ;;
    esac
  done
  return 0
}
linux_target() {  # HOST -> LINUX_TGT = "host=<alias>[ [PROD]]" (user@, scheme, :port and :path dropped)
  local h=$1
  h=${h#*://}; h=${h#*@}; h=${h%%/*}
  case "$h" in \[*\]*) h=${h#\[}; h=${h%%\]*} ;; *) h=${h%%:*} ;; esac
  LINUX_TGT="host=${h:-unknown}"
  printf '%s' "$h" | grep -qiE -- "$LINUX_PROD" 2>/dev/null && LINUX_TGT="$LINUX_TGT [PROD]"
  return 0
}
linux_remote_spec() {  # WORD -> rc 0 when it names a remote path (host:path, user@host:path, scp|rsync|sftp://); LT_HOST = the host part
  local w=$1 h
  case "$w" in
    scp://*|sftp://*|rsync://*) h=${w#*://} ;;
    /*|./*|../*|'~'*|-*|'') return 1 ;;
    *:*) h=${w%%:*}; case "$h" in */*|'') return 1 ;; esac ;;
    *) return 1 ;;
  esac
  LT_HOST=$h
  return 0
}
linux_is_dev() {  # WORD -> rc 0 when it names a device under /dev other than null, zero, tty… (or cannot be known: $VAR, `…`,
  # or a relative path while the command cds into /dev); LD_WHAT = the word
  local v=$1
  case "$v" in *'$'*|*'`'*) LD_WHAT=$v; return 0 ;; esac
  case "$v" in
    /dev/*) [[ $v =~ $LINUX_DEV_OK_RE ]] && return 1; LD_WHAT=$v; return 0 ;;
    /*|'') return 1 ;;
  esac
  if [ "${LINUX_IN_DEV:-false}" = true ]; then LD_WHAT=$v; return 0; fi
  return 1
}
linux_dev_operands() {  # FROM -> rc 0 when a non-flag word of LW from index FROM (or the value of --x=) is a device; LD_WHAT
  local j=$1 w
  if $LXA; then LD_WHAT="arguments xargs appends"; return 0; fi
  while [ "$j" -lt "${#LW[@]}" ]; do
    w=${LW[j]}; j=$((j+1))
    case "$w" in -*=*) w=${w#*=} ;; -*) continue ;; esac
    linux_is_dev "$w" && return 0
  done
  return 1
}
linux_ssh_key() {  # WORD -> rc 0 when it names a file or directory under ~/.ssh other than *.pub
  local w=$1
  [[ $w =~ $LINUX_SSH_DIR_RE ]] || return 1
  case "$w" in *.pub) return 1 ;; esac
  return 0
}
linux_ssh_opt() {  # OPTION (the value of -o) -> LS_ASK gains it when it forwards, tunnels, runs a local command or asks for a tty
  local o=$1 k v
  k=${o%%[= 	]*}; v=${o#"$k"}; v=${v#[= 	]}
  k=$(printf '%s' "$k" | tr 'A-Z' 'a-z'); v=$(printf '%s' "$v" | tr 'A-Z' 'a-z')
  case "$k" in
    proxycommand|localcommand|localforward|remoteforward|dynamicforward|remotecommand|tunnel) LS_ASK="${LS_ASK:+$LS_ASK, }-o $k" ;;
    permitlocalcommand|forwardagent|forwardx11|forwardx11trusted|requesttty|controlmaster)
      case "$v" in no|false|'') ;; *) LS_ASK="${LS_ASK:+$LS_ASK, }-o $k=$v" ;; esac ;;
  esac
  return 0
}
linux_ssh_parse() {  # FROM -> parse `ssh [opts] host [opts] [command…]` in LW from FROM: LS_HOST, LS_CMD (the remote command
  # joined as ssh sends it), LS_HASCMD, LS_NOCONN (-G/-V/-Q: prints and exits), LS_ASK (forwarding, tunnel, tty, background …)
  local i=$1 n=${#LW[@]} w s ch v ends=false
  LS_HOST=""; LS_CMD=""; LS_HASCMD=false; LS_NOCONN=false; LS_ASK=""
  while [ "$i" -lt "$n" ]; do
    w=${LW[i]}; i=$((i+1))
    if ! $ends; then
      case "$w" in
        --) ends=true; continue ;;
        -?*)
          s=${w#-}
          while [ -n "$s" ]; do
            ch=${s:0:1}; s=${s:1}
            case "$ch" in
              [BbcDEeFIiJLlmOoPpQRSWw])
                if [ -n "$s" ]; then v=$s; s=""; else v=${LW[i]:-}; i=$((i+1)); fi
                case "$ch" in
                  L) LS_ASK="${LS_ASK:+$LS_ASK, }-L (local port forwarding)" ;;
                  R) LS_ASK="${LS_ASK:+$LS_ASK, }-R (remote port forwarding)" ;;
                  D) LS_ASK="${LS_ASK:+$LS_ASK, }-D (SOCKS proxy)" ;;
                  W) LS_ASK="${LS_ASK:+$LS_ASK, }-W (stdio forwarding)" ;;
                  w) LS_ASK="${LS_ASK:+$LS_ASK, }-w (tunnel device)" ;;
                  O) LS_ASK="${LS_ASK:+$LS_ASK, }-O (control command)" ;;
                  o) linux_ssh_opt "$v" ;;
                  Q) LS_NOCONN=true ;;
                esac ;;
              t) LS_ASK="${LS_ASK:+$LS_ASK, }-t (interactive tty)" ;;
              N) LS_ASK="${LS_ASK:+$LS_ASK, }-N (no remote command: forwarding only)" ;;
              f) LS_ASK="${LS_ASK:+$LS_ASK, }-f (backgrounds itself)" ;;
              A) LS_ASK="${LS_ASK:+$LS_ASK, }-A (agent forwarding)" ;;
              [XY]) LS_ASK="${LS_ASK:+$LS_ASK, }-$ch (X11 forwarding)" ;;
              M) LS_ASK="${LS_ASK:+$LS_ASK, }-M (control master)" ;;
              [GV]) LS_NOCONN=true ;;
            esac
          done
          continue ;;
      esac
    fi
    if [ -z "$LS_HOST" ]; then LS_HOST=$w; ends=false; continue; fi
    # ssh parses options after the host too, up to the first word of the command
    LS_HASCMD=true
    LS_CMD="${LW[*]:$((i-1))}"
    break
  done
  return 0
}
linux_scp_parse() {  # FROM -> LP = the scp operands of LW from FROM; LS_ASK from -o
  local i=$1 n=${#LW[@]} w s ch v
  LP=(); LS_ASK=""
  while [ "$i" -lt "$n" ]; do
    w=${LW[i]}; i=$((i+1))
    case "$w" in
      --) while [ "$i" -lt "$n" ]; do LP+=("${LW[i]}"); i=$((i+1)); done ;;
      -?*)
        s=${w#-}
        while [ -n "$s" ]; do
          ch=${s:0:1}; s=${s:1}
          case "$ch" in
            [cFiJloPSDX])
              if [ -n "$s" ]; then v=$s; s=""; else v=${LW[i]:-}; i=$((i+1)); fi
              [ "$ch" = o ] && linux_ssh_opt "$v" ;;
          esac
        done ;;
      *) LP+=("$w") ;;
    esac
  done
  return 0
}
linux_rsync_parse() {  # FROM -> LP = the rsync operands of LW from FROM; LS_ASK for --rsync-path / --remove-source-files
  local i=$1 n=${#LW[@]} w
  LP=(); LS_ASK=""
  while [ "$i" -lt "$n" ]; do
    w=${LW[i]}; i=$((i+1))
    case "$w" in
      --) while [ "$i" -lt "$n" ]; do LP+=("${LW[i]}"); i=$((i+1)); done ;;
      --rsync-path|--rsync-path=*) LS_ASK="${LS_ASK:+$LS_ASK, }--rsync-path (runs a remote command)"; [ "$w" = --rsync-path ] && i=$((i+1)) ;;
      --remove-source-files) LS_ASK="${LS_ASK:+$LS_ASK, }--remove-source-files (deletes the source)" ;;
      --*=*) ;;
      --rsh|--filter|--exclude|--include|--exclude-from|--include-from|--files-from|--temp-dir|--partial-dir|--compare-dest|--copy-dest|--link-dest|--backup-dir|--suffix|--chmod|--chown|--log-file|--password-file|--port|--bwlimit|--timeout|--out-format|--info|--debug|--max-size|--min-size|--block-size|--modify-window|--usermap|--groupmap|--sockopts|--contimeout|--remote-option|--skip-compress|--iconv) i=$((i+1)) ;;
      --*) ;;
      -?*) case "$w" in -*[efBTM@]) i=$((i+1)) ;; esac ;;
      *) LP+=("$w") ;;
    esac
  done
  return 0
}

# ---- the read-only allow-list for a remote command (ssh HOST <command>) -------------------------
linux_ip_ro() {  # ip WORDS… -> rc 0 for an object with no verb or a show/list/get verb; LR_WHY otherwise
  local w obj="" verb="" skip=false
  for w in "$@"; do
    if $skip; then skip=false; continue; fi
    if [ -z "$obj" ]; then
      case "$w" in
        -b|-batch|-force) LR_WHY="'ip $w' runs commands from a file"; return 1 ;;
        -n|-netns|-f|-family|-l|-loops|-rc|-rcvbuf) skip=true; continue ;;
        -*) continue ;;
      esac
      obj=$w; continue
    fi
    verb=$w; break
  done
  case "$verb" in ''|show|list|lst|ls|sh|get|help) return 0 ;; esac
  LR_WHY="'ip $obj $verb' changes the network configuration"
  return 1
}
linux_ipt_action() {  # iptables WORDS… -> rc 0 when a rule- or chain-changing action is present
  local w
  for w in "$@"; do
    case "$w" in
      --append|--insert|--delete|--flush|--policy|--delete-chain|--new-chain|--replace|--zero|--rename-chain) return 0 ;;
      --append=*|--insert=*|--delete=*|--flush=*|--policy=*|--delete-chain=*|--new-chain=*|--replace=*|--zero=*|--rename-chain=*) return 0 ;;
      --*) ;;
      -*) linux_sflag AIDFPXNRZE "$w" && return 0 ;;
    esac
  done
  return 1
}
linux_ipt_list() {  # iptables WORDS… -> rc 0 when a listing (-L, -S, --list, --list-rules) is asked for
  local w
  for w in "$@"; do
    case "$w" in --list|--list=*|--list-rules|--list-rules=*) return 0 ;; --*) ;; -*) linux_sflag LS "$w" && return 0 ;; esac
  done
  return 1
}
linux_nmcli_ro() {  # nmcli WORDS… -> rc 0 for the show forms (general|device|connection [show|status], radio, monitor)
  local o v
  linux_pos '-f|--fields|-g|--get-values|-m|--mode|-e|--escape|-c|--colors|-w|--wait' "$@"
  o=${LP[0]:-}; v=${LP[1]:-}
  case "$o" in
    '') return 0 ;;
    g|ge|gen|gene|gener|genera|general)
      case "$v" in ''|status|permissions) return 0 ;; hostname|logging) [ "${#LP[@]}" -le 2 ] && return 0 ;; esac ;;
    d|de|dev|devi|devic|device)
      case "$v" in ''|status|show|lldp) return 0 ;; wifi) case "${LP[2]:-}" in ''|list) return 0 ;; esac ;; esac ;;
    c|co|con|conn|conne|connec|connect|connecti|connectio|connection)
      case "$v" in ''|show) return 0 ;; esac ;;
    r|ra|rad|radi|radio) [ "${#LP[@]}" -le 2 ] && return 0 ;;
    n|ne|net|netw|netwo|networ|network|networki|networkin|networking)
      case "$v" in '') return 0 ;; connectivity) [ "${#LP[@]}" -le 3 ] && return 0 ;; esac ;;
    m|mo|mon|moni|monit|monito|monitor) return 0 ;;
  esac
  LR_WHY="'nmcli ${LP[*]}' changes the network configuration"
  return 1
}
linux_ro_cmd() {  # WORD… (the first is the command) -> rc 0 when it is on the read-only allow-list; LR_WHY otherwise
  local c=${1##*/} w has=false skip=false re
  shift
  LR_WHY="'$c' is not on the read-only allow-list"
  case "$c" in
    cat|head|ls|stat|uname|uptime|id|whoami|df|du|free|lsblk|blkid|findmnt|lscpu|lspci|lsusb|lsmod|ps|w|last|lastlog|grep|egrep|fgrep|wc|cut|nproc|netstat|lvs|vgs|pvs|dpkg-query|iptables-save|ip6tables-save)
      return 0 ;;
    tail)
      for w in "$@"; do
        if linux_sflag fF "$w"; then LR_WHY="'tail -f' never returns; pass -n N instead"; return 1; fi
        case "$w" in --follow*|--retry) LR_WHY="'tail $w' never returns; pass -n N instead"; return 1 ;; esac
      done
      return 0 ;;
    journalctl)
      for w in "$@"; do
        if linux_sflag f "$w"; then LR_WHY="'journalctl -f' never returns; pass --since or -n instead"; return 1; fi
        case "$w" in
          --follow*) LR_WHY="'journalctl --follow' never returns; pass --since or -n instead"; return 1 ;;
          --vacuum*|--rotate|--flush|--sync|--relinquish-var|--smart-relinquish-var|--setup-keys|--update-catalog)
            LR_WHY="'journalctl $w' changes the journal"; return 1 ;;
        esac
      done
      return 0 ;;
    systemctl)
      linux_pos '-t|--type|-p|--property|-H|--host|-M|--machine|-n|--lines|-o|--output|--state|--root' "$@"
      case "${LP[0]:-}" in
        ''|status|is-active|is-enabled|is-failed|is-system-running|list-units|list-unit-files|list-timers|list-sockets|list-dependencies|list-jobs|show|cat|get-default) return 0 ;;
      esac
      LR_WHY="'systemctl ${LP[0]}' changes the host"; return 1 ;;
    dmesg)
      for w in "$@"; do
        if linux_sflag cCDEnwW "$w"; then LR_WHY="'dmesg $w' clears, follows or changes the kernel log"; return 1; fi
        case "$w" in --clear|--read-clear|--console-*|--follow*) LR_WHY="'dmesg $w' clears, follows or changes the kernel log"; return 1 ;; esac
      done
      return 0 ;;
    ip) linux_ip_ro "$@"; return ;;
    ss)
      for w in "$@"; do
        if linux_sflag K "$w" || [ "$w" = --kill ]; then LR_WHY="'ss -K' kills sockets"; return 1; fi
      done
      return 0 ;;
    hostname)
      for w in "$@"; do
        case "$w" in
          -f|-s|-d|-i|-I|-A|-a|-y|--fqdn|--long|--short|--domain|--ip-address|--ip-addresses|--all-ip-addresses|--all-fqdns|--alias|--nis|--yp) ;;
          *) LR_WHY="'hostname $w' may set the host name"; return 1 ;;
        esac
      done
      return 0 ;;
    date)
      for w in "$@"; do
        case "$w" in +*|-u|-R|--utc|--universal|--rfc-email|--rfc-3339=*|-I|-I[a-z]*|--iso-8601|--iso-8601=*|--debug) ;; *) LR_WHY="'date $w' may set the clock"; return 1 ;; esac
      done
      return 0 ;;
    mount)
      for w in "$@"; do [ "$w" = -l ] || { LR_WHY="'mount' with arguments mounts a file system"; return 1; }; done
      return 0 ;;
    sensors)
      for w in "$@"; do if linux_sflag s "$w" || [ "$w" = --set ]; then LR_WHY="'sensors -s' writes chip settings"; return 1; fi; done
      return 0 ;;
    sort)
      for w in "$@"; do if linux_sflag o "$w"; then LR_WHY="'sort -o' writes a file"; return 1; fi; case "$w" in --output*) LR_WHY="'sort --output' writes a file"; return 1 ;; esac; done
      return 0 ;;
    uniq)
      linux_pos '-f|--skip-fields|-s|--skip-chars|-w|--check-chars' "$@"
      [ "${#LP[@]}" -le 1 ] && return 0
      LR_WHY="'uniq IN OUT' writes a file"; return 1 ;;
    top)
      w=" $* "; re='[[:space:]]-[A-Za-z]*b'
      if [[ $w =~ $re ]]; then re='[[:space:]]-[A-Za-z]*n[[:space:]]*[0-9]+'; [[ $w =~ $re ]] && return 0; fi
      LR_WHY="'top' without -b -n1 is interactive"; return 1 ;;
    mdadm)
      for w in "$@"; do
        case "$w" in
          --detail|-D|--examine|-E|--query|-Q) has=true ;;
          --scan|-s|--brief|-b|--verbose|-v|--export|-Y|--test|-t|--misc) ;;
          -*) LR_WHY="'mdadm $w' changes an array"; return 1 ;;
        esac
      done
      $has && return 0
      LR_WHY="'mdadm' without --detail|--examine|--query changes an array"; return 1 ;;
    nft)
      for w in "$@"; do
        if linux_sflag fi "$w"; then LR_WHY="'nft $w' loads or edits rules"; return 1; fi
        case "$w" in --file|--file=*|--interactive) LR_WHY="'nft $w' loads or edits rules"; return 1 ;; esac
      done
      linux_pos '-I|--includepath|-D|--define|-T' "$@"
      [ "${LP[0]:-}" = list ] && return 0
      LR_WHY="'nft ${LP[0]:-}' changes the firewall"; return 1 ;;
    ufw)
      linux_pos '' "$@"
      case "${LP[0]:-}" in status|show) return 0 ;; esac
      LR_WHY="'ufw ${LP[0]:-}' changes the firewall"; return 1 ;;
    iptables|ip6tables|iptables-legacy|iptables-nft|ip6tables-legacy|ip6tables-nft)
      if linux_ipt_action "$@"; then LR_WHY="'$c' with -A/-I/-D/-F/-P/-X/-N/-R/-Z/-E changes the firewall"; return 1; fi
      linux_ipt_list "$@" && return 0
      LR_WHY="'$c' without -L/-S is not a listing"; return 1 ;;
    resolvectl)
      linux_pos '-i|--interface|-p|--protocol|-t|--type|-c|--class' "$@"
      case "${LP[0]:-}" in status|query|statistics) return 0 ;; dns|domain) [ "${#LP[@]}" -le 2 ] && return 0 ;; esac
      LR_WHY="'resolvectl ${LP[*]}' changes the resolver"; return 1 ;;
    networkctl)
      linux_pos '' "$@"
      case "${LP[0]:-}" in ''|status|list|lldp) return 0 ;; esac
      LR_WHY="'networkctl ${LP[0]}' changes the network"; return 1 ;;
    netplan)
      linux_pos '--root-dir' "$@"
      case "${LP[0]:-}" in get|status|info) return 0 ;; esac
      LR_WHY="'netplan ${LP[0]:-}' changes the network"; return 1 ;;
    nmcli) linux_nmcli_ro "$@"; return ;;
    sshd)
      for w in "$@"; do
        if $skip; then skip=false; continue; fi
        case "$w" in -T|-t|-G) has=true ;; -f|-C) skip=true ;; -f?*|-C?*) ;; *) LR_WHY="'sshd $w' runs the daemon"; return 1 ;; esac
      done
      $has && return 0
      LR_WHY="'sshd' without -T/-t/-G runs the daemon"; return 1 ;;
    smartctl)
      for w in "$@"; do
        if $skip; then skip=false; continue; fi
        case "$w" in
          -a|-H|-i|-x|-A|-c|-j|--all|--health|--info|--xall|--attributes|--capabilities|--scan|--scan-open|--json|--json=*|-d?*|--device=*) ;;
          -d) skip=true ;;
          -*) LR_WHY="'smartctl $w' changes the drive or starts a test"; return 1 ;;
        esac
      done
      return 0 ;;
    apt)
      linux_pos '-o|--option|-c|--config-file|-t|--target-release' "$@"
      case "${LP[0]:-}" in list|show|policy|search) return 0 ;; esac
      LR_WHY="'apt ${LP[0]:-}' changes packages"; return 1 ;;
    apt-cache)
      linux_pos '-o|--option|-c|--config-file' "$@"
      case "${LP[0]:-}" in policy|show|search|depends|rdepends|madison|showpkg|stats|pkgnames) return 0 ;; esac
      LR_WHY="'apt-cache ${LP[0]:-}' is not a read"; return 1 ;;
    dpkg)
      for w in "$@"; do
        case "$w" in
          -l|-L|-s|-S|-p|-W|--list|--listfiles|--status|--search|--print-avail|--get-selections|--print-architecture|--print-foreign-architectures|--show) has=true ;;
          -*) LR_WHY="'dpkg $w' changes packages"; return 1 ;;
        esac
      done
      $has && return 0
      LR_WHY="'dpkg' without a query flag changes packages"; return 1 ;;
    rpm)
      for w in "$@"; do
        case "$w" in
          -q*|--query|--query=*) has=true ;;
          --all|--info|--list|--file|--whatprovides|--whatrequires|--requires|--provides|--changelog|--queryformat=*|--qf=*) ;;
          -*) LR_WHY="'rpm $w' changes packages"; return 1 ;;
        esac
      done
      $has && return 0
      LR_WHY="'rpm' without -q changes packages"; return 1 ;;
    zpool)
      linux_pos '-o|-T' "$@"
      case "${LP[0]:-}" in status|list|get|iostat) return 0 ;; esac
      LR_WHY="'zpool ${LP[0]:-}' changes a pool"; return 1 ;;
    zfs)
      linux_pos '-o|-s|-S|-t|-d' "$@"
      case "${LP[0]:-}" in list|get) return 0 ;; esac
      LR_WHY="'zfs ${LP[0]:-}' changes a dataset"; return 1 ;;
    sudo|doas|su|pkexec) LR_WHY="remote $c (privilege escalation)"; return 1 ;;
    sh|bash|zsh|dash|ksh|ash|mksh|fish|python*|perl|ruby|node|eval|exec|source|.|env|xargs|nohup|timeout|watch)
      LR_WHY="remote '$c' runs other commands"; return 1 ;;
  esac
  return 1
}
linux_remote_ro() {  # REMOTE_COMMAND -> rc 0 when every clause is on the read-only allow-list; LR_WHY names the first that is not
  local out line first=true
  local -a rw
  out=$(printf '%s' "$1" | LC_ALL=C awk -v sq="'" "$LINUX_RSPLIT")
  while IFS= read -r line; do
    case "$line" in "!$LINUX_TABC"*) LR_WHY="remote ${line#*"$LINUX_TABC"}"; return 1 ;; esac
    [ -n "$line" ] || continue
    linux_words "$line" || { LR_WHY="remote unbalanced quotes"; return 1; }
    [ "${#LW[@]}" -gt 0 ] || continue
    case "${LW[0]}" in [A-Za-z_]*=*) LR_WHY="remote environment assignment (${LW[0]%%=*}=)"; return 1 ;; esac
    rw=("${LW[@]}")
    linux_ro_cmd "${rw[@]}" || return 1
    first=false
  done <<EOF
$out
EOF
  $first && { LR_WHY="no remote command"; return 1; }
  return 0
}
