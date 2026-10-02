"""Component taxonomy: stable ids and a small controlled vocabulary (docs/reference/taxonomy.md).

Every component a bundle ships (rule, skill, agent, guard section, permission list, MCP
server, CLI, installer, doctor check, manual step), every bundle, provider and profile is
classified the same way:

* **id** — derived from the path, never declared: ``<bundle>/<kind-dir>/<name>`` with the
  extension stripped (``k8s/agents/k8s-triage``, ``core/guard.d/30-git``,
  ``core/permissions``); bundles are bare (``k8s``); ``providers/<p>``, ``profiles/<p>``.
* **declared facets** — ``domain``, ``function``, ``posture``, only in the bundle's
  ``[taxonomy]`` table (bundle defaults plus ``[taxonomy.components]`` overrides keyed by the
  id without the ``<bundle>/`` prefix). Nothing goes into provider-format front matter.
* **derived facets** — ``kind`` (path), ``control`` (``[harness]`` guides/sensors), ``model``
  (front matter ``model:``), ``decisions`` (``# rule:`` comments, permission lists), bundle
  ``functions``, profile ``domains``/``posture``, provider ``tier`` and per-kind ``reach``.

The vocabulary below is the single source: ``schema/bundle.schema.json`` repeats the enums
literally (a unit test keeps them equal), ``harness lint`` (rule ``taxonomy``) enforces them,
``harness docs generate`` renders them, ``harness catalog`` lists every component.
"""
from __future__ import annotations

import os
import re
from collections import OrderedDict
from typing import Any, Dict, List, Optional

from .util import HarnessError, read_text

# catalog order
KINDS = ("bundle", "skill", "agent", "rule", "guard", "permission", "mcp", "bin", "installer",
         "doctor", "step", "provider", "profile")

KIND_TITLES = OrderedDict([
    ("bundle", "Bundles"), ("skill", "Skills"), ("agent", "Agents"), ("rule", "Rules"),
    ("guard", "Guard sections"), ("permission", "Permission lists"), ("mcp", "MCP servers"),
    ("bin", "CLIs"), ("installer", "Installers"), ("doctor", "Doctor checks"),
    ("step", "Manual steps"), ("provider", "Providers"), ("profile", "Profiles"),
])

# kind -> directory segment of its id (bundle components only)
KIND_DIR = OrderedDict([
    ("rule", "rules"), ("skill", "skills"), ("agent", "agents"), ("guard", "guard.d"),
    ("permission", "permissions"), ("mcp", "mcp"), ("bin", "bin"), ("installer", "install"),
    ("doctor", "doctor"), ("step", "steps"),
])
DIR_KIND = {v: k for k, v in KIND_DIR.items()}

FACETS: Dict[str, "OrderedDict[str, str]"] = {
    "domain": OrderedDict([
        ("base", "the harness itself: engine, credentials, conventions, core agents"),
        ("scm", "source hosts, branches, MRs/PRs"),
        ("tracker", "tickets, issues, their state"),
        ("delivery", "ticket-to-merge workflow spanning tracker and SCM"),
        ("kubernetes", "clusters, Helm, GitOps, IaC targeting them"),
        ("workspace", "docs, drive, sheets, mail"),
    ]),
    "function": OrderedDict([
        ("govern", "constrains the agent and says what to do instead"),
        ("client", "thin interface to one system"),
        ("workflow", "multi-step governed procedure"),
        ("investigate", "diagnoses to a root cause, never applies the fix"),
        ("plan", "designs; read-only"),
        ("execute", "implements autonomously"),
        ("review", "assesses and reports"),
        ("setup", "installs, verifies or configures once"),
    ]),
    "posture": OrderedDict([
        ("read-only", "reads only"),
        ("local", "edits the checkout and its own branches; other remote writes pass the guard"),
        ("label-gated", "writes promptlessly only to agent-* artefacts; human ones ask"),
    ]),
}
FACET_ORDER = ("kind", "control", "domain", "function", "posture", "model", "decisions")
POSTURE_ORDER = tuple(FACETS["posture"])

