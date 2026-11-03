# shellcheck shell=bash

# Section 35 (bundle core): shell hygiene. Pipe-to-shell only for now; sudo/doas, recursive
# removal outside the checkout and chmod -R 777 are planned (docs/roadmap.md).
# rule: curl|wget|fetch|http|xh … | [wrapper] sh|bash|zsh|ksh|dash|ash|mksh|fish|python[3]|perl|node|ruby reading its program from stdin (no -c/-e/-m/-n, script operand or stdin redirect; sh -s, bash -, python3 -, /dev/stdin count; sudo -s|-i, su, source|. /dev/stdin too; through { } ( ) if/for/while bodies, a continued line and tee >(sh)) | sh|bash|source|. <(curl …) | sh|bash -c "$(curl …)" | python|perl|ruby|node -c|-e "$(curl …)" | eval "$(curl …)" | an interpreter's <<< or heredoc expanding $(curl …) -> ask : runs downloaded code unreviewed; download to a file, check its sha256, read it, then run it instead
#
# How a command is read: the raw command ($cmd, newlines kept) is walked once by awk, a small
# quote-aware matcher (not a shell parser). Stages are split on | (pipe) and on ; & && || newline
# (list); a line ending in | continues the pipeline. Frames of their own: `$( )`, `<( )`, `>( )`,
# backticks, `( )` and `{ }` groups, if/while/until/for/select/case bodies, and the string of
# `sh|bash -c` / `eval` (so `sh -c 'curl … | sh'` is read as code). A group inherits the stdin
# of the stage it stands in (`curl … | { sh; }`), `>( )` the output of its stage. Any other
# quoted text is data, `$'…'` included: its separators and spaces are masked, so
# `echo "curl … | sh"` and `grep 'curl.*| sh' f` stay one harmless command, while a quoted
# command word (`"curl"`) still counts. Heredoc bodies are data unless an interpreter reads them;
# comments are dropped. A frame that ran a downloader passes that to the stage holding it, so
# `(curl …) | sh` and `sh -c "$(curl …)"` are seen. The command word skips assignments,
# `!`/`if`/`then`/`do`/`time` and the wrappers sudo, doas, env, command, builtin, exec, nohup,
# nice, stdbuf, setsid, ionice, unbuffer, timeout, busybox and xargs (xargs passes arguments,
# not stdin), and is compared by basename (/usr/bin/curl). It runs in the C locale (byte
# semantics, linear-time substitutions) and in any POSIX awk (gawk, mawk, BSD awk, busybox).
SHELL_HYG_FETCH_RE='^(curl|wget|fetch|http|https|xh|xhs)$'                                   # downloaders, by basename
SHELL_HYG_INTERP_RE='^(sh|bash|zsh|ksh|dash|ash|mksh|fish|python[0-9.]*|perl|ruby|node|nodejs)$'   # interpreters, by basename
repo_owns core/guard.d/35-shell-hygiene base && return 0   # principle 8: the repository's .harness.toml owns this section or domain base
# ---- Pipe-to-shell: ask (deferred, so a later deny still wins) -------------------------------
local LC_ALL=C hyg_n hyg_lex
case "$cmd" in                                                     # builtins only: most commands stop here
  *curl*|*wget*|*fetch*|*http*|*xh*) ;;
  *[\\\'\"]*) hyg_n=${cmd//\\/}; hyg_n=${hyg_n//\"/}; hyg_n=${hyg_n//\'/}   # c\url, "cu"rl
    case "$hyg_n" in *curl*|*wget*|*fetch*|*http*|*xh*) ;; *) return 0 ;; esac ;;
  *) return 0 ;;
