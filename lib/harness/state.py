"""Per-provider state files (ARCHITECTURE §6-§7).

``<provider home>/.harness-state.json``::

    {"version": 1, "harness_version": "0.1.0", "provider": "claude",
     "applied_at": "2026-09-30T12:00:00Z",
     "files": {"~/.claude/CLAUDE.md": {"sha256": "…", "bundle": "core,github", "mode": "managed-block",
                                        "blocks": {"core rules/10-x.md": "…"}, "created": true}},
     "conflicts": ["~/.claude/settings.json: permissions.allow: …"]}

Provider-independent outputs (``~/.local/bin`` links, bundle ``bin/`` copies, tools installed
by ``harness install``) live in ``$XDG_STATE_HOME/harness/hub-state.json`` (default
``~/.local/state/harness``) under the pseudo provider ``_hub``.

Paths are stored in ``~/`` form so a state file stays meaningful if ``$HOME`` moves.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional

from . import __version__
from .util import atomic_write, expand, state_dir

STATE_NAME = ".harness-state.json"
STATE_VERSION = 1


def state_path(provider_name: str, provider_home: Optional[str]) -> str:
    if provider_name == "_hub" or not provider_home:
        return os.path.join(state_dir(), "hub-state.json")
    return os.path.join(expand(provider_home), STATE_NAME)


class State:
    def __init__(self, path: str, provider: str, data: Optional[Dict[str, Any]] = None):
        self.path = path
        self.provider = provider
        data = data or {}
        self.version = data.get("version", STATE_VERSION)
        self.applied_at: Optional[str] = data.get("applied_at")
        self.harness_version: Optional[str] = data.get("harness_version")
        self.files: Dict[str, Dict[str, Any]] = dict(data.get("files", {}))
        self.conflicts: List[str] = list(data.get("conflicts", []))
        self.tools: Dict[str, Dict[str, Any]] = dict(data.get("tools", {}))
        self.exists = data != {}
        self._snapshot = self._fingerprint() if self.exists else None

    def _fingerprint(self) -> str:
        doc = self.to_json()
        doc.pop("applied_at", None)
        doc.pop("harness_version", None)
        return json.dumps(doc, sort_keys=True)

    def dirty(self) -> bool:
        return self._snapshot != self._fingerprint()

    # paths are keyed in ~/ form; callers use absolute paths
    @staticmethod
    def key(path: str) -> str:
        from .util import tilde

        return tilde(path)

    def get(self, path: str) -> Optional[Dict[str, Any]]:
        return self.files.get(self.key(path))

    def set(self, path: str, entry: Dict[str, Any]) -> None:
        self.files[self.key(path)] = entry

    def drop(self, path: str) -> None:
        self.files.pop(self.key(path), None)

    def paths(self) -> List[str]:
        return sorted(expand(k) for k in self.files)

    def to_json(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "version": STATE_VERSION,
            "harness_version": __version__,
            "provider": self.provider,
            "applied_at": self.applied_at,
            "files": {k: self.files[k] for k in sorted(self.files)},
            "conflicts": list(self.conflicts),
        }
        if self.tools:
            out["tools"] = {k: self.tools[k] for k in sorted(self.tools)}
        return out

    def save(self) -> None:
        self.applied_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        atomic_write(self.path, (json.dumps(self.to_json(), indent=2, sort_keys=False) + "\n").encode("utf-8"),
                     mode=0o644)

    def remove_file(self) -> None:
        try:
            os.unlink(self.path)
        except FileNotFoundError:
            pass


def load(provider_name: str, provider_home: Optional[str]) -> State:
    path = state_path(provider_name, provider_home)
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        data = {}
    except ValueError:
        from .util import HarnessError

        raise HarnessError("%s is not valid JSON; move it aside and re-run `harness apply --adopt`" % path)
    return State(path, provider_name, data)
