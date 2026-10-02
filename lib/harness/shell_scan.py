"""Heuristic scan of the binaries a shell script invokes (lint rule "dependencies", principle 1).

Not a shell parser. The text is first *masked* (quoted strings, ``${...}``, comments,
heredoc bodies and arithmetic become opaque, line numbers are kept), command and process
substitutions become separators, and then the first word of every simple command is
taken: at the start of a line and after ``|``, ``||``, ``&&``, ``;``, ``&``, ``$(``,
backticks, ``<(``, after control keywords (``if then do else elif while until ! { (``),
after wrappers (``exec env nohup sudo xargs time builtin``), the word after
``command -v|-V`` and the command after ``hn_timeout SECS``. Assignments, redirections,
case patterns (``word)``), words containing ``$`` or ``/`` and functions are ignored.

``commands(text)`` returns ``[(line, word)]``; ``function_names(text)`` the functions the
text defines. False positives are expected to be rare and are fixed in the allow-list.
"""
from __future__ import annotations

import re
from typing import List, Set, Tuple

MASK = "\x01"
CONT = "\x03"  # a backslash-newline: whitespace that still counts as a line

BUILTINS = set("""
. : [ [[ ]] ]] alias bg bind break builtin caller cd command compgen complete compopt continue declare
dirs disown echo enable eval exec exit export false fc fg getopts hash help history jobs kill let local
logout mapfile popd printf pushd pwd read readarray readonly return set shift shopt source suspend test
times trap true type typeset ulimit umask unalias unset wait
""".split())
KEYWORDS = set("if then else elif fi case esac for select while until do done in function time coproc".split())
# words after which the next word is again in command position
CMD_NEXT = set("if then else elif do while until ! { ( time exec nohup sudo xargs builtin env".split())
# words after which the rest of the simple command is not a command
NOT_CMD_AFTER = set("for select case function done fi esac }".split())

_FUNC_RE = re.compile(r"^[ \t]*(?:function[ \t]+)?([A-Za-z_][A-Za-z0-9_:.-]*)[ \t]*\(\)", re.M)
_FUNC_KW_RE = re.compile(r"^[ \t]*function[ \t]+([A-Za-z_][A-Za-z0-9_:.-]*)", re.M)
_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.+-]*$")
_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\[[^]]*\])?\+?=")
_REDIR_RE = re.compile(r"^[0-9]*(<<<|<<-?|>>|<>|>\||[<>])")
_TOKEN_RE = re.compile(r"\n|" + CONT + r"|&&|\|\||;;&?|;&|\|&|[;&|]|[^\s;&|" + CONT + r"]+")
_HEREDOC_RE = re.compile(r"<<(-?)[ \t]*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")


def function_names(text: str) -> Set[str]:
    return set(_FUNC_RE.findall(text)) | set(_FUNC_KW_RE.findall(text))


def _word_start(out: List[str]) -> bool:
    if not out:
        return True
    return out[-1] in " \t\n;|&(){}" + CONT


def mask(text: str) -> str:
    """Same length per line; see the module docstring."""
    out: List[str] = []
    stack: List[str] = ["top"]   # top | sub | dq | bt
    depth: List[int] = [0]       # paren depth inside each sub
    pending_heredocs: List[Tuple[str, bool]] = []
    i, n = 0, len(text)

    def keep_nl(ch: str) -> str:
        return ch if ch == "\n" else MASK

    while i < n:
        c = text[i]
        st = stack[-1]
        nxt = text[i + 1] if i + 1 < n else ""
        if st in ("top", "sub", "bt"):
            if c == "\\":
                if nxt == "\n":
                    out.append(" " + CONT)
                else:
                    out.append(MASK + MASK if nxt else MASK)
                i += 2
                continue
            if c == "'":
                j = text.find("'", i + 1)
                j = n if j < 0 else j
                out.append(MASK + "".join(keep_nl(ch) for ch in text[i + 1:j]) + (MASK if j < n else ""))
                i = j + 1
                continue
            if c == '"':
                stack.append("dq")
                out.append(MASK)
                i += 1
                continue
            if c == "#" and _word_start(out):
                j = text.find("\n", i)
                j = n if j < 0 else j
                out.append(" " * (j - i))
                i = j
                continue
            if c == "$" and nxt == "{":
                i = _skip_braces(text, i, out)
                continue
            if c == "$" and nxt == "(" and text[i + 2:i + 3] == "(":
                i = _skip_arith(text, i, out, 3)
                continue
            if c == "(" and nxt == "(" and _word_start(out):
                i = _skip_arith(text, i, out, 2)
                continue
            if (c == "$" or c in "<>") and nxt == "(":
                stack.append("sub")
                depth.append(0)
                out.append(" ;")
                i += 2
                continue
            if c == "`":
                if st == "bt":
                    stack.pop()
                else:
                    stack.append("bt")
                out.append(";")
                i += 1
                continue
            if st == "sub" and c == "(":
                depth[-1] += 1
            if st == "sub" and c == ")":
                if depth[-1] == 0:
                    stack.pop()
                    depth.pop()
                    out.append(";")
                    i += 1
                    continue
                depth[-1] -= 1
            if c == "<" and nxt == "<" and text[i + 2:i + 3] != "<":
                m = _HEREDOC_RE.match(text, i)
                if m:
                    pending_heredocs.append((m.group(3), m.group(1) == "-"))
                    out.append(text[i:m.end()].replace("'", MASK).replace('"', MASK))
                    i = m.end()
                    continue
            if c == "\n" and pending_heredocs:
                out.append("\n")
                i += 1
                while pending_heredocs and i < n:
                    delim, strip_tabs = pending_heredocs.pop(0)
                    while i < n:
                        j = text.find("\n", i)
                        j = n if j < 0 else j
                        line = text[i:j]
                        out.append(MASK * len(line) + ("\n" if j < n else ""))
                        i = j + 1
                        if (line.lstrip("\t") if strip_tabs else line) == delim:
                            break
                continue
            out.append(c)
            i += 1
            continue
        # dq
        if c == "\\":
            out.append(MASK + (keep_nl(nxt) if nxt else ""))
            i += 2
            continue
        if c == '"':
            stack.pop()
            out.append(MASK)
            i += 1
            continue
        if c == "$" and nxt == "{":
            i = _skip_braces(text, i, out)
            continue
        if c == "$" and nxt == "(" and text[i + 2:i + 3] == "(":
            i = _skip_arith(text, i, out, 3)
            continue
        if c == "$" and nxt == "(":
            stack.append("sub")
            depth.append(0)
            out.append(" ;")
            i += 2
            continue
        if c == "`":
            stack.append("bt")
            out.append(";")
            i += 1
            continue
        out.append(keep_nl(c))
        i += 1
    return "".join(out)


