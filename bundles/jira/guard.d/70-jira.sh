# shellcheck shell=bash

# Section 70 (bundle jira): Jira write governance.
# rule: jira set KEY issuelinks | create --field issuelinks= -> deny : use the governed link commands
# rule: jira link A TYPE B (both agent-labelled, type in HARNESS_JIRA_LINK_TYPES_RE) -> allow : otherwise deny
# rule: jira create without a provenance label (agent-drafted|agent-created) -> deny : every agent-created ticket is labelled; use labels agent-drafted (or agent-created) instead
# rule: jira create with more than one --field labels -> deny : the last one wins in Jira; pass a single --field labels='["agent-drafted"]' instead
# rule: jira create with a provenance label -> allow : creates are promptless
# rule: jira label KEY add agent-* -> allow : governance labelling is free
# rule: jira set|comment|upload|label KEY on agent-labelled tickets -> allow : promptless (so is a state change, on the main thread)
# rule: jira transition KEY, jira set KEY status|resolution on a human ticket -> ask : ticket state is a human decision; run it only on the user's explicit request (they confirm it), or ask the user to transition it in Jira instead
# rule: jira transition, jira set KEY status|resolution from a subagent -> deny : a subagent never changes ticket state, on human and agent-labelled tickets alike; hand the command back to the main thread
# rule: jira state change without a literal key ($VAR, xargs, LBL-1/../X, none) or whose labels cannot be read -> deny : the ticket cannot be checked; type the key literally (e.g. PROJ-123), or ask the user to transition it
# rule: jira write whose key is not a literal PROJ-123 word -> ask : the ticket cannot be checked; use a literal key instead
# rule: jira hidden from the guard (quoted/escaped/ANSI-C/globbed or case-changed command words, a $VAR/$(…) subcommand, jira fed by xargs, alias, a variable or $(which jira), or a jira call written anywhere outside a known data position) -> ask : the subcommand cannot be checked; write it literally and unquoted instead (a subagent is denied unless it is a known non-state write)
# rule: jira guard scanner failure (python3 missing, broken or timed out) -> ask : the command cannot be checked; ask the user to run it, or fix python3 (a subagent is denied)
# rule: jira writes to human tickets -> ask : need an explicit user request; ask the user, or label the ticket agent-worked first
# repo-override: WORK_TICKET_ALLOW_TRANSITION = "" -> deprecated, no effect since #67: a state change on a human ticket or issue asks on the main thread (and is denied in a subagent) with or without it; remove it
# repo-override: WORK_TICKET_LABELED_DECISION = "allow" -> allow|ask: the decision for writes to agent-labelled tickets, issues, MRs and PRs
repo_owns jira/guard.d/70-jira tracker && return 0   # principle 8: the repository's .harness.toml owns this section or domain tracker
# ---- Jira writes: governance gate (work-ticket / create-ticket skills) -----------
# create (with provenance label) and `label KEY add agent-*`: promptless.
# set/comment/upload/label/link/transition on tickets carrying ANY agent-* label: promptless.
# Purely human tickets (no agent-* label): writes ask. Ticket state (transition, set
# status|resolution) is a human decision (principle 2): on a human ticket it asks on the main
# thread (deferred), from a subagent it is denied before any lookup, and a state change whose
# ticket cannot be checked (no literal key, failed label lookup) is denied.
# link / create --link: only between agent-labelled tickets (deny otherwise).
#
# The command is read by a small shell scanner (JIRA_SCAN_PY below, python3 is a requirement of
# this bundle), not by regexes over the whole text, so text that only mentions jira (a comment
# body, a commit message, a grep pattern, a path argument) decides nothing. It prints:
#   C <clause>   a jira call in command position — after assignments and wrappers (env, exec,
#                command, sudo, nice, timeout, xargs, find -exec …), inside sh/bash -c strings,
#                eval, $(…) and backticks, heredoc bodies fed to a shell and text piped into one —
#                normalised to `jira VERB ARG…` (one space between words, quotes removed, a
#                comment body replaced by _, ; & | inside words replaced by _)
#   H <verb>     a jira call the guard cannot read: quoted/escaped/ANSI-C/globbed or case-changed
#                command words, a $VAR/$(…) verb ($), no verb (xargs jira, -), a NAME=jira
#                assignment or alias (-), $(which jira) as the command; and, failing closed, any
#                `jira VERB` text outside a known data position (the jira client's own arguments,
#                git commit/log/… arguments, grep/rg patterns, echo/printf and cat/tee heredocs
#                or here-strings whose pipeline holds only non-executing stages)
#   H !          the scanner itself failed (python3 missing, broken or timed out)
# Command, process and ${…} substitutions are scanned wherever they appear; heredocs and
# here-strings fed to a shell, and text piped into a shell through any number of stages, are
# scanned as commands; `sh -c CODE ARGS` runs ARGS as a command when CODE uses "$@" or "$0".
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
# cheap prefilter, so the scanner runs only when the command may hold a jira call: the name with
# quotes, backslashes and line continuations removed (j\ira, j""ira, ji\<newline>ra), an ANSI-C
# $'…' word (it can spell anything), or a state verb after any command word (a glob or $VAR
# spelling of the client: jir? transition, ${J}ra set KEY status)
printf '%s' "$cmd" | tr -d '\\\n"'"'" | grep -qi 'jira' \
  || printf '%s' "$flat" | grep -qF "\$'" \
  || printf '%s' "$flat_dq" | grep -qiE '(^|[[:space:]])(transition|set[[:space:]]+[^[:space:]]+[[:space:]]+(status|resolution))([[:space:]]|$)' \
  || return 0
