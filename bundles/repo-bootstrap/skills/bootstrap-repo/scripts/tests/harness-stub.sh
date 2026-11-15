#!/usr/bin/env bash
# harness stub: `harness repo init` prints a fixed draft like the real template's [repo] block.
[ "$1 $2" = "repo init" ] || exit 2
cat <<'T'
# .harness.toml - repository-level harness declaration (harness-hub, principle 8).
[repo]
# name = "shop"
# tracker = "jira"
# project = "PROJ"   # default Jira project for /create-ticket (tracker = jira only)

[owns]
# domains = ["delivery"]
T
