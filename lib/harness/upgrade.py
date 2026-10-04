"""upgrade: move the hub checkout forward, print migration notes, re-validate, plan, apply, doctor.

``--to TARGET`` (default ``latest``):

* ``latest``: ``git fetch --tags`` (skipped offline), then check out the newest release tag
  (highest SemVer 2.0.0 tag; pre-releases such as ``v1.3.0-rc.1`` are skipped). Without any
  release tag the error names ``--to BRANCH`` and the bundle-file flow. It never moves
  backwards: when ``VERSION`` at that tag is not newer than the checkout's (a contributor on
  ``main`` ahead of the last release), it says so and exits 0 without planning.
* ``TAG``: ``git fetch --tags`` then ``git checkout TAG`` (detached, pinned). When the fetch
  fails (air-gapped: ``origin`` unreachable) and TAG already exists in the clone, the local
  tag is used; when it does not, the error names the bundle-file flow (``origin`` ->
  ``NEW.bundle``, or ``git fetch NEW.bundle 'refs/tags/*:refs/tags/*'``)
* ``BRANCH`` (a local branch, e.g. ``main``): ``git checkout BRANCH`` + ``git pull --ff-only``
  (refuses on local changes), for contributors following the branch

Then: prints every ``## [X.Y.Z]`` section of CHANGELOG.md between the old and new VERSION,
re-validates the config (deprecations warn) and shows the plan; applies unless ``--no-apply``
or ``--dry-run`` (``--yes`` skips the confirmation) and runs ``harness doctor`` after a
successful apply (its exit status is the command's).
"""
from __future__ import annotations

import re
from typing import Any, List, Optional, Tuple

from .util import HarnessError, parse_semver, read_text, run_argv, version_key

_SECTION_RE = r"(?m)^## \[?v?([0-9][^\]\s]*)\]?.*$"


def changelog_between(text: str, old: str, new: str) -> List[Tuple[str, str]]:
    """Sections ``## [ver]`` with old < ver <= new (SemVer precedence), newest first."""
    out: List[Tuple[str, str]] = []
    parts = re.split(_SECTION_RE, text)
    # parts = [preamble, ver1, body1, ver2, body2, ...]
    lo, hi = version_key(old), version_key(new)
    for i in range(1, len(parts) - 1, 2):
        ver, body = parts[i], parts[i + 1]
        v = version_key(ver)
        if lo < v <= hi:
            out.append((ver, body.strip()))
    return out


def changelog_section(text: str, version: str) -> Optional[str]:
    """The body of the ``## [version]`` section (exact match, leading ``v`` ignored), or None."""
    want = version.lstrip("v")
    parts = re.split(_SECTION_RE, text)
    for i in range(1, len(parts) - 1, 2):
        if parts[i].lstrip("v") == want:
            body = parts[i + 1]
            # link reference definitions at the end of the file belong to no section
            body = re.split(r"(?m)^\[[^\]]+\]:\s", body)[0]
            return body.strip()
    return None


# ----------------------------------------------------------------- targets


def _git(home: str, args: List[str], timeout: float = 30) -> Tuple[int, str, str]:
    return run_argv(["git", "-C", home] + args, timeout=timeout)


def local_tags(home: str) -> List[str]:
    rc, out, _e = _git(home, ["tag", "--list"])
    return [t for t in out.split() if t] if rc == 0 else []


def latest_release_tag(home: str) -> Optional[str]:
    """Highest SemVer release tag (``vX.Y.Z``) in the clone; pre-releases are skipped."""
    best: Optional[str] = None
    for tag in local_tags(home):
        v = parse_semver(tag)
        if not v or v[3] or not tag.startswith("v"):
            continue
        if best is None or version_key(tag) > version_key(best):
            best = tag
    return best


def is_branch(home: str, name: str) -> bool:
    rc, _o, _e = _git(home, ["show-ref", "--verify", "-q", "refs/heads/%s" % name])
    return rc == 0


def fetch_tags(home: str, offline: bool = False) -> Tuple[bool, str]:
    """``git fetch --tags``; returns (ok, last error line). Skipped (not ok) when offline."""
    if offline:
        return False, "offline"
    rc, _o, e = _git(home, ["fetch", "--tags", "--quiet"], timeout=300)
    return rc == 0, (e.strip().splitlines() or ["rc=%d" % rc])[-1] if rc else ""


def _bundle_flow(home: str, to: str) -> str:
    return ("git -C %s remote set-url origin /path/NEW.bundle (or git -C %s fetch /path/NEW.bundle "
            "'refs/tags/*:refs/tags/*'), then re-run harness upgrade --to %s (see docs/runbooks/air-gapped.md)"
            % (home, home, to))


