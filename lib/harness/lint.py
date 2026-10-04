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

* ``[harness]`` refs that name no file, doctor check or lint rule of the bundle; a
  ``provider-feature`` sensor ref that is not ``<provider>:<feature>`` naming an entry of that
  provider's ``features``
* ``env-provides``: a ``[provides.env]`` key without a prefix the guard's guard.env parser
  accepts (parsed from the ``case "$_gk" in`` line of ``bundles/core/guard/engine.sh``)
* ``permissions-vs-guard``: a ``Bash(<prefix>:*)`` allow rule the guard (engine + core + the
  bundle, stubs from ``bundles/core/guard/tests/stubs``) denies or asks for ``<prefix> x``, or a
  deny rule it allows
* ``agent-tools``: a public agent whose ``model:`` is not ``{{ core.model_policy.plan|execute }}``
* ``fragments-target``: a ``skill-fragments/<skill>/`` entry whose skill no bundle in
  ``depends_on``, ``recommends`` or ``any_of`` provides
* ``profile-sane``: a profile naming unknown or private bundles, unknown providers, or a
  selection that does not resolve (depends_on, conflicts_with, any_of)
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
  ``bundles/**/*.sh``, ``providers/**/*.sh`` or ``tools/gate/*.sh`` that is neither on
  :data:`ALLOWED_BINARIES` nor declared by a bundle (``[requires.binaries]``, ``[provides] bin``);
  one warning per binary with its first ``file:line`` (heuristic, see ``shell_scan``)
* ``taxonomy`` (principle 6): a public bundle without ``[taxonomy]``; a public skill, agent,
  CLI or MCP server without a function or posture; a read-only agent whose front matter sets
  a public skill, agent, rule, guard section or permission list that ``[harness]`` declares as
  neither guide nor sensor (empty permission lists excepted)
* ``rule-guard-pairing`` (principle 6): a public ``rules/NN-x.md`` without a ``guard.d/NN-*.sh``
  (or the reverse) unless ``[harness].coverage_note`` names the topic ``x``
* ``agent-tools``: a read-only agent whose front matter sets a non-default ``permissionMode``
  or lists ``Edit``/``Write``/``MultiEdit``/``NotebookEdit`` in ``tools:`` (public bundles)
* ``skill-description``: a public SKILL.md description, expanded with
  ``tests/fixtures/harness.ci.toml``, outside 60-1024 chars or without a "Use when" trigger;
  workflow skills also need "NOT for" and an ``argument-hint``
* ``fragments-target``: a public bundle that ships skill fragments at all
* ``stability``: a ``stability = "stable"`` bundle whose coverage_note admits a missing suite,
  or whose skill or CLI has no ``tests/run.sh`` (CONTRIBUTING "Stability levels")

``harness lint --skip RULE`` turns off one of :data:`SKIPPABLE_RULES` (e.g. the slower
``permissions-vs-guard``).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from . import config as C
from . import manifest as M
from . import render as R
from .util import HarnessError, read_text, run_argv, which

ID_SHAPE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
RULE_LINE_RE = re.compile(r"^#\s*rule:\s*(?P<pat>.+?)\s+->\s+(?P<dec>allow|ask|deny|pass|defer)\s*:\s*(?P<reason>.+?)\s*$")
ALTERNATIVE_RE = re.compile(r"\b(use|instead|ask|run|mention|see)\b", re.I)
LINT_RULES = {"manifest", "templates", "guard-syntax", "guard-reasons", "guides-sensors", "dependencies", "private-ids",
              "taxonomy", "env-provides", "rule-guard-pairing", "permissions-vs-guard", "agent-tools",
              "skill-description", "fragments-target", "profile-sane", "stability"}
# rules `harness lint --skip RULE` can turn off (the others are woven into the manifest pass)
SKIPPABLE_RULES = ("agent-tools", "dependencies", "env-provides", "fragments-target", "permissions-vs-guard",
                   "private-ids", "profile-sane", "rule-guard-pairing", "skill-description", "stability")

# env-provides: the guard.env parser in bundles/core/guard/engine.sh accepts only keys with these
# prefixes. The list is parsed out of the engine's `case "$_gk" in ...` line; this copy is the
# fallback when that line cannot be found (lint then warns once).
GUARD_ENV_PREFIXES_FALLBACK = ("WORK_TICKET_", "HARNESS_", "K8S_", "GUARD_", "JIRA_", "GDOC_", "CREATE_TICKET_")
_ENV_CASE_RE = re.compile(r'case\s+"\$_gk"\s+in\s+((?:[A-Z][A-Z0-9_]*\*\|?)+)\)')

# permissions-vs-guard: client-path variables pointing the guard at the stubs in
# bundles/core/guard/tests/stubs (mirrors bundles/core/guard/tests/lib.sh)
GUARD_STUBS = (("WORK_TICKET_JIRA_PY", "jira-stub.py"), ("WORK_TICKET_GLAB", "glab-stub.sh"),
               ("WORK_TICKET_GDOC_PY", "gdoc-stub.py"), ("GUARD_KUBECTL", "kubectl-stub.sh"),
               ("GUARD_GIT", "git-stub.sh"), ("WORK_TICKET_GH", "gh-stub.sh"))
_BASH_RULE_RE = re.compile(r"^Bash\((?P<prefix>[^()]+):\*\)$")

# agent-tools
WRITE_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")

# skill-description
DESCRIPTION_MIN, DESCRIPTION_MAX = 60, 1024
TRIGGER_RE = re.compile(r"\bUse (this )?(skill )?when\b|\bUse when\b")
NEGATIVE_SCOPE_RE = re.compile(r"\bNOT for\b|\bNot for\b")
CI_CONFIG = os.path.join("tests", "fixtures", "harness.ci.toml")

# stability
NO_SUITE_RE = re.compile(r"no (unit |own )?(test )?suite", re.I)
STABLE_HINT = "stable requires a test suite per skill/CLI; move to beta or add the suite"

# Principle 1 (lightweight): binaries any script may call without a bundle declaring them.
ALLOWED_BINARIES = set(
    # the plan's base set: the hub's whole runtime footprint
    "bash sh python3 jq git curl ssh tar unzip shasum sha256sum awk sed grep cut tr sort uniq head tail wc "
    "find xargs mktemp install chmod ln readlink stat date printf cat env test "
    # POSIX utilities present on every Linux, WSL and macOS base system (found by the first scan)
    "dirname basename mkdir rm cp mv ls uname sleep diff cmp "
    # optional: only called behind `command -v` with a python fallback (core/lib/compat.sh hn_*)
    "timeout gtimeout realpath".split())
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
                rep: Report, providers: Optional[Dict[str, M.Provider]] = None) -> Set[str]:
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
    lint_harness(b, rep, providers)
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


PROVIDER_FEATURE_RE = re.compile(r"^(?P<provider>[a-z0-9][a-z0-9-]*):(?P<feature>[a-z0-9][a-z0-9-]*)$")


def lint_harness(b: M.Bundle, rep: Report, providers: Optional[Dict[str, M.Provider]] = None) -> None:
    """``[harness]`` refs must resolve; pairing gaps are warnings (principle 6).

    ``provider-feature`` sensor refs are ``<provider>:<feature>``; with ``providers`` given, the
    feature must be listed in that provider's ``features``.
    """
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
            elif kind == "provider-feature":
                m = PROVIDER_FEATURE_RE.match(ref)
                if not m:
                    rep.err("%s: [harness] sensor provider-feature %r must be <provider>:<feature> "
                            "(e.g. claude:auto-mode-classifier)" % (where, ref))
                elif providers is not None:
                    p = providers.get(m.group("provider"))
                    if p is None:
                        rep.err("%s: [harness] sensor provider-feature %r names unknown provider %s; use one of: %s"
                                % (where, ref, m.group("provider"), ", ".join(sorted(providers))))
                    elif m.group("feature") not in p.features:
                        rep.err("%s: [harness] sensor provider-feature %r: provider %s declares no feature %r "
                                "(features: %s); add it to providers/%s/provider.toml `features` or fix the ref"
                                % (where, ref, p.name, m.group("feature"), ", ".join(p.features) or "none",
                                   p.name))
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
        if public and c.kind in T.CONTROL_KINDS and c.kind != "doctor" and not c.control:
            if c.kind == "permission" and c.decisions == "empty (no rules)":
                continue
            rep.warn("%s %s appears in neither [harness] guides nor sensors; declare it as a guide or sensor "
                     "so its control facet is known" % (where, c.id))


# ----------------------------------------------------------------- env-provides


def guard_env_prefixes(engine_sh: str) -> List[str]:
    """The key prefixes the guard's guard.env parser accepts ([] when its case line is not found)."""
    for line in (read_text(engine_sh) or "").splitlines():
        m = _ENV_CASE_RE.search(line)
        if m:
            return [p[:-1] for p in m.group(1).split("|") if p.endswith("*")]
    return []


def resolve_env_prefixes(hub: Any, rep: Report) -> List[str]:
    """Prefixes parsed from the hub's guard engine; the fallback list (and one warning) otherwise."""
    engine = R.find_guard_engine([hub.bundles[n] for n in sorted(hub.bundles)])
    path = engine.rel("guard", "engine.sh") if engine else os.path.join(hub.home, "bundles", "core", "guard", "engine.sh")
    prefixes = guard_env_prefixes(path)
    if not prefixes:
        rep.warn("env-provides: could not parse the guard.env prefix list (the `case \"$_gk\" in A_*|B_*) ;;` line) "
                 "from %s; checking against the built-in list %s instead; keep that case pattern on one line"
                 % (os.path.relpath(path, hub.home), ", ".join(GUARD_ENV_PREFIXES_FALLBACK)))
        prefixes = list(GUARD_ENV_PREFIXES_FALLBACK)
    return prefixes


def lint_env_provides(b: M.Bundle, prefixes: Sequence[str], rep: Report) -> None:
    """Every ``[provides.env]`` key must survive the guard's guard.env prefix filter."""
    for key in sorted(b.provides.get("env") or {}):
        if not any(key.startswith(p) for p in prefixes):
            rep.err("%s: env-provides: key %s in [provides.env] would be dropped by the guard; prefix it with one "
                    "of %s (the only prefixes the guard.env parser in bundles/core/guard/engine.sh accepts)"
                    % (b.name, key, ", ".join(prefixes)))


# ----------------------------------------------------------------- rule-guard-pairing

_NN_TOPIC_RE = re.compile(r"^(?P<nn>[0-9][0-9])-(?P<topic>.+)\.(md|sh)$")


def _nn_topics(rels: Sequence[str]) -> List[Tuple[str, str, str]]:
    out = []
    for rel in rels:
        m = _NN_TOPIC_RE.match(os.path.basename(rel))
        if m:
            out.append((m.group("nn"), m.group("topic"), rel))
    return out


def mentions_topic(text: str, topic: str) -> bool:
    """``topic`` (``github-closing``) appears in ``text`` as a word, hyphens or spaces between parts."""
    pat = r"[- ]".join(re.escape(w) for w in topic.split("-") if w)
    return bool(pat) and re.search(r"(?<![A-Za-z0-9])%s(?![A-Za-z0-9])" % pat, text, re.I) is not None


def lint_rule_guard_pairing(b: M.Bundle, rep: Report) -> None:
    """A ``rules/NN-x.md`` without a ``guard.d/NN-*.sh`` (and vice versa), unless coverage_note names x."""
    if b.origin != "public":
        return
    note = str(b.harness.get("coverage_note") or "")
    rules, guards = _nn_topics(b.rules()), _nn_topics(b.guard_rules())
    rule_nn = {nn for nn, _t, _r in rules}
    guard_nn = {nn for nn, _t, _r in guards}
    for nn, topic, rel in rules:
        if nn not in guard_nn and not mentions_topic(note, topic):
            rep.warn("%s: rule-guard-pairing: %s has no guard.d/%s-*.sh enforcing it; add that guard section with "
                     "test rows, or name %r in [harness].coverage_note and say why it is guide-only"
                     % (b.name, rel, nn, topic))
    for nn, topic, rel in guards:
        if nn not in rule_nn and not mentions_topic(note, topic):
            rep.warn("%s: rule-guard-pairing: %s has no rules/%s-*.md telling the agent the rule up front; add that "
                     "rule, or name %r in [harness].coverage_note and say where its rule text lives"
                     % (b.name, rel, nn, topic))


# ----------------------------------------------------------------- permissions-vs-guard


def _bash_permission_prefixes(b: M.Bundle) -> Dict[str, List[str]]:
    """``{"allow": [prefix, ...], "deny": [...]}`` from the bundle's ``Bash(<prefix>:*)`` rules."""
    from . import toml_compat

    rel = b.permissions_file()
    if not rel or not os.path.isfile(b.rel(rel)):
        return {}
    try:
        perms = (toml_compat.load_file(b.rel(rel)).get("permissions") or {})
    except Exception:
        return {}  # the manifest pass reports unreadable files
    out: Dict[str, List[str]] = {}
    for kind in ("allow", "deny"):
        for rule in perms.get(kind) or []:
            m = _BASH_RULE_RE.match(str(rule))
            if m and "{{" not in m.group("prefix"):
                out.setdefault(kind, []).append(m.group("prefix").strip())
    return out


def _guard_members(b: M.Bundle, bundles: Dict[str, M.Bundle], engine: M.Bundle) -> List[M.Bundle]:
    """The engine's bundle, ``b`` and ``b``'s depends_on closure."""
    seen: Set[str] = set()
    stack = [b.name]
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        stack.extend(d for d in bundles[n].depends_on if d in bundles)
    return [bundles[n] for n in sorted(seen | {engine.name})]


def _guard_test_env(engine: M.Bundle, tmp: str) -> Dict[str, str]:
    """os.environ without guard-prefixed keys, plus the stubs and an empty HARNESS_GUARD_ENV."""
    drop = tuple(GUARD_ENV_PREFIXES_FALLBACK) + ("GIT_STUB_",)
    env = {k: v for k, v in os.environ.items() if not k.startswith(drop)}
    stubs = engine.rel("guard", "tests", "stubs")
    if os.path.isdir(stubs):
        for var, stub in GUARD_STUBS:
            if os.path.isfile(os.path.join(stubs, stub)):
                env[var] = os.path.join(stubs, stub)
        env["PATH"] = stubs + os.pathsep + env.get("PATH", "")
    empty = os.path.join(tmp, "guard.env")
    with open(empty, "w", encoding="utf-8"):
        pass
    env["HARNESS_GUARD_ENV"] = empty
    return env


def guard_decision(guard: str, command: str, cwd: str, env: Dict[str, str]) -> Tuple[str, str]:
    """(allow | ask | deny | pass | error, reason) of the guard script for one shell command."""
    payload = json.dumps({"tool_name": "Bash", "cwd": cwd, "tool_input": {"command": command}})
    try:
        proc = subprocess.run(["bash", guard], input=payload.encode("utf-8"), stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, cwd=cwd, env=env, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return "error", str(exc)
    out = proc.stdout.decode("utf-8", "replace").strip()
    if not out:
        return "pass", ""
    try:
        hso = json.loads(out.splitlines()[-1]).get("hookSpecificOutput") or {}
    except (ValueError, AttributeError):
        return "error", out[:200]
    return str(hso.get("permissionDecision") or "pass"), str(hso.get("permissionDecisionReason") or "")


def _guard_culprit(engine: M.Bundle, sections: Sequence[Tuple[str, str, str]], command: str, decision: str,
                   cwd: str, env: Dict[str, str], path: str) -> str:
    """The first section whose prefix of the guard reproduces ``decision``."""
    for i in range(len(sections) + 1):
        with open(path, "wb") as fh:
            fh.write(R.build_guard_from_sections(engine, sections[:i]))
        if guard_decision(path, command, cwd, env)[0] == decision:
            return "the engine" if i == 0 else "section %s (bundle %s)" % (sections[i - 1][0], sections[i - 1][1])
    return "the guard"


def lint_permissions_vs_guard(hub: Any, rep: Report) -> None:
    """Run the guard (engine + core + the bundle) on every ``Bash(<prefix>:*)`` allow/deny rule."""
    import shutil
    import tempfile
    from concurrent.futures import ThreadPoolExecutor

    bundles = [hub.bundles[n] for n in sorted(hub.bundles)]
    engine = R.find_guard_engine(bundles)
    if engine is None:
        return
    if not which("jq"):
        rep.warn("permissions-vs-guard: skipped: jq is not on PATH and the guard denies everything without it; "
                 "install jq, or pass --skip permissions-vs-guard")
        return
    tmp = tempfile.mkdtemp(prefix="harness-lint-guard-")
    try:
        cwd = os.path.join(tmp, "repo")
        os.makedirs(cwd)
        env = _guard_test_env(engine, tmp)
        jobs: List[Tuple[M.Bundle, str, str, str, List[Tuple[str, str, str]]]] = []
        for b in bundles:
            rules = _bash_permission_prefixes(b)
            if not rules:
                continue
            try:
                sections = R.guard_sections(_guard_members(b, hub.bundles, engine))
            except HarnessError:
                continue  # a missing section file is a manifest error already
            path = os.path.join(tmp, "guard-%s.sh" % b.name)
            with open(path, "wb") as fh:
                fh.write(R.build_guard_from_sections(engine, sections))
            for kind in ("allow", "deny"):
                for prefix in rules.get(kind, []):
                    jobs.append((b, kind, prefix, path, sections))
        workers = max(1, min(8, os.cpu_count() or 2))
        with ThreadPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(lambda j: guard_decision(j[3], j[2] + " x", cwd, env), jobs))
        culprit_path = os.path.join(tmp, "culprit.sh")
        for (b, kind, prefix, _path, sections), (dec, reason) in zip(jobs, results):
            command = prefix + " x"
            rel = b.permissions_file()
            if dec == "error":
                rep.warn("%s: permissions-vs-guard: the guard failed on `%s` (Bash(%s:*) in %s): %s; run the guard "
                         "suite (bin/harness test guard) to see why" % (b.name, command, prefix, rel, reason))
                continue
            if kind == "allow" and dec in ("deny", "ask"):
                by = _guard_culprit(engine, sections, command, dec, cwd, env, culprit_path)
                rep.err("%s: permissions-vs-guard: allow-listed command `%s` (Bash(%s:*) in %s) is %s by guard %s: "
                        "%s; fix one of them: narrow or drop the allow rule, or change the guard row (and its test "
                        "row)" % (b.name, command, prefix, rel, "denied" if dec == "deny" else "asked", by, reason))
            elif kind == "deny" and dec == "allow":
                by = _guard_culprit(engine, sections, command, dec, cwd, env, culprit_path)
                rep.err("%s: permissions-vs-guard: deny-listed command `%s` (Bash(%s:*) in %s) is allowed by guard "
                        "%s: %s; fix one of them: drop the deny rule, or make the guard deny it too (with a test row)"
                        % (b.name, command, prefix, rel, by, reason))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ----------------------------------------------------------------- agent-tools


def lint_agent_tools(b: M.Bundle, rep: Report) -> None:
    """Agent front matter vs the taxonomy posture and the model policy."""
    from . import taxonomy as T

    try:
        comps = T.components(b)
    except HarnessError:
        return  # reported by the taxonomy rule
    public = b.origin == "public"
    tax = b.taxonomy or {}
    where = "%s: agent-tools:" % b.name
    for c in comps:
        if c.kind != "agent":
            continue
        meta, _b = R.split_front_matter(read_text(b.rel(c.ref)) or "")
        if c.posture == "read-only":
            mode = meta.get("permissionMode")
            if mode in ("auto", "acceptEdits", "bypassPermissions"):
                raise_bundle = T.posture_rank("local") > T.posture_rank(tax.get("posture"))
                rep.warn("%s %s has posture read-only but its front matter sets permissionMode: %s; "
                         "set posture = \"local\" in components.%r%s or remove permissionMode"
                         % (where, c.id, mode, c.key, " (and raise taxonomy.posture on the bundle)" if raise_bundle else ""))
            tools = [t.strip().strip("'\"") for t in meta.get("tools", "").strip("[]").split(",")]
            writes = [t for t in tools if t in WRITE_TOOLS]
            if public and writes:
                rep.warn("%s %s has posture read-only but its front matter tools: lists %s; remove them (a read-only "
                         "agent reports, it does not edit) or set posture = \"local\" in components.%r"
                         % (where, c.id, ", ".join(writes), c.key))
        raw = (meta.get("model") or "").strip()
        if public and raw:
            m = T._MODEL_POLICY_RE.match(raw)
            if not m or m.group(1) not in ("plan", "execute"):
                rep.err("%s %s has a hard-coded model %r; use {{ core.model_policy.plan|execute }} (plan for "
                        "design-only agents, execute for the rest) so the configured model policy applies"
                        % (where, c.id, raw))


# ----------------------------------------------------------------- skill-description


def ci_templater(hub: Any) -> R.Templater:
    """A templater over tests/fixtures/harness.ci.toml with every public bundle's defaults."""
    from .hub import Hub

    ci = os.path.join(hub.home, CI_CONFIG)
    names = sorted(n for n, b in hub.bundles.items() if b.origin == "public")
    for selection in (names, ["core"] if "core" in names else []):
        try:
            h = Hub(home=hub.home, config_path=ci, bundles=selection or None, require_config=False)
            return R.Templater(h.template_context())
        except Exception:
            continue
    return R.Templater({})


def lint_skill_description(b: M.Bundle, tpl: R.Templater, rep: Report) -> None:
    """Length, trigger phrase and (workflow skills) negative scope + argument-hint of a SKILL.md description."""
    from . import taxonomy as T

    if b.origin != "public":
        return
    try:
        functions = {c.key: c.function for c in T.components(b) if c.kind == "skill"}
    except HarnessError:
        functions = {}
    for rel in b.skills():
        path = b.rel(rel, "SKILL.md")
        if not os.path.isfile(path):
            continue
        text = read_text(path) or ""
        meta, _body = R.split_front_matter(text)
        name = os.path.basename(rel.rstrip("/"))
        where = "%s: skill-description: skill %s" % (b.name, name)
        desc = " ".join(tpl.expand(T._description(text), "%s/SKILL.md" % rel).split())
        tpl.missing = []
        n = len(desc)
        if n < DESCRIPTION_MIN:
            rep.warn("%s: description is %d chars, under the %d-char minimum; say what the skill does and when to "
                     "use it" % (where, n, DESCRIPTION_MIN))
        elif n > DESCRIPTION_MAX:
            rep.warn("%s: description is %d chars after template expansion, over the %d-char limit (providers "
                     "truncate or reject longer ones); move detail into the SKILL.md body and keep the trigger list "
                     "and scope" % (where, n, DESCRIPTION_MAX))
        if not TRIGGER_RE.search(desc):
            rep.warn("%s: description has no trigger phrase; add a sentence starting \"Use when ...\" that lists "
                     "what the user says or does" % where)
        if functions.get(T.component_id(rel)) == "workflow":
            if not NEGATIVE_SCOPE_RE.search(desc):
                rep.warn("%s: workflow skill description has no negative scope; add \"NOT for ...\" naming the "
                         "requests another skill handles" % where)
            if "argument-hint" not in meta:
                rep.warn("%s: workflow skill has no argument-hint in its front matter; add one "
                         "(e.g. argument-hint: <KEY> [--flag])" % where)


# ----------------------------------------------------------------- fragments-target


def fragment_skills(b: M.Bundle) -> List[str]:
    """Skill names the bundle's ``skill-fragments/<skill>/`` entries and files target."""
    out = set()
    for pat in b.provides.get("skill_fragments") or []:
        parts = str(pat).split("/")
        if len(parts) >= 2 and parts[0] == "skill-fragments" and parts[1] and not re.search(r"[*?\[]", parts[1]):
            out.add(parts[1])
    for skill, _inner, _rel in b.skill_fragment_files():
        out.add(skill)
    return sorted(out)


def lint_fragments_target(b: M.Bundle, all_bundles: Dict[str, M.Bundle], rep: Report) -> None:
    skills = fragment_skills(b)
    if not skills:
        return
    related = list(dict.fromkeys(b.depends_on + b.recommends + [n for g in b.any_of for n in g]))
    owners = set()
    for n in related:
        if n in all_bundles:
            owners |= {os.path.basename(rel.rstrip("/")) for rel in all_bundles[n].skills()}
    for s in skills:
        if s not in owners:
            rep.err("%s: fragments-target: skill-fragments/%s/ targets skill %r, which no bundle in depends_on, "
                    "recommends or any_of provides (%s); add the owning bundle to depends_on or recommends, or fix "
                    "the directory name" % (b.name, s, s, ", ".join(related) or "none declared"))
    if b.origin == "public":
        rep.warn("%s: fragments-target: public bundle ships skill fragments (%s); prefer references inside the "
                 "owning skill; fragments are for org overlays (private bundles)"
                 % (b.name, ", ".join("skill-fragments/%s/" % s for s in skills)))


# ----------------------------------------------------------------- profile-sane


def lint_profiles(hub: Any, rep: Report, home: Optional[str] = None) -> None:
    """Every profile under ``<home>/profiles`` (default: the hub's) names public bundles and providers
    that exist and resolve together (depends_on closure, conflicts_with, any_of)."""
    home = home or hub.home
    public = {n: b for n, b in hub.bundles.items() if b.origin == "public"}
    for prof in M.list_profiles(home):
        where = "profiles/%s.toml: profile-sane:" % prof
        try:
            data = M.load_profile(home, prof)
        except Exception as exc:
            rep.err("profile-sane: %s" % exc)
            continue
        bundles = list(data.get("bundles", []))
        bad = False
        for n in bundles:
            if n not in hub.bundles:
                bad = True
                rep.err("%s unknown bundle %s; use one of: %s" % (where, n, ", ".join(sorted(public))))
            elif n not in public:
                bad = True
                rep.err("%s bundle %s is not public; a profile names public bundles only (select org bundles in "
                        "local/harness.toml)" % (where, n))
        for n in data.get("providers", []):
            if n not in hub.providers:
                rep.err("%s unknown provider %s; use one of: %s" % (where, n, ", ".join(sorted(hub.providers))))
        if not bad:
            try:
                M.resolve(bundles, public)
            except HarnessError as exc:
                rep.err("%s %s" % (where, exc))


# ----------------------------------------------------------------- stability


def _has_suite(path: str) -> bool:
    for dirpath, _dirs, files in os.walk(path):
        if "run.sh" in files and os.path.basename(dirpath) == "tests":
            return True
    return False


def lint_stability(b: M.Bundle, rep: Report) -> None:
    """``stability = "stable"`` needs a test suite for every skill and CLI (CONTRIBUTING "Stability levels")."""
    if (b.data.get("bundle") or {}).get("stability") != "stable":
        return
    where = "%s: stability:" % b.name
    note = " ".join(str(b.harness.get("coverage_note") or "").split())
    m = NO_SUITE_RE.search(note)
    if m:
        rep.warn("%s [harness].coverage_note admits a missing suite (%r); %s" % (where, m.group(0), STABLE_HINT))
    checked = set()
    for rel in b.skills():
        rel = rel.rstrip("/")
        checked.add(rel)
        if os.path.isdir(b.rel(rel)) and not _has_suite(b.rel(rel)):
            rep.warn("%s skill %s has no scripts/tests/run.sh; %s" % (where, rel, STABLE_HINT))
    for name, target in b.bins():
        parts = target.split("/")
        home = "/".join(parts[:2]) if parts[0] == "skills" and len(parts) > 2 else os.path.dirname(target)
        if home in checked:
            continue
        checked.add(home)
        if not (_has_suite(b.rel(home)) if home else False) and not os.path.isfile(b.rel("tests", "run.sh")):
            rep.warn("%s CLI %s (%s) has no tests/run.sh; %s" % (where, name, target, STABLE_HINT))


def shell_files(home: str) -> List[str]:
    """The scripts the dependency rule scans (sorted, relative to ``home``)."""
    import glob

    out = set()
    for pat in ("bin/*", "bootstrap", "bundles/**/*.sh", "providers/**/*.sh", "tools/gate/*.sh"):
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


def run_lint(hub: Any, skip: Sequence[str] = ()) -> Report:
    rep = Report()
    home = hub.home
    bschema = M.load_schema("bundle.schema.json", home)
    pschema = M.load_schema("provider.schema.json", home)
    schema = hub.schema
    used: Set[str] = set()
    on = lambda rule: rule not in skip  # noqa: E731
    prefixes = resolve_env_prefixes(hub, rep) if on("env-provides") else []
    tpl = ci_templater(hub) if on("skill-description") else None
    for name in sorted(hub.bundles):
        b = hub.bundles[name]
        used |= lint_bundle(b, hub.bundles, schema, bschema, rep, hub.providers)
        if on("env-provides"):
            lint_env_provides(b, prefixes, rep)
        if on("rule-guard-pairing"):
            lint_rule_guard_pairing(b, rep)
        if on("agent-tools"):
            lint_agent_tools(b, rep)
        if tpl is not None:
            lint_skill_description(b, tpl, rep)
        if on("fragments-target"):
            lint_fragments_target(b, hub.bundles, rep)
        if on("stability"):
            lint_stability(b, rep)
    if on("permissions-vs-guard"):
        lint_permissions_vs_guard(hub, rep)
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
    if on("profile-sane"):
        lint_profiles(hub, rep)
    if on("dependencies"):
        lint_dependencies(hub, rep)
    gate = os.path.join(home, "tools", "gate", "private-ids.sh")
    if os.path.isfile(gate) and os.environ.get("HARNESS_LINT_SKIP_GATE") != "1" and on("private-ids"):
        rc, out, err = run_argv(["bash", gate, "--ci"], timeout=300, cwd=home)
        if rc == 1:
            lines = [ln for ln in (out + err).splitlines() if ln.strip()][:20]
            rep.err("private-identifier gate failed:\n    " + "\n    ".join(lines))
        elif rc not in (0, 1):
            rep.warn("private-identifier gate could not run (rc=%d): %s" % (rc, (err or out).strip()[:200]))
    return rep


def run(ctx: Any, skip: Sequence[str] = ()) -> int:
    import sys

    from .hub import Hub

    unknown = [r for r in skip if r not in SKIPPABLE_RULES]
    if unknown:
        print("harness lint: --skip %s: not a skippable rule; use one of: %s"
              % (", ".join(unknown), ", ".join(SKIPPABLE_RULES)), file=sys.stderr)
        return 2
    hub = Hub(home=ctx.home, config_path=ctx.config, require_config=False, select=False)
    rep = run_lint(hub, skip)
    if hub.selection_error:
        rep.warn("config %s: %s" % (hub.config_path, hub.selection_error))
    for w in rep.warnings:
        print("WARN  %s" % w)
    for e in rep.errors:
        print("FAIL  %s" % e)
    print("lint: %d bundle(s), %d provider(s): %d error(s), %d warning(s)" % (
        len(hub.bundles), len(hub.providers), len(rep.errors), len(rep.warnings)))
    return 1 if rep.errors else 0
