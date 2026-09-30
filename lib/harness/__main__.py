"""``python3 -m harness`` entry point (normally reached through ``bin/harness``)."""
from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
