#!/usr/bin/env python3
"""Read-only Kubernetes operator client — stdlib only.

Canonical invocation: `k8s <cmd>` (symlinked into ~/.local/bin, like `jira`/`gdoc`).
Every command shells out to `kubectl --context <CTX> --request-timeout=<T>s ... -o json`
(or `helm --kube-context <CTX> ... -o json`) and does the JSON heavy lifting here, so
raw cluster dumps never land in a model context. Nothing here mutates anything, and the
kubeconfig is never read directly nor switched.

Output is findings-first: JSON when stdout is not a TTY (or --json), Markdown on a TTY
(or --md):
  {"context","prod","generated_at","command",
   "findings":[{"severity","kind","ns","name","message","evidence"}],"data":{...}}
Exit codes: 0 ok, 1 at least one crit/warn finding, 2 access error (unreachable /
unauthorized / forbidden / TLS / timeout).

Every command prints a banner to STDERR first:
  context=dev-cluster server=v1.26.15+rke2r1 ns=shop [PROD]
[PROD] marks a context or namespace matching K8S_PROD_RE — reads stay free there, but
every remediation is a suggestion for the human to run.

Commands (run with no args to print this list):
  contexts [--only A,B] [--probe-timeout 8] [--write]
                        All kubeconfig contexts, probed in parallel: reachable, server
                        version, ready/total nodes, prod flag, first error. --write
                        regenerates the clusters doc (K8S_CLUSTERS_MD). Exit 1 if any
                        unreachable.
  health [--ns NS]      Cluster sweep: node conditions, non-Running pods, restarts >= 5,
                        Pending PVCs, Warning events (last 60 min), Failed Jobs, ArgoCD
                        apps, Helm releases, PDBs blocking eviction, apiserver and
                        cert-manager certificate expiry.
  pod NS POD [--tail N] Triage bundle for one pod: phase, node, QoS, container states and
                        lastState, restarts, probes, Warning events, and the last N log
                        lines per container (plus --previous when it has restarted),
                        redacted.
  workload NS KIND/NAME Deployment|StatefulSet|DaemonSet|Job|CronJob|ReplicaSet|RayCluster
                        (short names ok): owner chain, rollout status, selected pods,
                        Warning events, and the worst pod's last log lines (redacted).
  events [--ns NS] [--warning] [--since 60m]
                        Recent events, newest first, grouped by reason with counts.
  capacity [--ns NS]    Per-node allocatable vs the sum of pod requests/limits (cpu,
                        memory, nvidia.com/gpu, ephemeral-storage, pods), live usage when
                        the metrics API allows it, and ResourceQuotas. Findings above 90%.
  argocd                Applications / ApplicationSets / AppProjects (plus Kargo Stages,
                        Promotions and Freights when those CRDs exist); maps
                        spec.source.path to <K8S_GITOPS_ROOT>/<path>.
  helm [--ns NS] [--values NAME]
                        Releases with status/chart/appVersion/updated; a non-deployed
                        release also gets its last 3 history rows and status description.
                        --values prints `helm get values -a` REDACTED.
  secret-keys NS NAME | secret-keys NS --all | secret-keys -
                        Secret key names and byte sizes only — values are never printed.
                        `-` reads a Secret or a List of Secrets as JSON from stdin.
  redact                stdin -> stdout filter (JSON or free text). No cluster call.
  promql QUERY [--svc NS/NAME:PORT] [--range 1h] [--step 60s]
                        Query Prometheus through the apiserver proxy (service auto-
                        discovered) and tabulate the result.
  certs                 apiserver certificate expiry, pending CSRs, cert-manager
                        Certificates. Findings under 30 d (crit under 7 d or expired).
  audit [--ns NS]       Pod-spec posture: privileged / hostPath / hostNetwork / hostPID,
                        missing limits, requests and probes, :latest images, runAsRoot,
                        allowPrivilegeEscalation, default ServiceAccount automount, and
                        namespaces without a Pod Security Admission enforce label.
                        Deduplicated per owning workload.

Common flags: --context CTX (default: the kubeconfig current-context; never switched),
--json/--md, --timeout S, --max-items N (50), --max-bytes N (200000), --tail N (50).

Deliberately NOT implemented — do not work around these with raw kubectl; the guard hook
asks or denies, so tell the human what to run instead: exec / attach / cp / debug /
port-forward / proxy; any mutation (apply, delete, patch, scale, rollout restart, helm
install/upgrade/uninstall/rollback); the argocd CLI and its login; kubeconfig switching,
editing or reading (including `config view --raw`); printing Secret values;
`kubectl create token`; `logs -f`.

Env (each falls back to the harness config key in brackets, read from build/config.json via
HARNESS_CONFIG_JSON / HARNESS_HOME, then to the default):
  KUBECTL, HELM          binary overrides (used by the tests)
  K8S_TIMEOUT            request timeout seconds (default 20)
  K8S_PROD_RE [k8s.prod_re]  default `(^|[-_./:])(prod|production)([-_./:]|$)`, matched
                         case-insensitively against the context name AND the namespace
  K8S_GITOPS_ROOT [k8s.gitops_root]  local GitOps checkout where `argocd` looks up source
                         paths (default: unset -> the local-path check is skipped)
  K8S_GITOPS_REPO_MATCH [k8s.gitops_repo_match]  substring of an Application's repoURL
                         that marks it as that checkout (default: basename of the root)
  K8S_CLUSTERS_MD [k8s.clusters_doc]  file `contexts --write` regenerates (default
                         ~/.local/state/harness/k8s/clusters.md; relative = under HARNESS_HOME)
"""
import argparse
import base64
import concurrent.futures
import datetime
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import tempfile
import urllib.parse

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


def _hpath(p):
    """Expand ~; a relative path is relative to HARNESS_HOME (config paths are hub-relative)."""
    p = os.path.expanduser(p or "")
    if p and not os.path.isabs(p):
        p = os.path.join(os.environ.get("HARNESS_HOME") or os.path.expanduser("~/harness-hub"), p)
    return p

KUBECTL = os.environ.get("KUBECTL", "kubectl")
HELM = os.environ.get("HELM", "helm")
TIMEOUT = int(os.environ.get("K8S_TIMEOUT", "20"))
PROD_RE = re.compile(
    os.environ.get("K8S_PROD_RE") or cfg("k8s.prod_re") or r"(^|[-_./:])(prod|production)([-_./:]|$)",
    re.I)
HERE = os.path.dirname(os.path.realpath(__file__))
CLUSTERS_MD = _hpath(os.environ.get("K8S_CLUSTERS_MD") or cfg("k8s.clusters_doc")
                     or "~/.local/state/harness/k8s/clusters.md")
GITOPS_ROOT = _hpath(os.environ.get("K8S_GITOPS_ROOT") or cfg("k8s.gitops_root") or "")
GITOPS_REPO_MATCH = (os.environ.get("K8S_GITOPS_REPO_MATCH") or cfg("k8s.gitops_repo_match")
                     or os.path.basename(GITOPS_ROOT.rstrip("/")))


def die(msg, code=1):
    print(msg, file=sys.stderr)
    sys.exit(code)


class AccessError(Exception):
    """Cluster unreachable / unauthorized / forbidden / TLS / timeout -> exit 2."""


def is_prod(*parts):
    return any(PROD_RE.search(p) for p in parts if p)


# --------------------------------------------------------------------------- redaction
KEY_BODY = (r"(pass(word|wd)?|secret|token|api[-_]?key|private[-_]?key|access[-_]?key"
            r"|client[-_]?secret|credential|auth|cert(ificate)?|jwt|dsn"
            r"|connection[-_]?string)")
SECRET_KEY_RE = re.compile(r"(?i)" + KEY_BODY)
REDACTED = "***REDACTED***"
_TEXT_KEY_RE = re.compile(r"^(\s*[\w.-]*" + KEY_BODY + r"[\w.-]*\s*[:=]\s*)(.+)$", re.I)
# the anchored rule above only catches `key: value` lines; logs usually carry a timestamp
# and a level first, so the same key=value shape is redacted anywhere in the line too.
_TEXT_KEY_INLINE_RE = re.compile(
    r"(?P<key>[\w.-]*" + KEY_BODY + r"[\w.-]*)(?P<sep>\s*[:=]\s*)"
    r"(?P<val>\"[^\"]*\"|'[^']*'|\S+)", re.I)
_AKIA_RE = re.compile(r"AKIA[0-9A-Z]{16}")
_JWT_RE = re.compile(r"eyJ[\w-]+\.[\w-]+\.[\w-]+")
_PEM_RE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
                     re.S)
_URLCRED_RE = re.compile(r"://[^/:@\s]+:[^@\s]+@")


def _secret_sizes(obj):
    """Replace a Secret's data/stringData values with '<N bytes>' (never the value)."""
    out = dict(obj)
    for field in ("data", "stringData"):
        blob = obj.get(field)
        if not isinstance(blob, dict):
            continue
        sized = {}
        for k, v in blob.items():
            if field == "data":
                try:
                    n = len(base64.b64decode(v or "", validate=False))
                except Exception:
                    n = len(v or "")
            else:
                n = len(v or "")
            sized[k] = "<%d bytes>" % n
        out[field] = sized
    return out


def redact_obj(obj):
    """Walk a JSON structure: secret-ish keys -> ***REDACTED***, Secret data -> sizes."""
    if isinstance(obj, dict):
        if obj.get("kind") == "Secret":
            obj = _secret_sizes(obj)
        out = {}
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                out[k] = redact_obj(v)
            elif SECRET_KEY_RE.search(str(k)) and v is not None and not (
                    isinstance(v, str) and v.startswith("<") and v.endswith("bytes>")):
                out[k] = REDACTED
            else:
                out[k] = v
        return out
    if isinstance(obj, list):
        return [redact_obj(x) for x in obj]
    return obj


def redact_text(text):
    """Redact free text / logs: key=value lines, AWS keys, JWTs, PEM blocks, URL creds."""
    if not text:
        return text
    text = _PEM_RE.sub(REDACTED, text)
    lines = []
    for line in text.split("\n"):
        m = _TEXT_KEY_RE.match(line)
        if m:
            line = m.group(1) + REDACTED
        else:
            line = _TEXT_KEY_INLINE_RE.sub(
                lambda x: x.group("key") + x.group("sep") + REDACTED, line)
        line = _AKIA_RE.sub(REDACTED, line)
        line = _JWT_RE.sub(REDACTED, line)
        line = _URLCRED_RE.sub("://***:***@", line)
        lines.append(line)
    return "\n".join(lines)


# ------------------------------------------------------------------------- subprocesses
ACCESS_RE = re.compile(
    r"Unable to connect|i/o timeout|no such host|connection refused|network is unreachable"
    r"|context .*(was not found|does not exist)|Unauthorized|forbidden|certificate|x509"
    r"|TLS handshake|executable file not found|couldn't get current server API group list"
    r"|dial tcp|deadline exceeded|timed out|the server has asked for the client to provide"
    r"|error loading config file|You must be logged in",
    re.I)


def clean_err(err):
    """Drop kubectl's version-skew WARNING lines (they would poison stderr parsing)."""
    return "\n".join(l for l in (err or "").splitlines()
                     if l.strip() and not l.startswith("WARNING:"))


def first_line(err):
    lines = clean_err(err).splitlines()
    return lines[0].strip() if lines else ""


def _run(cmd, timeout):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 10)
    except subprocess.TimeoutExpired:
        raise AccessError("timed out after %ds: %s" % (timeout + 10, " ".join(cmd[:4])))
    except FileNotFoundError:
        raise AccessError("executable file not found: %s" % cmd[0])
    except OSError as e:
        raise AccessError("%s: %s" % (cmd[0], e))
    return p.returncode, p.stdout, clean_err(p.stderr)


