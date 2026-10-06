"""``harness repo``: what a repository's ``.harness.toml`` declares and what yields there.

Principle 8 (user-level by design: repository-level wins). The hub is a user-level baseline;
inside a repository, every component yields to the repository's own harness by one of the
mechanisms of the derived ``yields`` facet (lib/harness/taxonomy.py). This module answers, for
one repository:

* the declaration: ``<root>/.harness.toml`` (root = first ancestor holding ``.git``), parsed with
  the same TOML subset the guard parses in bash (bundles/core/lib/harness_repo.py, loaded by
  path so there is one python parser), cross-checked against full TOML and
  ``schema/repo.schema.json``; every line the guard would ignore is reported;
* which hub components yield here and why (``[owns]`` by id or domain);
* name collisions between ``<root>/<repo_dir>/skills|agents`` and hub skills/agents, with the
  consequence each provider documents in its ``[precedence]`` table;
* the effective value of every repo override (environment > provider env in the repository's
  settings > ``.harness.toml`` > ``guard.env`` > default).

``harness repo owns ID [DIR]`` exits 0 when the repository owns ID (prints why), 1 when it does
not, 2 when ID names no component; skills run it as their Step 0.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

from .util import HarnessError, atomic_write, read_bytes, read_text

_HERE = os.path.dirname(os.path.abspath(__file__))
PARSER_PATH = os.path.normpath(os.path.join(_HERE, "..", "..", "bundles", "core", "lib", "harness_repo.py"))
DECL_NAME = ".harness.toml"
SECTIONS = ("repo", "owns", "overrides")


def parser_module() -> Any:
    """The shared subset parser (bundles/core/lib/harness_repo.py)."""
    mod = sys.modules.get("harness_repo_subset")
    if mod is None:
        spec = importlib.util.spec_from_file_location("harness_repo_subset", PARSER_PATH)
        if spec is None or spec.loader is None:  # pragma: no cover - broken checkout
            raise HarnessError("cannot load %s" % PARSER_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        sys.modules["harness_repo_subset"] = mod
    return mod


def find_root(start: Optional[str] = None) -> Optional[str]:
    return parser_module().repo_root(os.path.abspath(start or os.getcwd()))


class Problem:
    def __init__(self, level: str, line: int, message: str):
        self.level, self.line, self.message = level, line, message

    def to_dict(self) -> Dict[str, Any]:
        return OrderedDict([("level", self.level), ("line", self.line), ("message", self.message)])

    def __str__(self) -> str:
        return "%s%s%s" % ("ERROR " if self.level == "error" else "WARN  ",
                           "line %d: " % self.line if self.line else "", self.message)


class Declaration:
    """A repository's ``.harness.toml`` as the guard and the skills see it."""

    def __init__(self, root: Optional[str]):
        self.root = root
        self.path: Optional[str] = None
        self.data: Dict[str, Any] = {}           # what the subset parser (the guard) reads
        self.problems: List[Problem] = []
        if root and os.path.isfile(os.path.join(root, DECL_NAME)):
            self.path = os.path.join(root, DECL_NAME)

    @property
    def domains(self) -> List[str]:
        v = (self.data.get("owns") or {}).get("domains")
        return list(v) if isinstance(v, list) else []

    @property
    def components(self) -> List[str]:
        v = (self.data.get("owns") or {}).get("components")
        return list(v) if isinstance(v, list) else []

    @property
    def overrides(self) -> Dict[str, str]:
        v = self.data.get("overrides") or {}
        return {k: x for k, x in v.items() if isinstance(x, str)}

    def to_dict(self) -> Dict[str, Any]:
        return OrderedDict([("root", self.root), ("file", self.path),
                            ("repo", self.data.get("repo") or {}),
                            ("owns", OrderedDict([("domains", self.domains), ("components", self.components)])),
                            ("overrides", self.overrides),
                            ("problems", [p.to_dict() for p in self.problems])])


