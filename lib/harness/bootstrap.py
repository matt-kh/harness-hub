"""bootstrap: the first-run flow for a fresh clone (``./bootstrap``).

0. preflight   bash >= 3.2, python >= 3.9 (already running), jq, git; OS/arch; WSL; PATH hint
1. config      found? (--config > $HARNESS_CONFIG > <hub>/local/harness.toml) else init:
               interactive = email + bundle and provider checklists (detected binaries
               pre-checked); non-interactive = --bundles/--profile required
2. resolve     dependencies added, recommendations offered (interactive) or listed,
               conflicts/any_of stop with the sentence that fixes them; config validated
3. existing    foreign paths in provider homes: interactive keep/adopt/diff per path;
               non-interactive keeps them (or takes over --adopt PATH)
4. plan        printed; --dry-run stops here
5. apply       backups + atomic writes + state; missing tools with a lock are installed
               unless --no-install-tools / --offline
6. doctor      offline-aware
7. handoff     pending manual steps grouped by what they need (none / browser / admin)
"""
from __future__ import annotations

import os
import platform
import sys
from typing import Any, List, Optional, Sequence

from . import config as C
from .util import HarnessError, bin_dir, hub_home, read_text, run_argv, tilde, which

COMMON_BINARIES = {"bash", "jq", "git", "python3", "ssh", "curl", "sh"}


def interactive(ctx: Any) -> bool:
    return (not ctx.yes) and sys.stdin.isatty() and sys.stdout.isatty()


def preflight(log=print) -> List[str]:
    problems = []
    rc, out, _ = run_argv(["bash", "-c", "echo ${BASH_VERSINFO[0]}.${BASH_VERSINFO[1]}"], timeout=5)
    if rc != 0:
        problems.append("bash is not runnable")
    for tool in ("jq", "git"):
        if not which(tool):
            problems.append("%s is missing" % tool)
    wsl = False
    try:
        wsl = "microsoft" in (read_text("/proc/version") or "").lower()
    except OSError:
        pass
    log("preflight: %s %s%s, python %s, bash %s" % (platform.system(), platform.machine(), " (WSL)" if wsl else "",
                                                     platform.python_version(), out.strip() or "?"))
    if bin_dir() not in (os.environ.get("PATH") or "").split(os.pathsep):
        shell_rc = "~/.zprofile" if platform.system() == "Darwin" else "~/.bashrc (or ~/.zshrc)"
        log('hint: ~/.local/bin is not on PATH; add  export PATH="$HOME/.local/bin:$PATH"  to %s' % shell_rc)
    return problems


def checklist(title: str, items: List[List[Any]]) -> List[str]:
    """items: [name, checked, label]; toggle by number, Enter accepts."""
    while True:
        print("\n%s (toggle with a number, Enter to continue):" % title)
        for i, (name, checked, label) in enumerate(items, 1):
            print(" [%s] %2d %-18s %s" % ("x" if checked else " ", i, name, label))
        ans = input("> ").strip()
        if not ans:
            return [n for n, c, _l in items if c]
        for tok in ans.replace(",", " ").split():
            if tok.isdigit() and 1 <= int(tok) <= len(items):
                it = items[int(tok) - 1]
                if it[0] == "core":
                    print("core is required")
                    continue
                it[1] = not it[1]


def detected(bundle: Any) -> Optional[str]:
    names = [n for n, s in bundle.requires_binaries.items() if n not in COMMON_BINARIES and not s.get("optional")]
    if not names:
        return None
    found = [n for n in names if which(n)]
    return ", ".join(found) if found and len(found) == len(names) else None


def pick_interactive(home: str, email_default: str):
    from .hub import Hub

    hub = Hub(home=home, require_config=False)
    email = input("identity.email [%s]: " % email_default).strip() or email_default
    items = []
    for name in sorted(hub.bundles, key=lambda n: (n != "core", n)):
        b = hub.bundles[name]
        det = detected(b)
        label = b.summary + ("   detected: %s" % det if det else "") + ("   (required)" if name == "core" else "")
        items.append([name, name == "core" or bool(det), label])
    bundles = checklist("Select bundles", items)
    pitems = []
    for name in sorted(hub.providers):
        p = hub.providers[name]
        det = which(p.binary) if p.binary else None
        pitems.append([name, bool(det) or name == "claude" and not any(which(x.binary or "") for x in hub.providers.values()),
                       (p.summary or "") + ("   detected" if det else "")])
    providers = checklist("Select providers", pitems) or ["claude"]
    return bundles, providers, email


