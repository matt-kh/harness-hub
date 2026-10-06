#!/usr/bin/env bash
# work-ticket GitLab preflight: READ-ONLY repo facts as one JSON object. Never writes.
# Usage: gitlab-preflight.sh [CANDIDATE_BRANCH ...]   (candidates are tested against protected-branch rules)
# Normally reached through preflight.sh (provider dispatcher). Provider-neutral facts
# (root, host, default branch, dirty, precommit, repo_skill) come from lib/repo-facts.sh.
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
rf_load                                   # root host def dirty precommit repo_skill repo_decl repo_owns
api() { (cd "$root" && hn_timeout 20 glab api "$@" 2>/dev/null); }
proj=$(api "projects/:id") || proj='{}'
[ -n "$proj" ] && jq -e . <<<"$proj" >/dev/null 2>&1 || proj='{}'
[ -n "$def" ] || def=$(jq -r '.default_branch // empty' <<<"$proj")

# ---- GitLab version / stacked-MR UI (GA in 19.1) ---------------------------------
gl_ver=$(api version | jq -r '.version // empty' 2>/dev/null)
stack_ui=null
[ -n "$gl_ver" ] && stack_ui=$(awk -v v="$gl_ver" 'BEGIN{split(v,a,"."); print (a[1]+0>19||(a[1]+0==19&&a[2]+0>=1))?"true":"false"}')

