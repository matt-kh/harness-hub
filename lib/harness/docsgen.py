"""Generated documentation regions (ARCHITECTURE §8) and the harness.toml template.

A region is ``<!-- generated:begin source=S -->`` … ``<!-- generated:end -->``; everything
outside regions is hand-written and never touched. ``generate`` rewrites each expected
region (appending it when the page lacks it, creating the page with a one-line header when
the file does not exist); ``check`` computes the same and exits 1 listing stale pages.

Pages and sources:

* ``docs/bundles/<b>.md``            ``bundles/<b>/bundle.toml`` (public bundles only)
* ``docs/providers/<p>.md``          ``providers/<p>/provider.toml``
* ``docs/reference/config-schema.md`` ``schema/harness-config.schema.json`` (compiled with bundles)
* ``docs/reference/cli.md``           ``lib/harness/cli.py`` (argparse help, 100 columns)
* ``docs/reference/hook-policy.md``   ``bundles/*/guard.d`` (``# rule: <pattern> -> <decision> : <reason>``)
* ``docs/reference/secrets.md``       ``bundles/*/bundle.toml`` (every ``[requires.secrets]``)
* ``docs/reference/capability-matrix.md`` ``providers/*/provider.toml``
* ``docs/reference/harness-coverage.md`` ``bundles/*/bundle.toml#harness`` (guides × sensors per bundle)
* ``docs/reference/taxonomy.md``      ``lib/harness/taxonomy.py`` (facet values, facets and reach by kind)
* ``docs/catalog.md``                 ``bundles/*/bundle.toml#catalog`` (every component by kind) and
                                      ``bundles/*/bundle.toml#posture`` (domain × posture matrix)
* ``templates/harness.toml.tmpl``     whole file, from the compiled schema

Manual steps render as ``<a id="<id>"></a>`` + ``### <id> — <title>`` so that the doctor's
``docs/bundles/<b>.md#<id>`` links resolve on GitHub (whose own heading anchors differ).
Manifest strings are shown untemplated: docs are generic, ``{{ key }}`` tells the reader
which config key is substituted.
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
from contextlib import redirect_stdout
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import config as C
from . import manifest as M
from .util import HarnessError, atomic_write, read_text

RULE_RE = re.compile(r"^#\s*rule:\s*(?P<pat>.+?)\s+->\s+(?P<dec>allow|ask|deny|pass|defer)\s*:\s*(?P<reason>.+?)\s*$")
BEGIN_RE = re.compile(r"<!-- generated:begin source=(?P<src>\S+) -->\n?")
END = "<!-- generated:end -->"


# ----------------------------------------------------------------- region mechanics


def replace_region(text: Optional[str], source: str, body: str, header: str) -> str:
    """Return the page with the region for ``source`` set to ``body``."""
    block = "<!-- generated:begin source=%s -->\n%s%s" % (source, body if body.endswith("\n") or not body else body + "\n", END)
    if text is None:
        return "%s\n\n%s\n" % (header, block)
    pattern = re.compile(r"<!-- generated:begin source=%s -->\n?.*?<!-- generated:end -->" % re.escape(source), re.S)
    if pattern.search(text):
        return pattern.sub(lambda m: block, text, count=1)
    sep = "" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
    return text + sep + block + "\n"


def md_escape(s: Any) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ").strip()


def table(head: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    if not rows:
        return "_none_\n"
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    for r in rows:
        out.append("| " + " | ".join(md_escape(c) for c in r) + " |")
    return "\n".join(out) + "\n"


def code(s: Any) -> str:
    s = str(s)
    if not s:
        return ""
    fence = "``" if "`" in s else "`"
    return "%s%s%s" % (fence, s.replace("\n", " "), fence)


# ----------------------------------------------------------------- page bodies


def bundle_body(b: M.Bundle) -> str:
    out: List[str] = []
    out.append("## Summary\n")
    out.append("%s\n" % b.summary)
    if b.description.strip():
        out.append(b.description.strip() + "\n")
    meta = []
    for label, vals in (("Depends on", b.depends_on), ("Recommends", b.recommends), ("Conflicts with", b.conflicts_with)):
        if vals:
            meta.append("- **%s:** %s" % (label, ", ".join(code(v) for v in vals)))
    for grp in b.any_of:
        meta.append("- **Needs one of:** %s" % ", ".join(code(v) for v in grp))
    stab = b.data.get("bundle", {}).get("stability")
    if stab:
        meta.append("- **Stability:** %s" % stab)
    tax = b.taxonomy or {}
    if tax.get("domain") or tax.get("posture"):
        meta.append("- **Domain / posture:** %s / %s" % (tax.get("domain") or "unclassified",
                                                         tax.get("posture") or "unclassified"))
    if meta:
        out.append("\n".join(meta) + "\n")
    out.append(components_body(b))
    out.append("## Requirements\n")
    out.append("### Binaries\n")
    out.append(table(["binary", "min version", "install", "optional", "why"], [
        [code(n), s.get("min_version", ""), code("harness install %s" % s["install"]) if s.get("install") else "",
         "yes" if s.get("optional") else "no", s.get("why", "")]
        for n, s in sorted(b.requires_binaries.items())]))
    out.append("### Configuration\n")
    out.append(table(["key", "type", "required", "default", "description"], [
        [code(k), e.get("type", ""), "yes" if e.get("required") else "no",
         code(json.dumps(e["default"])) if "default" in e else "", e.get("description", "")]
        for k, e in sorted(b.requires_config.items())]))
    out.append("### Secrets (never in harness.toml)\n")
    out.append(table(["id", "where", "written by", "mode", "rotate"], [
        [code(i), code(s.get("where", "")), s.get("written_by", ""), s.get("mode", ""), s.get("rotate", "")]
        for i, s in sorted(b.requires_secrets.items())]))
    out.append("## Manual steps\n")
    if not b.manual_steps:
        out.append("_none_\n")
    for s in b.manual_steps:
        sid = s.get("id", "")
        out.append('<a id="%s"></a>\n' % sid)
        out.append("### %s — %s\n" % (sid, s.get("title", "")))
        meta = []
        if s.get("once_per"):
            meta.append("once per %s" % s["once_per"])
        needs = s.get("needs") or []
        meta.append("needs %s" % (", ".join(needs) if needs else "nothing but a terminal"))
        if s.get("minutes") is not None:
            meta.append("~%s min" % s["minutes"])
        out.append("*%s*\n" % " · ".join(meta))
        if s.get("why"):
            out.append("**Why:** %s\n" % " ".join(s["why"].split()))
        out.append("**How:**\n\n%s\n" % s.get("how", "").strip())
        v = s.get("verify") or {}
        if v.get("cmd"):
            exp = v.get("expect") or {}
            extra = []
            if "exit" in exp:
                extra.append("exit %s" % exp["exit"])
            if exp.get("stdout_regex"):
                extra.append("output matches %s" % code(exp["stdout_regex"]))
            out.append("**Verify:** %s%s\n" % (code(v["cmd"]), " (%s)" % ", ".join(extra) if extra else ""))
    out.append("## Doctor checks\n")
    steps = {s.get("id") for s in b.manual_steps}
    out.append(table(["id", "severity", "offline", "fix"], [
        [code(c.get("id", "")), c.get("severity", "fail"), "skipped" if c.get("offline_skip") else "runs",
         ("[%s](#%s)" % (c["fix"], c["fix"])) if c.get("fix") in steps else code(c.get("fix", ""))]
        for c in b.doctor_checks]))
    out.append(harness_body(b))
    out.append("## Uninstall\n")
    keeps = b.uninstall.get("keeps") or []
    out.append("Kept on uninstall: %s\n" % (", ".join(code(k) for k in keeps) if keeps else "_nothing_"))
    if b.uninstall.get("notes"):
        out.append("%s\n" % b.uninstall["notes"].strip())
    return "\n".join(out)


def components_body(b: M.Bundle) -> str:
    """The bundle's components with their ids and facets (taxonomy)."""
    from . import taxonomy as T

    comps = T.components(b)
    out = ["## Components\n"]
    out.append("Stable ids derived from the path, with their [taxonomy](../reference/taxonomy.md) facets "
               "(domain shown only where it differs from the bundle's). All bundles: [catalog](../catalog.md).\n")
    if not comps:
        out.append("_none_\n")
        return "\n".join(out)
    bundle_domain = (b.taxonomy or {}).get("domain")
    for kind in T.KINDS:
        group = sorted((c for c in comps if c.kind == kind), key=lambda c: c.sort_key())
        if not group:
            continue
        title = T.KIND_TITLES[kind]
        if kind in ("doctor", "step"):
            facets = "function: setup" + (" · posture: read-only" if kind == "doctor" else "")
            out.append("**%s** (%s; table below): %s\n" % (title, facets, ", ".join(code(c.id) for c in group)))
            continue
        lines = ["**%s**\n" % title]
        for c in group:
            badges = c.badges(("kind", "domain") if c.domain == bundle_domain else ("kind",))
            lines.append("- %s — %s" % (code(c.id), badges) if badges else "- %s" % code(c.id))
        out.append("\n".join(lines) + "\n")
    return "\n".join(out)


