# shellcheck shell=bash

# ---- Flush deferred decisions (every section has run; any deny already exited) -------
[ -z "$deferred" ] || ask "$deferred"
[ -z "$pending_allow" ] || decide allow "$pending_allow"
exit 0