# shellcheck disable=SC2168  # sections are wrapped in a function by build.sh
local jscan flat cl jv jk jf act lbls a b ltype k lb n_state state_unchecked state_keys is_state keys unchecked \
  all_gov state_human n_create n_prov n_link lkeys lblflag
JIRA_SCAN_PY=""
read -r -d '' JIRA_SCAN_PY <<'PY' || true
import codecs, fnmatch, re, sys
WRITES = ("set", "create", "transition", "upload", "comment", "label", "link")
WRAP = {"exec", "command", "builtin", "nohup", "time", "then", "do", "else", "elif", "if", "while",
        "until", "!", "{", "sudo", "doas", "nice", "stdbuf", "timeout", "xargs", "watch", "setsid",
        "unbuffer", "caffeinate", "chronic", "ionice", "taskset", "env", "noglob", "nocorrect", "parallel"}
WRAP_ARG = {"sudo": "ugCDhprRTU", "doas": "uC", "nice": "n", "xargs": "IidEeaLlnPs", "ionice": "cnp",
            "stdbuf": "ioe", "env": "uCS", "watch": "nd", "timeout": "sk", "time": "fo"}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "mksh", "fish", "busybox"}
INTERP_RE = re.compile(r"^(python[0-9.]*|perl|node|ruby|php|osascript|pwsh)$")
PY_VALUE_OPTS = ("-X", "-W", "-Q")
# stages that never execute what they read (a pipeline made only of these keeps text as data)
SINKS = {"cat", "tee", "grep", "egrep", "fgrep", "rg", "head", "tail", "wc", "sort", "uniq", "less",
         "more", "jq", "cut", "tr", "fold", "column", "nl", "base64", "xxd", "od"}
# commands whose arguments are data (patterns, messages, printed text)
SEARCHERS = {"grep", "egrep", "fgrep", "rg", "ag", "ack"}
GIT_DATA_SUBS = {"commit", "log", "tag", "notes", "show", "grep", "shortlog", "rev-list", "describe",
                 "status", "diff", "blame"}
JIRA_TEXT_RE = re.compile(r"\bjira(\.py)?\W+(" + "|".join(WRITES) + r")\b", re.I)
KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*-[0-9]+$")
ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
ALIAS_JIRA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*=(.*/)?jira(\.py)?$", re.I)
out, seen = [], set()


class W(object):
    def __init__(self, v, q, d):
        self.v, self.q, self.d = v, q, d


class Clause(object):
    def __init__(self, words, docs, sep):
        self.words, self.docs, self.sep = words, docs, sep


def emit(kind, text):
    line = "%s %s" % (kind, text)
    if line not in seen:
        seen.add(line)
        out.append(line)


def base(v):
    b = v.rsplit("/", 1)[-1]
    return b[1:] if b.startswith("=") else b   # zsh =cmd expands to the command's path


def jiraish(v):
    return base(v).lower() in ("jira", "jira.py")


def globbed_jira(v):
    b = base(v).lower()
    return bool(re.search(r"[*?\[]", b)) and (fnmatch.fnmatchcase("jira", b) or fnmatch.fnmatchcase("jira.py", b))


