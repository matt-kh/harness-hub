## Ticket preview

| field | value |
|---|---|
| Project | PROJ |
| Type | SW Task |
| Summary | Rotate the on-prem registry TLS certificate before expiry |
| Type of Problem | — |
| Category | Software Upgrade |
| Priority | High |
| Assignee | jdoe |
| Affects Version | — |
| Fix Version | — |
| Components | — |
| Labels | agent-drafted |
| Attachments (after create) | — |

### Problem Description (this type has no description field) (Jira wiki)
```
*Context:* The on-prem registry certificate expires on 2026-10-01.

*Goal:* Registry serves a renewed certificate with no pull failures.

*Acceptance criteria:*
 # New certificate installed
 # Nodes pull images without TLS errors

----
Drafted by Claude Code (create-ticket) for jdoe on 2026-09-09 — review and edit freely.
```

### Command (run verbatim on Create)
```bash
jira create PROJ 'SW Task' 'Rotate the on-prem registry TLS certificate before expiry' --field 'labels=["agent-drafted"]' --field 'priority={"name":"High"}' --field 'assignee={"name":"jdoe"}' --field 'customfield_20205={"value":"Software Upgrade"}' --field customfield_20000="$(cat OUT/problem-description.txt)"
```
