"""`harness lessons`: record format, counters, review gate, stats, index, propose, journal.

Every test runs with a temp HOME, XDG_STATE_HOME, HARNESS_JOURNAL_DIR and HARNESS_RETRO_DIR,
against a copy of the fixture bundles, so the guard id and the section lines are stable.
Goldens live in tests/fixtures/lessons/golden; `UPDATE=1` rewrites them. The validate run
with a real candidate edit is slow (a full copy of the hub's HEAD) and runs only with
HARNESS_TEST_SLOW=1.
"""
from __future__ import annotations

import difflib
import io
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout

from helpers import FIXTURES, REPO

from harness import cli
from harness import lessons as L

LFIX = os.path.join(FIXTURES, "lessons")
GOLD = os.path.join(LFIX, "golden")
UPDATE = os.environ.get("UPDATE") == "1"

_ENV = ("HOME", "XDG_STATE_HOME", "HARNESS_HOME", "HARNESS_BUNDLES_ROOT", "HARNESS_CONFIG", "HARNESS_JOURNAL_DIR",
        "HARNESS_RETRO_DIR", "HARNESS_BUILD_DIR", "XDG_CACHE_HOME", "HARNESS_BUNDLE_PATH", "HARNESS_PROVIDER_PATH")

CONFIG = """schema_version = 1
[identity]
email = "you@example.com"
[hub]
bundles = ["core", "alpha", "beta"]
providers = ["claude"]
"""


class LessonsCase(unittest.TestCase):
    extra_config = ""

    def setUp(self) -> None:
        self._saved = {k: os.environ.get(k) for k in _ENV}
        self.tmp = tempfile.mkdtemp(prefix="harness-lessons-")
        self.home = os.path.join(self.tmp, "home")
        os.makedirs(self.home)
        bundles = os.path.join(self.tmp, "bundles")
        shutil.copytree(os.path.join(FIXTURES, "bundles"), bundles, symlinks=True)
        for k in _ENV:
            os.environ.pop(k, None)
        os.environ.update({
            "HOME": self.home, "XDG_STATE_HOME": os.path.join(self.tmp, "state"), "HARNESS_HOME": REPO,
            "HARNESS_BUNDLES_ROOT": bundles, "HARNESS_JOURNAL_DIR": os.path.join(self.tmp, "journal"),
            "HARNESS_RETRO_DIR": os.path.join(self.tmp, "retro"), "XDG_CACHE_HOME": os.path.join(self.tmp, "cache")})
        self.cfg = os.path.join(self.tmp, "h.toml")
        self.write_config(self.extra_config)
        self.ldir = os.path.join(self.tmp, "state", "harness", "lessons")

    def tearDown(self) -> None:
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- helpers ----------------------------------------------------------------
    def write_config(self, extra: str = "") -> None:
        with open(self.cfg, "w", encoding="utf-8") as fh:
            fh.write(CONFIG + extra)

    def run_cli(self, *argv: str):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = cli.main(["lessons"] + list(argv) + ["--config", self.cfg])
        return rc, out.getvalue(), err.getvalue()

    def ok(self, *argv: str) -> str:
        rc, out, err = self.run_cli(*argv)
        self.assertEqual(rc, 0, "rc=%d\nstdout:\n%s\nstderr:\n%s" % (rc, out, err))
        return out

    def new(self, domain: str = "base", scope: str = "invariant", situation: str = "reading a key file",
            date: str = "2026-10-01", evidence=("journal:2026-10-01",), sensor: str = "core/guard.d/20-core",
            extra=()) -> str:
        argv = ["new", "--domain", domain, "--scope", scope, "--situation", situation,
                "--guide-ref", "core/rules/10-core", "--sensor-ref", sensor, "--date", date, "--evidence"]
        argv += list(evidence) + list(extra)
        return self.ok(*argv).strip()

    def journal(self, rows, name: str = "2026-10-26.log") -> None:
        d = os.environ["HARNESS_JOURNAL_DIR"]
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, name), "a", encoding="utf-8") as fh:
            for r in rows:
                fh.write("\t".join(r) + "\n")

    def guard_id(self) -> str:
        from harness.hub import Hub

        return L.GuardMap(Hub(home=REPO, config_path=self.cfg, require_config=False)).guard_id

    def golden(self, name: str, text: str) -> None:
        path = os.path.join(GOLD, name)
        if UPDATE:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
        with open(path, encoding="utf-8") as fh:
            want = fh.read()
        self.assertEqual(text, want, "golden %s differs (UPDATE=1 rewrites it):\n%s" % (
            name, "".join(difflib.unified_diff(want.splitlines(True), text.splitlines(True)))))

    def record(self, lid: str) -> L.Lesson:
        return L.load(self.ldir, lid)


