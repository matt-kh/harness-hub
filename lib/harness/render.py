"""Render bundles x providers x config into in-memory targets, plus the merge algorithms.

Nothing here touches provider directories: :func:`render_hub` returns a list of
:class:`Target` objects (one per destination path) and the pure merge functions
(:func:`merge_managed_blocks`, :func:`merge_json`, :func:`merge_toml_blocks`) compute a new
file from the live content and the previous state. ``plan`` and ``apply`` drive them.

Templating (ARCHITECTURE §3)
    ``{{ section.key }}`` with exactly one space inside the braces and a lowercase dotted key
    (at least one dot) is the only syntax. It is expanded in ``rules/*.md``, ``agents/*.md``,
    every ``*.md`` under ``skills/`` and ``skill-fragments/``, and in manifest strings
    (``manual_steps`` ``title/why/how/verify.cmd``, ``doctor_checks`` ``cmd``,
    ``[provides.env]`` values, ``permissions.toml`` and ``mcp.toml`` strings).
    Scripts are copied verbatim. ``${{ … }}`` (GitHub Actions expressions) and ``\\{{ … }}``
    are left alone; the backslash of the escape is dropped. Values render as: strings
    verbatim, booleans ``true``/``false``, numbers ``str()``, arrays joined with ``", "``,
    tables as compact sorted JSON. A key with no value is a plan error listing every
    missing key with its file.

Determinism: every collection is sorted, JSON built here is dumped with sorted keys, files
end with a single LF, and no timestamps are rendered.
"""
from __future__ import annotations

import copy
import json
import os
import re
import shlex
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from . import toml_compat
from .config import get_path
from .manifest import Bundle, Provider
from .util import HarnessError, canonical_json, dump_json, expand, list_files, read_bytes, tilde

TEMPLATE_RE = re.compile(r"(?<![$\\])\{\{ ([a-z][a-z0-9_]*(?:\.[A-Za-z0-9_]+)+) \}\}")
ESCAPED_RE = re.compile(r"\\(\{\{ [a-z][a-z0-9_]*(?:\.[A-Za-z0-9_]+)+ \}\})")
HUB = "_hub"  # pseudo provider for provider-independent outputs (bin links)


class RenderError(HarnessError):
    pass


# ================================================================= templating


def format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return ", ".join(format_value(v) for v in value)
    if isinstance(value, dict):
        return canonical_json(value)
    return str(value)


class Templater:
    """Expands ``{{ key }}`` against a context; collects missing keys instead of raising."""

    def __init__(self, context: Dict[str, Any]):
        self.context = context
        self.missing: List[Tuple[str, str]] = []  # (where, key)

    def expand(self, text: str, where: str) -> str:
        def sub(m: "re.Match[str]") -> str:
            key = m.group(1)
            val = get_path(self.context, key, None)
            if val is None:
                self.missing.append((where, key))
                return m.group(0)
            return format_value(val)

        out = TEMPLATE_RE.sub(sub, text)
        return ESCAPED_RE.sub(r"\1", out)

    def expand_obj(self, obj: Any, where: str) -> Any:
        if isinstance(obj, str):
            return self.expand(obj, where)
        if isinstance(obj, list):
            return [self.expand_obj(v, where) for v in obj]
        if isinstance(obj, dict):
            return {k: self.expand_obj(v, where) for k, v in obj.items()}
        return obj

    def check(self) -> None:
        if self.missing:
            seen = []
            for where, key in self.missing:
                line = "%s: {{ %s }} has no value (set it in harness.toml or a bundle default)" % (where, key)
                if line not in seen:
                    seen.append(line)
            raise RenderError("template keys missing:\n  " + "\n  ".join(seen))


def template_keys(text: str) -> List[str]:
    return sorted(set(TEMPLATE_RE.findall(text)))


def is_templated_file(rel: str) -> bool:
    return rel.endswith(".md")


def split_front_matter(text: str) -> Tuple[Dict[str, str], str]:
    """Minimal YAML front-matter split (``key: value`` lines only) for inlined agents."""
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end < 0:
        return {}, text
    meta: Dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"').strip("'")
    body = text[end + 4:]
    return meta, body.lstrip("\n")


# ================================================================= targets


class Block:
    def __init__(self, bundle: str, file: str, body: str):
        self.bundle = bundle
        self.file = file
        self.body = body.rstrip("\n")

    @property
    def key(self) -> str:
        return "%s %s" % (self.bundle, self.file)


class Target:
    """Everything the engine wants at one destination path."""

    def __init__(self, path: str, provider: str, mode: str):
        self.path = path
        self.provider = provider
        self.mode = mode  # file | managed-block | json-merge | toml-block | symlink
        self.bundles: Set[str] = set()
        # file
        self.content: bytes = b""
        self.executable = False
        self.source: Optional[str] = None      # absolute source path (1:1 copies)
        self.templated = False
        self.unit: Optional[str] = None        # foreign-detection unit (skill dir)
        # managed-block
        self.blocks: List[Block] = []
        # json-merge
        self.fragment: Dict[str, Any] = {}
        self.owners: List[Tuple[Tuple[str, ...], str]] = []   # (path, deep|replace)
        self.sort_arrays: List[Tuple[str, ...]] = []
        self.exclusive: List[List[Tuple[str, ...]]] = []
        # toml-block
        self.tblocks: Dict[str, str] = {}
        # symlink
        self.link: str = ""

    @property
    def bundle_label(self) -> str:
        return ",".join(sorted(self.bundles)) or "_engine"

    def __repr__(self) -> str:  # pragma: no cover
        return "Target(%s, %s)" % (self.mode, tilde(self.path))