# kinds whose function is fixed (never declared differently)
KIND_FUNCTION = {
    "rule": "govern", "guard": "govern", "permission": "govern",
    "bin": "client", "mcp": "client",
    "installer": "setup", "doctor": "setup", "step": "setup",
}
# kinds whose function is declared (bundle default or component override)
DECLARED_FUNCTION_KINDS = ("skill", "agent")
# kinds whose posture is declared (bundle default or component override)
POSTURE_KINDS = ("skill", "agent", "bin", "mcp")
# kinds whose posture is fixed
KIND_POSTURE = {"doctor": "read-only"}
# why a kind takes no posture (lint message)
NO_POSTURE_REASON = {
    "rule": "a rule is text; its decisions are made by the guard sections that enforce it",
    "guard": "its decisions are derived from its # rule: comments",
    "permission": "its decisions are derived from the allow/ask/deny lists in permissions.toml",
    "installer": "it has no write behaviour beyond installing its tool",
    "step": "a human performs the step",
    "doctor": "doctor checks are always read-only",
}
# kinds whose control facet comes from [harness]
CONTROL_KINDS = ("skill", "agent", "rule", "guard", "permission", "doctor")

RESERVED_BUNDLE_NAMES = ("providers", "profiles")

# what each kind reaches, by status.MATRIX_ROWS label (guard: the provider tier); REACH_TEXT
# holds the kinds that do not depend on a provider capability
REACH_ROW = {"rule": "instructions", "skill": "skills", "agent": "agents", "guard": "guard hook (tier)",
             "permission": "permission lists", "mcp": "mcp"}
REACH_TEXT = {
    "bundle": "selected in `[hub].bundles` or through a profile; rendered into every active provider.",
    "bin": "provider-independent: linked into `~/.local/bin`, callable by every provider and by you.",
    "installer": "provider-independent: run by `harness install <tool>`.",
    "doctor": "provider-independent: run by `harness doctor`.",
    "step": "provider-independent: done once by a human; `harness steps --pending` lists the open ones.",
    "provider": "the tier: enforced (guard hook with ask), partial (guard hook, ask mapped), advisory (no hook).",
    "profile": "a named bundle and provider selection: `[hub].profile` or `harness bootstrap --profile`.",
}

_MODEL_POLICY_RE = re.compile(r"^\{\{\s*core\.model_policy\.([a-z_]+)\s*\}\}$")
_NN_RE = re.compile(r"^([0-9][0-9])-")


# ----------------------------------------------------------------- ids


def component_id(ref: str) -> str:
    """Normalise a bundle-relative ref to the component key used in ids and overrides.

    ``agents/x.md`` -> ``agents/x``, ``guard.d/30-git.sh`` -> ``guard.d/30-git``,
    ``permissions.toml`` -> ``permissions``, ``skills/k8s/`` -> ``skills/k8s``,
    ``install/gh.sh`` -> ``install/gh``.
    """
    ref = ref.strip().rstrip("/")
    if ref.startswith("./"):
        ref = ref[2:]
    if os.path.basename(ref) == "permissions.toml":
        return "permissions"
    head, _sep, tail = ref.rpartition("/")
    tail = re.sub(r"\.(md|sh|py|toml)$", "", tail)
    return "%s/%s" % (head, tail) if head else tail


def kind_of_key(key: str) -> Optional[str]:
    """``agents/x`` -> ``agent``; ``permissions`` -> ``permission``; unknown -> None."""
    if key == "permissions":
        return "permission"
    return DIR_KIND.get(key.split("/", 1)[0]) if "/" in key else None


def posture_rank(p: Optional[str]) -> int:
    return POSTURE_ORDER.index(p) if p in POSTURE_ORDER else -1


# ----------------------------------------------------------------- components