def ansi_c(body):
    try:
        return codecs.decode(body.encode("latin-1", "backslashreplace"), "unicode_escape")
    except Exception:
        return body


def heredoc_head(s, i):
    """at s[i:] just after '<<' or '<<-': (delimiter, quoted, end index) or None"""
    m = re.match(r"""[ \t]*(?:'([^'\n]*)'|"([^"\n]*)"|\\?([^\s;&|()<>'"]+))""", s[i:])
    if not m:
        return None
    if m.group(1) is not None:
        return m.group(1), True, i + m.end()
    if m.group(2) is not None:
        return m.group(2), True, i + m.end()
    return m.group(3), s[i:i + m.end()].lstrip(" \t").startswith("\\"), i + m.end()


def skip_body(s, i, delim, strip):
    """s[i] starts a heredoc body line: (body, index after the delimiter line)"""
    n, body = len(s), []
    while i < n:
        j = s.find("\n", i)
        line = s[i:] if j < 0 else s[i:j]
        i = n if j < 0 else j + 1
        if (line.lstrip("\t") if strip else line) == delim:
            return "\n".join(body), i
        body.append(line)
    return "\n".join(body), n


def match_close(s, i, close):
    """s[i] follows an opening '$(' / '<(' / '>(' (close ')') or '${' (close '}'): index of the close"""
    n, depth, pend = len(s), 0, []
    while i < n:
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if c == "'":
            j = s.find("'", i + 1)
            i = n if j < 0 else j + 1
            continue
        if c == '"':
            i += 1
            while i < n and s[i] != '"':
                i += 2 if s[i] == "\\" else 1
            i += 1
            continue
        if c == "<" and s.startswith("<<", i) and not s.startswith("<<<", i):
            strip = s.startswith("<<-", i)
            h = heredoc_head(s, i + (3 if strip else 2))
            if h:
                pend.append((h[0], strip))
                i = h[2]
                continue
        if c == "\n" and pend:
            i += 1
            for d, st in pend:
                _b, i = skip_body(s, i, d, st)
            pend = []
            continue
        if c in "({":
            depth += 1
        elif c == close:
            if depth == 0:
                return i
            depth -= 1
        i += 1
    return n


def subs(text, depth):
    """scan the command substitutions of text that undergoes expansion (${...} bodies, unquoted heredocs)"""
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == "'" and i > 0 and text[i - 1] != "$":
            i += 1
            continue
        if text.startswith("$(", i) or text.startswith("<(", i) or text.startswith(">(", i):
            j = match_close(text, i + 2, ")")
            scan(text[i + 2:j], depth + 1)
            i = j + 1
            continue
        if text.startswith("${", i):
            j = match_close(text, i + 2, "}")
            subs(text[i + 2:j], depth + 1)
            i = j + 1
            continue
        if c == "`":
            j = text.find("`", i + 1)
            j = n if j < 0 else j
            scan(text[i + 1:j], depth + 1)
            i = j + 1
            continue
        i += 1


