"""``harness install TOOL``: pinned, sha256-verified tool downloads into ~/.local/bin.

Lock file ``tools/<tool>.lock.json``::

    {"tool": "gh", "version": "2.101.0", "verified": true,
     "checksums_url": "https://…/gh_2.101.0_checksums.txt",
     "assets": {"linux/amd64": {"url": "https://…/gh_2.101.0_linux_amd64.tar.gz",
                                "sha256": "…", "archive": "tar.gz",
                                "binary": "gh_2.101.0_linux_amd64/bin/gh"}, …}}

* ``verified = false`` or an empty ``sha256`` makes install refuse unless ``--insecure``.
* Downloads use urllib, which honours ``HTTPS_PROXY``/``NO_PROXY``.
  ``HARNESS_TOOLS_MIRROR=https://mirror.example.com/base`` replaces scheme+host of every
  asset URL (the path is kept), e.g. an Artifactory remote repository.
* ``--from FILE`` installs from a local archive (air-gapped); the sha256 check still applies.
* Only the declared ``binary`` member is extracted; it is written atomically with mode 0755
  and recorded in the hub state (``harness uninstall --purge-tools`` removes it).
* Without a lock file, a bundle's ``install/<tool>.sh`` is run instead (``HARNESS_BIN_DIR``
  and ``HARNESS_HOME`` exported).
"""
from __future__ import annotations

import glob
import hashlib
import io
import json
import os
import platform
import tarfile
import urllib.parse
import urllib.request
import zipfile
from typing import Any, Dict, List, Optional

from . import state as S
from .util import HarnessError, atomic_write, bin_dir, run_argv, sha256_bytes, tilde


def platform_key() -> str:
    system = platform.system().lower()
    osname = {"linux": "linux", "darwin": "darwin"}.get(system)
    if not osname:
        raise HarnessError("unsupported OS %s (Linux, WSL2 and macOS are supported)" % platform.system())
    machine = platform.machine().lower()
    arch = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}.get(machine)
    if not arch:
        raise HarnessError("unsupported architecture %s" % platform.machine())
    return "%s/%s" % (osname, arch)


def load_lock(home: str, tool: str) -> Optional[Dict[str, Any]]:
    path = os.path.join(home, "tools", "%s.lock.json" % tool)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def mirror_url(url: str, mirror: Optional[str]) -> str:
    if not mirror:
        return url
    parts = urllib.parse.urlsplit(url)
    return mirror.rstrip("/") + parts.path + ("?" + parts.query if parts.query else "")