def jl(ts: str, session: str, kind: str, site: str, gid: str, repo: str = "shop", prov: str = "claude"):
    return (ts, prov, session, kind, site, gid, repo)


def fake_token() -> str:
    return "gh" + "p_" + "a1B2c3D4" * 5   # built at runtime: no token shape in the source


# ======================================================================= format


class RecordFormatTest(LessonsCase):
    def test_fixture_round_trips_byte_for_byte(self):
        with open(os.path.join(LFIX, "record.md"), encoding="utf-8") as fh:
            text = fh.read()
        rec = L.parse(text, "record.md")
        self.assertEqual(L.dump(rec), text)
        self.assertEqual(rec.fm["bundles"], ["ticket-workflow", "github"])
        self.assertEqual(rec.fm["uses"], 4)

    def test_written_record_round_trips(self):
        lid = self.new(extra=["--lesson", "use the public half", "--bundles", "core,alpha",
                              "--edit", os.path.join(LFIX, "edit.diff")])
        path = os.path.join(self.ldir, lid + ".md")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        self.assertEqual(L.dump(L.parse(text)), text)
        rec = self.record(lid)
        self.assertEqual(rec.fm["candidate_edit"], "patches/base-001.diff")
        self.assertTrue(os.path.isfile(os.path.join(self.ldir, "patches", "base-001.diff")))
        self.assertEqual(rec.sections["Candidate edit"],
                         ["patches/base-001.diff:", "- bundles/core/rules/00-conventions.md (+1 -0)"])
        self.assertEqual(rec.fm["bundles"], ["core", "alpha"])

    def test_parse_rejects_hand_edits(self):
        with open(os.path.join(LFIX, "record.md"), encoding="utf-8") as fh:
            text = fh.read()
        for bad in (text.replace("status: confirmed", "status: great"),
                    text.replace("uses: 4\n", ""),
                    text.replace("uses: 4", "uses: four"),
                    text.replace("## Lesson\n", ""),
                    text.replace(L.BANNER + "\n", ""),
                    text.replace("domain: delivery", "domain: nowhere")):
            with self.assertRaises(L.LessonError):
                L.parse(bad)

    def test_id_sequencing(self):
        self.assertEqual(self.new(), "base-001")
        self.assertEqual(self.new(), "base-002")
        self.assertEqual(self.new(domain="scm", scope="domain"), "scm-001")
        shutil.copy(os.path.join(self.ldir, "base-002.md"), os.path.join(self.ldir, "base-009.md"))
        self.assertEqual(L.next_id(self.ldir, "base"), "base-010")
        self.assertEqual(L.next_id(self.ldir, "tracker"), "tracker-001")


