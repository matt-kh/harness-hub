#!/usr/bin/env python3
"""Fixture-driven stub for gh and glab (repoboot tests). No network, no real CLI.

    stub.py gh|glab ARGS...

$RB_FIXTURE (JSON) answers GETs: {"get": {"<path>": <json> | {"__status": 404}}, "labels": [...],
"writes": {"<METHOD> <path>" | "repo create" | "label create": {"rc": 1, "err": "... (HTTP 403)"}}}.
Every invocation is appended to $STUB_LOG as `<tool> <args>`; an --input file's JSON follows it.
"""
import json
import os
import sys


def out(obj=None, text=None, rc=0, err=""):
    if text is not None:
        sys.stdout.write(text)
    elif obj is not None:
        sys.stdout.write(json.dumps(obj))
    if err:
        sys.stderr.write(err + "\n")
    sys.exit(rc)


def main():
    tool, args = sys.argv[1], sys.argv[2:]
    data = {}
    if os.environ.get("RB_FIXTURE") and os.path.exists(os.environ["RB_FIXTURE"]):
        with open(os.environ["RB_FIXTURE"]) as fh:
            data = json.load(fh).get(tool) or {}
    log = os.environ.get("STUB_LOG")
    line = "%s %s" % (tool, " ".join(args))
    if "--input" in args:
        with open(args[args.index("--input") + 1]) as fh:
            body = json.load(fh)
        line = line.replace(args[args.index("--input") + 1], "BODY") + "\n  BODY " + json.dumps(body, sort_keys=True)
    if log:
        with open(log, "a") as fh:
            fh.write(line + "\n")
    writes = data.get("writes") or {}
    if args[:2] == ["auth", "status"]:
        out(text="Logged in\n")
    if args[:2] in (["repo", "create"], ["label", "create"]):
        w = writes.get(" ".join(args[:2])) or {}
        out(text=w.get("out", ""), rc=w.get("rc", 0), err=w.get("err", ""))
    if args[:2] == ["label", "list"]:
        out([{"name": n} for n in data.get("labels") or []])
    if args and args[0] == "api":
        rest = [a for a in args[1:]]
        if "--hostname" in rest:
            i = rest.index("--hostname")
            del rest[i:i + 2]
        method = "GET"
        if "-X" in rest:
            i = rest.index("-X")
            method = rest[i + 1]
            del rest[i:i + 2]
        path = rest[0]
        if method != "GET":
            w = writes.get("%s %s" % (method, path)) or {}
            out(text=w.get("out", "{}"), rc=w.get("rc", 0), err=w.get("err", ""))
        val = (data.get("get") or {}).get(path, {"__status": 404})
        if isinstance(val, dict) and "__status" in val:
            out(rc=1, err="HTTP %d: stub (%s)" % (val["__status"], path))
        out(val)
    out(rc=1, err="stub: no route for %s %s" % (tool, " ".join(args)))


if __name__ == "__main__":
    main()
