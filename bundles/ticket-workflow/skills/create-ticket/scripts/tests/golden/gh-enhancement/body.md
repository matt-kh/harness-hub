**Context:** Sync changes files immediately, so users cannot review what it will do. New machines are set up rarely and mistakes are costly.

**Goal:** Preview every change sync would make without touching the filesystem.

**Proposed change:** Add `--dry-run` to `dotlab sync` that prints the planned link/copy/remove actions and exits 0.

**Acceptance criteria**
- [ ] `dotlab sync --dry-run` writes nothing
- [ ] Output lists every planned action
- [ ] Exit code is 0 when the plan is valid

**Out of scope**
- Interactive confirmation mode

**Related:** #7

---
_Drafted by Claude Code (create-ticket) for jdoe on 2026-09-24 — review and edit freely._
