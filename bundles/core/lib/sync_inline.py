#!/usr/bin/env python3
"""Keep inlined helper blocks identical to their canonical source.

Rendered artefacts (the one-file guard hook, standalone skill scripts) cannot import from
bundles/core/lib, so they carry copies of a few helpers between marker lines:

    # >>> NAME            (first line of the block, indentation-free)
    ...
    # <<< NAME

Canonical sources (bundles/core/lib):
    hn_timeout      compat.sh
    harness_config  harness_config.py
    hcfg            harness_config.sh

Usage: sync_inline.py [--check] [ROOT]   ROOT defaults to the bundles/ directory.
  --check  exit 1 and list every drifted copy (CI / bundles/core/tests/run.sh)
  default  rewrite drifted copies in place
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCES = {"hn_timeout": "compat.sh", "harness_config": "harness_config.py", "hcfg": "harness_config.sh"}
BLOCK = r"(?ms)^# >>> {n}\n.*?^# <<< {n}$"


def canonical(name):
    path = os.path.join(HERE, SOURCES[name])
    m = re.search(BLOCK.format(n=re.escape(name)), open(path).read())
    if not m:
        sys.exit(f"sync_inline: no {name} block in {path}")
    return path, m.group(0)


def main(argv):
    check = "--check" in argv
    args = [a for a in argv[1:] if a != "--check"]
    root = args[0] if args else os.path.dirname(os.path.dirname(HERE))
    blocks = {n: canonical(n) for n in SOURCES}
    drift = []
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in (".git", "__pycache__", "golden", "fixtures")]
        for fn in fns:
            p = os.path.join(dp, fn)
            try:
                txt = open(p).read()
            except (UnicodeDecodeError, OSError):
                continue
            new = txt
            for n, (src, blk) in blocks.items():
                if os.path.abspath(p) == os.path.abspath(src):
                    continue
                new = re.sub(BLOCK.format(n=re.escape(n)), lambda _m: blk, new)
            if new != txt:
                drift.append(p)
                if not check:
                    open(p, "w").write(new)
    for p in drift:
        print(("DRIFT " if check else "synced ") + os.path.relpath(p, root))
    return 1 if (check and drift) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