def _rel_docs(path: str) -> str:
    """A docs/… path relative to docs/ (where catalog.md lives)."""
    return path[len("docs/"):] if path.startswith("docs/") else "../" + path


def catalog_body(bundles: Sequence[M.Bundle], providers: Sequence[M.Provider], home: str) -> str:
    """``docs/catalog.md``: every bundle, component, provider and profile by kind."""
    from . import taxonomy as T

    comps = [c for b in bundles for c in T.components(b)]
    docs = {b.name: _rel_docs(b.docs_path()) for b in bundles}
    out: List[str] = []
    for kind in T.KINDS:
        out.append("## %s\n" % T.KIND_TITLES[kind])
        out.append("**Reach:** %s\n" % T.reach_line(kind, list(providers)))
        group = sorted((c for c in comps if c.kind == kind), key=lambda c: c.sort_key())
        if kind == "bundle":
            rows = []
            for b in bundles:
                e = T.bundle_entry(b, [c for c in comps if c.bundle == b.name])
                rows.append(["[%s](%s#components)" % (code(b.name), docs[b.name]), e["domain"] or "", e["posture"] or "",
                             ", ".join(e["functions"]), e["stability"], b.summary])
            out.append(table(["id", "domain", "posture", "functions", "stability", "summary"], rows))
        elif kind in ("skill", "agent"):
            out.append(table(["id", "control", "domain", "function", "posture", "model", "summary"], [
                [code(c.id), c.control or "", c.domain or "", c.function or "", c.posture or "", c.model or "", c.blurb]
                for c in group]))
        elif kind == "rule":
            out.append(table(["id", "control", "domain", "summary"], [
                [code(c.id), c.control or "", c.domain or "", c.blurb] for c in group]))
        elif kind in ("guard", "permission"):
            ids = ["[%s](reference/hook-policy.md)" % code(c.id) if kind == "guard" else code(c.id) for c in group]
            out.append(table(["id", "control", "domain", "decisions", "note"], [
                [i, c.control or "", c.domain or "", c.decisions or "", c.blurb] for i, c in zip(ids, group)]))
        elif kind == "mcp":
            out.append(table(["id", "domain", "posture", "note"], [
                [code(c.id), c.domain or "", c.posture or "", c.blurb] for c in group]))
        elif kind == "bin":
            out.append(table(["id", "domain", "posture", "target"], [
                [code(c.id), c.domain or "", c.posture or "", code(c.ref)] for c in group]))
        elif kind == "installer":
            out.append(table(["id", "domain", "script"], [[code(c.id), c.domain or "", code(c.ref)] for c in group]))
        elif kind == "doctor":
            out.append(table(["id", "control", "domain", "title"], [
                ["[%s](%s#doctor-checks)" % (code(c.id), docs[c.bundle]), c.control or "", c.domain or "", c.blurb]
                for c in group]))
        elif kind == "step":
            out.append(table(["id", "domain", "title"], [
                ["[%s](%s#%s)" % (code(c.id), docs[c.bundle], c.ref), c.domain or "", c.blurb] for c in group]))
        elif kind == "provider":
            rows = []
            for p in providers:
                e = T.provider_entry(p)
                page = _rel_docs(p.data.get("provider", {}).get("docs") or "docs/providers/%s.md" % p.name)
                rows.append(["[%s](%s)" % (code(e["id"]), page), e["tier"], e["summary"]])
            out.append(table(["id", "tier", "summary"], rows))
        elif kind == "profile":
            rows = []
            for e in T.profile_entries(home, {b.name: b for b in bundles}):
                rows.append([code(e["id"]), ", ".join(e["domains"]), e["posture"] or "",
                             ", ".join(e["bundles"]), ", ".join(e["providers"]), e["summary"]])
            out.append(table(["id", "domains", "posture", "bundles", "providers", "summary"], rows))
    return "\n".join(out)


