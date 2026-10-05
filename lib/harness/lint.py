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

* ``[harness]`` refs that name no file, doctor check or lint rule of the bundle
* ``taxonomy`` (principle 6, variety reduction): a ``[taxonomy.components]`` key that names no
  component; a posture on a kind that takes none (rule, guard, permission, installer, step,
  doctor); a function that contradicts a kind's fixed one; a component posture stronger than
  the bundle's; a bundle named ``providers`` or ``profiles`` (reserved by the id scheme)

Warnings: deprecated manifest keys (``[bundle].tags`` -> ``[taxonomy]``), ``requires.config`` keys never referenced by any
template, manifest string or env value (scripts may still read them from build/config.json),
skills whose SKILL.md ``name`` differs from the directory, and three principle checks:

* ``guides-sensors`` (principle 6): a public bundle without ``[harness]``, or whose
  ``[harness]`` has guides but no sensors (feedforward only) or sensors but no guides
* ``guard-reasons`` (principle 6): a deny/ask ``# rule:`` reason that does not state the
  alternative (none of the words use, instead, ask, run, mention, see)
* ``dependencies`` (principle 1): a binary invoked by ``bin/*``, ``bootstrap``,
  ``bundles/**/*.sh``, ``providers/**/*.sh``, ``tools/gate/*.sh`` or ``lib/harness/*.sh``
  (the ``.run`` header) that is neither on
  :data:`ALLOWED_BINARIES` nor declared by a bundle (``[requires.binaries]``, ``[provides] bin``);
  one warning per binary with its first ``file:line`` (heuristic, see ``shell_scan``)
* ``taxonomy`` (principle 6): a public bundle without ``[taxonomy]``; a public skill, agent,
  CLI or MCP server without a function or posture; a read-only agent whose front matter sets
  a non-default ``permissionMode``; a public skill, agent, rule, guard section or permission
  list that ``[harness]`` declares as neither guide nor sensor (empty permission lists excepted)
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
RULE_LINE_RE = re.compile(r"^#\s*rule:\s*(?P<pat>.+?)\s+->\s+(?P<dec>allow|ask|deny|pass|defer)\s*:\s*(?P<reason>.+?)\s*$")
ALTERNATIVE_RE = re.compile(r"\b(use|instead|ask|run|mention|see)\b", re.I)
LINT_RULES = {"manifest", "templates", "guard-syntax", "guard-reasons", "guides-sensors", "dependencies", "private-ids",
              "taxonomy"}

# Principle 1 (lightweight): binaries any script may call without a bundle declaring them.
ALLOWED_BINARIES = set(
    # the plan's base set: the hub's whole runtime footprint
    "bash sh python3 jq git curl ssh tar unzip shasum sha256sum awk sed grep cut tr sort uniq head tail wc "
    "find xargs mktemp install chmod ln readlink stat date printf cat env test "
    # POSIX utilities present on every Linux, WSL and macOS base system (found by the first scan)
    "dirname basename mkdir rm cp mv ls uname sleep diff cmp "
    # optional: only called behind `command -v` with a python fallback (core/lib/compat.sh hn_*)
    "timeout gtimeout realpath "
    # not a binary: the payload marker, last line of lib/harness/selfextract-header.sh (never executed)
    "__PAYLOAD_BELOW__".split())
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
            if not s.startswith("# rule:"):
                continue
            m = RULE_LINE_RE.match(s)
            if not m:
                rep.err("%s: %s:%d malformed rule comment (want '# rule: <pattern> -> <decision> : <reason>')" % (where, rel, i))
            elif m.group("dec") in ("deny", "ask") and not ALTERNATIVE_RE.search(m.group("reason")):
                rep.warn("%s: %s:%d guard-reasons: the %s reason %r does not say what to do instead; name the "
                         "alternative (use / run / ask / see / mention ... instead)" % (where, rel, i, m.group("dec"), m.group("reason")))
    lint_harness(b, rep)
    lint_taxonomy(b, rep)
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


def lint_harness(b: M.Bundle, rep: Report) -> None:
    """``[harness]`` refs must resolve; pairing gaps are warnings (principle 6)."""
    where = b.name
    check_ids = {c.get("id") for c in b.doctor_checks}
    for side, entries in (("guides", b.guides), ("sensors", b.sensors)):
        for e in entries:
            kind, ref = e.get("kind", ""), e.get("ref", "")
            if kind == "doctor":
                if ref == "doctor_checks" and not check_ids:
                    rep.err("%s: [harness] sensor doctor_checks but the bundle has no doctor checks" % where)
                elif ref != "doctor_checks" and ref not in check_ids:
                    rep.err("%s: [harness] sensor doctor %r names no doctor check of the bundle" % (where, ref))
            elif kind == "lint":
                if ref not in LINT_RULES:
                    rep.err("%s: [harness] sensor lint %r is not a lint rule (%s)" % (where, ref, ", ".join(sorted(LINT_RULES))))
            elif ref and not os.path.exists(b.rel(ref)):
                rep.err("%s: [harness] %s %s %s does not exist in the bundle" % (where, side[:-1], kind, ref))
    status = b.pairing()
    hint = ("pair each guide with a sensor that checks it (guard section, doctor check, test, lint rule) "
            "and each sensor with the guide that tells the agent the rule up front")
    if status == "undeclared" and b.origin == "public":
        rep.warn("%s: guides-sensors: no [harness] section; declare the bundle's guides and sensors (%s)" % (where, hint))
    elif status == "guides only":
        rep.warn("%s: guides-sensors: [harness] has guides but no sensors (feedforward only); %s" % (where, hint))
    elif status == "sensors only":
        rep.warn("%s: guides-sensors: [harness] has sensors but no guides (feedback only); %s" % (where, hint))
    elif status == "empty":
        rep.warn("%s: guides-sensors: [harness] declares neither guides nor sensors; %s" % (where, hint))


def _one_of(facet: str) -> str:
    from . import taxonomy as T

    return "one of: %s" % ", ".join(T.FACETS[facet])


def lint_taxonomy(b: M.Bundle, rep: Report) -> None:
    """``[taxonomy]``: overrides must name components and respect each kind's fixed facets."""
    from . import taxonomy as T
    from .util import HarnessError

    where = "%s: taxonomy:" % b.name
    if b.name in T.RESERVED_BUNDLE_NAMES:
        rep.err("%s the bundle name %r is reserved by the component id scheme (providers/<p>, profiles/<p>); "
                "rename the bundle directory and bundle.name" % (where, b.name))
    tax = b.taxonomy or {}
    public = b.origin == "public"
    if "taxonomy" not in b.data and public:
        rep.warn("%s no [taxonomy] section; add one with domain (%s) and posture (%s); "
                 "see docs/reference/taxonomy.md" % (where, _one_of("domain"), _one_of("posture")))
    try:
        comps = T.components(b)
    except HarnessError as exc:
        rep.err("%s %s; fix the file so its components can be listed" % (where, exc))
        return
    by_key = {c.key: c for c in comps}
    bundle_posture = tax.get("posture")
    for key, cls in sorted((tax.get("components") or {}).items()):
        c = by_key.get(key)
        if c is None:
            rep.err("%s components.%r names no component of the bundle; use an id printed by "
                    "`harness catalog --bundle %s` without the %r prefix (agents/<name>, guard.d/NN-<topic>, "
                    "doctor/<id>, steps/<id>, bin/<name>, mcp/<server>, install/<tool>, permissions)"
                    % (where, key, b.name, b.name + "/"))
            continue
        cls = cls or {}
        if "posture" in cls and c.kind not in T.POSTURE_KINDS:
            rep.err("%s components.%r sets posture; remove it (%s)" % (where, key, T.NO_POSTURE_REASON[c.kind]))
        fixed = T.KIND_FUNCTION.get(c.kind)
        if "function" in cls and fixed and cls["function"] != fixed:
            rep.err("%s components.%r sets function = %r but a %s is always %r; remove the function key"
                    % (where, key, cls["function"], c.kind, fixed))
        if ("posture" in cls and c.kind in T.POSTURE_KINDS and bundle_posture
                and T.posture_rank(cls["posture"]) > T.posture_rank(bundle_posture)):
            rep.err("%s components.%r posture %r is stronger than the bundle posture %r; raise taxonomy.posture "
                    "on the bundle or lower the component" % (where, key, cls["posture"], bundle_posture))
    for c in comps:
        if public and c.kind in T.DECLARED_FUNCTION_KINDS and not c.function:
            rep.warn("%s %s has no function; set it in [taxonomy] as the bundle default or in components.%r "
                     "(%s)" % (where, c.id, c.key, _one_of("function")))
        if public and c.kind in T.POSTURE_KINDS and not c.posture:
            rep.warn("%s %s has no posture; set it in [taxonomy] as the bundle default or in components.%r "
                     "(%s)" % (where, c.id, c.key, _one_of("posture")))
        if c.kind == "agent" and c.posture == "read-only":
            meta, _b = R.split_front_matter(read_text(b.rel(c.ref)) or "")
            mode = meta.get("permissionMode")
            if mode in ("auto", "acceptEdits", "bypassPermissions"):
                raise_bundle = T.posture_rank("local") > T.posture_rank(tax.get("posture"))
                rep.warn("%s %s has posture read-only but its front matter sets permissionMode: %s; "
                         "set posture = \"local\" in components.%r%s or remove permissionMode"
                         % (where, c.id, mode, c.key, " (and raise taxonomy.posture on the bundle)" if raise_bundle else ""))
        if public and c.kind in T.CONTROL_KINDS and c.kind != "doctor" and not c.control:
            if c.kind == "permission" and c.decisions == "empty (no rules)":
                continue
            rep.warn("%s %s appears in neither [harness] guides nor sensors; declare it as a guide or sensor "
                     "so its control facet is known" % (where, c.id))


def shell_files(home: str) -> List[str]:
    """The scripts the dependency rule scans (sorted, relative to ``home``)."""
    import glob

    out = set()
    for pat in ("bin/*", "bootstrap", "bundles/**/*.sh", "providers/**/*.sh", "tools/gate/*.sh", "lib/harness/*.sh"):
        for p in glob.glob(os.path.join(home, pat), recursive=True):
            if not os.path.isfile(p):
                continue
            if not p.endswith(".sh"):
                head = (read_text(p) or "")[:80]
                if not re.match(r"^#!.*\b(ba)?sh\b", head):
                    continue
            out.add(os.path.relpath(p, home))
    return sorted(out)


def lint_dependencies(hub: Any, rep: Report) -> None:
    from . import shell_scan

    declared: Set[str] = set()
    for b in hub.bundles.values():
        declared |= set(b.requires_binaries)
        declared |= {name for name, _t in b.bins()}
    files = shell_files(hub.home)
    texts = {f: read_text(os.path.join(hub.home, f)) or "" for f in files}
    funcs: Set[str] = set()
    for t in texts.values():
        # guard sections are concatenated with the engine and skills source their libs:
        # a function defined in any scanned script counts as defined everywhere
        funcs |= shell_scan.function_names(t)
    seen: Dict[str, List[str]] = {}
    for f in files:
        for line, word in shell_scan.commands(texts[f]):
            if word in ALLOWED_BINARIES or word in declared or word in funcs:
                continue
            seen.setdefault(word, []).append("%s:%d" % (f, line))
    for word in sorted(seen):
        where = seen[word]
        rep.warn("dependencies: %s invokes `%s`%s, which is neither on the lint allow-list nor declared by a bundle; "
                 "use an allowed tool or python, or declare it in [requires.binaries] of the bundle that needs it"
                 % (where[0], word, " (%d more)" % (len(where) - 1) if len(where) > 1 else ""))


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
    lint_dependencies(hub, rep)
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