def load(root: Optional[str], comps: Optional[List[Any]] = None, override_names: Optional[List[str]] = None,
         home: Optional[str] = None) -> Declaration:
    """Parse and check ``<root>/.harness.toml``. ``comps``/``override_names`` enable the id/name checks."""
    from . import manifest as M
    from . import schema_lite
    from . import taxonomy as T
    from . import toml_compat

    decl = Declaration(root)
    if not decl.path:
        return decl
    hr = parser_module()
    _p, data, problems = hr.repo_declaration(root)
    decl.data = data
    for line, why in problems:
        decl.problems.append(Problem("error", line, "%s; the guard and the skills ignore %s" % (
            why, "this line" if line else "the whole file")))
    if any(line == 0 for line, _w in problems):
        return decl
    raw = read_bytes(decl.path) or b""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        text = raw.decode("utf-8", "replace")
        decl.problems.append(Problem("warning", 0, "not UTF-8 (byte %d); the guard compares the raw bytes, so ids "
                                     "or values with such bytes never match; save the file as UTF-8" % exc.start))
    try:
        full = toml_compat.loads(text)
    except toml_compat.TOMLDecodeError as exc:
        full = None
        decl.problems.append(Problem("warning", 0, "not valid TOML (%s); fix it so other TOML readers agree" % exc))
    if full is not None:
        for sec in sorted(set(full) | set(data)):
            if sec not in SECTIONS:
                decl.problems.append(Problem("warning", 0, "unknown section [%s] (known: %s); it is ignored"
                                             % (sec, ", ".join(SECTIONS))))
                continue
            a, b = data.get(sec) or {}, full.get(sec) or {}
            for key in sorted(set(a) | set(b)):
                if a.get(key) != b.get(key):
                    decl.problems.append(Problem("error", 0, "[%s] %s: TOML reads %s but the guard's subset reads "
                                                 "%s; write it on one line, quoted, without inline comments or "
                                                 "escapes" % (sec, key, json.dumps(b.get(key)), json.dumps(a.get(key)))))
        res = schema_lite.validate(M.load_schema("repo.schema.json", home), full)
        for e in res.errors:
            decl.problems.append(Problem("error", 0, "schema: %s (schema/repo.schema.json)" % e))
    for d in decl.domains:
        if d not in T.FACETS["domain"]:
            decl.problems.append(Problem("error", 0, "[owns] domains: unknown domain %r; use one of %s"
                                         % (d, ", ".join(T.FACETS["domain"]))))
    if "base" in decl.domains:
        decl.problems.append(Problem("warning", 0, "[owns] domains = base: the credential section and permission "
                                     "list never yield; base covers nothing else that yields by declaration"))
    if comps is not None:
        by_id = {c.id: c for c in comps}
        for cid in decl.components:
            c = by_id.get(cid)
            if c is None:
                decl.problems.append(Problem("warning", 0, "[owns] components: %s names no component of this hub; "
                                             "use an id printed by `harness catalog`" % cid))
            elif c.yields == "never":
                decl.problems.append(Problem("warning", 0, "[owns] components: %s never yields (it protects the "
                                             "developer's own credentials); remove it" % cid))
            elif c.yields == "name":
                decl.problems.append(Problem("warning", 0, "[owns] components: %s yields by name, not by "
                                             "declaration; ship an agent of the same name in the repository "
                                             "(e.g. .claude/agents/%s.md) instead" % (cid, cid.rsplit("/", 1)[-1])))
            elif c.yields != "declaration":
                decl.problems.append(Problem("warning", 0, "[owns] components: %s yields by %s, not by declaration; "
                                             "listing it changes nothing" % (cid, c.yields)))
    if override_names is not None:
        for name in sorted(decl.overrides):
            if name in T.REPO_OVERRIDE_DENY or re.search(r"_PY$|^GUARD_|^HARNESS_|CRED", name):
                decl.problems.append(Problem("error", 0, "[overrides] %s is settable only from the developer's own "
                                             "environment; the guard ignores it here" % name))
            elif name not in override_names:
                decl.problems.append(Problem("error", 0, "[overrides] %s is not a repo override; the guard ignores "
                                             "it (allowed: %s; docs/reference/hook-policy.md#repo-overrides)"
                                             % (name, ", ".join(override_names))))
    return decl


def owned_because(decl: Declaration, cid: str, domain: Optional[str]) -> Optional[str]:
    """Why ``decl`` owns component ``cid`` (``None`` when it does not; never for credentials)."""
    from . import taxonomy as T

    if not decl.path or cid in T.NEVER_YIELDS:
        return None
    if cid in decl.components:
        return "%s lists it in [owns] components" % DECL_NAME
    if domain and domain in decl.domains:
        return "%s lists its domain %s in [owns] domains" % (DECL_NAME, domain)
    return None