class RefusalTest(LessonsCase):
    def refused(self, *argv: str) -> str:
        rc, out, err = self.run_cli(*argv)
        self.assertEqual(rc, 1, out + err)
        self.assertFalse(os.path.exists(os.path.join(self.ldir, "base-001.md")))
        return err

    def base(self, **over):
        args = {"--domain": "base", "--scope": "invariant", "--situation": "reading a key file",
                "--guide-ref": "core/rules/10-core", "--sensor-ref": "core/guard.d/20-core"}
        args.update(over)
        argv = ["new"]
        for k, v in args.items():
            argv += [k, v]
        return argv

    def test_each_reason(self):
        self.assertIn("invariant needs domain base",
                      self.refused(*self.base(**{"--domain": "scm"}), "--evidence", "user:x"))
        self.assertIn("<bundle>/<kind>/<name>",
                      self.refused(*self.base(**{"--guide-ref": "core/00-conventions"}), "--evidence", "user:x"))
        self.assertIn("<bundle>/<kind>/<name>",
                      self.refused(*self.base(**{"--sensor-ref": "../x/guard.d/y"}), "--evidence", "user:x"))
        self.assertIn("token-shaped",
                      self.refused(*self.base(**{"--situation": "pasted %s here" % fake_token()}), "--evidence", "user:x"))
        self.assertIn("token-shaped", self.refused(*self.base(), "--evidence", "user:%s" % fake_token()))
        self.assertIn("URL userinfo",
                      self.refused(*self.base(), "--evidence", "user:cloned https://me" + ":" + "pw@git.example.com/x"))
        self.assertIn("cap is 300", self.refused(*self.base(**{"--situation": "x " * 200}), "--evidence", "user:x"))
        self.assertIn("cap is 400", self.refused(*self.base(), "--lesson", "y " * 250, "--evidence", "user:x"))
        self.assertIn("cap is 200", self.refused(*self.base(), "--evidence", "user:" + "z " * 150))
        self.assertIn("KIND one of", self.refused(*self.base(), "--evidence", "gossip:x"))
        bad = os.path.join(self.tmp, "bad.diff")
        with open(bad, "w") as fh:
            fh.write("--- a/README.md\n+++ b/README.md\n@@ -1 +1 @@\n-a\n+b\n")
        self.assertIn("outside bundles/", self.refused(*self.base(), "--evidence", "user:x", "--edit", bad))
        with open(bad, "w") as fh:
            fh.write("not a diff\n")
        self.assertIn("not a unified diff", self.refused(*self.base(), "--evidence", "user:x", "--edit", bad))

    def test_no_evidence_and_unknown_domain(self):
        with self.assertRaises(L.LessonError) as cm:
            L.new_lesson(self.ldir, "base", "invariant", "s", "core/rules/10-core", "core/guard.d/20-core", [])
        self.assertIn("no evidence", str(cm.exception))
        with self.assertRaises(L.LessonError) as cm:
            L.new_lesson(self.ldir, "nowhere", "domain", "s", "core/rules/10-core", "core/guard.d/20-core", ["user:x"])
        self.assertIn("unknown domain", str(cm.exception))
        with self.assertRaises(SystemExit):   # argparse: --evidence is required, unknown domain rejected
            with redirect_stderr(io.StringIO()):
                cli.main(["lessons"] + self.base() + ["--config", self.cfg])

    def test_identifiers_and_ids_are_not_tokens(self):
        for text in ("guard_section_core_20_credentials:37", "3f9c1a7e" + "02bd",
                     "0f8a2c4e-1b3d-4e5f-8a9b-0c1d2e3f4a5b", "a" * 40, "ticket-workflow/guard.d/75-ticket-workflow"):
            self.assertIsNone(L.secret_reason(text), text)

    def test_checkout_refusal(self):
        repo = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(repo, ".git"))
        self.write_config('[lessons]\ndir = "%s"\n' % os.path.join(repo, "notes", "lessons"))
        rc, _out, err = self.run_cli("list")
        self.assertEqual(rc, 1)
        self.assertIn("inside the git checkout", err)
        self.assertIn("outside every git checkout", err)
        self.write_config('[lessons]\ndir = "%s"\n' % os.path.join(REPO, "local", "lessons-never-created"))
        rc, _out, err = self.run_cli("list")
        self.assertEqual(rc, 1)
        self.assertIn("under the hub checkout", err)
        self.assertFalse(os.path.exists(os.path.join(REPO, "local", "lessons-never-created")))


# ======================================================================= counters


