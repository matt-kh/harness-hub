"""doctor: PASS/WARN/FAIL per check; every failure names the manual step that fixes it.

Built-in checks (ids in parentheses, usable in ``[doctor].warn_only``):

* runtime: ``python``, ``bash`` (reports whether bash >= 4 features are available), ``jq``, ``git``
* per active provider: ``provider-<p>`` binary + minimum version (WARN: the harness can
  render before the product is installed), ``hook-<p>`` rendered guard present, executable
  and matching the state sha, ``hook-entry-<p>`` hook registered in the provider config,
  ``conflicts-<p>`` conflicts recorded at the last apply
* ``~/.local/bin``: ``link-<name>`` for every link in the hub state, ``local-bin-path``
* per active bundle: ``bin-<bundle>-<binary>`` for ``[requires.binaries]`` and every
  ``[[doctor_checks]]`` (templated ``cmd`` via ``bash -c`` or ``script``, with a timeout)

A failing check whose ``fix`` names a manual step prints
``→ manual step <bundle>#<id>: <title> (docs/bundles/<b>.md#<id>)`` (title templated
against the config); any other ``fix`` is
printed as a command. ``--offline`` skips checks marked ``offline_skip``. Check scripts
exit 0 ok, 1 warn, 2+ fail. Output lines never echo secret-looking text.
"""
from __future__ import annotations

import json
import os
import platform
import re
import sys
from typing import Any, Dict, List, Optional, Sequence

from . import render as R
from . import state as S
from .util import (bin_dir, expand, first_line, paint, run_argv, run_shell, sha256_file, tilde,
                   version_ge, which)

DEFAULT_TIMEOUT = 10


class Result:
    def __init__(self, cid: str, status: str, detail: str = "", bundle: str = "", fix: str = "",
                 fix_line: str = ""):
        self.id = cid
        self.status = status  # PASS | WARN | FAIL | SKIP
        self.detail = detail
        self.bundle = bundle
        self.fix = fix
        self.fix_line = fix_line

    def to_json(self) -> Dict[str, Any]:
        return {"id": self.id, "status": self.status, "detail": self.detail, "bundle": self.bundle,
                "fix": self.fix, "fix_line": self.fix_line}


def fix_line(bundle: Any, fix: str, tpl: Optional[R.Templater] = None) -> str:
    """The hand-off line printed under a failing check (step title templated when ``tpl``)."""
    if not fix:
        return ""
    for step in bundle.manual_steps if bundle is not None else []:
        if step.get("id") == fix:
            title = step.get("title", "")
            if tpl is not None:
                title = tpl.expand(title, "%s manual_steps.%s.title" % (bundle.name, fix))
                tpl.missing = []
            return "→ manual step %s#%s: %s (%s#%s)" % (bundle.name, fix, title, bundle.docs_path(), fix)
    return "→ fix: %s" % fix


def _version_of(cmd: str, regex: Optional[str]) -> Optional[str]:
    rc, out, err = run_shell(cmd, timeout=DEFAULT_TIMEOUT)
    if rc != 0 and not out:
        return None
    text = out + err
    if regex:
        m = re.search(regex, text)
        return m.group(1) if m else None
    m = re.search(r"(\d+\.\d+(?:\.\d+)*)", text)
    return m.group(1) if m else None