def parse(s, depth):
    """split s into clauses; command, process and ${...} substitutions are scanned on the way"""
    clauses = []
    st = {"words": [], "docs": [], "cur": None, "drop": False, "here": False}
    pend = []
    n, i = len(s), 0

    def start():
        if st["cur"] is None:
            st["cur"] = [[], False, False]

    def endw():
        cur = st["cur"]
        if cur is not None:
            if st["here"]:
                st["docs"].append(("".join(cur[0]), True))   # a here-string: expanded already
                st["here"] = False
            elif st["drop"]:
                st["drop"] = False
            else:
                st["words"].append(W("".join(cur[0]), cur[1], cur[2]))
            st["cur"] = None

    def endc(sep):
        endw()
        if st["words"] or st["docs"]:
            clauses.append(Clause(st["words"], st["docs"], sep))
        st["words"], st["docs"], st["drop"], st["here"] = [], [], False, False

    def dollar(i, cur):
        """s[i] == '$' with a substitution after it: append it to cur, scan it; returns the next index"""
        if s.startswith("$(", i):
            j = match_close(s, i + 2, ")")
            scan(s[i + 2:j], depth + 1)
        elif s.startswith("${", i):
            j = match_close(s, i + 2, "}")
            subs(s[i + 2:j], depth + 1)
        else:
            return None
        cur[0].append(s[i:j + 1])
        cur[2] = True
        return j + 1

    while i < n:
        c = s[i]
        if c in " \t":
            endw()
            i += 1
            continue
        if c == "\n":
            endc("\n")
            i += 1
            for d, strip, quoted, dl in pend:
                body, i = skip_body(s, i, d, strip)
                if not quoted:
                    subs(body, depth)
                dl.append((body, quoted))
            pend = []
            continue
        if c == "#" and st["cur"] is None:
            j = s.find("\n", i)
            i = n if j < 0 else j
            continue
        if c == "\\":
            if s.startswith("\\\n", i):
                i += 2
                continue
            start()
            st["cur"][1] = True
            st["cur"][0].append(s[i + 1:i + 2])
            i += 2
            continue
        if s.startswith("$'", i):
            start()
            j, buf = i + 2, []
            while j < n and s[j] != "'":
                buf.append(s[j:j + 2] if s[j] == "\\" else s[j])
                j += 2 if s[j] == "\\" else 1
            st["cur"][0].append(ansi_c("".join(buf)))
            st["cur"][1] = True
            i = j + 1
            continue
        if c == "'":
            start()
            st["cur"][1] = True
            j = s.find("'", i + 1)
            j = n if j < 0 else j
            st["cur"][0].append(s[i + 1:j])
            i = j + 1
            continue
        if c == '"':
            start()
            cur = st["cur"]
            cur[1] = True
            i += 1
            while i < n and s[i] != '"':
                ch = s[i]
                if ch == "\\" and i + 1 < n:
                    if s[i + 1] in '$`"\\':
                        cur[0].append(s[i + 1])
                    elif s[i + 1] != "\n":
                        cur[0].append(s[i:i + 2])
                    i += 2
                    continue
                if ch == "$":
                    k = dollar(i, cur)
                    if k is not None:
                        i = k
                        continue
                    cur[2] = True
                if ch == "`":
                    j = s.find("`", i + 1)
                    j = n if j < 0 else j
                    scan(s[i + 1:j], depth + 1)
                    cur[0].append(s[i:j + 1])
                    cur[2] = True
                    i = j + 1
                    continue
                cur[0].append(ch)
                i += 1
            i += 1
            continue
        if c == "$":
            start()
            k = dollar(i, st["cur"])
            if k is not None:
                i = k
                continue
            st["cur"][2] = True
            st["cur"][0].append(c)
            i += 1
            continue
        if c == "`":
            start()
            j = s.find("`", i + 1)
            j = n if j < 0 else j
            scan(s[i + 1:j], depth + 1)
            st["cur"][0].append(s[i:j + 1])
            st["cur"][2] = True
            i = j + 1
            continue
        if c in "<>" and s.startswith("(", i + 1):   # process substitution <(…) / >(…)
            start()
            j = match_close(s, i + 2, ")")
            scan(s[i + 2:j], depth + 1)
            st["cur"][0].append(s[i:j + 1])
            st["cur"][2] = True
            i = j + 1
            continue
        if c in "<>" or s.startswith("&>", i):
            cur = st["cur"]
            if cur is not None and not cur[1] and not cur[2] and "".join(cur[0]).isdigit():
                st["cur"] = None
            else:
                endw()
            op = re.match(r"&>>?|<<<|<<-|<<|>>|>&|<&|>\||<>|>|<", s[i:]).group(0)
            i += len(op)
            if op in (">&", "<&"):
                m = re.match(r"[ \t]*([0-9]+-?|-)(?=[\s;&|()<>]|$)", s[i:])
                if m:
                    i += m.end()
                    continue
            if op in ("<<", "<<-"):
                h = heredoc_head(s, i)
                if h:
                    pend.append((h[0], op == "<<-", h[1], st["docs"]))
                    i = h[2]
                continue
            if op == "<<<":
                st["here"] = True
                continue
            st["drop"] = True
            continue
        if c in ";&|()":
            endc(c)
            i += 1
            continue
        start()
        st["cur"][0].append(c)
        i += 1
    endc("")
    return clauses