class Component:
    """One classified component of a bundle."""

    def __init__(self, bundle: str, kind: str, key: str, ref: str):
        self.bundle = bundle
        self.kind = kind
        self.key = key                        # id without the "<bundle>/" prefix
        self.id = "%s/%s" % (bundle, key)
        self.ref = ref                        # bundle-relative path, or the doctor/step id
        self.domain: Optional[str] = None
        self.function: Optional[str] = None
        self.posture: Optional[str] = None
        self.control: Optional[str] = None
        self.model: Optional[str] = None
        self.decisions: Optional[str] = None
        self.note: str = ""
        self.summary: str = ""
        self.stability: str = ""

    def sort_key(self) -> tuple:
        if self.kind in ("rule", "guard"):
            m = _NN_RE.match(self.key.split("/", 1)[1])
            return (m.group(1) if m else "99", self.id)
        return ("", self.id)

    @property
    def blurb(self) -> str:
        """The summary, or the ``[harness]`` / override note when there is none."""
        return self.summary or self.note

    def badges(self, skip: tuple = ("kind",)) -> str:
        parts = []
        for f in FACET_ORDER:
            v = getattr(self, f)
            if v and f not in skip:
                parts.append("%s: %s" % (f, v))
        return " · ".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = OrderedDict()
        for k in ("id", "kind", "bundle", "ref", "control", "domain", "function", "posture", "model",
                  "decisions", "stability", "summary", "note"):
            out[k] = getattr(self, k)
        return out


def _description(text: str) -> str:
    """The front matter ``description`` (handles ``>-`` / ``|`` folded scalars)."""
    from .render import split_front_matter

    meta, _body = split_front_matter(text)
    desc = meta.get("description", "")
    if desc in (">", ">-", ">+", "|", "|-", "|+"):
        lines = text.split("\n")
        out: List[str] = []
        grab = False
        for line in lines[1:]:
            if line.strip() == "---":
                break
            if grab:
                if line.startswith((" ", "\t")):
                    out.append(line.strip())
                    continue
                break
            if line.startswith("description:"):
                grab = True
        desc = " ".join(out)
    return desc


def first_sentence(text: str, limit: int = 160) -> str:
    text = " ".join(str(text).split())
    m = re.search(r"[.!?](?=\s+[A-Z(`]|$)", text)
    s = text[:m.start() + 1] if m else text
    if len(s) > limit:
        s = s[:limit - 1].rstrip() + "…"
    return s


def _model(meta: Dict[str, str]) -> Optional[str]:
    raw = (meta.get("model") or "").strip()
    if not raw:
        return None
    m = _MODEL_POLICY_RE.match(raw)
    return m.group(1) if m else raw


def guard_decisions(text: str) -> str:
    from .lint import RULE_LINE_RE

    counts = {"deny": 0, "ask": 0, "allow": 0}
    total = 0
    for line in text.splitlines():
        m = RULE_LINE_RE.match(line.strip())
        if m:
            total += 1
            if m.group("dec") in counts:
                counts[m.group("dec")] += 1
    if not total:
        return "helper (no rules)"
    parts = ["%s %d" % (k, counts[k]) for k in ("deny", "ask", "allow") if counts[k]]
    return " · ".join(parts) or "pass/defer only (%d rules)" % total


def permission_decisions(path: str) -> str:
    from . import toml_compat

    try:
        data = toml_compat.load_file(path)
    except (OSError, toml_compat.TOMLDecodeError):
        return ""
    perms = data.get("permissions", {}) or {}
    counts = {k: len(perms.get(k) or []) for k in ("deny", "ask", "allow")}
    if not sum(counts.values()):
        return "empty (no rules)"
    return " · ".join("%s %d" % (k, counts[k]) for k in ("deny", "ask", "allow") if counts[k])


def _mcp_summary(b: Any, server: str) -> str:
    """``runs `<command> <args>`` for one ``[servers.<name>]`` table of the MCP file."""
    from . import toml_compat

    try:
        spec = (toml_compat.load_file(b.rel(b.mcp_file())).get("servers") or {}).get(server) or {}
    except (OSError, toml_compat.TOMLDecodeError):
        return ""
    cmd = " ".join([str(spec.get("command", ""))] + [str(a) for a in spec.get("args") or []]).strip()
    return "runs `%s`" % cmd if cmd else ""


