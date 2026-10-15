#!/usr/bin/env python3
"""Fixture-routed stand-in for gh, glab and jira (ticket-workflow skill suites). No network.

    stub.py gh|glab|jira ARGS...       (reached through bin/<tool> on PATH)

Routes come from two layers, looked up in this order:
  1. the scenario: section "<tool>" of $TW_FIXTURE (one JSON file per scenario, optional)
  2. the base:     $TW_FIXTURES/_<tool>.json (the suite's defaults)
Each layer maps a route key to a response. The key is the argument list with the shape
modifiers dropped (`--json V`, `--jq V`, `--limit V`, `-f V`), e.g. `api user`,
`repo view owner/repo`, `pr list -R owner/repo --state all --search 7`. A layer is tried for
an exact key first, then for glob keys (fnmatch, longest first; `*` is the catch-all). When
both layers hold an exact object response, the scenario is deep-merged over the base.

A response is printed as JSON, a string is printed verbatim, and an object whose keys are
a subset of {out, rc, err} holding rc or err is the raw form: `out` (string or JSON) on
stdout, `err` on stderr, exit `rc`. A scenario value of null removes the route.
`--json a,b` filters the response to those fields (a missing field is an error, like gh) and
`--jq EXPR` runs the real jq (-r -c, like gh) over it.

Every call is appended to $STUB_LOG as `<tool> <args>`. A call with no route prints
`stub: no route for ...`, is appended to $STUB_MISS and exits 1, so the runner fails the case.
"""
import copy
import fnmatch
import json
import os
import subprocess
import sys

DROP = {"--json", "--jq", "--limit", "-f"}
RAW = {"out", "rc", "err"}


def merge(base, delta):
    out = copy.deepcopy(base)
    for k, v in delta.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def is_raw(v):
    return isinstance(v, dict) and v and set(v) <= RAW and ("rc" in v or "err" in v)


def layers(tool):
    out = []
    path = os.environ.get("TW_FIXTURE", "")
    if path and os.path.isfile(path):
        with open(path) as fh:
            out.append((json.load(fh).get(tool) or {}))
    else:
        out.append({})
    base = os.path.join(os.environ.get("TW_FIXTURES", ""), "_%s.json" % tool)
    if os.path.isfile(base):
        with open(base) as fh:
            out.append(json.load(fh))
    else:
        out.append({})
    return out


def route_key(args):
    key, i = [], 0
    while i < len(args):
        if args[i] in DROP:
            i += 2
            continue
        key.append(args[i])
        i += 1
    return " ".join(key)


def lookup(tool, key):
    scen, base = layers(tool)
    if key in scen:
        v = scen[key]
        if isinstance(v, dict) and not is_raw(v) and isinstance(base.get(key), dict) and not is_raw(base[key]):
            return True, merge(base[key], v)
        return v is not None, v
    for layer in (scen, base):
        if key in layer:
            return layer[key] is not None, layer[key]
        for pat in sorted((k for k in layer if any(c in k for c in "*?[")), key=lambda k: (-len(k), k)):
            if fnmatch.fnmatchcase(key, pat):
                return layer[pat] is not None, layer[pat]
    return False, None


def flag(args, name):
    return args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else None


def fields(value, wanted):
    def one(obj):
        missing = [f for f in wanted if f not in obj]
        if missing:
            fail('Unknown JSON field: "%s"' % missing[0])
        return {f: obj[f] for f in wanted}
    if isinstance(value, list):
        return [one(o) for o in value]
    if isinstance(value, dict):
        return one(value)
    return value


def fail(msg, rc=1):
    sys.stderr.write(msg + "\n")
    sys.exit(rc)


def main():
    tool, args = sys.argv[1], sys.argv[2:]
    log = os.environ.get("STUB_LOG")
    if log:
        with open(log, "a") as fh:
            fh.write("%s %s\n" % (tool, " ".join(args)))
    key = route_key(args)
    found, value = lookup(tool, key)
    if not found:
        miss = os.environ.get("STUB_MISS")
        if miss:
            with open(miss, "a") as fh:
                fh.write("%s %s\n" % (tool, key))
        fail("stub: no route for %s %s" % (tool, key))
    if is_raw(value):
        out = value.get("out", "")
        if out is not None:
            sys.stdout.write(out if isinstance(out, str) else json.dumps(out))
        if value.get("err"):
            sys.stderr.write(value["err"] + "\n")
        sys.exit(int(value.get("rc", 0)))
    if isinstance(value, str):
        sys.stdout.write(value)
        sys.exit(0)
    want = flag(args, "--json")
    if want:
        value = fields(value, [f for f in want.split(",") if f])
    text = json.dumps(value)
    jq = flag(args, "--jq")
    if jq:
        p = subprocess.run(["jq", "-r", "-c", jq], input=text, capture_output=True, text=True)
        sys.stdout.write(p.stdout)
        if p.returncode:
            fail(p.stderr.strip() or "jq failed", p.returncode)
        sys.exit(0)
    sys.stdout.write(text + "\n")
    sys.exit(0)


if __name__ == "__main__":
    main()
