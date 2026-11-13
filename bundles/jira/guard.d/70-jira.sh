# shellcheck shell=bash

# Section 70 (bundle jira): Jira write governance.
# rule: jira set KEY issuelinks | create --field issuelinks= -> deny : use the governed link commands
# rule: jira link A TYPE B (both agent-labelled, type in HARNESS_JIRA_LINK_TYPES_RE) -> allow : otherwise deny
# rule: jira create without a provenance label (agent-drafted|agent-created) -> deny : every agent-created ticket is labelled; use labels agent-drafted (or agent-created) instead
# rule: jira create with a provenance label -> allow : creates are promptless
# rule: jira label KEY add agent-* -> allow : governance labelling is free
# rule: jira set|comment|upload|label KEY on agent-labelled tickets -> allow : promptless (so is a state change, on the main thread)
# rule: jira transition KEY, jira set KEY status|resolution on a human ticket -> ask : ticket state is a human decision; run it only on the user's explicit request (they confirm it), or ask the user to transition it in Jira instead
# rule: jira transition, jira set KEY status|resolution from a subagent -> deny : a subagent never changes ticket state, on human and agent-labelled tickets alike; hand the command back to the main thread
# rule: jira state change without a literal key ($VAR, xargs, LBL-1/../X, none) or whose labels cannot be read -> deny : the ticket cannot be checked; type the key literally (e.g. PROJ-123), or ask the user to transition it
# rule: jira write whose key is not a literal PROJ-123 word -> ask : the ticket cannot be checked; use a literal key instead
# rule: jira hidden from the guard (quoted/escaped or case-changed command words, a $VAR/$(…) subcommand, jira fed by xargs, alias, a variable or $(which jira)) -> ask : the subcommand cannot be checked; write it literally and unquoted instead (a subagent is denied unless it is a known non-state write)
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
#   H <verb>     a jira call the guard cannot read: quoted/escaped or case-changed command
#                words, a $VAR/$(…) verb ($), no verb (xargs jira, -), a NAME=jira assignment or
#                alias (-), $(which jira) as the command, jira code in python/perl/node -c|-e
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
# cheap prefilter: quotes and backslashes removed (j\ira, j""ira); $'…' could spell anything
printf '%s' "$flat_dq" | grep -qi 'jira' || printf '%s' "$flat" | grep -qF "\$'" || return 0
# shellcheck disable=SC2168  # sections are wrapped in a function by build.sh
local jscan flat cl jv jk jf act lbls a b ltype
JIRA_SCAN_PY=""
read -r -d '' JIRA_SCAN_PY <<'PY' || true
import re, sys
WRITES = ("set", "create", "transition", "upload", "comment", "label", "link")
WRAP = {"exec", "command", "builtin", "nohup", "time", "then", "do", "else", "elif", "if", "while",
        "until", "!", "{", "sudo", "doas", "nice", "stdbuf", "timeout", "xargs", "watch", "setsid",
        "unbuffer", "caffeinate", "chronic", "ionice", "taskset", "env", "noglob", "nocorrect", "parallel"}
WRAP_ARG = {"sudo": "ugCDhprRTU", "doas": "uC", "nice": "n", "xargs": "IidEeaLlnPs", "ionice": "cnp",
            "stdbuf": "ioe", "env": "uCS", "watch": "nd", "timeout": "sk", "time": "fo"}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "mksh", "fish", "busybox"}
INTERP_RE = re.compile(r"^(python[0-9.]*|perl|node|ruby|php|osascript|pwsh)$")
DATA = {"cat"}
JIRA_TEXT_RE = re.compile(r"\bjira(\.py)?\W+(" + "|".join(WRITES) + r")\b", re.I)
ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
ALIAS_JIRA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*=(.*/)?jira(\.py)?$", re.I)
KEYED = ("set", "upload", "comment", "transition", "label")
out = []


class W(object):
    def __init__(self, v, q, d):
        self.v, self.q, self.d = v, q, d


def emit(kind, text):
    line = "%s %s" % (kind, text)
    if line not in out:
        out.append(line)


def base(v):
    return v.rsplit("/", 1)[-1]