class CountersTest(LessonsCase):
    def test_subjective_vs_objective_and_recurring_flip(self):
        lid = self.new()
        self.ok("note", lid, "--used", "--helped", "--date", "2026-10-02")
        self.ok("note", lid, "--recurred", "--evidence", "user:it happened again", "--date", "2026-10-03")
        r = self.record(lid)
        self.assertEqual((r.fm["uses"], r.fm["helped"], r.fm["recurred"], r.fm["recurred_objective"]), (1, 1, 1, 0))
        self.assertEqual(r.status, "candidate")
        for day in ("04", "05"):
            self.ok("note", lid, "--recurred", "--evidence", "journal:2026-10-%sT00:00:00Z claude s%s guard-deny "
                    "guard_section_core_20_core:8 3f9c1a7e02bd shop" % (day, day), "--date", "2026-10-%s" % day)
        r = self.record(lid)
        self.assertEqual((r.fm["recurred"], r.fm["recurred_objective"], r.status), (3, 2, "candidate"))
        out = self.ok("note", lid, "--recurred", "--evidence", "journal:2026-10-06 s6", "--note", "third time",
                      "--date", "2026-10-06")
        self.assertIn("now recurring", out)
        r = self.record(lid)
        self.assertEqual((r.fm["recurred_objective"], r.status, r.fm["updated"]), (3, "recurring", "2026-10-06"))
        self.assertEqual(r.sections["History"][-2:], [
            "- 2026-10-06 note: recurred (objective), evidence +1; third time",
            "- 2026-10-06 status recurring (3 objective recurrences >= lessons.promote_after 3)"])
        self.assertEqual(len([e for e in r.sections["Evidence"] if e.startswith("- journal: ")]), 4)

    def test_promote_after_from_config(self):
        self.write_config("[lessons]\npromote_after = 1\n")
        lid = self.new()
        self.ok("note", lid, "--recurred", "--evidence", "journal:x")
        self.assertEqual(self.record(lid).status, "recurring")

    def test_note_refusals_and_transitions(self):
        lid = self.new()
        rc, _o, err = self.run_cli("note", lid)
        self.assertEqual(rc, 2)
        self.assertIn("nothing to note", err)
        self.ok("confirm", lid, "--date", "2026-10-02")
        rc, _o, err = self.run_cli("confirm", lid)
        self.assertEqual(rc, 1)
        self.assertIn("only a candidate or recurring", err)
        self.ok("retire", lid, "--reason", "superseded", "--date", "2026-10-03")
        r = self.record(lid)
        self.assertEqual(r.status, "retired")
        self.assertEqual(r.sections["History"][-1], "- 2026-10-03 retired: superseded")
        rc, _o, err = self.run_cli("note", lid, "--used")
        self.assertEqual(rc, 1)
        self.assertIn("is retired", err)
        rc, _o, err = self.run_cli("show", "../etc")
        self.assertEqual(rc, 2)

    def test_list_and_show(self):
        a = self.new(date="2026-01-01")
        self.new(domain="scm", scope="domain", situation="pushing to main", date="2026-10-01")
        out = self.ok("list", "--stale")
        self.assertIn(a, out)
        self.assertNotIn("scm-001", out)
        data = json.loads(self.ok("list", "--domain", "scm", "--json"))
        self.assertEqual([d["id"] for d in data], ["scm-001"])
        self.assertEqual(data[0]["situation"], "pushing to main")
        self.assertTrue(self.ok("show", a).startswith(L.BANNER))


# ======================================================================= review