def scan(s, depth=0):
    if depth > 8:
        if re.search("jira", s, re.I):
            emit("H", "-")
        return
    pipes, cur = [], []
    for c in parse(s, depth):
        cur.append(c)
        if c.sep != "|":
            pipes.append(cur)
            cur = []
    if cur:
        pipes.append(cur)
    for p in pipes:
        for k, c in enumerate(p):
            clause(c.words, c.docs, p[:k], p[k + 1:], depth)


def opt_skip(words, i, b):
    """skip the options of wrapper b starting at words[i]; returns the index of the next word"""
    takes = WRAP_ARG.get(b, "")
    first_pos = b == "timeout"
    while i < len(words):
        v = words[i].v
        if v == "--":
            return i + 1
        if b == "env" and ASSIGN_RE.match(v):
            i += 1
            continue
        if v.startswith("-") and len(v) > 1:
            i += 1
            if not v.startswith("--") and len(v) == 2 and v[1] in takes:
                i += 1
            continue
        if first_pos:
            first_pos = False
            i += 1
            continue
        return i
    return i


def text_of(cl):
    return " ".join(w.v for w in cl.words) + "\n" + "\n".join(b for b, _q in cl.docs)


def all_sinks(nxt):
    for c in nxt:
        if not c.words or base(c.words[0].v) not in SINKS or any(w.d for w in c.words):
            return False
    return True


def fallback(text):
    """fail closed: a jira call written anywhere outside a known data position is a hidden call"""
    for m in JIRA_TEXT_RE.finditer(text):
        emit("H", m.group(2).lower())


def clause(words, docs, prev, nxt, depth):
    """decide one clause; `skip` collects the word indices that are data or already handled"""
    skip, docs_done = set(), False
    for w in words:
        if ALIAS_JIRA_RE.match(w.v):
            emit("H", "-")
    i = 0
    while i < len(words) and ASSIGN_RE.match(words[i].v):
        i += 1
    while i < len(words):
        b = base(words[i].v)
        if b == "command" and i + 1 < len(words) and words[i + 1].v in ("-v", "-V"):
            return
        if b in WRAP:
            i = opt_skip(words, i + 1, b)
            continue
        if b == "find":
            for k in range(i + 1, len(words)):
                if words[k].v in ("-exec", "-execdir", "-ok", "-okdir"):
                    end = k + 1
                    while end < len(words) and words[end].v not in (";", "+"):
                        end += 1
                    clause(words[k + 1:end], [], [], [], depth)
                    skip.update(range(k + 1, end))
        break
    if i < len(words):
        cw = words[i]
        b = base(cw.v)
        lb = b.lower()
        rest = words[i + 1:]
        if INTERP_RE.match(b):
            k = i + 1
            while k < len(words):
                v = words[k].v
                if v in PY_VALUE_OPTS:
                    k += 2
                    continue
                if v.startswith("-") and v not in ("-c", "-e", "-E", "-m", "-"):
                    k += 1
                    continue
                break
            if k < len(words) and (jiraish(words[k].v) or globbed_jira(words[k].v)):
                cw, b, lb, rest, i = words[k], base(words[k].v), base(words[k].v).lower(), words[k + 1:], k
            elif k >= len(words) or words[k].v == "-":
                fallback("\n".join(text_of(c) for c in prev))     # the interpreter runs its stdin
        if lb in SHELLS:
            code_at = None
            for k in range(i + 1, len(words)):
                v = words[k].v
                if re.match(r"^-[A-Za-z]*c[A-Za-z]*$", v):
                    code_at = k + 1
                    while code_at < len(words) and words[code_at].v == "--":
                        code_at += 1
                    break
                if not v.startswith("-"):
                    break
            if code_at is not None and code_at < len(words):
                code = words[code_at].v
                scan(code, depth + 1)
                skip.add(code_at)
                if re.search(r"\$(\{?[@*0-9])", code):     # "$@" / "$0" / "$1" run the positional words
                    after = words[code_at + 1:]
                    clause(after, [], [], [], depth)
                    clause(after[1:], [], [], [], depth)
                    skip.update(range(code_at + 1, len(words)))
            else:
                if prev:
                    scan("\n".join(text_of(c) for c in prev), depth + 1)
                for body, _q in docs:
                    scan(body, depth + 1)
                docs_done = True
        elif lb == "eval":
            scan(" ".join(w.v for w in rest), depth + 1)
            skip.update(range(i, len(words)))
        elif lb in ("jira", "jira.py") or globbed_jira(cw.v):
            jira_clause(cw, b, rest)
            skip.update(range(i, len(words)))
        elif cw.d and cw.v[:1] in ("$", "`"):
            nv = rest[0].v.lower() if rest and not rest[0].d else "-"
            if re.search("jira", cw.v, re.I):
                emit("H", nv)
            elif nv == "transition" or (nv == "set" and len(rest) > 2 and rest[2].v.lower() in ("status", "resolution")):
                emit("H", nv)        # ${J}ra transition KEY: a dynamic command word in front of a state verb
        elif re.search(r"[*?\[]", b) and rest and rest[0].v.lower() in ("transition", "set"):
            emit("H", rest[0].v.lower())
        elif lb in SEARCHERS:
            skip.update(range(i, len(words)))
        elif lb == "git":
            k = i + 1
            while k < len(words) and words[k].v.startswith("-"):
                k += 2 if words[k].v in ("-c", "-C") else 1
            if k < len(words) and words[k].v in GIT_DATA_SUBS:
                skip.update(range(k, len(words)))
        elif lb in ("echo", "printf") and all_sinks(nxt):
            skip.update(range(i, len(words)))
        elif lb in ("cat", "tee") and all_sinks(nxt) and not any(w.d for w in rest):
            skip.update(range(i, len(words)))
            docs_done = True
    text = " ".join(w.v for k, w in enumerate(words) if k not in skip)
    if not docs_done:
        text += "\n" + "\n".join(b for b, _q in docs)
    fallback(text)


