## Ticket preview

| field | value |
|---|---|
| Project | PROJ |
| Type | CR |
| Summary | Filter key is overwritten when editing a filter on Browse Images |
| Type of Problem | Bug Fix |
| Category | — |
| Priority | Medium (default) |
| Assignee | jdoe (default) |
| Affects Version | 1.12.0 |
| Fix Version | — |
| Components | Web-UI |
| Labels | agent-drafted |
| Attachments (after create) | — |

### Description (Jira wiki)
```
Steps to reproduce:
Step 1: Open Browse Images and create a filter with key `lot`
Step 2: Click Edit on the filter and change the value only
Step 3: Save
Actual Output: The filter key is replaced by the value text.
Expected Output: The key stays `lot`; only the value changes.

*Affected Region:* Browse Images > filter editor
*Environment / Version:* Chrome 129, on-prem, found in 1.12.0
*Evidence:* [https://gitlab.example.com/shop/shop-ui/-/issues/12]
*Related:* PROJ-1280

----
Drafted by Claude Code (create-ticket) for jdoe on 2026-09-09 — review and edit freely.
```

### Command (run verbatim on Create)
```bash
jira create PROJ CR 'Filter key is overwritten when editing a filter on Browse Images' --description "$(cat OUT/description.txt)" --field 'labels=["agent-drafted"]' --field 'priority={"name":"Medium"}' --field 'assignee={"name":"jdoe"}' --field 'customfield_20103={"value":"Bug Fix"}' --field 'versions=[{"name":"1.12.0"}]' --field 'components=[{"name":"Web-UI"}]' --field 'customfield_20000=Editing an existing filter on Browse Images replaces its key with the new value instead of keeping the original key.'
```