def run(ctx: Any, ns: Any) -> int:
    from . import apply as A
    from . import doctor as D
    from . import init as I
    from . import manifest as M
    from . import plan as P
    from . import steps as ST
    from .cli import _csv
    from .hub import Hub

    home = hub_home()
    problems = preflight()
    if problems:
        raise HarnessError("preflight failed: " + "; ".join(problems))
    path = C.resolve_config_path(ctx.config, home)
    bundles = _csv(ns.bundles)
    providers = _csv(ns.providers)
    # 1 config ---------------------------------------------------------------
    if not os.path.exists(path):
        if ns.profile:
            prof = M.load_profile(home, ns.profile)
            bundles = bundles or list(prof.get("bundles", []))
            providers = providers or list(prof.get("providers", []))
        email = ns.email or I.default_email()
        if not bundles:
            if not interactive(ctx):
                raise HarnessError("no config at %s: pass --bundles a,b (and --providers x) or --profile NAME "
                                   "for a non-interactive bootstrap" % tilde(path), 2)
            bundles, providers, email = pick_interactive(home, email)
        providers = providers or ["claude"]
        if ctx.dry_run:
            print("dry run: would write %s with bundles %s, providers %s" % (tilde(path), ",".join(bundles), ",".join(providers)))
        else:
            I.write_config(home, path, bundles, providers, email)
        bundles_override: Sequence[str] = bundles if ctx.dry_run else ()
        providers_override: Sequence[str] = providers if ctx.dry_run else ()
    else:
        print("config: %s" % tilde(path))
        bundles_override, providers_override = bundles, providers
    # 2 resolve ----------------------------------------------------------------
    hub = Hub(home=home, config_path=ctx.config, bundles=bundles_override or None,
              providers=providers_override or None, profile=ns.profile if os.path.exists(path) else None,
              require_config=not ctx.dry_run)
    for dep, by in sorted(hub.resolution.added.items()):
        print("resolve: + %s (required by %s)" % (dep, by))
    for rec, by in sorted(hub.resolution.recommended.items()):
        print("resolve: %s is recommended by %s (add it to [hub].bundles to enable)" % (rec, ", ".join(by)))
    res = hub.config.validate()
    for w in res.warnings:
        print("WARN  %s" % w)
    if res.errors:
        for e in res.errors:
            print("FAIL  %s" % e)
        raise HarnessError("fix %s and re-run ./bootstrap" % tilde(hub.config_path))
    if not hub.active_providers:
        raise HarnessError("no providers selected: set [hub].providers")
    # 3/4 plan -----------------------------------------------------------------
    adopt = list(ns.adopt or [])
    plan = P.build(hub, hub.active_providers, adopt=adopt)
    foreign = [it for it in plan.items if it.action == "conflict" and it.entry is None and it.target is not None]
    if foreign and interactive(ctx):
        print("\n%d path(s) already exist and are not managed by the harness:" % len(foreign))
        for it in foreign:
            while True:
                ans = input("  %s  [k]eep / [a]dopt (backup + replace) / [d]iff: " % tilde(it.path)).strip().lower() or "k"
                if ans.startswith("d"):
                    it.new = it.new if it.new is not None else (it.target.content if it.target else b"")
                    print(it.diff() or "  (no textual diff)")
                    continue
                if ans.startswith("a"):
                    adopt.append(it.path)
                break
        plan = P.build(hub, hub.active_providers, adopt=adopt)
    P.print_plan(plan)
    if ctx.dry_run:
        print("dry run: stopping before apply")
        return 0
    report = A.execute(plan, hub, {p.name: p.home for p in hub.active_providers})
    print(A.summary_line(report))
    # tools ---------------------------------------------------------------------
    if not ns.no_install_tools and not ctx.offline:
        from . import tools as T

        for b in hub.active_bundles:
            for name, spec in sorted(b.requires_binaries.items()):
                tool = spec.get("install")
                if not tool or which(name) or T.load_lock(home, tool) is None:
                    continue
                print("install: %s (missing, required by %s)" % (tool, b.name))
                try:
                    info = T.install_from_lock(T.load_lock(home, tool) or {}, tool, bin_dir())
                    from . import state as S

                    st = S.load("_hub", None)
                    st.tools[tool] = info
                    st.save()
                    print("installed %s %s" % (tool, info["version"]))
                except HarnessError as exc:
                    print("WARN  could not install %s: %s" % (tool, exc))
    # 6 doctor ------------------------------------------------------------------
    print("\n== doctor ==")
    D.run(hub, offline=ctx.offline)
    # 7 handoff -----------------------------------------------------------------
    rows = ST.collect(hub, pending=not ctx.offline)
    print()
    print(ST.render_text(rows, "Manual steps you must do" if rows else ""), end="")
    starts = " ".join("`%s`" % p.binary for p in hub.active_providers if p.binary)
    print("Then start your agent: %s" % starts)
    return 0