def posture_body(bundles: Sequence[M.Bundle]) -> str:
    """``docs/catalog.md#posture``: skills, agents, CLIs and MCP servers by domain × posture."""
    from . import taxonomy as T

    comps = [c for b in bundles for c in T.components(b) if c.kind in T.POSTURE_KINDS]
    rows = []
    for d in T.FACETS["domain"]:
        row = [d]
        for p in T.POSTURE_ORDER:
            ids = sorted(c.id for c in comps if c.domain == d and c.posture == p)
            row.append(", ".join(code(i) for i in ids) or "—")
        rows.append(row)
    return ("Skills, agents, CLIs and MCP servers by domain and posture (the strongest effect without a "
            "human prompt, weakest first).\n\n" + table(["domain"] + list(T.POSTURE_ORDER), rows))


def _facet_by_kind(kind: str) -> List[str]:
    from . import taxonomy as T

    shape = {"bundle": "`<bundle>`", "provider": "`providers/<name>`", "profile": "`profiles/<name>`",
             "permission": "`<bundle>/permissions`"}.get(kind) or "`<bundle>/%s/<name>`" % T.KIND_DIR[kind]
    control = "derived: `[harness]`" if kind in T.CONTROL_KINDS else "—"
    if kind == "bundle":
        domain, function, posture = "declared (required on public)", "derived: union", "declared (required on public)"
    elif kind == "profile":
        domain, function, posture = "derived: union", "—", "derived: max"
    elif kind == "provider":
        domain, function, posture = "—", "—", "— (tier instead)"
    else:
        domain = "inherited, overridable"
        function = ("fixed: %s" % T.KIND_FUNCTION[kind]) if kind in T.KIND_FUNCTION else "declared (required)"
        posture = ("fixed: %s" % T.KIND_POSTURE[kind] if kind in T.KIND_POSTURE
                   else "declared (required)" if kind in T.POSTURE_KINDS else "not allowed")
    model = "derived: front matter" if kind in ("skill", "agent") else "—"
    decisions = ("derived: `# rule:` comments" if kind == "guard" else "derived: allow/ask/deny lists"
                 if kind == "permission" else "—")
    return [kind, shape, control, domain, function, posture, model, decisions]


