"""Shell snippets in skill, agent and rule Markdown run in the user's login shell.

zsh, a common login shell, does not word-split unquoted parameter expansions, so a
multi-word ``${VAR:+--flag "$VAR"}`` arrives as one argument (``--flag value``) and the
command fails there while it works in bash. CONTRIBUTING "bash 3.2 rules" states the rule;
this test is its sensor.
"""
import glob
import os
import re
import unittest

from helpers import REPO

_START = re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*:?\+")


def unquoted_space_alternates(text):
    """Yield (line, snippet) for each ${VAR:+alt} whose alt has whitespace outside quotes."""
    for m in _START.finditer(text):
        i, depth, quote, bad = m.end(), 1, None, False
        while i < len(text) and depth:
            c = text[i]
            if quote:
                if c == quote:
                    quote = None
            elif c in "\"'":
                quote = c
            elif text.startswith("${", i):
                depth += 1
                i += 1
            elif c == "}":
                depth -= 1
            elif c in " \t":
                bad = True
            elif c == "\n":
                break
            i += 1
        if bad and depth == 0:
            yield text.count("\n", 0, m.start()) + 1, text[m.start():i]


def agent_markdown():
    pats = ("bundles/*/skills/**/*.md", "bundles/*/agents/*.md", "bundles/*/rules/*.md")
    for pat in pats:
        for path in sorted(glob.glob(os.path.join(REPO, pat), recursive=True)):
            yield path


class SkillSnippetTest(unittest.TestCase):
    def test_detector(self):
        bad = 'x ${cfg:+--config "$cfg"} y ${M:+-m "$M"}'
        self.assertEqual([s for _, s in unquoted_space_alternates(bad)],
                         ['${cfg:+--config "$cfg"}', '${M:+-m "$M"}'])
        good = ('${DRAFT:+--draft} ${M:+"--milestone=$M"} ${arr[@]+"${arr[@]}"} '
                '${cfg:-${HARNESS_CONFIG:-}} ${X:+"a b"}')
        self.assertEqual(list(unquoted_space_alternates(good)), [])

    def test_skill_snippets(self):
        hits = []
        for path in agent_markdown():
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            for line, snippet in unquoted_space_alternates(text):
                hits.append("%s:%d: %s" % (os.path.relpath(path, REPO), line, snippet))
        self.assertEqual(hits, [], "multi-word ${VAR:+...} alternates break in zsh; write one quoted "
                         "word (${M:+\"--milestone=$M\"}) or pass the value via the environment "
                         "(CONTRIBUTING, bash 3.2 rules):\n" + "\n".join(hits))


if __name__ == "__main__":
    unittest.main()