class ReviewTest(LessonsCase):
    def test_rc_3_reasons(self):
        rc, out, _e = self.run_cli("review", "--session", "s1")
        self.assertEqual(rc, 3)
        self.assertIn("no journal", out)
        self.journal([jl("2026-10-26T09:00:00Z", "s1", "guard-deny", "guard_section_core_20_core:8", "x")])
        rc, out, _e = self.run_cli("review")
        self.assertEqual(rc, 3)
        self.assertIn("no session", out)
        rc, out, _e = self.run_cli("review", "--session", "s2")
        self.assertEqual(rc, 3)
        self.assertIn("no signals", out)
        rc, out, _e = self.run_cli("review", "--session", "s2", "--json")
        self.assertEqual(rc, 3)
        self.assertEqual(json.loads(out)["due"], False)

    def test_thresholds_explain_and_current(self):
        site = "guard_section_core_20_core:8"
        self.journal([jl("2026-10-26T09:00:00Z", "s1", "guard-deny", site, "g"),
                      jl("2026-10-26T09:01:00Z", "s1", "correction", "-", "g"),
                      jl("2026-10-26T09:02:00Z", "s2", "correction", "-", "g"),
                      jl("2026-10-26T09:03:00Z", "s1", "guard-ask", site, "g")])
        with open(os.path.join(self.tmp, "journal", "2026-10-26.log"), "a") as fh:
            fh.write("malformed line\n")
        rc, out, _e = self.run_cli("review", "--session", "s1", "--explain")
        self.assertEqual(rc, 1)
        self.assertEqual(out, "\n".join([
            "due: no", "session: s1",
            "counts: guard-ask 1, guard-deny 1, correction 1, dissatisfaction 0",
            "fired: none (thresholds: lessons.review.corrections 2, lessons.review.dissatisfaction 1, "
            "lessons.review.denies 3; 0 = off)",
            "  2026-10-26T09:00:00Z  guard-deny  guard_section_core_20_core:8",
            "  2026-10-26T09:01:00Z  correction  -",
            "  2026-10-26T09:03:00Z  guard-ask  guard_section_core_20_core:8", ""]))
        self.journal([jl("2026-10-26T09:04:00Z", "s1", "correction", "-", "g")])
        os.makedirs(os.environ["HARNESS_RETRO_DIR"])
        with open(os.path.join(os.environ["HARNESS_RETRO_DIR"], "current"), "w") as fh:
            fh.write("s1\n")
        rc, out, _e = self.run_cli("review")
        self.assertEqual(rc, 0)
        self.assertIn("fired: corrections (correction 2 >= lessons.review.corrections 2)", out)
        data = json.loads(self.run_cli("review", "--json")[1])
        self.assertEqual(data, {"due": True, "session": "s1", "fired": ["corrections"], "counts": {
            "guard-ask": 1, "guard-deny": 1, "correction": 2, "dissatisfaction": 0}})
        # 0 disables a criterion
        self.write_config("[lessons.review]\ncorrections = 0\n")
        self.assertEqual(self.run_cli("review")[0], 1)
        self.journal([jl("2026-10-26T09:05:00Z", "s1", "dissatisfaction", "-", "g")])
        self.assertEqual(self.run_cli("review")[0], 0)
        self.write_config("[lessons.review]\ncorrections = 0\ndissatisfaction = 0\ndenies = 1\n")
        rc, out, _e = self.run_cli("review")
        self.assertEqual(rc, 0)
        self.assertIn("fired: denies", out)


# ======================================================================= stats / index


