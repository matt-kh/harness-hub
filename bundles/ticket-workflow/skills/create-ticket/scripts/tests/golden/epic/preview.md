## Ticket preview

| field | value |
|---|---|
| Project | PROJ |
| Type | Epic |
| Summary | Dataset export and audit tooling |
| Type of Problem | — |
| Category | — |
| Priority | Medium (default) |
| Assignee | jdoe (default) |
| Affects Version | — |
| Fix Version | — |
| Components | — |
| Labels | agent-drafted |
| Attachments (after create) | — |

### Description (Jira wiki)
```
*Goal:* Programs need auditable exports of datasets, manifests and labels. Audit requests are handled manually today.

*Scope:*
 # Manifest export (CSV)
 # Label export (COCO, YOLO)
 # Audit log of exports

*Child work (to be split into tickets):*
 # CSV manifest export
 # Label export formats
 # Export audit log

*Out of scope:*
 # Third-party storage connectors

----
Drafted by Claude Code (create-ticket) for jdoe on 2026-09-09 — review and edit freely.
```

### Command (run verbatim on Create)
```bash
jira create PROJ Epic 'Dataset export and audit tooling' --description "$(cat OUT/description.txt)" --field 'labels=["agent-drafted"]' --field 'priority={"name":"Medium"}' --field 'assignee={"name":"jdoe"}' --field 'customfield_21205=Dataset export'
```
