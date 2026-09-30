#!/usr/bin/env python3
"""Read the compiled harness config (build/config.json) from python tools. Stdlib only, 3.9+.

Resolution of the file (first that applies):
  1. $HARNESS_CONFIG_JSON                       (tests point it at a fixture or /dev/null)
  2. ${HARNESS_HOME:-~/harness-hub}/build/config.json
A missing or unreadable file is an empty config: every lookup returns its default.

Callers keep their existing env overrides and consult cfg() only when the env var is unset:
    url = os.environ.get("JIRA_URL") or cfg("jira.url", "")

Skills are rendered into provider homes (~/.claude/skills/<skill>/...) where this file is
not next to them, so each python skill script carries an inlined copy of the block between
the `>>> harness_config` / `<<< harness_config` markers below. bundles/core/tests/run.sh fails
when a copy drifts from this file. Shell scripts use the jq equivalent in `hcfg` (same markers
in sh form, see bundles/core/lib/harness_config.sh).

CLI:  harness_config.py get KEY [DEFAULT]   prints a string value as-is, anything else as JSON
      harness_config.py path                prints the config file path that would be read
"""
import json
import os
import sys

# >>> harness_config
_HARNESS_CFG = None


def _harness_cfg_path():
    return os.environ.get("HARNESS_CONFIG_JSON") or os.path.join(
        os.environ.get("HARNESS_HOME") or os.path.expanduser("~/harness-hub"), "build", "config.json")


def cfg(key, default=None):
    """Dotted lookup in the compiled harness config, e.g. cfg("jira.url", "")."""
    global _HARNESS_CFG
    if _HARNESS_CFG is None:
        try:
            with open(_harness_cfg_path()) as fh:
                _HARNESS_CFG = json.load(fh)
        except (OSError, ValueError):
            _HARNESS_CFG = {}
        if not isinstance(_HARNESS_CFG, dict):
            _HARNESS_CFG = {}
    cur = _HARNESS_CFG
    for part in key.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur
# <<< harness_config


def main(argv):
    if len(argv) >= 2 and argv[1] == "path":
        print(_harness_cfg_path())
        return 0
    if len(argv) not in (3, 4) or argv[1] != "get":
        print(__doc__.strip().splitlines()[-2].strip(), file=sys.stderr)
        return 1
    v = cfg(argv[2], argv[3] if len(argv) == 4 else None)
    if v is None:
        return 1
    print(v if isinstance(v, str) else json.dumps(v, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