def vocabulary_body(bundles: Sequence[M.Bundle], providers: Sequence[M.Provider]) -> str:
    """``docs/reference/taxonomy.md``: facet values with their meaning and use, facets and reach by kind."""
    from . import taxonomy as T

    comps = [c for b in bundles for c in T.components(b)]
    out: List[str] = []
    for facet, values in T.FACETS.items():
        out.append("### %s\n" % facet)
        rows = []
        for v, meaning in values.items():
            using = [c for c in comps if getattr(c, facet) == v]
            where = sorted(set(c.bundle for c in using))
            rows.append([code(v), meaning, "%d (%s)" % (len(using), ", ".join(where)) if using else "0"])
        out.append(table(["value", "meaning", "components using it"], rows))
    out.append("### Facets by kind\n")
    out.append(table(["kind", "id", "control", "domain", "function", "posture", "model", "decisions"],
                     [_facet_by_kind(k) for k in T.KINDS]))
    out.append("### Reach by kind\n")
    out.append(table(["kind", "reach"], [[k, T.reach_line(k, list(providers))] for k in T.KINDS]))
    return "\n".join(out)


GUIDE_KINDS = ("rule", "skill", "permission", "agent", "template")
SENSOR_KINDS = ("guard", "doctor", "test", "lint", "review-agent")


