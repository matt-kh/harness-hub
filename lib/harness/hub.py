"""The loaded hub: config + discovered bundles/providers + the resolved active sets.

Every command builds one :class:`Hub`. Loading is lazy about validation so that
``config validate``/``lint`` can report every error instead of stopping at the first.
"""
from __future__ import annotations

import hashlib
import os
from typing import Any, Dict, List, Optional, Sequence

from . import __version__
from . import config as cfgmod
from . import manifest
from .util import HarnessError, hub_home, user_home


def resolve_build_dir(home: str, config_path: str) -> str:
    """Where build products (config.json, guard.env) for this config go.

    ``$HARNESS_BUILD_DIR`` wins; the hub's own ``<hub>/build`` belongs to the canonical
    ``<hub>/local/harness.toml`` only (rendered skills read it through ``HARNESS_HOME``);
    any other config (fixtures, CI, a second checkout's config) gets a private directory
    ``${XDG_CACHE_HOME:-~/.cache}/harness/build/<sha1(realpath(config))[:12]>`` so a test
    or experiment never overwrites the live compiled config.
    """
    env = os.environ.get("HARNESS_BUILD_DIR")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    real = os.path.realpath(config_path)
    if real == os.path.realpath(os.path.join(home, "local", "harness.toml")):
        return os.path.join(home, "build")
    cache = os.environ.get("XDG_CACHE_HOME") or os.path.join(user_home(), ".cache")
    digest = hashlib.sha1(real.encode("utf-8")).hexdigest()[:12]
    return os.path.join(cache, "harness", "build", digest)