def norm(v):
    v = v.replace("\n", " ").replace("\t", " ")
    v = re.sub(r"[;&|]", "_", v)
    if re.search("jira", v, re.I):
        v = re.sub(r"\s+", "_", v)
    return v if v != "" else "''"


def jira_clause(cw, b, rest):
    hidden = cw.q or cw.d or b not in ("jira", "jira.py")
    if not rest:
        emit("H", "-")
        return
    verb = rest[0]
    if verb.d or verb.v[:1] in ("$", "`"):
        emit("H", "$")
        return
    if hidden or verb.q or not re.match(r"^[a-z]+$", verb.v):
        emit("H", verb.v.lower() or "-")
        return
    args = [norm(w.v) for w in rest[1:]]
    if verb.v == "comment" and len(args) > 1:
        args = args[:1] + ["_"]
    emit("C", " ".join(["jira", verb.v] + args))


if __name__ == "__main__":
    try:
        scan(sys.argv[1])
    except Exception:
        out.append("H !")
    sys.stdout.write("".join(l + "\n" for l in out))
PY
jscan=$(hn_timeout 5 python3 -c "$JIRA_SCAN_PY" "$cmd" 2>/dev/null) || jscan="H !"   # scanner failure: fail closed
# -- 0. calls the guard cannot read: a known read passes, a known non-state write asks, anything
#       else (transition, set, $VAR, no verb, unknown) is a human decision (a subagent is denied)
while read -r jk jv; do
  [ "$jk" = H ] || continue
  case "$jv" in
    get|links|search|fields|sprints|versions|transitions|whoami|attachments|download|api) ;;
    '!')
      human_decision_defer "jira guard scanner failed (python3 missing, broken or timed out), so this jira command cannot be checked — ask the user to run it, or fix python3 (a subagent hands the command back to the main thread)" ;;
    comment|upload|label|link|create)
      defer "jira $jv in a form the guard cannot check (quoted, escaped or case-changed command words) — write the jira subcommand literally and unquoted instead" ;;
    *)
      human_decision_defer "jira call the guard cannot check (quoted, escaped or case-changed command words, a \$VAR or \$(…) subcommand, jira fed by xargs, an alias or a variable) may change ticket state — write it literally as 'jira VERB KEY …' instead" ;;
  esac
done <<EOF
$jscan
EOF
# the jira calls, one normalised clause per line (word 1 = jira, word 2 = verb, word 3 = key)
flat=$(printf '%s\n' "$jscan" | sed -n 's/^C //p')
printf '%s\n' "$flat" | grep -qE '^jira (set|create|transition|upload|comment|label|link)( |$)' || return 0
# jira_clauses VERB_RE -> the clauses whose verb matches
jira_clauses() { printf '%s\n' "$flat" | grep -E "^jira ($1)( |\$)"; }
# is_key WORD -> rc 0 when WORD is exactly a literal ticket key
is_key() { printf '%s\n' "$1" | grep -qxE "$KEY_RE"; }

