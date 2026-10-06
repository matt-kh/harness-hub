"""Bundle and provider manifests: discovery, loading, validation and dependency resolution.

Discovery (in precedence order, a duplicate bundle name is an error):

* ``$HARNESS_HOME/bundles/*/bundle.toml`` (public bundles)
* ``<config dir>/bundles/*/bundle.toml`` (private org bundles in ``local/``), only when the
  config file is named ``harness.toml``
* every directory in ``[hub].bundle_paths`` (relative to the config file) and in
  ``$HARNESS_BUNDLE_PATH`` (colon separated) — used by tests and by org monorepos

Providers come from ``$HARNESS_HOME/providers/*/provider.toml`` plus ``$HARNESS_PROVIDER_PATH``.

``[provides]`` lists are authoritative when present (even when empty). When a key is absent
the directory convention is used: ``rules/NN-*.md``, ``skills/*/``, ``agents/*.md``,
``guard.d/NN-*.sh``, ``skill-fragments/**``, ``permissions.toml``, ``mcp.toml``, ``bin/*``.
``hook_rules`` is accepted as a deprecated alias of ``guard_rules``. Installers are
``install/*.sh``; MCP servers are the ``[servers.<name>]`` tables of the MCP file.

``[taxonomy]`` (optional; ``domain``, ``posture``, ``function`` and per-component
``[taxonomy.components]`` overrides) classifies the bundle's components; see
:mod:`harness.taxonomy` and docs/reference/taxonomy.md. ``[bundle].tags`` is deprecated in
its favour.
"""
from __future__ import annotations

import fnmatch
import glob
import json
import os
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from . import schema_lite, toml_compat
from .util import HarnessError, hub_home

_NN = re.compile(r"^[0-9][0-9]-")

PROFILE_SCHEMA: Dict[str, Any] = {
    "type": "object", "additionalProperties": False, "required": ["profile"],
    "properties": {"profile": {
        "type": "object", "additionalProperties": False, "required": ["bundles"],
        "properties": {
            "name": {"type": "string"}, "summary": {"type": "string"}, "description": {"type": "string"},
            "bundles": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
            "providers": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
        }}},
}


def load_schema(name: str, home: Optional[str] = None) -> Dict[str, Any]:
    with open(os.path.join(home or hub_home(), "schema", name), encoding="utf-8") as fh:
        return json.load(fh)


# ----------------------------------------------------------------- bundles