class TargetSet:
    """Collects targets; merges contributions that land on the same path."""

    def __init__(self) -> None:
        self.by_path: Dict[str, Target] = {}

    def get(self, path: str, provider: str, mode: str) -> Target:
        t = self.by_path.get(path)
        if t is None:
            t = Target(path, provider, mode)
            self.by_path[path] = t
            return t
        if t.mode != mode:
            raise RenderError("%s is rendered in two modes (%s and %s)" % (tilde(path), t.mode, mode))
        if t.provider != provider:
            raise RenderError("%s is rendered for two providers (%s and %s)" % (tilde(path), t.provider, provider))
        return t

    def add_file(self, path: str, provider: str, bundle: str, content: bytes, executable: bool = False,
                 source: Optional[str] = None, templated: bool = False, unit: Optional[str] = None) -> Target:
        if path in self.by_path:
            raise RenderError("%s is rendered twice (bundles %s and %s)" % (
                tilde(path), self.by_path[path].bundle_label, bundle))
        t = self.get(path, provider, "file")
        t.bundles.add(bundle)
        t.content = content
        t.executable = executable
        t.source = source
        t.templated = templated
        t.unit = unit
        return t

    def add_json(self, path: str, provider: str, bundle: str, dotted: Sequence[str], value: Any,
                 how: str = "deep") -> Target:
        t = self.get(path, provider, "json-merge")
        t.bundles.add(bundle)
        node = t.fragment
        for part in dotted[:-1]:
            node = node.setdefault(part, {})
        last = dotted[-1]
        if how == "deep" and isinstance(value, dict) and isinstance(node.get(last), dict):
            node[last] = _deep_union(node[last], value)
        elif how == "deep" and isinstance(value, list) and isinstance(node.get(last), list):
            node[last] = node[last] + [v for v in value if v not in node[last]]
        else:
            node[last] = value
        return t

    def targets(self) -> List[Target]:
        return [self.by_path[p] for p in sorted(self.by_path)]


