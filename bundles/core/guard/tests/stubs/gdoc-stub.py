#!/usr/bin/env python3
"""Stub for guard-bash hook tests: `meta ID` prints canned Drive metadata; no network.
AGT*  -> properties.agent_provenance = agent-created
MRK*  -> properties.agent_provenance = agent-worked
HUM*  -> properties = {"owner_team": "hr"} (no agent marker)
ERR*  -> exit 2 (auth/timeout/no access)   other -> properties = {}"""
import json, sys
if len(sys.argv) < 3 or sys.argv[1] != "meta":
    sys.exit(1)
fid = sys.argv[2]
if fid.startswith("ERR"):
    sys.exit(2)
props = {
    "AGT": {"agent_provenance": "agent-created", "agent_tool": "claude-code"},
    "MRK": {"agent_provenance": "agent-worked", "agent_tool": "claude-code"},
    "HUM": {"owner_team": "hr"},
}.get(fid[:3], {})
print(json.dumps({"id": fid, "name": "stub",
                  "mimeType": "application/vnd.google-apps.document",
                  "properties": props}))
