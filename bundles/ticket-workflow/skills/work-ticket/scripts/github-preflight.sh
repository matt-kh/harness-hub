#!/usr/bin/env bash
# work-ticket GitHub preflight: READ-ONLY repo facts as one JSON object. Never writes.
# Usage: github-preflight.sh [ISSUE] [CANDIDATE_BRANCH ...]
#   ISSUE  = N | #N | owner/repo#N | https://github.com/owner/repo/issues/N  (optional; enables existing_prs)
#   CANDIDATE_BRANCH = ticket / sub branch names tested against protection rules and Actions filters
# Normally reached through preflight.sh (provider dispatcher). Every gh call is wrapped in
# `hn_timeout 20` and tolerated: without gh or auth it emits auth_ok:false plus the local facts.
# REST calls are GETs only (never -f/-F/--input/-X, which would switch gh to POST); the one
# GraphQL call is an anonymous read `query` (branch-protection patterns), never a mutation.
# Override the binary with WORK_TICKET_GH (tests / stubs).
set -uo pipefail
# >>> hn_timeout
hn_timeout() {  # SECS CMD [ARGS...]
  local s=$1; shift
  if command -v timeout >/dev/null 2>&1; then timeout "$s" "$@"
  elif command -v gtimeout >/dev/null 2>&1; then gtimeout "$s" "$@"
  else
    python3 -c 'import subprocess, sys
try:
    sys.exit(subprocess.call(sys.argv[2:], timeout=float(sys.argv[1])))
except subprocess.TimeoutExpired:
    sys.exit(124)
except OSError:
    sys.exit(127)' "$s" "$@"
  fi
}
# <<< hn_timeout
# shellcheck source=lib/repo-facts.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib/repo-facts.sh"
rf_load                                   # root host def dirty precommit repo_skill

GH="${WORK_TICKET_GH:-gh}"
export GH_PROMPT_DISABLED=1 GH_NO_UPDATE_NOTIFIER=1 GH_PAGER=cat NO_COLOR=1
warnings=()
gh_installed=false; command -v "$GH" >/dev/null 2>&1 && gh_installed=true

# ghc ARGS...  -> stdout of gh (stderr to $GHERR), exit code preserved; never fails the script
GHERR=$(mktemp); trap 'rm -f "$GHERR"' EXIT
ghc() {
  [ "$gh_installed" = true ] || { echo "gh not installed" >"$GHERR"; return 127; }
  (cd "$root" && hn_timeout 20 "$GH" "$@" 2>"$GHERR")
}
http_of() { grep -oE 'HTTP [0-9]{3}' "$GHERR" 2>/dev/null | head -1 | awk '{print $2}'; }
json_or() { local v="$1" d="$2"; if [ -n "$v" ] && jq -e . <<<"$v" >/dev/null 2>&1; then printf '%s' "$v"; else printf '%s' "$d"; fi; }

# ---- issue ref ($1) ---------------------------------------------------------------------
issue_ref="" issue_repo="" issue_num=""
if [ $# -gt 0 ]; then
  case "$1" in
    https://github.com/*/*/issues/[0-9]*|http://github.com/*/*/issues/[0-9]*)
      issue_ref="$1"; p="${1#*://github.com/}"; issue_repo=$(cut -d/ -f1,2 <<<"$p"); issue_num=$(cut -d/ -f4 <<<"$p" | grep -oE '^[0-9]+'); shift ;;
    */*\#[0-9]*) issue_ref="$1"; issue_repo="${1%%#*}"; issue_num="${1##*#}"; shift ;;
    \#[0-9]*)    issue_ref="$1"; issue_num="${1#\#}"; shift ;;
    [0-9]*)      if [[ "$1" =~ ^[0-9]+$ ]]; then issue_ref="$1"; issue_num="$1"; shift; fi ;;
  esac
fi
[[ "$issue_num" =~ ^[0-9]+$ ]] || issue_num=""
candidates=("$@")

# ---- auth / identity --------------------------------------------------------------------
auth_ok=false
if ghc auth status --hostname github.com >/dev/null; then auth_ok=true
else warnings+=("gh auth status failed: $(head -c 200 "$GHERR" | tr '\n' ' ')"); fi
user='{}'; if [ "$auth_ok" = true ]; then user=$(json_or "$(ghc api user)" '{}'); fi
me=$(jq -r '.login // empty' <<<"$user"); plan=$(jq -r '.plan.name // empty' <<<"$user")

# ---- repos: origin (from the remote URL), base (set-default, else parent of a fork, else origin)
origin_repo=$(git -C "$root" remote get-url origin 2>/dev/null \
  | sed -E 's#^[a-z]+://([^@/]*@)?[^/:]+[:/]##; s#^[^@]*@[^:]+:##; s#\.git$##; s#/+$##' | cut -d/ -f1,2)
base_repo=""
if [ "$auth_ok" = true ]; then
  base_repo=$(ghc repo set-default --view | tr -d '[:space:]'); [[ "$base_repo" == */* ]] || base_repo=""