def download(url: str, timeout: float = 300.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "harness-hub"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (https URLs from the lock)
            return resp.read()
    except Exception as exc:  # urllib raises many types
        raise HarnessError("download failed: %s (%s)" % (url, exc))


def extract(data: bytes, archive: str, member: str) -> bytes:
    if archive in ("tar.gz", "tgz"):
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
            try:
                info = tf.getmember(member)
            except KeyError:
                raise HarnessError("archive does not contain %s" % member)
            if not info.isfile():
                raise HarnessError("%s in the archive is not a regular file" % member)
            fh = tf.extractfile(info)
            assert fh is not None
            return fh.read()
    if archive == "zip":
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            try:
                return zf.read(member)
            except KeyError:
                raise HarnessError("archive does not contain %s" % member)
    if archive in ("none", "binary"):
        return data
    raise HarnessError("unsupported archive type %s" % archive)


def install_from_lock(lock: Dict[str, Any], tool: str, dest_dir: str, from_file: Optional[str] = None,
                      insecure: bool = False, offline: bool = False, want_version: Optional[str] = None,
                      key: Optional[str] = None, log=print) -> Dict[str, Any]:
    version = lock.get("version", "")
    if want_version and want_version.lstrip("v") != version:
        raise HarnessError("%s: only the locked version %s can be installed (asked for %s); "
                           "update tools/%s.lock.json" % (tool, version, want_version, tool))
    key = key or platform_key()
    asset = (lock.get("assets") or {}).get(key)
    if not asset:
        raise HarnessError("%s %s has no asset for %s in tools/%s.lock.json" % (tool, version, key, tool))
    sha = (asset.get("sha256") or "").lower()
    if (not lock.get("verified") or not sha) and not insecure:
        raise HarnessError("tools/%s.lock.json is not verified (no sha256 for %s); refusing. "
                           "Re-run with --insecure only if you trust the source." % (tool, key))
    if from_file:
        with open(from_file, "rb") as fh:
            data = fh.read()
        log("using %s" % from_file)
    else:
        if offline:
            raise HarnessError("offline: pass --from FILE (see docs/runbooks/air-gapped.md)")
        url = mirror_url(asset["url"], os.environ.get("HARNESS_TOOLS_MIRROR"))
        log("fetch %s" % url)
        data = download(url)
    got = hashlib.sha256(data).hexdigest()
    if sha and got != sha:
        raise HarnessError("sha256 mismatch for %s: expected %s, got %s — not installing" % (tool, sha, got))
    if sha:
        log("ok    sha256 verified")
    else:
        log("WARN  no sha256 in the lock; installed with --insecure")
    binary = extract(data, asset.get("archive", "tar.gz"), asset.get("binary", tool))
    dest = os.path.join(dest_dir, asset.get("name", tool))
    atomic_write(dest, binary, mode=0o755)
    return {"version": version, "path": dest, "sha256": sha256_bytes(binary), "asset": key}


def install_script(hub_home: str, tool: str) -> Optional[str]:
    for pattern in ("bundles/*/install/%s.sh" % tool, "local/bundles/*/install/%s.sh" % tool):
        found = sorted(glob.glob(os.path.join(hub_home, pattern)))
        if found:
            return found[0]
    return None


def available(hub_home: str) -> List[str]:
    names = set(os.path.basename(p)[:-len(".lock.json")] for p in glob.glob(os.path.join(hub_home, "tools", "*.lock.json")))
    for p in glob.glob(os.path.join(hub_home, "bundles", "*", "install", "*.sh")):
        names.add(os.path.basename(p)[:-3])
    return sorted(names)


def run(ctx: Any, ns: Any) -> int:
    from .util import hub_home

    home = hub_home()
    tool = ns.tool
    if not tool:
        tools = available(home)
        print("installable tools: %s" % (", ".join(tools) or "none"))
        print("usage: harness install TOOL [--from FILE] [--insecure]")
        return 0
    dest_dir = os.path.abspath(os.path.expanduser(ns.dest)) if ns.dest else bin_dir()
    lock = load_lock(home, tool)
    if lock is None:
        script = install_script(home, tool)
        if not script:
            raise HarnessError("no tools/%s.lock.json and no bundle install/%s.sh (known: %s)" % (
                tool, tool, ", ".join(available(home)) or "none"))
        if ctx.dry_run:
            print("would run %s" % script)
            return 0
        env = dict(os.environ, HARNESS_BIN_DIR=dest_dir, HARNESS_HOME=home)
        rc, out, err = run_argv(["bash", script] + (["--from", ns.from_] if ns.from_ else []),
                                timeout=900, env=env)
        print(out, end="")
        if err:
            print(err, end="")
        return rc
    if ctx.dry_run:
        print("would install %s %s for %s into %s" % (tool, lock.get("version"), platform_key(), tilde(dest_dir)))
        return 0
    info = install_from_lock(lock, tool, dest_dir, from_file=ns.from_, insecure=ns.insecure,
                             offline=ctx.offline, want_version=ns.want_version)
    st = S.load("_hub", None)
    st.tools[tool] = info
    st.save()
    print("installed %s %s -> %s" % (tool, info["version"], tilde(info["path"])))
    rc, out, _ = run_argv([info["path"], "--version"], timeout=10)
    if rc == 0 and out.strip():
        print(out.strip().splitlines()[0])
    return 0