class Bundle:
    """A loaded ``bundle.toml`` plus its directory."""

    def __init__(self, path: str, data: Dict[str, Any], origin: str = "public"):
        self.path = path
        self.data = data
        self.origin = origin  # public | private | extra
        b = data.get("bundle", {})
        self.name: str = b.get("name", os.path.basename(path))
        self.summary: str = b.get("summary", "")
        self.description: str = b.get("description", "")
        self.depends_on: List[str] = list(b.get("depends_on", []))
        self.recommends: List[str] = list(b.get("recommends", []))
        self.conflicts_with: List[str] = list(b.get("conflicts_with", []))
        any_of = b.get("any_of", [])
        if any_of and all(isinstance(x, str) for x in any_of):
            any_of = [any_of]
        self.any_of: List[List[str]] = [list(g) for g in any_of]
        self.private: bool = bool(b.get("private", origin == "private"))
        req = data.get("requires", {})
        self.requires_binaries: Dict[str, Dict[str, Any]] = req.get("binaries", {})
        self.requires_config: Dict[str, Dict[str, Any]] = req.get("config", {})
        self.requires_secrets: Dict[str, Dict[str, Any]] = req.get("secrets", {})
        self.provides: Dict[str, Any] = data.get("provides", {})
        self.manual_steps: List[Dict[str, Any]] = data.get("manual_steps", [])
        self.doctor_checks: List[Dict[str, Any]] = data.get("doctor_checks", [])
        self.uninstall: Dict[str, Any] = data.get("uninstall", {})
        self.harness: Dict[str, Any] = data.get("harness", {})
        self.taxonomy: Dict[str, Any] = data.get("taxonomy", {})

    @property
    def manifest_path(self) -> str:
        return os.path.join(self.path, "bundle.toml")

    def rel(self, *parts: str) -> str:
        return os.path.join(self.path, *parts)

    def docs_path(self) -> str:
        return self.data.get("bundle", {}).get("docs") or "docs/bundles/%s.md" % self.name

    # -- provides, with directory-convention fallbacks -------------------------
    def _list(self, key: str, pattern: str) -> List[str]:
        if key in self.provides:
            return list(self.provides[key])
        return sorted(os.path.relpath(p, self.path) for p in glob.glob(os.path.join(self.path, pattern)))

    def rules(self) -> List[str]:
        return self._list("rules", "rules/[0-9][0-9]-*.md")

    def agents(self) -> List[str]:
        return self._list("agents", "agents/*.md")

    def guard_rules(self) -> List[str]:
        if "guard_rules" in self.provides:
            return list(self.provides["guard_rules"])
        if "hook_rules" in self.provides:
            return list(self.provides["hook_rules"])
        return self._list("guard_rules", "guard.d/[0-9][0-9]-*.sh")

    def skills(self) -> List[str]:
        """Skill directories, relative to the bundle (``skills/<name>``)."""
        if "skills" in self.provides:
            out = []
            for s in self.provides["skills"]:
                s = s.rstrip("/")
                out.append(s if "/" in s else "skills/" + s)
            return out
        return sorted(os.path.relpath(p, self.path).rstrip("/")
                      for p in glob.glob(os.path.join(self.path, "skills", "*", "")))

    def skill_fragment_files(self) -> List[Tuple[str, str, str]]:
        """(skill name, path inside the skill, bundle-relative source) for every fragment file."""
        patterns = self.provides.get("skill_fragments")
        root = os.path.join(self.path, "skill-fragments")
        if not os.path.isdir(root):
            return []
        out = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
            for fn in sorted(filenames):
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, self.path)
                if patterns is not None and not any(_glob_match(rel, p) for p in patterns):
                    continue
                inner = os.path.relpath(full, root).split(os.sep)
                if len(inner) < 2:
                    continue
                out.append((inner[0], "/".join(inner[1:]), rel))
        return sorted(out)

    def permissions_file(self) -> Optional[str]:
        p = self.provides.get("permissions")
        if p is None and os.path.exists(self.rel("permissions.toml")):
            p = "permissions.toml"
        return p or None

    def mcp_file(self) -> Optional[str]:
        p = self.provides.get("mcp")
        if p is None and os.path.exists(self.rel("mcp.toml")):
            p = "mcp.toml"
        return p or None

    def mcp_servers(self) -> List[str]:
        """Server names (``[servers.<name>]``) of the bundle's MCP file, in file order."""
        rel = self.mcp_file()
        if not rel or not os.path.isfile(self.rel(rel)):
            return []
        try:
            data = toml_compat.load_file(self.rel(rel))
        except toml_compat.TOMLDecodeError as exc:
            raise HarnessError("%s: TOML syntax error: %s" % (self.rel(rel), exc))
        return list((data.get("servers") or {}).keys())

    def installers(self) -> List[str]:
        """Tool installers, relative to the bundle (``install/<tool>.sh``)."""
        return sorted(os.path.relpath(p, self.path) for p in glob.glob(self.rel("install", "*.sh"))
                      if os.path.isfile(p))

    def bins(self) -> List[Tuple[str, str]]:
        """(link name, bundle-relative target) for every exposed executable."""
        out: List[Tuple[str, str]] = []
        entries = self.provides.get("bin")
        if entries is None:
            entries = sorted(os.path.relpath(p, self.path) for p in glob.glob(self.rel("bin", "*"))
                             if os.path.isfile(p))
        for e in entries:
            if isinstance(e, dict):
                out.append((e["name"], e["target"]))
            else:
                target = e if "/" in e else "bin/" + e
                name = os.path.basename(target)
                name = re.sub(r"\.(sh|py)$", "", name)
                out.append((name, target))
        return out

    def env(self) -> Dict[str, str]:
        return {k: v for k, v in sorted((self.provides.get("env") or {}).items())}

    # -- [harness]: guides (feedforward) and sensors (feedback) -----------------
    @property
    def guides(self) -> List[Dict[str, Any]]:
        return list(self.harness.get("guides") or [])

    @property
    def sensors(self) -> List[Dict[str, Any]]:
        return list(self.harness.get("sensors") or [])

    def pairing(self) -> str:
        """``paired`` | ``guides only`` | ``sensors only`` | ``empty`` | ``undeclared``."""
        if "harness" not in self.data:
            return "undeclared"
        g, s = bool(self.guides), bool(self.sensors)
        return "paired" if g and s else "guides only" if g else "sensors only" if s else "empty"