esac
hyg_lex='
function base(w) { sub(/.*\//, "", w); return w }
function tail(t) { return (length(t) > 200) ? substr(t, length(t) - 199) : t }
# cmdword(T) -> basename of the command word of stage text T; A[1..NA] = its words, CI = the
# index, XW = 1 when xargs runs it (its stdin is not the pipe)
function cmdword(t,   k, w, b, wrap, skip, td, ss) {
  NA = split(t, A, /[ \t]+/); wrap = ""; skip = 0; td = 0; ss = 0; XW = 0
  for (k = 1; k <= NA; k++) {
    w = A[k]
    if (w == "") continue
    if (skip) { skip = 0; continue }
    if (w ~ /^(!|then|do|else|elif|if|while|until|time)$/) continue
    if (td && w !~ /^-/) { td = 0; continue }                          # the duration of timeout
    b = base(w)
    if (b ~ /^(sudo|doas|env|command|builtin|exec|nohup|nice|stdbuf|setsid|ionice|unbuffer|timeout|busybox|xargs)$/) {
      wrap = b; if (b == "xargs") XW = 1; if (b == "timeout") td = 1; continue
    }
    if (w ~ /^[A-Za-z_][A-Za-z0-9_]*=/) continue
    if (wrap != "" && w ~ /^-/) {
      if (wrap ~ /^(sudo|doas)$/ && w ~ /^-[A-Za-z]*[is][A-Za-z]*$/) ss = 1        # sudo -s|-i: a shell
      if ((wrap ~ /^(sudo|doas)$/ && w ~ /^-[ugCDprtUTh]$/) || (wrap == "env" && w ~ /^-[uCS]$/) \
          || (wrap ~ /^(nice|ionice)$/ && w ~ /^-[ncp]$/) || (wrap == "xargs" && w ~ /^-[InPLsdaE]$/) \
          || (wrap == "timeout" && w ~ /^-[sk]$/) || (wrap == "exec" && w == "-a")) skip = 1
      if (wrap == "command" && w ~ /^-[vV]$/) { CI = NA + 1; return "" }
      continue
    }
    CI = k; return (w ~ /^[$][{]?SHELL[}]?$/) ? "sh" : b
  }
  CI = NA + 1; return ss ? "sh" : ""
}
# cw(T): the command word only, from the first 400 bytes (callers that run per quote stay linear)
function cw(t) { return cmdword(length(t) > 400 ? substr(t, 1, 400) : t) }
function isstdin(w) { return (w ~ /^\/(dev\/stdin|dev\/fd\/0|proc\/self\/fd\/0)$/) }
# stdin_prog(T) -> 1 when stage T is an interpreter that reads its program from stdin
function stdin_prog(t,   c, kind, k, w, skip, s, last) {
  c = cmdword(t)
  for (k = CI + 1; k <= NA; k++) if (A[k] ~ /^0?</) return 0             # stdin redirected: < f, <<EOF, <<<
  if (c == "source" || c == ".") return (!XW && isstdin(A[CI + 1]))
  if (c == "su") {                                                       # su [-] [user]: a login shell
    for (k = CI + 1; k <= NA; k++) if (A[k] ~ /^-[A-Za-z]*c$/ || A[k] ~ /^--(session-)?command/) return 0
    return !XW
  }
  if (c !~ ire) return 0
  kind = (c ~ /^(sh|bash|zsh|ksh|dash|ash|mksh|fish)$/) ? "sh" : (c ~ /^python/) ? "py" : (c ~ /^node/) ? "js" : "pl"
  last = NA; while (last > CI && A[last] == "") last--
  skip = 0; s = 0
  for (k = CI + 1; k <= NA; k++) {
    w = A[k]
    if (w == "") continue
    if (skip) { skip = 0; continue }
    if (w ~ /^[0-9]*(>|&>)/) { if (w ~ /^[0-9]*(>>?|&>>?|>&)$/) skip = 1; continue }   # redirections
    if (w == "-") return !XW
    if (w == "--") { k++; while (k <= NA && A[k] == "") k++; return (!XW && (s || k > NA || A[k] == "-")) }
    if (w ~ /^\+/ && kind == "sh") { if (w ~ /^\+[A-Za-z]*[oO]$/) skip = 1; continue }
    if (w ~ /^--/) {
      if (kind == "js" && w ~ /^--(eval|print|check)(=|$)/) return 0
      if (kind == "js" && w ~ /^--(require|import)$/) skip = 1
      if (kind == "sh" && w ~ /^--(rcfile|init-file)$/) skip = 1
      if (w ~ /^--(help|version)$/) return 0
      continue
    }
    if (w ~ /^-/) {                      # -c/-e: the program is the next word (xargs: its arguments)
      if (kind == "sh") { if (w ~ /c/) return (XW && k == last); if (w ~ /n/) return 0; if (w ~ /s/) s = 1; if (w ~ /^-[A-Za-z]*[oO]$/) skip = 1; continue }
      if (kind == "py") { if (w ~ /^-[^WX]*[cm]/) return (XW && k == last); if (w ~ /^-[WXQ]$/) skip = 1; continue }
      if (kind == "js") { if (w ~ /^-[^-]*[epc]/) return (XW && k == last); if (w ~ /^-r$/) skip = 1; continue }
      if (w ~ /^-[MmIr]/) { if (w ~ /^-[MmIr]$/) skip = 1; continue }  # perl, ruby: -Mmod -I dir -rlib
      if (w ~ /^-[^-]*[eE]/) return (XW && k == last)
      continue
    }
    if (isstdin(w)) return !XW                                           # the pipe, by name
    return (kind == "sh" && s && !XW)                                    # an operand: a script file
  }
  return !XW
}
# shellctx(T): T ends in `sh|bash … -c ` or `eval ` (the next word is shell code); progctx(T):
# `python -c ` / `perl|ruby|node -e ` (a substitution there is the program). Tail-only regexes.
function shellctx(t,   l, c) {
  l = tail(t)
  if (l ~ /(^| )eval +$/) return (cw(t) == "eval")
  if (l !~ /(^|[ \/])(sh|bash|zsh|dash|ksh|ash|mksh|fish)( +(-[A-Za-z]+|[-+]o +[A-Za-z]+))* +-[A-Za-z]*c( +--)? +$/) return 0
  c = cw(t); return (c ~ /^(sh|bash|zsh|dash|ksh|ash|mksh|fish)$/)
}
function progctx(t,   l, c) {
  l = tail(t)
  if (l !~ /(^|[ \/])(python[0-9.]*|perl|ruby|nodejs|node)( +-[A-Za-z0-9]+)* +-[A-Za-z]*[ceE]( +--)? +$/) return 0
  c = cw(t); return (c ~ /^(python[0-9.]*|perl|ruby|nodejs|node)$/)
}
function herestr(t,   c) {
  if (tail(t) !~ /<<< *$/) return 0
  c = cmdword(substr(t, 1, 400))
  return (c ~ ire || ((c == "source" || c == ".") && isstdin(A[CI + 1])))
}
function isprog(t,   c) { c = cw(t); return (c ~ ire || c == "source" || c == ".") }
# cmdpos(T): the next word of stage T is a command word (reserved words may open or close frames)
function cmdpos(t) { return (t !~ /[^ ]/ || (length(t) < 64 && t ~ /^( *(then|do|else|elif|!|time))+ +$/)) }
function mask(c) { return (c ~ /[ \t\n;&|()<>`$\\{}"]/ || c == sq) ? "_" : c }
function emit(pipe,   t, c) {
  t = CUR[d]
  if (t ~ /[^ ]/ || SD[d]) {
    c = cmdword(t)
    if (PP[d] && DL[d] && stdin_prog(t)) hit = 1
    if (c ~ fre || SD[d]) { DL[d] = 1; ANY[d] = 1 }
  }
  CUR[d] = ""; SD[d] = 0
  if (pipe) PP[d] = 1; else { PP[d] = FP[d]; DL[d] = FD[d] }
}
# push(END, KIND, CODE, STR, IN): a new frame ending at END. KIND: sub ( ), grp { }, kw (if/for/…
# body, END = fi|done|esac), cs ($( ), backtick, <( ), >( )), str (sh -c / eval string). CODE = 1
# when its output runs as a program; STR = 1 for the string of sh -c / eval (a substitution as its
# first word is that program); IN = 1 when its stdin is a download (each stage starts piped)
function push(e, kind, code, str, inp) {
  d++; FE[d] = e; FK[d] = kind; FC[d] = code; FSTR[d] = str; QD[d] = ""; CUR[d] = ""
  FP[d] = inp; FD[d] = inp; PP[d] = inp; DL[d] = inp; SD[d] = 0; ANY[d] = 0
}
function pop(   k) {
  emit(0); if (ANY[d] && FC[d]) hit = 1; k = FK[d]; d--
  if (ANY[d + 1]) SD[d] = 1
  if (k == "sub" || k == "grp" || k == "kw") CUR[d] = CUR[d] " _ "
}
# popto(K): close every frame down to and including frame K
function popto(k) { while (d >= k) pop() }
# opener(E, KINDS): the nearest frame ending at E with only frames of KINDS above it, or 0
function opener(e, kinds,   k) {
  for (k = d; k > 0; k--) { if (FE[k] == e) return k; if (index(kinds, FK[k]) == 0) return 0 }
  return 0
}
function runs(t) { return (shellctx(t) || progctx(t) || herestr(t) || (FSTR[d] && t ~ /^ *$/) || (HB && !hq)) }
function hdend(   k, line) {             # at the start of a line of an interpreter heredoc: its end?
  k = i; while (k <= n && substr(s, k, 1) != "\n") k++
  line = substr(s, i, k - i); if (hs) sub(/^\t+/, "", line)
  if (line == hw) { HB = 0; i = k + 1 }
}
BEGIN { RS = "\001" }
{ s = s (NR > 1 ? "\001" : "") $0 }      # a literal \001 in the command is one more byte, not a new command
END {
  n = length(s); d = 0; FE[0] = ""; FK[0] = ""; FC[0] = 0; FSTR[0] = 0; QD[0] = ""; CUR[0] = ""
  FP[0] = 0; FD[0] = 0; DL[0] = 0; PP[0] = 0; SD[0] = 0; ANY[0] = 0
  hit = 0; hp = 0; HB = 0; i = 1
  while (i <= n) {
    c = substr(s, i, 1); nx = substr(s, i + 1, 1); p = (i > 1) ? substr(s, i - 1, 1) : ""
    if (QD[d] == sq) { if (c == sq) QD[d] = ""; else CUR[d] = CUR[d] mask(c); i++; continue }
    if (QD[d] == "A") {                                  # $'…': backslash escapes, data
      if (c == "\\") { CUR[d] = CUR[d] "_"; i += 2; continue }
      if (c == sq) QD[d] = ""; else CUR[d] = CUR[d] mask(c)
      i++; continue
    }
    if (QD[d] == "E") {                                  # \"…\" inside a "…" code string
      if (c == "\\" && nx == "\"") { QD[d] = ""; i += 2; continue }
      if (c == "\"") { QD[d] = ""; popto(opener("\"", "subgrpkw")); i++; continue }
      CUR[d] = CUR[d] mask(c); i++; continue
    }
    if (QD[d] == "\"") {
      if (c == "\"") { QD[d] = ""; i++; continue }
      if (c == "\\") { CUR[d] = CUR[d] mask(nx); i += 2; continue }
      if (c == "$" && nx == "(") { code = (herestr(CUR[d]) || progctx(CUR[d])); CUR[d] = CUR[d] "_"; push(")", "cs", code, 0, 0); i += 2; continue }
      if (c == "`") { code = (herestr(CUR[d]) || progctx(CUR[d])); CUR[d] = CUR[d] "_"; push("`", "cs", code, 0, 0); i++; continue }
      CUR[d] = CUR[d] mask(c); i++; continue
    }
    if (c == "\\") {
      if (nx == "\n") { i += 2; continue }
      if (FE[d] == "\"" && nx == "\"") { QD[d] = "E"; i += 2; continue }
      CUR[d] = CUR[d] mask(nx); i += 2; continue
    }
    if (c == sq || c == "\"") {
      k = opener(c, "subgrpkw")
      if (k) { popto(k); i++; continue }                 # the end of a sh -c / eval string
      if (shellctx(CUR[d])) { CUR[d] = CUR[d] "_"; push(c, "str", 0, 1, 0) } else QD[d] = c
      i++; continue
    }
    if (c == "$" && nx == sq) {
      if (shellctx(CUR[d])) { CUR[d] = CUR[d] "_"; push(sq, "str", 0, 1, 0) } else QD[d] = "A"
      i += 2; continue
    }
    if (c == "`") {
      k = opener("`", "subgrpkw")
      if (k) { popto(k); i++; continue }
      code = runs(CUR[d]); CUR[d] = CUR[d] "_"; push("`", "cs", code, 0, 0); i++; continue
    }
    if (c == ")") {
      if (FK[d] == "kw" && FE[d] == "esac") { emit(0); i++; continue }    # a case pattern
      k = opener(")", "grpkw")
      if (k) popto(k); else emit(0)
      i++; continue
    }
    if (c == "#" && (CUR[d] == "" || CUR[d] ~ /[ \t]$/)) { while (i <= n && substr(s, i, 1) != "\n") i++; continue }
    if (c == "$" && nx == "(") { code = runs(CUR[d]); CUR[d] = CUR[d] "_"; push(")", "cs", code, 0, 0); i += 2; continue }
    if (c == "<" && nx == "(") { code = isprog(CUR[d]); CUR[d] = CUR[d] " _"; push(")", "cs", code, 0, 0); i += 2; continue }
    if (c == ">" && nx == "(") {                         # >(…) reads what its stage writes
      k = ((PP[d] && DL[d]) || SD[d] || cw(CUR[d]) ~ fre); CUR[d] = CUR[d] " _"; push(")", "cs", 0, 0, k); i += 2; continue
    }
    if (c == "<" && nx == "<") {
      if (substr(s, i + 2, 1) == "<") { CUR[d] = CUR[d] " <<< "; i += 3; continue }
      j = i + 2; hs = 0; q = 0
      if (substr(s, j, 1) == "-") { hs = 1; j++ }
      while (substr(s, j, 1) == " " || substr(s, j, 1) == "\t") j++
      w = ""
      while (j <= n) { e = substr(s, j, 1); if (e ~ /[ \t\n;&|<>()]/) break; if (e == "\"" || e == sq || e == "\\") q = 1; else w = w e; j++ }
      if (w != "") { hp = 1; hw = w; hx = isprog(CUR[d]); hq = q; CUR[d] = CUR[d] " <<_ " }
      i = j; continue
    }
    if (c == "\n") {
      i++
      if (!hp && !HB && PP[d] && CUR[d] !~ /[^ ]/ && !SD[d]) continue        # cmd |<newline> cmd
      emit(0)
      if (hp) {
        hp = 0
        if (hx) HB = 1
        else {
          while (i <= n) {
            k = i; while (k <= n && substr(s, k, 1) != "\n") k++
            line = substr(s, i, k - i); i = k + 1
            if (hs) sub(/^\t+/, "", line)
            if (line == hw) break
          }
        }
      }
      if (HB) hdend()
      continue
    }
    if (c == ";") { emit(0); i++; continue }
    if (c == "|") {
      if (p == ">") { CUR[d] = CUR[d] c; i++; continue }
      if (nx == "|") { emit(0); i += 2; continue }
      emit(1); i += (nx == "&") ? 2 : 1; continue
    }
    if (c == "&") {
      if (p == ">" || p == "<" || nx == ">") { CUR[d] = CUR[d] c; i++; continue }
      emit(0); i += (nx == "&") ? 2 : 1; continue
    }
    if (c == "(") { if (!cmdpos(CUR[d])) emit(0); push(")", "sub", 0, 0, PP[d] && DL[d]); i++; continue }
    if (c == "{" && cmdpos(CUR[d]) && (nx == "" || nx ~ /[ \t\n]/)) { push("}", "grp", 0, 0, PP[d] && DL[d]); i++; continue }
    if (c == "}" && cmdpos(CUR[d]) && (nx == "" || nx ~ /[ \t\n;&|)<>]/)) {
      k = opener("}", "kw")
      if (k) popto(k); else emit(0)
      i++; continue
    }
    if (c ~ /[a-z]/ && (p == "" || p ~ /[ \t\n;&|(){}]/) && cmdpos(CUR[d])) {   # reserved words
      j = i; while (j <= n && substr(s, j, 1) ~ /[a-z]/) j++
      e = substr(s, j, 1); w = substr(s, i, j - i)
      if ((e == "" || e ~ /[ \t\n;&|()<>]/) && w ~ /^(if|while|until|for|select|case|fi|done|esac)$/) {
        if (w ~ /^(fi|done|esac)$/) { k = opener(w, "grpkw"); if (k) { popto(k); i = j; continue } }
        else push((w == "if") ? "fi" : (w == "case") ? "esac" : "done", "kw", 0, 0, PP[d] && DL[d])
      }
      CUR[d] = CUR[d] w; i = j; continue
    }
    if (c == "\t") c = " "
    CUR[d] = CUR[d] c; i++
  }
  while (d > 0) pop()
  emit(0)
  if (hit) print "hit"
}'
[ -n "$(printf '%s' "$cmd" | LC_ALL=C awk -v sq="'" -v fre="$SHELL_HYG_FETCH_RE" -v ire="$SHELL_HYG_INTERP_RE" "$hyg_lex")" ] \
  && defer "a download piped into an interpreter (curl … | sh, bash <(curl …), sh -c \"\$(curl …)\", eval \"\$(curl …)\") runs downloaded code unreviewed — download to a file, check its sha256, read it, then run it instead"
return 0
