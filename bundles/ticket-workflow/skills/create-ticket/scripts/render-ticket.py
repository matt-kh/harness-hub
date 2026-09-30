#!/usr/bin/env python3
"""Render a Jira ticket deterministically from a ticket-model JSON.

Usage: render-ticket.py --model ticket.json --out-dir DIR [--facts facts.json] [--check]
                        [--provider jira|github]   (default jira)

--provider github writes body.md (GitHub Markdown, `- [ ]` acceptance), create.sh (ONE
`gh issue create -R owner/repo -t ... -F DIR/body.md -l agent-drafted[,...] [-a ...] [-m ...]`)
and preview.md; --check then enforces title <= 80, no GitHub closing keyword + #N /
owner/repo#N / issues URL in title or body, labels and milestone subset of facts
(agent-drafted must already exist). Jira-only field checks are skipped.

Writes into DIR:
  description.txt   Jira-wiki body (problem-description.txt instead when the type has no
                    description field: facts `has_description: false`, or a type rule with
                    body_field = "problem_description")
  create.sh         ONE `jira create ...` command line (the exact text the guard hook sees)
  preview.md        field table (+ "(default)" markers) + body + command

--check validates the model (summary <= 80 chars, required custom fields present, class/type
consistency, components/versions subset of facts, type rules, every custom field id known)
and exits non-zero.

Custom field ids (type_of_problem, category, epic_name, problem_description) resolve in this
order and are NEVER guessed: the model's field_ids -> the facts' field_ids for the type (by
field name) -> harness config jira.fields.<PROJECT>.<name> -> jira.fields.<name>. An id that
is needed but unknown is a CHECK FAIL (run create-facts.sh or set jira.fields).

Type rules come from the harness config `jira.issue_types` (a list of tables):
  name                    issue type name
  standalone = false      the type is a sub-task type; never create it on its own
  requires = [...]        model keys the type always needs (e.g. "epic_name")
  requires_without_facts  model keys needed only when no facts are given (facts carry the
                          project's real required fields)
  body_field              "description" (default) or "problem_description"
  hint                    appended to the requires error (e.g. allowed values)
Default when unset: Epic requires epic_name. Harness config: HARNESS_CONFIG_JSON / HARNESS_HOME.

Field-shape rules (Jira Server silently ignores wrong shapes, so they are fixed here):
  priority -> {"name"}   assignee -> {"name"}   components/versions/fixVersions -> [{"name"}]
  option custom fields -> {"value"}   labels -> ["agent-drafted", ...] (provenance label first)
"""
import argparse
import json
import os
import re
import shlex
import sys

# >>> harness_config
_HARNESS_CFG = None


def _harness_cfg_path():
    return os.environ.get("HARNESS_CONFIG_JSON") or os.path.join(
        os.environ.get("HARNESS_HOME") or os.path.expanduser("~/harness-hub"), "build", "config.json")


def cfg(key, default=None):
    """Dotted lookup in the compiled harness config, e.g. cfg("jira.url", "")."""
    global _HARNESS_CFG
    if _HARNESS_CFG is None:
        try:
            with open(_harness_cfg_path()) as fh:
                _HARNESS_CFG = json.load(fh)
        except (OSError, ValueError):
            _HARNESS_CFG = {}
        if not isinstance(_HARNESS_CFG, dict):
            _HARNESS_CFG = {}
    cur = _HARNESS_CFG
    for part in key.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur
# <<< harness_config


PROVENANCE_LABEL = "agent-drafted"
FOOTER = "----\nDrafted by Claude Code (create-ticket) for {drafted_by} on {date} — review and edit freely."
SUMMARY_MAX = 80
# model key -> Jira field name as createmeta reports it (facts field_ids are keyed by name)
FIELD_NAMES = {"type_of_problem": "Type of Problem", "category": "Category",
               "epic_name": "Epic Name", "problem_description": "Problem Description"}
GENERIC_TYPE_RULES = [{"name": "Epic", "requires": ["epic_name"]}]


def type_rules():
    rules = cfg("jira.issue_types")
    return [r for r in rules if isinstance(r, dict) and r.get("name")] if isinstance(rules, list) else GENERIC_TYPE_RULES


def type_rule(name):
    for r in type_rules():
        if r["name"] == name:
            return r
    return {}