def _glob_match(rel: str, pattern: str) -> bool:
    if pattern.endswith("/**"):
        return rel == pattern[:-3] or rel.startswith(pattern[:-3] + "/")
    if "**" in pattern:
        return fnmatch.fnmatch(rel, pattern.replace("**/", "*").replace("**", "*"))
    return fnmatch.fnmatch(rel, pattern) or rel == pattern


def load_bundle(path: str, origin: str = "public") -> Bundle:
    mpath = os.path.join(path, "bundle.toml")
    try:
        data = toml_compat.load_file(mpath)
    except toml_compat.TOMLDecodeError as exc:
        raise HarnessError("%s: TOML syntax error: %s" % (mpath, exc))
    return Bundle(path, data, origin)


def discover_bundles(roots: Sequence[Tuple[str, str]]) -> Dict[str, Bundle]:
    """``roots`` is a list of (directory, origin). Returns name -> Bundle."""
    found: Dict[str, Bundle] = {}
    for root, origin in roots:
        if not os.path.isdir(root):
            continue
        for entry in sorted(os.listdir(root)):
            d = os.path.join(root, entry)
            if not os.path.isfile(os.path.join(d, "bundle.toml")):
                continue
            b = load_bundle(d, origin)
            if b.name in found:
                raise HarnessError("bundle %r defined twice: %s and %s" % (b.name, found[b.name].path, d))
            found[b.name] = b
    return found


def validate_bundle(b: Bundle, schema: Dict[str, Any]) -> schema_lite.ValidationResult:
    res = schema_lite.validate(schema, b.data)
    prefix = os.path.relpath(b.manifest_path, hub_home()) if b.origin == "public" else b.manifest_path
    res.errors = ["%s: %s" % (prefix, e) for e in res.errors]
    res.warnings = ["%s: %s" % (prefix, w) for w in res.warnings]
    if b.data.get("bundle", {}).get("name") and b.name != os.path.basename(b.path):
        res.errors.append("%s: bundle.name %r does not match its directory %r" % (
            prefix, b.name, os.path.basename(b.path)))
    return res


# ----------------------------------------------------------------- providers


class Provider:
    def __init__(self, path: str, data: Dict[str, Any]):
        self.path = path
        self.data = data
        p = data.get("provider", {})
        self.name: str = p.get("name", os.path.basename(path))
        self.home: str = p.get("home", "~/." + self.name)
        self.binary: Optional[str] = p.get("binary")
        self.version_cmd: Optional[str] = p.get("version_cmd")
        self.version_regex: Optional[str] = p.get("version_regex")
        self.min_version: Optional[str] = p.get("min_version")
        self.summary: str = p.get("summary", "")
        self.verified: str = p.get("verified", "")
        self.targets: Dict[str, Dict[str, Any]] = data.get("targets", {})
        self.capabilities: Dict[str, Any] = data.get("capabilities", {})
        # product features a bundle's [harness] may name as `provider-feature` sensors
        self.features: List[str] = list(data.get("features", []))
        self.precedence: Dict[str, Any] = data.get("precedence", {}) or {}

    def target(self, name: str) -> Optional[Dict[str, Any]]:
        t = self.targets.get(name)
        if not t or t.get("mode") == "unsupported":
            return None
        return t

    @property
    def manifest_path(self) -> str:
        return os.path.join(self.path, "provider.toml")


