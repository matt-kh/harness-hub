"""``harness release check | notes``: the preflight and the notes of a tag-driven release.

``check [TAG]`` (default: the tag on HEAD) reports a problem (exit 1) when

1. TAG is not SemVer 2.0.0 with a leading ``v`` (``vX.Y.Z`` or ``vX.Y.Z-pre.N``), or carries
   ``+build`` metadata (tag names stay comparable across forges)
2. TAG does not exist or is lightweight (releases need an annotated tag; a signed tag is
   reported, not required)
3. ``VERSION`` at TAG (and in the working tree when HEAD is the tag commit) is not TAG
   without the ``v``
4. ``CHANGELOG.md`` at TAG has no ``## [X.Y.Z] - YYYY-MM-DD`` heading with a valid date, or
   its ``[Unreleased]`` section still holds entries (warning: the ``[X.Y.Z]: …`` link line
   is missing)
5. ``local/`` is tracked at TAG or anywhere in its history
6. the working tree is dirty (warning: HEAD is not the tag commit)
7. unless ``--no-remote``: TAG's commit is not on ``REMOTE/BRANCH`` after ``git fetch``
8. two ``tools/*.lock.json`` assets of the release platforms share a basename (GitHub
   release assets are flat)

``--json`` adds ``prerelease`` for the workflow. ``notes TAG [--dir DIR] [--out FILE]`` prints
the release notes: the CHANGELOG section of TAG, install lines for the ``.run`` and the bundle,
the verification commands and, with ``--dir``, the release directory's ``SHA256SUMS``.
"""
from __future__ import annotations

import datetime
import json
import os
import re
from typing import Any, Dict, List, Optional

from . import pack as P
from .upgrade import changelog_section
from .util import SEMVER_RE, HarnessError, atomic_write, hub_home, is_prerelease, parse_semver, tilde

RELEASE_PLATFORMS = ("linux/amd64", "linux/arm64", "darwin/amd64", "darwin/arm64")
_UNRELEASED_RE = re.compile(r"(?ms)^## \[Unreleased\][^\n]*\n(.*?)(?=^## |\Z)")


def _git(root: str, args: List[str]):
    return P._git(args, cwd=root, timeout=120)


def _show(root: str, rev_path: str) -> Optional[str]:
    rc, out, _e = _git(root, ["show", rev_path])
    return out if rc == 0 else None


def _rev(root: str, rev: str) -> Optional[str]:
    rc, out, _e = _git(root, ["rev-parse", "--verify", "-q", rev])
    return out.strip() if rc == 0 and out.strip() else None


def head_tag(root: str) -> Optional[str]:
    rc, out, _e = _git(root, ["describe", "--tags", "--exact-match", "HEAD"])
    return out.strip() if rc == 0 and out.strip() else None


def tool_asset_clashes(root: str, platforms=RELEASE_PLATFORMS) -> List[str]:
    from . import tools as T

    seen: Dict[str, str] = {}
    clashes: List[str] = []
    tdir = os.path.join(root, "tools")
    locks = sorted(f[:-len(".lock.json")] for f in os.listdir(tdir) if f.endswith(".lock.json")) \
        if os.path.isdir(tdir) else []
    for tool in locks:
        assets = (T.load_lock(root, tool) or {}).get("assets") or {}
        for key in platforms:
            a = assets.get(key)
            if not a:
                continue
            base = os.path.basename(a["url"].split("?", 1)[0])
            where = "%s %s" % (tool, key)
            if base in seen:
                clashes.append("%s and %s both ship tools/%s" % (seen[base], where, base))
            else:
                seen[base] = where
    return clashes


