"""Principle 1 (lightweight): the engine imports only the standard library and its _vendor copy,
and the shell scanner behind the `dependencies` lint rule finds what scripts invoke."""
from __future__ import annotations

import ast
import os
import sys
import unittest

from helpers import REPO  # noqa: E402

from harness import shell_scan as S

ENGINE = os.path.join(REPO, "lib", "harness")

# python 3.9 has no sys.stdlib_module_names: the stdlib modules an engine may reasonably use
FALLBACK_STDLIB = set("""
__future__ abc argparse ast base64 binascii bisect calendar codecs collections concurrent configparser
contextlib copy csv dataclasses datetime decimal difflib email enum errno fcntl filecmp fnmatch
fractions functools getpass glob gzip hashlib heapq hmac html http importlib inspect io ipaddress
itertools json keyword locale logging lzma math mimetypes operator os pathlib pickle platform
plistlib posixpath pprint pwd queue random re secrets select selectors shlex shutil signal socket
ssl stat string struct subprocess sys sysconfig tarfile tempfile textwrap threading time timeit
tokenize tomllib traceback types typing unicodedata unittest urllib uuid warnings weakref zipfile
zlib
""".split())


def stdlib_names():
    names = getattr(sys, "stdlib_module_names", None)
    return set(names) if names else FALLBACK_STDLIB


def engine_imports():
    """(file, line, top-level module) for every absolute import under lib/harness (not _vendor)."""
    out = []
    for dirpath, dirnames, files in os.walk(ENGINE):
        dirnames[:] = sorted(d for d in dirnames if d not in ("_vendor", "__pycache__"))
        for fn in sorted(files):
            if not fn.endswith(".py"):
                continue
            path = os.path.join(dirpath, fn)
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read(), path)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        out.append((path, node.lineno, a.name.split(".")[0]))
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    out.append((path, node.lineno, node.module.split(".")[0]))
    return out


class EngineImportsTest(unittest.TestCase):
    def test_stdlib_or_vendor_only(self):
        std = stdlib_names()
        bad = ["%s:%d imports %s" % (os.path.relpath(p, REPO), ln, mod)
               for p, ln, mod in engine_imports() if mod not in std and mod != "harness"]
        self.assertEqual(bad, [], "lib/harness must stay stdlib-only (vendor into lib/harness/_vendor instead)")

    def test_scan_sees_imports(self):
        mods = {m for _p, _l, m in engine_imports()}
        self.assertIn("json", mods)
        self.assertIn("subprocess", mods)

    def test_fallback_covers_what_the_engine_uses(self):
        # the 3.9 path must not reject an import that 3.10+ accepts
        used = {m for _p, _l, m in engine_imports() if m != "harness"}
        self.assertEqual(sorted(used - FALLBACK_STDLIB), [], "extend FALLBACK_STDLIB")


class ShellScanTest(unittest.TestCase):
    SCRIPT = r"""#!/usr/bin/env bash
x=$(foo | bar)
if command -v baz >/dev/null; then hn_timeout 5 qux --a; fi
cat <<EOF
notacmd here; alsonot
EOF
y="$(zap)" ; [[ a && b ]] && ok1
case $x in a|b) ok2 ;; HEAD|GET) ok3 ;; *) ok4 ;; esac
echo 'no; nope' # comment; nope2
(( i > 0 )) && ok5
foo \
  notcmd && ok6
myfn() { inner; }
"$var" arg; ${py} -c 'x'; ./local.sh; VAR=1 env other
"""

    def test_commands(self):
        words = [w for _l, w in S.commands(self.SCRIPT)]
        for w in ("foo", "bar", "baz", "qux", "cat", "zap", "ok1", "ok2", "ok3", "ok4", "ok5", "ok6",
                  "inner", "env", "other"):
            self.assertIn(w, words)
        for w in ("notacmd", "alsonot", "nope", "nope2", "HEAD", "GET", "notcmd", "a", "b", "i",
                  "var", "py", "hn_timeout", "command", "echo", "if", "then"):
            self.assertNotIn(w, words)

    def test_line_numbers(self):
        lines = {}
        for ln, w in S.commands(self.SCRIPT):
            lines.setdefault(w, ln)
        self.assertEqual(lines["foo"], 2)
        self.assertEqual(lines["zap"], 7)
        self.assertEqual(lines["ok6"], 12)

    def test_function_names(self):
        self.assertEqual(S.function_names("a() { :; }\nfunction b {\n:\n}\n  c () {\n"), {"a", "b", "c"})

    def test_repo_has_no_unlisted_binaries(self):
        from harness import lint
        from harness.hub import Hub

        hub = Hub(home=REPO, require_config=False, select=False, config_path=os.path.join(REPO, "tests", "fixtures", "harness.ci.toml"))
        rep = lint.Report()
        lint.lint_dependencies(hub, rep)
        self.assertEqual(rep.warnings, [])


if __name__ == "__main__":
    unittest.main()
