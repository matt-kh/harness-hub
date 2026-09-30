"""harness-hub engine.

Renders one declarative configuration (``local/harness.toml``) plus a set of bundles into the
configuration directories of several AI coding-agent providers. Python standard library only;
runs on python 3.9+. See ARCHITECTURE.md at the repository root for the normative contracts.
"""
from __future__ import annotations

__all__ = ["__version__"]


def _read_version() -> str:
    import os

    here = os.path.dirname(os.path.abspath(__file__))
    try:
        with open(os.path.join(here, "..", "..", "VERSION"), encoding="utf-8") as fh:
            return fh.read().strip() or "0.0.0"
    except OSError:
        return "0.0.0"


__version__ = _read_version()
