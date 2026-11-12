"""GitHub provider of repoboot: probes with `gh api` GETs, writes with `gh repo create`, `gh api -X
PATCH|POST` and `gh label create`. Loaded by repoboot.py (Engine.provider); never run directly."""
import json
import urllib.parse

RULESET_NAME = "repo-standard"
PLAN_403 = ("rulesets on a private repository need GitHub Pro, Team or Enterprise (or a public "
            "repository); protect the default branch by hand or upgrade the plan")


class Provider(object):
    name = "github"

    def __init__(self, e, core):
        self.e, self.c = e, core
        self.slug = e.derived()["slug"]
        self.url = e.derived()["ssh_url"]
        self.branch = e.default_branch()
        self.blocked = None

    # ---- answers -> desired state
    def spec(self, qid):
        return self.c.spec_get(self.e.spec, qid)

    def desired_settings(self):
        m = self.spec("workflow.merge_method") or "squash"
        s = {"delete_branch_on_merge": True, "allow_auto_merge": False,
             "allow_squash_merge": m == "squash", "allow_merge_commit": m == "merge",
             "allow_rebase_merge": m == "rebase"}
        if m == "squash":
            s["squash_merge_commit_title"] = "PR_TITLE"
            s["squash_merge_commit_message"] = "PR_BODY"
        return s

    def ruleset(self):
        approvals = int(self.spec("workflow.required_approvals") or 0)
        rules = [{"type": "deletion"}, {"type": "non_fast_forward"},
                 {"type": "pull_request", "parameters": {
                     "required_approving_review_count": approvals,
                     "dismiss_stale_reviews_on_push": True,
                     "require_code_owner_review": bool(self.spec("workflow.codeowners")) and approvals > 0,
                     "require_last_push_approval": False,
                     "required_review_thread_resolution": True}}]
        checks = self.c.as_list(self.spec("quality.required_checks"))
        if checks:
            rules.append({"type": "required_status_checks", "parameters": {
                "strict_required_status_checks_policy": False,
                "required_status_checks": [{"context": x} for x in checks]}})
        return {"name": RULESET_NAME, "target": "branch", "enforcement": "active",
                "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
                "rules": rules}

    def labels(self):
        if not self.spec("workflow.agent_labels"):
            return []
        return [(name, self.c.LABEL_TEXT[role]) for role, name in self.c.agent_labels()]

    # ---- steps
    def patch_step(self, fields, sid="settings", note="merge settings: squash/merge/rebase, delete branches on merge"):
        argv = ["gh", "api", "-X", "PATCH", "repos/" + self.slug]
        for k in sorted(fields):
            v = fields[k]
            if isinstance(v, bool):
                argv += ["-F", "%s=%s" % (k, "true" if v else "false")]
            else:
                argv += ["-f", "%s=%s" % (k, v)]
        return self.c.step(sid, argv, note)

    def ruleset_step(self):
        body = self.ruleset()
        return self.c.step("protection", ["gh", "api", "-X", "POST", "repos/%s/rulesets" % self.slug, "--input", "@BODY"],
                           "default-branch ruleset %r: PRs only, %d approval(s), no force-push or deletion%s" % (
                               RULESET_NAME, body["rules"][2]["parameters"]["required_approving_review_count"],
                               ", required checks" if len(body["rules"]) > 3 else ""),
                           body=body, tolerate={"403": PLAN_403})

    def label_step(self, name, text):
        color, desc = text
        return self.c.step("label:" + name, ["gh", "label", "create", name, "-R", self.slug, "-c", color, "-d", desc],
                           "provenance label %s" % name)

    # ---- probe (GET only)
    def get(self, path, missing_ok=(404,)):
        return self.c.read_json(["gh", "api", path], missing_ok=missing_ok)

    def probe(self):
        st, repo = self.get("repos/" + self.slug)
        if st == 404 or repo is None:
            return {"exists": False, "summary": "%s does not exist" % self.slug}
        _st, branches = self.get("repos/%s/branches?per_page=1" % self.slug)
        r = {"exists": True, "repo": repo, "empty": not branches,
             "summary": "%s exists (%s, %s)" % (self.slug, repo.get("visibility") or "?",
                                                 "empty" if not branches else "default branch " + repo.get("default_branch", "?"))}
        if branches:
            branch = repo.get("default_branch") or self.branch
            st, rules = self.get("repos/%s/rules/branches/%s" % (self.slug, urllib.parse.quote(branch, safe="")),
                                 missing_ok=(403, 404))
            r["rules"] = rules if st == 200 else None
            st, prot = self.get("repos/%s/branches/%s/protection" % (self.slug, urllib.parse.quote(branch, safe="")),
                                missing_ok=(403, 404))
            r["protection"] = prot if st == 200 else None
            r["protection_status"] = st
        rc, out, err = self.c.call(["gh", "label", "list", "-R", self.slug, "--json", "name", "--limit", "500"])
        if rc == 0:
            r["labels"] = [x.get("name") for x in json.loads(out or "[]")]
        else:
            r["labels"] = []
        return r

    # ---- new repository
    def new_steps(self, remote):
        steps, notes = [], []
        if remote["exists"] and not remote.get("empty"):
            self.blocked = ("%s already exists and has branches: clone it (git clone %s) and run repoboot in that "
                            "checkout, which plans the drift fixes instead" % (self.slug, self.url))
            return steps, notes
        vis = self.spec("repo.visibility") or "private"
        if not remote["exists"]:
            argv = ["gh", "repo", "create", self.slug, "--" + vis]
            if self.spec("repo.description"):
                argv += ["--description", self.spec("repo.description")]
            steps.append(self.c.step("create", argv, "create the %s repository on GitHub" % vis))
        else:
            notes.append("%s exists and is empty: it is used as it is (no create)" % self.slug)
        steps.extend(self.c_push_steps())
        fields = self.desired_settings()
        fields["default_branch"] = self.branch
        steps.append(self.patch_step(fields))
        steps.append(self.ruleset_step())
        for name, text in self.labels():
            steps.append(self.label_step(name, text))
        if vis == "private":
            notes.append("private repository: the ruleset needs GitHub Pro/Team/Enterprise; on Free it is "
                         "reported as a warning, not a failure")
        return steps, notes

    def c_push_steps(self):
        out = []
        origin = self.e.facts.get("origin")
        if not origin:
            out.append(self.c.step("remote", ["git", "-C", self.e.dir, "remote", "add", "origin", self.url],
                                   "origin = %s" % self.url))
        elif origin != self.url:
            self.blocked = ("%s already has origin %s, not %s: fix the answers (repo.owner, repo.name) or the "
                            "remote first" % (self.e.dir, origin, self.url))
        out.append(self.c.step("push", ["git", "-C", self.e.dir, "push", "-u", "origin", self.branch],
                               "the initial push of %s — only after `git ls-remote` shows the remote has no branches"
                               % self.branch))
        return out

    def apply_new(self, steps, results, run_step):
        for s in steps:
            if s["id"] == "push" and not self.c_remote_empty(results):
                return False
            if not run_step(s, results):
                return False
        return True

    def c_remote_empty(self, results):
        rc, out, err = self.c.call(["git", "-C", self.e.dir, "ls-remote", "--heads", "origin"])
        if rc != 0 or out.strip():
            results.append({"id": "push", "status": "failed", "command": "git ls-remote --heads origin",
                            "message": "the remote is not empty (or unreadable: %s); nothing was pushed — "
                                       "clone it and run repoboot there" % (self.c.first_line(err) or "has branches")})
            return False
        return True

    # ---- existing repository
    def drift(self, remote):
        F, findings, steps = self.c.finding, [], []
        repo = remote.get("repo") or {}
        if not remote.get("exists"):
            return [F("fail", "remote", "%s does not exist" % self.slug, "repoboot apply")], []
        want = self.desired_settings()
        diff = {}
        for k in sorted(want):
            have = repo.get(k)
            if have is None and k.startswith("squash_merge_commit"):
                continue   # older API answers omit them
            if have != want[k]:
                diff[k] = want[k]
                findings.append(F("warn", "setting:" + k, "%s, the standard says %s" % (self.c.as_text(have), self.c.as_text(want[k]))))
            else:
                findings.append(F("ok", "setting:" + k, self.c.as_text(have)))
        if repo.get("default_branch") and repo.get("default_branch") != self.branch:
            findings.append(F("warn", "default_branch", "%s, the standard says %s (rename the branch in the web UI "
                              "or answer workflow.default_branch=%s)" % (repo["default_branch"], self.branch,
                                                                       repo["default_branch"])))
        if diff:
            s = self.patch_step(diff, note="align the merge settings with the standard")
            steps.append(s)
            for f in findings:
                if f["key"].startswith("setting:") and f["severity"] == "warn":
                    f["fix"] = s["command"]
        findings.extend(self.protection_findings(remote, steps))
        have = set(remote.get("labels") or [])
        for name, text in self.labels():
            if name in have:
                findings.append(F("ok", "label:" + name, "present"))
            else:
                s = self.label_step(name, text)
                steps.append(s)
                findings.append(F("warn", "label:" + name, "missing", s["command"]))
        return findings, steps

    def protection_findings(self, remote, steps):
        F = self.c.finding
        want = int(self.spec("workflow.required_approvals") or 0)
        rules = remote.get("rules")
        prot = remote.get("protection")
        if rules:
            kinds = dict((r.get("type"), r.get("parameters") or {}) for r in rules)
            pr = kinds.get("pull_request")
            missing = [k for k in ("pull_request", "non_fast_forward", "deletion") if k not in kinds]
            if pr is not None and int(pr.get("required_approving_review_count") or 0) < want:
                missing.append("%d approval(s)" % want)
            if not missing:
                return [F("ok", "protection", "default-branch rules: pull requests, no force-push, no deletion")]
            s = self.ruleset_step()
            steps.append(s)
            return [F("warn", "protection", "the default branch's rules lack: %s" % ", ".join(missing),
                      s["command"] + "  (body: repoboot plan --json)")]
        if prot:
            rev = prot.get("required_pull_request_reviews") or {}
            force = (prot.get("allow_force_pushes") or {}).get("enabled")
            if rev and int(rev.get("required_approving_review_count") or 0) >= want and not force:
                return [F("ok", "protection", "classic branch protection: pull requests, no force-push")]
        if remote.get("protection_status") == 403 and not rules:
            return [F("warn", "protection", "unavailable: " + PLAN_403)]
        s = self.ruleset_step()
        steps.append(s)
        return [F("warn", "protection", "the default branch is not protected", s["command"] + "  (body: repoboot plan --json)")]