fi
FIELDS=nameWithOwner,isPrivate,isFork,parent,viewerPermission,viewerCanAdminister,defaultBranchRef,deleteBranchOnMerge,squashMergeAllowed,mergeCommitAllowed,rebaseMergeAllowed,hasIssuesEnabled,isArchived,visibility
repo='null'
if [ "$auth_ok" = true ]; then
  origin_view=$(json_or "$(ghc repo view "${base_repo:-$origin_repo}" --json "$FIELDS")" 'null')
  if [ -z "$base_repo" ] && [ "$(jq -r '.isFork // false' <<<"$origin_view")" = true ]; then
    base_repo=$(jq -r '.parent | "\(.owner.login)/\(.name)"' <<<"$origin_view")
    repo=$(json_or "$(ghc repo view "$base_repo" --json "$FIELDS")" 'null')
  else
    repo="$origin_view"
  fi
  [ "$repo" = null ] && warnings+=("gh repo view failed: $(head -c 200 "$GHERR" | tr '\n' ' ')")
fi
[ -n "$base_repo" ] || base_repo="$origin_repo"
[ -n "$def" ] || def=$(jq -r '.defaultBranchRef.name // empty' <<<"$repo")
perm=$(jq -r '.viewerPermission // empty' <<<"$repo")
is_private=$(jq -r 'if . == null then "" else (.isPrivate|tostring) end' <<<"$repo")