# ----------------------------------------------------------------- bootstrap --from FILE.bundle

FROM_ONLY_FLAGS = ("--from", "--dest", "--origin", "--home")


def passthrough_args(argv: Sequence[str]) -> List[str]:
    """``argv`` minus the command word and the flags that only the outer hub understands."""
    out: List[str] = []
    skip = False
    dropped_cmd = False
    for i, a in enumerate(argv):
        if skip:
            skip = False
            continue
        if a in FROM_ONLY_FLAGS:
            skip = True
            continue
        if any(a.startswith(f + "=") for f in FROM_ONLY_FLAGS):
            continue
        if a == "bootstrap" and not dropped_cmd:
            dropped_cmd = True
            continue
        out.append(a)
    return out


def from_bundle(ctx: Any, ns: Any) -> int:
    """Clone a hub bundle file into --dest, then exec the clone's own ./bootstrap."""
    src = os.path.abspath(os.path.expanduser(ns.from_))
    if not os.path.isfile(src):
        raise HarnessError("--from %s: no such file" % tilde(src), 2)
    dest = os.path.abspath(os.path.expanduser(ns.dest or "~/harness-hub"))
    if os.path.exists(dest) and (not os.path.isdir(dest) or os.listdir(dest)):
        raise HarnessError("--dest %s exists and is not empty; pick another directory or remove it" % tilde(dest), 2)
    rest = passthrough_args(getattr(ctx, "argv", []) or [])
    script = os.path.join(dest, "bootstrap")
    if ctx.dry_run:
        print("dry run: would clone %s into %s%s, then run %s %s" % (
            tilde(src), tilde(dest), " (origin %s)" % ns.origin if ns.origin else "", tilde(script), " ".join(rest)))
        return 0
    from .pack import git_bundle_verify

    ok, text = git_bundle_verify(src)
    if not ok:
        raise HarnessError("%s is not a valid bundle: %s" % (tilde(src), text.splitlines()[-1] if text else "verify failed"))
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    rc, out, err = run_argv(["git", "clone", "-q", src, dest], timeout=600, env=env)
    if rc != 0:
        raise HarnessError("git clone %s failed: %s" % (tilde(src), (err or out).strip()))
    rc, _o, _e = run_argv(["git", "-C", dest, "rev-parse", "--verify", "-q", "HEAD"], timeout=30)
    if rc != 0:
        # a --tag bundle has no HEAD: check out the newest tag
        _rc, tags, _e = run_argv(["git", "-C", dest, "tag", "--sort=-v:refname"], timeout=30)
        newest = (tags.split() or [""])[0]
        if not newest:
            raise HarnessError("%s has neither HEAD nor a tag to check out" % tilde(src))
        rc, out, err = run_argv(["git", "-C", dest, "-c", "advice.detachedHead=false", "checkout", "-q", newest], timeout=120)
        if rc != 0:
            raise HarnessError("git checkout %s failed: %s" % (newest, (err or out).strip()))
        print("checked out tag %s" % newest)
    if ns.origin:
        rc, out, err = run_argv(["git", "-C", dest, "remote", "set-url", "origin", ns.origin], timeout=30)
        if rc != 0:
            raise HarnessError("git remote set-url origin failed: %s" % (err or out).strip())
    print("cloned %s -> %s (origin %s)" % (tilde(src), tilde(dest), ns.origin or tilde(src)))
    if not os.path.isfile(script):
        raise HarnessError("%s has no bootstrap script; is it a harness-hub bundle?" % tilde(dest))
    sys.stdout.flush()
    child_env = dict(os.environ)
    child_env.pop("HARNESS_HOME", None)  # the clone is its own hub
    os.execvpe("bash", ["bash", script] + rest, child_env)
    return 0  # not reached