def yielding(decl: Declaration, comps: List[Any]) -> List[Tuple[Any, str]]:
    """Components with ``yields = declaration`` that the declaration owns, with the reason."""
    out = []
    for c in sorted(comps, key=lambda c: c.id):
        if c.yields != "declaration":
            continue
        why = owned_because(decl, c.id, c.domain)
        if why:
            out.append((c, why))
    return out


def _names(path: str, agents: bool) -> List[str]:
    if not os.path.isdir(path):
        return []
    out = []
    for n in sorted(os.listdir(path)):
        if agents and n.endswith(".md") and os.path.isfile(os.path.join(path, n)):
            out.append(n[:-3])
        elif not agents and os.path.isfile(os.path.join(path, n, "SKILL.md")):
            out.append(n)
    return out


def collisions(root: Optional[str], bundles: List[Any], providers: List[Any]) -> List[Dict[str, str]]:
    """Repository skills/agents with the name of a hub skill/agent, per provider with ``[precedence]``."""
    if not root:
        return []
    hub_skills = {os.path.basename(rel.rstrip("/")): "%s/skills/%s" % (b.name, os.path.basename(rel.rstrip("/")))
                  for b in bundles for rel in b.skills()}
    hub_agents = {os.path.splitext(os.path.basename(rel))[0]: "%s/agents/%s" % (
        b.name, os.path.splitext(os.path.basename(rel))[0]) for b in bundles for rel in b.agents()}
    out: List[Dict[str, str]] = []
    for p in providers:
        prec = getattr(p, "precedence", None) or {}
        rdir = prec.get("repo_dir")
        if not rdir:
            continue
        for kind, hub, agents in (("skill", hub_skills, False), ("agent", hub_agents, True)):
            sub = "agents" if agents else "skills"
            winner = prec.get(sub, "unknown")
            for name in _names(os.path.join(root, rdir, sub), agents):
                if name not in hub:
                    continue
                path = "%s/%s/%s" % (rdir, sub, name + (".md" if agents else ""))
                if winner == "project":
                    effect = "the repository's %s replaces the hub's (%s resolves by name, project wins)" % (kind, p.name)
                    fix = ""
                elif winner == "user":
                    effect = ("the hub's personal %s shadows the repository's (%s: user level wins on a name "
                              "collision)" % (kind, p.name))
                    hint = (prec.get("skill_override_hint") or "").replace("<name>", name)
                    fix = ("give the repository's %s a distinct name%s" % (
                        kind, ", or add %s to %s/settings.json" % (hint, rdir) if hint and kind == "skill" else ""))
                else:
                    effect = "%s does not document which %s wins" % (p.name, kind)
                    fix = "give the repository's %s a distinct name" % kind
                out.append(OrderedDict([("provider", p.name), ("kind", kind), ("name", name), ("hub", hub[name]),
                                        ("repo", path), ("effect", effect), ("fix", fix)]))
    return out


def _settings(root: Optional[str], providers: List[Any]) -> List[Tuple[str, Dict[str, Any]]]:
    out = []
    if not root:
        return out
    for p in providers:
        rdir = (getattr(p, "precedence", None) or {}).get("repo_dir")
        if not rdir:
            continue
        for fn in ("settings.json", "settings.local.json"):
            path = os.path.join(root, rdir, fn)
            try:
                data = json.loads(read_text(path) or "null")
            except ValueError:  # includes UnicodeDecodeError
                data = None
            if isinstance(data, dict):
                out.append(("%s/%s" % (rdir, fn), data))
    return out


def read_guard_env(path: Optional[str]) -> Dict[str, str]:
    """``KEY=value`` lines of a rendered guard.env (parsed like the engine; never sourced)."""
    out: Dict[str, str] = {}
    for line in (read_text(path) or "").splitlines() if path else []:
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
            v = v[1:-1]
        out[k] = v
    return out