# ---- protection: classic (default branch + GraphQL patterns) and rulesets, 403/404 tolerant
branch_rules_json='{}'   # candidate branch -> [rule types] (built as JSON: no bash-4 associative arrays)
bp='{"status":"unavailable"}'; bp_patterns='null'; rulesets='{"status":"unavailable","items":[]}'
if [ "$auth_ok" = true ] && [ -n "$base_repo" ]; then
  if [ -n "$def" ]; then
    out=$(ghc api "repos/$base_repo/branches/$def/protection"); rc=$?; code=$(http_of)
    if [ $rc -eq 0 ]; then
      bp=$(jq -c '{status:"protected", required_reviews:(.required_pull_request_reviews.required_approving_review_count // null),
                   required_status_checks:(.required_status_checks.contexts // []), enforce_admins:.enforce_admins.enabled,
                   allow_force_pushes:.allow_force_pushes.enabled, linear_history:.required_linear_history.enabled}' <<<"$out" 2>/dev/null || echo '{"status":"parse-failed"}')
    elif [ "$code" = 404 ]; then bp='{"status":"not_protected","http":404}'
    elif [ "$code" = 403 ]; then bp='{"status":"forbidden","http":403,"note":"Free private repo or no admin"}'
    else bp=$(jq -cn --arg c "${code:-}" '{status:"error", http:(if $c=="" then null else ($c|tonumber) end)}'); fi
  fi
  owner="${base_repo%%/*}"; name="${base_repo#*/}"
  q='query($o:String!,$n:String!){repository(owner:$o,name:$n){branchProtectionRules(first:50){nodes{pattern requiresApprovingReviews requiredApprovingReviewCount allowsForcePushes}}}}'
  bp_patterns=$(ghc api graphql -f query="$q" -F o="$owner" -F n="$name" \
                | jq -c 'if .data.repository.branchProtectionRules then [.data.repository.branchProtectionRules.nodes[]?] else empty end' 2>/dev/null)
  bp_patterns=$(json_or "$bp_patterns" 'null')
  out=$(ghc api "repos/$base_repo/rulesets?includes_parents=true&per_page=100"); rc=$?; code=$(http_of)
  if [ $rc -eq 0 ] && jq -e 'type=="array"' <<<"$out" >/dev/null 2>&1; then
    items='[]'
    while read -r rid; do
      [ -n "$rid" ] || continue
      one=$(json_or "$(ghc api "repos/$base_repo/rulesets/$rid")" 'null')
      [ "$one" = null ] && continue
      items=$(jq -c --argjson r "$one" '. + [$r | {id, name, target, enforcement,
               include:(.conditions.ref_name.include // []), exclude:(.conditions.ref_name.exclude // []),
               rules:[.rules[]?.type]}]' <<<"$items")
    done < <(jq -r '.[] | select(.target == "branch" or .target == null) | .id' <<<"$out" | head -20)
    rulesets=$(jq -c '{status:"ok", items:.}' <<<"$items")
  elif [ "$code" = 404 ]; then rulesets='{"status":"not_available","http":404,"items":[]}'
  elif [ "$code" = 403 ]; then rulesets='{"status":"forbidden","http":403,"items":[]}'
  else rulesets='{"status":"error","items":[]}'; fi
  for b in "${candidates[@]}"; do
    out=$(ghc api "repos/$base_repo/rules/branches/$b"); rc=$?
    if [ $rc -eq 0 ] && jq -e 'type=="array"' <<<"$out" >/dev/null 2>&1; then
      branch_rules_json=$(jq -c --arg b "$b" --argjson v "$(jq -c '[.[].type]' <<<"$out")" '. + {($b):$v}' <<<"$branch_rules_json")
    fi
  done
fi

prot_json=$(python3 - "$def" "$bp" "$bp_patterns" "$rulesets" "$branch_rules_json" "${candidates[@]}" <<'PY' 2>/dev/null
import sys, json, re
default, bp, pats, rs, brules = sys.argv[1], *map(json.loads, sys.argv[2:6])
cands = sys.argv[6:]
def glob_re(p):
    out, i = "", 0
    while i < len(p):
        c = p[i]
        if p.startswith("**", i): out += ".*"; i += 2; continue
        out += {"*": "[^/]*", "?": "[^/]"}.get(c, re.escape(c)); i += 1
    return re.compile("^" + out + "$")
def strip(p): return p[len("refs/heads/"):] if p.startswith("refs/heads/") else p
def matches(pattern, b):
    if pattern == "~ALL": return True
    if pattern == "~DEFAULT_BRANCH": return b == default
    return bool(glob_re(strip(pattern)).match(b))
rules = []
for n in (pats or []):
    rules.append({"name": n.get("pattern"), "source": "branch_protection",
                  "required_reviews": n.get("requiredApprovingReviewCount") if n.get("requiresApprovingReviews") else 0,
                  "allows_force_pushes": n.get("allowsForcePushes")})
if pats is None and bp.get("status") == "protected":
    rules.append({"name": default, "source": "branch_protection", "required_reviews": bp.get("required_reviews")})
for r in rs.get("items", []):
    if r.get("enforcement") == "disabled": continue
    for inc in r.get("include", []):
        rules.append({"name": strip(inc), "source": "ruleset:" + str(r.get("name")), "enforcement": r.get("enforcement"),
                      "exclude": [strip(e) for e in r.get("exclude", [])], "rules": r.get("rules", [])})
def hit(rule, b):
    return matches(rule["name"], b) and not any(matches(e, b) for e in rule.get("exclude", []))
m = {b: (any(hit(r, b) for r in rules) or bool(brules.get(b))) for b in cands}
print(json.dumps({
    "rules": rules,
    "wildcards": [r["name"] for r in rules if any(ch in r["name"] for ch in "*?[") or r["name"] == "~ALL"],
    "matches": m,
    "sub_pattern_matches": any(hit(r, "zz-ticket-sub-01-part") or "-sub-" in r["name"] for r in rules),
    "branch_rules": brules,
    "default_branch_protection": bp,
    "rulesets_status": rs.get("status"),
    "patterns_visible": pats is not None}))
PY
)
prot_json=$(json_or "$prot_json" '{"rules":[],"wildcards":[],"matches":{},"sub_pattern_matches":false}')

# ---- derived permissions / plan ----------------------------------------------------------
can_label=null fork_flow=null draft=null
case "$perm" in
  ADMIN|MAINTAIN|WRITE) can_label=true;  fork_flow=false ;;
  READ|TRIAGE)          can_label=false; fork_flow=true ;;