def discover_providers(roots: Sequence[str]) -> Dict[str, Provider]:
    found: Dict[str, Provider] = {}
    for root in roots:
        if not os.path.isdir(root):
            continue
        for entry in sorted(os.listdir(root)):
            mpath = os.path.join(root, entry, "provider.toml")
            if not os.path.isfile(mpath):
                continue
            try:
                data = toml_compat.load_file(mpath)
            except toml_compat.TOMLDecodeError as exc:
                raise HarnessError("%s: TOML syntax error: %s" % (mpath, exc))
            p = Provider(os.path.join(root, entry), data)
            if p.name in found:
                raise HarnessError("provider %r defined twice" % p.name)
            found[p.name] = p
    return found


def validate_provider(p: Provider, schema: Dict[str, Any]) -> schema_lite.ValidationResult:
    res = schema_lite.validate(schema, p.data)
    prefix = os.path.relpath(p.manifest_path, hub_home())
    res.errors = ["%s: %s" % (prefix, e) for e in res.errors]
    return res


# ----------------------------------------------------------------- profiles


def load_profile(home: str, name: str) -> Dict[str, Any]:
    path = os.path.join(home, "profiles", name + ".toml")
    if not os.path.exists(path):
        avail = ", ".join(list_profiles(home)) or "none"
        raise HarnessError("unknown profile %r (available: %s)" % (name, avail))
    data = toml_compat.load_file(path)
    res = schema_lite.validate(PROFILE_SCHEMA, data)
    if not res.ok:
        raise HarnessError("profiles/%s.toml: %s" % (name, "; ".join(res.errors)))
    return data["profile"]


def list_profiles(home: str) -> List[str]:
    return sorted(os.path.basename(p)[:-5] for p in glob.glob(os.path.join(home, "profiles", "*.toml")))


# ----------------------------------------------------------------- resolution


class Resolution:
    def __init__(self, order: List[str], added: Dict[str, str], recommended: Dict[str, List[str]]):
        self.order = order                  # active bundle names, dependency order
        self.added = added                  # auto-added dependency -> required by
        self.recommended = recommended      # inactive recommendation -> recommended by


def resolve(requested: Iterable[str], bundles: Dict[str, Bundle]) -> Resolution:
    """Close ``requested`` over depends_on, check conflicts and any_of, order deterministically.

    Order: a dependency always precedes its dependents; ties are broken by name.
    """
    requested = list(dict.fromkeys(requested))
    unknown = [n for n in requested if n not in bundles]
    if unknown:
        raise HarnessError("unknown bundle(s): %s (known: %s)" % (
            ", ".join(unknown), ", ".join(sorted(bundles)) or "none"))
    active: Dict[str, None] = {}
    added: Dict[str, str] = {}
    stack = list(reversed(requested))
    while stack:
        n = stack.pop()
        if n in active:
            continue
        active[n] = None
        for dep in bundles[n].depends_on:
            if dep not in bundles:
                raise HarnessError("bundle %s depends on unknown bundle %s" % (n, dep))
            if dep not in active and dep not in requested:
                added.setdefault(dep, n)
            stack.append(dep)
    names = set(active)
    for n in sorted(names):
        for c in bundles[n].conflicts_with:
            if c in names:
                raise HarnessError("bundles %s and %s conflict (conflicts_with); remove one from [hub].bundles" % (n, c))
    for n in sorted(names):
        for group in bundles[n].any_of:
            if not any(g in names for g in group):
                raise HarnessError(
                    "bundle %s needs at least one of: %s — add one to [hub].bundles" % (n, ", ".join(group)))
    # Kahn's algorithm with sorted ready set
    deps = {n: set(d for d in bundles[n].depends_on if d in names) for n in names}
    order: List[str] = []
    ready = sorted(n for n in names if not deps[n])
    while ready:
        n = ready.pop(0)
        order.append(n)
        for m in sorted(names):
            if n in deps[m]:
                deps[m].discard(n)
                if not deps[m] and m not in order and m not in ready:
                    ready.append(m)
        ready.sort()
    if len(order) != len(names):
        cyc = sorted(n for n in names if n not in order)
        raise HarnessError("dependency cycle among bundles: %s" % ", ".join(cyc))
    recommended: Dict[str, List[str]] = {}
    for n in order:
        for r in bundles[n].recommends:
            if r not in names and r in bundles:
                recommended.setdefault(r, []).append(n)
    return Resolution(order, added, recommended)