def _wants_json(args):
    if any(a == "--raw" or a.startswith("--raw=") for a in args):
        return False
    if args and args[0] in ("logs",):
        return False
    return not any(a in ("-o", "--output") or a.startswith("-o") or a.startswith("--output=")
                   for a in args)


def run_kubectl(ctx, args, timeout=None, json_out=True, soft=False):
    """kubectl --context CTX --request-timeout=Ts <args> [-o json]. Never merges stderr."""
    t = timeout or TIMEOUT
    args = [str(a) for a in args]
    cmd = [KUBECTL, "--context", ctx, "--request-timeout=%ds" % t] + args
    if json_out and _wants_json(args):
        cmd += ["-o", "json"]
    rc, out, err = _run(cmd, t)
    if soft:
        return rc, out, err
    if rc != 0:
        line = first_line(err) or ("kubectl exited %d" % rc)
        if ACCESS_RE.search(err):
            raise AccessError(line)
        die(line, 1)
    return out


def kjson(ctx, args, timeout=None):
    out = run_kubectl(ctx, args, timeout=timeout)
    return json.loads(out) if out.strip() else {}


def ktry(ctx, args, timeout=None, json_out=True):
    """Optional read: (parsed|None, first error line|None). Swallows access errors too."""
    try:
        rc, out, err = run_kubectl(ctx, args, timeout=timeout, json_out=json_out, soft=True)
    except AccessError as e:
        return None, str(e)
    if rc != 0:
        return None, first_line(err) or ("kubectl exited %d" % rc)
    if not json_out:
        return out, None
    try:
        return json.loads(out) if out.strip() else {}, None
    except ValueError as e:
        return None, "unparseable JSON: %s" % e


def kubectl_plain(args, timeout=None):
    """kubectl without --context (config view / current-context only)."""
    t = timeout or TIMEOUT
    rc, out, err = _run([KUBECTL] + [str(a) for a in args], t)
    if rc != 0:
        line = first_line(err) or ("kubectl exited %d" % rc)
        raise AccessError(line)
    return out


def run_helm(ctx, args, timeout=None, soft=False):
    t = timeout or TIMEOUT
    cmd = [HELM] + [str(a) for a in args] + ["--kube-context", ctx]
    rc, out, err = _run(cmd, t)
    if soft:
        return rc, out, err
    if rc != 0:
        line = first_line(err) or ("helm exited %d" % rc)
        if ACCESS_RE.search(err):
            raise AccessError(line)
        die(line, 1)
    return out


def htry(ctx, args, timeout=None):
    try:
        rc, out, err = run_helm(ctx, args, timeout=timeout, soft=True)
    except AccessError as e:
        return None, str(e)
    if rc != 0:
        return None, first_line(err) or ("helm exited %d" % rc)
    try:
        return json.loads(out) if out.strip() else [], None
    except ValueError as e:
        return None, "unparseable JSON: %s" % e


def current_context():
    try:
        out = kubectl_plain(["config", "current-context"], timeout=10).strip()
    except AccessError as e:
        die("cannot read the current kubeconfig context (%s) — pass --context CTX" % e, 2)
    if not out:
        die("kubeconfig has no current-context — pass --context CTX", 2)
    return out


def server_version(ctx, timeout=None):
    data, _ = ktry(ctx, ["version"], timeout=timeout)
    if isinstance(data, dict):
        return (data.get("serverVersion") or {}).get("gitVersion") or "?"
    return "?"


def banner(ctx, server, ns=None):
    parts = ["context=%s" % ctx, "server=%s" % (server or "?")]
    if ns:
        parts.append("ns=%s" % ns)
    if is_prod(ctx, ns or ""):
        parts.append("[PROD]")
    print(" ".join(parts), file=sys.stderr)


# --------------------------------------------------------------------------- quantities
_SUFFIX = {"": 1.0, "n": 1e-9, "u": 1e-6, "m": 1e-3, "k": 1e3, "K": 1e3, "M": 1e6,
           "G": 1e9, "T": 1e12, "P": 1e15, "E": 1e18, "Ki": 2.0 ** 10, "Mi": 2.0 ** 20,
           "Gi": 2.0 ** 30, "Ti": 2.0 ** 40, "Pi": 2.0 ** 50, "Ei": 2.0 ** 60}
_QTY_RE = re.compile(r"^\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*([a-zA-Z]*)\s*$")


def parse_quantity(val):
    """Kubernetes quantity -> float in base units (cores for cpu, bytes for memory)."""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    m = _QTY_RE.match(str(val))
    if not m:
        return 0.0
    return float(m.group(1)) * _SUFFIX.get(m.group(2), 1.0)


def cpu_m(val):
    return parse_quantity(val) * 1000.0


def fmt_cpu(millicores):
    return "%dm" % round(millicores)


def fmt_bytes(n):
    n = float(n)
    for unit in ("B", "Ki", "Mi", "Gi", "Ti", "Pi"):
        if abs(n) < 1024.0 or unit == "Pi":
            return ("%.0f%s" % (n, unit)) if unit == "B" else ("%.1f%s" % (n, unit))
        n /= 1024.0
    return "%.1fPi" % n


def parse_duration(s, default_seconds=3600):
    """Nm / Nh / Nd / Ns -> seconds."""
    if not s:
        return default_seconds
    m = re.match(r"^\s*(\d+)\s*([smhd]?)\s*$", str(s))
    if not m:
        die("bad duration %r — use e.g. 30m, 6h, 2d" % s)
    n = int(m.group(1))
    return n * {"s": 1, "m": 60, "h": 3600, "d": 86400, "": 60}[m.group(2)]


def parse_ts(s):
    if not s:
        return None
    try:
        return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=datetime.timezone.utc)
    except ValueError:
        pass
    try:
        return datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def event_time(ev):
    for key in ("lastTimestamp", "eventTime", "firstTimestamp"):
        t = parse_ts(ev.get(key))
        if t:
            return t
    return parse_ts((ev.get("metadata") or {}).get("creationTimestamp"))


# ------------------------------------------------------------------------------- report
SEV_ORDER = {"crit": 0, "warn": 1, "info": 2}


class Report(object):
    def __init__(self, command, ctx, ns=None):
        self.command = command
        self.ctx = ctx
        self.ns = ns
        self.prod = bool(is_prod(ctx, ns or ""))
        self.findings = []
        self.data = {}
        self._seen = set()

    def add(self, severity, kind, ns, name, message, evidence=None, dedupe=False):
        if severity not in SEV_ORDER:
            severity = "info"
        key = (severity, kind, ns, name, message)
        if dedupe:
            if key in self._seen:
                return
            self._seen.add(key)
        self.findings.append({"severity": severity, "kind": kind, "ns": ns or "",
                              "name": name or "", "message": message,
                              "evidence": evidence})

    def section(self, name, items, max_items=None):
        """Store a list section, capped, marking <name>_truncated when it was cut."""
        if max_items and isinstance(items, list) and len(items) > max_items:
            self.data[name] = items[:max_items]
            self.data[name + "_truncated"] = True
            self.data[name + "_total"] = len(items)
        else:
            self.data[name] = items

    def exit_code(self):
        return 1 if any(f["severity"] in ("crit", "warn") for f in self.findings) else 0

    def sorted_findings(self):
        return sorted(self.findings, key=lambda f: (SEV_ORDER[f["severity"]], f["kind"],
                                                    f["ns"], f["name"]))

    def envelope(self):
        return {
            "context": self.ctx,
            "prod": self.prod,
            "generated_at": now_utc().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "command": self.command,
            "findings": self.sorted_findings(),
            "data": self.data,
        }

    def markdown(self):
        out = ["# k8s %s — %s%s" % (self.command, self.ctx, " [PROD]" if self.prod else ""),
               ""]
        fs = self.sorted_findings()
        out.append("## Findings (%d)" % len(fs))
        out.append("")
        if fs:
            out.append("| sev | kind | ns/name | message |")
            out.append("|---|---|---|---|")
            for f in fs:
                ref = "/".join(x for x in (f["ns"], f["name"]) if x) or "-"
                out.append("| %s | %s | %s | %s |" % (f["severity"], f["kind"], ref,
                                                      md_cell(f["message"])))
        else:
            out.append("none")
        out.append("")
        for name, val in self.data.items():
            if name.endswith("_truncated") or name.endswith("_total"):
                continue
            out.append("## %s" % name)
            out.append("")
            out.extend(md_value(val))
            if self.data.get(name + "_truncated"):
                out.append("")
                out.append("_showing %d of %d — rerun with --max-items N or --json_"
                           % (len(val), self.data.get(name + "_total", len(val))))
            out.append("")
        return "\n".join(out)

    def emit(self, fmt, max_bytes):
        if fmt == "json":
            txt = json.dumps(self.envelope(), indent=2, default=str)
        else:
            txt = self.markdown()
        raw = txt.encode("utf-8")
        if max_bytes and len(raw) > max_bytes:
            txt = raw[:max_bytes].decode("utf-8", "ignore")
            txt += "\n\n…[truncated %d bytes — rerun with --json > file]" % (
                len(raw) - max_bytes)
        sys.stdout.write(txt if txt.endswith("\n") else txt + "\n")


def md_cell(v):
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        v = json.dumps(v, default=str)
    return str(v).replace("|", "\\|").replace("\n", " ⏎ ")


def md_value(val, depth=0):
    """Render one data section: list of dicts -> table, dict -> kv table, else literal."""
    if isinstance(val, list):
        if not val:
            return ["_none_"]
        if all(isinstance(x, dict) for x in val):
            cols = []
            for row in val:
                for k in row:
                    if k not in cols:
                        cols.append(k)
            lines = ["| " + " | ".join(cols) + " |",
                     "|" + "|".join("---" for _ in cols) + "|"]
            for row in val:
                lines.append("| " + " | ".join(md_cell(row.get(c)) for c in cols) + " |")
            return lines
        return ["- " + md_cell(x) for x in val]
    if isinstance(val, dict):
        if not val:
            return ["_none_"]
        lines = ["| key | value |", "|---|---|"]
        for k, v in val.items():
            lines.append("| %s | %s |" % (md_cell(k), md_cell(v)))
        return lines
    if isinstance(val, str) and "\n" in val:
        return ["```", val, "```"]
    return [md_cell(val)]


# ------------------------------------------------------------------------ shared lookups
def kubeconfig_view(timeout=None):
    """`kubectl config view -o json` — redacted by kubectl; NEVER --raw, never ~/.kube."""
    try:
        return json.loads(kubectl_plain(["config", "view", "-o", "json"], timeout=timeout))
    except AccessError:
        raise
    except ValueError as e:
        die("cannot parse `kubectl config view -o json`: %s" % e, 2)


def cluster_for_context(cfg, ctx):
    name = None
    for c in cfg.get("contexts") or []:
        if c.get("name") == ctx:
            name = (c.get("context") or {}).get("cluster")
    for c in cfg.get("clusters") or []:
        if c.get("name") == name:
            return c.get("cluster") or {}
    return {}


def crd_present(ctx, name, timeout=None):
    rc, _out, _err = run_kubectl(ctx, ["get", "crd", name], timeout=timeout, soft=True)
    return rc == 0


def items_of(obj):
    if isinstance(obj, dict):
        return obj.get("items") or []
    if isinstance(obj, list):
        return obj
    return []


def owner_of(obj):
    refs = (obj.get("metadata") or {}).get("ownerReferences") or []
    return refs[0] if refs else None


