## Ticket preview

| field | value |
|---|---|
| Project | PROJ |
| Type | CR |
| Summary | [ACME] Allow exporting the dataset manifest as CSV from the dataset page |
| Type of Problem | Enhancement |
| Category | — |
| Priority | Medium (default) |
| Assignee | jdoe |
| Affects Version | — |
| Fix Version | 1.12.0 |
| Components | Web-UI, Shop-Backend |
| Labels | agent-drafted |
| Attachments (after create) | — |

### Description (Jira wiki)
```
*Context:* Users copy dataset manifests by hand into spreadsheets for audits. Audits happen weekly per program.

*Goal:* One-click CSV export of the manifest currently shown.

*Proposed change:* Add an Export CSV action on the dataset page that downloads the visible manifest with the same columns and filters.

*Acceptance criteria:*
 # Export CSV button visible on the dataset page
 # Downloaded file matches the visible rows and columns
 # Filters applied on screen are respected

*Where to test:* Dataset page; Dataset page with an active filter

*What to test:*
 # Export produces a CSV
 # Row count matches the filtered table

*Out of scope:*
 # Scheduled or emailed exports

----
Drafted by Claude Code (create-ticket) for jdoe on 2026-09-09 — review and edit freely.
```

### Command (run verbatim on Create)
```bash
jira create PROJ CR '[ACME] Allow exporting the dataset manifest as CSV from the dataset page' --description "$(cat OUT/description.txt)" --field 'labels=["agent-drafted"]' --field 'priority={"name":"Medium"}' --field 'assignee={"name":"jdoe"}' --field 'customfield_20103={"value":"Enhancement"}' --field 'fixVersions=[{"name":"1.12.0"}]' --field 'components=[{"name":"Web-UI"},{"name":"Shop-Backend"}]' --field 'customfield_20000=Users copy dataset manifests by hand into spreadsheets for audits.'
```
