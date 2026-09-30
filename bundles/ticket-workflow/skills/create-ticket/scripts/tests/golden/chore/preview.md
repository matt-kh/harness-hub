## Ticket preview

| field | value |
|---|---|
| Project | PROJ |
| Type | Task |
| Summary | Upgrade shop-serving base image to Python 3.12 |
| Type of Problem | — |
| Category | — |
| Priority | Low |
| Assignee | jdoe (default) |
| Affects Version | — |
| Fix Version | — |
| Components | shop-serving |
| Labels | agent-drafted |
| Attachments (after create) | — |

### Description (Jira wiki)
```
*Context:* The serving image still builds on Python 3.10, which leaves security support in 2026.

*Goal:* Serving image builds and passes CI on Python 3.12.

*Acceptance criteria:*
 # Dockerfile uses a 3.12 base image
 # CI pipeline green
 # No runtime warnings on startup

----
Drafted by Claude Code (create-ticket) for jdoe on 2026-09-09 — review and edit freely.
```

### Command (run verbatim on Create)
```bash
jira create PROJ Task 'Upgrade shop-serving base image to Python 3.12' --description "$(cat OUT/description.txt)" --field 'labels=["agent-drafted"]' --field 'priority={"name":"Low"}' --field 'assignee={"name":"jdoe"}' --field 'components=[{"name":"shop-serving"}]'
```