class Hub:
    def __init__(self, home: Optional[str] = None, config_path: Optional[str] = None,
                 bundles: Optional[Sequence[str]] = None, providers: Optional[Sequence[str]] = None,
                 profile: Optional[str] = None, require_config: bool = True,
                 environ: Optional[Dict[str, str]] = None, select: bool = True):
        self.home = os.path.abspath(home or hub_home())
        self.version = __version__
        self.config_path = cfgmod.resolve_config_path(config_path, self.home)
        self.config_dir = os.path.dirname(self.config_path)
        self.build_dir = resolve_build_dir(self.home, self.config_path)
        self.environ = environ
        self.user_layers = cfgmod.user_layers(self.config_path, required=require_config)
        raw: Dict[str, Any] = {}
        for layer in self.user_layers:
            raw = cfgmod.deep_merge(raw, layer.data)
        self.raw_user = raw

        # discovery ---------------------------------------------------------
        # HARNESS_BUNDLES_ROOT replaces the public bundles/ directory (tests, forks)
        public = os.environ.get("HARNESS_BUNDLES_ROOT") or os.path.join(self.home, "bundles")
        roots = [(os.path.abspath(os.path.expanduser(public)), "public")]
        # private org bundles live next to a canonical config file (local/harness.toml ->
        # local/bundles/); a differently named file (tests/fixtures/harness.ci.toml) gets none,
        # so fixtures and CI configs never pick up neighbouring directories by accident
        if os.path.basename(self.config_path) == "harness.toml":
            roots.append((os.path.join(self.config_dir, "bundles"), "private"))
        for extra in (raw.get("hub", {}) or {}).get("bundle_paths", []) or []:
            roots.append((os.path.normpath(os.path.join(self.config_dir, os.path.expanduser(extra))), "extra"))
        for extra in filter(None, (os.environ.get("HARNESS_BUNDLE_PATH") or "").split(":")):
            roots.append((os.path.abspath(os.path.expanduser(extra)), "extra"))
        # the config dir may be the hub itself (bundles/ already listed)
        seen = set()
        uniq = []
        for r, o in roots:
            key = os.path.realpath(r)
            if key in seen:
                continue
            seen.add(key)
            uniq.append((r, o))
        self.bundles = manifest.discover_bundles(uniq)
        prov_roots = [os.path.join(self.home, "providers")]
        prov_roots += [os.path.abspath(p) for p in filter(None, (os.environ.get("HARNESS_PROVIDER_PATH") or "").split(":"))]
        self.providers = manifest.discover_providers(prov_roots)

        # selection -----------------------------------------------------------
        hub_cfg = raw.get("hub", {}) or {}
        prof_name = profile or hub_cfg.get("profile")
        prof: Dict[str, Any] = manifest.load_profile(self.home, prof_name) if prof_name else {}
        self.profile = prof_name
        req_bundles = list(bundles) if bundles else list(hub_cfg.get("bundles") or prof.get("bundles") or [])
        req_providers = list(providers) if providers else list(hub_cfg.get("providers") or prof.get("providers") or [])
        if not req_bundles and require_config:
            raise HarnessError("no bundles selected: set [hub].bundles or [hub].profile in %s" % self.config_path)
        self.selection_error: Optional[str] = None
        if not select:
            # lint/docs: manifests only; a broken [hub] selection must not hide manifest errors
            try:
                manifest.resolve(req_bundles, self.bundles)
            except HarnessError as exc:
                self.selection_error = str(exc)
            req_bundles, req_providers = [], []
        self.requested_bundles = req_bundles
        self.resolution = manifest.resolve(req_bundles, self.bundles)
        self.active_bundles: List[manifest.Bundle] = [self.bundles[n] for n in self.resolution.order]
        unknown = [p for p in req_providers if p not in self.providers]
        if unknown:
            raise HarnessError("unknown provider(s): %s (known: %s)" % (
                ", ".join(unknown), ", ".join(sorted(self.providers))))
        self.active_providers: List[manifest.Provider] = [self.providers[p] for p in req_providers]

        # config --------------------------------------------------------------
        base = cfgmod.load_base_schema(self.home)
        self.schema = cfgmod.compile_schema(base, self.bundles.values(), self.resolution.order)
        layers = cfgmod.bundle_default_layers(self.active_bundles) + self.user_layers
        self.config = cfgmod.Config(self.config_path, layers, self.schema, environ)

    # ------------------------------------------------------------------ helpers
    @property
    def active_names(self) -> List[str]:
        return [b.name for b in self.active_bundles]

    def bundle(self, name: str) -> manifest.Bundle:
        if name not in self.bundles:
            raise HarnessError("unknown bundle %r" % name)
        return self.bundles[name]

    def provider(self, name: str) -> manifest.Provider:
        if name not in self.providers:
            raise HarnessError("unknown provider %r" % name)
        return self.providers[name]

    def filter_providers(self, names: Optional[Sequence[str]]) -> List[manifest.Provider]:
        if not names:
            return list(self.active_providers)
        out = []
        for n in names:
            p = self.provider(n)
            out.append(p)
        return out

    def validate_config(self, strict: bool = False) -> None:
        res = self.config.validate()
        errors = list(res.errors)
        if strict:
            errors += res.warnings
        if errors:
            raise HarnessError("configuration is invalid:\n  " + "\n  ".join(errors))

    def template_context(self, provider: Optional[manifest.Provider] = None) -> Dict[str, Any]:
        """Values visible to ``{{ key }}``: the merged config plus built-ins.

        Built-ins: ``hub.home``, ``hub.version``, ``hub.config`` and, when rendering for a
        provider, ``provider.name``, ``provider.home`` (``~`` form) and
        ``provider.skills_dir``.
        """
        ctx = cfgmod.deep_merge(self.config.data, {})
        hub = ctx.setdefault("hub", {})
        if isinstance(hub, dict):
            hub.update({"home": self.home, "version": self.version, "config": self.config_path})
        if provider is not None:
            skills = provider.target("skills")
            ctx["provider"] = {
                "name": provider.name,
                "home": provider.home,
                "skills_dir": skills["path"].replace("/<name>", "") if skills else "",
            }
        return ctx