def _controls(b: Any) -> Dict[str, str]:
    """component key -> control facet, from ``[harness]``."""
    out: Dict[str, List[str]] = {}
    doctor_keys = ["doctor/%s" % c.get("id") for c in b.doctor_checks]
    for side, entries in (("guide", b.guides), ("sensor", b.sensors)):
        for e in entries:
            kind, ref = e.get("kind", ""), e.get("ref", "")
            if side == "sensor" and kind == "doctor":
                keys = doctor_keys if ref == "doctor_checks" else ["doctor/%s" % ref]
            elif kind in ("test", "lint"):
                continue
            elif kind == "permission" or (ref and ref == b.permissions_file()):
                keys = ["permissions"]
            else:
                keys = [component_id(ref)]
            label = "sensor (inferential)" if kind == "review-agent" else side
            for k in keys:
                if label not in out.setdefault(k, []):
                    out[k].append(label)
    return {k: " + ".join(v) for k, v in out.items()}


def _notes(b: Any) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for e in b.guides + b.sensors:
        if e.get("kind") in ("test", "lint", "doctor"):
            continue
        k = component_id(e.get("ref", ""))
        if e.get("note") and k not in out:
            out[k] = e["note"]
    return out


def raw_components(b: Any) -> List[Component]:
    """Every component of ``b`` with only ids, kinds and refs filled in."""
    out: List[Component] = []

    def add(kind: str, key: str, ref: str) -> None:
        out.append(Component(b.name, kind, key, ref))

    for rel in b.rules():
        add("rule", component_id(rel), rel)
    for rel in b.skills():
        add("skill", component_id(rel), rel)
    for rel in b.agents():
        add("agent", component_id(rel), rel)
    for rel in b.guard_rules():
        add("guard", component_id(rel), rel)
    perm = b.permissions_file()
    if perm:
        add("permission", "permissions", perm)
    for name in b.mcp_servers():
        add("mcp", "mcp/%s" % name, b.mcp_file() or "")
    for name, target in b.bins():
        add("bin", "bin/%s" % name, target)
    for rel in b.installers():
        add("installer", component_id(rel), rel)
    for c in b.doctor_checks:
        add("doctor", "doctor/%s" % c.get("id", ""), c.get("id", ""))
    for s in b.manual_steps:
        add("step", "steps/%s" % s.get("id", ""), s.get("id", ""))
    return out


def components(b: Any) -> List[Component]:
    """Every component of ``b``, classified: kind defaults -> bundle ``[taxonomy]`` -> override."""
    tax = b.taxonomy or {}
    overrides = tax.get("components") or {}
    controls = _controls(b)
    notes = _notes(b)
    stability = (b.data.get("bundle", {}) or {}).get("stability", "")
    checks = {c.get("id"): c for c in b.doctor_checks}
    steps = {s.get("id"): s for s in b.manual_steps}
    out = raw_components(b)
    for c in out:
        cls = overrides.get(c.key) or {}
        c.stability = stability
        c.domain = cls.get("domain") or tax.get("domain")
        if c.kind in KIND_FUNCTION:
            c.function = KIND_FUNCTION[c.kind]
        else:
            c.function = cls.get("function") or tax.get("function")
        if c.kind in KIND_POSTURE:
            c.posture = KIND_POSTURE[c.kind]
        elif c.kind in POSTURE_KINDS:
            c.posture = cls.get("posture") or tax.get("posture")
        if c.kind in CONTROL_KINDS:
            c.control = controls.get(c.key)
        c.note = cls.get("note") or notes.get(c.key, "")
        if c.kind in ("skill", "agent"):
            path = b.rel(c.ref, "SKILL.md") if c.kind == "skill" else b.rel(c.ref)
            text = read_text(path) or ""
            from .render import split_front_matter

            meta, _body = split_front_matter(text)
            c.model = _model(meta)
            c.summary = first_sentence(_description(text))
        elif c.kind == "rule":
            for line in (read_text(b.rel(c.ref)) or "").splitlines():
                m = re.match(r"^#{1,6}\s+(.+)$", line)
                if m:
                    c.summary = m.group(1).strip()
                    break
        elif c.kind == "guard":
            c.decisions = guard_decisions(read_text(b.rel(c.ref)) or "")
        elif c.kind == "permission":
            c.decisions = permission_decisions(b.rel(c.ref))
        elif c.kind == "mcp":
            c.summary = _mcp_summary(b, c.key.split("/", 1)[1])
        elif c.kind == "doctor":
            c.summary = (checks.get(c.ref) or {}).get("title", "")
        elif c.kind == "step":
            c.summary = (steps.get(c.ref) or {}).get("title", "")
    return out