def harness_body(b: M.Bundle) -> str:
    """The bundle's ``[harness]``: guides (feedforward) and sensors (feedback)."""
    out = ["## Guides and sensors\n"]
    status = b.pairing()
    if status == "undeclared":
        out.append("_This bundle declares no `[harness]` section._\n")
        return "\n".join(out)
    out.append("Guides steer the agent before it acts; sensors detect at or after the action. "
               "Pairing: **%s**.\n" % status)
    rows = [["guide", e.get("kind", ""), code(e.get("ref", "")), e.get("note", "")] for e in b.guides]
    rows += [["sensor", e.get("kind", ""), code(e.get("ref", "")), e.get("note", "")] for e in b.sensors]
    out.append(table(["side", "kind", "ref", "note"], rows))
    if b.harness.get("coverage_note"):
        out.append("**Not covered:** %s\n" % " ".join(str(b.harness["coverage_note"]).split()))
    return "\n".join(out)


def coverage_body(bundles: Sequence[M.Bundle]) -> str:
    rows = []
    for b in bundles:
        gk = sorted(set(e.get("kind", "") for e in b.guides), key=lambda k: GUIDE_KINDS.index(k) if k in GUIDE_KINDS else 99)
        sk = sorted(set(e.get("kind", "") for e in b.sensors), key=lambda k: SENSOR_KINDS.index(k) if k in SENSOR_KINDS else 99)
        rows.append(["[%s](../bundles/%s.md#guides-and-sensors)" % (b.name, b.name), len(b.guides), ", ".join(gk),
                     len(b.sensors), ", ".join(sk), b.pairing(),
                     " ".join(str(b.harness.get("coverage_note", "")).split())])
    return table(["bundle", "guides", "guide kinds", "sensors", "sensor kinds", "pairing", "not covered"], rows)


def provider_body(p: M.Provider) -> str:
    out = []
    out.append("**Verified against:** %s\n" % (p.verified or "unverified"))
    rows = []
    for name in ("instructions", "skills", "agents", "settings", "hooks", "permissions", "trust", "mcp"):
        t = p.targets.get(name)
        if t is None:
            rows.append([name, "", "not declared", ""])
            continue
        detail = []
        for k in ("owner_keys", "key", "table", "event", "matcher", "shim", "register", "register_path"):
            if t.get(k):
                v = t[k]
                detail.append("%s=%s" % (k, ", ".join(v) if isinstance(v, list) else v))
        if isinstance(t.get("register"), dict):
            detail = [d for d in detail if not d.startswith("register=")]
            detail.append("registers in %s [[%s]]" % (t["register"]["path"], t["register"]["table"]))
        if t.get("note"):
            detail.append(t["note"])
        rows.append([name, code(t.get("path", "")), t.get("mode", ""), "; ".join(detail)])
    out.append("### Targets\n")
    out.append(table(["artifact", "path", "mode", "details"], rows))
    out.append("### Capabilities\n")
    caps = p.capabilities
    out.append(table(["capability", "value"], [[k, json.dumps(caps[k]) if isinstance(caps[k], bool) else caps[k]]
                                               for k in sorted(caps)]))
    return "\n".join(out)


def config_body(schema: Dict[str, Any]) -> str:
    rows = []
    for key, sub in sorted(C.schema_leaf_keys(schema).items()):
        typ = sub.get("type", "")
        if isinstance(typ, list):
            typ = " or ".join(typ)
        if typ == "object" and isinstance(sub.get("additionalProperties"), dict):
            typ = "table of %s" % (sub["additionalProperties"].get("type") or "tables")
        desc = sub.get("description", "")
        if sub.get("deprecated"):
            desc = "**Deprecated**%s. %s" % (", use %s" % code(sub["x-replaced-by"]) if sub.get("x-replaced-by") else "", desc)
        default = code(json.dumps(sub["default"])) if "default" in sub else ""
        rows.append([code(key), typ, default, sub.get("x-bundle", ""), desc])
    return ("Environment override for any key: `HARNESS_<SECTION>_<KEY>` "
            "(e.g. `HARNESS_JIRA_URL`).\n\n" + table(["key", "type", "default", "bundle", "description"], rows))