def top_owner(pod):
    """Best-effort workload key for a pod, one hop past a ReplicaSet/Job."""
    ref = owner_of(pod)
    if not ref:
        return "Pod/%s" % (pod.get("metadata") or {}).get("name", "?")
    kind, name = ref.get("kind", "?"), ref.get("name", "?")
    if kind == "ReplicaSet":
        m = re.match(r"^(.*)-[0-9a-f]{5,10}$", name)
        if m:
            return "Deployment/%s" % m.group(1)
    if kind == "Job":
        m = re.match(r"^(.*)-\d{8,}$", name)
        if m:
            return "CronJob/%s" % m.group(1)
    return "%s/%s" % (kind, name)


def pod_restarts(pod):
    return sum((cs.get("restartCount") or 0)
               for cs in (pod.get("status") or {}).get("containerStatuses") or [])


def container_state(cs):
    st = cs.get("state") or {}
    for key in ("waiting", "running", "terminated"):
        if key in st:
            d = st[key] or {}
            bits = [key]
            if d.get("reason"):
                bits.append(d["reason"])
            if d.get("exitCode") is not None:
                bits.append("exit=%s" % d["exitCode"])
            return " ".join(bits)
    return "unknown"


def last_state(cs):
    st = cs.get("lastState") or {}
    term = st.get("terminated") or {}
    if not term:
        return ""
    bits = [term.get("reason") or "terminated"]
    if term.get("exitCode") is not None:
        bits.append("exit=%s" % term["exitCode"])
    if term.get("signal"):
        bits.append("signal=%s" % term["signal"])
    return " ".join(bits)


def pod_row(p):
    md, st = p.get("metadata") or {}, p.get("status") or {}
    return {
        "ns": md.get("namespace", ""),
        "pod": md.get("name", ""),
        "phase": st.get("phase", ""),
        "ready": "%d/%d" % (
            sum(1 for c in st.get("containerStatuses") or [] if c.get("ready")),
            len(st.get("containerStatuses") or [])),
        "restarts": pod_restarts(p),
        "node": (p.get("spec") or {}).get("nodeName", ""),
        "state": "; ".join(
            "%s=%s" % (c.get("name"), container_state(c))
            for c in (st.get("containerStatuses") or []) + (st.get("initContainerStatuses") or [])
            if container_state(c) not in ("running",)) or "ok",
    }


def scope_args(ns):
    return ["-n", ns] if ns else ["-A"]


# ----------------------------------------------------------------------------- contexts
def probe_context(name, probe_timeout):
    res = {"name": name, "reachable": False, "server": "", "nodes_ready": 0,
           "nodes_total": 0, "error": ""}
    rc, out, err = run_kubectl(name, ["version"], timeout=probe_timeout, soft=True)
    if rc != 0:
        res["error"] = first_line(err) or "kubectl exited %d" % rc
        return res
    try:
        res["server"] = (json.loads(out).get("serverVersion") or {}).get("gitVersion") or "?"
    except ValueError:
        res["server"] = "?"
    res["reachable"] = True
    rc, out, err = run_kubectl(name, ["get", "nodes"], timeout=probe_timeout, soft=True)
    if rc != 0:
        res["error"] = first_line(err) or ""
        return res
    try:
        nodes = items_of(json.loads(out))
    except ValueError:
        return res
    res["nodes_total"] = len(nodes)
    res["nodes_ready"] = sum(
        1 for n in nodes
        if any(c.get("type") == "Ready" and c.get("status") == "True"
               for c in (n.get("status") or {}).get("conditions") or []))
    return res


def render_clusters_md(rows):
    today = now_utc().strftime("%Y-%m-%d")
    out = ["<!-- generated %s by k8s contexts --write; do not hand-edit — regenerate "
           "with: k8s contexts --write -->" % today,
           "",
           "# Clusters (kubeconfig contexts)",
           "",
           "| context | prod | reachable | server | nodes | notes |",
           "|---|---|---|---|---|---|"]
    for r in rows:
        nodes = ("%d/%d" % (r["nodes_ready"], r["nodes_total"])) if r["nodes_total"] else "-"
        out.append("| `%s` | %s | %s | %s | %s | %s |" % (
            r["name"], "yes" if r["prod"] else "", "yes" if r["reachable"] else "**no**",
            r["server"] or "-", nodes, md_cell(r["error"]) or ""))
    out += [
        "",
        "The registry directories under `gitops/clusters/<env>/<stage>/<ctx>` are",
        "**ArgoCD cluster names**, not kubeconfig contexts — the two namespaces of names do",
        "not line up (e.g. `team-dev-test` apps run on the `dev-cluster` context). Use",
        "`k8s argocd --context <ctx>` to see what is actually deployed where.",
        "",
    ]
    return "\n".join(out)


def cmd_contexts(a):
    cfg = kubeconfig_view(timeout=a.timeout)
    names = [c.get("name") for c in cfg.get("contexts") or [] if c.get("name")]
    if a.only:
        wanted = [x.strip() for x in a.only.split(",") if x.strip()]
        missing = [w for w in wanted if w not in names]
        if missing:
            die("no such context(s) in the kubeconfig: %s" % ", ".join(missing))
        names = [n for n in names if n in wanted]
    if not names:
        die("kubeconfig has no contexts")
    ctx = a.context or cfg.get("current-context") or names[0]
    clusters = {c.get("name"): (c.get("cluster") or {}) for c in cfg.get("clusters") or []}
    ctx_cluster = {c.get("name"): (c.get("context") or {}).get("cluster")
                   for c in cfg.get("contexts") or []}
    rep = Report("contexts", ctx)
    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(names))) as ex:
        futures = {ex.submit(probe_context, n, a.probe_timeout): n for n in names}
        for fut in concurrent.futures.as_completed(futures):
            n = futures[fut]
            try:
                rows.append(fut.result())
            except Exception as e:  # a probe must never sink the command
                rows.append({"name": n, "reachable": False, "server": "", "nodes_ready": 0,
                             "nodes_total": 0, "error": str(e)})
    by_name = {r["name"]: r for r in rows}
    ordered = []
    for n in names:
        r = by_name.get(n) or {"name": n, "reachable": False, "server": "",
                               "nodes_ready": 0, "nodes_total": 0, "error": "not probed"}
        cl = ctx_cluster.get(n) or ""
        r["cluster"] = cl
        r["prod"] = bool(is_prod(n, cl))
        r["current"] = (n == cfg.get("current-context"))
        ordered.append({"name": r["name"], "cluster": cl, "prod": r["prod"],
                        "reachable": r["reachable"], "server": r["server"],
                        "nodes_ready": r["nodes_ready"], "nodes_total": r["nodes_total"],
                        "error": r["error"]})
        if not r["reachable"]:
            rep.add("warn", "Context", "", n, "unreachable: %s" % (r["error"] or "unknown"))
    banner(ctx, (by_name.get(ctx) or {}).get("server") or "?")
    rep.section("contexts", ordered, a.max_items)
    rep.data["current_context"] = cfg.get("current-context") or ""
    if a.write:
        os.makedirs(os.path.dirname(CLUSTERS_MD), exist_ok=True)
        with open(CLUSTERS_MD, "w") as f:
            f.write(render_clusters_md(ordered))
        rep.data["written"] = CLUSTERS_MD
        print("wrote %s" % CLUSTERS_MD, file=sys.stderr)
    return rep


# ------------------------------------------------------------------------------- health
def apiserver_cert(ctx, cfg):
    """(notAfter datetime, note) for the apiserver certificate, or (None, reason)."""
    cl = cluster_for_context(cfg, ctx)
    if cl.get("insecure-skip-tls-verify"):
        return None, "insecure-skip-tls-verify — certificate not checked"
    url = cl.get("server") or ""
    if not url:
        return None, "no server URL in the kubeconfig for this context"
    u = urllib.parse.urlparse(url)
    host, port = u.hostname, u.port or 443
    if not host:
        return None, "unparseable server URL"
    try:
        pem = ssl.get_server_certificate((host, port), timeout=10)
    except TypeError:  # very old pythons have no timeout kwarg
        try:
            socket.setdefaulttimeout(10)
            pem = ssl.get_server_certificate((host, port))
        except Exception as e:
            return None, "TLS probe failed: %s" % e
    except Exception as e:
        return None, "TLS probe failed: %s" % e
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(suffix=".pem")
        with os.fdopen(fd, "w") as f:
            f.write(pem)
        decoded = ssl._ssl._test_decode_cert(tmp)  # stdlib-private but present everywhere
    except Exception as e:
        return None, "certificate parse failed: %s" % e
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)
    not_after = decoded.get("notAfter")
    try:
        dt = datetime.datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(
            tzinfo=datetime.timezone.utc)
    except Exception as e:
        return None, "unparseable notAfter %r: %s" % (not_after, e)
    subj = decoded.get("subject") or ()
    cn = ""
    for rdn in subj:
        for k, v in rdn:
            if k == "commonName":
                cn = v
    return dt, "%s:%d %s" % (host, port, cn)


def cert_severity(days):
    if days < 0:
        return "crit"
    if days < 7:
        return "crit"
    if days < 30:
        return "warn"
    return None