# -- 1. ticket state: jira transition, jira set KEY status|resolution. A subagent is denied before
#       any lookup; a state change whose key is not a literal PROJ-123 word is denied.
n_state=0; state_unchecked=false; state_keys=""
while IFS= read -r cl; do
  [ -n "$cl" ] || continue
  read -r _ jv jk jf _ <<<"$cl"
  if [ "$jv" = set ]; then
    case "$(printf '%s' "${jf:-}" | tr '[:upper:]' '[:lower:]')" in status|resolution) ;; *) continue ;; esac
  fi
  n_state=$((n_state+1))
  if is_key "${jk:-}"; then state_keys="$state_keys $jk"; else state_unchecked=true; fi
done <<EOF
$(jira_clauses 'transition|set')
EOF
is_state=false; [ "$n_state" -gt 0 ] && is_state=true
if $is_state && [ "$IN_SUBAGENT" = true ]; then
  human_decision "jira transition or set status/resolution changes ticket state, a human decision; ask the user instead"
fi
$state_unchecked && deny "jira state change without an identifiable literal ticket key (\$VAR, xargs, a path-like or quoted word, or none) cannot be checked — type the key literally (e.g. ${HARNESS_TICKET_EXAMPLE:-PROJ-123}), or ask the user to transition it"

# -- 2. raw issuelinks writes are not governed -> deny, point at the governed commands
printf '%s\n' "$flat" | grep -qE '^jira set [^ ]+ issuelinks( |$)' && deny "issuelinks field rewrite — use 'jira link FROM TYPE TO' (governed)"
printf '%s\n' "$flat" | grep -qE -- "--field[= ]+issuelinks=" && deny "issuelinks in jira create — use --link TYPE:KEY (governed)"

# -- 3. jira link A TYPE B: two distinct literal keys, allowed type, both agent-labelled
while IFS= read -r cl; do
  [ -n "$cl" ] || continue
  a=$(printf '%s' "$cl" | awk '{print $3}'); b=$(printf '%s' "$cl" | awk 'NF>=5 {print $NF}')
  { is_key "$a" && is_key "$b" && [ "$a" != "$b" ]; } \
    || deny "jira link needs exactly two distinct literal ticket keys (no \$VARS) — use 'jira link FROM TYPE TO' with literal keys instead"
  ltype=$(printf '%s' "$cl" | awk '{s=""; for (i=4; i<NF; i++) s = s (s=="" ? "" : " ") $i; print s}' | tr '[:upper:]' '[:lower:]')
  printf '%s' "$ltype" | grep -qE "$LINK_TYPES_RE" || deny "jira link type '$ltype' not permitted (allowed: $LINK_TYPES_RE) — use one of the allowed types instead"
  for k in $a $b; do
    lb=$(fetch_labels "$k") || { defer "jira link — could not verify labels on $k; check 'jira whoami', or ask the user"; continue; }
    labels_have_write "$lb" || deny "linking to a human ticket is not permitted ($k has no agent-* label) — ask the user to link it, or label it first (jira label $k add $GOV_LABEL)"
  done
done <<EOF
$(jira_clauses link)
EOF