def cli_body() -> str:
    from . import cli

    old = os.environ.get("COLUMNS")
    old_nc = os.environ.get("NO_COLOR")
    os.environ["COLUMNS"] = "100"
    os.environ["NO_COLOR"] = "1"  # python 3.14 colourises help on a tty
    try:
        parser = cli.build_parser()
        parts = ["### harness\n", "```text\n%s```\n" % _help(parser)]
        sub = [a for a in parser._actions if a.__class__.__name__ == "_SubParsersAction"][0]
        for name, _h in cli.COMMANDS:
            sp = sub.choices[name]
            parts.append("### harness %s\n" % name)
            parts.append("```text\n%s```\n" % _help(sp))
            nested = [a for a in sp._actions if a.__class__.__name__ == "_SubParsersAction"]
            for n in nested:
                for sname, ssp in n.choices.items():
                    parts.append("#### harness %s %s\n" % (name, sname))
                    parts.append("```text\n%s```\n" % _help(ssp))
    finally:
        for k, v in (("COLUMNS", old), ("NO_COLOR", old_nc)):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return "\n".join(parts)


def _help(parser: Any) -> str:
    text = parser.format_help()
    # python 3.10 renamed "optional arguments:" to "options:"; normalise for stable docs
    text = text.replace("optional arguments:", "options:")
    return re.sub(r"[ \t]+\n", "\n", text)


def hook_rules(bundles: Sequence[M.Bundle]) -> List[Tuple[str, str, str, str, str]]:
    rows = []
    for b in bundles:
        for rel in sorted(b.guard_rules(), key=lambda r: os.path.basename(r)):
            text = read_text(b.rel(rel)) or ""
            for line in text.splitlines():
                m = RULE_RE.match(line.strip())
                if m:
                    rows.append((os.path.basename(rel), b.name, m.group("pat"), m.group("dec"), m.group("reason")))
    rows.sort(key=lambda r: (r[0], r[1]))
    return rows


def hook_body(bundles: Sequence[M.Bundle]) -> str:
    rows = [[s, b, code(p), d, r] for s, b, p, d, r in hook_rules(bundles)]
    return table(["section", "bundle", "pattern", "decision", "reason"], rows)


def secrets_body(bundles: Sequence[M.Bundle]) -> str:
    rows = []
    for b in bundles:
        for sid, s in sorted(b.requires_secrets.items()):
            rows.append([code(sid), b.name, code(s.get("where", "")), s.get("written_by", ""), s.get("mode", ""),
                         s.get("rotate", ""), s.get("description", "")])
    return table(["secret", "bundle", "where", "written by", "mode", "rotate", "notes"], rows)


def matrix_body(providers: Sequence[M.Provider]) -> str:
    from .status import matrix_rows

    rows = matrix_rows(list(providers))
    return table(rows[0], rows[1:])


# ----------------------------------------------------------------- template


def _placeholder(sub: Dict[str, Any]) -> Optional[str]:
    from . import toml_compat

    # a commented default documents the real behaviour; an example is only a placeholder
    if "default" in sub:
        return toml_compat.dump_value(sub["default"])
    if sub.get("examples"):
        return toml_compat.dump_value(sub["examples"][0])
    typ = sub.get("type")
    return {"string": '""', "array": "[]", "boolean": "false", "integer": "0", "number": "0"}.get(typ if isinstance(typ, str) else "")