def jiraish(v):
    return base(v).lower() in ("jira", "jira.py")


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
    """s[i] follows an opening '$(' (close ')') or '${' (close '}'): index of the matching close"""
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
        elif c == close or (close == ")" and c == ")"):
            if depth == 0:
                return i
            depth -= 1
        i += 1
    return n


def subs(text, depth):
    """scan the command substitutions of text that undergoes expansion (an unquoted heredoc body)"""
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if text.startswith("$(", i):
            j = match_close(text, i + 2, ")")
            scan(text[i + 2:j], depth + 1)
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
    """split s into clauses: [(words, heredocs, sep)]; command substitutions are scanned on the way"""
    clauses, st = [], {"words": [], "docs": [], "cur": None, "drop": False}
    pend = []
    n, i = len(s), 0

    def start():
        if st["cur"] is None:
            st["cur"] = [[], False, False]

    def endw():
        cur = st["cur"]
        if cur is not None:
            if st["drop"]:
                st["drop"] = False
            else:
                st["words"].append(W("".join(cur[0]), cur[1], cur[2]))
            st["cur"] = None

    def endc(sep):
        endw()
        if st["words"] or st["docs"]:
            clauses.append((st["words"], st["docs"], sep))
        st["words"], st["docs"] = [], []

    while i < n:
        c = s[i]
        if c in " \t":
            endw()
            i += 1
            continue
        if c == "\n":
            docs = st["docs"]
            endc("\n")
            i += 1
            for d, strip, quoted, dl in pend:
                body, i = skip_body(s, i, d, strip)
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
                if s.startswith("$(", i):
                    j = match_close(s, i + 2, ")")
                    scan(s[i + 2:j], depth + 1)
                    cur[0].append(s[i:j + 1])
                    cur[2] = True
                    i = j + 1
                    continue
                if s.startswith("${", i):
                    j = match_close(s, i + 2, "}")
                    cur[0].append(s[i:j + 1])
                    cur[2] = True
                    i = j + 1
                    continue
                if ch == "`":
                    j = s.find("`", i + 1)
                    j = n if j < 0 else j
                    scan(s[i + 1:j], depth + 1)
                    cur[0].append(s[i:j + 1])
                    cur[2] = True
                    i = j + 1
                    continue
                if ch == "$":
                    cur[2] = True
                cur[0].append(ch)
                i += 1
            i += 1
            continue
        if s.startswith("$(", i):
            start()
            j = match_close(s, i + 2, ")")
            scan(s[i + 2:j], depth + 1)
            st["cur"][0].append(s[i:j + 1])
            st["cur"][2] = True
            i = j + 1
            continue
        if s.startswith("${", i):
            start()
            j = match_close(s, i + 2, "}")
            st["cur"][0].append(s[i:j + 1])
            st["cur"][2] = True
            i = j + 1
            continue
        if c == "$":
            start()
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
            st["drop"] = True
            continue
        if c in ";&|()":
            sep = c
            endc(sep)
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
    prev = None
    for words, docs, sep in parse(s, depth):
        clause(words, docs, sep, prev, depth)
        prev = (words, docs, sep)


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


