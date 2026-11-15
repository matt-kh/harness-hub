#!/usr/bin/env python3
"""Read-only Linux host client over SSH aliases — stdlib only.

Canonical invocation: `lx <cmd>` (symlinked into ~/.local/bin, like `k8s`/`obs`).
Hosts are the `Host` aliases of ~/.ssh/config (and the files it `Include`s) — nothing else
is accepted as a host. Every remote call is

    ssh -o BatchMode=yes -o ConnectTimeout=<LINUX_SSH_TIMEOUT> -o LogLevel=ERROR -T -n -- ALIAS '<script>'

with one fixed, read-only script per subcommand (every probe tolerant of a missing tool:
`command -v X >/dev/null && X …`). Host-key checking is left to your ssh config (never
disabled), no tty is requested, nothing is uploaded, no key file is read, and the parsing
happens here so raw dumps never land in a model context. All remote text passes the
redactor.

Output is findings-first: human-readable Markdown by default, JSON with --json:
  {"host","prod","os","command","findings":[{"severity","kind","name","message","evidence"}],
   "data":{...}}
Exit codes: 0 ok, 1 at least one crit/warn finding (or a usage error), 2 access error
(unknown alias, unreachable, auth failed, host key not verified, timeout, no ssh).

Every host command prints a banner to STDERR:
  host=web1 os=ubuntu 24.04 [PROD]
[PROD] marks an alias matching LINUX_PROD_RE — reads stay free there, but every
remediation is a suggestion for the human to run, with its blast radius.

Commands (run with no args to print this list):
  hosts                 Host aliases from ~/.ssh/config (+ Include), no wildcards: alias,
                        HostName, User, Port, and role / notes from LINUX_INVENTORY. Never
                        shows IdentityFile or reads a key. No remote call.
  check HOST            Reachability and key auth (BatchMode): remote user, hostname, kernel.
  facts HOST            os-release, kernel, hostname, uptime, CPUs and model, memory and swap,
                        virtualisation, init, timezone, Proxmox VE / NixOS versions.
  health HOST           Failed systemd units, load per CPU, disk and inode usage, memory
                        available and pressure (PSI), swap, OOM kills (24 h), pending
                        reboot (Debian flag, needs-restarting, NixOS booted != current),
                        time sync.
  logs HOST [--since 1h] [--limit 200] [--unit U] [--priority P]
                        journalctl, bounded (--since and -n always set, never a follow
                        mode), UTC ISO timestamps, redacted. Falls back to the tail of
                        /var/log/messages or syslog on hosts without journald.
  net HOST              ip -br addr/link, routes, bonds / VLANs / bridges, the renderer in
                        use (netplan, systemd-networkd, NetworkManager, ifupdown,
                        network-scripts, NixOS), firewall services and nft / ufw /
                        firewalld state, resolvers.
  storage HOST          lsblk, real mounts (read-only remounts flagged), df, LVM (lvs/vgs,
                        thin-pool fill), ZFS pools, md RAID, SMART health when readable
                        without sudo.
  audit HOST            sshd effective settings (sshd -T when readable, else the config
                        files, approximate), listening sockets, sudoers shape (mode,
                        readability, counts — never contents), automatic updates, pending
                        (security) updates, SUID count in /usr, world-writable files in /etc.
  redact                stdin -> stdout filter (JSON or free text). No remote call.

Common flags (after the subcommand): --json, --timeout S (whole remote call, default 120),
--max-items N (50), --max-bytes N (200000). `lx --version` prints the version.

Deliberately NOT implemented — do not work around these with raw ssh; the guard asks or
denies, so tell the human what to run instead: anything that changes a host (restarts,
package installs, config edits, firewall or network changes), remote sudo, interactive
sessions and -t, tunnels and forwarding, uploads, follow modes (journalctl -f / tail -f),
disabling host-key checking, reading or copying private keys.

Env (each falls back to the harness config key in brackets, read from build/config.json via
HARNESS_CONFIG_JSON / HARNESS_HOME, then to the default):
  LINUX_PROD_RE [linux.prod_re]  default `(^|[-_./:])(prod|production)([-_./:]|$)`, matched
                         case-insensitively against the alias
  LINUX_INVENTORY [linux.inventory]  optional host file, one host per line: alias, role,
                         notes (tab-, comma- or space-separated; `#` comments); relative =
                         under HARNESS_HOME
  LINUX_SSH_TIMEOUT [linux.ssh_timeout]  ssh ConnectTimeout in seconds (default 10)
  LINUX_REDACT_EXTRA_RE [linux.redact_extra_re]  extra Python regex of token shapes masked
                         on top of the built-in list (default: empty)
  LINUX_SSH_BIN          ssh binary override (used by the tests; default `ssh`)
  LINUX_SSH_CONFIG       user ssh config override (used by the tests; default ~/.ssh/config)
"""
import argparse
import base64
import glob
import json
import os
import re
import subprocess
import sys

__version__ = "0.1.0"

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


def _setting(env, key, default):
    v = os.environ.get(env)
    if v is None or v == "":
        v = cfg(key)
    return default if v is None or v == "" else v


SSH = os.environ.get("LINUX_SSH_BIN") or "ssh"
SSH_CONFIG = os.path.expanduser(os.environ.get("LINUX_SSH_CONFIG") or "~/.ssh/config")
PROD_RE = re.compile(str(_setting("LINUX_PROD_RE", "linux.prod_re",
                                  r"(^|[-_./:])(prod|production)([-_./:]|$)")), re.I)
INVENTORY = _hpath(str(_setting("LINUX_INVENTORY", "linux.inventory", "")))
try:
    SSH_TIMEOUT = max(1, int(_setting("LINUX_SSH_TIMEOUT", "linux.ssh_timeout", 10)))
except (TypeError, ValueError):
    SSH_TIMEOUT = 10
ALIAS_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")


def die(msg, code=1):
    print(msg, file=sys.stderr)
    sys.exit(code)


class AccessError(Exception):
    """Unknown alias / unreachable / auth / host key / timeout / no ssh -> exit 2."""


def is_prod(alias):
    return bool(alias and PROD_RE.search(alias))


# --------------------------------------------------------------------------- redaction
# >>> redact
KEY_BODY = (r"(pass(word|wd)?|secret|token|api[-_]?key|private[-_]?key|access[-_]?key"
            r"|client[-_]?secret|credential|auth|cert(ificate)?|jwt|dsn"
            r"|connection[-_]?string)")
SECRET_KEY_RE = re.compile(r"(?i)" + KEY_BODY)
REDACTED = "***REDACTED***"
_TEXT_KEY_RE = re.compile(r"^(\s*[\w.-]*" + KEY_BODY + r"[\w.-]*\s*[:=]\s*)(.+)$", re.I)
# the anchored rule above only catches `key: value` lines; logs usually carry a timestamp
# and a level first, so the same key=value shape is redacted anywhere in the line too.
# An HTTP auth scheme word (`Authorization: Bearer X`) is consumed with the token after it,
# so the credential does not survive behind a masked scheme word. Accepted cost: a value
# that merely looks like a scheme word (`token=basic retry`) also masks the word after it.
_AUTH_SCHEME = r"(?:bearer|basic|token|digest|negotiate|api-?key|ssws|oauth)"
_TEXT_KEY_INLINE_RE = re.compile(
    r"(?P<key>[\w.-]*" + KEY_BODY + r"[\w.-]*)(?P<sep>\s*[:=]\s*)"
    r"(?P<val>\"[^\"]*\"|'[^']*'|" + _AUTH_SCHEME + r"\s+\S+|\S+)", re.I)
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


_EXTRA_WARNED = []


def _usable_extra(extra_re):
    """extra_re, or None when it is unset or matches the empty string (warned once)."""
    if extra_re is None or not extra_re.match(""):
        return extra_re
    if not _EXTRA_WARNED:
        _EXTRA_WARNED.append(True)
        sys.stderr.write("redact: extra pattern matches the empty string; ignored\n")
    return None


def redact_obj(obj, extra_re=None):
    """Walk a JSON structure: secret-ish keys -> ***REDACTED***, Secret data -> sizes.
    extra_re (compiled regex or None): its matches inside the remaining string values are
    redacted too, after key masking; Secret `<N bytes>` sizes are never passed to it."""
    return _redact_walk(obj, _usable_extra(extra_re))