def template_text(schema: Dict[str, Any], bundle_names: Sequence[str]) -> str:
    """``templates/harness.toml.tmpl``: every key, commented, tagged with its bundle.

    Line forms consumed by ``harness init``:
      ``#@ <bundles> <toml line>``  belongs to these bundles (comma separated); uncommented
                                    when one is selected and the key is required or has no
                                    default, otherwise emitted as a ``# `` comment
      ``@@EMAIL@@ @@BUNDLES@@ @@PROVIDERS@@``  filled in by init
      anything else                 copied verbatim
    """
    from . import toml_compat

    names = set(bundle_names)
    lines = [
        "# harness.toml - the single source of truth for your organisation- and person-specific values.",
        "# Generated from schema/ by `harness docs generate`; `harness init` fills it in.",
        "# Secrets NEVER go here (see docs/reference/secrets.md).",
        "# Validate: harness config validate    Explain a key: harness config explain jira.url",
        "schema_version = 1",
        "",
        "[identity]",
        "email = @@EMAIL@@",
        "",
        "[hub]",
        "bundles = @@BUNDLES@@",
        "providers = @@PROVIDERS@@",
        '# profile = "github-dev"                  # alternative to listing bundles; explicit lists win',
    ]
    skip_sections = {"schema_version", "identity", "hub", "kubernetes", "harness", "providers"}
    props = schema.get("properties", {})
    for section, sub in props.items():
        if section in skip_sections or not isinstance(sub, dict) or sub.get("deprecated"):
            continue
        leaves = template_leaves(sub, section)
        leaves = {k: v for k, v in leaves.items() if not v.get("deprecated")}
        if not leaves:
            continue
        section_owner = sub.get("x-bundle") or ""
        owners = sorted(set(_owner(k, v, names) or section_owner for k, v in leaves.items()) - {""})
        lines.append("")
        if sub.get("description"):
            lines.append("# %s" % sub["description"])
        header = "[%s]" % section
        lines.append(("#@ %s %s" % (",".join(owners), header)) if owners else header)
        subsections: Dict[str, List[str]] = {}
        for key, ls in sorted(leaves.items(), key=lambda kv: list(leaves).index(kv[0])):
            rel = key[len(section) + 1:]
            val = _placeholder(ls)
            desc = " ".join((ls.get("description") or "").split())
            if len(desc) > 90:
                desc = desc[:87].rstrip() + "..."
            if val is None or "\n" in val:
                lines.append("# %s: see docs/reference/config-schema.md (%s)" % (rel, desc))
                continue
            owner = _owner(key, ls, names) or section_owner
            req = "required" if key in _required_keys(schema) else ""
            has_default = "default" in ls
            tag = "!" if (req or not has_default) else ""
            line = "%s = %s" % (toml_compat.quote_key(rel) if "." not in rel else rel, val)
            comment = "  # %s%s" % (desc, " (required)" if req else "")
            if owner:
                lines.append("#@%s %s %s%s" % (tag, owner, line, comment if desc else ""))
            else:
                lines.append("%s%s%s" % ("" if tag else "# ", line, comment if desc else ""))
    lines.append("")
    lines.append("# Providers without an 'ask' decision map guard asks to deny (default) or allow.")
    lines.append("[providers.gemini]")
    lines.append('ask_as = "deny"')
    lines.append("[providers.copilot]")
    lines.append('ask_as = "deny"')
    return "\n".join(lines) + "\n"


def template_leaves(sub: Dict[str, Any], prefix: str) -> Dict[str, Dict[str, Any]]:
    """Leaf keys for the template: objects with a default/example are one inline-table leaf."""
    out: Dict[str, Dict[str, Any]] = {}
    for k, s in (sub.get("properties") or {}).items():
        key = "%s.%s" % (prefix, k)
        if (isinstance(s, dict) and s.get("type") == "object" and s.get("properties")
                and "default" not in s and not s.get("examples")):
            out.update(template_leaves(s, key))
        elif isinstance(s, dict):
            out[key] = s
    return out


def _owner(key: str, sub: Dict[str, Any], names: set) -> str:
    if sub.get("x-bundle"):
        return sub["x-bundle"]
    top = key.split(".")[0]
    return top if top in names else ""


def _required_keys(schema: Dict[str, Any]) -> set:
    out = set()

    def walk(node: Dict[str, Any], prefix: str) -> None:
        for r in node.get("required", []) or []:
            out.add("%s.%s" % (prefix, r) if prefix else r)
        for k, sub in (node.get("properties") or {}).items():
            if isinstance(sub, dict):
                walk(sub, "%s.%s" % (prefix, k) if prefix else k)

    walk(schema, "")
    return out


