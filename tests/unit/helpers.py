"""Shared helpers for the engine unit tests.

Every test runs against a throw-away ``$HOME`` and a *copy* of the fixture bundles
(``tests/fixtures/bundles``), so tests may write sources (sync --adopt) and provider homes
freely. ``HARNESS_BUNDLES_ROOT`` points the hub at the copy; the real ``bundles/`` tree is
never read by these tests.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
LIB = os.path.join(REPO, "lib")
if LIB not in sys.path:
    sys.path.insert(0, LIB)
FIXTURES = os.path.join(REPO, "tests", "fixtures")

_ENV_KEYS = ("HOME", "HARNESS_BUNDLES_ROOT", "HARNESS_CONFIG", "HARNESS_HOME", "XDG_STATE_HOME",
             "XDG_DATA_HOME", "HARNESS_BUNDLE_PATH", "HARNESS_PROVIDER_PATH")


class HubTestCase(unittest.TestCase):
    """Temp HOME + copied fixture bundles + a config file in the temp dir."""

    config_text = None  # override per test class; default = fixtures/harness.fixture.toml

    def setUp(self) -> None:
        # commands print progress; keep the unittest output readable (HARNESS_TEST_VERBOSE=1 shows it)
        self._stdout = sys.stdout
        if not os.environ.get("HARNESS_TEST_VERBOSE"):
            import io

            sys.stdout = io.StringIO()
        self._saved = {k: os.environ.get(k) for k in _ENV_KEYS}
        for k in list(os.environ):
            if k.startswith("HARNESS_") and k not in _ENV_KEYS:
                self._saved[k] = os.environ.pop(k)
        self.tmp = tempfile.mkdtemp(prefix="harness-unit-")
        self.home = os.path.join(self.tmp, "home")
        os.makedirs(self.home)
        self.bundles = os.path.join(self.tmp, "bundles")
        shutil.copytree(os.path.join(FIXTURES, "bundles"), self.bundles, symlinks=True)
        os.environ["HOME"] = self.home
        os.environ["HARNESS_BUNDLES_ROOT"] = self.bundles
        os.environ["HARNESS_HOME"] = REPO
        for k in ("HARNESS_CONFIG", "XDG_STATE_HOME", "XDG_DATA_HOME", "HARNESS_BUNDLE_PATH", "HARNESS_PROVIDER_PATH"):
            os.environ.pop(k, None)
        self.cfg_dir = os.path.join(self.tmp, "local")
        os.makedirs(self.cfg_dir)
        self.cfg = os.path.join(self.cfg_dir, "harness.toml")
        text = self.config_text
        if text is None:
            with open(os.path.join(FIXTURES, "harness.fixture.toml"), encoding="utf-8") as fh:
                text = fh.read()
        self.write(self.cfg, text)

    def tearDown(self) -> None:
        sys.stdout = self._stdout
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- helpers --------------------------------------------------------------
    @staticmethod
    def write(path: str, text: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    @staticmethod
    def read(path: str) -> str:
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def hub(self, **kw):
        from harness.hub import Hub

        return Hub(home=REPO, config_path=self.cfg, **kw)

    def plan(self, hub=None, providers=None, adopt=()):
        from harness import plan as P

        hub = hub or self.hub()
        provs = hub.filter_providers(providers)
        return hub, P.build(hub, provs, adopt=adopt)

    def apply(self, hub=None, providers=None, adopt=()):
        from harness import apply as A

        hub, plan = self.plan(hub, providers, adopt)
        A.execute(plan, hub, {p.name: p.home for p in hub.filter_providers(providers)}, log=lambda *a: None)
        return plan

    def h(self, *parts: str) -> str:
        return os.path.join(self.home, *parts)
