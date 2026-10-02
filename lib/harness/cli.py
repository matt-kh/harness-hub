"""Command-line interface (ARCHITECTURE §6). ``harness <command> --help`` for details.

Global flags may appear before or after the command: ``--config``, ``--home`` (the hub
directory, i.e. HARNESS_HOME), ``--json``, ``--offline``, ``--yes``, ``--dry-run``.
Environment: HARNESS_HOME, HARNESS_CONFIG, HARNESS_OFFLINE, NO_COLOR.

Exit codes: 0 ok, 1 error or failed check, 2 usage error or plan with conflicts.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, List, Optional, Sequence

from . import __version__
from .util import HarnessError, eprint

COMMANDS = [
    ("bootstrap", "first run: init -> resolve -> plan -> apply -> doctor -> manual steps"),
    ("init", "write local/harness.toml from the template (optionally from an org overlay)"),
    ("bundles", "list bundles or show one"),
    ("config", "validate | get | set | explain | migrate the configuration"),
    ("plan", "render to memory and show what apply would change"),
    ("apply", "execute the plan (backups, atomic writes, state)"),
    ("sync", "classify managed files clean|drifted|missing|foreign; adopt edits back"),
    ("render", "render the provider trees into a directory (no live files read)"),
    ("doctor", "PASS/WARN/FAIL checks with the manual step that fixes each failure"),
    ("status", "active bundles/providers, drift summary, capability matrix"),
    ("install", "install a pinned, sha256-verified tool into ~/.local/bin"),
    ("upgrade", "update the hub checkout, print migration notes, re-plan"),
    ("pack", "write the hub as a release artifact: git bundle + SHA256SUMS + INSTALL.txt (+ tools)"),
    ("verify", "check a hub bundle file: git bundle verify, heads/tags, SHA256SUMS beside it"),
    ("uninstall", "remove what the harness wrote (state-listed paths only)"),
    ("test", "run the engine, guard, bundle, skill and provider test suites"),
    ("lint", "validate manifests, cross-references, templates, private identifiers"),
    ("docs", "generate | check the generated regions under docs/"),
    ("steps", "list manual steps (--pending: only those whose verify fails)"),
    ("version", "print hub, applied and runtime versions"),
]


def _csv(values: Optional[Sequence[str]]) -> List[str]:
    out: List[str] = []
    for v in values or []:
        out.extend(x.strip() for x in v.split(",") if x.strip())
    return out


def _global_parent() -> argparse.ArgumentParser:
    g = argparse.ArgumentParser(add_help=False)
    s = argparse.SUPPRESS
    g.add_argument("--config", default=s, metavar="PATH", help="config file (default: $HARNESS_CONFIG or <hub>/local/harness.toml)")
    g.add_argument("--home", default=s, metavar="DIR", help="hub directory (HARNESS_HOME)")
    g.add_argument("--json", action="store_true", default=s, help="machine-readable output")
    g.add_argument("--offline", action="store_true", default=s, help="skip network checks (HARNESS_OFFLINE=1)")
    g.add_argument("--yes", "-y", action="store_true", default=s, help="assume yes; never prompt")
    g.add_argument("--dry-run", action="store_true", default=s, help="show what would happen, write nothing")
    return g


def _selection(p: argparse.ArgumentParser, bundles: bool = True) -> None:
    if bundles:
        p.add_argument("--bundles", "--bundle", action="append", metavar="A,B", help="override [hub].bundles")
    p.add_argument("--providers", "--provider", action="append", metavar="X,Y", help="override [hub].providers")


class StableHelpFormatter(argparse.HelpFormatter):
    """Help text identical on python 3.9-3.14 (3.13 changed how multi-flag options render),
    so the generated docs/reference/cli.md does not drift with the interpreter."""

    def _format_action_invocation(self, action: argparse.Action) -> str:
        if not action.option_strings:
            default = self._get_default_metavar_for_positional(action)
            (metavar,) = self._metavar_formatter(action, default)(1)
            return metavar
        if action.nargs == 0:
            return ", ".join(action.option_strings)
        default = self._get_default_metavar_for_optional(action)
        args = self._format_args(action, default)
        return ", ".join("%s %s" % (opt, args) for opt in action.option_strings)


def build_parser() -> argparse.ArgumentParser:
    g = _global_parent()
    parser = argparse.ArgumentParser(
        prog="harness", parents=[g], formatter_class=StableHelpFormatter,
        description="harness-hub: render one declarative config into every agent provider you use.",
        epilog="Run `harness <command> --help` for command flags. Docs: docs/reference/cli.md")
    parser.add_argument("--version", action="version", version="harness %s" % __version__)
    sub = parser.add_subparsers(dest="command", metavar="command")
    helps = dict(COMMANDS)

    def add(name: str) -> argparse.ArgumentParser:
        return sub.add_parser(name, parents=[g], help=helps[name], description=helps[name],
                              formatter_class=StableHelpFormatter)

    p = add("bootstrap")
    _selection(p)
    p.add_argument("--profile", help="profile name from profiles/")
    p.add_argument("--email", help="identity.email for a new config")
    p.add_argument("--no-install-tools", action="store_true", help="do not run `harness install` for missing binaries")
    p.add_argument("--adopt", action="append", default=[], metavar="PATH", help="take over this foreign path (backed up)")
    p.add_argument("--from", dest="from_", metavar="FILE.bundle",
                   help="clone the hub from this bundle file into --dest, then run the clone's bootstrap with the other flags")
    p.add_argument("--dest", metavar="DIR", help="with --from: where to clone (default ~/harness-hub; must not exist or be empty)")
    p.add_argument("--origin", metavar="URL", help="with --from: set the clone's origin remote (default: the bundle file)")

    p = add("init")
    _selection(p)
    p.add_argument("--profile", help="profile name from profiles/")
    p.add_argument("--from", dest="from_", metavar="PATH|URL", help="org overlay file or git URL -> local/harness.org.toml")
    p.add_argument("--email", help="identity.email")
    p.add_argument("--force", action="store_true", help="overwrite an existing config")
    p.add_argument("--git", action="store_true", help="git init local/ as a private repository")

    p = add("bundles")
    p.add_argument("action", nargs="?", default="list", choices=["list", "show"])
    p.add_argument("name", nargs="?")

    p = add("config")
    csub = p.add_subparsers(dest="action", metavar="action")
    F = StableHelpFormatter
    c = csub.add_parser("validate", parents=[g], formatter_class=F, help="schema + secret-shape check of the merged config")
    c.add_argument("--strict", action="store_true", help="deprecations are errors")
    c = csub.add_parser("get", parents=[g], formatter_class=F, help="print one merged value")
    c.add_argument("key")
    c = csub.add_parser("set", parents=[g], formatter_class=F, help="set a scalar/simple array in the config file (comments kept)")
    c.add_argument("key")
    c.add_argument("value", help="TOML/JSON literal or bare string")
    c = csub.add_parser("explain", parents=[g], formatter_class=F, help="type, default, source layer and users of a key")
    c.add_argument("key")
    c = csub.add_parser("migrate", parents=[g], formatter_class=F, help="rename deprecated keys in the config file")
    c.add_argument("--write", action="store_true", help="write the result (default: show it)")

    p = add("plan")
    _selection(p)
    p.add_argument("--diff", action="store_true", help="show unified diffs")
    p.add_argument("--adopt", action="append", default=[], metavar="PATH", help="preview taking over PATH")
    p.add_argument("-v", "--verbose", action="store_true", help="also list unchanged paths")

    p = add("apply")
    _selection(p)
    p.add_argument("--diff", action="store_true", help="show unified diffs")
    p.add_argument("--adopt", action="append", default=[], metavar="PATH", help="back up and take over PATH (foreign or edited)")
    p.add_argument("-v", "--verbose", action="store_true")

    p = add("sync")
    _selection(p, bundles=False)
    p.add_argument("--adopt", nargs="*", metavar="PATH", help="copy drifted untemplated files back into their bundle (all, or PATHs)")

    p = add("render")
    _selection(p)
    p.add_argument("--out", required=True, metavar="DIR", help="directory standing in for $HOME")

    p = add("doctor")
    p.add_argument("--bundle", action="append", metavar="NAME")
    p.add_argument("--provider", action="append", metavar="NAME")

    p = add("status")
    p.add_argument("--matrix", action="store_true", help="capability matrix of every provider")

    p = add("install")
    p.add_argument("tool", nargs="?", help="tool id (tools/<id>.lock.json or a bundle's install/<id>.sh)")
    p.add_argument("--from", dest="from_", metavar="FILE", help="use a local archive (air-gapped)")
    p.add_argument("--version", dest="want_version", help="must equal the locked version")
    p.add_argument("--insecure", action="store_true", help="allow a lock without verified sha256")
    p.add_argument("--dest", metavar="DIR", help="install directory (default ~/.local/bin)")

    p = add("upgrade")
    p.add_argument("--to", metavar="TAG", help="check out this tag (default: fast-forward the branch)")
    p.add_argument("--no-apply", action="store_true", help="stop after the plan")

    p = add("pack")
    p.add_argument("--out", metavar="DIR", help="output directory (default <hub>/build/release)")
    p.add_argument("--tag", metavar="TAG", help="release this existing tag (bundle carries every tag; default: branches + tags + HEAD)")
    p.add_argument("--tools", action="append", metavar="OS/ARCH,...",
                   help="also download tools/*.lock.json assets for these platforms (e.g. linux/amd64,darwin/arm64)")

    p = add("verify")
    p.add_argument("file", metavar="FILE.bundle", help="the bundle file (SHA256SUMS beside it is checked too)")

    p = add("uninstall")
    p.add_argument("--bundle", action="append", metavar="NAME", help="only paths owned by these bundles")
    p.add_argument("--provider", action="append", metavar="NAME", help="only these providers")
    p.add_argument("--all", action="store_true", help="every provider with a state file")
    p.add_argument("--purge-tools", action="store_true", help="also remove tools installed by `harness install`")

    p = add("test")
    p.add_argument("suite", nargs="?", default="all",
                   help="all | unit | guard | bundles | skills | providers | smoke | <bundle name>")
    p.add_argument("-v", "--verbose", action="store_true")

    add("lint")

    p = add("docs")
    p.add_argument("action", choices=["generate", "check"])

    p = add("steps")
    p.add_argument("--bundle", action="append", metavar="NAME")
    p.add_argument("--pending", action="store_true", help="only steps whose verify command fails")

    add("version")
    return parser


class Ctx:
    """Parsed global options with defaults applied."""

    def __init__(self, ns: argparse.Namespace):
        self.ns = ns
        self.config = getattr(ns, "config", None)
        self.home = getattr(ns, "home", None)
        if self.home:
            os.environ["HARNESS_HOME"] = os.path.abspath(os.path.expanduser(self.home))
        self.json = bool(getattr(ns, "json", False))
        self.offline = bool(getattr(ns, "offline", False)) or os.environ.get("HARNESS_OFFLINE") in ("1", "true", "yes")
        self.yes = bool(getattr(ns, "yes", False))
        self.dry_run = bool(getattr(ns, "dry_run", False))
        self.argv: List[str] = []

    def hub(self, require_config: bool = True, bundles: Optional[Sequence[str]] = None,
            providers: Optional[Sequence[str]] = None, profile: Optional[str] = None):
        from .hub import Hub

        return Hub(home=self.home, config_path=self.config, bundles=bundles or None,
                   providers=providers or None, profile=profile, require_config=require_config)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    ns = parser.parse_args(argv)
    if not ns.command:
        parser.print_help()
        return 2
    ctx = Ctx(ns)
    ctx.argv = list(sys.argv[1:] if argv is None else argv)
    try:
        return int(dispatch(ctx, ns, parser) or 0)
    except HarnessError as exc:
        eprint("harness: %s" % exc)
        return exc.code
    except KeyboardInterrupt:
        eprint("harness: interrupted")
        return 130
    except BrokenPipeError:
        return 0


def dispatch(ctx: Ctx, ns: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    cmd = ns.command
    if cmd == "version":
        return cmd_version(ctx)
    if cmd == "bundles":
        return cmd_bundles(ctx, ns)
    if cmd == "config":
        return cmd_config(ctx, ns, parser)
    if cmd in ("plan", "apply"):
        return cmd_plan_apply(ctx, ns, apply=(cmd == "apply"))
    if cmd == "render":
        return cmd_render(ctx, ns)
    if cmd == "sync":
        from . import sync

        hub = ctx.hub()
        return sync.run(hub, hub.filter_providers(_csv(ns.providers)), adopt=ns.adopt, as_json=ctx.json)
    if cmd == "doctor":
        from . import doctor

        hub = ctx.hub()
        return doctor.run(hub, offline=ctx.offline, as_json=ctx.json, bundles=ns.bundle, providers=ns.provider)
    if cmd == "steps":
        from . import steps

        return steps.run(ctx.hub(), bundles=ns.bundle, pending=ns.pending, as_json=ctx.json)
    if cmd == "status":
        from . import status

        return status.run(ctx, matrix=ns.matrix)
    if cmd == "install":
        from . import tools

        return tools.run(ctx, ns)
    if cmd == "upgrade":
        from . import upgrade

        return upgrade.run(ctx, ns)
    if cmd in ("pack", "verify"):
        from . import pack

        return pack.run_pack(ctx, ns) if cmd == "pack" else pack.run_verify(ctx, ns)
    if cmd == "uninstall":
        from . import uninstall

        return uninstall.run(ctx, ns)
    if cmd == "test":
        from . import test as testmod

        return testmod.run(ctx, ns.suite, verbose=ns.verbose)
    if cmd == "lint":
        from . import lint

        return lint.run(ctx)
    if cmd == "docs":
        from . import docsgen

        return docsgen.run(ctx, ns.action)
    if cmd == "init":
        from . import init

        return init.run(ctx, ns)
    if cmd == "bootstrap":
        from . import bootstrap

        if ns.from_:
            return bootstrap.from_bundle(ctx, ns)
        if ns.dest or ns.origin:
            raise HarnessError("--dest and --origin only apply with --from FILE.bundle", 2)
        return bootstrap.run(ctx, ns)
    raise HarnessError("unknown command %s" % cmd, 2)


# ----------------------------------------------------------------- small commands


def cmd_version(ctx: Ctx) -> int:
    import platform

    from . import state as S
    from .util import hub_home, run_argv

    info = {"harness": __version__, "home": hub_home(), "python": platform.python_version()}
    rc, out, _ = run_argv(["bash", "-c", "echo $BASH_VERSION"], timeout=5)
    info["bash"] = out.strip() if rc == 0 else "missing"
    try:
        hub = ctx.hub()
        applied = {}
        for p in hub.active_providers:
            st = S.load(p.name, p.home)
            applied[p.name] = st.harness_version or "(never applied)"
        info["applied"] = applied
    except HarnessError:
        pass
    if ctx.json:
        print(json.dumps(info, indent=2, sort_keys=True))
    else:
        for k in ("harness", "home", "python", "bash"):
            print("%-8s %s" % (k, info[k]))
        for name, ver in sorted((info.get("applied") or {}).items()):
            print("%-8s %s (applied to %s)" % ("applied", ver, name))
    return 0


def cmd_bundles(ctx: Ctx, ns: argparse.Namespace) -> int:
    hub = ctx.hub(require_config=False)
    active = set(hub.active_names) if hub.requested_bundles else set()
    if ns.action == "show":
        if not ns.name:
            raise HarnessError("usage: harness bundles show NAME", 2)
        b = hub.bundle(ns.name)
        if ctx.json:
            print(json.dumps(b.data, indent=2, sort_keys=True, default=str))
            return 0
        print("%s — %s" % (b.name, b.summary))
        if b.description:
            print("\n" + b.description.strip() + "\n")
        for label, vals in (("depends_on", b.depends_on), ("recommends", b.recommends),
                            ("conflicts_with", b.conflicts_with)):
            if vals:
                print("%-15s %s" % (label, ", ".join(vals)))
        if b.any_of:
            print("%-15s %s" % ("any_of", " ; ".join(" | ".join(g) for g in b.any_of)))
        print("%-15s %s" % ("path", b.path))
        print("%-15s %s" % ("docs", b.docs_path()))
        for s in b.manual_steps:
            print("manual step     %s — %s" % (s.get("id"), s.get("title")))
        return 0
    rows = []
    for name in sorted(hub.bundles):
        b = hub.bundles[name]
        rows.append({"name": name, "active": name in active, "origin": b.origin, "summary": b.summary})
    if ctx.json:
        print(json.dumps(rows, indent=2))
        return 0
    for r in rows:
        print("%s %-18s %-8s %s" % ("*" if r["active"] else " ", r["name"], r["origin"], r["summary"]))
    return 0


def cmd_config(ctx: Ctx, ns: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from . import config as C
    from . import toml_compat

    action = ns.action
    if not action:
        raise HarnessError("usage: harness config validate|get|set|explain|migrate", 2)
    if action == "validate":
        hub = ctx.hub()
        res = hub.config.validate()
        errors = list(res.errors) + (list(res.warnings) if ns.strict else [])
        if ctx.json:
            print(json.dumps({"ok": not errors, "errors": res.errors, "warnings": res.warnings}, indent=2))
        else:
            for w in res.warnings:
                print("WARN  %s" % w)
            for e in res.errors:
                print("FAIL  %s" % e)
            print("config: %s — %d error(s), %d warning(s)" % (hub.config_path, len(res.errors), len(res.warnings)))
        return 1 if errors else 0
    if action == "get":
        hub = ctx.hub()
        if not hub.config.has(ns.key):
            raise HarnessError("%s: not set" % ns.key)
        val = hub.config.get(ns.key)
        if ctx.json or not isinstance(val, (str, int, float)) or isinstance(val, bool):
            print(json.dumps(val, indent=2 if isinstance(val, (dict, list)) else None, sort_keys=True))
        else:
            print(val)
        return 0
    if action == "explain":
        hub = ctx.hub()
        for line in hub.config.explain(ns.key, hub.bundles.values()):
            print(line)
        return 0
    if action == "set":
        path = C.resolve_config_path(ctx.config)
        text = C.read_config_text(path)
        value = _parse_cli_value(ns.value)
        new = C.set_in_text(text, ns.key, value)
        toml_compat.loads(new)  # never write an unparsable file
        if C.secret_findings(C.flatten_to_nested({ns.key: value})):
            raise HarnessError("%s: refusing to store a secret-shaped value (see %s)" % (ns.key, C.SECRETS_DOC))
        if ctx.dry_run:
            sys.stdout.write(new)
            return 0
        from .util import atomic_write

        atomic_write(path, new.encode("utf-8"))
        hub = ctx.hub()
        res = hub.config.validate()
        for e in res.errors:
            print("FAIL  %s" % e)
        print("set %s = %s in %s" % (ns.key, toml_compat.dump_value(value), path))
        return 1 if res.errors else 0
    if action == "migrate":
        hub = ctx.hub()
        path = hub.config_path
        text = C.read_config_text(path)
        new, notes = C.migrate_text(text, hub.schema)
        for n in notes:
            print(n)
        if not notes:
            print("nothing to migrate")
            return 0
        if ns.write and not ctx.dry_run:
            from .util import atomic_write

            atomic_write(path, new.encode("utf-8"))
            print("wrote %s" % path)
        else:
            sys.stdout.write(new)
            print("(dry run; re-run with --write)")
        return 0
    raise HarnessError("unknown config action %s" % action, 2)


def _parse_cli_value(raw: str) -> Any:
    from . import toml_compat

    try:
        return toml_compat.loads("v = " + raw)["v"]
    except Exception:
        pass
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def cmd_plan_apply(ctx: Ctx, ns: argparse.Namespace, apply: bool) -> int:
    from . import apply as A
    from . import plan as P

    hub = ctx.hub(bundles=_csv(ns.bundles), providers=_csv(ns.providers))
    hub.validate_config()
    providers = hub.active_providers
    if not providers:
        raise HarnessError("no providers selected: set [hub].providers")
    plan = P.build(hub, providers, adopt=ns.adopt)
    if ctx.json and not apply:
        print(json.dumps(plan.to_json(), indent=2))
    else:
        P.print_plan(plan, show_diff=ns.diff, verbose=ns.verbose)
    if not apply:
        return 2 if plan.counts()["conflict"] else 0
    if ctx.dry_run:
        print("dry run: nothing written")
        return 0
    if plan.changes and not ctx.yes and sys.stdin.isatty():
        answer = input("Apply %d change(s)? [y/N] " % plan.changes).strip().lower()
        if answer not in ("y", "yes"):
            print("aborted")
            return 1
    report = A.execute(plan, hub, {p.name: p.home for p in providers})
    if ctx.json:
        print(json.dumps(report, indent=2))
    else:
        print(A.summary_line(report))
    return 0


def cmd_render(ctx: Ctx, ns: argparse.Namespace) -> int:
    from . import build_products
    from . import render as R
    from .util import atomic_write, user_home

    hub = ctx.hub(bundles=_csv(ns.bundles), providers=_csv(ns.providers))
    hub.validate_config()
    targets = R.Renderer(hub).render(hub.active_providers, include_hub=True)
    out = os.path.abspath(ns.out)
    home = user_home().rstrip("/")
    n = links = 0
    for t in targets:
        if t.mode == "symlink":
            links += 1
            continue
        data = R.pure_content(t)
        if data is None:
            continue
        rel = t.path[len(home) + 1:] if t.path.startswith(home + "/") else os.path.join("_abs", t.path.lstrip("/"))
        dest = os.path.join(out, rel)
        if not ctx.dry_run:
            atomic_write(dest, data, mode=0o755 if (t.mode == "file" and t.executable) else 0o644)
        n += 1
    if not ctx.dry_run:
        build_products.write(hub)
    print("rendered %d file(s) into %s (%d ~/.local/bin link(s) not rendered in --out mode)" % (n, out, links))
    return 0