# ----------------------------------------------------------------- orchestration


def public_bundles(home: str) -> List[M.Bundle]:
    root = os.environ.get("HARNESS_BUNDLES_ROOT") or os.path.join(home, "bundles")
    found = M.discover_bundles([(root, "public")])
    return [found[n] for n in sorted(found) if not found[n].private]


def expected(home: str) -> Dict[str, List[Tuple[str, str, str]]]:
    """page path (relative) -> [(source, body, header)]."""
    bundles = public_bundles(home)
    providers_d = M.discover_providers([os.path.join(home, "providers")])
    providers = [providers_d[n] for n in sorted(providers_d)]
    base = C.load_base_schema(home)
    schema = C.compile_schema(base, bundles, [b.name for b in bundles])
    pages: Dict[str, List[Tuple[str, str, str]]] = {}
    for b in bundles:
        rel = b.docs_path()
        pages.setdefault(rel, []).append(("bundles/%s/bundle.toml" % b.name, bundle_body(b),
                                          "# Bundle: %s" % b.name))
    for p in providers:
        rel = p.data.get("provider", {}).get("docs") or "docs/providers/%s.md" % p.name
        pages.setdefault(rel, []).append(("providers/%s/provider.toml" % p.name, provider_body(p),
                                          "# Provider: %s" % p.name))
    ref = "docs/reference/"
    pages.setdefault(ref + "config-schema.md", []).append(
        ("schema/harness-config.schema.json", config_body(schema), "# Configuration reference"))
    pages.setdefault(ref + "cli.md", []).append(("lib/harness/cli.py", cli_body(), "# CLI reference"))
    pages.setdefault(ref + "hook-policy.md", []).append(("bundles/*/guard.d", hook_body(bundles), "# Hook policy"))
    pages.setdefault(ref + "secrets.md", []).append(("bundles/*/bundle.toml", secrets_body(bundles), "# Secrets"))
    pages.setdefault(ref + "capability-matrix.md", []).append(
        ("providers/*/provider.toml", matrix_body(providers), "# Capability matrix"))
    pages.setdefault(ref + "harness-coverage.md", []).append(
        ("bundles/*/bundle.toml#harness", coverage_body(bundles), "# Harness coverage"))
    pages.setdefault(ref + "taxonomy.md", []).append(
        ("lib/harness/taxonomy.py", vocabulary_body(bundles, providers), "# Taxonomy"))
    pages.setdefault("docs/catalog.md", []).extend([
        ("bundles/*/bundle.toml#catalog", catalog_body(bundles, providers, home), "# Catalog"),
        ("bundles/*/bundle.toml#posture", posture_body(bundles), "# Catalog"),
    ])
    return pages


def compute(home: str) -> Dict[str, str]:
    """Every generated file's full new content, keyed by path relative to ``home``."""
    out: Dict[str, str] = {}
    for rel, regions in sorted(expected(home).items()):
        text = read_text(os.path.join(home, rel))
        for source, body, header in regions:
            text = replace_region(text, source, body, header)
        out[rel] = text or ""
    bundles = public_bundles(home)
    schema = C.compile_schema(C.load_base_schema(home), bundles, [])
    out["templates/harness.toml.tmpl"] = template_text(schema, [b.name for b in bundles])
    return out


def run(ctx: Any, action: str) -> int:
    from .util import hub_home

    home = hub_home()
    new = compute(home)
    stale = []
    for rel, text in sorted(new.items()):
        cur = read_text(os.path.join(home, rel))
        if cur != text:
            stale.append(rel)
            if action == "generate" and not ctx.dry_run:
                atomic_write(os.path.join(home, rel), text.encode("utf-8"))
    if action == "check":
        for rel in stale:
            print("stale    %s" % rel)
        print("docs: %d stale of %d generated file(s)%s" % (len(stale), len(new), "" if not stale else " — run `harness docs generate`"))
        return 1 if stale else 0
    print("docs: %s %d of %d generated file(s)" % ("would update" if ctx.dry_run else "updated", len(stale), len(new)))
    for rel in stale:
        print("  %s" % rel)
    return 0