def cmd_health(a):
    ctx = a.context or current_context()
    ns = a.ns
    sv = server_version(ctx, a.timeout)
    banner(ctx, sv, ns)
    rep = Report("health", ctx, ns)
    rep.data["server"] = sv

    # nodes -------------------------------------------------------------------
    nodes = items_of(kjson(ctx, ["get", "nodes"], a.timeout))
    node_rows = []
    for n in nodes:
        name = (n.get("metadata") or {}).get("name", "")
        conds = {c.get("type"): c for c in (n.get("status") or {}).get("conditions") or []}
        ready = (conds.get("Ready") or {}).get("status")
        pressures = [t for t in ("MemoryPressure", "DiskPressure", "PIDPressure")
                     if (conds.get(t) or {}).get("status") == "True"]
        unsched = (n.get("spec") or {}).get("unschedulable")
        node_rows.append({"node": name, "ready": ready or "?",
                          "pressure": ",".join(pressures) or "-",
                          "unschedulable": bool(unsched),
                          "kubelet": ((n.get("status") or {}).get("nodeInfo") or {})
                          .get("kubeletVersion", "")})
        if ready != "True":
            rep.add("crit", "Node", "", name, "NotReady (Ready=%s): %s" % (
                ready, (conds.get("Ready") or {}).get("message", "")[:160]))
        for p in pressures:
            rep.add("warn", "Node", "", name, "%s=True" % p)
        if unsched:
            rep.add("warn", "Node", "", name, "cordoned (unschedulable)")
    rep.section("nodes", node_rows, a.max_items)

    # pods --------------------------------------------------------------------
    pods = items_of(kjson(ctx, ["get", "pods"] + scope_args(ns), a.timeout))
    bad = []
    for p in pods:
        md, st = p.get("metadata") or {}, p.get("status") or {}
        phase = st.get("phase")
        pname, pns = md.get("name", ""), md.get("namespace", "")
        if phase in ("Succeeded",):
            continue
        restarts = pod_restarts(p)
        if phase != "Running":
            bad.append(pod_row(p))
            why = (st.get("reason") or "") or "; ".join(
                filter(None, [container_state(c) for c in
                              st.get("containerStatuses") or []]))
            if not why:
                why = "; ".join(c.get("message") for c in st.get("conditions") or []
                                if c.get("status") == "False" and c.get("message"))
            rep.add("crit", "Pod", pns, pname, "phase=%s: %s" % (phase, why[:200]))
        elif restarts >= 5:
            bad.append(pod_row(p))
            rep.add("warn", "Pod", pns, pname, "%d restarts" % restarts,
                    "; ".join(filter(None, [last_state(c) for c in
                                            st.get("containerStatuses") or []])))
        elif any(not c.get("ready") for c in st.get("containerStatuses") or []):
            bad.append(pod_row(p))
            rep.add("warn", "Pod", pns, pname, "containers not ready",
                    "; ".join("%s=%s" % (c.get("name"), container_state(c))
                              for c in st.get("containerStatuses") or []
                              if not c.get("ready")))
    rep.data["pods_total"] = len(pods)
    rep.section("problem_pods", bad, a.max_items)

    # pvcs --------------------------------------------------------------------
    pvcs = items_of(kjson(ctx, ["get", "pvc"] + scope_args(ns), a.timeout))
    pend = []
    for c in pvcs:
        md, st = c.get("metadata") or {}, c.get("status") or {}
        if st.get("phase") != "Bound":
            pend.append({"ns": md.get("namespace", ""), "pvc": md.get("name", ""),
                         "phase": st.get("phase", ""),
                         "storageClass": (c.get("spec") or {}).get("storageClassName", "")})
            rep.add("warn", "PVC", md.get("namespace", ""), md.get("name", ""),
                    "phase=%s" % st.get("phase"))
    rep.section("unbound_pvcs", pend, a.max_items)

    # warning events (last 60 min) --------------------------------------------
    evs = items_of(kjson(ctx, ["get", "events"] + scope_args(ns) +
                         ["--field-selector", "type=Warning"], a.timeout))
    cutoff = now_utc() - datetime.timedelta(minutes=60)
    recent = []
    for e in evs:
        t = event_time(e)
        if not t or t < cutoff:
            continue
        io = e.get("involvedObject") or {}
        recent.append({"age": human_age(t), "ns": io.get("namespace", ""),
                       "object": "%s/%s" % (io.get("kind", ""), io.get("name", "")),
                       "reason": e.get("reason", ""), "count": e.get("count", 1),
                       "message": (e.get("message") or "")[:200]})
    recent.sort(key=lambda r: r["count"] or 0, reverse=True)
    rep.section("warning_events_60m", recent, a.max_items)
    if recent:
        rep.add("warn", "Events", ns or "", "",
                "%d Warning events in the last 60 min" % len(recent),
                ", ".join(sorted({r["reason"] for r in recent}))[:200])

    # jobs --------------------------------------------------------------------
    jobs = items_of(kjson(ctx, ["get", "jobs"] + scope_args(ns), a.timeout))
    failed_jobs = []
    for j in jobs:
        md, st = j.get("metadata") or {}, j.get("status") or {}
        conds = [c for c in st.get("conditions") or []
                 if c.get("type") == "Failed" and c.get("status") == "True"]
        if conds or (st.get("failed") or 0) > 0:
            failed_jobs.append({"ns": md.get("namespace", ""), "job": md.get("name", ""),
                                "failed": st.get("failed", 0),
                                "reason": conds[0].get("reason", "") if conds else ""})
            rep.add("crit", "Job", md.get("namespace", ""), md.get("name", ""),
                    "failed=%s %s" % (st.get("failed", 0),
                                      conds[0].get("message", "") if conds else ""))
    rep.section("failed_jobs", failed_jobs, a.max_items)

    # pdbs --------------------------------------------------------------------
    pdbs = items_of(kjson(ctx, ["get", "pdb"] + scope_args(ns), a.timeout))
    blocking = []
    for p in pdbs:
        md, st = p.get("metadata") or {}, p.get("status") or {}
        if (st.get("disruptionsAllowed") or 0) == 0 and (st.get("expectedPods") or 0) > 0:
            blocking.append({"ns": md.get("namespace", ""), "pdb": md.get("name", ""),
                             "healthy": st.get("currentHealthy"),
                             "desired": st.get("desiredHealthy"),
                             "expected": st.get("expectedPods")})
            rep.add("warn", "PodDisruptionBudget", md.get("namespace", ""),
                    md.get("name", ""), "disruptionsAllowed=0 — blocks drain/eviction")
    rep.section("blocking_pdbs", blocking, a.max_items)

    # argocd ------------------------------------------------------------------
    apps, aerr = ktry(ctx, ["get", "applications.argoproj.io"] + scope_args(ns), a.timeout)
    if apps is None:
        rep.data["argocd"] = "not available (%s)" % (aerr or "no CRD")
    else:
        rows = []
        for app in items_of(apps):
            md, st = app.get("metadata") or {}, app.get("status") or {}
            sync = (st.get("sync") or {}).get("status", "?")
            health = (st.get("health") or {}).get("status", "?")
            rows.append({"ns": md.get("namespace", ""), "app": md.get("name", ""),
                         "sync": sync, "health": health})
            if health == "Degraded":
                rep.add("crit", "Application", md.get("namespace", ""), md.get("name", ""),
                        "health=Degraded sync=%s" % sync,
                        (st.get("health") or {}).get("message", "")[:200])
            elif sync != "Synced" or health != "Healthy":
                rep.add("warn", "Application", md.get("namespace", ""), md.get("name", ""),
                        "sync=%s health=%s" % (sync, health))
        rep.section("argocd_apps", rows, a.max_items)

    # helm --------------------------------------------------------------------
    rels, herr = htry(ctx, ["list"] + (["-n", ns] if ns else ["-A"]) + ["-o", "json"],
                      a.timeout)
    if rels is None:
        rep.data["helm"] = "not available (%s)" % (herr or "helm failed")
    else:
        rows = []
        for r in rels:
            rows.append({"ns": r.get("namespace", ""), "release": r.get("name", ""),
                         "status": r.get("status", ""), "chart": r.get("chart", ""),
                         "revision": r.get("revision", "")})
            if r.get("status") == "failed":
                rep.add("crit", "HelmRelease", r.get("namespace", ""), r.get("name", ""),
                        "status=failed (chart %s rev %s)" % (r.get("chart"),
                                                             r.get("revision")))
            elif str(r.get("status", "")).startswith("pending"):
                rep.add("warn", "HelmRelease", r.get("namespace", ""), r.get("name", ""),
                        "status=%s — a previous operation may still hold the lock"
                        % r.get("status"))
        rep.section("helm_releases", rows, a.max_items)

    # cert-manager ------------------------------------------------------------
    certs, cerr = ktry(ctx, ["get", "certificates.cert-manager.io"] + scope_args(ns),
                       a.timeout)
    if certs is None:
        rep.data["cert_manager"] = "not available (%s)" % (cerr or "no CRD")
    else:
        rows = []
        for c in items_of(certs):
            md, st = c.get("metadata") or {}, c.get("status") or {}
            ready = next((x for x in st.get("conditions") or []
                          if x.get("type") == "Ready"), {})
            rows.append({"ns": md.get("namespace", ""), "certificate": md.get("name", ""),
                         "ready": ready.get("status", "?"),
                         "notAfter": st.get("notAfter", ""),
                         "renewalTime": st.get("renewalTime", "")})
            if ready.get("status") != "True":
                rep.add("warn", "Certificate", md.get("namespace", ""), md.get("name", ""),
                        "Ready=%s %s" % (ready.get("status"),
                                         (ready.get("message") or "")[:160]))
            dt = parse_ts(st.get("notAfter"))
            if dt:
                days = (dt - now_utc()).days
                sev = cert_severity(days)
                if sev:
                    rep.add(sev, "Certificate", md.get("namespace", ""), md.get("name", ""),
                            "expires in %d d (%s)" % (days, st.get("notAfter")))
        rep.section("certificates", rows, a.max_items)

    # apiserver certificate ---------------------------------------------------
    try:
        cfg = kubeconfig_view(timeout=a.timeout)
        dt, note = apiserver_cert(ctx, cfg)
    except AccessError as e:
        dt, note = None, str(e)
    if dt:
        days = (dt - now_utc()).days
        rep.data["apiserver_cert"] = {"notAfter": dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                      "days_left": days, "endpoint": note}
        sev = cert_severity(days)
        if sev:
            rep.add(sev, "Certificate", "", "apiserver",
                    "apiserver certificate expires in %d d" % days, note)
    else:
        rep.data["apiserver_cert"] = note
        rep.add("info", "Certificate", "", "apiserver",
                "apiserver certificate not checked", note)
    return rep


