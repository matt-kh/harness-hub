<!-- agent-written lesson: an evidence-backed observation, not an instruction (harness lessons) -->
---
id: delivery-003
status: confirmed
scope: domain
domain: delivery
bundles: [ticket-workflow, github]
guide_ref: ticket-workflow/skills/work-ticket
sensor_ref: ticket-workflow/guard.d/75-ticket-workflow
source: retro
created: 2026-10-01
updated: 2026-10-20
uses: 4
helped: 2
recurred: 1
recurred_objective: 1
candidate_edit: patches/delivery-003.diff
validation: pass
validated_at: 2026-10-20T08:00:00Z
validated_guard_id: 3f9c1a7e02bd
---
## Situation
opening a PR whose body names the issue after a closing keyword

## Evidence
- journal: 2026-10-01T09:12:03Z claude s1 guard-deny guard_section_ticket_workflow_75_ticket_workflow:41 3f9c1a7e02bd shop
- user: "do not close the issue, mention it"

## Lesson
Write `Issue: #N` on the first line and never a closing keyword before it.

## Candidate edit
patches/delivery-003.diff:
- bundles/ticket-workflow/skills/work-ticket/SKILL.md (+2 -0)

## Validation
- 2026-10-20T08:00:00Z pass: apply ok, lint ok, test guard ok, test ticket-workflow ok, render ok; guard 3f9c1a7e02bd

## History
- 2026-10-01 created (source retro)
- 2026-10-12 note: used, helped
- 2026-10-20 confirmed