def _redact_walk(obj, extra_re):
    if isinstance(obj, dict):
        sized = ()
        if obj.get("kind") == "Secret":
            obj = _secret_sizes(obj)
            sized = ("data", "stringData")
        out = {}
        for k, v in obj.items():
            if k in sized and isinstance(v, dict):
                out[k] = v  # byte sizes only: no value left to mask
            elif isinstance(v, (dict, list)):
                out[k] = _redact_walk(v, extra_re)
            elif SECRET_KEY_RE.search(str(k)) and v is not None and not (
                    isinstance(v, str) and v.startswith("<") and v.endswith("bytes>")):
                out[k] = REDACTED
            else:
                out[k] = _redact_walk(v, extra_re)
        return out
    if isinstance(obj, list):
        return [_redact_walk(x, extra_re) for x in obj]
    if extra_re is not None and isinstance(obj, str):
        return extra_re.sub(REDACTED, obj)
    return obj


def redact_text(text, extra_re=None):
    """Redact free text / logs: key=value lines, AWS keys, JWTs, PEM blocks, URL creds.
    extra_re (compiled regex or None): its matches are redacted too, after the built-in
    rules, so a pattern naming a key or scheme word cannot hide what they would catch."""
    if not text:
        return text
    extra_re = _usable_extra(extra_re)
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
    text = "\n".join(lines)
    if extra_re is not None:
        text = extra_re.sub(REDACTED, text)
    return text
# <<< redact


# extra token shapes (linux.redact_extra_re), compiled on first use by a redacting path.
_EXTRA_RE_CACHE = []


def _extra_re():
    if not _EXTRA_RE_CACHE:
        src = str(_setting("LINUX_REDACT_EXTRA_RE", "linux.redact_extra_re", ""))
        try:
            _EXTRA_RE_CACHE.append(re.compile(src) if src else None)
        except re.error as e:
            die("linux.redact_extra_re is not a valid Python regex: %s "
                "(LINUX_REDACT_EXTRA_RE / linux.redact_extra_re; fix or unset it)" % e)
    return _EXTRA_RE_CACHE[0]


def red(text):
    return redact_text(text or "", _extra_re())


