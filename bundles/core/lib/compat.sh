# shellcheck shell=bash
# Portability helpers (bash 3.2 / macOS safe). Source this file; it defines functions only.
#   hn_timeout SECS CMD [ARGS...]   run CMD with a time limit (exit 124 on timeout):
#                                   timeout(1) -> gtimeout(1) (coreutils on macOS) -> python3
#   hn_realpath PATH                canonical absolute path (realpath(1) -> python3)
#   hn_sha256 FILE                  lowercase hex sha256 of FILE (sha256sum -> shasum -> python3)
# The guard engine inlines an identical copy of hn_timeout (the rendered hook is one file);
# bundles/core/tests/run.sh fails when the two copies drift.

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

hn_realpath() {  # PATH
  if command -v realpath >/dev/null 2>&1 && realpath "$1" 2>/dev/null; then return 0; fi
  python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$1"
}

# Twin: lib/harness/selfextract-header.sh carries an identical copy (tests/unit/test_pack.py checks).
hn_sha256() {  # FILE
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | awk '{print $1}'
  else python3 -c 'import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$1"
  fi
}
