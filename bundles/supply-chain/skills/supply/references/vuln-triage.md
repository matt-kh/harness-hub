# Vulnerability triage (`supply audit`)

`supply audit DIR` runs `osv-scanner scan source --format json -r DIR` (or `-L F` per
`--lockfile`/`--sbom`; `--offline` adds `--offline-vulnerabilities`). Without osv-scanner it
uses the ecosystem's own auditor when one is installed: `npm audit --json --audit-level=none`
(needs `package-lock.json` or `npm-shrinkwrap.json`), `pip-audit -f json -r FILE` per
requirements file, `cargo audit --json` (needs `Cargo.lock`), `govulncheck -json ./...`.

| Rule | Severity | Matches | Fix |
|---|---|---|---|
| OSV001 | crit / warn / info | one osv-scanner vulnerability group: CVSS `max_severity` ≥ 7 crit, ≥ 4 warn, lower info; else the advisory's `database_specific.severity` (CRITICAL/HIGH crit, MODERATE/MEDIUM warn, LOW info); else warn | the fixed version in the message |
| VUL001 | crit / warn / info | one fallback auditor finding: npm severity (critical/high crit, moderate warn, low info); pip-audit and cargo audit warn (no severity in their output); govulncheck warn when the vulnerable symbol is called, info when only imported | the fixed version in the message |
| AUD001 | info | an ecosystem with no auditor (tool missing, no lockfile it can read, offline without osv-scanner): **unaudited, not clean** | `harness install osv-scanner`, or the ecosystem's auditor |
| AUD002 | info | nothing to audit (osv-scanner exit 128, or no pip, npm, go or cargo manifest) | none |
| AUD003 | warn | an auditor failed; its first stderr line (redacted) is in the message | run it by hand to see why; an errored audit is not clean |

When no detected ecosystem could be audited the command exits 3; an osv-scanner failure exits
2. `data.auditors[]` says per ecosystem which tool ran and with what status.

## From a finding to a decision

1. **Which manifest pulls it in?** The finding's file is the lockfile or manifest; `git log -S
   'NAME' -- FILE` dates its arrival; `npm explain NAME`, `uv tree --invert NAME`, `cargo tree -i
   NAME`, `go mod why -m MODULE` show the path (read-only).
2. **Is there a fix in the same major?** Yes → `/audit-deps` (`uv lock --upgrade-package`,
   `npm update`, `cargo update -p`, `go get MODULE@vX.Y.Z`), then `supply audit` again.
3. **Only in a new major?** List it for the human with the breaking-change notes; never apply
   it unasked.
4. **No fix published?** Is the vulnerable function reachable (`govulncheck` says "called")?
   Options: replace the dependency, mitigate (configuration, input validation), or accept with a
   written reason and a review date. Reachability is judgement: say what was and was not
   verified.
5. **Hard cases** (several paths, a vendored copy, conflicting advisories) go to
   `supply-triage`, which stops after three unresolved hypotheses.