class StatsIndexTest(LessonsCase):
    def test_stats_golden(self):
        gid = self.guard_id()
        self.new(date="2026-10-10", situation="fixture deny")                      # site scope
        self.new(domain="scm", scope="domain", situation="beta things", date="2026-10-12",
                 sensor="beta/rules/05-beta")                                       # domain scope (beta = scm)
        self.journal([
            jl("2026-10-01T10:00:00Z", "a", "guard-deny", "guard_section_core_20_core:8", gid),
            jl("2026-10-01T10:01:00Z", "a", "guard-deny", "guard_section_core_20_core:8", gid),
            jl("2026-10-02T10:00:00Z", "b", "guard-ask", "guard_section_beta_15_beta:3", "oldguard0000"),
            jl("2026-10-02T10:01:00Z", "b", "correction", "-", gid),
            jl("2026-10-11T10:00:00Z", "c", "guard-deny", "guard_section_core_20_core:8", gid),
            jl("2026-10-13T10:00:00Z", "d", "guard-ask", "guard_section_beta_15_beta:3", gid),
            jl("2026-10-13T10:01:00Z", "e", "guard-deny", "guard_section_alpha_40_alpha:6", gid),
        ])
        self.ok("note", "base-001", "--used", "--helped", "--date", "2026-10-12")
        self.golden("stats.txt", self.ok("stats"))
        rows = json.loads(self.ok("stats", "--json"))
        self.assertEqual(rows[1]["window"], "after")
        self.assertEqual(rows[1]["denies_per_session"], "0.33")
        self.assertIn("since 2026-10-11", self.ok("stats", "--since", "2026-10-11", "--domain", "scm"))

    def make_library(self):
        # base: 1 confirmed, 1 recurring, 1 proposed, 7 candidates (5 shown), 1 retired; scm: 1 stale candidate
        ids = [self.new(situation="lesson %d" % i, date="2026-10-%02d" % (i + 1)) for i in range(11)]
        self.ok("confirm", ids[0], "--date", "2026-10-20")
        self.write_config("[lessons]\npromote_after = 1\n")
        self.ok("note", ids[1], "--recurred", "--evidence", "journal:x", "--date", "2026-10-21")
        self.write_config("[lessons]\npromote_after = 3\n")
        self.ok("confirm", ids[2], "--date", "2026-10-21")
        self.ok("propose", ids[2], "--out", os.path.join(self.tmp, "p"), "--repo", "octocat/hub", "--mark",
                "--date", "2026-10-22")
        self.ok("retire", ids[3], "--date", "2026-10-22")
        self.new(domain="scm", scope="domain", situation="old scm thing", date="2026-01-05")
        return ids

    def test_index_golden_with_caps(self):
        self.make_library()
        self.ok("index", "--now", "2026-10-26T00:00:00Z")
        with open(os.path.join(self.ldir, "INDEX.md"), encoding="utf-8") as fh:
            self.golden("INDEX.md", fh.read())
        self.write_config("[lessons]\nindex_max = 4\nindex_max_candidates = 2\n")
        self.ok("index", "--now", "2026-10-26T00:00:00Z")
        with open(os.path.join(self.ldir, "INDEX.md"), encoding="utf-8") as fh:
            self.golden("INDEX-capped.md", fh.read())

    def test_index_prune(self):
        self.make_library()
        out = self.ok("index", "--prune", "--now", "2026-10-26T00:00:00Z")
        self.assertIn("scm-001: retired (stale)", out)
        r = self.record("scm-001")
        self.assertEqual(r.status, "retired")
        self.assertEqual(r.sections["History"][-1], "- 2026-10-26 retired: stale (no update in 90 days)")
        with open(os.path.join(self.ldir, "INDEX.md"), encoding="utf-8") as fh:
            self.assertNotIn("### scm", fh.read())


# ======================================================================= propose


