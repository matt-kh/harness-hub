# shellcheck shell=bash

# Section 35 (bundle core): shell hygiene. Pipe-to-shell only for now; sudo/doas, recursive
# removal outside the checkout and chmod -R 777 are planned (docs/roadmap.md).
# rule: curl|wget|fetch … | [sudo] sh|bash|zsh|ksh|dash|python[3]|perl|node|ruby reading its program from stdin (no -c/-m/-e/-n/-p or script operand; sh -s, bash -, python3 -, /dev/stdin count; source|. /dev/stdin too) | sh|bash|source|. <(curl|wget|fetch …) | sh|bash -c "$(curl|wget|fetch …)" | eval "$(curl|wget|fetch …)" -> ask : runs downloaded code unreviewed; download to a file, check its sha256, read it, then run it instead
#
# How a command is read: the raw command ($cmd, newlines kept) is walked once by awk, a small
# quote-aware matcher (not a shell parser). Stages are split on | (pipe) and on ; & && || newline
# ( ) { } (list); `$( )`, `<( )`, backticks, subshells and the string of `sh|bash -c` / `eval`
# are frames of their own, so `sh -c 'curl … | sh'` is read as code. Any other quoted text is
# data: its separators and spaces are masked, so `echo "curl … | sh"` and `grep 'curl.*| sh' f`
# stay one harmless command, while a quoted command word (`"curl"`) still counts. Heredoc bodies
# are data unless an interpreter reads them; comments are dropped. A frame that ran a downloader
# passes that to the stage holding it, so `(curl …) | sh` and `sh -c "$(curl …)"` are seen. The
# command word skips assignments, `!`/`if`/`then`/`do`/`time` and wrappers (sudo, doas, env,
# command, exec, nohup, nice, xargs, …) and is compared by basename (/usr/bin/curl).
SHELL_HYG_FETCH_RE='^(curl|wget|fetch)$'                                              # downloaders, by basename
SHELL_HYG_INTERP_RE='^(sh|bash|zsh|ksh|dash|python[0-9.]*|perl|ruby|node|nodejs)$'   # interpreters, by basename
repo_owns core/guard.d/35-shell-hygiene base && return 0   # principle 8: the repository's .harness.toml owns this section or domain base
# ---- Pipe-to-shell: ask (deferred, so a later deny still wins) -------------------------------
local hyg_n hyg_lex
hyg_n=${cmd//\\/}; hyg_n=${hyg_n//\"/}; hyg_n=${hyg_n//\'/}
case "$hyg_n" in *curl*|*wget*|*fetch*) ;; *) return 0 ;; esac     # builtins only: most commands stop here
hyg_lex='
function base(w) { sub(/.*\//, "", w); return w }
# cmdword(T) -> basename of the command word of stage text T; A[1..NA] = its words, CI = the index
function cmdword(t,   k, w, wrap, skip) {
  NA = split(t, A, /[ \t]+/); wrap = ""; skip = 0
  for (k = 1; k <= NA; k++) {
    w = A[k]
    if (w == "") continue
    if (skip) { skip = 0; continue }
    if (w ~ /^(!|then|do|else|elif|if|while|until|time)$/) continue
    if (w ~ /^(sudo|doas|env|command|builtin|exec|nohup|nice|stdbuf|setsid|ionice|unbuffer|xargs)$/) { wrap = w; continue }
    if (w ~ /^[A-Za-z_][A-Za-z0-9_]*=/) continue
    if (wrap != "" && w ~ /^-/) {
      if ((wrap ~ /^(sudo|doas)$/ && w ~ /^-[ugCDprtUT]$/) || (wrap == "env" && w ~ /^-[uCS]$/) \
          || (wrap ~ /^(nice|ionice)$/ && w ~ /^-[ncp]$/) || (wrap == "xargs" && w ~ /^-[InPLsdaE]$/)) skip = 1
      continue
    }
    CI = k; return base(w)
  }
  CI = NA + 1; return ""
}
# stdin_prog(T) -> 1 when stage T is an interpreter that reads its program from stdin
function stdin_prog(t,   c, kind, k, w, skip, s) {
  c = cmdword(t)
  if (c == "source" || c == ".") return (A[CI + 1] ~ /^\/(dev\/stdin|dev\/fd\/0|proc\/self\/fd\/0)$/)
  if (c !~ ire) return 0
  kind = (c ~ /^(sh|bash|zsh|ksh|dash)$/) ? "sh" : (c ~ /^python/) ? "py" : (c ~ /^node/) ? "js" : "pl"
  skip = 0; s = 0
  for (k = CI + 1; k <= NA; k++) {
    w = A[k]
    if (w == "") continue
    if (skip) { skip = 0; continue }
    if (w ~ /^[0-9]*(<|>|&>)/) { if (w ~ /^[0-9]*(<|>>?|&>>?|>&)$/) skip = 1; continue }   # redirections
    if (w == "-") return 1
    if (w == "--") { k++; while (k <= NA && A[k] == "") k++; return (s || k > NA || A[k] == "-") }
    if (w ~ /^\+/ && kind == "sh") { if (w ~ /^\+[oO]$/) skip = 1; continue }
    if (w ~ /^--/) {
      if (kind == "js" && w ~ /^--(eval|print|check)(=|$)/) return 0
      if (kind == "js" && w ~ /^--(require|import)$/) skip = 1
      if (kind == "sh" && w ~ /^--(rcfile|init-file)$/) skip = 1
      if (w ~ /^--(help|version)$/) return 0
      continue
    }
    if (w ~ /^-/) {
      if (kind == "sh") { if (w ~ /c/) return 0; if (w ~ /s/) s = 1; if (w ~ /^-[oO]$/) skip = 1; continue }
      if (kind == "py") { if (w ~ /^-[^WX]*[cm]/) return 0; if (w ~ /^-[WXQ]$/) skip = 1; continue }
      if (kind == "js") { if (w ~ /^-[^-]*[epc]/) return 0; if (w ~ /^-r$/) skip = 1; continue }
      if (w ~ /^-[^-]*[eEnp]/) return 0                                  # perl, ruby
      continue
    }
    if (w ~ /^\/(dev\/stdin|dev\/fd\/0|proc\/self\/fd\/0)$/) return 1             # the pipe, by name
    return (kind == "sh" && s)                                           # an operand: a script file
  }
  return 1
}
function shellctx(t) { return (t ~ /(^|[ \/])(sh|bash|zsh|dash|ksh)( +-[A-Za-z]+)* +-[A-Za-z]*c +$/ || t ~ /(^| )eval +$/) }
function herestr(t) { return (t ~ /<<< *$/ && cmdword(t) ~ ire) }
function isprog(t,   c) { c = cmdword(t); return (c ~ ire || c == "source" || c == ".") }
function mask(c) { return (c ~ /[ \t\n;&|()<>`$\\{}"]/ || c == sq) ? "_" : c }
function emit(pipe,   t, c) {
  t = CUR[d]
  if (t ~ /[^ ]/ || SD[d]) {
    c = cmdword(t)
    if (PP[d] && DL[d] && stdin_prog(t)) hit = 1
    if (c ~ fre || SD[d]) { DL[d] = 1; ANY[d] = 1 }
  }
  CUR[d] = ""; SD[d] = 0
  if (pipe) PP[d] = 1; else { PP[d] = 0; DL[d] = 0 }
}
# push(END, CODE, STR): a new frame ending at END; CODE = 1 when its output runs as a program,
# STR = 1 for the string of sh -c / eval (a substitution as its first word is that program)
function push(e, code, str) { d++; FE[d] = e; FC[d] = code; FSTR[d] = str; QD[d] = ""; CUR[d] = ""; DL[d] = 0; PP[d] = 0; SD[d] = 0; ANY[d] = 0 }
function pop() { emit(0); if (ANY[d] && FC[d]) hit = 1; d--; if (ANY[d + 1]) SD[d] = 1 }
function runs(t) { return (shellctx(t) || herestr(t) || (FSTR[d] && t ~ /^ *$/)) }
BEGIN { RS = "\001" }
{
  s = $0; n = length(s); d = 0; FE[0] = ""; FC[0] = 0; FSTR[0] = 0; QD[0] = ""; CUR[0] = ""; DL[0] = 0; PP[0] = 0; SD[0] = 0; ANY[0] = 0
  hit = 0; hp = 0; i = 1
  while (i <= n) {
    c = substr(s, i, 1); nx = substr(s, i + 1, 1); p = (i > 1) ? substr(s, i - 1, 1) : ""
    if (QD[d] == sq) { if (c == sq) QD[d] = ""; else CUR[d] = CUR[d] mask(c); i++; continue }
    if (QD[d] == "E") {                                  # \"…\" inside a "…" code string
      if (c == "\\" && nx == "\"") { QD[d] = ""; i += 2; continue }
      if (c == "\"") { QD[d] = ""; pop(); i++; continue }
      CUR[d] = CUR[d] mask(c); i++; continue
    }
    if (QD[d] == "\"") {
      if (c == "\"") { QD[d] = ""; i++; continue }
      if (c == "\\") { CUR[d] = CUR[d] mask(nx); i += 2; continue }
      if (c == "$" && nx == "(") { code = herestr(CUR[d]); CUR[d] = CUR[d] "_"; push(")", code, 0); i += 2; continue }
      if (c == "`") { code = herestr(CUR[d]); CUR[d] = CUR[d] "_"; push("`", code, 0); i++; continue }
      CUR[d] = CUR[d] mask(c); i++; continue
    }
    if (c == "\\") {
      if (nx == "\n") { i += 2; continue }
      if (FE[d] == "\"" && nx == "\"") { QD[d] = "E"; i += 2; continue }
      CUR[d] = CUR[d] mask(nx); i += 2; continue
    }
    if (FE[d] != "" && c == FE[d]) { pop(); i++; continue }
    if (c == sq || c == "\"") {
      if (shellctx(CUR[d])) { emit(0); push(c, 0, 1) } else QD[d] = c
      i++; continue
    }
    if (c == "#" && (CUR[d] == "" || CUR[d] ~ /[ \t]$/)) { while (i <= n && substr(s, i, 1) != "\n") i++; continue }
    if (c == "$" && nx == "(") { code = runs(CUR[d]); CUR[d] = CUR[d] "_"; push(")", code, 0); i += 2; continue }
    if (c == "`") { code = runs(CUR[d]); CUR[d] = CUR[d] "_"; push("`", code, 0); i++; continue }
    if ((c == "<" || c == ">") && nx == "(") { code = (c == "<" && isprog(CUR[d])); CUR[d] = CUR[d] " _"; push(")", code, 0); i += 2; continue }
    if (c == "<" && nx == "<") {
      if (substr(s, i + 2, 1) == "<") { CUR[d] = CUR[d] " <<< "; i += 3; continue }
      j = i + 2; hs = 0
      if (substr(s, j, 1) == "-") { hs = 1; j++ }
      while (substr(s, j, 1) == " " || substr(s, j, 1) == "\t") j++
      w = ""
      while (j <= n) { e = substr(s, j, 1); if (e ~ /[ \t\n;&|<>()]/) break; if (e != "\"" && e != sq && e != "\\") w = w e; j++ }
      if (w != "") { hp = 1; hw = w; hx = isprog(CUR[d]) }
      i = j; continue
    }
    if (c == "\n") {
      emit(0); i++
      if (hp) {
        hp = 0
        if (!hx) {
          while (i <= n) {
            k = index(substr(s, i), "\n")
            if (k == 0) { line = substr(s, i); i = n + 1 } else { line = substr(s, i, k - 1); i += k }
            if (hs) sub(/^\t+/, "", line)
            if (line == hw) break
          }
        }
      }
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
    if (c == "(") { emit(0); push(")", 0, 0); i++; continue }
    if (c == ")") { emit(0); i++; continue }
    if ((c == "{" || c == "}") && (CUR[d] == "" || CUR[d] ~ /[ \t]$/) && (nx == "" || nx ~ /[ \t\n;]/)) { emit(0); i++; continue }
    if (c == "\t") c = " "
    CUR[d] = CUR[d] c; i++
  }
  while (d > 0) pop()
  emit(0)
  if (hit) print "hit"
}'
[ -n "$(printf '%s' "$cmd" | awk -v sq="'" -v fre="$SHELL_HYG_FETCH_RE" -v ire="$SHELL_HYG_INTERP_RE" "$hyg_lex")" ] \
  && defer "a download piped into an interpreter (curl … | sh, bash <(curl …), sh -c \"\$(curl …)\", eval \"\$(curl …)\") runs downloaded code unreviewed — download to a file, check its sha256, read it, then run it instead"
return 0