# ----------------------------------------------------------------- bundles, providers, profiles


def _ordered(values: Any, facet: str) -> List[str]:
    order = list(FACETS[facet])
    return sorted(set(v for v in values if v), key=lambda v: order.index(v) if v in order else 99)


def bundle_entry(b: Any, comps: Optional[List[Component]] = None) -> Dict[str, Any]:
    comps = components(b) if comps is None else comps
    tax = b.taxonomy or {}
    return OrderedDict([
        ("id", b.name), ("kind", "bundle"), ("bundle", b.name), ("control", None),
        ("domain", tax.get("domain")), ("function", None), ("posture", tax.get("posture")),
        ("functions", _ordered((c.function for c in comps), "function")),
        ("stability", (b.data.get("bundle", {}) or {}).get("stability", "")),
        ("origin", b.origin), ("summary", b.summary),
    ])


def provider_tier(caps: Dict[str, Any]) -> str:
    if caps.get("hook_enforced"):
        return "enforced" if caps.get("ask") else "partial"
    return "advisory"


def provider_entry(p: Any) -> Dict[str, Any]:
    return OrderedDict([
        ("id", "providers/%s" % p.name), ("kind", "provider"), ("bundle", None), ("control", None),
        ("domain", None), ("function", None), ("posture", None),
        ("tier", provider_tier(p.capabilities)), ("summary", p.summary),
    ])


def profile_entry(home: str, name: str, bundles: Dict[str, Any]) -> Dict[str, Any]:
    from . import manifest as M

    prof = M.load_profile(home, name)
    known = [n for n in prof.get("bundles", []) if n in bundles]
    taxes = [bundles[n].taxonomy or {} for n in known]
    postures = [t.get("posture") for t in taxes if t.get("posture")]
    posture = max(postures, key=posture_rank) if postures else None
    return OrderedDict([
        ("id", "profiles/%s" % name), ("kind", "profile"), ("bundle", None), ("control", None),
        ("domains", _ordered((t.get("domain") for t in taxes), "domain")),
        ("domain", None), ("function", None), ("posture", posture),
        ("bundles", list(prof.get("bundles", []))), ("providers", list(prof.get("providers", []))),
        ("summary", prof.get("summary", "")),
    ])


def profile_entries(home: str, bundles: Dict[str, Any]) -> List[Dict[str, Any]]:
    from . import manifest as M

    out = []
    for name in M.list_profiles(home):
        try:
            out.append(profile_entry(home, name, bundles))
        except HarnessError:
            continue  # lint reports broken profiles
    return out


def reach_line(kind: str, providers: List[Any]) -> str:
    """One line: which providers a kind of component reaches, and how."""
    if kind in REACH_TEXT:
        return REACH_TEXT[kind]
    from .status import MATRIX_ROWS

    fn = provider_tier if kind == "guard" else dict(MATRIX_ROWS)[REACH_ROW[kind]]
    groups: "OrderedDict[str, List[str]]" = OrderedDict()
    for p in sorted(providers, key=lambda p: p.name):
        groups.setdefault(str(fn(p.capabilities)), []).append(p.name)
    if not groups:
        return "no providers discovered."
    if kind == "guard":
        tiers = ("enforced", "partial", "advisory")
        groups = OrderedDict(sorted(groups.items(), key=lambda kv: tiers.index(kv[0]) if kv[0] in tiers else 9))
    return "; ".join("%s on %s" % (v, ", ".join(names)) for v, names in groups.items()) + "."
