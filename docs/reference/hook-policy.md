# Reference: hook policy

Every guard rule — bundle, command pattern, decision (`allow`, `ask`, `deny`) and reason — plus
the override variables a repository can set. Generated from the `# rule: <pattern> -> <decision> : <reason>`
comments in `bundles/*/guard.d/*.sh`; do not edit inside the generated region.

Decisions are evaluated section by section in numeric order (`10` k8s … `90+` private); a deny
anywhere wins over an earlier ask, and an allow never overrides a pending ask. On providers without
an ask prompt, `ask` is mapped by `[providers.<name>].ask_as`. Model and rationale:
[governance](../governance.md).

<!-- generated:begin source=bundles/*/guard.d -->
<!-- generated:end -->