def human_age(dt):
    if not dt:
        return ""
    secs = int((now_utc() - dt).total_seconds())
    if secs < 90:
        return "%ds" % secs
    if secs < 5400:
        return "%dm" % (secs // 60)
    if secs < 172800:
        return "%dh" % (secs // 3600)
    return "%dd" % (secs // 86400)


# ---------------------------------------------------------------------------------- pod
def container_specs(pod):
    spec = pod.get("spec") or {}
    return list(spec.get("initContainers") or []) + list(spec.get("containers") or [])


def probe_summary(c):
    bits = []
    for kind in ("livenessProbe", "readinessProbe", "startupProbe"):
        if c.get(kind):
            bits.append(kind.replace("Probe", ""))
    return ",".join(bits) or "none"


def fetch_logs(ctx, ns, pod, container, tail, timeout, previous=False):
    args = ["logs", pod, "-n", ns, "-c", container, "--tail", str(tail)]
    if previous:
        args.append("--previous")
    out, err = ktry(ctx, args, timeout=timeout, json_out=False)
    if out is None:
        return None
    return redact_text(out.rstrip("\n"))


def cmd_pod(a):
    ctx = a.context or current_context()
    ns, name = a.ns_pos, a.pod
    sv = server_version(ctx, a.timeout)
    banner(ctx, sv, ns)
    rep = Report("pod", ctx, ns)
    pod = kjson(ctx, ["get", "pod", name, "-n", ns], a.timeout)
    md, spec, st = pod.get("metadata") or {}, pod.get("spec") or {}, pod.get("status") or {}
    rep.data["pod"] = {
        "ns": ns, "name": name, "phase": st.get("phase", ""),
        "node": spec.get("nodeName", ""), "qos": st.get("qosClass", ""),
        "serviceAccount": spec.get("serviceAccountName", "default"),
        "owner": top_owner(pod), "startTime": st.get("startTime", ""),
        "restarts": pod_restarts(pod),
        "podIP": st.get("podIP", ""), "reason": st.get("reason", ""),
        "message": (st.get("message") or "")[:300],
    }
    rep.data["conditions"] = [
        {"type": c.get("type"), "status": c.get("status"), "reason": c.get("reason", ""),
         "message": (c.get("message") or "")[:200]}
        for c in st.get("conditions") or []]

    by_name = {c.get("name"): c for c in container_specs(pod)}
    statuses = list(st.get("initContainerStatuses") or []) + list(
        st.get("containerStatuses") or [])
    rows = []
    for cs in statuses:
        cname = cs.get("name")
        cspec = by_name.get(cname) or {}
        res = cspec.get("resources") or {}
        rows.append({
            "container": cname, "state": container_state(cs), "lastState": last_state(cs),
            "restarts": cs.get("restartCount", 0), "ready": bool(cs.get("ready")),
            "image": cspec.get("image", cs.get("image", "")),
            "pullPolicy": cspec.get("imagePullPolicy", ""),
            "requests": json.dumps(res.get("requests") or {}, sort_keys=True),
            "limits": json.dumps(res.get("limits") or {}, sort_keys=True),
            "probes": probe_summary(cspec),
        })
        waiting = ((cs.get("state") or {}).get("waiting") or {})
        reason = waiting.get("reason") or ""
        term = (cs.get("lastState") or {}).get("terminated") or {}
        if reason in ("CrashLoopBackOff",):
            rep.add("crit", "Container", ns, "%s/%s" % (name, cname),
                    "CrashLoopBackOff after %s restarts" % cs.get("restartCount", 0),
                    last_state(cs) or waiting.get("message", "")[:200])
        elif reason in ("ImagePullBackOff", "ErrImagePull", "InvalidImageName"):
            rep.add("crit", "Container", ns, "%s/%s" % (name, cname),
                    reason, (waiting.get("message") or "")[:200])
        elif reason in ("CreateContainerConfigError", "CreateContainerError",
                        "RunContainerError"):
            rep.add("crit", "Container", ns, "%s/%s" % (name, cname),
                    reason, (waiting.get("message") or "")[:200])
        if term.get("reason") == "OOMKilled" or term.get("exitCode") == 137:
            rep.add("crit", "Container", ns, "%s/%s" % (name, cname),
                    "last exit was OOMKilled/137 — raise the memory limit or cut usage",
                    last_state(cs))
        elif term.get("exitCode") not in (None, 0):
            rep.add("warn", "Container", ns, "%s/%s" % (name, cname),
                    "last exit code %s (%s)" % (term.get("exitCode"), term.get("reason")))
    rep.data["containers"] = rows

    if st.get("phase") == "Pending":
        msgs = [c.get("message") for c in st.get("conditions") or []
                if c.get("status") == "False" and c.get("message")]
        rep.add("crit", "Pod", ns, name, "Pending: %s" % (
            "; ".join(msgs)[:300] or st.get("reason") or "no scheduling message yet"))
    elif st.get("phase") not in ("Running", "Succeeded"):
        rep.add("crit", "Pod", ns, name, "phase=%s %s" % (st.get("phase"),
                                                          st.get("reason") or ""))

    evs, _ = ktry(ctx, ["get", "events", "-n", ns, "--field-selector",
                        "involvedObject.name=%s" % name], a.timeout)
    ev_rows = []
    for e in sorted(items_of(evs or {}), key=lambda e: event_time(e) or now_utc(),
                    reverse=True):
        ev_rows.append({"age": human_age(event_time(e)), "type": e.get("type", ""),
                        "reason": e.get("reason", ""), "count": e.get("count", 1),
                        "message": (e.get("message") or "")[:250]})
    rep.section("events", ev_rows, a.max_items)

    logs = {}
    for cs in statuses:
        cname = cs.get("name")
        txt = fetch_logs(ctx, ns, name, cname, a.tail, a.timeout)
        if txt is not None:
            logs[cname] = txt
        if (cs.get("restartCount") or 0) > 0:
            prev = fetch_logs(ctx, ns, name, cname, a.tail, a.timeout, previous=True)
            if prev:
                logs[cname + " (previous)"] = prev
    rep.data["logs"] = logs
    return rep


# ----------------------------------------------------------------------------- workload
KIND_ALIAS = {
    "deploy": "deployment", "deployment": "deployment", "deployments": "deployment",
    "sts": "statefulset", "statefulset": "statefulset", "statefulsets": "statefulset",
    "ds": "daemonset", "daemonset": "daemonset", "daemonsets": "daemonset",
    "job": "job", "jobs": "job", "cj": "cronjob", "cronjob": "cronjob",
    "cronjobs": "cronjob", "rs": "replicaset", "replicaset": "replicaset",
    "replicasets": "replicaset", "raycluster": "raycluster", "rayclusters": "raycluster",
}
KIND_RESOURCE = {
    "deployment": "deployments.apps", "statefulset": "statefulsets.apps",
    "daemonset": "daemonsets.apps", "job": "jobs.batch", "cronjob": "cronjobs.batch",
    "replicaset": "replicasets.apps", "raycluster": "rayclusters.ray.io",
}


def selector_string(match_labels):
    return ",".join("%s=%s" % (k, v) for k, v in sorted((match_labels or {}).items()))


def cmd_workload(a):
    ctx = a.context or current_context()
    ns = a.ns_pos
    if "/" not in a.ref:
        die("workload takes NS KIND/NAME, e.g. `k8s workload shop deploy/shop-api`")
    kind_raw, name = a.ref.split("/", 1)
    kind = KIND_ALIAS.get(kind_raw.lower())
    if not kind:
        die("unknown kind %r — one of: %s" % (kind_raw, ", ".join(sorted(set(KIND_ALIAS)))))
    sv = server_version(ctx, a.timeout)
    banner(ctx, sv, ns)
    rep = Report("workload", ctx, ns)
    obj = kjson(ctx, ["get", KIND_RESOURCE[kind], name, "-n", ns], a.timeout)
    md, spec, st = obj.get("metadata") or {}, obj.get("spec") or {}, obj.get("status") or {}

    chain = ["%s/%s" % (obj.get("kind") or kind, name)]
    ref = owner_of(obj)
    if ref:
        chain.append("%s/%s" % (ref.get("kind"), ref.get("name")))
    rep.data["workload"] = {
        "ns": ns, "kind": obj.get("kind") or kind, "name": name,
        "owner_chain": " <- ".join(chain),
        "generation": md.get("generation"),
        "observedGeneration": st.get("observedGeneration"),
        "created": md.get("creationTimestamp", ""),
        "images": ", ".join(c.get("image", "") for c in
                            (((spec.get("template") or {}).get("spec") or {})
                             .get("containers") or [])),
    }
    rollout = {k: st.get(k) for k in ("replicas", "readyReplicas", "updatedReplicas",
                                      "availableReplicas", "unavailableReplicas",
                                      "currentReplicas", "numberReady",
                                      "desiredNumberScheduled", "succeeded", "failed",
                                      "active")
               if st.get(k) is not None}
    rollout["spec_replicas"] = spec.get("replicas")
    rep.data["rollout"] = {k: v for k, v in rollout.items() if v is not None}
    rep.data["conditions"] = [
        {"type": c.get("type"), "status": c.get("status"), "reason": c.get("reason", ""),
         "message": (c.get("message") or "")[:200]} for c in st.get("conditions") or []]
    if (md.get("generation") is not None and st.get("observedGeneration") is not None
            and md["generation"] != st["observedGeneration"]):
        rep.add("warn", obj.get("kind") or kind, ns, name,
                "observedGeneration %s behind generation %s — controller has not caught up"
                % (st["observedGeneration"], md["generation"]))
    for c in st.get("conditions") or []:
        if c.get("type") in ("Available", "Ready") and c.get("status") == "False":
            rep.add("crit", obj.get("kind") or kind, ns, name,
                    "%s=False (%s)" % (c.get("type"), c.get("reason")),
                    (c.get("message") or "")[:200])
        if c.get("type") == "Progressing" and c.get("status") == "False":
            rep.add("crit", obj.get("kind") or kind, ns, name,
                    "Progressing=False (%s)" % c.get("reason"),
                    (c.get("message") or "")[:200])
        if c.get("type") == "Failed" and c.get("status") == "True":
            rep.add("crit", obj.get("kind") or kind, ns, name,
                    "Failed (%s)" % c.get("reason"), (c.get("message") or "")[:200])
    want = spec.get("replicas")
    have = st.get("readyReplicas") or 0
    if want is not None and have < want:
        rep.add("warn" if have else "crit", obj.get("kind") or kind, ns, name,
                "%s/%s replicas ready" % (have, want))

    # pods --------------------------------------------------------------------
    pods = []
    if kind == "cronjob":
        jobs = items_of(kjson(ctx, ["get", "jobs.batch", "-n", ns], a.timeout))
        owned = [j for j in jobs
                 if any(r.get("name") == name and r.get("kind") == "CronJob"
                        for r in (j.get("metadata") or {}).get("ownerReferences") or [])]
        rep.section("jobs", [{"job": (j.get("metadata") or {}).get("name"),
                              "succeeded": (j.get("status") or {}).get("succeeded", 0),
                              "failed": (j.get("status") or {}).get("failed", 0),
                              "start": (j.get("status") or {}).get("startTime", "")}
                             for j in owned], a.max_items)
        job_names = {(j.get("metadata") or {}).get("name") for j in owned}
        allpods = items_of(kjson(ctx, ["get", "pods", "-n", ns], a.timeout))
        pods = [p for p in allpods
                if any(r.get("name") in job_names
                       for r in (p.get("metadata") or {}).get("ownerReferences") or [])]
    else:
        if kind == "raycluster":
            sel = "ray.io/cluster=%s" % name
        else:
            sel = selector_string((spec.get("selector") or {}).get("matchLabels"))
        rep.data["selector"] = sel or "(none)"
        if sel:
            pods = items_of(kjson(ctx, ["get", "pods", "-n", ns, "-l", sel], a.timeout))
        if kind in ("deployment",) and pods:
            rs = items_of(kjson(ctx, ["get", "replicasets.apps", "-n", ns, "-l", sel],
                                a.timeout))
            rep.section("replicasets", [
                {"rs": (r.get("metadata") or {}).get("name"),
                 "desired": (r.get("spec") or {}).get("replicas"),
                 "ready": (r.get("status") or {}).get("readyReplicas", 0),
                 "revision": ((r.get("metadata") or {}).get("annotations") or {})
                 .get("deployment.kubernetes.io/revision", "")}
                for r in sorted(rs, key=lambda x: (x.get("metadata") or {})
                                .get("creationTimestamp", ""), reverse=True)],
                a.max_items)
    pod_rows = [pod_row(p) for p in pods]
    rep.section("pods", pod_rows, a.max_items)
    for p in pods:
        pmd, pst = p.get("metadata") or {}, p.get("status") or {}
        if pst.get("phase") not in ("Running", "Succeeded"):
            rep.add("crit", "Pod", ns, pmd.get("name", ""),
                    "phase=%s" % pst.get("phase"),
                    "; ".join(container_state(c) for c in pst.get("containerStatuses") or []))
        elif pod_restarts(p) >= 5:
            rep.add("warn", "Pod", ns, pmd.get("name", ""),
                    "%d restarts" % pod_restarts(p))

    # warning events for the object and its pods ------------------------------
    names = {name} | {(p.get("metadata") or {}).get("name") for p in pods}
    evs = items_of(kjson(ctx, ["get", "events", "-n", ns, "--field-selector",
                               "type=Warning"], a.timeout))
    ev_rows = []
    for e in sorted(evs, key=lambda e: event_time(e) or now_utc(), reverse=True):
        io = e.get("involvedObject") or {}
        if io.get("name") not in names:
            continue
        ev_rows.append({"age": human_age(event_time(e)),
                        "object": "%s/%s" % (io.get("kind", ""), io.get("name", "")),
                        "reason": e.get("reason", ""), "count": e.get("count", 1),
                        "message": (e.get("message") or "")[:250]})
    rep.section("warning_events", ev_rows, a.max_items)

    # worst pod's logs --------------------------------------------------------
    if pods:
        worst = sorted(pods, key=lambda p: (
            (p.get("status") or {}).get("phase") == "Running", -pod_restarts(p)))[0]
        wname = (worst.get("metadata") or {}).get("name")
        rep.data["worst_pod"] = wname
        logs = {}
        for c in (worst.get("spec") or {}).get("containers") or []:
            txt = fetch_logs(ctx, ns, wname, c.get("name"), a.tail, a.timeout)
            if txt is not None:
                logs[c.get("name")] = txt
        rep.data["logs"] = logs
    return rep


# ------------------------------------------------------------------------------- events
def cmd_events(a):
    ctx = a.context or current_context()
    ns = a.ns
    sv = server_version(ctx, a.timeout)
    banner(ctx, sv, ns)
    rep = Report("events", ctx, ns)
    args = ["get", "events"] + scope_args(ns)
    if a.warning:
        args += ["--field-selector", "type=Warning"]
    evs = items_of(kjson(ctx, args, a.timeout))
    cutoff = now_utc() - datetime.timedelta(seconds=parse_duration(a.since, 3600))
    keep = []
    for e in evs:
        t = event_time(e)
        if not t or t < cutoff:
            continue
        keep.append((t, e))
    keep.sort(key=lambda x: x[0], reverse=True)
    rows, by_reason = [], {}
    for t, e in keep:
        io = e.get("involvedObject") or {}
        reason = e.get("reason", "")
        by_reason[reason] = by_reason.get(reason, 0) + (e.get("count") or 1)
        rows.append({"age": human_age(t), "type": e.get("type", ""), "reason": reason,
                     "ns": io.get("namespace", ""),
                     "object": "%s/%s" % (io.get("kind", ""), io.get("name", "")),
                     "count": e.get("count", 1),
                     "message": (e.get("message") or "")[:250]})
    rep.data["since"] = a.since
    rep.data["by_reason"] = dict(sorted(by_reason.items(), key=lambda kv: -kv[1]))
    rep.section("events", rows, a.max_items)
    warn_n = sum(1 for _t, e in keep if e.get("type") == "Warning")
    if warn_n:
        rep.add("warn", "Events", ns or "", "",
                "%d Warning events in the last %s" % (warn_n, a.since),
                ", ".join(list(rep.data["by_reason"])[:8]))
    return rep


# ----------------------------------------------------------------------------- capacity
CAP_RESOURCES = ("cpu", "memory", "nvidia.com/gpu", "ephemeral-storage")


def _res_sum(container_list, field):
    out = {r: 0.0 for r in CAP_RESOURCES}
    for c in container_list:
        blob = ((c.get("resources") or {}).get(field) or {})
        for r in CAP_RESOURCES:
            if r in blob:
                out[r] += cpu_m(blob[r]) if r == "cpu" else parse_quantity(blob[r])
    return out


def fmt_res(r, v):
    if r == "cpu":
        return fmt_cpu(v)
    if r in ("memory", "ephemeral-storage"):
        return fmt_bytes(v)
    return "%g" % v


def cmd_capacity(a):
    ctx = a.context or current_context()
    ns = a.ns
    sv = server_version(ctx, a.timeout)
    banner(ctx, sv, ns)
    rep = Report("capacity", ctx, ns)
    nodes = items_of(kjson(ctx, ["get", "nodes"], a.timeout))
    pods = items_of(kjson(ctx, ["get", "pods"] + scope_args(ns), a.timeout))
    live = {}
    metrics, merr = ktry(ctx, ["get", "--raw", "/apis/metrics.k8s.io/v1beta1/nodes"],
                         a.timeout)
    if metrics:
        for m in items_of(metrics):
            u = m.get("usage") or {}
            live[(m.get("metadata") or {}).get("name")] = {
                "cpu": cpu_m(u.get("cpu")), "memory": parse_quantity(u.get("memory"))}
    else:
        rep.data["live_usage"] = "unavailable (%s)" % (merr or "metrics API")

    per_node = {}
    for p in pods:
        st = p.get("status") or {}
        if st.get("phase") in ("Succeeded", "Failed"):
            continue
        node = (p.get("spec") or {}).get("nodeName") or ""
        d = per_node.setdefault(node, {"pods": 0,
                                       "req": {r: 0.0 for r in CAP_RESOURCES},
                                       "lim": {r: 0.0 for r in CAP_RESOURCES}})
        d["pods"] += 1
        cs = (p.get("spec") or {}).get("containers") or []
        for field, key in (("requests", "req"), ("limits", "lim")):
            s = _res_sum(cs, field)
            for r in CAP_RESOURCES:
                d[key][r] += s[r]

    rows, totals = [], {"alloc": {r: 0.0 for r in CAP_RESOURCES},
                        "req": {r: 0.0 for r in CAP_RESOURCES},
                        "lim": {r: 0.0 for r in CAP_RESOURCES},
                        "pods": 0, "pod_cap": 0}
    for n in nodes:
        name = (n.get("metadata") or {}).get("name", "")
        alloc_raw = (n.get("status") or {}).get("allocatable") or {}
        alloc = {r: (cpu_m(alloc_raw.get(r)) if r == "cpu" else
                     parse_quantity(alloc_raw.get(r))) for r in CAP_RESOURCES}
        pod_cap = int(parse_quantity(alloc_raw.get("pods")) or 0)
        d = per_node.get(name, {"pods": 0, "req": {r: 0.0 for r in CAP_RESOURCES},
                                "lim": {r: 0.0 for r in CAP_RESOURCES}})
        row = {"node": name, "pods": "%d/%d" % (d["pods"], pod_cap)}
        for r in CAP_RESOURCES:
            pct = (100.0 * d["req"][r] / alloc[r]) if alloc[r] else 0.0
            row[r] = "%s/%s (%.0f%%)" % (fmt_res(r, d["req"][r]), fmt_res(r, alloc[r]), pct)
            row["lim_" + r] = fmt_res(r, d["lim"][r])
            totals["alloc"][r] += alloc[r]
            totals["req"][r] += d["req"][r]
            totals["lim"][r] += d["lim"][r]
            if alloc[r] <= 0:
                continue
            if r == "nvidia.com/gpu" and d["req"][r] >= alloc[r]:
                rep.add("crit", "Node", "", name,
                        "GPU fully requested: %g/%g nvidia.com/gpu" % (d["req"][r], alloc[r]))
            elif pct > 90.0:
                rep.add("warn", "Node", "", name,
                        "%s requests at %.0f%% of allocatable (%s/%s)" % (
                            r, pct, fmt_res(r, d["req"][r]), fmt_res(r, alloc[r])))
        if live.get(name):
            row["live"] = "cpu=%s mem=%s" % (fmt_cpu(live[name]["cpu"]),
                                             fmt_bytes(live[name]["memory"]))
        if pod_cap and d["pods"] >= 0.9 * pod_cap:
            rep.add("warn", "Node", "", name, "pod slots %d/%d" % (d["pods"], pod_cap))
        totals["pods"] += d["pods"]
        totals["pod_cap"] += pod_cap
        rows.append(row)
    rep.section("nodes", rows, a.max_items)
    rep.data["cluster_totals"] = dict(
        [("pods", "%d/%d" % (totals["pods"], totals["pod_cap"]))] +
        [(r, "%s requested / %s limits / %s allocatable" % (
            fmt_res(r, totals["req"][r]), fmt_res(r, totals["lim"][r]),
            fmt_res(r, totals["alloc"][r]))) for r in CAP_RESOURCES])

    pending_gpu = [(p.get("metadata") or {}).get("name") for p in pods
                   if (p.get("status") or {}).get("phase") == "Pending"
                   and any("nvidia.com/gpu" in ((c.get("resources") or {}).get("requests")
                                                or {})
                           for c in (p.get("spec") or {}).get("containers") or [])]
    if pending_gpu:
        rep.add("crit", "Scheduling", ns or "", "",
                "%d Pending pod(s) request nvidia.com/gpu" % len(pending_gpu),
                ", ".join(pending_gpu[:10]))

    quotas = items_of(kjson(ctx, ["get", "resourcequotas"] + scope_args(ns), a.timeout))
    qrows = []
    for q in quotas:
        md, st = q.get("metadata") or {}, q.get("status") or {}
        hard, used = st.get("hard") or {}, st.get("used") or {}
        for k, v in hard.items():
            u = used.get(k, "0")
            qrows.append({"ns": md.get("namespace", ""), "quota": md.get("name", ""),
                          "resource": k, "used": u, "hard": v})
            hv, uv = parse_quantity(v), parse_quantity(u)
            if hv > 0 and uv / hv > 0.9:
                rep.add("warn", "ResourceQuota", md.get("namespace", ""), md.get("name", ""),
                        "%s at %.0f%% (%s/%s)" % (k, 100.0 * uv / hv, u, v))
    rep.section("resourcequotas", qrows, a.max_items)
    return rep


# ------------------------------------------------------------------------------- argocd
def source_paths(spec):
    out = []
    for s in ([spec.get("source")] if spec.get("source") else []) + list(
            spec.get("sources") or []):
        if not isinstance(s, dict):
            continue
        out.append((s.get("repoURL") or "", s.get("path") or s.get("chart") or "",
                    s.get("targetRevision") or ""))
    return out


def cmd_argocd(a):
    ctx = a.context or current_context()
    sv = server_version(ctx, a.timeout)
    banner(ctx, sv)
    rep = Report("argocd", ctx)
    apps, aerr = ktry(ctx, ["get", "applications.argoproj.io", "-A"], a.timeout)
    if not GITOPS_ROOT:
        print("note: K8S_GITOPS_ROOT / k8s.gitops_root not set - local source-path check skipped",
              file=sys.stderr)
    if apps is None:
        rep.data["applications"] = "not available (%s)" % (aerr or "no CRD")
        rep.add("info", "Application", "", "", "ArgoCD Application CRD not available",
                aerr or "")
    else:
        rows = []
        for app in items_of(apps):
            md, spec, st = (app.get("metadata") or {}, app.get("spec") or {},
                            app.get("status") or {})
            sync = (st.get("sync") or {}).get("status", "?")
            health = (st.get("health") or {}).get("status", "?")
            paths, local, exists = [], [], []
            for repo, path, rev in source_paths(spec):
                paths.append("%s@%s" % (path, rev) if path else repo)
                if GITOPS_ROOT and GITOPS_REPO_MATCH and GITOPS_REPO_MATCH in repo and path:
                    lp = os.path.join(GITOPS_ROOT, path)
                    local.append(lp)
                    exists.append(os.path.isdir(lp))
            rows.append({
                "ns": md.get("namespace", ""), "app": md.get("name", ""),
                "project": spec.get("project", ""), "sync": sync, "health": health,
                "revision": ((st.get("sync") or {}).get("revision") or "")[:12],
                "dest": "%s/%s" % ((spec.get("destination") or {}).get("name")
                                   or (spec.get("destination") or {}).get("server", ""),
                                   (spec.get("destination") or {}).get("namespace", "")),
                "source_path": ", ".join(paths),
                "local_path": ", ".join(local),
                "local_path_exists": all(exists) if exists else None,
            })
            if health == "Degraded":
                rep.add("crit", "Application", md.get("namespace", ""), md.get("name", ""),
                        "health=Degraded sync=%s" % sync,
                        (st.get("health") or {}).get("message", "")[:200])
            elif sync != "Synced" or health != "Healthy":
                rep.add("warn", "Application", md.get("namespace", ""), md.get("name", ""),
                        "sync=%s health=%s" % (sync, health))
            if exists and not all(exists):
                rep.add("info", "Application", md.get("namespace", ""), md.get("name", ""),
                        "source path not found locally under %s" % GITOPS_ROOT,
                        ", ".join(local))
        rep.section("applications", rows, a.max_items)

    appsets, serr = ktry(ctx, ["get", "applicationsets.argoproj.io", "-A"], a.timeout)
    if appsets is None:
        rep.data["applicationsets"] = "not available (%s)" % (serr or "no CRD")
    else:
        rows = []
        for s in items_of(appsets):
            md, st = s.get("metadata") or {}, s.get("status") or {}
            conds = st.get("conditions") or []
            bad = [c for c in conds if c.get("type") in ("ErrorOccurred",)
                   and c.get("status") == "True"]
            rows.append({"ns": md.get("namespace", ""), "applicationset": md.get("name", ""),
                         "generators": len((s.get("spec") or {}).get("generators") or []),
                         "conditions": ", ".join(
                             "%s=%s" % (c.get("type"), c.get("status")) for c in conds)})
            for c in bad:
                rep.add("warn", "ApplicationSet", md.get("namespace", ""),
                        md.get("name", ""), "ErrorOccurred: %s"
                        % (c.get("message") or "")[:200])
        rep.section("applicationsets", rows, a.max_items)

    projs, perr = ktry(ctx, ["get", "appprojects.argoproj.io", "-A"], a.timeout)
    if projs is None:
        rep.data["appprojects"] = "not available (%s)" % (perr or "no CRD")
    else:
        rep.section("appprojects", [
            {"ns": (p.get("metadata") or {}).get("namespace", ""),
             "project": (p.get("metadata") or {}).get("name", ""),
             "sourceRepos": ", ".join((p.get("spec") or {}).get("sourceRepos") or []),
             "destinations": len((p.get("spec") or {}).get("destinations") or [])}
            for p in items_of(projs)], a.max_items)

    if crd_present(ctx, "stages.kargo.akuity.io", a.timeout):
        kargo = {}
        for res, label in (("stages.kargo.akuity.io", "stages"),
                           ("promotions.kargo.akuity.io", "promotions"),
                           ("freights.kargo.akuity.io", "freights")):
            obj, err = ktry(ctx, ["get", res, "-A"], a.timeout)
            kargo[label] = [
                {"ns": (i.get("metadata") or {}).get("namespace", ""),
                 "name": (i.get("metadata") or {}).get("name", ""),
                 "phase": (i.get("status") or {}).get("phase", "")}
                for i in items_of(obj or {})] if obj is not None else "error: %s" % err
        rep.data["kargo"] = kargo
    else:
        rep.data["kargo"] = "CRDs not installed"
    return rep


# --------------------------------------------------------------------------------- helm
def cmd_helm(a):
    ctx = a.context or current_context()
    ns = a.ns
    sv = server_version(ctx, a.timeout)
    banner(ctx, sv, ns)
    rep = Report("helm", ctx, ns)
    if a.values:
        if not ns:
            die("`helm --values NAME` needs --ns NS")
        out, err = htry(ctx, ["get", "values", a.values, "-n", ns, "-a", "-o", "json"],
                        a.timeout)
        if out is None:
            die("helm get values failed: %s" % err, 1)
        rep.data["values"] = redact_obj(out)
        rep.data["values_note"] = ("redacted by k8s — secret-looking keys are "
                                   "***REDACTED***; Secret data is shown as byte sizes")
    rels, herr = htry(ctx, ["list"] + (["-n", ns] if ns else ["-A"]) + ["-o", "json"],
                      a.timeout)
    if rels is None:
        die("helm list failed: %s" % herr, 1)
    rows = []
    for r in rels:
        rname, rns, status = r.get("name", ""), r.get("namespace", ""), r.get("status", "")
        row = {"ns": rns, "release": rname, "status": status, "chart": r.get("chart", ""),
               "appVersion": r.get("app_version", ""), "revision": r.get("revision", ""),
               "updated": (r.get("updated") or "")[:19]}
        if status != "deployed":
            hist, _ = htry(ctx, ["history", rname, "-n", rns, "-o", "json"], a.timeout)
            if hist:
                row["history"] = "; ".join(
                    "r%s %s %s" % (h.get("revision"), h.get("status"),
                                   (h.get("description") or "")[:60])
                    for h in list(hist)[-3:])
            stat, _ = htry(ctx, ["status", rname, "-n", rns, "-o", "json"], a.timeout)
            if isinstance(stat, dict):
                row["description"] = ((stat.get("info") or {}).get("description") or "")[:200]
            if status == "failed":
                rep.add("crit", "HelmRelease", rns, rname,
                        "status=failed — %s" % row.get("description", ""),
                        row.get("history"))
            elif status.startswith("pending"):
                rep.add("warn", "HelmRelease", rns, rname,
                        "status=%s — a previous operation may still hold the lock" % status,
                        row.get("history"))
            elif status in ("superseded", "unknown", "uninstalling"):
                rep.add("warn", "HelmRelease", rns, rname, "status=%s" % status,
                        row.get("history"))
        rows.append(row)
    rep.section("releases", rows, a.max_items)
    return rep


# -------------------------------------------------------------------------- secret-keys
def secret_summary(obj):
    md = obj.get("metadata") or {}
    keys = {}
    for k, v in (obj.get("data") or {}).items():
        try:
            keys[k] = len(base64.b64decode(v or "", validate=False))
        except Exception:
            keys[k] = len(v or "")
    for k, v in (obj.get("stringData") or {}).items():
        keys[k] = len(v or "")
    return {"name": md.get("name", ""), "ns": md.get("namespace", ""),
            "type": obj.get("type", ""), "keys": dict(sorted(keys.items()))}


def cmd_secret_keys(a):
    if a.ns_pos == "-":
        raw = sys.stdin.read()
        try:
            obj = json.loads(raw)
        except ValueError as e:
            die("stdin is not JSON (%s) — pipe a Secret or List as JSON" % e)
        secrets = ([obj] if obj.get("kind") == "Secret"
                   else [i for i in items_of(obj) if i.get("kind", "Secret") == "Secret"])
        if not secrets:
            die("stdin holds no Secret objects")
        rep = Report("secret-keys", "-")
        rep.section("secrets", [secret_summary(s) for s in secrets], a.max_items)
        rep.data["note"] = "keys and byte sizes only — Secret values are never printed"
        return rep
    ctx = a.context or current_context()
    ns = a.ns_pos
    sv = server_version(ctx, a.timeout)
    banner(ctx, sv, ns)
    rep = Report("secret-keys", ctx, ns)
    if a.all:
        obj = kjson(ctx, ["get", "secrets", "-n", ns], a.timeout)
        rep.section("secrets", [secret_summary(s) for s in items_of(obj)], a.max_items)
    elif not a.name:
        die("secret-keys takes NS NAME, or NS --all, or `-` to read stdin")
    else:
        obj = kjson(ctx, ["get", "secret", a.name, "-n", ns], a.timeout)
        rep.data["secret"] = secret_summary(obj)
    rep.data["note"] = "keys and byte sizes only — Secret values are never printed"
    return rep


# ------------------------------------------------------------------------------- redact
def cmd_redact(a):
    raw = sys.stdin.read()
    try:
        obj = json.loads(raw)
    except ValueError:
        sys.stdout.write(redact_text(raw))
        if raw and not raw.endswith("\n"):
            sys.stdout.write("\n")
        sys.exit(0)
    indent = 2 if (sys.stdout.isatty() or a.md) else None
    sys.stdout.write(json.dumps(redact_obj(obj), indent=indent, default=str) + "\n")
    sys.exit(0)


# ------------------------------------------------------------------------------- promql
PROM_NAMES = ("rancher-monitoring-prometheus", "prometheus-operated", "prometheus-k8s",
              "kube-prometheus-stack-prometheus", "prometheus")


def discover_prometheus(ctx, timeout):
    svcs = items_of(kjson(ctx, ["get", "svc", "-A"], timeout))
    best = None
    for s in svcs:
        md, spec = s.get("metadata") or {}, s.get("spec") or {}
        name = md.get("name", "")
        if name not in PROM_NAMES:
            continue
        port = None
        for p in spec.get("ports") or []:
            if p.get("name") in ("web", "http-web") or p.get("port") == 9090:
                port = p.get("name") or p.get("port")
                break
        if port is None:
            continue
        rank = PROM_NAMES.index(name)
        if best is None or rank < best[0]:
            best = (rank, md.get("namespace", ""), name, port)
    if not best:
        die("no Prometheus service found (looked for %s) — pass --svc NS/NAME:PORT"
            % ", ".join(PROM_NAMES), 1)
    return best[1], best[2], best[3]


def cmd_promql(a):
    ctx = a.context or current_context()
    sv = server_version(ctx, a.timeout)
    banner(ctx, sv)
    rep = Report("promql", ctx)
    if a.svc:
        m = re.match(r"^([^/]+)/([^:]+):(.+)$", a.svc)
        if not m:
            die("--svc takes NS/NAME:PORT")
        pns, pname, pport = m.group(1), m.group(2), m.group(3)
    else:
        pns, pname, pport = discover_prometheus(ctx, a.timeout)
    rep.data["prometheus"] = "%s/%s:%s" % (pns, pname, pport)
    base = "/api/v1/namespaces/%s/services/%s:%s/proxy/api/v1" % (pns, pname, pport)
    q = urllib.parse.quote(a.query, safe="")
    if a.range:
        end = now_utc()
        start = end - datetime.timedelta(seconds=parse_duration(a.range, 3600))
        path = "%s/query_range?query=%s&start=%d&end=%d&step=%s" % (
            base, q, int(start.timestamp()), int(end.timestamp()),
            urllib.parse.quote(a.step, safe=""))
    else:
        path = "%s/query?query=%s" % (base, q)
    body = kjson(ctx, ["get", "--raw", path], a.timeout)
    if body.get("status") != "success":
        die("prometheus: %s %s" % (body.get("errorType", ""), body.get("error", "")), 1)
    data = body.get("data") or {}
    rtype = data.get("resultType", "")
    rep.data["query"] = a.query
    rep.data["resultType"] = rtype
    rows = []
    for item in data.get("result") or []:
        metric = item.get("metric") or {}
        label = metric.get("__name__", "")
        rest = {k: v for k, v in metric.items() if k != "__name__"}
        if rtype == "matrix":
            vals = item.get("values") or []
            value = vals[-1][1] if vals else ""
            extra = {"samples": len(vals)}
        else:
            value = (item.get("value") or ["", ""])[1]
            extra = {}
        row = {"metric": label or "{}", "labels": ", ".join(
            "%s=%s" % (k, v) for k, v in sorted(rest.items()))[:200], "value": value}
        row.update(extra)
        rows.append(row)
    rep.section("result", rows, a.max_items)
    return rep


# -------------------------------------------------------------------------------- certs
def cmd_certs(a):
    ctx = a.context or current_context()
    sv = server_version(ctx, a.timeout)
    banner(ctx, sv)
    rep = Report("certs", ctx)
    try:
        cfg = kubeconfig_view(timeout=a.timeout)
        dt, note = apiserver_cert(ctx, cfg)
    except AccessError as e:
        dt, note = None, str(e)
    if dt:
        days = (dt - now_utc()).days
        rep.data["apiserver_cert"] = {"endpoint": note, "days_left": days,
                                      "notAfter": dt.strftime("%Y-%m-%dT%H:%M:%SZ")}
        sev = cert_severity(days)
        if sev:
            rep.add(sev, "Certificate", "", "apiserver",
                    "apiserver certificate %s in %d d" % (
                        "expired" if days < 0 else "expires", abs(days)), note)
    else:
        rep.data["apiserver_cert"] = note
        rep.add("info", "Certificate", "", "apiserver", "not checked", note)

    csrs, cerr = ktry(ctx, ["get", "csr"], a.timeout)
    if csrs is None:
        rep.data["csrs"] = "not available (%s)" % (cerr or "")
    else:
        rows = []
        for c in items_of(csrs):
            md, st = c.get("metadata") or {}, c.get("status") or {}
            conds = [x.get("type") for x in st.get("conditions") or []]
            state = conds[0] if conds else "Pending"
            rows.append({"csr": md.get("name", ""), "state": state,
                         "signer": (c.get("spec") or {}).get("signerName", ""),
                         "requestor": (c.get("spec") or {}).get("username", ""),
                         "age": human_age(parse_ts(md.get("creationTimestamp")))})
            if state == "Pending":
                rep.add("warn", "CertificateSigningRequest", "", md.get("name", ""),
                        "pending approval (signer %s)"
                        % (c.get("spec") or {}).get("signerName", ""))
        rep.section("csrs", rows, a.max_items)

    certs, err = ktry(ctx, ["get", "certificates.cert-manager.io", "-A"], a.timeout)
    if certs is None:
        rep.data["cert_manager"] = "not available (%s)" % (err or "no CRD")
    else:
        rows = []
        for c in items_of(certs):
            md, st = c.get("metadata") or {}, c.get("status") or {}
            ready = next((x for x in st.get("conditions") or []
                          if x.get("type") == "Ready"), {})
            dt2 = parse_ts(st.get("notAfter"))
            days = (dt2 - now_utc()).days if dt2 else None
            rows.append({"ns": md.get("namespace", ""), "certificate": md.get("name", ""),
                         "ready": ready.get("status", "?"),
                         "notAfter": st.get("notAfter", ""),
                         "days_left": days,
                         "renewalTime": st.get("renewalTime", ""),
                         "secret": (c.get("spec") or {}).get("secretName", "")})
            if ready.get("status") != "True":
                rep.add("warn", "Certificate", md.get("namespace", ""), md.get("name", ""),
                        "Ready=%s %s" % (ready.get("status"),
                                         (ready.get("message") or "")[:160]))
            if days is not None:
                sev = cert_severity(days)
                if sev:
                    rep.add(sev, "Certificate", md.get("namespace", ""), md.get("name", ""),
                            "%s in %d d (%s)" % ("expired" if days < 0 else "expires",
                                                 abs(days), st.get("notAfter")))
        rep.section("cert_manager", rows, a.max_items)
    return rep


# -------------------------------------------------------------------------------- audit
SYSTEM_NS_RE = re.compile(r"^(kube-|cattle-|calico-|tigera-|fleet-|rancher)")


def image_tag_bad(image):
    ref = image.split("/")[-1]
    if "@" in ref:
        return False
    if ":" not in ref:
        return True
    return ref.rsplit(":", 1)[1] == "latest"


def cmd_audit(a):
    ctx = a.context or current_context()
    ns = a.ns
    sv = server_version(ctx, a.timeout)
    banner(ctx, sv, ns)
    rep = Report("audit", ctx, ns)
    pods = items_of(kjson(ctx, ["get", "pods"] + scope_args(ns), a.timeout))
    namespaces = items_of(kjson(ctx, ["get", "namespaces"], a.timeout))
    sas = items_of(kjson(ctx, ["get", "serviceaccounts"] + scope_args(ns), a.timeout))
    sa_automount = {}
    for s in sas:
        md = s.get("metadata") or {}
        sa_automount[(md.get("namespace"), md.get("name"))] = s.get(
            "automountServiceAccountToken")

    by_owner = {}
    for p in pods:
        md, spec = p.get("metadata") or {}, p.get("spec") or {}
        pns, owner = md.get("namespace", ""), top_owner(p)
        entry = by_owner.setdefault((pns, owner), {"ns": pns, "workload": owner,
                                                   "pods": 0, "issues": []})
        entry["pods"] += 1

        def flag(sev, code, message, evidence=None):
            if code in entry["issues"]:
                return
            entry["issues"].append(code)
            rep.add(sev, "Workload", pns, owner, message, evidence, dedupe=True)

        pod_sc = spec.get("securityContext") or {}
        if spec.get("hostNetwork"):
            flag("crit", "hostNetwork", "hostNetwork=true — shares the node network namespace")
        if spec.get("hostPID"):
            flag("crit", "hostPID", "hostPID=true — sees every process on the node")
        if spec.get("hostIPC"):
            flag("crit", "hostIPC", "hostIPC=true — shares the node IPC namespace")
        hostpaths = [(v.get("hostPath") or {}).get("path")
                     for v in spec.get("volumes") or [] if v.get("hostPath")]
        if hostpaths:
            flag("crit", "hostPath", "mounts hostPath volume(s)",
                 ", ".join(x for x in hostpaths if x)[:200])
        containers = list(spec.get("containers") or []) + list(
            spec.get("initContainers") or [])
        for c in containers:
            sc = c.get("securityContext") or {}
            res = c.get("resources") or {}
            if sc.get("privileged"):
                flag("crit", "privileged", "container %s runs privileged" % c.get("name"))
            if sc.get("allowPrivilegeEscalation") is not False:
                flag("warn", "allowPrivilegeEscalation",
                     "container %s does not set allowPrivilegeEscalation=false"
                     % c.get("name"))
            if not res.get("limits"):
                flag("warn", "no-limits", "container %s has no resource limits"
                     % c.get("name"))
            if not res.get("requests"):
                flag("info", "no-requests", "container %s has no resource requests"
                     % c.get("name"))
            if image_tag_bad(c.get("image", "")):
                flag("warn", "mutable-image",
                     "container %s uses a mutable image tag" % c.get("name"),
                     c.get("image", ""))
            if not (c.get("livenessProbe") or c.get("readinessProbe")):
                flag("info", "no-probes", "container %s has no liveness/readiness probe"
                     % c.get("name"))
            run_as_user = sc.get("runAsUser", pod_sc.get("runAsUser"))
            non_root = sc.get("runAsNonRoot", pod_sc.get("runAsNonRoot"))
            if run_as_user == 0 or (non_root is not True and run_as_user is None):
                flag("warn", "run-as-root",
                     "container %s may run as root (runAsNonRoot unset/false)"
                     % c.get("name"))
        sa = spec.get("serviceAccountName") or "default"
        automount = spec.get("automountServiceAccountToken")
        if automount is None:
            automount = sa_automount.get((pns, sa))
        if sa == "default" and automount is not False:
            flag("warn", "default-sa-automount",
                 "uses the default ServiceAccount with its token automounted")

    rows = [{"ns": v["ns"], "workload": v["workload"], "pods": v["pods"],
             "issues": ", ".join(sorted(v["issues"])) or "-"}
            for v in by_owner.values() if v["issues"]]
    rows.sort(key=lambda r: (r["ns"], r["workload"]))
    rep.data["workloads_scanned"] = len(by_owner)
    rep.section("workloads", rows, a.max_items)

    ns_rows = []
    for n in namespaces:
        md = n.get("metadata") or {}
        name = md.get("name", "")
        if ns and name != ns:
            continue
        labels = md.get("labels") or {}
        enforce = labels.get("pod-security.kubernetes.io/enforce")
        ns_rows.append({"namespace": name, "psa_enforce": enforce or "-",
                        "psa_audit": labels.get("pod-security.kubernetes.io/audit", "-"),
                        "psa_warn": labels.get("pod-security.kubernetes.io/warn", "-")})
        if not enforce and not SYSTEM_NS_RE.match(name):
            rep.add("info", "Namespace", name, "",
                    "no pod-security.kubernetes.io/enforce label "
                    "(Pod Security Admission not enforced)")
    rep.section("namespaces", ns_rows, a.max_items)
    return rep


# --------------------------------------------------------------------------------- main
class _Parser(argparse.ArgumentParser):
    def error(self, message):
        die("k8s %s: %s\n\nRun `k8s` with no arguments for the command list."
            % (self.prog.split()[-1] if " " in self.prog else "", message), 1)


def common_parser():
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--context", help="kubeconfig context (default: current-context)")
    p.add_argument("--json", action="store_true", help="force JSON output")
    p.add_argument("--md", action="store_true", help="force Markdown output")
    p.add_argument("--timeout", type=int, default=TIMEOUT,
                   help="per-call --request-timeout in seconds (default %d)" % TIMEOUT)
    p.add_argument("--max-items", type=int, default=50, dest="max_items")
    p.add_argument("--max-bytes", type=int, default=200000, dest="max_bytes")
    p.add_argument("--tail", type=int, default=50, help="log lines per container")
    return p


def build_parser():
    common = common_parser()
    top = _Parser(prog="k8s", description="Read-only Kubernetes operator client",
                  add_help=False)
    subs = top.add_subparsers(dest="cmd")

    def sub(name, **kw):
        return subs.add_parser(name, parents=[common], **kw)

    c = sub("contexts", help="probe every kubeconfig context")
    c.add_argument("--only", help="comma-separated context names")
    c.add_argument("--probe-timeout", type=int, default=8, dest="probe_timeout")
    c.add_argument("--write", action="store_true",
                   help="regenerate references/clusters.md")
    c.set_defaults(fn=cmd_contexts)

    h = sub("health", help="cluster health sweep")
    h.add_argument("--ns", help="restrict namespaced reads to NS")
    h.set_defaults(fn=cmd_health)

    p = sub("pod", help="triage one pod")
    p.add_argument("ns_pos", metavar="NS")
    p.add_argument("pod", metavar="POD")
    p.set_defaults(fn=cmd_pod)

    w = sub("workload", help="triage one workload (KIND/NAME)")
    w.add_argument("ns_pos", metavar="NS")
    w.add_argument("ref", metavar="KIND/NAME")
    w.set_defaults(fn=cmd_workload)

    e = sub("events", help="recent events")
    e.add_argument("--ns")
    e.add_argument("--warning", action="store_true", help="type=Warning only")
    e.add_argument("--since", default="60m", help="Nm/Nh/Nd (default 60m)")
    e.set_defaults(fn=cmd_events)

    cap = sub("capacity", help="allocatable vs requests/limits")
    cap.add_argument("--ns")
    cap.set_defaults(fn=cmd_capacity)

    ag = sub("argocd", help="ArgoCD (and Kargo) state")
    ag.set_defaults(fn=cmd_argocd)

    hl = sub("helm", help="Helm releases")
    hl.add_argument("--ns")
    hl.add_argument("--values", metavar="NAME", help="print `helm get values -a` redacted")
    hl.set_defaults(fn=cmd_helm)

    sk = sub("secret-keys", help="Secret key names and byte sizes only")
    sk.add_argument("ns_pos", metavar="NS", help="namespace, or `-` to read stdin")
    sk.add_argument("name", metavar="NAME", nargs="?")
    sk.add_argument("--all", action="store_true", help="every Secret in NS")
    sk.set_defaults(fn=cmd_secret_keys)

    rd = sub("redact", help="stdin -> redacted stdout")
    rd.set_defaults(fn=cmd_redact)

    pq = sub("promql", help="query Prometheus through the apiserver proxy")
    pq.add_argument("query", metavar="QUERY")
    pq.add_argument("--svc", metavar="NS/NAME:PORT")
    pq.add_argument("--range", help="range query window, e.g. 1h")
    pq.add_argument("--step", default="60s")
    pq.set_defaults(fn=cmd_promql)

    ct = sub("certs", help="certificate expiry and pending CSRs")
    ct.set_defaults(fn=cmd_certs)

    au = sub("audit", help="pod-spec security posture")
    au.add_argument("--ns")
    au.set_defaults(fn=cmd_audit)
    return top, list(subs.choices)


def main():
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        sys.exit(1)
    top, names = build_parser()
    if argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        sys.exit(0)
    if argv[0] not in names:
        die("Unknown command %r. Commands: %s\n\nRun `k8s` with no arguments for the "
            "full usage." % (argv[0], ", ".join(names)), 1)
    a = top.parse_args(argv)
    try:
        rep = a.fn(a)
    except AccessError as e:
        die(str(e), 2)
    except BrokenPipeError:
        sys.exit(0)
    fmt = "json" if a.json else ("md" if a.md else
                                 ("md" if sys.stdout.isatty() else "json"))
    rep.emit(fmt, a.max_bytes)
    sys.exit(rep.exit_code())


if __name__ == "__main__":
    main()