class ProposeTest(LessonsCase):
    def confirmed(self, situation="pushing a branch named after the ticket", lesson="name branches by topic"):
        lid = self.new(domain="scm", scope="domain", situation=situation, date="2026-10-01", sensor="beta/guard.d/15-beta",
                       evidence=["journal:2026-10-01T09:12:03Z claude s1 guard-deny guard_section_beta_15_beta:3 "
                                 "3f9c1a7e02bd shop", "user:\"not in shop again\""],
                       extra=["--lesson", lesson, "--edit", os.path.join(LFIX, "edit.diff"), "--bundles", "beta"])
        self.ok("confirm", lid, "--date", "2026-10-02")
        return lid

    def test_goldens_github(self):
        lid = self.confirmed()
        out_dir = os.path.join(self.tmp, "p")
        out = self.ok("propose", lid, "--out", out_dir, "--repo", "octocat/hub", "--date", "2026-10-03")
        self.assertIn("never runs create.sh", out)
        for name in ("body.md", "preview.md", "create.sh"):
            with open(os.path.join(out_dir, name), encoding="utf-8") as fh:
                self.golden(os.path.join("propose", name), fh.read())
        self.assertEqual(os.stat(os.path.join(out_dir, "create.sh")).st_mode & 0o111, 0)   # never executable
        self.assertEqual(self.record(lid).status, "confirmed")                               # no --mark
        self.ok("propose", lid, "--out", out_dir, "--repo", "octocat/hub", "--keep-repos")
        with open(os.path.join(out_dir, "body.md"), encoding="utf-8") as fh:
            self.assertIn("not in shop again", fh.read())
        self.ok("propose", lid, "--out", out_dir, "--repo", "octocat/hub", "--mark", "--date", "2026-10-04")
        r = self.record(lid)
        self.assertEqual((r.status, r.sections["History"][-1]), ("proposed", "- 2026-10-04 proposed"))

    def test_refusals(self):
        out_dir = os.path.join(self.tmp, "p")
        lid = self.new()
        rc, _o, err = self.run_cli("propose", lid, "--out", out_dir, "--repo", "octocat/hub")
        self.assertEqual(rc, 1)
        self.assertIn("is a candidate", err)
        self.assertFalse(os.path.exists(out_dir))
        self.write_config("[lessons]\npromote_after = 1\n")
        self.ok("note", lid, "--recurred", "--evidence", "journal:x")
        self.ok("propose", lid, "--out", out_dir, "--repo", "octocat/hub")   # recurring, objective >= 1
        self.write_config("[lessons]\npromote_after = 3\n")
        rc, _o, err = self.run_cli("propose", lid, "--out", out_dir, "--repo", "octocat/hub")
        self.assertEqual(rc, 1)
        self.assertIn("objective recurrence(s) < lessons.promote_after 3", err)
        self.ok("confirm", lid)
        self.ok("propose", lid, "--out", out_dir, "--repo", "octocat/hub", "--mark")
        rc, _o, err = self.run_cli("propose", lid, "--out", out_dir, "--repo", "octocat/hub")
        self.assertIn("already proposed", err)
        b = self.new()
        self.ok("retire", b)
        rc, _o, err = self.run_cli("propose", b, "--out", out_dir, "--repo", "octocat/hub")
        self.assertEqual(rc, 1)
        self.assertIn("is retired", err)
        rc, _o, err = self.run_cli("propose", lid, "--out", out_dir, "--repo", "not a repo")
        self.assertEqual(rc, 2)

    def test_closing_keywords_and_issue_refs(self):
        out_dir = os.path.join(self.tmp, "p")
        lid = self.confirmed(lesson="this fixes #12 for good")
        rc, _o, err = self.run_cli("propose", lid, "--out", out_dir, "--repo", "octocat/hub")
        self.assertEqual(rc, 1)
        self.assertIn("closing keyword", err)
        lid = self.confirmed(situation="after #12 the branch name broke")
        rc, _o, err = self.run_cli("propose", lid, "--out", out_dir, "--repo", "octocat/hub")
        self.assertEqual(rc, 1)
        self.assertIn("issue reference (#N)", err)
        for text in ("Closes #3", "resolved octocat/hub#4", "Fixes: https://github.com/octocat/hub/issues/5",
                     "implements PROJ-123"):
            self.assertTrue(L.CLOSING_RE.search(text), text)
        for text in ("fix the parser", "see #3", "closes the file handle", "PROJ-123 fix parser"):
            self.assertFalse(L.CLOSING_RE.search(text), text)

    def test_jira_tracker_and_title_cap(self):
        lid = self.confirmed(situation="a very long situation " * 6)
        files = L.propose_files(self.record(lid), "jira", None, "agent-drafted", False, None)
        self.assertIn("# /create-ticket Lesson scm-001:", files["create.sh"])
        self.assertNotIn("gh issue", files["create.sh"])
        title = [ln for ln in files["preview.md"].splitlines() if ln.startswith("- title: ")][0][len("- title: "):]
        self.assertLessEqual(len(title), 80)
        self.assertTrue(title.endswith("..."))


# ======================================================================= journal / validate