def resolve_field_ids(m, facts):
    """Fill m["field_ids"] for every known model key; never invent an id."""
    ids = dict(m.get("field_ids") or {})
    ftype = {}
    for t in (facts or {}).get("types", []):
        if t.get("name") == m.get("type"):
            ftype = t.get("field_ids") or {}
    proj = cfg("jira.fields." + str(m.get("project")), {}) if m.get("project") else {}
    glob = cfg("jira.fields", {})
    for key, fname in FIELD_NAMES.items():
        if ids.get(key):
            continue
        for src in (ftype.get(fname), (proj or {}).get(key) if isinstance(proj, dict) else None,
                    glob.get(key) if isinstance(glob, dict) else None):
            if isinstance(src, dict):
                src = src.get("id")
            if isinstance(src, str) and src:
                ids[key] = src
                break
    m["field_ids"] = ids
    return ids


def needed_fields(m, body_in_problem_description):
    need = [k for k in ("type_of_problem", "category", "epic_name") if m.get(k)]
    if body_in_problem_description or (m.get("problem_description_echo") and m.get("problem")):
        need.append("problem_description")
    return need


def die(msg):
    print(f"render-ticket: {msg}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------- summary
def render_summary(m):
    s = " ".join((m.get("summary") or "").split()).rstrip(".").strip()
    if not s:
        die("summary is empty")
    prog = (m.get("program") or "").strip().strip("[]")
    if prog and not s.startswith("["):
        s = f"[{prog}] {s}"
    return s


# ---------------------------------------------------------------- body templates
def _list(items):
    return "\n".join(f" # {i}" for i in items if str(i).strip())


def _section(label, value):
    return f"*{label}:* {value}" if value else ""


def body_defect(m):
    steps = [s for s in m.get("steps") or [] if str(s).strip()] or ["_to be captured_"]
    lines = ["Steps to reproduce:"]
    lines += [f"Step {i}: {s}" for i, s in enumerate(steps, 1)]
    lines.append(f"Actual Output: {m.get('actual') or '_to be captured_'}")
    lines.append(f"Expected Output: {m.get('expected') or '_to be captured_'}")
    env = m.get("environment") or ""
    if m.get("affects_versions"):
        env = (env + ", " if env else "") + "found in " + ", ".join(m["affects_versions"])
    extra = [
        _section("Affected Region", m.get("affected_region")),
        _section("Environment / Version", env),
        _section("Evidence", " ".join(f"[{e}]" for e in m.get("evidence") or [])),
        _section("Related", ", ".join(m.get("related") or [])),
    ]
    extra = [e for e in extra if e]
    return "\n".join(lines) + ("\n\n" + "\n".join(extra) if extra else "")


def body_enhancement(m):
    parts = []
    ctx = " ".join(x for x in [m.get("problem"), m.get("motivation")] if x)
    if ctx:
        parts.append(_section("Context", ctx))
    if m.get("goal"):
        parts.append(_section("Goal", m["goal"]))
    if m.get("proposed_change"):
        parts.append(_section("Proposed change", m["proposed_change"]))
    if m.get("acceptance"):
        parts.append("*Acceptance criteria:*\n" + _list(m["acceptance"]))
    if m.get("where_to_test"):
        parts.append(_section("Where to test", "; ".join(m["where_to_test"])))
        parts.append("*What to test:*\n" + _list(m.get("what_to_test") or m.get("acceptance") or []))
    if m.get("out_of_scope"):
        parts.append("*Out of scope:*\n" + _list(m["out_of_scope"]))
    if m.get("related"):
        parts.append(_section("Related", ", ".join(m["related"])))
    if not parts:
        die("enhancement body has no content (need problem/goal/proposed_change/acceptance)")
    return "\n\n".join(parts)


def body_epic(m):
    parts = [_section("Goal", " ".join(x for x in [m.get("problem"), m.get("motivation")] if x))]
    if m.get("acceptance"):
        parts.append("*Scope:*\n" + _list(m["acceptance"]))
    if m.get("children"):
        parts.append("*Child work (to be split into tickets):*\n" + _list(m["children"]))
    if m.get("out_of_scope"):
        parts.append("*Out of scope:*\n" + _list(m["out_of_scope"]))
    return "\n\n".join(p for p in parts if p)


def render_body(m):
    cls = m.get("class")
    if cls == "defect":
        body = body_defect(m)
    elif cls in ("enhancement", "chore"):
        body = body_enhancement(m)
    elif cls == "epic":
        body = body_epic(m)
    elif cls == "swtask":
        body = body_defect(m) if m.get("steps") else body_enhancement(m)
    else:
        die(f"unknown class '{cls}'")
    meta = m.get("meta") or {}
    return body + "\n\n" + FOOTER.format(drafted_by=meta.get("drafted_by", "?"), date=meta.get("date", "?"))


# ---------------------------------------------------------------- command
def build_fields(m, summary, body_path, body_in_problem_description):
    fid = m.get("field_ids") or {}
    fields = []  # list of (name, json-string)
    labels = list(m.get("labels") or [])
    if PROVENANCE_LABEL in labels:
        labels.remove(PROVENANCE_LABEL)
    labels = [PROVENANCE_LABEL] + labels
    fields.append(("labels", json.dumps(labels, separators=(",", ":"))))
    if m.get("priority"):
        fields.append(("priority", json.dumps({"name": m["priority"]}, separators=(",", ":"))))
    if m.get("assignee"):
        fields.append(("assignee", json.dumps({"name": m["assignee"]}, separators=(",", ":"))))
    missing = [k for k in needed_fields(m, body_in_problem_description) if not fid.get(k)]
    if missing:
        die(f"field id unknown for {', '.join(missing)} — run create-facts.sh {m.get('project')} "
            f"or set jira.fields.{m.get('project')}.<name> in the harness config")
    if m.get("type_of_problem"):
        fields.append((fid["type_of_problem"],
                       json.dumps({"value": m["type_of_problem"]}, separators=(",", ":"))))
    if m.get("category"):
        fields.append((fid["category"],
                       json.dumps({"value": m["category"]}, separators=(",", ":"))))
    if m.get("epic_name"):
        fields.append((fid["epic_name"], m["epic_name"]))
    for key, name in (("affects_versions", "versions"), ("fix_versions", "fixVersions"), ("components", "components")):
        if m.get(key):
            fields.append((name, json.dumps([{"name": v} for v in m[key]], separators=(",", ":"))))
    pd_id = fid.get("problem_description")
    if body_in_problem_description:
        fields.append((pd_id, f'$(cat {shlex.quote(body_path)})'))
    elif m.get("problem_description_echo") and m.get("problem"):
        fields.append((pd_id, m["problem"]))
    return fields


def build_command(m, summary, body_path, body_in_problem_description):
    parts = ["jira", "create", shlex.quote(m["project"]), shlex.quote(m["type"]), shlex.quote(summary)]
    if not body_in_problem_description:
        parts += ["--description", f'"$(cat {shlex.quote(body_path)})"']
    for name, val in build_fields(m, summary, body_path, body_in_problem_description):
        if val.startswith("$(cat "):
            parts += ["--field", f'{name}="{val}"']
        else:
            parts += ["--field", shlex.quote(f"{name}={val}")]
    return " ".join(parts)


# ---------------------------------------------------------------- check
def check(m, facts, summary, body_in_problem_description=False):
    errs = []
    if len(summary) > SUMMARY_MAX:
        errs.append(f"summary is {len(summary)} chars (max {SUMMARY_MAX})")
    if re.search(r"\b[A-Z][A-Z0-9_]*-\d+\b", summary):
        errs.append("summary must not contain a ticket key")
    rule = type_rule(m.get("type"))
    if rule.get("standalone") is False:
        errs.append(f"{m.get('type')} is a sub-task type; never create it standalone")
    hint = f" ({rule['hint']})" if rule.get("hint") else ""
    for k in list(rule.get("requires") or []) + (list(rule.get("requires_without_facts") or []) if facts is None else []):
        if not m.get(k):
            errs.append(f"{m.get('type')} requires {k}{hint}")
    fid = m.get("field_ids") or {}
    for k in needed_fields(m, body_in_problem_description):
        if not fid.get(k):
            errs.append(f"field id for {k} unknown — run create-facts.sh {m.get('project')} "
                        f"or set jira.fields.{m.get('project')}.{k} in the harness config (never guessed)")
    if facts:
        tnames = {t["name"] for t in facts.get("types", [])}
        if tnames and m.get("type") not in tnames:
            errs.append(f"type '{m.get('type')}' not in project types {sorted(tnames)}")
        for t in facts.get("types", []):
            if t["name"] == m.get("type"):
                have = {"type_of_problem": m.get("type_of_problem"), "category": m.get("category"),
                        "epic_name": m.get("epic_name")}
                names = {"Type of Problem": "type_of_problem", "Category": "category", "Epic Name": "epic_name"}
                for r in t.get("required", []):
                    k = names.get(r["name"])
                    if k and not have.get(k):
                        errs.append(f"{m['type']} requires '{r['name']}' ({r['id']})")
                    if k and have.get(k) and r.get("allowed") and have[k] not in r["allowed"]:
                        errs.append(f"'{have[k]}' not an allowed value for {r['name']}: {r['allowed']}")
        comps = set(facts.get("components", []))
        for c in m.get("components") or []:
            if comps and c not in comps:
                errs.append(f"component '{c}' does not exist (never invent components)")
        vers = {v["name"] for v in facts.get("versions_unreleased", [])}
        for v in (m.get("fix_versions") or []) + (m.get("affects_versions") or []):
            if vers and v not in vers:
                errs.append(f"version '{v}' is not an unreleased version of {facts.get('project')}")
        if facts.get("priorities") and m.get("priority") not in facts["priorities"]:
            errs.append(f"priority '{m.get('priority')}' not in {facts['priorities']}")
    return errs


# ---------------------------------------------------------------- preview
def preview(m, summary, body, cmd):
    src = (m.get("meta") or {}).get("sources", {})

    def mark(k):
        return " (default)" if src.get(k) == "default" else ""

    rows = [
        ("Project", m["project"] + mark("project")), ("Type", m["type"] + mark("type")),
        ("Summary", summary + mark("summary")),
        ("Type of Problem", (m.get("type_of_problem") or "—") + mark("type_of_problem")),
        ("Category", (m.get("category") or "—") + mark("category")),
        ("Priority", (m.get("priority") or "—") + mark("priority")),
        ("Assignee", (m.get("assignee") or "unassigned") + mark("assignee")),
        ("Affects Version", ", ".join(m.get("affects_versions") or []) or "—"),
        ("Fix Version", ", ".join(m.get("fix_versions") or []) or "—"),
        ("Components", ", ".join(m.get("components") or []) or "—"),
        ("Labels", ", ".join([PROVENANCE_LABEL] + [l for l in m.get("labels") or [] if l != PROVENANCE_LABEL])),
        ("Attachments (after create)", ", ".join(m.get("attachments") or []) or "—"),
    ]
    table = "| field | value |\n|---|---|\n" + "\n".join(f"| {k} | {v} |" for k, v in rows)
    where = "Problem Description (this type has no description field)" if "problem-description.txt" in cmd else "Description"
    return f"## Ticket preview\n\n{table}\n\n### {where} (Jira wiki)\n```\n{body}\n```\n\n### Command (run verbatim on Create)\n```bash\n{cmd}\n```\n"


# ================================================================ GitHub provider
# Markdown body, `gh issue create`, GitHub-specific checks. Jira output above is untouched.
GH_CLASS_LABEL = {"defect": "bug", "enhancement": "enhancement"}  # chore/epic: none
# GitHub closing keywords followed by #N, owner/repo#N or an issues URL (case-insensitive).
GH_CLOSE_RE = re.compile(
    r"\b(close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b[\s:]+"
    r"(#\d+|[\w.-]+/[\w.-]+#\d+|https?://github\.com/[\w.-]+/[\w.-]+/issues/\d+)",
    re.IGNORECASE)
GH_FOOTER = "---\n_Drafted by Claude Code (create-ticket) for {drafted_by} on {date} — review and edit freely._"


def _md_list(items, marker="-"):
    items = [str(i) for i in items or [] if str(i).strip()]
    if marker == "1.":
        return "\n".join(f"{n}. {i}" for n, i in enumerate(items, 1))
    return "\n".join(f"{marker} {i}" for i in items)


def _md_section(label, value):
    return f"**{label}:** {value}" if value else ""


def gh_body_defect(m):
    steps = [s for s in m.get("steps") or [] if str(s).strip()] or ["_to be captured_"]
    parts = ["**Steps to reproduce**\n" + _md_list(steps, "1."),
             _md_section("Actual", m.get("actual") or "_to be captured_"),
             _md_section("Expected", m.get("expected") or "_to be captured_")]
    env = m.get("environment") or ""
    if m.get("affects_versions"):
        env = (env + ", " if env else "") + "found in " + ", ".join(m["affects_versions"])
    parts += [_md_section("Affected region", m.get("affected_region")),
              _md_section("Environment / version", env),
              _md_section("Evidence", " ".join(f"<{e}>" if "://" in e else e for e in m.get("evidence") or [])),
              _md_section("Related", ", ".join(m.get("related") or []))]
    return "\n\n".join(p for p in parts if p)


def gh_body_enhancement(m):
    parts = []
    ctx = " ".join(x for x in [m.get("problem"), m.get("motivation")] if x)
    parts.append(_md_section("Context", ctx))
    parts.append(_md_section("Goal", m.get("goal")))
    parts.append(_md_section("Proposed change", m.get("proposed_change")))
    if m.get("acceptance"):
        parts.append("**Acceptance criteria**\n" + _md_list(m["acceptance"], "- [ ]"))
    if m.get("where_to_test"):
        parts.append(_md_section("Where to test", "; ".join(m["where_to_test"])))
        parts.append("**What to test**\n" + _md_list(m.get("what_to_test") or m.get("acceptance") or [], "1."))
    if m.get("out_of_scope"):
        parts.append("**Out of scope**\n" + _md_list(m["out_of_scope"]))
    parts.append(_md_section("Related", ", ".join(m.get("related") or [])))
    parts = [p for p in parts if p]
    if not parts:
        die("enhancement body has no content (need problem/goal/proposed_change/acceptance)")
    return "\n\n".join(parts)


def gh_body_epic(m):
    parts = [_md_section("Goal", " ".join(x for x in [m.get("problem"), m.get("motivation")] if x))]
    if m.get("acceptance"):
        parts.append("**Scope**\n" + _md_list(m["acceptance"], "- [ ]"))
    if m.get("children"):
        parts.append("**Child work (to be split into issues)**\n" + _md_list(m["children"], "- [ ]"))
    if m.get("out_of_scope"):
        parts.append("**Out of scope**\n" + _md_list(m["out_of_scope"]))
    return "\n\n".join(p for p in parts if p)


def gh_render_body(m):
    cls = m.get("class")
    if cls == "defect":
        body = gh_body_defect(m)
    elif cls in ("enhancement", "chore"):
        body = gh_body_enhancement(m)
    elif cls == "epic":
        body = gh_body_epic(m)
    else:
        die(f"class '{cls}' is not supported for GitHub (defect|enhancement|chore|epic)")
    meta = m.get("meta") or {}
    return body + "\n\n" + GH_FOOTER.format(drafted_by=meta.get("drafted_by", "?"), date=meta.get("date", "?"))


def gh_labels(m, facts):
    """agent-drafted first, then the class label (only if the repo has it), then model labels."""
    labels = [PROVENANCE_LABEL]
    cl = GH_CLASS_LABEL.get(m.get("class"))
    if cl and facts is not None and cl in (facts.get("labels") or []):
        labels.append(cl)
    for l in m.get("labels") or []:
        if l not in labels:
            labels.append(l)
    return labels


def gh_build_command(m, summary, body_path, labels):
    parts = ["gh", "issue", "create", "-R", shlex.quote(m["project"]), "-t", shlex.quote(summary),
             "-F", shlex.quote(body_path), "-l", shlex.quote(",".join(labels))]
    if m.get("assignee"):
        parts += ["-a", shlex.quote(m["assignee"])]
    if m.get("milestone"):
        parts += ["-m", shlex.quote(m["milestone"])]
    return " ".join(parts)


def gh_check(m, facts, summary, body, labels):
    errs = []
    proj = m.get("project") or ""
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", proj):
        errs.append(f"project '{proj}' must be owner/repo for GitHub")
    if len(summary) > SUMMARY_MAX:
        errs.append(f"summary is {len(summary)} chars (max {SUMMARY_MAX})")
    for where, text in (("title", summary), ("body", body)):
        hit = GH_CLOSE_RE.search(text)
        if hit:
            errs.append(f"{where} contains a GitHub closing keyword ('{hit.group(0)}') — mention #N instead")
    if facts:
        if facts.get("provider") not in (None, "github"):
            errs.append(f"facts are for provider '{facts.get('provider')}', not github")
        if facts.get("project") and facts["project"].lower() != proj.lower():
            errs.append(f"facts are for '{facts['project']}', model says '{proj}'")
        if facts.get("creatable") is False:
            errs.append(f"issues are disabled (or unreadable) in {proj}")
        have = set(facts.get("labels") or [])
        if PROVENANCE_LABEL not in have:
            errs.append(f"label '{PROVENANCE_LABEL}' missing in {proj}: create it first "
                        f"(gh label create {PROVENANCE_LABEL} -R {proj} ...) and re-run create-facts.sh")
        for l in labels:
            if l != PROVENANCE_LABEL and l not in have:
                errs.append(f"label '{l}' does not exist in {proj} (never invent labels)")
        ms = m.get("milestone")
        if ms and ms not in (facts.get("milestones") or []):
            errs.append(f"milestone '{ms}' is not an open milestone of {proj}")
        if m.get("assignee") and facts.get("can_assign") is False:
            errs.append(f"no permission to assign in {proj} (needs WRITE); drop the assignee")
    return errs


def gh_preview(m, summary, body, cmd, labels):
    src = (m.get("meta") or {}).get("sources", {})

    def mark(k):
        return " (default)" if src.get(k) == "default" else ""

    rows = [
        ("Repository", m["project"] + mark("project")), ("Class", (m.get("class") or "—") + mark("class")),
        ("Title", summary + mark("summary")),
        ("Labels", ", ".join(labels)),
        ("Assignee", (m.get("assignee") or "unassigned") + mark("assignee")),
        ("Milestone", (m.get("milestone") or "—") + mark("milestone")),
        ("Attachments (web UI, after create)", ", ".join(m.get("attachments") or []) or "—"),
    ]
    table = "| field | value |\n|---|---|\n" + "\n".join(f"| {k} | {v} |" for k, v in rows)
    return (f"## Issue preview\n\n{table}\n\n### Body (GitHub Markdown)\n```markdown\n{body}\n```\n\n"
            f"### Command (run verbatim on Create)\n```bash\n{cmd}\n```\n")


def main_github(a, m, facts):
    summary = render_summary(m)
    body = gh_render_body(m)
    labels = gh_labels(m, facts)
    if a.check:
        errs = gh_check(m, facts, summary, body, labels)
        if errs:
            for e in errs:
                print(f"CHECK FAIL: {e}", file=sys.stderr)
            sys.exit(2)
    os.makedirs(a.out_dir, exist_ok=True)
    body_path = os.path.join(a.out_dir, "body.md")
    with open(body_path, "w") as f:
        f.write(body + "\n")
    cmd = gh_build_command(m, summary, body_path, labels)
    with open(os.path.join(a.out_dir, "create.sh"), "w") as f:
        f.write(cmd + "\n")
    with open(os.path.join(a.out_dir, "preview.md"), "w") as f:
        f.write(gh_preview(m, summary, body, cmd, labels))
    print(os.path.join(a.out_dir, "preview.md"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--facts")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--provider", choices=("jira", "github"), default="jira")
    a = ap.parse_args()
    with open(a.model) as f:
        m = json.load(f)
    facts = None
    if a.facts:
        with open(a.facts) as f:
            facts = json.load(f)
    if a.provider == "github":
        return main_github(a, m, facts)
    resolve_field_ids(m, facts)
    # body placement: description when the type has one (facts), else Problem Description
    body_in_pd = type_rule(m.get("type")).get("body_field") == "problem_description"
    if facts:
        for t in facts.get("types", []):
            if t["name"] == m.get("type") and "has_description" in t:
                body_in_pd = not t["has_description"]
    summary = render_summary(m)
    if a.check:
        errs = check(m, facts, summary, body_in_pd)
        if errs:
            for e in errs:
                print(f"CHECK FAIL: {e}", file=sys.stderr)
            sys.exit(2)
    body = render_body(m)
    os.makedirs(a.out_dir, exist_ok=True)
    body_path = os.path.join(a.out_dir, "problem-description.txt" if body_in_pd else "description.txt")
    with open(body_path, "w") as f:
        f.write(body + "\n")
    cmd = build_command(m, summary, body_path, body_in_pd)
    with open(os.path.join(a.out_dir, "create.sh"), "w") as f:
        f.write(cmd + "\n")
    with open(os.path.join(a.out_dir, "preview.md"), "w") as f:
        f.write(preview(m, summary, body, cmd))
    print(os.path.join(a.out_dir, "preview.md"))


if __name__ == "__main__":
    main()