def check(home: str, tag: Optional[str] = None, remote: str = "origin", branch: str = "main",
          fetch: bool = True) -> Dict[str, Any]:
    root = P.repo_root(home)
    res: Dict[str, Any] = {"tag": tag, "version": None, "commit": None, "prerelease": False,
                           "problems": [], "warnings": [], "info": [], "ok": False}
    problems, warnings, info = res["problems"], res["warnings"], res["info"]

    def done() -> Dict[str, Any]:
        res["ok"] = not problems
        return res

    if not tag:
        tag = head_tag(root)
        res["tag"] = tag
        if not tag:
            problems.append("HEAD carries no tag; pass TAG, or tag the release commit first: "
                            "git tag -a vX.Y.Z -m \"harness-hub vX.Y.Z\"")
            return done()
    # 1. SemVer 2.0.0, mandatory v, no +build
    v = parse_semver(tag)
    if not tag.startswith("v") or v is None or not SEMVER_RE.match(tag):
        problems.append("tag %s is not SemVer 2.0.0 with a leading v; use vX.Y.Z or vX.Y.Z-rc.N "
                        "(git tag -d %s, then git tag -a vX.Y.Z -m ...)" % (tag, tag))
        return done()
    if v[4]:
        problems.append("tag %s carries +build metadata; release tags are vX.Y.Z[-pre] only "
                        "(re-tag without the +%s part)" % (tag, v[4]))
    version = tag[1:].split("+", 1)[0]
    res["version"] = version
    res["prerelease"] = is_prerelease(tag)
    # 2. annotated (signed optional)
    _rc, out, _e = _git(root, ["for-each-ref", "--format=%(objecttype)", "refs/tags/%s" % tag])
    kind = out.strip()
    if not kind:
        problems.append("tag %s does not exist; create it on the release commit: git tag -a %s -m \"harness-hub %s\""
                        % (tag, tag, tag))
        return done()
    if kind != "tag":
        problems.append("tag %s is lightweight; releases need an annotated tag: git tag -d %s && git tag -a %s -m "
                        "\"harness-hub %s\"" % (tag, tag, tag, tag))
    else:
        _rc, raw, _e = _git(root, ["cat-file", "tag", "refs/tags/%s" % tag])
        if "-----BEGIN" in raw and "SIGNATURE-----" in raw:
            rc3, o3, e3 = _git(root, ["tag", "-v", tag])
            last = ((e3 or o3).strip().splitlines() or ["(no output)"])[-1]
            info.append("signed tag: git tag -v %s %s: %s" % (tag, "ok" if rc3 == 0 else "failed", last))
        else:
            info.append("annotated tag (not signed; signing is optional)")
    commit = _rev(root, "refs/tags/%s^{commit}" % tag)
    res["commit"] = commit
    head = _rev(root, "HEAD")
    # 3. VERSION
    at_tag = (_show(root, "%s:VERSION" % tag) or "").strip()
    if at_tag != version:
        problems.append("VERSION at %s is %r, want %r; bump VERSION in the release PR, merge, then re-tag"
                        % (tag, at_tag or "(missing)", version))
    if head == commit:
        try:
            with open(os.path.join(root, "VERSION"), encoding="utf-8") as fh:
                wt = fh.read().strip()
        except OSError:
            wt = ""
        if wt != version:
            problems.append("working-tree VERSION is %r, want %r; restore it (git checkout -- VERSION)" % (wt, version))
    # 4. CHANGELOG
    log = _show(root, "%s:CHANGELOG.md" % tag) or ""
    m = re.search(r"(?m)^## \[%s\] - (\S+)\s*$" % re.escape(version), log)
    if not m:
        problems.append("CHANGELOG.md at %s has no '## [%s] - YYYY-MM-DD' heading; rename [Unreleased] to it in the "
                        "release PR" % (tag, version))
    else:
        try:
            datetime.datetime.strptime(m.group(1), "%Y-%m-%d")
        except ValueError:
            problems.append("CHANGELOG.md heading for %s has date %r; write YYYY-MM-DD" % (version, m.group(1)))
    um = _UNRELEASED_RE.search(log)
    if um is None:
        warnings.append("CHANGELOG.md at %s has no '## [Unreleased]' section; add an empty one above [%s]"
                        % (tag, version))
    else:
        left = [ln for ln in um.group(1).splitlines() if re.match(r"^(### |\s*[-*] )", ln)]
        if left:
            problems.append("CHANGELOG.md [Unreleased] still holds %d heading/bullet line(s) (first: %r); move them "
                            "into [%s] in the release PR" % (len(left), left[0].strip(), version))
    if log and not re.search(r"(?m)^\[%s\]:\s*\S" % re.escape(version), log):
        warnings.append("CHANGELOG.md has no '[%s]: <compare URL>' link line; add it in the next PR" % version)
    # 5. local/
    leaked = P.local_paths(root, ["refs/tags/%s" % tag])
    if leaked:
        problems.append("local/ is tracked at %s (%s); remove it from history before releasing"
                        % (tag, ", ".join(leaked[:3])))
    # 6. working tree
    dirty = P.dirty_paths(root)
    if dirty:
        problems.append("working tree is dirty (%d path(s), first: %s); commit or stash first"
                        % (len(dirty), dirty[0].strip()))
    if head != commit:
        warnings.append("HEAD (%s) is not the tag commit (%s); the checks read the tag, not the working tree"
                        % ((head or "?")[:7], (commit or "?")[:7]))
    # 7. on REMOTE/BRANCH
    if fetch:
        rc, _o, e = _git(root, ["fetch", "--quiet", remote, branch])
        if rc != 0:
            warnings.append("git fetch %s %s failed (%s); checked the local %s/%s ref"
                            % (remote, branch, (e.strip().splitlines() or ["rc=%d" % rc])[-1], remote, branch))
        ref = "refs/remotes/%s/%s" % (remote, branch)
        if not _rev(root, ref):
            problems.append("%s/%s is unknown; fetch it (git fetch %s %s) or pass --no-remote for a local rehearsal"
                            % (remote, branch, remote, branch))
        else:
            rc, _o, _e = _git(root, ["merge-base", "--is-ancestor", "%s^{commit}" % tag, ref])
            if rc != 0:
                problems.append("%s is not on %s/%s; tag the merge commit on %s (releases come from %s only)"
                                % (tag, remote, branch, branch, branch))
    # 8. flat asset names
    for c in tool_asset_clashes(root):
        problems.append("release assets must have unique basenames: %s; rename one in its tools/*.lock.json" % c)
    return done()