class Doctor:
    def __init__(self, hub: Any, offline: bool = False, bundles: Optional[Sequence[str]] = None,
                 providers: Optional[Sequence[str]] = None):
        self.hub = hub
        self.offline = offline
        self.only_bundles = set(bundles or [])
        self.providers = hub.filter_providers(providers)
        self.results: List[Result] = []
        self.warn_only = set(hub.config.get("doctor.warn_only", []) or [])
        self._tpl: Optional[R.Templater] = None

    @property
    def tpl(self) -> R.Templater:
        if self._tpl is None:
            self._tpl = R.Templater(self.hub.template_context())
        return self._tpl

    # ---------------------------------------------------------------- recording
    def add(self, cid: str, status: str, detail: str = "", bundle: Any = None, fix: str = "") -> Result:
        bname = bundle.name if bundle is not None else ""
        if status == "FAIL" and (cid in self.warn_only or ("%s/%s" % (bname, cid)) in self.warn_only):
            status = "WARN"
            detail = (detail + " [warn_only]").strip()
        r = Result(cid, status, detail, bname, fix, fix_line(bundle, fix, self.tpl) if status in ("FAIL", "WARN") else "")
        self.results.append(r)
        return r

    # ---------------------------------------------------------------- checks
    def run(self) -> List[Result]:
        self.runtime()
        for p in self.providers:
            self.provider(p)
        self.links()
        for b in self.hub.active_bundles:
            if self.only_bundles and b.name not in self.only_bundles:
                continue
            self.binaries(b)
            self.bundle_checks(b)
        return self.results

    def runtime(self) -> None:
        self.add("python", "PASS", "python %s" % platform.python_version())
        rc, out, _ = run_argv(["bash", "-c", "echo ${BASH_VERSINFO[0]}.${BASH_VERSINFO[1]}"], timeout=5)
        ver = out.strip()
        if rc != 0:
            self.add("bash", "FAIL", "bash not runnable")
        elif not version_ge(ver, "3.2"):
            self.add("bash", "FAIL", "bash %s is older than 3.2" % ver)
        elif not version_ge(ver, "4.0"):
            self.add("bash", "PASS", "bash %s (bash >= 4 features such as mapfile are disabled)" % ver)
        else:
            self.add("bash", "PASS", "bash %s (bash >= 4 features available)" % ver)
        jq = which("jq")
        if jq:
            rc, out, _ = run_argv(["jq", "--version"], timeout=5)
            self.add("jq", "PASS", out.strip() or "jq present")
        else:
            self.add("jq", "FAIL", "jq missing: the guard hook denies every command without it",
                     fix="install jq (https://jqlang.org/download/)")
        self.add("git", "PASS" if which("git") else "WARN", "git present" if which("git") else "git missing")

    def provider(self, p: Any) -> None:
        cid = "provider-%s" % p.name
        if p.binary:
            path = which(p.binary)
            if not path:
                self.add(cid, "WARN", "%s not on PATH (install %s; rendered files are ready)" % (p.binary, p.summary or p.name))
            elif p.version_cmd and p.min_version:
                ver = _version_of(p.version_cmd, p.version_regex)
                if ver and version_ge(ver, p.min_version):
                    self.add(cid, "PASS", "%s %s" % (p.binary, ver))
                else:
                    self.add(cid, "WARN", "%s %s is older than %s (adapter: %s)" % (
                        p.binary, ver or "(unknown version)", p.min_version, p.verified or "unverified"))
            else:
                self.add(cid, "PASS", "%s present" % p.binary)
        st = S.load(p.name, p.home)
        hooks = p.target("hooks")
        if hooks:
            guard = os.path.join(expand(hooks["path"]), "guard-bash.sh")
            entry = st.get(guard)
            if not os.path.exists(guard):
                self.add("hook-%s" % p.name, "FAIL", "%s missing" % tilde(guard), fix="harness apply")
            elif not os.access(guard, os.X_OK):
                self.add("hook-%s" % p.name, "FAIL", "%s is not executable" % tilde(guard), fix="harness apply")
            elif entry is None:
                self.add("hook-%s" % p.name, "WARN", "%s is not managed by the harness (foreign)" % tilde(guard),
                         fix="harness apply --adopt %s" % tilde(guard))
            elif sha256_file(guard) != entry.get("sha256"):
                self.add("hook-%s" % p.name, "WARN", "%s was edited outside the harness" % tilde(guard),
                         fix="harness sync")
            else:
                self.add("hook-%s" % p.name, "PASS", "%s present, executable, matches state" % tilde(guard))
            self.hook_entry(p, hooks)
        else:
            self.add("hook-%s" % p.name, "PASS", "no command hook on %s: guard is advisory" % p.name)
        if st.conflicts:
            self.add("conflicts-%s" % p.name, "WARN", "%d conflict(s) at the last apply, e.g. %s" % (
                len(st.conflicts), st.conflicts[0][:120]), fix="harness plan")

    def hook_entry(self, p: Any, hooks: Dict[str, Any]) -> None:
        cid = "hook-entry-%s" % p.name
        if hooks.get("register", "settings") == "settings":
            st = p.target("settings")
            path = expand(st["path"]) if st else ""
        else:
            path = expand(hooks.get("register_path", ""))
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            json.loads(text)
        except FileNotFoundError:
            self.add(cid, "FAIL", "%s missing" % tilde(path), fix="harness apply")
            return
        except ValueError:
            self.add(cid, "FAIL", "%s does not parse as JSON" % tilde(path), fix="harness plan")
            return
        script = "shim.sh" if hooks.get("shim") else "guard-bash.sh"
        needle = os.path.join(expand(hooks["path"]), os.path.basename(hooks.get("shim") or script))
        if needle in text:
            self.add(cid, "PASS", "hook registered in %s" % tilde(path))
        else:
            self.add(cid, "FAIL", "%s does not reference %s" % (tilde(path), tilde(needle)), fix="harness apply")

    def links(self) -> None:
        st = S.load("_hub", None)
        for path in st.paths():
            entry = st.get(path) or {}
            if entry.get("mode") != "symlink":
                continue
            name = os.path.basename(path)
            want = entry.get("target", "")
            if not os.path.islink(path):
                self.add("link-%s" % name, "FAIL", "%s missing" % tilde(path), fix="harness apply")
            elif os.readlink(path) != want:
                self.add("link-%s" % name, "FAIL", "%s -> %s (expected %s)" % (tilde(path), os.readlink(path), tilde(want)),
                         fix="harness apply --adopt %s" % tilde(path))
            elif not os.path.exists(want):
                self.add("link-%s" % name, "FAIL", "%s -> %s (target missing)" % (tilde(path), tilde(want)), fix="harness apply")
            elif not os.access(want, os.X_OK):
                self.add("link-%s" % name, "FAIL", "%s is not executable" % tilde(want), fix="harness apply")
            else:
                self.add("link-%s" % name, "PASS", "%s -> %s" % (tilde(path), tilde(want)))
        bd = bin_dir()
        on_path = bd in (os.environ.get("PATH") or "").split(os.pathsep)
        self.add("local-bin-path", "PASS" if on_path else "WARN",
                 "%s %s PATH" % (tilde(bd), "on" if on_path else "not on"),
                 fix="" if on_path else 'add  export PATH="$HOME/.local/bin:$PATH"  to your shell profile')

    def binaries(self, b: Any) -> None:
        for name, spec in sorted(b.requires_binaries.items()):
            provs = spec.get("providers") or []
            if provs and not any(p.name in provs for p in self.providers):
                continue
            cid = "bin-%s-%s" % (b.name, name)
            install = spec.get("install")
            fix = "harness install %s" % install if install else ""
            sev = "WARN" if spec.get("optional") else "FAIL"
            if not which(name):
                self.add(cid, sev, "%s not on PATH%s" % (name, " (optional)" if spec.get("optional") else ""),
                         bundle=b, fix=self._fix_for_binary(b, name) or fix)
                continue
            want = spec.get("min_version")
            if want and spec.get("version_cmd"):
                have = _version_of(spec["version_cmd"], spec.get("version_regex"))
                if have and version_ge(have, want):
                    self.add(cid, "PASS", "%s %s" % (name, have), bundle=b)
                else:
                    self.add(cid, sev, "%s %s is older than %s" % (name, have or "(unknown)", want), bundle=b, fix=fix)
            else:
                self.add(cid, "PASS", "%s present" % name, bundle=b)

    @staticmethod
    def _fix_for_binary(b: Any, name: str) -> str:
        """Prefer a manual step whose id mentions the binary (install-gh)."""
        for step in b.manual_steps:
            sid = step.get("id", "")
            if sid in ("install-%s" % name, "%s-install" % name):
                return sid
        return ""

    def bundle_checks(self, b: Any) -> None:
        tpl = self.tpl
        env = dict(os.environ)
        env.setdefault("HARNESS_HOME", self.hub.home)
        # checks run the rendered tools against this config's own build products (hub.build_dir)
        env["HARNESS_CONFIG_JSON"] = os.path.join(self.hub.build_dir, "config.json")
        active = [p.name for p in self.providers]
        for chk in b.doctor_checks:
            cid = chk.get("id", "?")
            provs = chk.get("providers") or []
            if provs and not any(p in provs for p in active):
                continue
            sev = "FAIL" if chk.get("severity", "fail") == "fail" else "WARN"
            fix = chk.get("fix", "")
            if self.offline and chk.get("offline_skip"):
                self.add(cid, "SKIP", "offline", bundle=b)
                continue
            timeout = float(chk.get("timeout", DEFAULT_TIMEOUT))
            expect = chk.get("expect")
            if chk.get("script"):
                script = b.rel(chk["script"])
                rc, out, err = run_argv(["bash", script], timeout=timeout, env=env, cwd=b.path)
            else:
                cmd = tpl.expand(chk.get("cmd", ""), "%s doctor_checks.%s" % (b.name, cid))
                if tpl.missing:
                    self.add(cid, sev, "template key missing: %s" % tpl.missing[-1][1], bundle=b, fix=fix)
                    tpl.missing = []
                    continue
                rc, out, err = run_shell(cmd, timeout=timeout, env=env)
            line = first_line(out) or first_line(err)
            if rc == 124:
                self.add(cid, sev, "timed out after %ss" % int(timeout), bundle=b, fix=fix)
                continue
            if expect is None and chk.get("script"):
                status = "PASS" if rc == 0 else ("WARN" if rc == 1 else sev)
                self.add(cid, status, line if rc == 0 else "rc=%d %s" % (rc, line), bundle=b, fix=fix)
                continue
            expect = expect or {}
            ok = rc == int(expect.get("exit", 0))
            rx = expect.get("stdout_regex")
            if ok and rx and not re.search(rx, out + err):
                ok = False
                line = "output does not match /%s/" % rx
            if ok:
                self.add(cid, "PASS", line, bundle=b)
            else:
                self.add(cid, sev, "rc=%d %s" % (rc, line) if rc else line, bundle=b, fix=fix)


def run(hub: Any, offline: bool = False, as_json: bool = False, bundles: Optional[Sequence[str]] = None,
        providers: Optional[Sequence[str]] = None) -> int:
    doc = Doctor(hub, offline=offline, bundles=bundles, providers=providers)
    results = doc.run()
    fails = sum(1 for r in results if r.status == "FAIL")
    warns = sum(1 for r in results if r.status == "WARN")
    skips = sum(1 for r in results if r.status == "SKIP")
    passes = sum(1 for r in results if r.status == "PASS")
    if as_json:
        print(json.dumps({"fail": fails, "warn": warns, "pass": passes, "skip": skips,
                          "results": [r.to_json() for r in results]}, indent=2))
    else:
        for r in results:
            label = "%s/%s" % (r.bundle, r.id) if r.bundle else r.id
            print("%s  %-28s %s" % (paint(r.status, "%-4s" % r.status), label, r.detail))
            if r.fix_line:
                print("      %s" % r.fix_line)
        print("----")
        print("doctor: %d fail, %d warn, %d pass, %d skipped" % (fails, warns, passes, skips))
    sys.stdout.flush()
    return 1 if fails else 0