def _deep_union(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(a)
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_union(out[k], v)
        elif isinstance(v, list) and isinstance(out.get(k), list):
            out[k] = out[k] + [x for x in v if x not in out[k]]
        else:
            out[k] = copy.deepcopy(v)
    return out


def dotted_tuple(s: str) -> Tuple[str, ...]:
    return tuple(p for p in s.split(".") if p)


# ================================================================= guard


def guard_sections(bundles: Iterable[Bundle]) -> List[Tuple[str, str, str]]:
    """(basename, bundle, absolute path) of every guard section, in concatenation order.

    Same ordering contract as ``bundles/core/guard/build.sh``: file basename in C byte
    order across all bundles, ties broken by bundle name; only ``NN-*.sh`` files.
    """
    rows = []
    for b in bundles:
        for rel in b.guard_rules():
            base = os.path.basename(rel)
            if not re.match(r"^[0-9][0-9]-.*\.sh$", base):
                continue
            full = b.rel(rel)
            if not os.path.isfile(full):
                raise RenderError("%s: provides guard rule %s which does not exist" % (b.name, rel))
            rows.append((base, b.name, full))
    rows.sort(key=lambda r: (r[0].encode("utf-8"), r[1].encode("utf-8")))
    return rows


def find_guard_engine(bundles: Sequence[Bundle]) -> Optional[Bundle]:
    for b in bundles:
        if os.path.isfile(b.rel("guard", "engine.sh")) and os.path.isfile(b.rel("guard", "engine-flush.sh")):
            return b
    return None


def build_guard(engine: Bundle, bundles: Iterable[Bundle]) -> bytes:
    """engine.sh + sections (sorted) + engine-flush.sh, byte-identical to build.sh."""
    parts: List[bytes] = [read_bytes(engine.rel("guard", "engine.sh")) or b""]
    for base, bname, full in guard_sections(bundles):
        parts.append(("\n# ==== section %s (bundle %s) ====\n" % (base, bname)).encode("utf-8"))
        parts.append(read_bytes(full) or b"")
    parts.append(b"\n# ==== flush ====\n")
    parts.append(read_bytes(engine.rel("guard", "engine-flush.sh")) or b"")
    return b"".join(parts)


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def guard_env(env: Dict[str, str]) -> bytes:
    lines = [
        "# guard.env - generated by `harness render`; do not edit (edit harness.toml instead).",
        "# Sourced by guard-bash.sh at start. Values are single-quoted shell words;",
        "# variables already set in the environment take precedence; empty values are omitted.",
    ]
    for k in sorted(env):
        if str(env[k]) == "":
            continue  # empty = unset: never mask a script's own default with ""
        lines.append("%s=%s" % (k, shell_quote(str(env[k]))))
    return ("\n".join(lines) + "\n").encode("utf-8")


# ================================================================= renderer


class Renderer:
    def __init__(self, hub: Any):
        self.hub = hub
        self.targets = TargetSet()
        self.notes: List[str] = []
        self.skill_homes: Dict[str, str] = {}  # skill name -> rendered dir of the primary provider

    # ---------------------------------------------------------------- public
    def render(self, providers: Sequence[Provider], include_hub: bool = True) -> List[Target]:
        bundles = self.hub.active_bundles
        self.env = self._compile_env(bundles)
        for p in providers:
            self._render_provider(p, bundles)
        if include_hub:
            self._render_hub_bins(bundles, providers)
        return self.targets.targets()

    # ---------------------------------------------------------------- env
    def _compile_env(self, bundles: Sequence[Bundle]) -> Dict[str, str]:
        tpl = Templater(self.hub.template_context())
        env: Dict[str, str] = {}
        owner: Dict[str, str] = {}
        for b in bundles:
            for k, v in b.env().items():
                val = format_value(tpl.expand_obj(v, "%s [provides.env].%s" % (b.name, k)))
                if k in env and env[k] != val:
                    raise RenderError("[provides.env].%s is set by %s (%r) and %s (%r)" % (
                        k, owner[k], env[k], b.name, val))
                env[k] = val
                owner[k] = b.name
        tpl.check()
        env["HARNESS_BUNDLES"] = " ".join(b.name for b in bundles)
        env["HARNESS_HOME"] = self.hub.home
        return env

    # ---------------------------------------------------------------- provider
    def _render_provider(self, p: Provider, bundles: Sequence[Bundle]) -> None:
        tpl = Templater(self.hub.template_context(p))
        self._instructions(p, bundles, tpl)
        self._skills(p, bundles, tpl)
        self._agents(p, bundles, tpl)
        self._hooks(p, bundles)
        self._permissions(p, bundles, tpl)
        self._trust(p)
        self._provider_settings(p)
        self._mcp(p, bundles, tpl)
        tpl.check()

    def _instructions(self, p: Provider, bundles: Sequence[Bundle], tpl: Templater) -> None:
        t = p.target("instructions")
        if not t:
            return
        path = expand(t["path"])
        blocks: List[Tuple[Tuple[int, bytes, bytes], Block]] = []
        for b in bundles:
            for rel in b.rules():
                src = b.rel(rel)
                text = _read_required(src, b, rel)
                body = tpl.expand(text, "%s/%s" % (b.name, rel))
                blocks.append(((0, os.path.basename(rel).encode(), b.name.encode()), Block(b.name, rel, body)))
        agents_t = p.targets.get("agents") or {}
        if agents_t.get("mode") == "inline":
            for b in bundles:
                for rel in b.agents():
                    text = _read_required(b.rel(rel), b, rel)
                    meta, body = split_front_matter(tpl.expand(text, "%s/%s" % (b.name, rel)))
                    name = meta.get("name") or os.path.splitext(os.path.basename(rel))[0]
                    head = "## Agent: %s\n\n" % name
                    if meta.get("description"):
                        head += "_%s_\n\n" % meta["description"]
                    blocks.append(((1, name.encode(), b.name.encode()), Block(b.name, rel, head + body)))
        if not blocks:
            return
        target = self.targets.get(path, p.name, "managed-block")
        for _, blk in sorted(blocks, key=lambda x: x[0]):
            target.blocks.append(blk)
            target.bundles.add(blk.bundle)

    def _skill_sources(self, bundles: Sequence[Bundle]) -> Dict[str, Tuple[Bundle, str]]:
        skills: Dict[str, Tuple[Bundle, str]] = {}
        for b in bundles:
            for rel in b.skills():
                name = os.path.basename(rel.rstrip("/"))
                if not os.path.isdir(b.rel(rel)):
                    raise RenderError("%s: provides skill %s which does not exist" % (b.name, rel))
                if name in skills:
                    raise RenderError("skill %r is provided by both %s and %s" % (name, skills[name][0].name, b.name))
                skills[name] = (b, rel)
        return skills

    def _skills(self, p: Provider, bundles: Sequence[Bundle], tpl: Templater) -> None:
        t = p.target("skills")
        if not t:
            return
        skills = self._skill_sources(bundles)
        fragments: Dict[str, List[Tuple[Bundle, str, str]]] = {}
        for b in bundles:
            for skill, inner, rel in b.skill_fragment_files():
                if skill not in skills:
                    continue  # owning bundle inactive: fragment not rendered
                fragments.setdefault(skill, []).append((b, inner, rel))
        rendered_dirs = []
        for name in sorted(skills):
            b, rel = skills[name]
            dest = expand(t["path"].replace("<name>", name))
            rendered_dirs.append(dest)
            if name not in self.skill_homes:
                self.skill_homes[name] = dest
            files: Dict[str, Tuple[Bundle, str]] = {}
            for f in list_files(b.rel(rel)):
                files[f.replace(os.sep, "/")] = (b, os.path.join(rel, f))
            for fb, inner, frel in fragments.get(name, []):
                files[inner] = (fb, frel)
            for inner in sorted(files):
                ob, orel = files[inner]
                src = ob.rel(orel)
                self._copy(p.name, ob, src, "%s/%s" % (ob.name, orel), os.path.join(dest, inner), tpl, unit=dest)
        reg = t.get("register")
        if reg and rendered_dirs:
            table = reg["table"]
            text = "".join(
                toml_compat.dump_table(table, {"path": d, "enabled": True}, array=True)
                for d in sorted(rendered_dirs))
            target = self.targets.get(expand(reg["path"]), p.name, "toml-block")
            target.tblocks["skills"] = text
            target.bundles.update(skills[n][0].name for n in skills)

    def _copy(self, provider: str, b: Bundle, src: str, where: str, dest: str, tpl: Templater,
              unit: Optional[str] = None) -> None:
        data = read_bytes(src)
        if data is None:
            raise RenderError("%s: missing source file" % where)
        templated = False
        if is_templated_file(src):
            text = data.decode("utf-8")
            new = tpl.expand(text, where)
            templated = new != text or bool(TEMPLATE_RE.search(text))
            data = new.encode("utf-8")
        executable = os.access(src, os.X_OK)
        self.targets.add_file(dest, provider, b.name, data, executable=executable, source=src,
                              templated=templated, unit=unit)

    def _agents(self, p: Provider, bundles: Sequence[Bundle], tpl: Templater) -> None:
        t = p.target("agents")
        if not t or t.get("mode") != "file":
            return
        for b in bundles:
            for rel in b.agents():
                stem = os.path.splitext(os.path.basename(rel))[0]
                dest = expand(t["path"].replace("<name>", stem))
                self._copy(p.name, b, b.rel(rel), "%s/%s" % (b.name, rel), dest, tpl)

    def _hooks(self, p: Provider, bundles: Sequence[Bundle]) -> None:
        t = p.target("hooks")
        if not t:
            return
        engine = find_guard_engine(bundles)
        if engine is None:
            if any(b.guard_rules() for b in bundles):
                raise RenderError("guard sections are active but no active bundle ships guard/engine.sh "
                                  "and guard/engine-flush.sh (normally bundles/core)")
            self.notes.append("%s: no guard engine among active bundles; hook not rendered" % p.name)
            return
        hooks_dir = expand(t["path"])
        guard_path = os.path.join(hooks_dir, "guard-bash.sh")
        g = self.targets.add_file(guard_path, p.name, engine.name, build_guard(engine, bundles), executable=True)
        g.bundles.update(b.name for b in bundles if b.guard_rules())
        env = dict(self.env)
        env["HARNESS_PROVIDER"] = p.name
        ask_supported = p.capabilities.get("ask", True)
        ask_as = None
        if not ask_supported:
            ask_as = self.hub.config.get("providers.%s.ask_as" % p.name) or "deny"
            env["HARNESS_ASK_AS"] = ask_as
        e = self.targets.add_file(os.path.join(hooks_dir, "guard.env"), p.name, engine.name, guard_env(env))
        e.bundles.update(b.name for b in bundles if b.env())
        shim = t.get("shim") or ""
        script = guard_path
        if shim:
            src = os.path.join(p.path, shim)
            data = read_bytes(src)
            if data is None:
                raise RenderError("provider %s: shim %s does not exist" % (p.name, shim))
            script = os.path.join(hooks_dir, os.path.basename(shim))
            self.targets.add_file(script, p.name, engine.name, data, executable=True, source=src)
        command = "bash %s" % script
        if ask_as is not None:
            command = "HARNESS_ASK_AS=%s %s" % (ask_as, command)
        entry_tpl = t.get("entry") or '{"matcher":"{matcher}","hooks":[{"type":"command","command":"{command}"}]}'
        entry_text = (entry_tpl.replace("{command}", _json_str(command))
                      .replace("{matcher}", _json_str(t.get("matcher", "")))
                      .replace("{event}", _json_str(t.get("event", ""))))
        try:
            entry = json.loads(entry_text)
        except ValueError as exc:
            raise RenderError("provider %s: targets.hooks.entry is not valid JSON after substitution: %s" % (p.name, exc))
        register = t.get("register", "settings")
        if register == "settings":
            st = p.target("settings")
            if not st:
                raise RenderError("provider %s: hooks.register = settings but no settings target" % p.name)
            self._settings_target(p, st)
            self.targets.add_json(expand(st["path"]), p.name, engine.name, ("hooks", t["event"]), [entry])
        else:
            path = expand(t["register_path"])
            self.targets.add_file(path, p.name, engine.name, dump_json(entry, sort_keys=True))

    def _settings_target(self, p: Provider, st: Dict[str, Any]) -> Target:
        path = expand(st["path"])
        target = self.targets.get(path, p.name, "json-merge")
        if not target.owners or not any(o for o in target.owners if o[1] == "deep"):
            for k in st.get("owner_keys", []):
                pair = (dotted_tuple(k), "deep")
                if pair not in target.owners:
                    target.owners.append(pair)
            target.sort_arrays = [dotted_tuple(s) for s in st.get("sort_arrays", [])]
            target.exclusive = [[dotted_tuple(s) for s in grp] for grp in st.get("exclusive", [])]
        return target

    def _into_settings(self, p: Provider, name: str) -> Optional[Tuple[Dict[str, Any], Tuple[str, ...]]]:
        t = p.target(name)
        if not t:
            return None
        st = p.target("settings")
        if not st:
            raise RenderError("provider %s: targets.%s writes into settings but there is no settings target" % (p.name, name))
        self._settings_target(p, st)
        return st, dotted_tuple(t["key"])

    def _permissions(self, p: Provider, bundles: Sequence[Bundle], tpl: Templater) -> None:
        dest = self._into_settings(p, "permissions")
        if not dest:
            return
        st, key = dest
        merged: Dict[str, List[str]] = {"allow": [], "ask": [], "deny": []}
        contributors: Set[str] = set()
        for b in bundles:
            rel = b.permissions_file()
            if not rel:
                continue
            data = _load_toml(b.rel(rel), b, rel)
            perms = tpl.expand_obj(data.get("permissions", {}), "%s/%s" % (b.name, rel))
            for kind in ("allow", "ask", "deny"):
                for rule in perms.get(kind, []) or []:
                    if rule not in merged[kind]:
                        merged[kind].append(rule)
                        contributors.add(b.name)
        # a rule in several lists: deny beats ask beats allow
        seen: Set[str] = set()
        for kind in ("deny", "ask", "allow"):
            merged[kind] = sorted(r for r in set(merged[kind]) if r not in seen)
            seen.update(merged[kind])
        value = {k: v for k, v in merged.items() if v}
        if not value:
            return
        t = self.targets.add_json(expand(st["path"]), p.name, sorted(contributors)[0], key, value)
        t.bundles.update(contributors)

    def _trust(self, p: Provider) -> None:
        dest = self._into_settings(p, "trust")
        if not dest:
            return
        st, key = dest
        lines = trust_environment(self.hub.config.get("trust", {}) or {})
        target = self.targets.add_json(expand(st["path"]), p.name, "_config", key, lines, how="replace")
        if (key, "replace") not in target.owners:
            target.owners.append((key, "replace"))

    def _provider_settings(self, p: Provider) -> None:
        extra = self.hub.config.get("providers.%s.settings" % p.name)
        if not extra:
            return
        st = p.target("settings")
        if not st:
            raise RenderError("providers.%s.settings is set but provider %s has no settings target" % (p.name, p.name))
        self._settings_target(p, st)
        owners = [dotted_tuple(k) for k in st.get("owner_keys", [])]
        for k, v in sorted(extra.items()):
            if not any(o and o[0] == k for o in owners):
                raise RenderError("providers.%s.settings.%s: only the owner keys %s can be set" % (
                    p.name, k, ", ".join(st.get("owner_keys", []))))
            self.targets.add_json(expand(st["path"]), p.name, "_config", (k,), copy.deepcopy(v))

    def _mcp(self, p: Provider, bundles: Sequence[Bundle], tpl: Templater) -> None:
        t = p.target("mcp")
        servers = self.collect_mcp(bundles, tpl)
        if not servers:
            return
        if not t:
            self.notes.append("%s: MCP servers not rendered (provider has no MCP target)" % p.name)
            return
        extra = t.get("entry") or {}
        path = expand(t["path"])
        if t["mode"] == "json-merge":
            key = dotted_tuple(t.get("key", "mcpServers"))
            for name in sorted(servers):
                bname, spec = servers[name]
                entry = dict(sorted(extra.items()))
                entry.update(mcp_entry(spec))
                target = self.targets.add_json(path, p.name, bname, key + (name,), entry, how="replace")
                pair = (key + (name,), "replace")
                if pair not in target.owners:
                    target.owners.append(pair)
        else:
            table = t.get("table", "mcp_servers")
            text = ""
            owners = set()
            for name in sorted(servers):
                bname, spec = servers[name]
                entry = dict(sorted(extra.items()))
                entry.update(mcp_entry(spec))
                text += toml_compat.dump_table("%s.%s" % (table, name), entry)
                owners.add(bname)
            target = self.targets.get(path, p.name, "toml-block")
            target.tblocks["mcp"] = text
            target.bundles.update(owners)

    def collect_mcp(self, bundles: Sequence[Bundle], tpl: Templater) -> Dict[str, Tuple[str, Dict[str, Any]]]:
        servers: Dict[str, Tuple[str, Dict[str, Any]]] = {}
        for b in bundles:
            rel = b.mcp_file()
            if not rel:
                continue
            data = _load_toml(b.rel(rel), b, rel)
            for name, spec in sorted((data.get("servers") or {}).items()):
                when = spec.get("when")
                if when is not None:
                    flag = self.hub.config.get(when) if isinstance(when, str) else when
                    if not flag:
                        continue
                if name in servers:
                    raise RenderError("MCP server %r is defined by %s and %s" % (name, servers[name][0], b.name))
                servers[name] = (b.name, tpl.expand_obj(spec, "%s/%s [servers.%s]" % (b.name, rel, name)))
        return servers

    # ---------------------------------------------------------------- hub bins
    def _render_hub_bins(self, bundles: Sequence[Bundle], providers: Sequence[Provider]) -> None:
        from .util import bin_dir, data_dir

        links: Dict[str, Tuple[str, str]] = {}
        harness_bin = os.path.join(self.hub.home, "bin", "harness")
        if os.path.exists(harness_bin):
            links["harness"] = (harness_bin, "_hub")
        for b in bundles:
            for name, rel in b.bins():
                parts = rel.split("/")
                target = None
                if parts[0] == "skills" and len(parts) >= 3:
                    home = self.skill_homes.get(parts[1])
                    if home:
                        target = os.path.join(home, *parts[2:])
                if target is None and parts[0] == "bin":
                    target = os.path.join(data_dir(), "bin", b.name, *parts[1:])
                    self.targets.add_file(target, HUB, b.name, read_bytes(b.rel(rel)) or b"",
                                          executable=True, source=b.rel(rel))
                if target is None:
                    target = b.rel(rel)  # no provider renders skills: link the hub source
                if name in links and links[name][1] != b.name:
                    raise RenderError("~/.local/bin/%s is exposed by both %s and %s" % (name, links[name][1], b.name))
                links[name] = (target, b.name)
        for name in sorted(links):
            target, bname = links[name]
            t = self.targets.get(os.path.join(bin_dir(), name), HUB, "symlink")
            t.link = target
            t.bundles.add(bname)


def _json_str(s: str) -> str:
    return json.dumps(s)[1:-1]


def _read_required(path: str, b: Bundle, rel: str) -> str:
    data = read_bytes(path)
    if data is None:
        raise RenderError("%s: provides %s which does not exist" % (b.name, rel))
    return data.decode("utf-8")


def _load_toml(path: str, b: Bundle, rel: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        raise RenderError("%s: provides %s which does not exist" % (b.name, rel))
    try:
        return toml_compat.load_file(path)
    except toml_compat.TOMLDecodeError as exc:
        raise RenderError("%s/%s: TOML syntax error: %s" % (b.name, rel, exc))


# ================================================================= MCP + trust


def mcp_entry(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Provider-neutral server entry. ``env_files`` become a ``bash -c`` wrapper that reads the
    secret at launch, so no token ever appears in a provider config file."""
    command = spec.get("command", "")
    args = [str(a) for a in spec.get("args", []) or []]
    env = {k: str(v) for k, v in sorted((spec.get("env") or {}).items())}
    files = spec.get("env_files") or {}
    out: Dict[str, Any] = {}
    if files:
        exports = "; ".join('export %s="$(cat %s)"' % (k, v) for k, v in sorted(files.items()))
        inner = " ".join([shlex.quote(command)] + [shlex.quote(a) for a in args])
        out["command"] = "bash"
        out["args"] = ["-c", "%s; exec %s" % (exports, inner)]
    else:
        out["command"] = command
        out["args"] = args
    out["env"] = env
    return out


def trust_environment(trust: Dict[str, Any]) -> List[str]:
    """Claude Code ``autoMode.environment`` lines from ``[trust]``.

    ``trust.environment`` (raw lines) wins verbatim when non-empty, so an organisation can
    reproduce a hand-tuned text exactly; otherwise a generic list is generated.
    """
    raw = trust.get("environment") or []
    if raw:
        return list(raw)

    def join(key: str) -> str:
        vals = trust.get(key) or []
        return ", ".join(vals) if vals else "None configured"

    lines = ["### Org-wide"]
    sc = trust.get("source_control") or []
    lines.append("**Source control**: %s" % (
        "trusted " + ", ".join(sc) + " — no other orgs configured" if sc else "None configured"))
    lines.append("**Trusted internal domains**: %s" % join("domains"))
    lines.append("**Trusted cloud buckets**: %s" % join("buckets"))
    lines.append("**Sensitive remote targets**: any namespace, host, or container whose name carries "
                 "`prod` or `production` as a whole word or name segment")
    notes = (trust.get("notes") or "").strip()
    if notes:
        lines.append("### User-specific")
        lines.extend(line.rstrip() for line in notes.splitlines() if line.strip())
    return lines


# ================================================================= merge: managed blocks

_BLOCK_RE = re.compile(
    r"<!-- harness:begin bundle=(?P<b>\S+) file=(?P<f>\S+) -->\n(?P<body>.*?)\n?"
    r"<!-- harness:end bundle=(?P=b) file=(?P=f) -->", re.S)


def block_text(blk: Block) -> str:
    return "<!-- harness:begin bundle=%s file=%s -->\n%s\n<!-- harness:end bundle=%s file=%s -->" % (
        blk.bundle, blk.file, blk.body, blk.bundle, blk.file)


def parse_blocks(text: str) -> List[Tuple[str, Any]]:
    """Split text into ("text", str) and ("block", (key, body)) segments."""
    segs: List[Tuple[str, Any]] = []
    pos = 0
    for m in _BLOCK_RE.finditer(text):
        if m.start() > pos:
            segs.append(("text", text[pos:m.start()]))
        segs.append(("block", ("%s %s" % (m.group("b"), m.group("f")), m.group("body"))))
        pos = m.end()
    if pos < len(text):
        segs.append(("text", text[pos:]))
    return segs


def body_sha(body: str) -> str:
    from .util import sha256_bytes

    return sha256_bytes(body.rstrip("\n").encode("utf-8"))


def merge_managed_blocks(live: Optional[str], blocks: Sequence[Block], prev: Dict[str, str],
                         adopt: bool = False) -> Tuple[str, Dict[str, str], List[str]]:
    """Insert/replace/remove harness blocks; text outside blocks is kept byte for byte.

    ``prev`` maps block key -> body sha recorded at the last apply. A block whose live body
    differs from both ``prev`` and the new render was edited by hand: the user wins (kept,
    reported as a conflict) unless ``adopt``.
    """
    desired = {b.key: b for b in blocks}
    order = [b.key for b in blocks]
    conflicts: List[str] = []
    state: Dict[str, str] = {}
    if not live:
        text = "\n\n".join(block_text(b) for b in blocks) + "\n" if blocks else ""
        return text, {b.key: body_sha(b.body) for b in blocks}, conflicts
    segs = parse_blocks(live)
    out: List[List[Any]] = []
    placed: Set[str] = set()
    for kind, val in segs:
        if kind == "text":
            out.append(["text", val])
            continue
        key, body = val
        if key in placed:
            conflicts.append("block %s appears twice; the second copy is removed" % key)
            continue
        if key in desired:
            new = desired[key]
            live_sha = body_sha(body)
            if (live_sha != body_sha(new.body) and key in prev and live_sha != prev[key]
                    and not adopt):
                conflicts.append("block %s was edited outside the harness (kept; use sync --adopt or apply --adopt)" % key)
                out.append(["block", key, body])
                state[key] = prev[key]
            else:
                out.append(["block", key, new.body])
                state[key] = body_sha(new.body)
            placed.add(key)
        else:
            if key in prev and body_sha(body) != prev[key] and not adopt:
                conflicts.append("block %s is no longer rendered but was edited; kept" % key)
                out.append(["block", key, body])
                state[key] = prev[key]
                placed.add(key)
            else:
                # drop it and one separating newline
                out.append(["removed"])
    # insert missing blocks next to their ordered neighbours
    for i, key in enumerate(order):
        if key in placed:
            continue
        blk = desired[key]
        pos = None
        for prev_key in reversed(order[:i]):
            idx = _seg_index(out, prev_key)
            if idx is not None:
                pos = ("after", idx)
                break
        if pos is None:
            for next_key in order[i + 1:]:
                idx = _seg_index(out, next_key)
                if idx is not None:
                    pos = ("before", idx)
                    break
        seg = ["block", key, blk.body]
        if pos is None:
            out.append(["append", key, blk.body])
        elif pos[0] == "after":
            out[pos[1] + 1:pos[1] + 1] = [["text", "\n\n"], seg]
        else:
            out[pos[1]:pos[1]] = [seg, ["text", "\n\n"]]
        placed.add(key)
        state[key] = body_sha(blk.body)
    # serialise
    text = ""
    trim = False
    tail_removed = False  # a block was removed and no block follows it
    for seg in out:
        if seg[0] == "text":
            chunk = seg[1]
            if trim:
                t_nl = len(text) - len(text.rstrip("\n"))
                s_nl = len(chunk) - len(chunk.lstrip("\n"))
                keep = max(0, min(s_nl, 2 - t_nl)) if text else 0
                chunk = "\n" * keep + chunk[s_nl:]
                trim = False
            text += chunk
        elif seg[0] == "block":
            trim = tail_removed = False
            b, f = seg[1].split(" ", 1)
            text += block_text(Block(b, f, seg[2]))
        elif seg[0] == "removed":
            trim = tail_removed = True
        elif seg[0] == "append":
            trim = tail_removed = False
            b, f = seg[1].split(" ", 1)
            if text and not text.endswith("\n"):
                text += "\n"
            if text and not text.endswith("\n\n"):
                text += "\n"
            text += block_text(Block(b, f, seg[2])) + "\n"
    if tail_removed:
        text = text.rstrip("\n") + "\n" if text.strip() else ""
    if not text.strip():
        return "", state, conflicts
    if not text.endswith("\n"):
        text += "\n"
    return text, state, conflicts


def _seg_index(out: List[List[Any]], key: str) -> Optional[int]:
    for i, seg in enumerate(out):
        if seg[0] in ("block", "append") and seg[1] == key:
            return i
    return None


# ================================================================= merge: JSON


def _get(node: Any, path: Tuple[str, ...]) -> Any:
    for p in path:
        if not isinstance(node, dict) or p not in node:
            return _MISSING
        node = node[p]
    return node


_MISSING = object()


def _prune(node: Dict[str, Any], path: Tuple[str, ...]) -> None:
    """Remove empty containers along ``path`` (deepest first)."""
    for depth in range(len(path), 0, -1):
        sub = _get(node, path[:depth])
        if sub is _MISSING or not isinstance(sub, (dict, list)) or sub:
            continue
        parent = _get(node, path[:depth - 1]) if depth > 1 else node
        if isinstance(parent, dict):
            parent.pop(path[depth - 1], None)


def unapply_owned(live: Dict[str, Any], owned: Sequence[Dict[str, Any]]) -> None:
    """Remove the contributions recorded at the last apply that are still unchanged."""
    for rec in owned:
        path = tuple(rec["path"])
        cur = _get(live, path)
        if cur is _MISSING:
            continue
        if "items" in rec:
            if isinstance(cur, list):
                for item in rec["items"]:
                    c = canonical_json(item)
                    for i, x in enumerate(cur):
                        if canonical_json(x) == c:
                            del cur[i]
                            break
        elif "value" in rec:
            if canonical_json(cur) == canonical_json(rec["value"]):
                parent = _get(live, path[:-1]) if len(path) > 1 else live
                if isinstance(parent, dict):
                    parent.pop(path[-1], None)
        _prune(live, path)


def merge_json(live: Optional[Dict[str, Any]], target: Target, owned_prev: Sequence[Dict[str, Any]],
               adopt: bool = False) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[str]]:
    """Deep-merge ``target.fragment`` into ``live``; return (new doc, owned records, conflicts).

    Only paths under ``target.owners`` are touched. ``deep`` owners merge recursively
    (objects by key, arrays by value with de-duplication); ``replace`` owners are set
    wholesale (MCP servers). Scalars and replace-values that the user changed after the
    last apply, or that exist with a different value on first contact, are conflicts:
    the user's value is kept unless ``adopt``.
    """
    doc: Dict[str, Any] = copy.deepcopy(live) if isinstance(live, dict) else {}
    unapply_owned(doc, owned_prev)
    owned: List[Dict[str, Any]] = []
    conflicts: List[str] = []
    excl: Dict[Tuple[str, ...], List[Tuple[str, ...]]] = {}
    for grp in target.exclusive:
        for p in grp:
            excl[p] = [q for q in grp if q != p]

    def label(path: Tuple[str, ...]) -> str:
        return ".".join(path)

    def set_value(path: Tuple[str, ...], value: Any) -> None:
        node = doc
        for p in path[:-1]:
            if not isinstance(node.get(p), dict):
                node[p] = {}
            node = node[p]
        node[path[-1]] = copy.deepcopy(value)

    def leaf(path: Tuple[str, ...], value: Any, replace: bool) -> None:
        # a non-object on the way down belongs to the user
        for depth in range(1, len(path)):
            cur = _get(doc, path[:depth])
            if cur is not _MISSING and not isinstance(cur, dict):
                conflicts.append("%s: user value is not an object; kept" % label(path[:depth]))
                return
        cur = _get(doc, path)
        if cur is _MISSING:
            set_value(path, value)
            owned.append({"path": list(path), "value": copy.deepcopy(value)})
        elif canonical_json(cur) == canonical_json(value):
            if adopt:
                owned.append({"path": list(path), "value": copy.deepcopy(value)})
        elif adopt:
            set_value(path, value)
            owned.append({"path": list(path), "value": copy.deepcopy(value)})
        else:
            conflicts.append("%s: differs from the rendered value; user value kept (apply --adopt %s to take over)"
                             % (label(path), tilde(target.path)))

    def array(path: Tuple[str, ...], items: List[Any]) -> None:
        cur = _get(doc, path)
        if cur is _MISSING:
            set_value(path, [])
            cur = _get(doc, path)
        if not isinstance(cur, list):
            conflicts.append("%s: user value is not an array; kept" % label(path))
            return
        added: List[Any] = []
        for item in items:
            c = canonical_json(item)
            if any(canonical_json(x) == c for x in cur):
                if adopt:
                    added.append(item)
                continue
            clash = None
            for other in excl.get(path, []):
                oarr = _get(doc, other)
                if isinstance(oarr, list) and any(canonical_json(x) == c for x in oarr):
                    clash = other
                    break
            if clash is not None and not adopt:
                conflicts.append("%s: %s is in the user's %s; user placement kept" % (
                    label(path), c, label(clash)))
                continue
            if clash is not None:
                oarr = _get(doc, clash)
                oarr[:] = [x for x in oarr if canonical_json(x) != c]
            cur.append(copy.deepcopy(item))
            added.append(item)
        if path in target.sort_arrays:
            cur.sort(key=lambda x: x if isinstance(x, str) else canonical_json(x))
        if added:
            owned.append({"path": list(path), "items": copy.deepcopy(added)})
        _prune(doc, path)

    def walk(path: Tuple[str, ...], value: Any, mode: str) -> None:
        if mode == "replace":
            leaf(path, value, True)
        elif isinstance(value, dict) and value:
            for k in sorted(value):
                walk(path + (k,), value[k], mode)
        elif isinstance(value, list):
            array(path, value)
        else:
            leaf(path, value, False)

    owners = sorted(target.owners, key=lambda o: (len(o[0]), o[0]))
    replace_paths = [o[0] for o in owners if o[1] == "replace"]
    for top in sorted(target.fragment):
        _walk_fragment(doc, (top,), target.fragment[top], owners, replace_paths, walk, conflicts)
    return doc, owned, conflicts


def _walk_fragment(doc, path, value, owners, replace_paths, walk, conflicts) -> None:
    if path in replace_paths:
        walk(path, value, "replace")
        return
    if isinstance(value, dict) and any(r[:len(path)] == path and len(r) > len(path) for r in replace_paths):
        for k in sorted(value):  # a replace owner lies deeper: descend key by key
            _walk_fragment(doc, path + (k,), value[k], owners, replace_paths, walk, conflicts)
        return
    if not any(o[0] == path[:len(o[0])] for o in owners if o[1] == "deep"):
        raise RenderError("internal: %s is not under an owner key" % ".".join(path))
    walk(path, value, "deep")


def owner_view(doc: Dict[str, Any], target: Target) -> Dict[str, Any]:
    """The subset of ``doc`` under the target's owner paths (safe to show in diffs)."""
    view: Dict[str, Any] = {}
    for path, _mode in sorted(target.owners):
        cur = _get(doc, path)
        if cur is _MISSING:
            continue
        node = view
        for p in path[:-1]:
            node = node.setdefault(p, {})
        node[path[-1]] = cur
    return view


# ================================================================= merge: TOML blocks


def toml_block_markers(block_id: str) -> Tuple[str, str]:
    return "# harness:begin block=%s" % block_id, "# harness:end block=%s" % block_id


_TBLOCK_RE = re.compile(r"# harness:begin block=(?P<id>\S+)\n(?P<body>.*?)# harness:end block=(?P=id)\n?", re.S)


def merge_toml_blocks(live: Optional[str], tblocks: Dict[str, str], prev: Dict[str, str],
                      adopt: bool = False) -> Tuple[str, Dict[str, str], List[str]]:
    """Managed blocks in a TOML file (Codex ``config.toml``), always at the end of the file.

    The result is re-parsed; if the combination is invalid TOML (for example the user
    already defines the same table) the live file is kept and a conflict reported.
    """
    from .util import sha256_bytes

    text = live or ""
    conflicts: List[str] = []
    existing = {m.group("id"): m.group("body") for m in _TBLOCK_RE.finditer(text)}
    base = _TBLOCK_RE.sub("", text)
    state: Dict[str, str] = {}
    out_blocks: Dict[str, str] = {}
    for bid, body in existing.items():
        sha = sha256_bytes(body.encode())
        if bid in prev and sha != prev[bid] and not adopt:
            conflicts.append("block %s was edited outside the harness (kept)" % bid)
            out_blocks[bid] = body
            state[bid] = prev[bid]
    for bid in sorted(tblocks):
        if bid in out_blocks:
            continue
        out_blocks[bid] = tblocks[bid] if tblocks[bid].endswith("\n") else tblocks[bid] + "\n"
        state[bid] = sha256_bytes(out_blocks[bid].encode())
    base = base.rstrip("\n")
    parts = [base + "\n"] if base else []
    for bid in sorted(out_blocks):
        begin, end = toml_block_markers(bid)
        parts.append("%s\n%s%s\n" % (begin, out_blocks[bid], end))
    new = "\n".join(parts)
    try:
        toml_compat.loads(new)
    except toml_compat.TOMLDecodeError as exc:
        conflicts.append("merged file would be invalid TOML (%s); live file kept" % exc)
        return text, prev and dict(prev) or {}, conflicts
    return new, state, conflicts


# ================================================================= pure render (render --out)


def pure_content(t: Target) -> Optional[bytes]:
    """Content of a target rendered onto nothing (deterministic, independent of live files)."""
    if t.mode == "file":
        return t.content
    if t.mode == "managed-block":
        text, _, _ = merge_managed_blocks(None, t.blocks, {})
        return text.encode("utf-8")
    if t.mode == "json-merge":
        doc, _, _ = merge_json({}, t, [])
        return dump_json(doc, sort_keys=True)
    if t.mode == "toml-block":
        text, _, _ = merge_toml_blocks(None, t.tblocks, {})
        return text.encode("utf-8")
    return None
