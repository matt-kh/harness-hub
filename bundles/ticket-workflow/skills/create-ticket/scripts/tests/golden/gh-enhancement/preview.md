## Issue preview

| field | value |
|---|---|
| Repository | jdoe/dotlab |
| Class | enhancement |
| Title | Add a --dry-run flag to the sync command |
| Labels | agent-drafted, enhancement, documentation |
| Assignee | @me (default) |
| Milestone | v0.3 |
| Attachments (web UI, after create) | — |

### Body (GitHub Markdown)
```markdown
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
```

### Command (run verbatim on Create)
```bash
gh issue create -R jdoe/dotlab -t 'Add a --dry-run flag to the sync command' -F OUT/body.md -l agent-drafted,enhancement,documentation -a @me -m v0.3
```
