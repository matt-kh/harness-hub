# Proposal preview: scm-001

- tracker: GitHub Issues, octocat/hub
- title: Lesson scm-001: pushing a branch named after the ticket
- label: agent-drafted
- command (in create.sh, never run by the harness): `gh issue create -R octocat/hub -t 'Lesson scm-001: pushing a branch named after the ticket' -F body.md -l 'agent-drafted'`
- repository names: replaced by <repo>

---

Lesson `scm-001` from a private lessons library, drafted by `harness lessons propose`. It is an agent-written observation backed by the evidence below; a human decides whether the guide and sensor change.

- scope: domain, domain: scm, status: confirmed
- guide: `core/rules/10-core`
- sensor: `beta/guard.d/15-beta`
- bundles: `beta`
- counters: uses 0, helped 0, recurred 0 (0 backed by the guard journal)

## Situation

pushing a branch named after the ticket

## Lesson

name branches by topic

## Evidence

- journal: 2026-10-01T09:12:03Z claude s1 guard-deny guard_section_beta_15_beta:3 3f9c1a7e02bd <repo>
- user: "not in <repo> again"

## Candidate edit

```diff
diff --git a/bundles/core/rules/00-conventions.md b/bundles/core/rules/00-conventions.md
--- a/bundles/core/rules/00-conventions.md
+++ b/bundles/core/rules/00-conventions.md
@@ -1,2 +1,3 @@
 # Conventions
+- Check a key's format with its public half (`ssh-keygen -l -f FILE.pub`), never the private file.
 Precedence first.
```

## Validation

not validated (`harness lessons validate scm-001`)

Paired guide and sensor: the change lands as one PR with its guard rows or test, and a human merges it.