def clause(words, docs, sep, prev, depth):
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
                    clause(words[k + 1:end], [], "", None, depth)
            return
        break
    if i >= len(words):
        for body, quoted in docs:
            scan(body, depth + 1)
        return
    cw = words[i]
    b = base(cw.v)
    rest = words[i + 1:]
    if INTERP_RE.match(b):
        k = 0
        while k < len(rest) and rest[k].v.startswith("-") and rest[k].v not in ("-c", "-e", "-E", "-m"):
            k += 1
        if k < len(rest) and rest[k].v in ("-c", "-e", "-E"):
            code = rest[k + 1].v if k + 1 < len(rest) else ""
            m = JIRA_TEXT_RE.search(code)
            if m:
                emit("H", m.group(2).lower())
            return
        if k < len(rest) and rest[k].v == "-m":
            return
        if k < len(rest) and jiraish(rest[k].v):
            cw, b, rest = rest[k], base(rest[k].v), rest[k + 1:]
        else:
            fed = docs_text(docs) + (piped(prev) if prev and prev[2] == "|" else "")
            m = JIRA_TEXT_RE.search(fed)
            if m:
                emit("H", m.group(2).lower())
            return
    if b in SHELLS:
        for k, w in enumerate(rest):
            if re.match(r"^-[A-Za-z]*c[A-Za-z]*$", w.v) and not w.v.startswith("--"):
                if k + 1 < len(rest):
                    scan(rest[k + 1].v, depth + 1)
                return
        if prev and prev[2] == "|":
            scan(piped(prev), depth + 1)
        for body, quoted in docs:
            scan(body, depth + 1)
        return
    if b == "eval":
        scan(" ".join(w.v for w in rest), depth + 1)
        return
    if b.lower() in ("jira", "jira.py"):
        jira_clause(cw, b, rest)
        return
    if cw.d and cw.v[:1] in ("$", "`"):
        if re.search("jira", cw.v, re.I) or cw.v.startswith("$'"):
            emit("H", rest[0].v.lower() if rest and not rest[0].d else "-")
        return
    for body, quoted in docs:
        if base(cw.v) in DATA and sep != "|":
            if not quoted:
                subs(body, depth)
        else:
            scan(body, depth + 1)
    for k, w in enumerate(rest):
        if jiraish(w.v) and k + 1 < len(rest) and rest[k + 1].v.lower() in WRITES:
            emit("H", rest[k + 1].v.lower())


def docs_text(docs):
    return "\n".join(b for b, _q in docs)


def piped(prev):
    words, docs, _sep = prev
    return " ".join(w.v for w in words[1:]) + "\n" + docs_text(docs)


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
        out.append("H -")
    sys.stdout.write("".join(l + "\n" for l in out))
PY
jscan=$(hn_timeout 5 python3 -c "$JIRA_SCAN_PY" "$cmd" 2>/dev/null) || jscan="H -"   # scanner failure: fail closed
# -- 0. calls the guard cannot read: a known read passes, a known non-state write asks, anything
#       else (transition, set, $VAR, no verb, unknown) is a human decision (a subagent is denied)
while read -r jk jv; do
  [ "$jk" = H ] || continue
  case "$jv" in
    get|links|search|fields|sprints|versions|transitions|whoami|attachments|download|api) ;;
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
    lb=$(fetch_labels "$k") || ask "jira link — could not verify labels on $k; check 'jira whoami', or ask the user"
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
      lb=$(fetch_labels "$k") || ask "jira create --link — could not verify labels on $k; check 'jira whoami', or ask the user"
      labels_have_write "$lb" || deny "linking to a human ticket is not permitted ($k lacks $GOV_LABEL) — ask the user to link it, or label it first (jira label $k add $GOV_LABEL)"
    done
  fi
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
$unchecked && ask "jira write (could not identify the ticket key) — use a literal key like PROJ-123 instead"
# shellcheck disable=SC2086  # word-split the key list on purpose
keys=$(printf '%s\n' $keys | sort -u | tr '\n' ' ' | sed 's/^ *//; s/ *$//')
[ -n "$keys" ] || allow "jira link / create / labelling — agent-labelled targets and provenance labels checked"

all_gov=true; state_human=false
for k in $keys; do
  lb=$(fetch_labels "$k") || {
    $is_state && deny "jira state change on $k — could not verify labels; ticket state is human-only, ask the user to transition it instead"
    ask "jira write to $k — could not verify its labels (jira get failed: timeout/auth/403); check 'jira whoami', or ask the user"
  }
  if ! labels_have_write "$lb"; then
    all_gov=false
    case " $state_keys " in *" $k "*) state_human=true ;; esac
  fi
done

if $all_gov; then
  [ "$LABELED_DECISION" = "allow" ] && allow "jira write to $keys — ticket(s) carry an agent-* label"
  ask "jira write to $keys (ticket(s) carry an agent-* label; WORK_TICKET_LABELED_DECISION=ask here, so ask the user to confirm)"
fi
if $state_human; then
  human_decision_defer "jira state change on $keys — the state of a human-written ticket is a human decision; run it only on the user's explicit request (they confirm it), or ask the user to transition it in Jira instead (jira set status|resolution: use jira transition)"
  return 0
fi
ask "ticket(s) $keys not all agent-labelled — writes to human tickets need an explicit user request; ask the user, or label first (jira label KEY add $GOV_LABEL)"