esac
if [ "$is_private" = false ]; then draft=true
elif [ "$is_private" = true ]; then
  if [ -n "$plan" ] && [ "$plan" != free ]; then draft=true; else draft=false; fi
fi

# ---- templates / codeowners (local checkout; GitHub matches names case-insensitively) -----
first_file() { local f; for f in "$@"; do f=$(find "$root/$(dirname "$f")" -maxdepth 1 -type f -iname "$(basename "$f")" 2>/dev/null | head -1); [ -n "$f" ] && { echo "$f"; return; }; done; }
tmpl=$(first_file .github/pull_request_template.md pull_request_template.md docs/pull_request_template.md)
pr_multi=$(find "$root/.github" -maxdepth 1 -type d -iname pull_request_template -print0 2>/dev/null \
  | xargs -0 -I{} find {} -maxdepth 1 -type f -iname '*.md' 2>/dev/null | sort | jq -R . | jq -sc .)
issue_tmpls=$(find "$root/.github" -maxdepth 1 -type d -iname issue_template -print0 2>/dev/null \
  | xargs -0 -I{} find {} -maxdepth 1 -type f 2>/dev/null | sort | jq -R . | jq -sc .)
codeowners=$(first_file .github/CODEOWNERS CODEOWNERS docs/CODEOWNERS)
contributing=$(first_file .github/CONTRIBUTING.md CONTRIBUTING.md docs/CONTRIBUTING.md)

# ---- labels / milestones / existing PRs ---------------------------------------------------
labels='[]' milestones='[]' prs='[]'
if [ "$auth_ok" = true ] && [ -n "$base_repo" ]; then
  labels=$(json_or "$(ghc label list -R "$base_repo" --limit 300 --json name | jq -c '[.[].name]' 2>/dev/null)" '[]')
  milestones=$(json_or "$(ghc api "repos/$base_repo/milestones?state=open&per_page=100" | jq -c '[.[]|{number,title,due_on}]' 2>/dev/null)" '[]')
  if [ -n "$issue_num" ]; then
    prs=$(ghc pr list -R "$base_repo" --state all --limit 50 --search "$issue_num" \
            --json number,title,body,headRefName,baseRefName,state,isDraft,isCrossRepository,url,labels \
          | jq -c --arg n "$issue_num" '[.[] | select(((.title + "\n" + (.body // "")) | test("(#|/issues/)" + $n + "\\b")))
                                         | del(.body) | .labels = [.labels[].name]]' 2>/dev/null)
    prs=$(json_or "$prs" '[]')
  fi
fi

# ---- CI: GitHub Actions ------------------------------------------------------------------
wf_files=()
while IFS= read -r f; do wf_files+=("$f"); done < <(find "$root/.github/workflows" -maxdepth 1 -type f \( -name '*.yml' -o -name '*.yaml' \) 2>/dev/null | sort)
CHECK_RE='pre-commit|ruff|eslint|nx (lint|test|affected)|pytest|manage\.py test|jest|helm lint|bats|shellcheck|mypy|yamllint|kubeconform|trivy|secret[_-]detection|golangci-lint|go test|go vet|cargo (test|clippy)|codeql|gitleaks'
if [ "${#wf_files[@]}" -gt 0 ]; then
  ci_checks=$(grep -ohsE "$CHECK_RE" "${wf_files[@]}" | sort -u | jq -R . | jq -sc .)