def effective_overrides(decl: Declaration, overrides: List[Dict[str, str]], environ: Dict[str, str],
                        settings: List[Tuple[str, Dict[str, Any]]], guard_env: Dict[str, str]) -> List[Dict[str, str]]:
    """Every allow-listed override with its effective value and where it comes from."""
    from . import taxonomy as T

    seen: "OrderedDict[str, str]" = OrderedDict()
    for o in overrides:
        seen.setdefault(o["name"], o["default"])
    out = []
    for name, default in sorted(seen.items()):
        chain = []
        if name in environ:
            chain.append(("environment", environ[name]))
        for where, data in settings:
            env = data.get("env") if isinstance(data.get("env"), dict) else {}
            if name in env:
                chain.append(("%s env" % where, str(env[name])))
        if name in decl.overrides and name not in T.REPO_OVERRIDE_DENY:
            chain.append((".harness.toml", decl.overrides[name]))
        if name in guard_env:
            chain.append(("guard.env", guard_env[name]))
        chain.append(("default", default))
        src, val = chain[0]
        out.append(OrderedDict([("name", name), ("value", val), ("source", src),
                                ("shadowed", ["%s=%s" % c for c in chain[1:] if c[0] != "default"])]))
    return out


def hooks_disabled(settings: List[Tuple[str, Dict[str, Any]]]) -> List[str]:
    return [where for where, data in settings if data.get("disableAllHooks") is True]


def template(comps: List[Any]) -> str:
    """The commented ``.harness.toml`` that ``harness repo init`` prints."""
    from . import taxonomy as T

    ids = sorted(c.id for c in comps if c.yields == "declaration")
    lines = [
        "# .harness.toml - repository-level harness declaration (harness-hub, principle 8).",
        "# Provider-neutral: the hub's guard reads it from the hook's cwd, its skills at preflight.",
        "# Commit it; nothing in it is a secret. `harness repo` shows what it changes.",
        "# Subset: one statement per line, whole-line comments only (no inline comments, escapes",
        "# or multi-line arrays), each key once, at most 16 KiB and 400 lines - the guard parses it in bash.",
        "[repo]",
        "# name = \"shop\"",
        "# harness = \"docs/agent-workflow.md\"   # where your own harness is described",
        "",
        "[owns]",
        "# Domains your harness covers: every hub component in them yields here.",
        "# Values: %s." % ", ".join(T.FACETS["domain"]),
        "# domains = [\"delivery\"]",
        "# Single components by id (`harness catalog`), e.g.:",
    ]
    lines += ["#   %s" % i for i in ids]
    lines += [
        "# components = [\"core/guard.d/30-git\"]",
        "",
        "[overrides]",
        "# Allow-listed WORK_TICKET_* guard settings (docs/reference/hook-policy.md#repo-overrides); a provider env",
        "# override of the same name (e.g. .claude/settings.json \"env\") wins per key.",
        "# WORK_TICKET_ALLOW_TRANSITION = \"1\"",
        "",
    ]
    return "\n".join(lines)


# ----------------------------------------------------------------- CLI


def _context(ctx: Any) -> Tuple[Any, List[Any], List[Any]]:
    from . import taxonomy as T
    from .hub import Hub

    hub = Hub(home=ctx.home, config_path=ctx.config, require_config=False, select=False)
    bundles = [hub.bundles[n] for n in sorted(hub.bundles)]
    comps = [c for b in bundles for c in T.components(b)]
    return hub, bundles, comps


def _resolve_dir(arg: Optional[str]) -> str:
    d = os.path.abspath(os.path.expanduser(arg or os.getcwd()))
    if not os.path.isdir(d):
        raise HarnessError("%s is not a directory" % d, 2)
    return d


