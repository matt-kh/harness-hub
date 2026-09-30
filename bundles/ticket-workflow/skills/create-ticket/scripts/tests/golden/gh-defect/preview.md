## Issue preview

| field | value |
|---|---|
| Repository | jdoe/dotlab |
| Class | defect |
| Title | Sync command drops symlinked dotfiles on the second run |
| Labels | agent-drafted, bug |
| Assignee | @me (default) |
| Milestone | — |
| Attachments (web UI, after create) | — |

### Body (GitHub Markdown)
```markdown
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
```

### Command (run verbatim on Create)
```bash
gh issue create -R jdoe/dotlab -t 'Sync command drops symlinked dotfiles on the second run' -F OUT/body.md -l agent-drafted,bug -a @me
```
