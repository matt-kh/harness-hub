"""Small shared helpers: paths, hashing, atomic writes, subprocess with timeout, output."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional, Sequence, Tuple


class HarnessError(Exception):
    """A user-facing error. ``code`` becomes the process exit status."""

    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.code = code


# ----------------------------------------------------------------- locations

def hub_home() -> str:
    """HARNESS_HOME, defaulting to the directory that contains ``bin/harness``."""
    env = os.environ.get("HARNESS_HOME")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def user_home() -> str:
    return os.path.expanduser("~")


def expand(path: str) -> str:
    """Expand a leading ``~`` against ``$HOME`` and return an absolute path."""
    return os.path.abspath(os.path.expanduser(path))


def tilde(path: str) -> str:
    """Inverse of :func:`expand` for display and state keys (``/home/u/x`` -> ``~/x``)."""
    home = user_home().rstrip("/")
    if path == home:
        return "~"
    if path.startswith(home + "/"):
        return "~" + path[len(home):]
    return path


def state_dir() -> str:
    base = os.environ.get("XDG_STATE_HOME") or os.path.join(user_home(), ".local", "state")
    return os.path.join(base, "harness")


def data_dir() -> str:
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(user_home(), ".local", "share")
    return os.path.join(base, "harness")


def bin_dir() -> str:
    return os.path.join(user_home(), ".local", "bin")


# ----------------------------------------------------------------- hashing / io

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str) -> Optional[str]:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except (OSError, IsADirectoryError):
        return None


def read_bytes(path: str) -> Optional[bytes]:
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except (FileNotFoundError, IsADirectoryError, NotADirectoryError):
        return None


def read_text(path: str) -> Optional[str]:
    data = read_bytes(path)
    return None if data is None else data.decode("utf-8")


def atomic_write(path: str, data: bytes, mode: Optional[int] = None) -> None:
    """Write via a temp file in the same directory + rename (never a half-written file).

    ``mode`` defaults to the existing file's permission bits, else 0644.
    """
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    if mode is None:
        try:
            mode = os.stat(path).st_mode & 0o7777
        except OSError:
            mode = 0o644
    fd, tmp = tempfile.mkstemp(prefix=".harness-", dir=directory)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_symlink(target: str, path: str) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    tmp = os.path.join(directory, ".harness-link-%d" % os.getpid())
    try:
        os.unlink(tmp)
    except OSError:
        pass
    os.symlink(target, tmp)
    os.replace(tmp, path)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def dump_json(value: Any, sort_keys: bool = False) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=sort_keys, ensure_ascii=False) + "\n").encode("utf-8")


# ----------------------------------------------------------------- versions

_VER_RE = re.compile(r"(\d+(?:\.\d+)*)")


def parse_version(text: str) -> Tuple[int, ...]:
    m = _VER_RE.search(text or "")
    if not m:
        return ()
    return tuple(int(p) for p in m.group(1).split("."))


def version_ge(have: str, want: str) -> bool:
    a, b = parse_version(have), parse_version(want)
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) >= b + (0,) * (n - len(b))


# ----------------------------------------------------------------- subprocess

def run_shell(cmd: str, timeout: float = 10.0, cwd: Optional[str] = None,
              env: Optional[Dict[str, str]] = None) -> Tuple[int, str, str]:
    """Run ``bash -c CMD`` with a timeout (portable replacement for GNU ``timeout``).

    Returns ``(rc, stdout, stderr)``; rc 124 on timeout, 127 when bash is missing.
    stdin is /dev/null so a check can never block on a prompt.
    """
    return run_argv(["bash", "-c", cmd], timeout=timeout, cwd=cwd, env=env)


def run_argv(argv: Sequence[str], timeout: float = 10.0, cwd: Optional[str] = None,
             env: Optional[Dict[str, str]] = None) -> Tuple[int, str, str]:
    try:
        proc = subprocess.Popen(
            list(argv), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, cwd=cwd, env=env, start_new_session=True,
        )
    except FileNotFoundError:
        return 127, "", "%s: not found" % argv[0]
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, 9)
        except OSError:
            proc.kill()
        proc.communicate()
        return 124, "", "timed out after %ss" % timeout
    return proc.returncode, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")


_SECRETISH = re.compile(r"token|secret|password|bearer|authorization", re.I)


def first_line(text: str, width: int = 100) -> str:
    """First non-empty output line with anything secret-looking dropped (doctor summaries)."""
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or _SECRETISH.search(line):
            continue
        return line[:width]
    return ""


# ----------------------------------------------------------------- output

def color_enabled(stream=None) -> bool:
    stream = stream or sys.stdout
    return (not os.environ.get("NO_COLOR")) and hasattr(stream, "isatty") and stream.isatty()


_COLORS = {"PASS": "32", "OK": "32", "WARN": "33", "FAIL": "31", "SKIP": "90",
           "create": "32", "update": "33", "conflict": "31", "orphan": "35", "skip": "90"}


def paint(word: str, text: Optional[str] = None) -> str:
    text = word if text is None else text
    code = _COLORS.get(word)
    if code and color_enabled():
        return "\033[%sm%s\033[0m" % (code, text)
    return text


def eprint(*args: Any) -> None:
    print(*args, file=sys.stderr)


def which(name: str) -> Optional[str]:
    from shutil import which as _which

    return _which(name)


def rel_to(path: str, base: str) -> str:
    try:
        rel = os.path.relpath(path, base)
    except ValueError:
        return path
    return path if rel.startswith("..") else rel


def list_files(root: str) -> List[str]:
    """Every regular file (and symlink) below ``root``, sorted, relative to ``root``."""
    out: List[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in ("__pycache__", ".git"))
        for fn in filenames:
            if fn.endswith((".pyc", ".pyo")) or fn == ".DS_Store":
                continue
            out.append(os.path.relpath(os.path.join(dirpath, fn), root))
    return sorted(out)
