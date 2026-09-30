"""Build products under ``$HARNESS_HOME/build/`` (gitignored).

* ``build/config.json`` - the merged configuration plus ``_harness`` (active bundles and
  providers, hub home, version) for python tools and scripts (``jq`` friendly).
* ``build/guard.env`` - the provider-neutral guard environment (``[provides.env]`` of every
  active bundle after templating, plus ``HARNESS_HOME``/``HARNESS_BUNDLES``).
"""
from __future__ import annotations

import os
from typing import Any

from .util import atomic_write, dump_json


def write(hub: Any) -> None:
    from .render import Renderer, guard_env

    os.makedirs(hub.build_dir, exist_ok=True)
    doc = dict(hub.config.data)
    doc["_harness"] = {
        "home": hub.home,
        "version": hub.version,
        "config": hub.config_path,
        "bundles": hub.active_names,
        "providers": [p.name for p in hub.active_providers],
    }
    atomic_write(os.path.join(hub.build_dir, "config.json"), dump_json(doc, sort_keys=True))
    env = Renderer(hub)._compile_env(hub.active_bundles)
    atomic_write(os.path.join(hub.build_dir, "guard.env"), guard_env(env))
