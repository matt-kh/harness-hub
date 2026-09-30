#!/usr/bin/env python3
"""Stub for guard-bash hook tests: `get KEY` prints canned labels; no network.
LBL-*  -> agent-worked            CRE-* -> agent-created + agent-worked
DRF-*  -> agent-drafted only      HUM-* -> no labels
ERR-*  -> exit 2 (unreachable/403)"""
import json, sys
if len(sys.argv) < 3 or sys.argv[1] != "get":
    sys.exit(1)
key = sys.argv[2]
if key.startswith("ERR-"):
    sys.exit(2)
labels = {"LBL": ["agent-worked", "ready"], "CRE": ["agent-created", "agent-worked"],
          "DRF": ["agent-drafted"], "HUM": []}.get(key.split("-")[0], [])
print(json.dumps({"key": key, "labels": labels}))