def _skip_braces(text: str, i: int, out: List[str]) -> int:
    d, j, n = 0, i + 1, len(text)
    while j < n:
        if text[j] == "{":
            d += 1
        elif text[j] == "}":
            d -= 1
            if d == 0:
                break
        j += 1
    out.append("".join("\n" if ch == "\n" else MASK for ch in text[i:j + 1]))
    return j + 1


def _skip_arith(text: str, i: int, out: List[str], opener: int) -> int:
    d, j, n = 0, i + opener - 2, len(text)
    while j < n:
        if text[j] == "(":
            d += 1
        elif text[j] == ")":
            d -= 1
            if d == 0:
                break
        j += 1
    out.append("".join("\n" if ch == "\n" else MASK for ch in text[i:j + 1]))
    return j + 1


def commands(text: str) -> List[Tuple[int, str]]:
    masked = mask(text)
    found: List[Tuple[int, str]] = []
    line = 1
    cmdpos = True
    skip_next = False      # redirection target / hn_timeout duration
    probe_next = False     # after `command -v`
    after_command = False  # just saw `command`
    in_test = False        # inside [[ ... ]]
    toks = [m.group(0) for m in _TOKEN_RE.finditer(masked)]
    for idx, tok in enumerate(toks):
        if tok == "\n" or tok == CONT:
            line += 1
            if tok == "\n" and not in_test:
                cmdpos, skip_next, probe_next, after_command = True, False, False, False
            continue
        if in_test:
            if tok == "]]":
                in_test = False
                cmdpos = False
            continue
        if tok in ("&&", "||", "|", ";", "&", ";;", ";;&", ";&", "|&"):
            cmdpos, skip_next, probe_next, after_command = True, False, False, False
            continue
        if skip_next:
            skip_next = False
            continue
        if _REDIR_RE.match(tok):
            if _REDIR_RE.sub("", tok, count=1) == "":
                skip_next = True
            continue
        if probe_next:
            probe_next = False
            if _NAME_RE.match(tok):
                found.append((line, tok))
            cmdpos = False
            continue
        if not cmdpos:
            continue
        if after_command:
            after_command = False
            if tok in ("-v", "-V"):
                probe_next = True
                continue
            if tok.startswith("-"):
                continue
        if tok == "[[":
            in_test = True
            continue
        if tok.endswith(")") and tok not in (")",):
            continue  # case pattern; the command follows
        if _case_alternatives(toks, idx):
            continue  # first alternative of `a|b|c)`
        if tok in ("()", ")", "{", "}"):
            cmdpos = tok in ("()", "{")
            continue
        if tok.startswith("(") and len(tok) > 1:
            tok = tok.lstrip("(")
        if _ASSIGN_RE.match(tok) or tok.startswith("-"):
            continue
        if tok == "command":
            after_command = True
            continue
        if tok == "hn_timeout":
            skip_next = True
            continue
        if tok in CMD_NEXT:
            if tok in ("env", "xargs", "nohup", "sudo", "time") and tok not in BUILTINS:
                found.append((line, tok))
            continue
        if tok in NOT_CMD_AFTER:
            cmdpos = False
            continue
        cmdpos = False
        if tok in KEYWORDS or tok in BUILTINS:
            continue
        if not _NAME_RE.match(tok):
            continue
        found.append((line, tok))
    return found


def _case_alternatives(toks: List[str], idx: int) -> bool:
    """``toks[idx]`` starts a ``word|word|...)`` case pattern."""
    j = idx + 1
    while j + 1 < len(toks) and toks[j] == "|":
        nxt = toks[j + 1]
        if nxt.endswith(")"):
            return True
        if nxt in ("\n", CONT) or nxt in ("&&", "||", ";", "&"):
            return False
        j += 2
    return False
