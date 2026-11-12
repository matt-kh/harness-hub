"""GitLab provider of repoboot (CE included): probes with `glab api` GETs, writes with `glab repo
create`, `glab api -X PUT|POST|DELETE` and `glab label create`. Loaded by repoboot.py
(Engine.provider); never run directly."""
import urllib.parse

ACCESS = {0: "no one", 30: "developers", 40: "maintainers"}
MERGE = {"squash": ("merge", "always"), "merge": ("merge", "default_off"), "rebase": ("ff", "never")}


class Provider(object):
    name = "gitlab"

    def __init__(self, e, core):
        self.e, self.c = e, core
        d = e.derived()
        self.slug, self.url, self.host = d["slug"], d["ssh_url"], d["server"]
        self.pid = urllib.parse.quote(self.slug, safe="")
        self.branch = e.default_branch()
        self.env = {"GITLAB_HOST": self.host}
        self.blocked = None
        if not self.host:
            raise core.UserError("no GitLab server: answer repo.server=<host> or set gitlab.host (HARNESS_GITLAB_HOST)")

    def spec(self, qid):
        return self.c.spec_get(self.e.spec, qid)

    def api(self, *args):
        return ["glab", "api", "--hostname", self.host] + list(args)

    # ---- answers -> desired state
    def desired_settings(self):
        method, squash = MERGE[self.spec("workflow.merge_method") or "squash"]
        ci = bool(self.c.as_list(self.spec("quality.ci_jobs")))
        return {"merge_method": method, "squash_option": squash,
                "only_allow_merge_if_pipeline_succeeds": ci,
                "only_allow_merge_if_all_discussions_are_resolved": True,
                "remove_source_branch_after_merge": self.e.remove_source_branch() == "true"}

    def labels(self):
        if not self.spec("workflow.agent_labels"):
            return []
        return [(name, self.c.LABEL_TEXT[role]) for role, name in self.c.agent_labels()]

    # ---- steps
    def put_step(self, fields, note="merge settings: method, squash, pipelines and threads, source-branch default"):
        argv = self.api("-X", "PUT", "projects/" + self.pid)
        for k in sorted(fields):
            v = fields[k]
            if isinstance(v, bool):
                argv += ["-F", "%s=%s" % (k, "true" if v else "false")]
            else:
                argv += ["-f", "%s=%s" % (k, v)]
        return self.c.step("settings", argv, note)

    def protection_steps(self, existing=True):
        enc = urllib.parse.quote(self.branch, safe="")
        out = []
        if existing:
            out.append(self.c.step("unprotect", self.api("-X", "DELETE", "projects/%s/protected_branches/%s" % (self.pid, enc)),
                                   "drop the instance-default protection of %s (re-created below)" % self.branch,
                                   tolerate={"404": "the branch was not protected yet"}))
        out.append(self.c.step("protection", self.api("-X", "POST", "projects/%s/protected_branches" % self.pid,
                                                      "-f", "name=" + self.branch, "-F", "push_access_level=0",
                                                      "-F", "merge_access_level=40", "-F", "allow_force_push=false"),
                               "protect %s: push no one, merge maintainers, no force-push" % self.branch))
        return out

    def label_step(self, name, text):
        color, desc = text
        return self.c.step("label:" + name, ["glab", "label", "create", "-R", self.slug, "-n", name,
                                             "-c", "#" + color, "-d", desc],
                           "provenance label %s" % name, env=self.env)

    # ---- probe (GET only)
    def get(self, path, missing_ok=(404,)):
        return self.c.read_json(self.api(path), missing_ok=missing_ok)

    def probe(self):
        st, proj = self.get("projects/" + self.pid)
        if st == 404 or proj is None:
            return {"exists": False, "summary": "%s/%s does not exist" % (self.host, self.slug)}
        r = {"exists": True, "project": proj, "empty": bool(proj.get("empty_repo")),
             "summary": "%s/%s exists (%s, %s)" % (self.host, self.slug, proj.get("visibility") or "?",
                                                   "empty" if proj.get("empty_repo") else
                                                   "default branch %s" % proj.get("default_branch"))}
        if not r["empty"]:
            st, pb = self.get("projects/%s/protected_branches/%s" % (
                self.pid, urllib.parse.quote(proj.get("default_branch") or self.branch, safe="")))
            r["protected"] = pb if st == 200 else None
        _st, labels = self.get("projects/%s/labels?per_page=100" % self.pid)
        r["labels"] = [x.get("name") for x in labels or []]
        return r

    # ---- new repository
    def new_steps(self, remote):
        steps, notes = [], []
        if remote["exists"] and not remote.get("empty"):
            self.blocked = ("%s/%s already exists and has commits: clone it (git clone %s) and run repoboot in that "
                            "checkout, which plans the drift fixes instead" % (self.host, self.slug, self.url))
            return steps, notes
        vis = self.spec("repo.visibility") or "private"
        if not remote["exists"]:
            argv = ["glab", "repo", "create", self.slug, "--" + vis, "--defaultBranch", self.branch]
            if self.spec("repo.description"):
                argv += ["--description", self.spec("repo.description")]
            steps.append(self.c.step("create", argv, "create the %s project on %s" % (vis, self.host), env=self.env))
        else:
            notes.append("%s exists and is empty: it is used as it is (no create)" % self.slug)
        origin = self.e.facts.get("origin")
        if not origin:
            steps.append(self.c.step("remote", ["git", "-C", self.e.dir, "remote", "add", "origin", self.url],
                                     "origin = %s" % self.url))
        elif origin != self.url:
            self.blocked = ("%s already has origin %s, not %s: fix the answers (repo.owner, repo.name, repo.server) "
                            "or the remote first" % (self.e.dir, origin, self.url))
        steps.append(self.c.step("push", ["git", "-C", self.e.dir, "push", "-u", "origin", self.branch],
                                 "the initial push of %s — only after `git ls-remote` shows the remote has no branches"
                                 % self.branch))
        fields = self.desired_settings()
        fields["default_branch"] = self.branch
        steps.append(self.put_step(fields))
        steps.extend(self.protection_steps())
        for name, text in self.labels():
            steps.append(self.label_step(name, text))
        if int(self.spec("workflow.required_approvals") or 0) > 0:
            notes.append("required approvals (%s) are a GitLab Premium feature: recorded in the spec and the README, "
                         "not enforced" % self.spec("workflow.required_approvals"))
        if self.e.remove_source_branch() == "false":
            notes.append("remove_source_branch_after_merge is off: the stack bundle needs it off on GitLab CE "
                         "(MRs still pass --remove-source-branch one by one)")
        return steps, notes

    def apply_new(self, steps, results, run_step):
        for s in steps:
            if s["id"] == "push":
                rc, out, err = self.c.call(["git", "-C", self.e.dir, "ls-remote", "--heads", "origin"])
                if rc != 0 or out.strip():
                    results.append({"id": "push", "status": "failed", "command": "git ls-remote --heads origin",
                                    "message": "the remote is not empty (or unreadable: %s); nothing was pushed — "
                                               "clone it and run repoboot there" % (self.c.first_line(err) or "has branches")})
                    return False
            if not run_step(s, results):
                return False
        return True

    # ---- existing repository
    def drift(self, remote):
        F, findings, steps = self.c.finding, [], []
        if not remote.get("exists"):
            return [F("fail", "remote", "%s does not exist" % self.slug, "repoboot apply")], []
        proj = remote.get("project") or {}
        want = self.desired_settings()
        diff = {}
        for k in sorted(want):
            have = proj.get(k)
            if have != want[k]:
                diff[k] = want[k]
                findings.append(F("warn", "setting:" + k, "%s, the standard says %s" % (self.c.as_text(have), self.c.as_text(want[k]))))
            else:
                findings.append(F("ok", "setting:" + k, self.c.as_text(have)))
        if proj.get("default_branch") and proj["default_branch"] != self.branch:
            findings.append(F("warn", "default_branch", "%s, the standard says %s (answer workflow.default_branch=%s "
                              "or change it in Settings → Repository)" % (proj["default_branch"], self.branch,
                                                                         proj["default_branch"])))
        if diff:
            s = self.put_step(diff, note="align the merge settings with the standard")
            steps.append(s)
            for f in findings:
                if f["key"].startswith("setting:") and f["severity"] == "warn":
                    f["fix"] = s["command"]
        pb = remote.get("protected")
        push = sorted(x.get("access_level") for x in (pb or {}).get("push_access_levels") or [])
        merge = sorted(x.get("access_level") for x in (pb or {}).get("merge_access_levels") or [])
        if pb and push == [0] and merge and min(merge) >= 40 and not pb.get("allow_force_push"):
            findings.append(F("ok", "protection", "%s: push no one, merge maintainers" % self.branch))
        else:
            ps = self.protection_steps(existing=bool(pb))
            steps.extend(ps)
            what = ("push %s, merge %s%s" % ("/".join(ACCESS.get(x, str(x)) for x in push) or "?",
                                             "/".join(ACCESS.get(x, str(x)) for x in merge) or "?",
                                             ", force-push allowed" if pb.get("allow_force_push") else "")
                    if pb else "not protected")
            findings.append(F("warn", "protection", "%s: %s; the standard says push no one, merge maintainers"
                              % (self.branch, what), " && ".join(s["command"] for s in ps)))
        have = set(remote.get("labels") or [])
        for name, text in self.labels():
            if name in have:
                findings.append(F("ok", "label:" + name, "present"))
            else:
                s = self.label_step(name, text)
                steps.append(s)
                findings.append(F("warn", "label:" + name, "missing", s["command"]))
        return findings, steps