class JournalTest(LessonsCase):
    def test_grouping_stale_and_ack(self):
        gid = self.guard_id()
        self.assertRegex(gid, r"^[0-9a-f]{12}$")
        self.journal([
            jl("2026-10-26T09:00:00Z", "s1", "guard-deny", "guard_section_core_20_core:8", gid),
            jl("2026-10-26T09:01:00Z", "s2", "guard-deny", "guard_section_core_20_core:8", gid),
            jl("2026-10-26T09:02:00Z", "s1", "guard-deny", "guard_section_core_20_core:8", "0123456789ab"),
            jl("2026-10-26T09:03:00Z", "s1", "correction", "-", gid),
            jl("2026-10-26T09:04:00Z", "s1", "guard-ask", "guard_section_core_20_core:9", gid),
        ])
        data = json.loads(self.ok("journal", "--json"))
        self.assertEqual((data["from"], data["lines"], data["guard_id"]), ("all", 5, gid))
        got = [(g["kind"], g["site"], g["status"], g["count"], g["sessions"], g["text"]) for g in data["groups"]]
        self.assertEqual(got, [
            ("guard-ask", "guard_section_core_20_core:9", "current", 1, 1, 'fixture-ask*) ask "asked by core" ;;'),
            ("guard-deny", "guard_section_core_20_core:8", "current", 2, 2,
             'fixture-deny*) deny "denied by core (ticket ${FIX_TICKET:-unset})" ;;'),
            ("guard-deny", "guard_section_core_20_core:8", "stale", 1, 1, ""),
            ("correction", "-", "-", 1, 1, "")])
        self.assertIn("(older guard; line not attributed)", self.ok("journal"))
        rdir = os.environ["HARNESS_RETRO_DIR"]
        os.makedirs(os.path.join(rdir, "sessions"))
        old, fresh = os.path.join(rdir, "sessions", "old"), os.path.join(rdir, "sessions", "fresh")
        for p in (old, fresh):
            with open(p, "w") as fh:
                fh.write("x\n")
        past = time.time() - 8 * 86400
        os.utime(old, (past, past))
        self.assertIn("acknowledged", self.ok("journal", "--ack"))
        with open(os.path.join(rdir, "last")) as fh:
            self.assertRegex(fh.read(), r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\n$")
        self.assertEqual((os.path.exists(old), os.path.exists(fresh)), (False, True))
        data = json.loads(self.ok("journal", "--json"))
        self.assertEqual((data["from"], data["lines"]), ("retro/last", 0))
        self.assertEqual(json.loads(self.ok("journal", "--all", "--json"))["lines"], 5)
        self.assertEqual(json.loads(self.ok("journal", "--since", "2026-10-26T09:02:30Z", "--json"))["lines"], 2)


class ValidateTest(LessonsCase):
    def test_without_edit(self):
        lid = self.new()
        rc, out, _e = self.run_cli("validate", lid)
        self.assertEqual(rc, 1)
        self.assertIn("validation none (no candidate edit", out)
        self.assertEqual(self.record(lid).fm["validation"], "none")
        rc, out, _e = self.run_cli("validate")
        self.assertEqual(rc, 1)
        self.assertIn("no lesson with a candidate edit", out)

    @unittest.skipUnless(os.environ.get("HARNESS_TEST_SLOW") == "1", "slow: set HARNESS_TEST_SLOW=1")
    def test_with_edit_slow(self):
        rel = "bundles/core/rules/00-conventions.md"
        head = subprocess.run(["git", "-C", REPO, "show", "HEAD:" + rel], stdout=subprocess.PIPE, check=True).stdout
        old = head.decode("utf-8").splitlines(True)
        new = old + ["\n", "- Check a key's format with its public half, never the private file.\n"]
        diff = "".join(difflib.unified_diff(old, new, "a/" + rel, "b/" + rel))
        path = os.path.join(self.tmp, "real.diff")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(diff)
        lid = self.new(extra=["--edit", path])
        out = self.ok("validate", lid, "--quick", "--now", "2026-10-26T00:00:00Z")
        self.assertIn("validation pass", out)
        r = self.record(lid)
        self.assertEqual((r.fm["validation"], r.fm["validated_at"]), ("pass", "2026-10-26T00:00:00Z"))
        self.assertRegex(r.fm["validated_guard_id"], r"^[0-9a-f]{12}$")
        self.assertRegex(r.sections["Validation"][0], r"^- 2026-10-26T00:00:00Z pass: apply ok, lint ok, "
                         r"test guard ok, render ok; guard [0-9a-f]{12}$")


if __name__ == "__main__":
    unittest.main()
