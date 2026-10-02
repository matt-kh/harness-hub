## What and why

<!-- One paragraph. Mention the issue as "#N"; never "Closes/Fixes/Resolves #N" (see CONTRIBUTING). -->

## Principle(s) served

<!-- Numbers from PRINCIPLES.md (e.g. "1, 6"), or "neutral". If this PR conflicts with a principle, say so and link the proposed principle change. -->

## Changes

<!-- Behaviour-level summary; which bundles / providers / engine commands are affected. -->

## Checklist

- [ ] `make test` passes (guard rows, engine unit tests, bundle tests)
- [ ] `make lint` passes (shellcheck, `bash -n`, `harness lint`, link check)
- [ ] `make gate` passes, and nothing in this PR contains organisation or personal identifiers
      (hostnames, project keys, account ids, internal IPs, work emails) — placeholders only
- [ ] `make docs` passes (`harness docs check`); regenerated regions are committed
- [ ] New or changed guard rules have test rows; golden updates (`UPDATE=1`) were reviewed as a diff
- [ ] Guide/sensor pairing checked: new guides have a sensor and new sensors a guide, declared in the bundle's `[harness]` section; every new deny/ask reason states the alternative
- [ ] No new dependency outside python stdlib, bash, jq, git, curl (or it is a bundle's declared, optional `requires.binaries`)
- [ ] Principle changes (if any) bump `principles_version` and add a CHANGELOG "Principles" entry
- [ ] Scripts parse under bash 3.2 and avoid GNU-only tools (see CONTRIBUTING, "bash 3.2 rules")
- [ ] `CHANGELOG.md` has an entry under `[Unreleased]` (with **Migration** if a config key changed)
- [ ] Commit subjects carry no ticket keys and no closing keywords

## Manual verification

<!-- Anything you ran by hand: `harness plan` output, a provider session, doctor on macOS/WSL. -->
