**Steps to reproduce**
1. Run `dotlab sync` on a clean home
2. Run `dotlab sync` again
3. List `~/.config`

**Actual:** Symlinks created by the first run are gone.

**Expected:** The second run is a no-op.

**Affected region:** sync command

**Environment / version:** Ubuntu 24.04, WSL2, found in v0.2.1

**Evidence:** <https://github.com/jdoe/dotlab/actions/runs/123>

**Related:** #12

---
_Drafted by Claude Code (create-ticket) for jdoe on 2026-09-24 — review and edit freely._