def checkout_tag(home: str, tag: str, log=print, offline: bool = False, fetch: bool = True) -> None:
    """``git fetch --tags`` (tolerated offline when ``tag`` is already local) + checkout.

    ``fetch=False`` skips the fetch (the caller already fetched, e.g. ``resolve_target``).
    """
    ok, why = fetch_tags(home, offline) if fetch else (True, "")
    have, _o, _e = _git(home, ["rev-parse", "--verify", "-q", "%s^{commit}" % tag])
    if have != 0:
        if not ok:
            raise HarnessError(
                "git fetch --tags failed (%s) and %s is not in the clone. Offline, take it from a bundle file: %s"
                % (why, tag, _bundle_flow(home, tag)))
        raise HarnessError(
            "no branch or tag %s in %s (a clone made from a tag-only bundle has no branches); use --to TAG "
            "(git -C %s tag lists them) or --to latest" % (tag, home, home), 2)
    if not ok:
        log("note: %s; using local tag %s" % ("offline" if why == "offline" else "fetch failed", tag))
    rc, _o, e = _git(home, ["-c", "advice.detachedHead=false", "checkout", "--quiet", tag], timeout=300)
    if rc != 0:
        raise HarnessError("checkout --quiet %s failed: %s" % (tag, e.strip()))


def resolve_target(home: str, to: Optional[str], offline: bool = False, log=print) -> Tuple[str, str]:
    """``("tag", "vX.Y.Z")`` or ``("branch", "main")`` for ``--to`` (None = ``latest``)."""
    if not to or to == "latest":
        ok, why = fetch_tags(home, offline)
        if not ok and why != "offline":
            log("note: git fetch --tags failed (%s); choosing among the local tags" % why)
        tag = latest_release_tag(home)
        if not tag:
            raise HarnessError(
                "no release tag (vX.Y.Z) in %s. Follow a branch with harness upgrade --to main, pick a tag with "
                "--to TAG, or bring a newer release from a bundle file: %s" % (home, _bundle_flow(home, "latest")))
        return "tag", tag
    if is_branch(home, to):
        return "branch", to
    rc, _o, _e = _git(home, ["show-ref", "--verify", "-q", "refs/remotes/origin/%s" % to])
    if rc == 0:
        return "branch", to  # git checkout creates the tracking branch
    return "tag", to


def tag_version(home: str, tag: str) -> str:
    """``VERSION`` as committed at ``tag``; the tag name without ``v`` when it has none."""
    rc, out, _e = _git(home, ["show", "%s:VERSION" % tag])
    text = out.strip() if rc == 0 else ""
    if text:
        return text
    return tag[1:] if tag.startswith("v") else tag


def newer_release(home: str, tag: str, current: str) -> bool:
    """True when ``tag`` (by its committed VERSION) has higher SemVer precedence than ``current``."""
    return version_key(tag_version(home, tag)) > version_key(current)


def run(ctx: Any, ns: Any) -> int:
    import subprocess
    import sys

    from .util import hub_home

    home = hub_home()
    old = (read_text(home + "/VERSION") or "0.0.0").strip()
    rc, out, err = run_argv(["git", "-C", home, "status", "--porcelain", "--untracked-files=no"], timeout=30)
    if rc != 0:
        raise HarnessError("%s is not a git checkout: %s" % (home, err.strip()))
    if out.strip() and not ctx.dry_run:
        raise HarnessError("the hub has local changes; commit or stash them first:\n" + out)
    to = getattr(ns, "to", None)
    if ctx.dry_run:
        if not to or to == "latest":
            what = "fetch tags and check out the newest release tag (now: %s)" % (latest_release_tag(home) or "none local")
        elif is_branch(home, to):
            what = "check out branch %s and git pull --ff-only" % to
        else:
            what = "fetch tags and check out %s" % to
        print("dry run: would %s" % what)
    else:
        kind, target = resolve_target(home, to, offline=ctx.offline)
        if kind == "tag" and (not to or to == "latest") and not newer_release(home, target, old):
            # --to latest never moves backwards; an explicit --to TAG still pins (and may downgrade)
            print("hub %s is at or ahead of the newest release %s; nothing to upgrade "
                  "(pin with --to TAG, follow a branch with --to BRANCH)" % (old, target))
            return 0
        if kind == "branch":
            rc, _o, e = run_argv(["git", "-C", home, "checkout", "--quiet", target], timeout=120)
            if rc != 0:
                raise HarnessError("git checkout %s failed: %s" % (target, e.strip()))
            rc, _o, e = run_argv(["git", "-C", home, "pull", "--ff-only", "--quiet"], timeout=300)
            if rc != 0:
                raise HarnessError("git pull --ff-only on %s failed: %s; fix the branch (or use --to TAG)"
                                   % (target, e.strip()))
        else:
            # resolve_target already fetched for latest; fetch only for an explicit tag
            checkout_tag(home, target, offline=ctx.offline, fetch=bool(to and to != "latest"))
        print("now at %s %s" % (kind, target))
    new = (read_text(home + "/VERSION") or old).strip()
    print("hub %s -> %s" % (old, new))
    for ver, body in changelog_between(read_text(home + "/CHANGELOG.md") or "", old, new):
        print("\n## %s\n%s" % (ver, body))
    # re-exec so the new engine code is the one that plans
    tail = ["--config", ctx.config] if ctx.config else []
    sys.stdout.flush()  # our lines before the children's
    rc = subprocess.call(["bash", home + "/bin/harness", "plan"] + tail)
    if rc == 1:
        return 1
    if ns.no_apply or ctx.dry_run:
        return 0
    apply_argv = ["bash", home + "/bin/harness", "apply"] + tail + (["--yes"] if ctx.yes else [])
    rc = subprocess.call(apply_argv)
    if rc != 0:
        return rc
    return subprocess.call(["bash", home + "/bin/harness", "doctor"] + (["--offline"] if ctx.offline else []) + tail)