# --------------------------------------------------------------------------- ssh config
def _cfg_words(line):
    """`Key value…` or `Key=value…` -> (key lower, [values]); quotes respected."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None, []
    m = re.match(r"^([A-Za-z][A-Za-z0-9]*)\s*(?:=\s*|\s+)(.*)$", line)
    if not m:
        return None, []
    vals = re.findall(r'"([^"]*)"|(\S+)', m.group(2))
    return m.group(1).lower(), [a or b for a, b in vals]


def _include_paths(pattern, base_dir):
    p = os.path.expanduser(pattern)
    if not os.path.isabs(p):
        p = os.path.join(base_dir, p)
    return sorted(glob.glob(p))


def parse_ssh_config(path=None, base_dir=None, depth=0, seen=None):
    """[{alias, hostname, user, port}] for every non-wildcard Host pattern, in file order.
    IdentityFile and every other option are ignored; key files are never opened."""
    path = path or SSH_CONFIG
    base_dir = base_dir or os.path.dirname(SSH_CONFIG)
    seen = seen if seen is not None else set()
    real = os.path.realpath(path)
    if depth > 16 or real in seen:
        return []
    seen.add(real)
    try:
        with open(path) as fh:
            lines = fh.read().splitlines()
    except (OSError, UnicodeDecodeError):
        return []
    hosts, block = [], None
    for line in lines:
        key, vals = _cfg_words(line)
        if key is None:
            continue
        if key == "include":
            for v in vals:
                for inc in _include_paths(v, base_dir):
                    hosts.extend(parse_ssh_config(inc, base_dir, depth + 1, seen))
            continue
        if key == "host":
            block = []
            for v in vals:
                if any(c in v for c in "*?!") or not ALIAS_RE.match(v):
                    continue
                block.append({"alias": v, "hostname": "", "user": "", "port": ""})
            hosts.extend(block)
            continue
        if key == "match":
            block = None
            continue
        if block and key in ("hostname", "user", "port") and vals:
            for h in block:
                if not h[key]:          # ssh semantics: the first value obtained wins
                    h[key] = vals[0]
    return hosts


def known_aliases():
    out, seen = [], set()
    for h in parse_ssh_config():
        if h["alias"] not in seen:
            seen.add(h["alias"])
            out.append(h)
    return out


def read_inventory():
    """{alias: (role, notes)} from LINUX_INVENTORY, or {} when unset/unreadable."""
    if not INVENTORY:
        return {}
    try:
        with open(INVENTORY) as fh:
            lines = fh.read().splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    inv = {}
    for line in lines:
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "\t" in s:
            parts = s.split("\t", 2)
        elif "," in s:
            parts = s.split(",", 2)
        else:
            parts = s.split(None, 2)
        parts = [p.strip() for p in parts] + ["", ""]
        if parts[0]:
            inv[parts[0]] = (parts[1], parts[2])
    return inv


def resolve_alias(alias):
    if not ALIAS_RE.match(alias or ""):
        raise AccessError("%r is not a host alias (letters, digits, `._-`; no user@ or options) "
                          "— run `lx hosts`" % alias)
    if alias not in {h["alias"] for h in known_aliases()}:
        raise AccessError("%s is not a Host alias in %s — run `lx hosts`; add the alias to your "
                          "ssh config yourself (lx only reaches aliases)" % (alias, SSH_CONFIG))
    return alias


# ------------------------------------------------------------------------------ remote
def ssh_argv(alias, script):
    return [SSH, "-o", "BatchMode=yes", "-o", "ConnectTimeout=%d" % SSH_TIMEOUT,
            "-o", "LogLevel=ERROR", "-T", "-n", "--", alias, script]


def classify_ssh_error(alias, err):
    e = err or ""
    first = next((l.strip() for l in e.splitlines() if l.strip()), "ssh exited 255")
    if re.search(r"Permission denied|Too many authentication failures|no such identity", e, re.I):
        return ("%s: key auth failed (BatchMode, no password prompts): %s — load your key "
                "with ssh-add, then `lx check %s`" % (alias, first, alias))
    if re.search(r"Host key verification failed|REMOTE HOST IDENTIFICATION HAS CHANGED"
                 r"|No [A-Z0-9]+ host key is known", e, re.I):
        return ("%s: host key not verified: %s — compare the fingerprint and add the "
                "known_hosts entry yourself; never disable the check" % (alias, first))
    if re.search(r"timed out|No route to host|Connection refused|Could not resolve"
                 r"|Name or service not known|Network is unreachable|Connection closed"
                 r"|Connection reset", e, re.I):
        return "%s: unreachable: %s" % (alias, first)
    return "%s: ssh failed: %s" % (alias, first)


def run_remote(alias, script, timeout):
    try:
        p = subprocess.run(ssh_argv(alias, script), capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise AccessError("%s: timed out after %ds (whole call; raise --timeout)" % (alias, timeout))
    except FileNotFoundError:
        raise AccessError("executable file not found: %s" % SSH)
    except OSError as e:
        raise AccessError("%s: %s" % (SSH, e))
    if p.returncode == 255:
        raise AccessError(classify_ssh_error(alias, p.stderr))
    return p.stdout


def section(name, body):
    return "echo '@@lx %s'\n{\n%s\n} 2>/dev/null" % (name, body.strip("\n"))


def script(cmd, sections):
    parts = ["echo '@@lxcmd %s'" % cmd] + [section(n, b) for n, b in sections] + ["true"]
    return "\n".join(parts) + "\n"


def parse_sections(out):
    secs, cur = {}, None
    for line in (out or "").splitlines():
        if line.startswith("@@lxcmd "):
            continue
        if line.startswith("@@lx "):
            cur = line[5:].strip()
            secs[cur] = []
            continue
        if cur is not None:
            secs[cur].append(line)
    return {k: "\n".join(v).rstrip("\n") for k, v in secs.items()}


OS_SECTION = ("os", "cat /etc/os-release 2>/dev/null || cat /usr/lib/os-release")


def parse_os_release(text):
    d = {}
    for line in (text or "").splitlines():
        m = re.match(r"^([A-Z_][A-Z0-9_]*)=(.*)$", line.strip())
        if m:
            v = m.group(2).strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            d[m.group(1)] = v
    return d


def os_label(osr):
    label = " ".join(x for x in (osr.get("ID", ""), osr.get("VERSION_ID", "")) if x)
    return label or "?"


def banner(alias, os_lbl):
    print("host=%s os=%s%s" % (alias, os_lbl or "?", " [PROD]" if is_prod(alias) else ""),
          file=sys.stderr)


# ------------------------------------------------------------------------------ report
SEV_ORDER = {"crit": 0, "warn": 1, "info": 2}


class Report(object):
    def __init__(self, command, host=None, osr=None):
        self.command = command
        self.host = host
        self.prod = is_prod(host) if host else False
        self.os = os_label(osr) if osr is not None else None
        self.findings = []
        self.data = {}
        self.blocks = set()

    def add(self, severity, kind, name, message, evidence=None):
        if severity not in SEV_ORDER:
            severity = "info"
        self.findings.append({"severity": severity, "kind": kind, "name": name or "",
                              "message": message, "evidence": evidence})

    def section(self, name, items, max_items=None, block=False):
        if block:
            self.blocks.add(name)
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
                                                    f["name"], f["message"]))

    def envelope(self):
        env = {"host": self.host, "prod": self.prod}
        if self.os is not None:
            env["os"] = self.os
        env.update({"command": self.command, "findings": self.sorted_findings(),
                    "data": self.data})
        return env

    def markdown(self):
        title = "# lx %s" % self.command
        if self.host:
            title += " — %s%s" % (self.host, " [PROD]" if self.prod else "")
        out = [title, ""]
        if self.os is not None:
            out += ["os: %s" % self.os, ""]
        fs = self.sorted_findings()
        out += ["## Findings (%d)" % len(fs), ""]
        if fs:
            out += ["| sev | kind | name | message |", "|---|---|---|---|"]
            for f in fs:
                out.append("| %s | %s | %s | %s |" % (f["severity"], f["kind"],
                                                      md_cell(f["name"] or "-"),
                                                      md_cell(f["message"])))
        else:
            out.append("none")
        out.append("")
        for name, val in self.data.items():
            if name.endswith("_truncated") or name.endswith("_total"):
                continue
            out += ["## %s" % name, ""]
            if name in self.blocks and isinstance(val, list):
                out += ["```"] + [str(x) for x in val] + ["```"] if val else ["_none_"]
            else:
                out.extend(md_value(val))
            if self.data.get(name + "_truncated"):
                out += ["", "_showing %d of %d — rerun with --max-items N or --json_"
                        % (len(val), self.data.get(name + "_total", len(val)))]
            out.append("")
        return "\n".join(out)

    def emit(self, fmt, max_bytes):
        txt = json.dumps(self.envelope(), indent=2) if fmt == "json" else self.markdown()
        raw = txt.encode("utf-8")
        if max_bytes and len(raw) > max_bytes:
            txt = raw[:max_bytes].decode("utf-8", "ignore")
            txt += "\n\n…[truncated %d bytes — rerun with --json > file]" % (len(raw) - max_bytes)
        sys.stdout.write(txt if txt.endswith("\n") else txt + "\n")


def md_cell(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, (dict, list)):
        v = json.dumps(v)
    return str(v).replace("|", "\\|").replace("\n", " ⏎ ")


def md_value(val):
    if isinstance(val, list):
        if not val:
            return ["_none_"]
        if all(isinstance(x, dict) for x in val):
            cols = []
            for row in val:
                for k in row:
                    if k not in cols:
                        cols.append(k)
            lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
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
    return [md_cell(val)]


# ----------------------------------------------------------------------------- helpers
def kv_lines(text, sep="="):
    d = {}
    for line in (text or "").splitlines():
        if sep in line:
            k, v = line.split(sep, 1)
            d[k.strip()] = v.strip()
    return d


def meminfo_kib(text):
    d = {}
    for line in (text or "").splitlines():
        m = re.match(r"^(\w+):\s+(\d+)", line)
        if m:
            d[m.group(1)] = int(m.group(2))
    return d


def fmt_kib(n):
    if n is None:
        return ""
    for unit, div in (("T", 1024.0 ** 3), ("G", 1024.0 ** 2), ("M", 1024.0)):
        if n >= div:
            return "%.1f%s" % (n / div, unit)
    return "%dK" % n


def fmt_duration(seconds):
    s = int(seconds)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m = s // 60
    return ("%dd %dh %dm" % (d, h, m)) if d else ("%dh %dm" % (h, m))


def to_int(s, default=None):
    try:
        return int(str(s).strip().rstrip("%"))
    except (TypeError, ValueError):
        return default


PSEUDO_FS = {"tmpfs", "devtmpfs", "squashfs", "overlay", "efivarfs", "proc", "sysfs", "devpts",
             "cgroup", "cgroup2", "mqueue", "debugfs", "tracefs", "securityfs", "pstore", "bpf",
             "autofs", "hugetlbfs", "configfs", "fusectl", "binfmt_misc", "nsfs", "ramfs",
             "rpc_pipefs", "selinuxfs", "fuse.gvfsd-fuse", "fuse.portal", "nfsd", "iso9660",
             "fuse.lxcfs", "zram", "none"}


def parse_df(text):
    """df -PT (or -P) -> [{fs, type, size_kib|inodes, used, avail, use_pct, mount}]."""
    rows = []
    for line in (text or "").splitlines():
        f = line.split()
        if not f or f[0] == "Filesystem":
            continue
        if len(f) >= 7:
            src, typ, size, used, avail, pct, mnt = f[0], f[1], f[2], f[3], f[4], f[5], " ".join(f[6:])
        elif len(f) == 6:
            src, typ, size, used, avail, pct, mnt = f[0], "", f[1], f[2], f[3], f[4], f[5]
        else:
            continue
        if typ in PSEUDO_FS or (not typ and src in PSEUDO_FS) or mnt.startswith("/snap/"):
            continue
        rows.append({"fs": src, "type": typ, "size": to_int(size), "used": to_int(used),
                     "avail": to_int(avail), "use_pct": to_int(pct), "mount": mnt})
    return rows


def usage_findings(rep, rows, kind, what):
    for r in rows:
        p = r["use_pct"]
        if p is None:
            continue
        if p >= 95:
            rep.add("crit", kind, r["mount"], "%s %d%% used on %s" % (what, p, r["fs"]))
        elif p >= 90:
            rep.add("warn", kind, r["mount"], "%s %d%% used on %s" % (what, p, r["fs"]))


def disk_rows(rows):
    return [{"mount": r["mount"], "fs": r["fs"], "type": r["type"], "size": fmt_kib(r["size"]),
             "used": fmt_kib(r["used"]), "avail": fmt_kib(r["avail"]),
             "use%": r["use_pct"]} for r in rows]


def inode_rows(rows):
    return [{"mount": r["mount"], "inodes": r["size"], "used": r["used"],
             "use%": r["use_pct"]} for r in rows if r["use_pct"] is not None]


def remote_report(cmd, alias, sections, a):
    """Run the fixed script for `cmd` and return (Report, parsed sections)."""
    alias = resolve_alias(alias)
    out = run_remote(alias, script(cmd, [OS_SECTION] + sections), a.timeout)
    secs = parse_sections(out)
    osr = parse_os_release(secs.get("os", ""))
    banner(alias, os_label(osr))
    rep = Report(cmd, alias, osr)
    return rep, secs, osr


# -------------------------------------------------------------------------------- hosts
def cmd_hosts(a):
    rep = Report("hosts")
    hosts = known_aliases()
    inv = read_inventory()
    if not os.path.exists(SSH_CONFIG):
        rep.add("warn", "ssh-config", SSH_CONFIG, "no ssh config — lx only reaches Host aliases; "
                "add them to ~/.ssh/config yourself")
    elif not hosts:
        rep.add("warn", "ssh-config", SSH_CONFIG, "no Host aliases (wildcard patterns are not "
                "aliases) — add one `Host <alias>` block per machine")
    if inv is None:
        rep.add("warn", "inventory", INVENTORY, "linux.inventory is set but unreadable")
        inv = {}
    rows = []
    for h in hosts:
        role, notes = inv.get(h["alias"], ("", ""))
        rows.append({"alias": h["alias"], "hostname": h["hostname"], "user": h["user"],
                     "port": h["port"], "role": role, "notes": notes,
                     "prod": is_prod(h["alias"])})
    names = {h["alias"] for h in hosts}
    for alias in inv:
        if alias not in names:
            rep.add("warn", "inventory", alias, "in the inventory but not a Host alias in the "
                    "ssh config — lx cannot reach it")
    rep.section("hosts", rows, a.max_items)
    return rep


# -------------------------------------------------------------------------------- check
def cmd_check(a):
    alias = resolve_alias(a.host)
    try:
        out = run_remote(alias, script("check", [
            OS_SECTION, ("user", "id -un"), ("hostname", "hostname"),
            ("kernel", "uname -sr")]), a.timeout)
    except AccessError as e:
        banner(alias, "?")
        rep = Report("check", alias)
        rep.add("crit", "access", alias, str(e))
        rep.section("check", {"reachable": False, "auth": False, "error": str(e)})
        rep.access_failed = True
        return rep
    secs = parse_sections(out)
    osr = parse_os_release(secs.get("os", ""))
    banner(alias, os_label(osr))
    rep = Report("check", alias, osr)
    rep.section("check", {"reachable": True, "auth": True, "batch_mode": True,
                          "remote_user": secs.get("user", ""),
                          "hostname": secs.get("hostname", ""),
                          "kernel": secs.get("kernel", ""),
                          "os": osr.get("PRETTY_NAME", "")})
    if secs.get("user", "") == "root":
        rep.add("warn", "login", alias, "logs in as root — give agents an unprivileged alias")
    return rep


# -------------------------------------------------------------------------------- facts
FACTS = [
    ("kernel", "uname -srm"),
    ("hostname", "hostname -f 2>/dev/null || hostname"),
    ("uptime", "cat /proc/uptime"),
    ("cpu", "nproc\ngrep -m1 -E '^(model name|Model|cpu model)' /proc/cpuinfo"),
    ("mem", "grep -E '^(MemTotal|SwapTotal):' /proc/meminfo"),
    ("virt", "command -v systemd-detect-virt >/dev/null && systemd-detect-virt"),
    ("init", "cat /proc/1/comm"),
    ("timezone", "timedatectl show -p Timezone --value 2>/dev/null || cat /etc/timezone"),
    ("pve", "command -v pveversion >/dev/null && pveversion"),
    ("nixos", "command -v nixos-version >/dev/null && nixos-version"),
]


def cmd_facts(a):
    rep, s, osr = remote_report("facts", a.host, FACTS, a)
    up = s.get("uptime", "").split()
    cpu = s.get("cpu", "").splitlines()
    mem = meminfo_kib(s.get("mem", ""))
    model = cpu[1].split(":", 1)[1].strip() if len(cpu) > 1 and ":" in cpu[1] else ""
    try:
        uptime = fmt_duration(float(up[0])) if up else ""
    except ValueError:
        uptime = ""
    facts = {
        "os": osr.get("PRETTY_NAME", ""), "id": osr.get("ID", ""),
        "id_like": osr.get("ID_LIKE", ""), "version_id": osr.get("VERSION_ID", ""),
        "kernel": s.get("kernel", ""), "hostname": s.get("hostname", ""),
        "uptime": uptime, "cpus": to_int(cpu[0]) if cpu else None, "cpu_model": model,
        "mem_total": fmt_kib(mem.get("MemTotal")), "swap_total": fmt_kib(mem.get("SwapTotal")),
        "virt": s.get("virt", "") or "unknown", "init": s.get("init", ""),
        "timezone": s.get("timezone", ""),
    }
    if s.get("pve"):
        facts["proxmox_ve"] = s["pve"]
    if s.get("nixos"):
        facts["nixos"] = s["nixos"]
    rep.section("facts", facts)
    if facts["init"] and facts["init"] != "systemd":
        rep.add("info", "init", a.host, "PID 1 is %s, not systemd: health and logs read less"
                % facts["init"])
    return rep


# ------------------------------------------------------------------------------- health
HEALTH = [
    ("nproc", "nproc"),
    ("loadavg", "cat /proc/loadavg"),
    ("failed", "systemctl list-units --failed --no-legend --plain --no-pager"),
    ("df", "df -PT 2>/dev/null || df -P"),
    ("dfi", "df -PTi 2>/dev/null || df -Pi"),
    ("meminfo", "grep -E '^(MemTotal|MemAvailable|SwapTotal|SwapFree):' /proc/meminfo"),
    ("psi", "cat /proc/pressure/memory"),
    ("reboot", "test -f /var/run/reboot-required && echo required=yes\n"
               "test -f /var/run/reboot-required.pkgs && sed 's/^/pkg=/' /var/run/reboot-required.pkgs\n"
               "command -v needs-restarting >/dev/null && { needs-restarting -r >/dev/null 2>&1; "
               "echo \"needs-restarting=$?\"; }\n"
               "test -e /run/booted-system && echo \"booted=$(readlink /run/booted-system/kernel)\" "
               "&& echo \"current=$(readlink /run/current-system/kernel)\""),
    ("timesync", "timedatectl show -p NTPSynchronized -p NTP"),
    ("oom", "journalctl -k -q --no-pager --since -24h | grep -ciE 'out of memory|oom-kill'"),
]


def cmd_health(a):
    rep, s, _ = remote_report("health", a.host, HEALTH, a)
    host = a.host
    ncpu = to_int(s.get("nproc"), 0) or 0
    load = s.get("loadavg", "").split()
    loads = {}
    if len(load) >= 3:
        loads = {"load1": load[0], "load5": load[1], "load15": load[2], "cpus": ncpu}
        try:
            per = float(load[0]) / ncpu if ncpu else 0.0
            if ncpu and per > 2.0:
                rep.add("warn", "load", host, "load1 %s on %d CPUs (%.1f per CPU)" % (load[0], ncpu, per))
        except ValueError:
            pass
    failed = []
    for line in s.get("failed", "").splitlines():
        f = line.split(None, 4)
        if f and f[0] not in ("●", "*"):
            failed.append({"unit": f[0], "load": f[1] if len(f) > 1 else "",
                           "active": f[2] if len(f) > 2 else "", "sub": f[3] if len(f) > 3 else "",
                           "description": f[4] if len(f) > 4 else ""})
    for u in failed:
        rep.add("warn", "unit", u["unit"], "failed: %s" % u["description"])
    disks = parse_df(s.get("df", ""))
    usage_findings(rep, disks, "disk", "disk")
    inodes = parse_df(s.get("dfi", ""))
    usage_findings(rep, inodes, "inodes", "inodes")
    mem = meminfo_kib(s.get("meminfo", ""))
    memory = {}
    if mem.get("MemTotal"):
        avail = mem.get("MemAvailable", 0)
        pct = 100.0 * avail / mem["MemTotal"]
        memory = {"total": fmt_kib(mem["MemTotal"]), "available": fmt_kib(avail),
                  "available%": round(pct, 1)}
        if pct < 5:
            rep.add("crit", "memory", host, "only %.1f%% memory available" % pct)
        elif pct < 10:
            rep.add("warn", "memory", host, "only %.1f%% memory available" % pct)
        if mem.get("SwapTotal"):
            used = mem["SwapTotal"] - mem.get("SwapFree", 0)
            spct = 100.0 * used / mem["SwapTotal"]
            memory.update({"swap_total": fmt_kib(mem["SwapTotal"]), "swap_used%": round(spct, 1)})
            if spct >= 80:
                rep.add("warn", "swap", host, "swap %.0f%% used" % spct)
    m = re.search(r"some avg10=([\d.]+)", s.get("psi", ""))
    if m:
        memory["psi_some_avg10"] = float(m.group(1))
        if float(m.group(1)) >= 10:
            rep.add("warn", "memory", host, "memory pressure: tasks stalled %s%% of the last 10 s"
                    % m.group(1))
    oom = to_int(s.get("oom"), None)
    if oom:
        memory["oom_kills_24h"] = oom
        rep.add("warn", "oom", host, "%d OOM kill line(s) in the kernel log (24 h)" % oom)
    rb = s.get("reboot", "")
    kv = kv_lines(rb)
    pkgs = [l[4:] for l in rb.splitlines() if l.startswith("pkg=")]
    reboot = {"required": False}
    if kv.get("required") == "yes":
        reboot = {"required": True, "source": "/var/run/reboot-required", "packages": pkgs}
    elif kv.get("needs-restarting") == "1":
        reboot = {"required": True, "source": "needs-restarting -r"}
    elif kv.get("booted") and kv.get("current") and kv["booted"] != kv["current"]:
        reboot = {"required": True, "source": "NixOS booted-system kernel != current-system"}
    if reboot["required"]:
        rep.add("warn", "reboot", host, "reboot pending (%s)%s" % (
            reboot["source"], (": " + ", ".join(pkgs)) if pkgs else ""))
    ts = kv_lines(s.get("timesync", ""))
    timesync = {"ntp": ts.get("NTP", ""), "synchronized": ts.get("NTPSynchronized", "")}
    if timesync["synchronized"] == "no":
        rep.add("warn", "time", host, "clock not NTP-synchronised (NTP=%s)" % (timesync["ntp"] or "?"))
    rep.section("load", loads)
    rep.section("failed_units", failed, a.max_items)
    rep.section("disks", disk_rows(disks), a.max_items)
    rep.section("inodes", inode_rows(inodes), a.max_items)
    rep.section("memory", memory)
    rep.section("reboot", reboot)
    rep.section("timesync", timesync)
    return rep


# --------------------------------------------------------------------------------- logs
SINCE_RE = re.compile(r"^(\d+[smhdw]|today|yesterday|\d{4}-\d{2}-\d{2}( \d{2}:\d{2}(:\d{2})?)?)$")
UNIT_RE = re.compile(r"^[A-Za-z0-9@._:\\-]+$")
_PRIO = r"(emerg|alert|crit|err|warning|notice|info|debug|[0-7])"
PRIO_RE = re.compile(r"^%s(\.\.%s)?$" % (_PRIO, _PRIO))
MAX_LIMIT = 2000


def journal_cmd(since, limit, unit, prio):
    spec = ("-" + since) if re.match(r"^\d+[smhdw]$", since) else since
    parts = ["journalctl", "--no-pager", "-q", "--utc", "-o", "short-iso",
             "--since", "'%s'" % spec, "-n", str(limit)]
    if unit:
        parts += ["-u", "'%s'" % unit]
    if prio:
        parts += ["-p", "'%s'" % prio]
    return " ".join(parts)


def cmd_logs(a):
    since = a.since or "1h"
    if not SINCE_RE.match(since):
        die("lx logs: --since takes Ns/Nm/Nh/Nd/Nw, today, yesterday or YYYY-MM-DD[ HH:MM[:SS]]", 1)
    limit = a.limit if a.limit is not None else 200
    if limit < 1 or limit > MAX_LIMIT:
        die("lx logs: --limit must be 1..%d" % MAX_LIMIT, 1)
    if a.unit and not UNIT_RE.match(a.unit):
        die("lx logs: --unit takes a unit name (letters, digits, @._:-)", 1)
    if a.priority and not PRIO_RE.match(a.priority):
        die("lx logs: --priority takes emerg..debug or 0..7, or a range like warning..emerg", 1)
    body = ("if command -v journalctl >/dev/null 2>&1; then %s 2>&1\n"
            "else echo '@@nojournal'; tail -n %d /var/log/messages 2>/dev/null "
            "|| tail -n %d /var/log/syslog; fi" % (journal_cmd(since, limit, a.unit, a.priority),
                                                    limit, limit))
    rep, s, _ = remote_report("logs", a.host, [("logs", body)], a)
    lines, hints = [], []
    raw = s.get("logs", "")
    source = "journalctl"
    for line in raw.splitlines():
        if line == "@@nojournal":
            source = "/var/log tail"
            continue
        if line.startswith("Hint: ") or line.startswith("No journal files were"):
            hints.append(line)
            continue
        lines.append(red(line))
    if source != "journalctl":
        rep.add("info", "logs", a.host, "no journalctl on this host: last %d lines of "
                "/var/log/messages or /var/log/syslog, no --since/--unit filter" % limit)
    if hints:
        rep.add("info", "logs", a.host, "journal partly unreadable for this login (not in the "
                "adm / systemd-journal group): " + red(hints[0]))
    rep.section("query", {"source": source, "since": since, "limit": limit,
                          "unit": a.unit or "", "priority": a.priority or "",
                          "lines": len(lines)})
    rep.section("lines", lines, block=True)
    return rep


# ---------------------------------------------------------------------------------- net
NET = [
    ("addr", "ip -br addr"),
    ("link", "ip -br link"),
    ("route", "ip route show"),
    ("route6", "ip -6 route show default"),
    ("detail", "ip -o -d link show"),
    ("renderer",
     "ls /etc/netplan 2>/dev/null | sed 's/^/netplan-file=/'\n"
     "grep -h 'renderer:' /etc/netplan/*.yaml 2>/dev/null | tr -d ' ' | sed 's/^renderer:/netplan-renderer=/'\n"
     "for u in systemd-networkd NetworkManager networking network; do "
     "echo \"$u=$(systemctl is-active $u 2>/dev/null)\"; done\n"
     "test -f /etc/network/interfaces && echo \"ifupdown-ifaces=$(grep -cE '^[[:space:]]*iface' /etc/network/interfaces)\"\n"
     "test -d /etc/sysconfig/network-scripts && echo \"ifcfg=$(ls /etc/sysconfig/network-scripts 2>/dev/null | grep -c '^ifcfg-')\"\n"
     "test -e /etc/NIXOS && echo nixos=yes"),
    ("firewall",
     "for u in nftables firewalld ufw iptables; do echo \"unit-$u=$(systemctl is-active $u 2>/dev/null)\"; done\n"
     "command -v nft >/dev/null && nft list tables 2>&1 | sed 's/^/nft: /'\n"
     "command -v ufw >/dev/null && ufw status 2>&1 | head -1 | sed 's/^/ufw: /'\n"
     "command -v firewall-cmd >/dev/null && firewall-cmd --state 2>&1 | sed 's/^/firewalld: /'"),
    ("dns", "grep -E '^(nameserver|search|domain)' /etc/resolv.conf\n"
            "command -v resolvectl >/dev/null && resolvectl dns 2>/dev/null | sed 's/^/resolved: /'"),
]
VIRTUAL_KINDS = ("veth", "bridge", "vxlan", "wireguard", "tun", "dummy", "macvlan", "ipvlan")
LINK_KINDS = ("bond", "bond_slave", "vlan", "bridge", "bridge_slave", "vxlan", "wireguard",
              "veth", "macvlan", "ipvlan", "tun", "dummy")
PERM_RE = re.compile(r"Operation not permitted|Permission denied|must be root|need to be root"
                     r"|You need to be root|Authorization failed|not authorized", re.I)


def parse_link_detail(text):
    out = {}
    for line in (text or "").splitlines():
        m = re.match(r"^\d+:\s+([^:@\s]+)(?:@(\S+?))?:\s+<([^>]*)>(.*)$", line)
        if not m:
            continue
        name, parent, rest = m.group(1), m.group(2) or "", m.group(4)
        segs = [x.strip() for x in rest.split("\\")]
        kind, extra = "", ""
        for seg in segs[2:] if len(segs) > 2 else []:
            w = seg.split()
            if w and w[0] in LINK_KINDS:
                kind = w[0]
                if kind == "vlan":
                    mm = re.search(r"\bid (\d+)", seg)
                    extra = "id %s" % mm.group(1) if mm else ""
                elif kind == "bond":
                    mm = re.search(r"\bmode (\S+)", seg)
                    extra = "mode %s" % mm.group(1) if mm else ""
                break
        master = re.search(r"\bmaster (\S+)", segs[0] if segs else "")
        out[name] = {"kind": kind, "parent": parent, "master": master.group(1) if master else "",
                     "detail": extra}
    return out


def cmd_net(a):
    rep, s, osr = remote_report("net", a.host, NET, a)
    host = a.host
    detail = parse_link_detail(s.get("detail", ""))
    addrs = {}
    for line in s.get("addr", "").splitlines():
        f = line.split()
        if f:
            addrs[f[0].split("@")[0]] = f[2:]
    links = []
    for line in s.get("link", "").splitlines():
        f = line.split()
        if len(f) < 2:
            continue
        name = f[0].split("@")[0]
        flags = f[-1].strip("<>").split(",") if f[-1].startswith("<") else []
        d = detail.get(name, {})
        links.append({"name": name, "state": f[1], "kind": d.get("kind", ""),
                      "master": d.get("master", ""), "parent": d.get("parent", ""),
                      "detail": d.get("detail", ""),
                      "addresses": " ".join(addrs.get(name, []))})
        if (name != "lo" and "UP" in flags and "NO-CARRIER" in flags
                and d.get("kind", "") not in VIRTUAL_KINDS):
            rep.add("warn", "link", name, "administratively up but no carrier (cable, switch "
                    "port or peer down)")
    bonds = {l["name"]: [x["name"] for x in links if x["master"] == l["name"]]
             for l in links if l["kind"] == "bond"}
    for b, members in sorted(bonds.items()):
        if len(members) < 2:
            rep.add("warn", "bond", b, "bond has %d member(s); no redundancy" % len(members))
    routes = [l for l in s.get("route", "").splitlines() if l.strip()]
    routes6 = [l for l in s.get("route6", "").splitlines() if l.strip()]
    if not any(r.startswith("default") for r in routes):
        rep.add("warn", "route", host, "no IPv4 default route")
    rk = kv_lines(s.get("renderer", ""))
    netplan_files = [l.split("=", 1)[1] for l in s.get("renderer", "").splitlines()
                     if l.startswith("netplan-file=")]
    active = [u for u in ("systemd-networkd", "NetworkManager", "networking", "network")
              if rk.get(u) == "active"]
    if rk.get("nixos") == "yes":
        renderer = "nixos (networking.* in configuration.nix%s)" % (
            ", systemd-networkd" if "systemd-networkd" in active else "")
    elif netplan_files:
        backend = rk.get("netplan-renderer", "") or "networkd"
        renderer = "netplan -> %s" % ("NetworkManager" if backend == "NetworkManager"
                                     else "systemd-networkd")
    elif "NetworkManager" in active:
        renderer = "NetworkManager"
    elif "systemd-networkd" in active:
        renderer = "systemd-networkd"
    elif to_int(rk.get("ifupdown-ifaces"), 0):
        renderer = "ifupdown (/etc/network/interfaces)"
    elif to_int(rk.get("ifcfg"), 0):
        renderer = "network-scripts (ifcfg-*)"
    else:
        renderer = "unknown"
    fw_lines = s.get("firewall", "").splitlines()
    fk = kv_lines("\n".join(l for l in fw_lines if l.startswith("unit-")))
    fw_active = [k[5:] for k, v in sorted(fk.items()) if v == "active"]
    nft = [l[5:] for l in fw_lines if l.startswith("nft: ")]
    ufw = next((l[5:] for l in fw_lines if l.startswith("ufw: ")), "")
    fwd = next((l[11:] for l in fw_lines if l.startswith("firewalld: ")), "")
    firewall = {"active_services": fw_active,
                "nft_tables": "needs root" if any(PERM_RE.search(x) for x in nft)
                else [x.replace("table ", "") for x in nft],
                "ufw": "needs root" if PERM_RE.search(ufw) else ufw,
                "firewalld": "needs root" if PERM_RE.search(fwd) else fwd}
    if not fw_active and not (isinstance(firewall["nft_tables"], list) and firewall["nft_tables"]):
        rep.add("info", "firewall", host, "no firewall service active and no nft tables visible "
                "(for the human: `sudo nft list ruleset`)")
    dns_lines = s.get("dns", "").splitlines()
    nameservers = [l.split()[1] for l in dns_lines if l.startswith("nameserver ") and len(l.split()) > 1]
    search = [w for l in dns_lines if l.startswith("search ") for w in l.split()[1:]]
    resolved = [l[len("resolved: "):] for l in dns_lines if l.startswith("resolved: ")]
    if not nameservers:
        rep.add("warn", "dns", host, "no nameserver in /etc/resolv.conf")
    rep.section("links", links, a.max_items)
    rep.section("routes", routes, a.max_items)
    rep.section("routes6_default", routes6)
    rep.section("renderer", {"in_use": renderer, "netplan_files": netplan_files,
                             "active_services": active})
    rep.section("firewall", firewall)
    rep.section("dns", {"nameservers": nameservers, "search": search,
                        "resolved": [x for x in resolved if x.strip()]})
    return rep


# ------------------------------------------------------------------------------ storage
STORAGE = [
    ("lsblk", "lsblk -J -o NAME,TYPE,SIZE,FSTYPE,MOUNTPOINT,RO,ROTA,MODEL 2>/dev/null "
              "|| lsblk -P -o NAME,TYPE,SIZE,FSTYPE,MOUNTPOINT,RO,ROTA,MODEL"),
    ("findmnt", "findmnt -rn -o TARGET,SOURCE,FSTYPE,OPTIONS"),
    ("df", "df -PT 2>/dev/null || df -P"),
    ("lvs", "command -v lvs >/dev/null && lvs --noheadings --separator '|' "
            "-o lv_name,vg_name,lv_attr,lv_size,data_percent,pool_lv 2>&1"),
    ("vgs", "command -v vgs >/dev/null && vgs --noheadings --separator '|' "
            "-o vg_name,pv_count,lv_count,vg_size,vg_free 2>&1"),
    ("zpool", "command -v zpool >/dev/null && zpool list -H -o name,size,alloc,free,cap,health"),
    ("zstatus", "command -v zpool >/dev/null && zpool status -x"),
    ("mdstat", "cat /proc/mdstat"),
    ("smart",
     "command -v smartctl >/dev/null && for d in /sys/block/*; do n=${d##*/}; "
     "case $n in loop*|ram*|zram*|sr*|dm-*|md*|nbd*) continue;; esac; "
     "r=$(smartctl -H \"/dev/$n\" 2>&1 | grep -iE 'overall-health|health status|permission denied"
     "|operation not permitted|unable to detect|open device' | head -1); "
     "echo \"$n ${r:-unknown}\"; done"),
]


def flatten_lsblk(nodes, depth=0, out=None):
    out = [] if out is None else out
    for n in nodes or []:
        out.append({"name": ("  " * depth) + str(n.get("name", "")), "type": n.get("type", ""),
                    "size": n.get("size", ""), "fstype": n.get("fstype") or "",
                    "mountpoint": n.get("mountpoint") or "",
                    "ro": n.get("ro") in (True, "1", 1), "rota": n.get("rota") in (True, "1", 1),
                    "model": (n.get("model") or "").strip()})
        flatten_lsblk(n.get("children"), depth + 1, out)
    return out


def parse_lsblk(text):
    try:
        return flatten_lsblk(json.loads(text).get("blockdevices"))
    except (ValueError, AttributeError):
        pass
    rows = []
    for line in (text or "").splitlines():
        d = dict(re.findall(r'(\w+)="([^"]*)"', line))
        if d:
            rows.append({"name": d.get("NAME", ""), "type": d.get("TYPE", ""),
                         "size": d.get("SIZE", ""), "fstype": d.get("FSTYPE", ""),
                         "mountpoint": d.get("MOUNTPOINT", ""), "ro": d.get("RO") == "1",
                         "rota": d.get("ROTA") == "1", "model": d.get("MODEL", "").strip()})
    return rows


def cmd_storage(a):
    rep, s, _ = remote_report("storage", a.host, STORAGE, a)
    host = a.host
    devices = parse_lsblk(s.get("lsblk", ""))
    mounts = []
    for line in s.get("findmnt", "").splitlines():
        f = line.split(" ")
        if len(f) < 4 or f[2] in PSEUDO_FS or f[2].startswith("fuse.") or f[0].startswith("/snap/"):
            continue
        opts = f[3].split(",")
        target = f[0].replace("\\x20", " ")
        mounts.append({"target": target, "source": f[1], "fstype": f[2],
                       "ro": "ro" in opts})
        if "ro" in opts:
            rep.add("warn", "mount", target, "%s (%s) is mounted read-only — often an error "
                    "remount; check `lx logs %s --priority err`" % (target, f[2], host))
    disks = parse_df(s.get("df", ""))
    usage_findings(rep, disks, "disk", "disk")
    lvs, vgs = [], []
    lvs_txt, vgs_txt = s.get("lvs", ""), s.get("vgs", "")
    if PERM_RE.search(lvs_txt + vgs_txt) or "non-root" in (lvs_txt + vgs_txt):
        lvs = vgs = "needs root (for the human: sudo lvs; sudo vgs)"
        rep.add("info", "lvm", host, "LVM not readable without root")
    elif lvs_txt or vgs_txt:
        for line in lvs_txt.splitlines():
            f = [x.strip() for x in line.split("|")]
            if len(f) >= 4 and f[0] and not f[0].startswith("WARNING"):
                lvs.append({"lv": f[0], "vg": f[1], "attr": f[2], "size": f[3],
                            "data%": f[4] if len(f) > 4 else "", "pool": f[5] if len(f) > 5 else ""})
                pct = float(f[4]) if len(f) > 4 and re.match(r"^[\d.]+$", f[4]) else None
                if f[2].startswith("t") and pct is not None:
                    if pct >= 95:
                        rep.add("crit", "lvm", "%s/%s" % (f[1], f[0]), "thin pool %.1f%% full" % pct)
                    elif pct >= 90:
                        rep.add("warn", "lvm", "%s/%s" % (f[1], f[0]), "thin pool %.1f%% full" % pct)
        for line in vgs_txt.splitlines():
            f = [x.strip() for x in line.split("|")]
            if len(f) >= 5 and f[0] and not f[0].startswith("WARNING"):
                vgs.append({"vg": f[0], "pvs": to_int(f[1]), "lvs": to_int(f[2]),
                            "size": f[3], "free": f[4]})
    pools = []
    for line in s.get("zpool", "").splitlines():
        f = line.split("\t") if "\t" in line else line.split()
        if len(f) < 6:
            continue
        pools.append({"pool": f[0], "size": f[1], "alloc": f[2], "free": f[3], "cap": f[4],
                      "health": f[5]})
        if f[5] != "ONLINE":
            rep.add("crit", "zfs", f[0], "pool %s" % f[5])
        cap = to_int(f[4])
        if cap is not None and cap >= 90:
            rep.add("crit", "zfs", f[0], "pool %d%% full (ZFS slows sharply past 80%%)" % cap)
        elif cap is not None and cap >= 80:
            rep.add("warn", "zfs", f[0], "pool %d%% full (keep ZFS under 80%%)" % cap)
    zst = s.get("zstatus", "").strip()
    if zst and zst not in ("all pools are healthy", "no pools available") and pools:
        rep.add("warn", "zfs", host, "zpool status -x: %s" % zst.splitlines()[0].strip())
    md = []
    for line in s.get("mdstat", "").splitlines():
        m = re.match(r"^(md\d+)\s*:\s*(\S+)\s+(\S+)?\s*(.*)$", line)
        if m:
            md.append({"array": m.group(1), "state": m.group(2), "level": m.group(3) or "",
                       "members": m.group(4).strip(), "status": ""})
            continue
        if md:
            st = re.search(r"\[([U_]+)\]", line)
            if st and not md[-1]["status"]:
                md[-1]["status"] = st.group(1)
                if "_" in st.group(1):
                    rep.add("crit", "raid", md[-1]["array"], "degraded [%s]" % st.group(1))
            prog = re.search(r"(resync|recovery|reshape|check)\s*=\s*([\d.]+%)", line)
            if prog:
                md[-1]["status"] += " %s %s" % (prog.group(1), prog.group(2))
                rep.add("info", "raid", md[-1]["array"], "%s at %s" % (prog.group(1), prog.group(2)))
    smart = []
    unreadable = []
    for line in s.get("smart", "").splitlines():
        f = line.split(None, 1)
        if not f:
            continue
        txt = f[1] if len(f) > 1 else "unknown"
        if PERM_RE.search(txt) or re.search(r"open device", txt, re.I):
            state = "needs root"
            unreadable.append(f[0])
        elif re.search(r"PASSED|: OK\b", txt):
            state = "PASSED"
        elif re.search(r"FAILED", txt):
            state = "FAILED"
            rep.add("crit", "smart", f[0], "SMART overall health FAILED — replace the disk")
        else:
            state = "unknown"
        smart.append({"device": f[0], "health": state})
    if unreadable:
        rep.add("info", "smart", ",".join(unreadable), "SMART needs root (for the human: "
                "sudo smartctl -H /dev/%s)" % unreadable[0])
    rep.section("devices", devices, a.max_items)
    rep.section("mounts", mounts, a.max_items)
    rep.section("disks", disk_rows(disks), a.max_items)
    rep.section("lvm_volumes", lvs, a.max_items)
    rep.section("lvm_groups", vgs)
    rep.section("zfs", pools)
    rep.section("md_raid", md)
    rep.section("smart", smart)
    return rep


# -------------------------------------------------------------------------------- audit
SSHD_KEYS = ("permitrootlogin", "passwordauthentication", "kbdinteractiveauthentication",
             "challengeresponseauthentication", "pubkeyauthentication", "permitemptypasswords",
             "x11forwarding", "allowtcpforwarding", "allowagentforwarding", "maxauthtries",
             "authenticationmethods", "port", "listenaddress", "allowusers", "allowgroups")
AUDIT = [
    ("sshd", "S=$(command -v sshd 2>/dev/null || echo /usr/sbin/sshd); "
             "[ -x \"$S\" ] && \"$S\" -T 2>/dev/null | grep -iE '^(%s) '" % "|".join(SSHD_KEYS)),
    ("sshdcfg", "grep -hiE '^[[:space:]]*(%s)[[:space:]=]' /etc/ssh/sshd_config.d/*.conf "
                "/etc/ssh/sshd_config" % "|".join(SSHD_KEYS)),
    ("ports", "ss -Htuln 2>/dev/null || ss -tuln | tail -n +2"),
    ("sudo",
     "echo \"uid=$(id -u)\"\n"
     "echo \"sudoers-mode=$(stat -c '%a %U:%G' /etc/sudoers 2>/dev/null)\"\n"
     "if [ -r /etc/sudoers ]; then echo sudoers-readable=yes; echo \"nopasswd=$(cat /etc/sudoers "
     "/etc/sudoers.d/* 2>/dev/null | grep -v '^[[:space:]]*#' | grep -c NOPASSWD)\"; "
     "else echo sudoers-readable=no; fi\n"
     "if [ -r /etc/sudoers.d ] && [ -x /etc/sudoers.d ]; then echo \"sudoers.d=$(ls -A "
     "/etc/sudoers.d | wc -l)\"; else echo sudoers.d=unreadable; fi\n"
     "echo \"admin-groups=$(id -Gn | tr ' ' '\\n' | grep -xE 'sudo|wheel|admin' | tr '\\n' ' ')\""),
    ("updates",
     "if command -v apt >/dev/null; then echo pm=apt; echo \"upgradable=$(apt list --upgradable "
     "2>/dev/null | grep -c upgradable)\"; echo \"security=$(apt list --upgradable 2>/dev/null "
     "| grep -c -- '-security')\"; "
     "elif command -v dnf >/dev/null; then echo pm=dnf; echo \"upgradable=$(dnf -q --cacheonly "
     "check-update 2>/dev/null | grep -cE '^[[:alnum:]]')\"; echo \"security=$(dnf -q --cacheonly "
     "updateinfo list --security 2>/dev/null | grep -c .)\"; "
     "elif command -v nixos-version >/dev/null; then echo pm=nix; fi"),
    ("auto",
     "test -f /etc/apt/apt.conf.d/20auto-upgrades && grep -h 'Unattended-Upgrade' "
     "/etc/apt/apt.conf.d/20auto-upgrades | sed 's/^/apt-conf: /'\n"
     "for u in unattended-upgrades.service apt-daily-upgrade.timer dnf-automatic.timer "
     "dnf-automatic-install.timer nixos-upgrade.timer; do echo \"$u=$(systemctl is-enabled $u "
     "2>/dev/null)\"; done\n"
     "test -f /etc/dnf/automatic.conf && grep -hE '^[[:space:]]*apply_updates' "
     "/etc/dnf/automatic.conf | sed 's/^/dnf-conf: /'"),
    ("suid", "find /usr -xdev -perm -4000 -type f 2>/dev/null | wc -l"),
    ("ww", "find /etc -xdev -perm -0002 -type f 2>/dev/null | head -50"),
]
RISKY_PORTS = {"21": "ftp", "23": "telnet", "111": "rpcbind", "2375": "docker API (no TLS)",
               "6379": "redis", "9200": "elasticsearch", "11211": "memcached",
               "27017": "mongodb"}


def sshd_settings(s):
    if s.get("sshd", "").strip():
        src, txt = "sshd -T", s["sshd"]
    elif s.get("sshdcfg", "").strip():
        src, txt = "config files (approximate: first value wins, Match blocks ignored)", s["sshdcfg"]
    else:
        return "", {}
    d = {}
    for line in txt.splitlines():
        k, vals = _cfg_words(line)
        if k in SSHD_KEYS and k not in d:
            d[k] = " ".join(vals)
    return src, d


def cmd_audit(a):
    rep, s, _ = remote_report("audit", a.host, AUDIT, a)
    host = a.host
    src, sshd = sshd_settings(s)
    low = {k: v.lower() for k, v in sshd.items()}
    if not src:
        rep.add("info", "sshd", host, "sshd settings not readable (for the human: sudo sshd -T)")
    if low.get("permitrootlogin") == "yes":
        rep.add("crit", "sshd", "PermitRootLogin", "root may log in (any method) — set "
                "`PermitRootLogin no` in the host's sshd config (infra repo)")
    elif low.get("permitrootlogin") in ("prohibit-password", "without-password"):
        rep.add("info", "sshd", "PermitRootLogin", "root may log in with a key — consider `no`")
    if low.get("permitemptypasswords") == "yes":
        rep.add("crit", "sshd", "PermitEmptyPasswords", "empty passwords accepted")
    if low.get("passwordauthentication") == "yes":
        rep.add("warn", "sshd", "PasswordAuthentication", "password logins enabled — keys only")
    if low.get("kbdinteractiveauthentication") == "yes":
        rep.add("warn", "sshd", "KbdInteractiveAuthentication",
                "keyboard-interactive enabled (password prompts through PAM)")
    if low.get("x11forwarding") == "yes":
        rep.add("info", "sshd", "X11Forwarding", "X11 forwarding enabled on a server")
    mat = to_int(low.get("maxauthtries"))
    if mat is not None and mat > 6:
        rep.add("info", "sshd", "MaxAuthTries", "MaxAuthTries %d (default 6)" % mat)
    ports, wild = [], []
    for line in s.get("ports", "").splitlines():
        f = line.split()
        if len(f) < 5:
            continue
        proto, local = f[0], f[4]
        addr, _, port = local.rpartition(":")
        addr = addr.split("%")[0]
        if addr.startswith("127.") or addr in ("[::1]", "::1"):
            scope = "loopback"
        elif addr in ("0.0.0.0", "*", "[::]", "::"):
            scope = "all"
        else:
            scope = "address"
        ports.append({"proto": proto, "address": addr, "port": port, "scope": scope})
        if scope == "all" and port not in [p for _, p in wild]:
            wild.append((proto, port))
    for proto, port in wild:
        if port in RISKY_PORTS:
            rep.add("warn", "port", "%s/%s" % (proto, port), "%s listening on all interfaces"
                    % RISKY_PORTS[port])
    others = sorted({p for _, p in wild if p not in RISKY_PORTS and p != "22"}, key=lambda x: to_int(x, 0))
    if others:
        rep.add("info", "port", host, "listening on all interfaces: %s — confirm each is meant "
                "to be reachable" % ", ".join(others))
    sk = kv_lines(s.get("sudo", ""))
    uid = sk.get("uid", "")
    if uid == "0":
        rep.add("warn", "login", host, "audit ran as root — give agents an unprivileged alias")
    elif sk.get("sudoers-readable") == "yes":
        rep.add("warn", "sudoers", "/etc/sudoers", "readable by this non-root login (mode %s; "
                "only root should read it)" % (sk.get("sudoers-mode") or "?"))
    nop = to_int(sk.get("nopasswd"))
    if nop:
        rep.add("info", "sudoers", host, "%d NOPASSWD rule(s)" % nop)
    sudo = {"login_uid": uid, "sudoers_mode": sk.get("sudoers-mode", ""),
            "sudoers_readable": sk.get("sudoers-readable", ""),
            "sudoers_d_entries": sk.get("sudoers.d", ""),
            "nopasswd_rules": nop if sk.get("sudoers-readable") == "yes" else "not readable",
            "login_admin_groups": sk.get("admin-groups", "").split()}
    uk = kv_lines(s.get("updates", ""))
    pm = uk.get("pm", "")
    upd = {"package_manager": pm, "upgradable": to_int(uk.get("upgradable")),
           "security": to_int(uk.get("security"))}
    if upd["security"]:
        rep.add("warn", "updates", host, "%d security update(s) pending" % upd["security"])
    elif upd["upgradable"]:
        rep.add("info", "updates", host, "%d update(s) pending" % upd["upgradable"])
    au_lines = s.get("auto", "").splitlines()
    ak = kv_lines("\n".join(l for l in au_lines if ": " not in l))
    enabled = sorted(k for k, v in ak.items() if v in ("enabled", "static", "alias"))
    apt_conf = " ".join(l[len("apt-conf: "):] for l in au_lines if l.startswith("apt-conf: "))
    dnf_conf = " ".join(l[len("dnf-conf: "):] for l in au_lines if l.startswith("dnf-conf: "))
    auto = {"enabled_units": enabled}
    if pm == "apt":
        on = bool(re.search(r'Unattended-Upgrade\s+"1"', apt_conf))
        auto.update({"apt_unattended_upgrade": apt_conf or "not configured", "on": on})
        if not on:
            rep.add("warn", "updates", host, "unattended-upgrades not on (APT::Periodic::"
                    "Unattended-Upgrade \"1\" in 20auto-upgrades)")
    elif pm == "dnf":
        on = any(u.startswith("dnf-automatic") for u in enabled)
        auto.update({"dnf_automatic": dnf_conf or "not configured", "on": on})
        if not on:
            rep.add("warn", "updates", host, "dnf-automatic timer not enabled")
    elif pm == "nix":
        on = "nixos-upgrade.timer" in enabled
        auto["on"] = on
        if not on:
            rep.add("info", "updates", host, "system.autoUpgrade not enabled (nixos-upgrade.timer)")
    suid = to_int(s.get("suid"))
    ww = [l for l in s.get("ww", "").splitlines() if l.strip()]
    if ww:
        rep.add("warn", "perms", "/etc", "%d world-writable file(s): %s" % (
            len(ww), ", ".join(ww[:5]) + (" …" if len(ww) > 5 else "")))
    if suid is not None:
        rep.add("info", "perms", "/usr", "%d SUID file(s) — compare with a known-good host "
                "of the same release" % suid)
    rep.section("sshd", dict(sshd, source=src or "not readable") if sshd else {"source": src or "not readable"})
    rep.section("listening", ports, a.max_items)
    rep.section("sudo", sudo)
    rep.section("updates", upd)
    rep.section("auto_updates", auto)
    rep.section("files", {"suid_in_usr": suid, "world_writable_in_etc": ww})
    return rep


# ------------------------------------------------------------------------------- redact
def cmd_redact(a):
    raw = sys.stdin.read()
    try:
        obj = json.loads(raw)
    except ValueError:
        sys.stdout.write(redact_text(raw, _extra_re()))
        if raw and not raw.endswith("\n"):
            sys.stdout.write("\n")
        sys.exit(0)
    sys.stdout.write(json.dumps(redact_obj(obj, _extra_re()), indent=2 if a.json else None) + "\n")
    sys.exit(0)


# ------------------------------------------------------------------------------ parsing
class _Parser(argparse.ArgumentParser):
    def error(self, message):
        die("lx %s: %s\n\nRun `lx` with no arguments for the command list."
            % (self.prog.split()[-1] if " " in self.prog else "", message), 1)


def common_parser():
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--json", action="store_true", help="JSON output (default: Markdown)")
    p.add_argument("--timeout", type=int, default=120,
                   help="whole remote call in seconds (default 120; connect timeout is "
                        "LINUX_SSH_TIMEOUT=%d)" % SSH_TIMEOUT)
    p.add_argument("--max-items", type=int, default=50, dest="max_items")
    p.add_argument("--max-bytes", type=int, default=200000, dest="max_bytes")
    return p


def build_parser():
    common = common_parser()
    top = _Parser(prog="lx", description="Read-only Linux host client", add_help=False)
    subs = top.add_subparsers(dest="cmd")

    def sub(name, fn, help_, host=True):
        p = subs.add_parser(name, parents=[common], help=help_)
        if host:
            p.add_argument("host", metavar="HOST", help="a Host alias from ~/.ssh/config")
        p.set_defaults(fn=fn)
        return p

    sub("hosts", cmd_hosts, "Host aliases from ~/.ssh/config", host=False)
    sub("check", cmd_check, "reachability and key auth")
    sub("facts", cmd_facts, "os, kernel, cpu, memory, virtualisation")
    sub("health", cmd_health, "failed units, load, disk, memory, reboot, time sync")
    lg = sub("logs", cmd_logs, "bounded, redacted journalctl")
    lg.add_argument("--since", default="1h", help="Ns/Nm/Nh/Nd/Nw, today, yesterday or a date "
                                                  "(default 1h)")
    lg.add_argument("--limit", type=int, default=200, help="max lines (default 200, max %d)" % MAX_LIMIT)
    lg.add_argument("--unit", help="systemd unit")
    lg.add_argument("--priority", help="emerg..debug or 0..7, or a range like warning..emerg")
    sub("net", cmd_net, "addresses, links, routes, renderer, firewall, DNS")
    sub("storage", cmd_storage, "block devices, mounts, LVM, ZFS, RAID, SMART")
    sub("audit", cmd_audit, "sshd, listening sockets, sudoers shape, updates, file modes")
    sub("redact", cmd_redact, "stdin -> redacted stdout", host=False)
    return top, list(subs.choices)


GLOBAL_FLAGS = ("--json",)


def main():
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        sys.exit(1)
    if argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        sys.exit(0)
    if argv[0] in ("--version", "-V", "version"):
        print("lx %s" % __version__)
        sys.exit(0)
    lead = []
    while argv and argv[0] in GLOBAL_FLAGS:     # `lx --json facts h` == `lx facts h --json`
        lead.append(argv.pop(0))
    top, names = build_parser()
    if not argv or argv[0] not in names:
        die("Unknown command %r. Commands: %s\n\nRun `lx` with no arguments for the full usage."
            % (argv[0] if argv else "", ", ".join(names)), 1)
    a = top.parse_args(argv + lead)
    try:
        rep = a.fn(a)
    except AccessError as e:
        die(str(e), 2)
    except BrokenPipeError:
        sys.exit(0)
    rep.emit("json" if a.json else "md", a.max_bytes)
    sys.exit(2 if getattr(rep, "access_failed", False) else rep.exit_code())


if __name__ == "__main__":
    main()