# -- 4. jira create: every agent-created ticket carries a provenance label: agent-drafted
#       (create-ticket) or agent-created (work-ticket sub-tickets), counted per create so a batch
#       cannot smuggle an unlabelled one; --link targets must be literal agent-labelled keys
if jira_clauses create >/dev/null; then
  if jira_clauses create | grep -qE -- '--link\b'; then
    lblflag=$(jira_clauses create | grep -oE -- "--field[= ]+labels=[^ ]*" | head -1)
    { printf '%s' "$lblflag" | grep -q "$CREATED_LABEL" && printf '%s' "$lblflag" | grep -q "$GOV_LABEL"; } \
      || deny "jira create --link without labels $CREATED_LABEL + $GOV_LABEL would create an unlabelled linked ticket — pass --field labels=$CREATED_LABEL,$GOV_LABEL instead"
    n_link=$(jira_clauses create | grep -oE -- '--link\b' | wc -l)
    lkeys=$(jira_clauses create | grep -oE -- "--link[= ]+[^:]+:${KEY_RE}( |\$)" | grep -oE "${KEY_RE} ?\$" | tr -d ' ' | sort -u)
    [ "$(jira_clauses create | grep -oE -- "--link[= ]+[^:]+:${KEY_RE}( |\$)" | wc -l)" -ge "$n_link" ] \
      || deny "jira create --link needs a literal target key — use --link TYPE:PROJ-123 instead"
    for k in $lkeys; do
      lb=$(fetch_labels "$k") || { defer "jira create --link — could not verify labels on $k; check 'jira whoami', or ask the user"; continue; }
      labels_have_write "$lb" || deny "linking to a human ticket is not permitted ($k lacks $GOV_LABEL) — ask the user to link it, or label it first (jira label $k add $GOV_LABEL)"
    done
  fi
  jira_clauses create | while IFS= read -r cl; do
    [ "$(printf '%s\n' "$cl" | grep -oE -- "--field[= ]+labels=" | wc -l)" -le 1 ] || exit 1
  done || deny "jira create with more than one --field labels — the last one wins in Jira, so pass a single --field labels='[\"${DRAFTED_LABEL}\"]' instead"
  n_create=$(jira_clauses create | wc -l)
  n_prov=$(jira_clauses create | grep -cE -- "--field[= ]+labels=\[[^] ]*\"(${DRAFTED_LABEL}|${CREATED_LABEL})\"")
  [ "$n_prov" -ge "$n_create" ] \
    || deny "jira create without a provenance label — pass --field labels='[\"${DRAFTED_LABEL}\"]' (create-ticket) or '[\"${CREATED_LABEL}\",\"${GOV_LABEL}\"]' (work-ticket sub-tickets)"
fi

# -- 5. keyed writes (set, upload, comment, transition, label) on existing tickets. `jira label KEY
#       add agent-*` with a literal key is free; every other keyed clause goes through the gate.
keys=""; unchecked=false
while IFS= read -r cl; do
  [ -n "$cl" ] || continue
  read -r _ jv jk act lbls <<<"$cl"
  if [ "$jv" = label ] && [ "${act:-}" = add ] && is_key "${jk:-}" && [ -n "${lbls:-}" ] \
     && ! printf '%s\n' "$lbls" | tr ' ,' '\n\n' | grep -v '^$' | grep -vqE "$AGENT_LABEL_RE"; then
    continue   # governance labelling (agent-* labels only)
  fi
  if is_key "${jk:-}"; then keys="$keys $jk"; else unchecked=true; fi
done <<EOF
$(jira_clauses 'set|upload|comment|transition|label')
EOF
$unchecked && { defer "jira write (could not identify the ticket key) — use a literal key like PROJ-123 instead"; return 0; }
# shellcheck disable=SC2086  # word-split the key list on purpose
keys=$(printf '%s\n' $keys | sort -u | tr '\n' ' ' | sed 's/^ *//; s/ *$//')
# allows wait for every later section (pending_allow): a deny there still wins
[ -n "$keys" ] || { pending_allow="jira link / create / labelling — agent-labelled targets and provenance labels checked"; return 0; }

all_gov=true; state_human=false
for k in $keys; do
  lb=$(fetch_labels "$k") || {
    $is_state && deny "jira state change on $k — could not verify labels on $k (jira get failed: timeout/auth/403); check 'jira whoami', type a literal key and retry, or ask the user to transition it"
    defer "jira write to $k — could not verify its labels (jira get failed: timeout/auth/403); check 'jira whoami', or ask the user"
    return 0
  }
  if ! labels_have_write "$lb"; then
    all_gov=false
    case " $state_keys " in *" $k "*) state_human=true ;; esac
  fi
done

if $all_gov; then
  if [ "$LABELED_DECISION" = "allow" ]; then pending_allow="jira write to $keys — ticket(s) carry an agent-* label"; return 0; fi
  defer "jira write to $keys (ticket(s) carry an agent-* label; WORK_TICKET_LABELED_DECISION=ask here, so ask the user to confirm)"
  return 0
fi
if $state_human; then
  human_decision_defer "jira state change on $keys — the state of a human-written ticket is a human decision; run it only on the user's explicit request (they confirm it), or ask the user to transition it in Jira instead (jira set status|resolution: use jira transition)"
  return 0
fi
defer "ticket(s) $keys not all agent-labelled — writes to human tickets need an explicit user request; ask the user, or label first (jira label KEY add $GOV_LABEL)"