else ci_checks='[]'; fi
ci_cost='{"heuristic":"none","pipeline_model":null,"mr_pipeline":false,"per_branch_heavy":false,"per_branch_heavy_jobs":[],"mr_heavy_jobs":[],"sub_branch_excluded":false,"pr_ci_on_ticket_base":false,"sub_branch_push_ci":false,"paths_filters":[],"workflows":[]}'
if [ "${#wf_files[@]}" -gt 0 ]; then
  if python3 -c 'import yaml' 2>/dev/null; then
    ci_cost=$(python3 - "$root" "${candidates[0]:-}" "${wf_files[@]}" <<'PY'
import sys, re, os, json, yaml

class Loader(yaml.SafeLoader): pass
Loader.add_multi_constructor('!', lambda l, s, n: None)

root, ticket = sys.argv[1], (sys.argv[2] or "zz-ticket")
ticket = re.sub(r"-sub-\d+.*$", "", ticket)
sub = ticket + "-sub-01-part"
files = sys.argv[3:]

HEAVY_RUN = re.compile(r"kubectl\s+(apply|set\s+image|rollout|annotate|create)|helm\s+(install|upgrade)"
                       r"|docker(\s+buildx)?\s+(build|push)|docker-compose\s+up|npx\s+nx\s+build|\bnx\s+build"
                       r"|npm\s+run\s+build|\bng\s+build|mvn\s+(package|deploy)|gradle\s+build"
                       r"|terraform\s+apply|pulumi\s+up|\bkind\s+create\s+cluster|goreleaser")
HEAVY_USES = re.compile(r"^(docker/build-push-action|docker/bake-action|aws-actions/amazon-ecs-deploy|aws-actions/amazon-eks"
                        r"|google-github-actions/(deploy-|get-gke-credentials)|azure/(webapps-deploy|k8s-deploy|aks-set-context|functions-action)"
                        r"|pulumi/actions|hashicorp/tfc-|helm/kind-action|helm/chart-releaser-action|actions/deploy-pages"
                        r"|peaceiris/actions-gh-pages|cloudflare/wrangler-action|goreleaser/goreleaser-action|softprops/action-gh-release)", re.I)
PINNED_IF = re.compile(r"refs/tags/|startsWith\(\s*github\.ref\s*,\s*'refs/tags|github\.ref\s*==\s*'refs/heads/"
                       r"|github\.ref_name\s*==\s*'|github\.event_name\s*==\s*'(release|schedule|workflow_dispatch|repository_dispatch)'"
                       r"|github\.repository\s*==\s*'", re.I)
PUSH_ONLY_IF = re.compile(r"github\.event_name\s*==\s*'push'", re.I)
PR_ONLY_IF = re.compile(r"github\.event_name\s*==\s*'pull_request(_target)?'", re.I)

def load(f):
    try:
        d = yaml.load(open(f), Loader=Loader)
        return d if isinstance(d, dict) else None
    except Exception:
        return None

def events(d):
    on = d.get("on", d.get(True))          # PyYAML (YAML 1.1) parses a bare `on:` key as True
    if on is None: return {}
    if isinstance(on, str): return {on: None}
    if isinstance(on, list): return {str(e): None for e in on}
    if isinstance(on, dict): return {str(k): v for k, v in on.items()}
    return {}

def glob_re(p):
    out, i = "", 0
    while i < len(p):
        if p.startswith("**", i): out += ".*"; i += 2; continue
        c = p[i]
        if c == "*": out += "[^/]*"
        elif c == "?": out += "."
        elif c == "+": out += "+"
        elif c == "[":
            j = p.find("]", i)
            if j > i: out += p[i:j + 1]; i = j + 1; continue
            out += re.escape(c)
        else: out += re.escape(c)
        i += 1
    return re.compile("^" + out + "$")

def listify(x):
    if x is None: return None
    return [str(i) for i in (x if isinstance(x, list) else [x])]

def branch_filter_ok(cfg, b):
    """GitHub branches / branches-ignore semantics (incl. ordered `!` negation)."""
    if not isinstance(cfg, dict): return True
    inc, ign = listify(cfg.get("branches")), listify(cfg.get("branches-ignore"))
    if inc is None and ign is None:
        return True
    if inc is not None:
        ok = False
        for p in inc:
            if p.startswith("!"):
                if glob_re(p[1:]).match(b): ok = False
            elif glob_re(p).match(b): ok = True
        return ok
    return not any(glob_re(p).match(b) for p in ign)

def push_runs_for_branch(cfg, b):
    if not isinstance(cfg, dict): return True
    has_b = "branches" in cfg or "branches-ignore" in cfg
    has_t = "tags" in cfg or "tags-ignore" in cfg
    if has_t and not has_b: return False    # tag-only filter: branch pushes do not trigger
    return branch_filter_ok(cfg, b)

def flat(x):
    if x is None: return ""
    if isinstance(x, str): return x
    if isinstance(x, (list, tuple)): return "\n".join(flat(i) for i in x)
    if isinstance(x, dict): return "\n".join(flat(v) for v in x.values())
    return str(x)

def minutes(t):
    try: return int(t)
    except Exception: return 0

def heavy(job, depth=0):
    if not isinstance(job, dict): return None
    uses = job.get("uses")
    if isinstance(uses, str):
        if uses.startswith("./") and depth < 2:
            sub_d = load(os.path.join(root, uses.split("@")[0][2:]))
            for jn, j in ((sub_d or {}).get("jobs") or {}).items():
                w = heavy(j, depth + 1)
                if w: return f"reusable {uses}: {jn}: {w}"
        return None
    if job.get("environment"): return "has environment (deploy)"
    if minutes(job.get("timeout-minutes")) >= 60: return f"timeout-minutes {job.get('timeout-minutes')}"
    for st in job.get("steps") or []:
        if not isinstance(st, dict): continue
        u = st.get("uses")
        if isinstance(u, str) and HEAVY_USES.search(u): return f"uses: {u.split('@')[0]}"
        m = HEAVY_RUN.search(flat(st.get("run")))
        if m: return f"run: {m.group(0)}"
    return None

workflows, per_branch, mr_heavy, paths = [], [], [], []
pr_ci, push_ci, sub_excl, any_pr, any_push = False, False, False, False, False
for f in files:
    d = load(f)
    rel = os.path.relpath(f, root)
    if d is None:
        workflows.append({"file": rel, "error": "unparseable"}); continue
    ev = events(d)
    workflows.append({"file": rel, "name": d.get("name"), "events": sorted(ev)})
    for e, cfg in ev.items():
        if isinstance(cfg, dict) and ("paths" in cfg or "paths-ignore" in cfg):
            paths.append({"workflow": rel, "event": e, "paths": listify(cfg.get("paths")), "paths_ignore": listify(cfg.get("paths-ignore"))})
        if isinstance(cfg, dict):
            for p in (listify(cfg.get("branches-ignore")) or []) + [x for x in (listify(cfg.get("branches")) or []) if x.startswith("!")]:
                if "sub" in p: sub_excl = True
    push_cfg = ev.get("push", False)
    on_push_sub = "push" in ev and push_runs_for_branch(push_cfg, sub)
    pr_events = [e for e in ("pull_request", "pull_request_target") if e in ev]
    on_pr_ticket = any(branch_filter_ok(ev[e], ticket) for e in pr_events)
    any_pr |= bool(pr_events); any_push |= "push" in ev
    pr_ci |= on_pr_ticket; push_ci |= on_push_sub
    for jn, job in (d.get("jobs") or {}).items():
        if not isinstance(job, dict): continue
        cond = flat(job.get("if"))
        if PINNED_IF.search(cond): continue
        why = heavy(job)
        if not why: continue
        ent = {"name": f"{rel}:{jn}", "why": why, "workflow": rel}
        if on_push_sub and not PR_ONLY_IF.search(cond): per_branch.append(ent)
        if on_pr_ticket and not PUSH_ONLY_IF.search(cond): mr_heavy.append(ent)

model = "pull_request" if any_pr else ("branch" if any_push else None)
print(json.dumps({"heuristic": "yaml", "pipeline_model": model, "mr_pipeline": any_pr,
                  "per_branch_heavy": bool(per_branch), "per_branch_heavy_jobs": per_branch,
                  "mr_heavy_jobs": mr_heavy, "sub_branch_excluded": sub_excl,
                  "pr_ci_on_ticket_base": pr_ci, "sub_branch_push_ci": push_ci,
                  "sample_branches": {"ticket_base": ticket, "sub": sub},
                  "paths_filters": paths, "workflows": workflows}))
PY
    ) || ci_cost='{"heuristic":"yaml-failed","pipeline_model":null,"mr_pipeline":null,"per_branch_heavy":false,"per_branch_heavy_jobs":[],"mr_heavy_jobs":[],"sub_branch_excluded":false,"pr_ci_on_ticket_base":null,"sub_branch_push_ci":null,"paths_filters":[],"workflows":[]}'
  else
    mrp=false; grep -qsE '^\s*pull_request(_target)?\s*:|^\s*on:.*pull_request|^\s*-\s*pull_request\s*$' "${wf_files[@]}" && mrp=true
    ci_cost=$(jq -cn --argjson mrp "$mrp" '{heuristic:"grep",pipeline_model:(if $mrp then "pull_request" else "branch" end),mr_pipeline:$mrp,
      per_branch_heavy:null,per_branch_heavy_jobs:[],mr_heavy_jobs:[],sub_branch_excluded:false,pr_ci_on_ticket_base:null,sub_branch_push_ci:null,paths_filters:[],workflows:[]}')
  fi
