"""lint: everything CI checks about manifests, before anything is rendered.

Errors (exit 1):
* schema validation of every bundle (public, private, extra), provider and profile
* unknown bundle names in depends_on / recommends / conflicts_with / any_of / profiles,
  unknown providers in profiles
* duplicate manual step or doctor check ids; ``doctor_checks[].fix`` that looks like an id
  but names no manual step of the bundle (dangling); ``unblocks`` naming no doctor check
* ``[provides]`` paths that do not exist; guard sections not named ``NN-*.sh`` or failing
  ``bash -n``; malformed ``# rule:`` comments; provider shims missing or failing ``bash -n``
* ``{{ key }}`` references to keys no schema knows (templated files and manifest strings)
* ``tools/gate/private-ids.sh`` (when present) reporting private identifiers

Warnings: deprecated manifest keys, ``requires.config`` keys never referenced by any
template, manifest string or env value (scripts may still read them from build/config.json),
skills whose SKILL.md ``name`` differs from the directory.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Set

from . import config as C
from . import manifest as M
from . import render as R
from .util import read_text, run_argv

ID_SHAPE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
BUILTIN_KEYS = {"hub.home", "hub.version", "hub.config", "provider.name", "provider.home", "provider.skills_dir"}


class Report:
    def __init__(self) -> None:
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def err(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


def _manifest_strings(b: M.Bundle) -> List[str]:
    out: List[str] = []
    for s in b.manual_steps:
        out += [s.get("title", ""), s.get("why", ""), s.get("how", ""), (s.get("verify") or {}).get("cmd", "")]
    for c in b.doctor_checks:
        out.append(c.get("cmd", ""))
    out += [str(v) for v in b.env().values()]
    for rel in (b.permissions_file(), b.mcp_file()):
        if rel and os.path.exists(b.rel(rel)):
            out.append(read_text(b.rel(rel)) or "")
    for e in b.requires_config.values():
        if isinstance(e.get("default"), str):
            out.append(e["default"])
    return out


def _templated_texts(b: M.Bundle) -> List[tuple]:
    texts = []
    for rel in b.rules() + b.agents():
        if os.path.exists(b.rel(rel)):
            texts.append((rel, read_text(b.rel(rel)) or ""))
    for rel in b.skills():
        base = b.rel(rel)
        if os.path.isdir(base):
            for dirpath, _d, files in os.walk(base):
                for fn in files:
                    if fn.endswith(".md"):
                        p = os.path.join(dirpath, fn)
                        texts.append((os.path.relpath(p, b.path), read_text(p) or ""))
    for _skill, _inner, rel in b.skill_fragment_files():
        if rel.endswith(".md"):
            texts.append((rel, read_text(b.rel(rel)) or ""))
    return texts


def key_known(key: str, leaves: Set[str], schema: Dict[str, Any]) -> bool:
    if key in BUILTIN_KEYS or key in leaves:
        return True
    from .schema_lite import subschema_at

    return subschema_at(schema, key) is not None


def lint_bundle(b: M.Bundle, all_bundles: Dict[str, M.Bundle], schema: Dict[str, Any], bschema: Dict[str, Any],
                rep: Report) -> Set[str]:
    """Returns the template keys the bundle references."""
    res = M.validate_bundle(b, bschema)
    for e in res.errors:
        rep.err(e)
    for w in res.warnings:
        rep.warn(w)
    where = b.name
    for label, names in (("depends_on", b.depends_on), ("recommends", b.recommends),
                         ("conflicts_with", b.conflicts_with)):
        for n in names:
            if n not in all_bundles and label != "conflicts_with":
                rep.err("%s: %s names unknown bundle %s" % (where, label, n))
    for grp in b.any_of:
        if not any(n in all_bundles for n in grp):
            rep.err("%s: any_of group %s names no known bundle" % (where, grp))
    step_ids = [s.get("id") for s in b.manual_steps]
    check_ids = [c.get("id") for c in b.doctor_checks]
    for label, ids in (("manual_steps", step_ids), ("doctor_checks", check_ids)):
        dup = sorted(set(i for i in ids if ids.count(i) > 1))
        for d in dup:
            rep.err("%s: duplicate %s id %s" % (where, label, d))
    for c in b.doctor_checks:
        fix = c.get("fix", "")
        if fix and ID_SHAPE.match(fix) and fix not in step_ids:
            rep.err("%s: doctor_checks.%s.fix = %r names no manual step (dangling id)" % (where, c.get("id"), fix))
        if c.get("script") and not os.path.isfile(b.rel(c["script"])):
            rep.err("%s: doctor_checks.%s.script %s does not exist" % (where, c.get("id"), c["script"]))
    for s in b.manual_steps:
        for u in (s.get("unblocks") or []) + ((s.get("verify") or {}).get("unblocks") or []):
            if u not in check_ids:
                rep.err("%s: manual_steps.%s unblocks unknown doctor check %s" % (where, s.get("id"), u))
    # provides paths
    for rel in b.rules() + b.agents():
        if not os.path.isfile(b.rel(rel)):
            rep.err("%s: provides %s which does not exist" % (where, rel))
    for rel in b.skills():
        if not os.path.isdir(b.rel(rel)):
            rep.err("%s: provides skill %s which does not exist" % (where, rel))
        else:
            meta, _ = R.split_front_matter(read_text(b.rel(rel, "SKILL.md")) or "")
            name = os.path.basename(rel.rstrip("/"))
            if meta.get("name") and meta["name"] != name:
                rep.warn("%s: %s/SKILL.md name %r differs from the directory" % (where, rel, meta["name"]))
    for rel in (b.permissions_file(), b.mcp_file()):
        if rel and not os.path.isfile(b.rel(rel)):
            rep.err("%s: provides %s which does not exist" % (where, rel))
    for name, target in b.bins():
        if not os.path.isfile(b.rel(target)):
            rep.err("%s: bin %s -> %s does not exist" % (where, name, target))
    for rel in b.guard_rules():
        full = b.rel(rel)
        base = os.path.basename(rel)
        if not os.path.isfile(full):
            rep.err("%s: guard rule %s does not exist" % (where, rel))
            continue
        if not re.match(r"^[0-9][0-9]-.*\.sh$", base):
            rep.err("%s: guard rule %s must be named NN-<topic>.sh" % (where, rel))
        rc, _o, err = run_argv(["bash", "-n", full], timeout=20)
        if rc != 0:
            rep.err("%s: bash -n %s: %s" % (where, rel, err.strip().splitlines()[0] if err.strip() else rc))
        for i, line in enumerate((read_text(full) or "").splitlines(), 1):
            s = line.strip()
            if s.startswith("# rule:") and not re.match(r"^#\s*rule:\s*.+?\s+->\s+(allow|ask|deny|pass|defer)\s*:\s*.+$", s):
                rep.err("%s: %s:%d malformed rule comment (want '# rule: <pattern> -> <decision> : <reason>')" % (where, rel, i))
    # templates
    used: Set[str] = set()
    leaves = set(C.schema_leaf_keys(schema))
    for rel, text in _templated_texts(b):
        for key in R.template_keys(text):
            used.add(key)
            if not key_known(key, leaves, schema):
                rep.err("%s: %s uses {{ %s }} which no schema key defines" % (where, rel, key))
    for text in _manifest_strings(b):
        for key in R.template_keys(text):
            used.add(key)
            if not key_known(key, leaves, schema):
                rep.err("%s: bundle.toml/permissions/mcp uses {{ %s }} which no schema key defines" % (where, key))
    return used


def run_lint(hub: Any) -> Report:
    rep = Report()
    home = hub.home
    bschema = M.load_schema("bundle.schema.json", home)
    pschema = M.load_schema("provider.schema.json", home)
    schema = hub.schema
    used: Set[str] = set()
    for name in sorted(hub.bundles):
        used |= lint_bundle(hub.bundles[name], hub.bundles, schema, bschema, rep)
    for name in sorted(hub.bundles):
        b = hub.bundles[name]
        for key in sorted(b.requires_config):
            env_refs = any(key in str(v) for v in b.env().values())
            if key not in used and not env_refs:
                rep.warn("%s: requires.config %s is not referenced by any template (fine if scripts read build/config.json)"
                         % (name, key))
    for name in sorted(hub.providers):
        p = hub.providers[name]
        res = M.validate_provider(p, pschema)
        for e in res.errors:
            rep.err(e)
        hooks = p.targets.get("hooks") or {}
        shim = hooks.get("shim") if hooks.get("mode") != "unsupported" else ""
        if shim:
            path = os.path.join(p.path, shim)
            if not os.path.isfile(path):
                rep.err("providers/%s: shim %s does not exist" % (name, shim))
            else:
                rc, _o, err = run_argv(["bash", "-n", path], timeout=20)
                if rc != 0:
                    rep.err("providers/%s: bash -n %s failed: %s" % (name, shim, err.strip()))
    for prof in M.list_profiles(home):
        try:
            data = M.load_profile(home, prof)
        except Exception as exc:
            rep.err(str(exc))
            continue
        for n in data.get("bundles", []):
            if n not in hub.bundles:
                rep.err("profiles/%s.toml: unknown bundle %s" % (prof, n))
        for n in data.get("providers", []):
            if n not in hub.providers:
                rep.err("profiles/%s.toml: unknown provider %s" % (prof, n))
    gate = os.path.join(home, "tools", "gate", "private-ids.sh")
    if os.path.isfile(gate) and os.environ.get("HARNESS_LINT_SKIP_GATE") != "1":
        rc, out, err = run_argv(["bash", gate, "--ci"], timeout=300, cwd=home)
        if rc == 1:
            lines = [ln for ln in (out + err).splitlines() if ln.strip()][:20]
            rep.err("private-identifier gate failed:\n    " + "\n    ".join(lines))
        elif rc not in (0, 1):
            rep.warn("private-identifier gate could not run (rc=%d): %s" % (rc, (err or out).strip()[:200]))
    return rep


def run(ctx: Any) -> int:
    from .hub import Hub

    hub = Hub(home=ctx.home, config_path=ctx.config, require_config=False, select=False)
    rep = run_lint(hub)
    if hub.selection_error:
        rep.warn("config %s: %s" % (hub.config_path, hub.selection_error))
    for w in rep.warnings:
        print("WARN  %s" % w)
    for e in rep.errors:
        print("FAIL  %s" % e)
    print("lint: %d bundle(s), %d provider(s): %d error(s), %d warning(s)" % (
        len(hub.bundles), len(hub.providers), len(rep.errors), len(rep.warnings)))
    return 1 if rep.errors else 0
