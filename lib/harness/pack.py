"""``harness pack`` / ``harness verify``: the hub as one verifiable file (ARCHITECTURE §10).

A release artifact is a directory::

    harness-hub-<version>.bundle   git bundle: branches + tags + HEAD (history included)
    tools/<asset>                  optional: lock-file assets for the --tools platforms
    INSTALL.txt                    verify / clone / bootstrap, in three lines
    SHA256SUMS                     sha256 of every file above (``sha256sum -c`` / ``shasum -a 256 -c``)

``pack`` refuses on a dirty working tree (uncommitted or untracked files would silently be
left out) and when any bundled ref has ever tracked a ``local/`` path (the private overlay
never leaves the workstation). The ``local/`` check runs twice: on the refs before the bundle
is written and on the heads the finished bundle lists.

``--tools linux/amd64,darwin/arm64`` downloads every ``tools/*.lock.json`` asset for those
platforms with the same code and sha256 check as ``harness install``. Offline (``--offline``)
or on a network failure the bundle is still written, the missing assets are listed and the
exit status is 1; without ``--tools`` nothing is downloaded and the exit status is 0.

``verify FILE.bundle`` runs ``git bundle verify`` (in a throw-away repository, so it works
anywhere), prints the heads and tags and, when a ``SHA256SUMS`` sits beside the file, checks
every entry whose file is present.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .util import HarnessError, atomic_write, hub_home, run_argv, tilde

PLATFORM_RE = re.compile(r"^(linux|darwin)/(amd64|arm64)$")
GIT_TIMEOUT = 600.0


def _git(args: Sequence[str], cwd: Optional[str] = None, timeout: float = GIT_TIMEOUT) -> Tuple[int, str, str]:
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", LC_ALL="C")
    return run_argv(["git"] + list(args), timeout=timeout, cwd=cwd, env=env)


def _git_ok(args: Sequence[str], cwd: Optional[str] = None) -> str:
    rc, out, err = _git(args, cwd=cwd)
    if rc != 0:
        raise HarnessError("git %s failed: %s" % (" ".join(args), (err or out).strip().splitlines()[-1:] or rc))
    return out


def sha256_path(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ----------------------------------------------------------------- checks


def repo_root(home: str) -> str:
    rc, out, _ = _git(["rev-parse", "--show-toplevel"], cwd=home)
    if rc != 0:
        raise HarnessError("%s is not a git checkout; pack needs the hub's own repository" % tilde(home))
    return out.strip()


def dirty_paths(root: str) -> List[str]:
    out = _git_ok(["status", "--porcelain", "--untracked-files=normal"], cwd=root)
    return [ln for ln in out.splitlines() if ln.strip()]


def local_paths(root: str, revs: Sequence[str]) -> List[str]:
    """``local/`` paths tracked at any of ``revs`` or anywhere in their history."""
    found: List[str] = []
    for rev in revs:
        out = _git_ok(["ls-tree", "-r", "--name-only", rev, "--", "local"], cwd=root)
        found += ["%s:%s" % (rev, p) for p in out.splitlines() if p.strip()]
    if revs:
        out = _git_ok(["log", "--format=%h", "--name-only"] + list(revs) + ["--", "local"], cwd=root)
        hist = [ln for ln in out.splitlines() if ln.startswith("local/")]
        found += ["history:%s" % p for p in sorted(set(hist))]
    return found


def bundle_heads(path: str) -> List[Tuple[str, str]]:
    rc, out, err = _git(["bundle", "list-heads", path])
    if rc != 0:
        raise HarnessError("git bundle list-heads %s: %s" % (tilde(path), (err or out).strip()))
    heads = []
    for ln in out.splitlines():
        parts = ln.split(None, 1)
        if len(parts) == 2:
            heads.append((parts[0], parts[1].strip()))
    return heads


def git_bundle_verify(path: str) -> Tuple[bool, str]:
    """``git bundle verify`` needs a repository: use an empty throw-away one."""
    tmp = tempfile.mkdtemp(prefix="harness-verify-")
    try:
        _git_ok(["init", "-q", tmp])
        rc, out, err = _git(["bundle", "verify", os.path.abspath(path)], cwd=tmp)
        text = (out + err).strip()
        return rc == 0, text
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def read_sums(path: str) -> Dict[str, str]:
    sums: Dict[str, str] = {}
    with open(path, encoding="utf-8") as fh:
        for ln in fh:
            m = re.match(r"^([0-9a-fA-F]{64})\s+\*?(.+?)\s*$", ln)
            if m:
                sums[m.group(2)] = m.group(1).lower()
    return sums


# ----------------------------------------------------------------- pack


def release_version(root: str, tag: Optional[str]) -> str:
    if tag:
        return tag
    rc, out, _ = _git(["describe", "--tags", "--exact-match", "HEAD"], cwd=root)
    if rc == 0 and out.strip():
        return out.strip()
    try:
        with open(os.path.join(root, "VERSION"), encoding="utf-8") as fh:
            base = fh.read().strip() or "0.0.0"
    except OSError:
        base = "0.0.0"
    sha = _git_ok(["rev-parse", "--short=7", "HEAD"], cwd=root).strip()
    return "v%s-g%s" % (base.lstrip("v"), sha)


def install_text(name: str, version: str, tag: Optional[str], tool_files: Sequence[str]) -> str:
    clone = "git clone %s%s ~/harness-hub" % ("-b %s " % tag if tag else "", name)
    lines = [
        "harness-hub %s: the whole hub as one git repository file (git bundle)." % version,
        "",
        "Install (git, bash, python3 >= 3.9 and jq on the target machine):",
        "",
        "  shasum -a 256 -c SHA256SUMS            # or: sha256sum -c SHA256SUMS",
        "  %s" % clone,
        "  ~/harness-hub/bootstrap --offline --no-install-tools",
        "",
        "From an existing hub instead of the last two lines:",
        "  harness bootstrap --from %s --dest ~/harness-hub --offline" % name,
        "",
        "Check the bundle itself: harness verify %s  (or `git bundle verify` inside any repository)" % name,
        "Upgrade a clone offline with a newer bundle file:",
        "  git -C ~/harness-hub remote set-url origin /path/NEW.bundle",
        "    (or: git -C ~/harness-hub fetch /path/NEW.bundle 'refs/tags/*:refs/tags/*')",
        "  harness upgrade --to <tag>",
    ]
    if tool_files:
        lines += ["", "Pinned tools (sha256 from tools/<tool>.lock.json, also listed in SHA256SUMS):"]
        for t in tool_files:
            lines.append("  harness install <tool> --from %s" % t)
    lines += ["", "Docs: docs/distribution.md and docs/runbooks/air-gapped.md inside the clone."]
    return "\n".join(lines) + "\n"


def fetch_tools(root: str, out_dir: str, platforms: Sequence[str], offline: bool,
                log=print) -> Tuple[List[str], List[str]]:
    """Download lock-file assets. Returns (written relative paths, problems)."""
    from . import tools as T

    written: List[str] = []
    problems: List[str] = []
    locks = sorted(f[:-len(".lock.json")] for f in os.listdir(os.path.join(root, "tools"))
                   if f.endswith(".lock.json")) if os.path.isdir(os.path.join(root, "tools")) else []
    mirror = os.environ.get("HARNESS_TOOLS_MIRROR")
    for tool in locks:
        lock = T.load_lock(root, tool) or {}
        for key in platforms:
            asset = (lock.get("assets") or {}).get(key)
            if not asset:
                log("note  %s %s publishes no %s asset; skipped" % (tool, lock.get("version", ""), key))
                continue
            sha = (asset.get("sha256") or "").lower()
            if not lock.get("verified") or not sha:
                problems.append("%s %s: lock is not verified (no sha256); not shipped" % (tool, key))
                continue
            url = T.mirror_url(asset["url"], mirror)
            fname = os.path.basename(asset["url"].split("?", 1)[0]) or "%s-%s" % (tool, key.replace("/", "-"))
            rel = "tools/%s" % fname
            if offline:
                problems.append("%s %s: offline, not downloaded (%s)" % (tool, key, url))
                continue
            log("fetch %s" % url)
            try:
                data = T.download(url)
            except HarnessError as exc:
                problems.append("%s %s: %s" % (tool, key, exc))
                continue
            got = hashlib.sha256(data).hexdigest()
            if got != sha:
                problems.append("%s %s: sha256 mismatch (expected %s, got %s); not shipped" % (tool, key, sha, got))
                continue
            atomic_write(os.path.join(out_dir, rel), data, mode=0o644)
            written.append(rel)
    return written, problems


def pack(home: str, out_dir: str, tag: Optional[str] = None, platforms: Sequence[str] = (),
         offline: bool = False, log=print) -> Dict[str, Any]:
    root = repo_root(home)
    for p in platforms:
        if not PLATFORM_RE.match(p):
            raise HarnessError("--tools %s: want os/arch with os in linux|darwin and arch in amd64|arm64" % p, 2)
    dirty = dirty_paths(root)
    if dirty:
        shown = "\n  ".join(dirty[:20]) + ("\n  …" if len(dirty) > 20 else "")
        raise HarnessError("working tree is dirty; commit or stash first (a bundle carries commits only):\n  " + shown)
    if tag:
        rc, _o, _e = _git(["rev-parse", "--verify", "-q", "refs/tags/%s" % tag], cwd=root)
        if rc != 0:
            raise HarnessError("tag %s does not exist; create it first (git tag -a %s -m ...)" % (tag, tag), 2)
        refs = ["--tags"]
        revs = ["refs/tags/%s" % tag]
    else:
        # branches + tags + HEAD; remote-tracking refs and stashes are local bookkeeping
        refs = ["--branches", "--tags", "HEAD"]
        revs = [r for r in _git_ok(["for-each-ref", "--format=%(refname)", "refs/heads", "refs/tags"],
                                   cwd=root).split() if r] + ["HEAD"]
    leaked = local_paths(root, revs)
    if leaked:
        raise HarnessError("refusing to pack: local/ is tracked in the refs to bundle (%s); the private overlay "
                           "must stay gitignored — remove it from history first" % ", ".join(leaked[:5]))
    version = release_version(root, tag)
    name = "harness-hub-%s.bundle" % version
    out_dir = os.path.abspath(os.path.expanduser(out_dir))
    os.makedirs(out_dir, exist_ok=True)
    dest = os.path.join(out_dir, name)
    part = dest + ".part"
    rc, out, err = _git(["bundle", "create", "-q", part] + refs, cwd=root)
    if rc != 0:
        if os.path.exists(part):
            os.unlink(part)
        raise HarnessError("git bundle create failed: %s" % (err or out).strip())
    try:
        heads = bundle_heads(part)
        leaked = local_paths(root, [sha for sha, _r in heads])
        if leaked:
            raise HarnessError("refusing to pack: the bundle would carry local/ (%s)" % ", ".join(leaked[:5]))
        ok, text = git_bundle_verify(part)
        if not ok:
            raise HarnessError("git bundle verify failed: %s" % text)
    except HarnessError:
        os.unlink(part)
        raise
    os.replace(part, dest)
    log("bundle %s (%d head(s))" % (tilde(dest), len(heads)))
    tool_files: List[str] = []
    problems: List[str] = []
    if platforms:
        tool_files, problems = fetch_tools(root, out_dir, platforms, offline, log=log)
    else:
        log("note  no --tools given: tool archives not included (harness pack --tools linux/amd64,...)")
    atomic_write(os.path.join(out_dir, "INSTALL.txt"), install_text(name, version, tag, tool_files).encode("utf-8"), mode=0o644)
    files = [name, "INSTALL.txt"] + sorted(tool_files)
    sums = "".join("%s  %s\n" % (sha256_path(os.path.join(out_dir, f)), f) for f in files)
    atomic_write(os.path.join(out_dir, "SHA256SUMS"), sums.encode("utf-8"), mode=0o644)
    return {"bundle": dest, "version": version, "heads": [r for _s, r in heads], "files": files,
            "out": out_dir, "problems": problems}


# ----------------------------------------------------------------- verify


def verify(path: str) -> Dict[str, Any]:
    path = os.path.abspath(os.path.expanduser(path))
    if not os.path.isfile(path):
        raise HarnessError("%s: no such file" % tilde(path), 2)
    report: Dict[str, Any] = {"bundle": path, "ok": True, "problems": [], "warnings": []}
    ok, text = git_bundle_verify(path)
    report["git_verify"] = text
    if not ok:
        report["ok"] = False
        report["problems"].append("git bundle verify: %s" % (text.splitlines()[-1] if text else "failed"))
        return report
    heads = bundle_heads(path)
    report["heads"] = [r for _s, r in heads if not r.startswith("refs/tags/")]
    report["tags"] = [r[len("refs/tags/"):] for _s, r in heads if r.startswith("refs/tags/")]
    sums_path = os.path.join(os.path.dirname(path), "SHA256SUMS")
    report["sha256sums"] = os.path.isfile(sums_path)
    if report["sha256sums"]:
        sums = read_sums(sums_path)
        base = os.path.dirname(path)
        if os.path.basename(path) not in sums:
            report["warnings"].append("SHA256SUMS does not list %s" % os.path.basename(path))
        checked = []
        for rel, want in sorted(sums.items()):
            f = os.path.join(base, rel)
            if not os.path.isfile(f):
                report["warnings"].append("%s listed in SHA256SUMS is missing" % rel)
                continue
            got = sha256_path(f)
            if got != want:
                report["ok"] = False
                report["problems"].append("sha256 mismatch: %s" % rel)
            checked.append(rel)
        report["checked"] = checked
    return report


# ----------------------------------------------------------------- commands


def run_pack(ctx: Any, ns: Any) -> int:
    from .cli import _csv

    home = hub_home()
    out = ns.out or os.path.join(home, "build", "release")
    platforms = _csv(ns.tools)
    if ctx.dry_run:
        root = repo_root(home)
        dirty = dirty_paths(root)
        print("would pack %s into %s%s" % (tilde(root), tilde(out), " (refused: dirty tree)" if dirty else ""))
        return 1 if dirty else 0
    res = pack(home, out, tag=ns.tag, platforms=platforms, offline=ctx.offline)
    for p in res["problems"]:
        print("WARN  %s" % p)
    if ctx.json:
        print(json.dumps(res, indent=2, sort_keys=True))
    else:
        for f in res["files"] + ["SHA256SUMS"]:
            print("wrote %s" % tilde(os.path.join(res["out"], f)))
        print("pack: %s, %d file(s), %d tool problem(s)" % (res["version"], len(res["files"]) + 1, len(res["problems"])))
    return 1 if (platforms and res["problems"]) else 0


def run_verify(ctx: Any, ns: Any) -> int:
    res = verify(ns.file)
    if ctx.json:
        print(json.dumps(res, indent=2, sort_keys=True))
        return 0 if res["ok"] else 1
    print("bundle  %s" % tilde(res["bundle"]))
    for h in res.get("heads", []):
        print("head    %s" % h)
    for t in res.get("tags", []):
        print("tag     %s" % t)
    if res.get("sha256sums"):
        for rel in res.get("checked", []):
            print("sha256  %s" % rel)
    else:
        print("note    no SHA256SUMS beside the bundle; checked the bundle only")
    for w in res["warnings"]:
        print("WARN    %s" % w)
    for p in res["problems"]:
        print("FAIL    %s" % p)
    print("verify: %s" % ("ok" if res["ok"] else "FAILED"))
    return 0 if res["ok"] else 1