fi
ci_cost=$(json_or "$ci_cost" '{"heuristic":"failed"}')

warn_json=$(printf '%s\n' "${warnings[@]+"${warnings[@]}"}" | jq -R 'select(length>0)' | jq -sc .)
jq -n --arg root "$root" --arg host "$host" --arg def "$def" --arg tmpl "$tmpl" --arg skill "$repo_skill" \
      --arg me "$me" --arg plan "$plan" --arg origin "$origin_repo" --arg base "$base_repo" --arg perm "$perm" \
      --arg codeowners "$codeowners" --arg contributing "$contributing" \
      --arg iref "$issue_ref" --arg irepo "$issue_repo" --arg inum "$issue_num" \
      --argjson gh "$gh_installed" --argjson auth "$auth_ok" --argjson repo "$repo" --argjson prot "$prot_json" \
      --argjson canlabel "$can_label" --argjson fork "$fork_flow" --argjson draft "$draft" \
      --argjson prmulti "$pr_multi" --argjson itmpl "$issue_tmpls" --argjson labels "$labels" \
      --argjson ms "$milestones" --argjson prs "$prs" --argjson checks "$ci_checks" --argjson cost "$ci_cost" \
      --argjson precommit "$precommit" --argjson dirty "$dirty" --argjson warn "$warn_json" '
