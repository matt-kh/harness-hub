"""init: write ``local/harness.toml`` from ``templates/harness.toml.tmpl``.

* Only the selected bundles' keys are uncommented, and of those only the ones that are
  required or have no default (defaults stay commented so upgrades of bundle defaults flow
  through). Everything else remains visible as ``# key = value`` documentation.
* ``--from PATH|URL`` saves an organisation overlay as ``local/harness.org.toml`` (layer 2).
  A URL ending in ``.toml`` is downloaded; anything else is treated as a git repository
  whose ``harness.org.toml`` is copied (``git clone --depth 1``).
* ``local/`` is scaffolded with a README (and ``git init`` with ``--git``); it is gitignored
  by the hub, so it never reaches the public repository.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from typing import Any, Dict, List, Optional, Sequence

from . import config as C
from . import toml_compat
from .util import HarnessError, atomic_write, hub_home, read_text, tilde

LOCAL_README = """# local/ — your private overlay (gitignored by the hub)

| file | purpose |
|---|---|
| `harness.toml` | the single source of truth: identity, bundles, providers, org values |
| `harness.org.toml` | optional organisation overlay written by `harness init --from` |
| `harness.user.toml` | optional machine-specific overrides (highest file layer) |
| `bundles/<org>/` | private bundles with the same layout as the public ones |

Secrets never live here either: tokens stay in the files their tools own
(see `docs/reference/secrets.md`). Validate with `harness config validate`.
"""


def fill_template(tmpl: str, bundles: Sequence[str], providers: Sequence[str], email: str) -> str:
    selected = set(bundles)
    out: List[str] = []
    for line in tmpl.splitlines():
        m = re.match(r"^#@(!?) (\S+) (.*)$", line)
        if not m:
            out.append(line.replace("@@EMAIL@@", toml_compat.dump_string(email))
                       .replace("@@BUNDLES@@", toml_compat.dump_value(list(bundles)))
                       .replace("@@PROVIDERS@@", toml_compat.dump_value(list(providers))))
            continue
        force, owners, rest = m.group(1), set(m.group(2).split(",")), m.group(3)
        active = bool(owners & selected)
        is_header = rest.startswith("[")
        if active and (force or is_header):
            out.append(rest)
        else:
            out.append("# " + rest)
    text = "\n".join(out) + "\n"
    # drop section headers left without any active key (keeps the file valid and tidy)
    return text


def fetch_overlay(src: str) -> str:
    if os.path.exists(os.path.expanduser(src)):
        text = read_text(os.path.expanduser(src))
        assert text is not None
        return text
    if re.match(r"^https?://", src) and src.endswith(".toml"):
        from .tools import download

        return download(src, timeout=60).decode("utf-8")
    tmp = tempfile.mkdtemp(prefix="harness-org-")
    try:
        rc = subprocess.call(["git", "clone", "--quiet", "--depth", "1", src, tmp])
        if rc != 0:
            raise HarnessError("could not clone %s" % src)
        path = os.path.join(tmp, "harness.org.toml")
        text = read_text(path)
        if text is None:
            raise HarnessError("%s has no harness.org.toml at its root" % src)
        return text
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def write_config(home: str, path: str, bundles: Sequence[str], providers: Sequence[str], email: str,
                 force: bool = False, overlay: Optional[str] = None, git: bool = False, log=print) -> str:
    if os.path.exists(path) and not force:
        raise HarnessError("%s exists (use --force to overwrite; your file would be backed up)" % path)
    tmpl = read_text(os.path.join(home, "templates", "harness.toml.tmpl"))
    if tmpl is None:
        raise HarnessError("templates/harness.toml.tmpl missing (run `harness docs generate`)")
    text = fill_template(tmpl, bundles, providers, email)
    try:
        toml_compat.loads(text)
    except toml_compat.TOMLDecodeError as exc:
        raise HarnessError("internal: the filled template is not valid TOML: %s" % exc)
    local = os.path.dirname(path)
    os.makedirs(local, exist_ok=True)
    try:
        os.chmod(local, 0o700)
    except OSError:
        pass
    if os.path.exists(path):
        shutil.copy2(path, path + ".bak")
        log("backed up the old config to %s.bak" % tilde(path))
    atomic_write(path, text.encode("utf-8"), mode=0o600)
    log("wrote %s" % tilde(path))
    readme = os.path.join(local, "README.md")
    if not os.path.exists(readme) and os.path.basename(local) == "local":
        atomic_write(readme, LOCAL_README.encode("utf-8"))
    if overlay is not None:
        org = os.path.join(local, "harness.org.toml")
        toml_compat.loads(overlay)
        atomic_write(org, overlay.encode("utf-8"), mode=0o600)
        log("wrote %s (org overlay, layer 2)" % tilde(org))
    if git and not os.path.isdir(os.path.join(local, ".git")):
        subprocess.call(["git", "-C", local, "init", "--quiet"])
        log("initialised a private git repository in %s (no remote)" % tilde(local))
    return path


def default_email() -> str:
    try:
        out = subprocess.run(["git", "config", "--get", "user.email"], stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, timeout=5).stdout.decode().strip()
        return out or "you@example.com"
    except Exception:
        return "you@example.com"


def run(ctx: Any, ns: Any) -> int:
    from . import manifest as M
    from .cli import _csv

    home = hub_home()
    path = C.resolve_config_path(ctx.config, home)
    bundles = _csv(ns.bundles)
    providers = _csv(ns.providers)
    if ns.profile:
        prof = M.load_profile(home, ns.profile)
        bundles = bundles or list(prof.get("bundles", []))
        providers = providers or list(prof.get("providers", []))
    if not bundles:
        raise HarnessError("choose bundles: --bundles a,b or --profile NAME (or run ./bootstrap for the picker)", 2)
    providers = providers or ["claude"]
    overlay = fetch_overlay(ns.from_) if ns.from_ else None
    if ctx.dry_run:
        tmpl = read_text(os.path.join(home, "templates", "harness.toml.tmpl")) or ""
        print(fill_template(tmpl, bundles, providers, ns.email or default_email()), end="")
        return 0
    write_config(home, path, bundles, providers, ns.email or default_email(), force=ns.force,
                 overlay=overlay, git=ns.git)
    print("next: edit %s, then `harness config validate` and `harness plan`" % tilde(path))
    return 0