def _repo_slug(root: str) -> str:
    env = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if env:
        return env
    rc, out, _e = _git(root, ["remote", "get-url", "origin"])
    m = re.search(r"github\.com[:/]([^/\s]+/[^/\s]+?)(?:\.git)?/?$", out.strip()) if rc == 0 else None
    return m.group(1) if m else "OWNER/REPO"


def notes(home: str, tag: str, rel_dir: Optional[str] = None) -> str:
    root = P.repo_root(home)
    version = tag.lstrip("v").split("+", 1)[0]
    log = _show(root, "%s:CHANGELOG.md" % tag)
    if log is None:
        raise HarnessError("cannot read CHANGELOG.md at %s; does the tag exist? (git tag -l %s)" % (tag, tag))
    body = changelog_section(log, version)
    if body is None:
        raise HarnessError("CHANGELOG.md at %s has no [%s] section; run harness release check %s" % (tag, version, tag))
    slug = _repo_slug(root)
    bundle, run = "harness-hub-%s.bundle" % tag, P.run_name(tag)
    have_run = rel_dir is None or os.path.isfile(os.path.join(rel_dir, run))
    lines = ["# harness-hub %s" % tag, ""]
    if is_prerelease(tag):
        lines += ["> Pre-release: `harness upgrade` (default `--to latest`) skips it; "
                  "use `harness upgrade --to %s` to try it." % tag, ""]
    lines += [body, "", "## Install", ""]
    if have_run:
        lines += ["One file (git, bash, python3 >= 3.9 and jq on the target machine):", "", "```sh",
                  "sh %s --check" % run,
                  "sh %s --dest ~/harness-hub --offline --no-install-tools" % run,
                  "```", "",
                  "Run a newer `.run` with the same `--dest` to upgrade that clone.", ""]
    lines += ["From the bundle:", "", "```sh",
              "shasum -a 256 -c SHA256SUMS            # or: sha256sum -c SHA256SUMS",
              "git clone -b %s %s ~/harness-hub" % (tag, bundle),
              "~/harness-hub/bootstrap",
              "```", "",
              "Upgrade an existing hub: `harness upgrade --to %s`." % tag, "",
              "## Verify", "", "```sh",
              "harness verify %s                 # git bundle verify + SHA256SUMS (offline)" % bundle,
              "gh attestation verify %s -R %s    # build provenance (online)" % (bundle, slug),
              "```"]
    if rel_dir:
        sums = os.path.join(rel_dir, "SHA256SUMS")
        try:
            with open(sums, encoding="utf-8") as fh:
                text = fh.read().rstrip("\n")
        except OSError:
            raise HarnessError("%s: no SHA256SUMS; run harness pack --out %s first" % (tilde(rel_dir), tilde(rel_dir)))
        lines += ["", "## SHA256SUMS", "", "```", text, "```"]
    return "\n".join(lines) + "\n"


def run(ctx: Any, ns: Any) -> int:
    home = hub_home()
    if ns.action == "check":
        res = check(home, ns.tag, remote=ns.remote, branch=ns.branch, fetch=not ns.no_remote)
        if ctx.json:
            print(json.dumps(res, indent=2, sort_keys=True))
        else:
            for i in res["info"]:
                print("info  %s" % i)
            for w in res["warnings"]:
                print("WARN  %s" % w)
            for p in res["problems"]:
                print("FAIL  %s" % p)
            print("release check: %s %s%s" % (res["tag"] or "(no tag)", "ok" if res["ok"] else "FAILED",
                                              " (pre-release)" if res["prerelease"] else ""))
        return 0 if res["ok"] else 1
    if ns.action == "notes":
        text = notes(home, ns.tag, rel_dir=os.path.abspath(ns.dir) if ns.dir else None)
        if ns.out:
            atomic_write(os.path.abspath(ns.out), text.encode("utf-8"), mode=0o644)
            print("wrote %s" % tilde(os.path.abspath(ns.out)))
        else:
            print(text, end="")
        return 0
    raise HarnessError("usage: harness release check [TAG] | notes TAG [--dir DIR] [--out FILE]", 2)
