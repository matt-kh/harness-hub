"""harness pack / verify / bootstrap --from against a throw-away fixture repository."""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import unittest

from helpers import REPO  # noqa: E402,F401  (puts lib/ on sys.path)

from harness import bootstrap as B
from harness import pack as P
from harness import test as T
from harness import upgrade as U
from harness.util import HarnessError

GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0",
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
}


def sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


class SuiteEnvTest(unittest.TestCase):
    def test_git_discovery_vars_are_dropped(self):
        saved = {k: os.environ.get(k) for k in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "KEEP_ME")}
        os.environ.update({"GIT_DIR": "/x/.git", "GIT_WORK_TREE": "/x", "GIT_INDEX_FILE": "/x/i", "KEEP_ME": "1"})
        try:
            env = T.suite_env("/hub", "/build")
        finally:
            for k, v in saved.items():
                os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        for k in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
            self.assertNotIn(k, env)
        self.assertEqual(env["KEEP_ME"], "1")
        self.assertEqual((env["HARNESS_HOME"], env["HARNESS_BUILD_DIR"]), ("/hub", "/build"))


class PackTest(unittest.TestCase):
    def setUp(self):
        self._env = {k: os.environ.get(k) for k in list(GIT_ENV) + ["HARNESS_TOOLS_MIRROR"] + list(T.GIT_DISCOVERY_ENV)}
        os.environ.update(GIT_ENV)
        os.environ.pop("HARNESS_TOOLS_MIRROR", None)
        # git exports these to hooks; left in place, the fixture repo below would be the real checkout
        for k in T.GIT_DISCOVERY_ENV:
            os.environ.pop(k, None)
        self.tmp = tempfile.mkdtemp(prefix="harness-pack-")
        self.repo = os.path.join(self.tmp, "hub")
        self.out = os.path.join(self.tmp, "rel")
        os.makedirs(os.path.join(self.repo, "tools"))
        self.write("VERSION", "1.2.3\n")
        self.write(".gitignore", "/local/\n/build/\n")
        self.write("bootstrap", "#!/usr/bin/env bash\necho fixture \"$@\"\n")
        self.write("bin/harness", "#!/usr/bin/env bash\necho \"harness-stub $*\"\n")
        self.write("local/harness.toml", "secret = 'never packed'\n")  # ignored  # pragma: allowlist secret
        self.git("init", "-q", "-b", "main")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "fixture")
        self.logs = []

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, rel, text, root=None):
        path = os.path.join(root or self.repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def git(self, *args, cwd=None):
        return subprocess.run(["git"] + list(args), cwd=cwd or self.repo, check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode()

    def pack(self, **kw):
        return P.pack(self.repo, self.out, log=self.logs.append, **kw)

    # ------------------------------------------------------------------ pack
    def test_pack_writes_bundle_sums_and_install(self):
        res = self.pack()
        head = self.git("rev-parse", "--short=7", "HEAD").strip()
        name = "harness-hub-1.2.3-g%s.bundle" % head
        self.assertEqual(os.path.basename(res["bundle"]), name)
        self.assertEqual(sorted(os.listdir(self.out)), sorted([name, "INSTALL.txt", "SHA256SUMS"]))
        sums = P.read_sums(os.path.join(self.out, "SHA256SUMS"))
        self.assertEqual(sorted(sums), sorted([name, "INSTALL.txt"]))
        for rel, want in sums.items():
            self.assertEqual(sha(os.path.join(self.out, rel)), want)
        self.assertIn("git clone %s ~/harness-hub" % name, self.read(os.path.join(self.out, "INSTALL.txt")))
        self.assertIn("refs/heads/main", res["heads"])
        self.assertIn("HEAD", res["heads"])

    def test_exact_tag_names_the_bundle(self):
        self.git("tag", "-a", "1.2.3", "-m", "r")
        res = self.pack()
        self.assertTrue(res["bundle"].endswith("harness-hub-1.2.3.bundle"))

    def test_tag_mode(self):
        self.git("tag", "-a", "1.2.3", "-m", "r")
        res = self.pack(tag="1.2.3")
        self.assertEqual(res["heads"], ["refs/tags/1.2.3"])
        self.assertIn("git clone -b 1.2.3 ", self.read(os.path.join(self.out, "INSTALL.txt")))
        with self.assertRaises(HarnessError):
            self.pack(tag="9.9.9")

    def test_verify_ok(self):
        res = self.pack()
        rep = P.verify(res["bundle"])
        self.assertTrue(rep["ok"], rep)
        self.assertTrue(rep["sha256sums"])
        self.assertIn(os.path.basename(res["bundle"]), rep["checked"])
        self.assertIn("refs/heads/main", rep["heads"])

    def test_verify_detects_tampering(self):
        res = self.pack()
        with open(os.path.join(self.out, "INSTALL.txt"), "a", encoding="utf-8") as fh:
            fh.write("tampered\n")
        rep = P.verify(res["bundle"])
        self.assertFalse(rep["ok"])
        self.assertIn("sha256 mismatch: INSTALL.txt", rep["problems"])

    def test_verify_rejects_garbage(self):
        bad = self.write("x.bundle", "not a bundle\n", root=self.tmp)
        self.assertFalse(P.verify(bad)["ok"])

    def test_verify_without_sums(self):
        res = self.pack()
        os.unlink(os.path.join(self.out, "SHA256SUMS"))
        rep = P.verify(res["bundle"])
        self.assertTrue(rep["ok"])
        self.assertFalse(rep["sha256sums"])

    def test_dirty_tree_refused(self):
        self.write("new.txt", "untracked\n")
        with self.assertRaises(HarnessError) as cm:
            self.pack()
        self.assertIn("dirty", str(cm.exception))
        os.unlink(os.path.join(self.repo, "new.txt"))
        self.write("VERSION", "1.2.4\n")  # modified tracked file
        with self.assertRaises(HarnessError):
            self.pack()
        self.assertFalse(os.path.exists(self.out))

    def test_local_excluded(self):
        res = self.pack()
        clone = os.path.join(self.tmp, "clone")
        self.git("clone", "-q", res["bundle"], clone, cwd=self.tmp)
        self.assertTrue(os.path.isfile(os.path.join(clone, "VERSION")))
        self.assertFalse(os.path.exists(os.path.join(clone, "local")))
        self.assertEqual(self.git("ls-tree", "-r", "--name-only", "HEAD", "--", "local", cwd=clone), "")

    def test_tracked_local_refused(self):
        self.git("add", "-f", "local/harness.toml")
        self.git("commit", "-q", "-m", "oops")
        with self.assertRaises(HarnessError) as cm:
            self.pack()
        self.assertIn("local/", str(cm.exception))
        # removing it at the tip is not enough: history still carries it
        self.git("rm", "-q", "--cached", "local/harness.toml")
        self.git("commit", "-q", "-m", "remove")
        with self.assertRaises(HarnessError) as cm:
            self.pack()
        self.assertIn("history:local/harness.toml", str(cm.exception))

    # ------------------------------------------------------------------ tools
    def _lock(self, data, verified=True, digest=None):
        asset = os.path.join(self.tmp, "fake_1.0_linux_amd64.tar.gz")
        with open(asset, "wb") as fh:
            fh.write(data)
        lock = {"tool": "fake", "version": "1.0", "verified": verified,
                "assets": {"linux/amd64": {"url": "file://" + asset, "archive": "tar.gz", "binary": "fake",
                                           "sha256": digest if digest is not None else hashlib.sha256(data).hexdigest()}}}
        self.write("tools/fake.lock.json", json.dumps(lock))
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "lock")

    def _targz(self):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tf:
            info = tarfile.TarInfo("fake")
            info.size = 3
            tf.addfile(info, io.BytesIO(b"hi\n"))
        return buf.getvalue()

    def test_tools_downloaded_and_summed(self):
        self._lock(self._targz())
        res = self.pack(platforms=["linux/amd64", "darwin/arm64"])
        self.assertEqual(res["problems"], [])
        self.assertIn("tools/fake_1.0_linux_amd64.tar.gz", res["files"])
        sums = P.read_sums(os.path.join(self.out, "SHA256SUMS"))
        self.assertIn("tools/fake_1.0_linux_amd64.tar.gz", sums)
        self.assertTrue(P.verify(res["bundle"])["ok"])
        self.assertTrue(any("no darwin/arm64 asset" in ln for ln in self.logs))

    def test_tools_bad_sha_not_shipped(self):
        self._lock(self._targz(), digest="0" * 64)
        res = self.pack(platforms=["linux/amd64"])
        self.assertEqual(len(res["problems"]), 1)
        self.assertIn("mismatch", res["problems"][0])
        self.assertFalse(os.path.exists(os.path.join(self.out, "tools")))

    def test_tools_offline_and_unverified(self):
        self._lock(self._targz())
        res = self.pack(platforms=["linux/amd64"], offline=True)
        self.assertIn("offline", res["problems"][0])
        self.assertTrue(os.path.isfile(res["bundle"]))  # the bundle is still written
        self._lock(self._targz(), verified=False)
        res = self.pack(platforms=["linux/amd64"])
        self.assertIn("not verified", res["problems"][0])

    def test_bad_platform(self):
        with self.assertRaises(HarnessError):
            self.pack(platforms=["windows/amd64"])

    # ------------------------------------------------------------------ bootstrap --from
    def test_passthrough_args(self):
        self.assertEqual(
            B.passthrough_args(["--home", "/h", "bootstrap", "--from", "x.bundle", "--dest=/d", "--origin", "u",
                                "--yes", "--bundles", "core", "--config", "c.toml"]),
            ["--yes", "--bundles", "core", "--config", "c.toml"])

    def test_from_bundle_refuses_non_empty_dest(self):
        res = self.pack()

        class NS:
            from_ = res["bundle"]
            dest = self.repo
            origin = None

        class Ctx:
            dry_run = False
            argv = []

        with self.assertRaises(HarnessError) as cm:
            B.from_bundle(Ctx(), NS())
        self.assertIn("not empty", str(cm.exception))

    # ------------------------------------------------------------------ upgrade --to offline
    def test_upgrade_uses_local_tag_when_fetch_fails(self):
        self.git("tag", "-a", "1.2.3", "-m", "r")
        self.git("commit", "-q", "--allow-empty", "-m", "after")
        self.git("remote", "add", "origin", os.path.join(self.tmp, "nowhere.bundle"))
        logs = []
        U.checkout_tag(self.repo, "1.2.3", log=logs.append)
        self.assertEqual(logs, ["note: fetch failed; using local tag 1.2.3"])
        self.assertEqual(self.git("rev-parse", "HEAD").strip(), self.git("rev-parse", "1.2.3^{commit}").strip())

    def test_upgrade_missing_tag_names_the_bundle_flow(self):
        self.git("remote", "add", "origin", os.path.join(self.tmp, "nowhere.bundle"))
        with self.assertRaises(HarnessError) as cm:
            U.checkout_tag(self.repo, "9.9.9", log=lambda *a: None)
        self.assertIn("remote set-url origin /path/NEW.bundle", str(cm.exception))
        self.assertIn("refs/tags/*:refs/tags/*", str(cm.exception))

    def test_upgrade_from_a_newer_bundle(self):
        self.git("tag", "-a", "1.2.3", "-m", "r")
        first = self.pack(tag="1.2.3")["bundle"]
        clone = os.path.join(self.tmp, "clone")
        self.git("clone", "-q", "-b", "1.2.3", first, clone, cwd=self.tmp)
        self.write("VERSION", "1.2.4\n")
        self.git("commit", "-q", "-am", "next")
        self.git("tag", "-a", "1.2.4", "-m", "r")
        self.out = os.path.join(self.tmp, "rel2")
        newer = self.pack(tag="1.2.4")["bundle"]
        self.git("remote", "set-url", "origin", newer, cwd=clone)
        logs = []
        U.checkout_tag(clone, "1.2.4", log=logs.append)
        self.assertEqual(logs, [])
        self.assertEqual(self.read(os.path.join(clone, "VERSION")), "1.2.4\n")
        self.assertIn("remote set-url origin /path/NEW.bundle", self.read(os.path.join(self.out, "INSTALL.txt")))

    # ------------------------------------------------------------------ self-extracting .run
    def sh(self, *args, env=None, unset=()):
        e = dict(os.environ)
        e.update(env or {})
        e.pop("HARNESS_HOME", None)
        for k in unset:
            e.pop(k, None)
        return subprocess.run(["sh"] + list(args), stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=e,
                              cwd=self.tmp)

    def test_self_extract_payload_deterministic(self):
        for name, text in (("a.txt", "alpha\n"), ("tools/t.tar.gz", "tool\n")):
            self.write(name, text, root=self.out)
        files = ["a.txt", "tools/t.tar.gz"]
        one = P.build_payload(self.out, files, os.path.join(self.tmp, "p1.tar"), 1700000000)
        two = P.build_payload(self.out, list(reversed(files)), os.path.join(self.tmp, "p2.tar"), 1700000000)
        self.assertEqual(one, two)
        with open(os.path.join(self.tmp, "p1.tar"), "rb") as a, open(os.path.join(self.tmp, "p2.tar"), "rb") as b:
            self.assertEqual(a.read(), b.read())
        with tarfile.open(os.path.join(self.tmp, "p1.tar")) as tf:
            members = tf.getmembers()
        self.assertEqual([m.name for m in members], ["a.txt", "tools", "tools/t.tar.gz"])
        self.assertEqual({(m.uid, m.gid, m.uname, m.gname, m.mtime) for m in members}, {(0, 0, "", "", 1700000000)})
        self.assertEqual([m.mode for m in members], [0o644, 0o755, 0o644])
        h1 = P.header_text("1.2.3", "1.2.3", "harness-hub-1.2.3.bundle", one[0], one[1])
        self.assertEqual(h1, P.header_text("1.2.3", "1.2.3", "harness-hub-1.2.3.bundle", one[0], one[1]))
        skip = int(re.search(r"(?m)^HN_SKIP='(\d+)'$", h1).group(1))
        self.assertEqual(h1.count("\n") + 1, skip)  # the @SKIP@ line is the first payload line
        self.assertTrue(h1.endswith("\n__PAYLOAD_BELOW__\n"))
        self.assertNotRegex(h1, r"@[A-Z_]+@")
        with self.assertRaises(HarnessError):
            P.header_text("v1;rm -rf /", "", "x.bundle", one[0], one[1])

    def test_commit_time_honours_source_date_epoch(self):
        self.assertTrue(P.commit_time(self.repo) > 0)
        os.environ["SOURCE_DATE_EPOCH"] = "1234567890"
        try:
            self.assertEqual(P.commit_time(self.repo), 1234567890)
        finally:
            os.environ.pop("SOURCE_DATE_EPOCH")

    def test_sha256_ladder_twins_are_identical(self):
        def block(path):
            text = self.read(path)
            return re.search(r"(?ms)^hn_sha256\(\) \{.*?^\}$", text).group(0)

        self.assertEqual(block(os.path.join(REPO, "bundles/core/lib/compat.sh")), block(P.HEADER_TEMPLATE))

    def _run_release(self, tag="1.2.3"):
        self.git("tag", "-a", tag, "-m", "r")
        return self.pack(tag=tag, self_extract=True)

    def test_self_extract_check_list_extract(self):
        res = self._run_release()
        run = res["run"]
        self.assertEqual(os.path.basename(run), "harness-hub-1.2.3.run")
        self.assertTrue(os.access(run, os.X_OK))
        r = self.sh(run, "--check")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(b"payload ok", r.stdout)
        r = self.sh(run, "--list")
        self.assertEqual(r.returncode, 0, r.stderr)
        listed = r.stdout.decode().split()
        for name in ("harness-hub-1.2.3.bundle", "INSTALL.txt", "SHA256SUMS"):
            self.assertIn(name, listed)
        x = os.path.join(self.tmp, "x")
        r = self.sh(run, "--extract", x)
        self.assertEqual(r.returncode, 0, r.stderr)
        inner = P.read_sums(os.path.join(x, "SHA256SUMS"))
        self.assertEqual(sorted(inner), ["INSTALL.txt", "harness-hub-1.2.3.bundle"])
        for rel in ("harness-hub-1.2.3.bundle", "INSTALL.txt"):
            self.assertEqual(sha(os.path.join(x, rel)), sha(os.path.join(self.out, rel)))
        outer = P.read_sums(os.path.join(self.out, "SHA256SUMS"))
        self.assertEqual(outer["harness-hub-1.2.3.run"], sha(run))
        self.assertEqual({k: v for k, v in outer.items() if k != "harness-hub-1.2.3.run"}, inner)
        self.assertIn("sh harness-hub-1.2.3.run --check", self.read(os.path.join(self.out, "INSTALL.txt")))
        self.assertTrue(P.verify(res["bundle"])["ok"])
        rep = P.verify(run)
        self.assertTrue(rep["ok"], rep)
        self.assertEqual(rep["kind"], "run")
        self.assertIn("harness-hub-1.2.3.run", rep["checked"])

    def test_self_extract_tamper_fails(self):
        run = self._run_release()["run"]
        with open(run, "rb") as fh:
            data = fh.read()
        at = data.index(b"\n__PAYLOAD_BELOW__\n") + len(b"\n__PAYLOAD_BELOW__\n") + 600
        bad = os.path.join(self.tmp, "bad.run")
        with open(bad, "wb") as fh:
            fh.write(data[:at] + bytes([data[at] ^ 0xFF]) + data[at + 1:])
        r = self.sh(bad, "--check")
        self.assertEqual(r.returncode, 1)
        self.assertIn(b"sha256", r.stderr)
        self.assertIn(b"re-download", r.stderr)
        with open(bad, "wb") as fh:
            fh.write(data[:-1000])
        r = self.sh(bad, "--check")
        self.assertEqual(r.returncode, 1)
        self.assertIn(b"truncated", r.stderr)
        self.assertFalse(P.verify(bad)["ok"])

    def test_self_extract_install_and_upgrade(self):
        run = self._run_release()["run"]
        home, hub, rel = (os.path.join(self.tmp, d) for d in ("home", "inst", "relx"))
        os.makedirs(home)
        r = self.sh(run, "--dest", hub, "--release-dir", rel, "--", "--extra", env={"HOME": home})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(b"fixture --extra", r.stdout)
        self.assertEqual(self.git("rev-parse", "HEAD", cwd=hub), self.git("rev-parse", "1.2.3^{commit}"))
        self.assertEqual(self.git("remote", "get-url", "origin", cwd=hub).strip(),
                         os.path.join(rel, "harness-hub-1.2.3.bundle"))
        # a non-empty directory that is not a clone is refused
        r = self.sh(run, "--dest", self.out, "--release-dir", rel, env={"HOME": home})
        self.assertEqual(r.returncode, 1)
        self.assertIn(b"pass --dest DIR", r.stderr)
        # a newer .run with the same --dest takes the upgrade path
        self.write("VERSION", "1.2.4\n")
        self.git("commit", "-q", "-am", "next")
        self.out = os.path.join(self.tmp, "rel2")
        run2 = self._run_release("1.2.4")["run"]
        # the install command line works for upgrades: bootstrap-only flags (and values) are dropped
        r = self.sh(run2, "--dest", hub, "--offline", "--no-install-tools", "--bundles", "core",
                    "--yes", "--providers=claude", "--profile", "p", "--config", "c.toml", env={"HOME": home})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(b"harness-stub upgrade --to 1.2.4 --offline --yes --config c.toml\n", r.stdout)
        self.assertIn(b"note: install-only flags ignored for the upgrade: --no-install-tools --bundles core "
                      b"--providers=claude --profile p\n", r.stdout)
        rel2 = os.path.join(home, ".local", "share", "harness", "releases", "1.2.4")
        self.assertEqual(self.git("remote", "get-url", "origin", cwd=hub).strip(),
                         os.path.join(rel2, "harness-hub-1.2.4.bundle"))
        self.assertIn("1.2.4", self.git("tag", "--list", cwd=hub).split())

    def test_self_extract_refuses_a_clone_that_is_not_a_hub_before_writing(self):
        run = self._run_release()["run"]
        home, other = os.path.join(self.tmp, "home"), os.path.join(self.tmp, "other")
        os.makedirs(home)
        os.makedirs(other)
        self.git("init", "-q", cwd=other)
        r = self.sh(run, "--dest", other, env={"HOME": home})
        self.assertEqual(r.returncode, 1)
        self.assertIn(b"not a harness hub", r.stderr)
        self.assertIn(b"pass --dest DIR", r.stderr)
        self.assertEqual(self.git("remote", cwd=other), "")  # no origin added
        self.assertEqual(self.git("tag", "--list", cwd=other), "")  # nothing fetched
        self.assertFalse(os.path.exists(os.path.join(home, ".local", "share", "harness")))

    def test_self_extract_dest_after_passthrough_flags_is_refused(self):
        run = self._run_release()["run"]
        home = os.path.join(self.tmp, "home")
        os.makedirs(home)
        for args in (["--yes", "--dest", "x"], ["--yes", "--release-dir=x"], ["--", "--dest=x"]):
            r = self.sh(run, *args, env={"HOME": home})
            self.assertEqual(r.returncode, 1, args)
            self.assertIn(b"put --dest and --release-dir before other flags", r.stderr)

    def test_self_extract_without_home_names_the_flag(self):
        run = self._run_release()["run"]
        r = self.sh(run, "--dest", os.path.join(self.tmp, "d"), unset=("HOME", "XDG_DATA_HOME"))
        self.assertEqual(r.returncode, 1)
        self.assertIn(b"HOME is not set; pass --release-dir DIR", r.stderr)
        r = self.sh(run, "--release-dir", os.path.join(self.tmp, "r"), unset=("HOME", "XDG_DATA_HOME"))
        self.assertEqual(r.returncode, 1)
        self.assertIn(b"HOME is not set; pass --dest DIR", r.stderr)

    def test_dev_build_run_refuses_an_existing_clone(self):
        self.git("tag", "-a", "1.2.3", "-m", "r")
        tagged = os.path.join(self.tmp, "inst")
        home = os.path.join(self.tmp, "home")
        os.makedirs(home)
        r = self.sh(self.pack(tag="1.2.3", self_extract=True)["run"], "--dest", tagged, env={"HOME": home})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.git("commit", "-q", "--allow-empty", "-m", "dev")
        self.out = os.path.join(self.tmp, "rel-dev")
        dev = self.pack(self_extract=True)["run"]
        r = self.sh(dev, "--dest", tagged, "--yes", env={"HOME": home})
        self.assertEqual(r.returncode, 1)
        self.assertIn(b"a dev build installs only; pass --dest NEW_DIR, or upgrade from a tagged release .run",
                      r.stderr)
        self.assertNotIn(b"harness-stub", r.stdout)

    def test_pack_self_extract_dev_version(self):
        res = self.pack(self_extract=True)
        run = res["run"]
        self.assertRegex(os.path.basename(run), r"^harness-hub-1\.2\.3-g[0-9a-f]{7}\.run$")
        with open(run, "rb") as fh:
            self.assertIn(b"\nHN_TAG=''\n", fh.read(4096))
        home, hub = os.path.join(self.tmp, "home"), os.path.join(self.tmp, "hub2")
        os.makedirs(home)
        r = self.sh(run, "--dest", hub, env={"HOME": home, "XDG_DATA_HOME": os.path.join(self.tmp, "xdg")})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.git("rev-parse", "HEAD", cwd=hub), self.git("rev-parse", "HEAD"))
        self.assertTrue(self.git("remote", "get-url", "origin", cwd=hub).startswith(os.path.join(self.tmp, "xdg")))

    @staticmethod
    def read(path):
        with open(path, encoding="utf-8") as fh:
            return fh.read()


if __name__ == "__main__":
    unittest.main()