def run(ctx: Any, action: Optional[str], args: List[str], write: bool = False) -> int:
    from . import taxonomy as T

    if action and action not in ("show", "owns", "init"):
        args = [action] + list(args)
        action = "show"
    action = action or "show"
    hub, bundles, comps = _context(ctx)
    if action == "owns":
        if not args or len(args) > 2:
            raise HarnessError("usage: harness repo owns ID [DIR]", 2)
        cid = args[0]
        by_id = {c.id: c for c in comps}
        if cid not in by_id:
            print("harness repo: %s names no component; use an id printed by `harness catalog`" % cid, file=sys.stderr)
            return 2
        root = find_root(_resolve_dir(args[1] if len(args) > 1 else None))
        decl = load(root, home=hub.home)
        c = by_id[cid]
        why = owned_because(decl, cid, c.domain)
        if why:
            print("owned: %s yields here (%s)" % (cid, why))
            return 0
        if cid in T.NEVER_YIELDS:
            print("not owned: %s never yields (it protects the developer's own credentials)" % cid)
        elif not decl.path:
            print("not owned: %s" % ("no %s in %s" % (DECL_NAME, root) if root else "not inside a git checkout"))
        else:
            print("not owned: %s does not list %s or its domain %s" % (decl.path, cid, c.domain))
        return 1
    if len(args) > 1:
        raise HarnessError("usage: harness repo [show|init] [DIR]", 2)
    start = _resolve_dir(args[0] if args else None)
    root = find_root(start)
    if action == "init":
        text = template(comps)
        if not write:
            print(text, end="")
            return 0
        if not root:
            raise HarnessError("%s is not inside a git checkout; run `harness repo init --write` in the repository" % start)
        path = os.path.join(root, DECL_NAME)
        if os.path.exists(path):
            raise HarnessError("%s already exists; edit it, or run `harness repo init` to print the template" % path)
        atomic_write(path, text.encode("utf-8"))
        print("wrote %s; edit it, commit it, then run `harness repo`" % path)
        return 0
    overrides = T.repo_overrides(bundles)
    names = sorted(set(o["name"] for o in overrides))
    decl = load(root, comps, names, home=hub.home)
    providers = [hub.providers[n] for n in sorted(hub.providers)]
    settings = _settings(root, providers)
    guard_env = read_guard_env(os.path.join(hub.build_dir, "guard.env"))
    report = OrderedDict([
        ("declaration", decl.to_dict()),
        ("yielding", [OrderedDict([("id", c.id), ("kind", c.kind), ("domain", c.domain), ("why", why)])
                      for c, why in yielding(decl, comps)]),
        ("never", sorted(c.id for c in comps if c.yields == "never")),
        ("collisions", collisions(root, bundles, providers)),
        ("overrides", effective_overrides(decl, overrides, dict(os.environ), settings, guard_env)),
        ("warnings", ["%s sets disableAllHooks: every user-level hook, the hub's guard included, is off in this "
                      "repository; declare [owns] in %s instead" % (w, DECL_NAME) for w in hooks_disabled(settings)]),
    ])
    if ctx.json:
        print(json.dumps(report, indent=2))
        return 1 if any(p.level == "error" for p in decl.problems) else 0
    _print_show(report, decl)
    return 1 if any(p.level == "error" for p in decl.problems) else 0


def _print_show(report: Dict[str, Any], decl: Declaration) -> None:
    from .status import format_table

    if not decl.root:
        print("repository   none (not inside a git checkout): every hub component applies unchanged")
    else:
        print("repository   %s" % decl.root)
        print("declaration  %s" % (decl.path or "none - `harness repo init` prints a template"))
    if decl.problems:
        print("\nproblems")
        for p in decl.problems:
            print("  %s" % p)
    y = report["yielding"]
    print("\nyields here (by declaration)")
    if y:
        print("".join("  " + ln + "\n" for ln in format_table(
            [[e["id"], e["kind"], e["domain"] or "-", e["why"]] for e in y]).splitlines()), end="")
    else:
        print("  nothing: every guard section and skill applies")
    print("never yields: %s, and the `# never-yields:` preludes (commands that print a stored credential, "
          "shell writes to %s)" % (", ".join(report["never"]), DECL_NAME))
    if report["collisions"]:
        print("\nname collisions with the repository")
        for c in report["collisions"]:
            print("  %s %s (%s): %s%s" % (c["kind"], c["name"], c["repo"], c["effect"],
                                         "; %s" % c["fix"] if c["fix"] else ""))
    print("\nrepo overrides (effective value <- source)")
    print("".join("  " + ln + "\n" for ln in format_table(
        [[o["name"], json.dumps(o["value"]), "<- %s" % o["source"],
          ("(over %s)" % ", ".join(o["shadowed"])) if o["shadowed"] else ""] for o in report["overrides"]]
    ).splitlines()), end="")
    for w in report["warnings"]:
        print("\nWARN  %s" % w)