def nn: if . == "" then null else . end;
{provider:"github", repo_root:$root, remote_host:$host, default_branch:($def|nn), dirty_files:$dirty,
 gh_installed:$gh, auth_ok:$auth, me:($me|nn), plan:($plan|nn),
 origin_repo:($origin|nn), base_repo:($base|nn),
 project:{path:($base|nn), my_access:($perm|nn),
          is_private:$repo.isPrivate, is_fork:$repo.isFork,
          parent:(if $repo.parent then "\($repo.parent.owner.login)/\($repo.parent.name)" else null end),
          is_archived:$repo.isArchived, has_issues:$repo.hasIssuesEnabled,
          delete_branch_on_merge:$repo.deleteBranchOnMerge, squash_merge_allowed:$repo.squashMergeAllowed,
          merge_commit_allowed:$repo.mergeCommitAllowed, rebase_merge_allowed:$repo.rebaseMergeAllowed,
          viewer_can_administer:$repo.viewerCanAdminister, visibility:$repo.visibility},
 repo:$repo,
 draft_prs_available:$draft, can_label:$canlabel, fork_flow:$fork,
 protected_branches:$prot,
 mr_template:($tmpl|nn), pr_templates:$prmulti, issue_templates:$itmpl,
 codeowners:($codeowners|nn), contributing:($contributing|nn),
 labels:$labels,
 agent_labels:{"agent-worked":($labels|index("agent-worked") != null), "agent-created":($labels|index("agent-created") != null),
               "agent-drafted":($labels|index("agent-drafted") != null), "agent-wip":($labels|index("agent-wip") != null)},
 milestones:$ms,
 issue:(if $inum == "" then null else {ref:$iref, repo:(($irepo|nn) // ($base|nn)), number:($inum|tonumber)} end),
 existing_prs:$prs, stack_detected:([$prs[].headRefName | select(test("-sub-"))] | length > 0),
 ci:({checks:$checks, precommit:$precommit} + $cost),
 repo_skill:($skill|nn),
 warnings:$warn}'