# ---- protected branches (wildcards would stop Developers merging into ticket/sub branches)
prot=$(api "projects/:id/protected_branches"); jq -e 'type=="array"' <<<"$prot" >/dev/null 2>&1 || prot='[]'
prot_json=$(jq -c --args '
  {rules:[.[]|{name, merge:[.merge_access_levels[]?.access_level_description], push:[.push_access_levels[]?.access_level_description]}],
   wildcards:[.[].name|select(test("[*]"))],
   matches:([$ARGS.positional[] as $b | {key:$b, value:(any(.[].name; . as $p | ($b|test("^"+($p|gsub("[.]";"\\.")|gsub("[*]";".*"))+"$"))))}] | from_entries),
   sub_pattern_matches:(any(.[].name; test("^[*]$|-sub-|^[*]-")))}' "$@" <<<"$prot")

# ---- CI files -----------------------------------------------------------------------
ci_files=()
[ -f "$root/.gitlab-ci.yml" ] && ci_files+=("$root/.gitlab-ci.yml")
if [ -f "$root/.gitlab-ci.yml" ]; then
  while read -r inc; do
    inc="${inc#/}"; [ -n "$inc" ] && [ -f "$root/$inc" ] && ci_files+=("$root/$inc")
  done < <(grep -oE "local:[[:space:]]*[\"']?[^\"' ]+" "$root/.gitlab-ci.yml" | sed -E "s/local:[[:space:]]*[\"']?//")
fi
mr_pipeline=false
[ "${#ci_files[@]}" -gt 0 ] && grep -qsE 'merge_request_event|^\s*-\s*merge_requests\s*$' "${ci_files[@]}" && mr_pipeline=true
if [ "${#ci_files[@]}" -gt 0 ]; then
  ci_checks=$(grep -ohsE 'pre-commit|ruff|eslint|nx (lint|test|affected)|pytest|manage\.py test|jest|helm lint|bats|shellcheck|mypy|yamllint|kubeconform|trivy|secret[_-]detection' "${ci_files[@]}" | sort -u | jq -R . | jq -sc .)
else
  ci_checks='[]'
fi

# ---- CI cost heuristic: which heavy jobs run per branch push / per MR ------------------
# Structured parse with PyYAML when available; grep fallback otherwise.
ci_cost='{"heuristic":"none","pipeline_model":null,"per_branch_heavy":false,"per_branch_heavy_jobs":[],"mr_heavy_jobs":[],"sub_branch_excluded":false}'
if [ "${#ci_files[@]}" -gt 0 ]; then
  if python3 -c 'import yaml' 2>/dev/null; then
    ci_cost=$(python3 - "${ci_files[@]}" <<'PY'
import sys, re, json, yaml

class Loader(yaml.SafeLoader): pass
Loader.add_multi_constructor('!', lambda l, s, n: None)   # ignore !reference and friends

RESERVED = {"stages","variables","include","workflow","default","image","services","cache",
            "before_script","after_script","pages"}
HEAVY_RE = re.compile(r"kubectl\s+(apply|set\s+image|rollout|annotate|create)|helm\s+(install|upgrade)"
                      r"|docker(\s+buildx)?\s+(build|push)|docker-compose\s+up|npx\s+nx\s+build|\bnx\s+build"
                      r"|npm\s+run\s+build|\bng\s+build|mvn\s+(package|deploy)|gradle\s+build")
PIN_RE = re.compile(r'CI_DEFAULT_BRANCH|CI_COMMIT_TAG|CI_COMMIT_(BRANCH|REF_NAME)\s*(==|=~)'
                    r'|CI_PIPELINE_SOURCE\s*==\s*"(schedule|web|trigger|pipeline|api)"|\$[A-Z_]+\s*==\s*"')
MR_RE = re.compile(r"merge_request_event|merge_requests")

docs = {}
for f in sys.argv[1:]:
    try:
        d = yaml.load(open(f), Loader=Loader) or {}
    except Exception:
        continue
    if isinstance(d, dict):
        docs.update(d)

def flat(x):
    if x is None: return ""
    if isinstance(x, str): return x
    if isinstance(x, (list, tuple)): return "\n".join(flat(i) for i in x)
    if isinstance(x, dict): return "\n".join(flat(v) for v in x.values())
    return str(x)

def resolve(name, seen=None):
    seen = seen or set()
    job = docs.get(name)
    if not isinstance(job, dict) or name in seen: return {}
    seen.add(name)
    base = {}
    ext = job.get("extends")
    for parent in ([ext] if isinstance(ext, str) else (ext or [])):
        base.update(resolve(parent, seen))
    base.update(job)
    return base

def minutes(t):
    if not t: return 0
    m = re.findall(r"(\d+)\s*(h|hour|hours|m|min|minute|minutes)", str(t))
    return sum(int(n) * (60 if u.startswith("h") else 1) for n, u in m)

def heavy(job):
    if job.get("when") == "manual": return None
    script = flat(job.get("script")) + "\n" + flat(job.get("before_script"))
    m = HEAVY_RE.search(script)
    if m: return f"script: {m.group(0)}"
    if job.get("environment"): return "has environment (deploy)"
    if minutes(job.get("timeout")) >= 60: return f"timeout {job.get('timeout')}"
    return None

def refs_of(only):
    if only is None: return None
    if isinstance(only, list): return [str(x) for x in only]
    if isinstance(only, dict): return [str(x) for x in (only.get("refs") or [])]
    return []

def rules_text(job):
    return "\n".join(flat(r.get("if")) for r in (job.get("rules") or []) if isinstance(r, dict))

def runs_per_branch(job):
    only, exc, rules = job.get("only"), job.get("except"), job.get("rules")
    if rules:
        for r in rules:
            if not isinstance(r, dict) or r.get("when") == "never": continue
            cond = flat(r.get("if"))
            if not cond: return True
            if not PIN_RE.search(cond) or ("!=" in cond and not re.search(r"==|=~", cond)): return True
        return False
    if only is None:
        er = refs_of(exc) or []
        return "branches" not in er
    refs = refs_of(only)
    if isinstance(only, dict) and not only.get("refs"):
        return False                           # only: variables/changes
    er = refs_of(exc) or []
    return any(r == "branches" or r.startswith("/") for r in refs) and "branches" not in er

def runs_in_mr(job):
    only, rules = job.get("only"), job.get("rules")
    if rules:
        for r in rules:
            if not isinstance(r, dict) or r.get("when") == "never": continue
            cond = flat(r.get("if"))
            if not cond or MR_RE.search(cond) or not PIN_RE.search(cond): return True
        return False
    if only is None: return True
    return "merge_requests" in (refs_of(only) or [])

model = "merge_request" if MR_RE.search(flat(docs.get("workflow")) + flat({k: v for k, v in docs.items() if k not in RESERVED})) else "branch"
per_branch, mr_heavy, sub_excl = [], [], False
for name in docs:
    if name in RESERVED or name.startswith("."): continue
    job = resolve(name)
    if not job or not (job.get("script") or job.get("trigger") or job.get("extends")): continue
    txt = flat(job.get("except")) + rules_text(job)
    if "-sub-" in txt: sub_excl = True
    why = heavy(job)
    if not why: continue
    if model == "branch" and runs_per_branch(job):
        per_branch.append({"name": name, "why": why})
    if model == "merge_request" and runs_in_mr(job) and "CI_MERGE_REQUEST_TARGET_BRANCH_NAME" not in rules_text(job):
        mr_heavy.append({"name": name, "why": why})
print(json.dumps({"heuristic": "yaml", "pipeline_model": model,
                  "per_branch_heavy": bool(per_branch), "per_branch_heavy_jobs": per_branch,
                  "mr_heavy_jobs": mr_heavy, "sub_branch_excluded": sub_excl}))
PY
    ) || ci_cost='{"heuristic":"yaml-failed","pipeline_model":null,"per_branch_heavy":false,"per_branch_heavy_jobs":[],"mr_heavy_jobs":[],"sub_branch_excluded":false}'
  else
    pbh=false
    if [ "$mr_pipeline" = false ] && grep -qsE '^\s*only:\s*$|^\s*-\s*branches\s*$' "${ci_files[@]}"; then pbh=true; fi
    sbe=false; grep -qs -- '-sub-' "${ci_files[@]}" && sbe=true
    ci_cost=$(jq -cn --argjson pbh "$pbh" --argjson sbe "$sbe" --arg model "$([ "$mr_pipeline" = true ] && echo merge_request || echo branch)" \
      '{heuristic:"grep",pipeline_model:$model,per_branch_heavy:$pbh,per_branch_heavy_jobs:[],mr_heavy_jobs:[],sub_branch_excluded:$sbe}')
  fi
fi

tmpl=$(ls "$root"/.gitlab/merge_request_templates/{default,Default}.md 2>/dev/null | head -1)
me=$(api user | jq -r '.id // empty' 2>/dev/null)
access="unknown"
if [ -n "$me" ] && [ "$(jq -r '.id // empty' <<<"$proj")" != "" ]; then
  access=$(api "projects/:id/members/all/$me" | jq -r '.access_level // "unknown"' 2>/dev/null); [ -n "$access" ] || access="unknown"
fi

jq -n --arg root "$root" --arg host "$host" --arg def "$def" --arg tmpl "$tmpl" --arg skill "$repo_skill" \
      --arg rdecl "$repo_decl" --argjson rowns "$repo_owns" \
      --arg access "$access" --arg glver "$gl_ver" --argjson stackui "$stack_ui" --argjson prot "$prot_json" \
      --argjson proj "$proj" --argjson mr "$mr_pipeline" --argjson checks "$ci_checks" --argjson cost "$ci_cost" \
      --argjson precommit "$precommit" --argjson dirty "$dirty" '
{provider:"gitlab", repo_root:$root, remote_host:$host, default_branch:$def, dirty_files:$dirty,
 gitlab:{version:(if $glver=="" then null else $glver end), stack_ui_available:$stackui},
 project:{id:$proj.id, path:$proj.path_with_namespace, squash_option:$proj.squash_option, merge_method:$proj.merge_method,
          merge_needs_pipeline:$proj.only_allow_merge_if_pipeline_succeeds,
          remove_source_branch_after_merge:$proj.remove_source_branch_after_merge, my_access:$access},
 protected_branches:$prot,
 mr_template:(if $tmpl=="" then null else $tmpl end),
 ci:({mr_pipeline:$mr, checks:$checks, precommit:$precommit} + $cost),
 repo_skill:(if $skill=="" then null else $skill end),
 repo_declaration:(if $rdecl=="" then null else $rdecl end), repo_owns:$rowns}'
