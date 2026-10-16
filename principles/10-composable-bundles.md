# Principle 10 — Composable bundles

Part of [PRINCIPLES.md](../PRINCIPLES.md). Read this before copying a helper into a second
script, adding a `depends_on`, calling another bundle's tool, or creating `skill-fragments/`.

## Statement

> Components in a bundle (skills, hooks, guards, etc) should be as shareable and composable
> as possible to be shared with other bundles.

- A component is written once, in the bundle that owns its domain, and reached by others
  through a declared **seam**: a dependency, a CLI on `PATH`, a guard section slot, an
  inlined marked block.
- Rendered artefacts live in provider homes and cannot import from `bundles/core/lib`
  ([principle 1](01-lightweight.md), [principle 4](04-install-as-a-platform.md)), so sharing
  at render time means copies that are **generated and checked**, never hand-maintained.
- Composition is checkable: the manifest declares what a bundle needs; a build or test proves
  the copies are identical and the sections stand alone.

## Rationale

- Every bundle solves the same small problems: a timeout wrapper, reading `build/config.json`,
  reading `.harness.toml`, stubbing a tool for tests. Two hand-written versions drift, and
  the drift shows up as a guard that behaves differently from a skill.
- Bundles are selected per developer (`profiles/`, `hub.bundles`). A bundle that reaches into
  another by path breaks when the other is absent; one that reaches through `depends_on` and
  a CLI degrades honestly ("add the `github` bundle").
- Org platform instances ([principle 3](03-platform-for-everyone.md)) add bundles on top; they
  can only build on what is exposed through seams, not on private internals.
- Reuse is what keeps the dependency list short ([principle 1](01-lightweight.md)): one
  `hn_timeout`, not five.

## What it means in this repo

- **Dependencies are declared, resolved and ordered.** `depends_on`, `recommends`,
  `conflicts_with` and `any_of` in `bundle.toml`
  ([ARCHITECTURE §3](../ARCHITECTURE.md#3-bundles-bundlesname)) are resolved deterministically
  by `lib/harness/manifest.py`; the `profile-sane` lint rule keeps every profile resolvable.
- **Clients are CLIs, not API calls.** `ticket-workflow` reaches Jira, GitHub and GitLab only
  through the `jira`, `gh` and `glab` CLIs of the `jira`, `github` and `gitlab` bundles; when
  one is missing the skill stops and names the bundle ("never fall back to raw API calls",
  `work-ticket/SKILL.md`, `create-ticket/SKILL.md`). Fakes in `tests/fakes/bin/` stand in for
  every CLI in tests.
- **One canonical source, inlined copies, one check.** `bundles/core/lib/compat.sh`,
  `harness_config.{py,sh}`, `harness_repo.{py,sh}` and `redact.py` each hold a block between
  `# >>> NAME` and `# <<< NAME` markers (`hn_timeout`, `harness_config`, `hcfg`, `hrepo`,
  `harness_repo`, `redact`). The copies in the guard engine and in the skill scripts are rewritten by
  `bundles/core/lib/sync_inline.py` and verified by `sync_inline.py --check` from
  `bundles/core/tests/run.sh`. Adding a shared helper means adding a block to `SOURCES` in
  that script, nothing else.
- **Shell and python twins give the same answers.** `harness_repo.sh` and `harness_repo.py`
  implement the same TOML subset and the core bundle test compares them; `hn_sha256` has a
  python twin checked by `tests/unit/test_pack.py`.
- **Guard sections compose by prefix.** Each bundle contributes `guard.d/NN-*.sh`; `build.sh`
  concatenates in basename order; the shared `t`, `tc`, `tr` and `g` helpers and the stubs in
  `bundles/core/guard/tests/stubs` are the only test API. Every bundle's `tests/run.sh` builds
  core plus that bundle only, which proves its sections depend on nothing else.
- **Providers share one fixture runner.** `providers/_shared/run-shim-tests.sh` drives every
  shim from `NAME.in.json` and `NAME.out.json` pairs.
- **Skill fragments are the org-overlay seam.** `skill-fragments/<skill>/` overlays files into
  a skill another bundle owns. Public bundles do not ship them (`fragments-target` warns),
  because a fragment is silently not rendered when its bundle is inactive; they belong in
  `local/bundles/<org>/` ([roadmap](../docs/roadmap.md)). Public bundles keep SCM- or
  tracker-specific text as references inside the owning skill.
- **Within a skill, shared logic is a sourced library; across skills it is a core block.**
  `work-ticket/scripts/lib/repo-facts.sh` is sourced by the three preflight scripts of that
  skill. Logic two skills or two bundles need becomes a `bundles/core/lib` block.

## What it rules out

- A second hand-written copy of anything that has a canonical block, or should have one. The
  standing example: the Jira `whoami` plus `mypermissions` query in
  `create-ticket/scripts/create-facts.sh` and `work-ticket/scripts/jira-facts.sh`.
- Importing or sourcing across bundle roots (`bundles/a/…` reading `bundles/b/lib/…`), or a
  rendered skill importing from `lib/harness/`.
- Calling another bundle's tracker or SCM API directly instead of its CLI; depending on a
  bundle without declaring it.
- Public bundles shipping `skill-fragments/`; org overlays patching a public skill in place
  instead of overlaying it.
- Seven identical `bundles/*/tests/run.sh` maintained by hand (the `tests-boilerplate` lint
  rule on the [roadmap](../docs/roadmap.md)).
- A shared helper that carries organisation or tool specifics (hostnames, project keys);
  those stay in config ([principle 3](03-platform-for-everyone.md)).

## How it is checked

| Check | Kind | Where |
|---|---|---|
| Inlined copies of the six core blocks match their canonical source | bundle test | `bundles/core/tests/run.sh` (`sync_inline.py --check`) |
| `harness_repo.sh` and `harness_repo.py` agree on fixture files | bundle test | `bundles/core/tests/run.sh` |
| Unknown names in `depends_on`, `recommends`, `conflicts_with`, `any_of`; profiles that do not resolve | lint error `manifest`, `profile-sane` | `harness lint` |
| Fragment directories target a skill some declared dependency provides; public bundles ship none | lint error and warning `fragments-target` | `harness lint` |
| Each bundle's guard sections pass their rows when built with core plus that bundle only | bundle test | `bundles/<b>/tests/run.sh` |
| Binaries a script calls are on the allow-list or declared by a bundle | lint warning `dependencies` | `harness lint` |
| Every provider shim passes the shared fixture runner | provider test | `providers/_shared/run-shim-tests.sh` |
| A known helper body (`hn_timeout() {`, `hcfg() {`, `hrepo_root() {`, …) appearing outside its `# >>> NAME` markers | check (follow-up) | `bundles/core/lib/sync_inline.py --check`, a signature list next to `SOURCES` |
| Jira facts shared: a `jira facts PROJECT` subcommand of the `jira` CLI (or one core block) used by both skills | refactor (follow-up) | `bundles/jira/skills/jira/scripts/jira.py`, `create-facts.sh`, `jira-facts.sh` |
| `bundles/*/tests/run.sh` generated from one template | lint `tests-boilerplate` (follow-up, [roadmap](../docs/roadmap.md)) | `harness lint` |
| One redactor (`redact` block) inlined into every CLI that prints logs; the `k8s` CLI carries it today | bundle test | `bundles/core/lib/redact.py`, `sync_inline.py --check` |

## Tensions and how they are resolved

- **With principle 1 (lightweight).** A shared library looks like a dependency. Resolution:
  no library. A canonical block, inlined and checked, adds no runtime footprint. This answers
  the open question in [principle 1](01-lightweight.md): python bundle CLIs stay
  self-contained files and share through `sync_inline.py` blocks.
- **With principle 3 (platform for everyone).** Organisations want to extend public skills.
  Resolution: `skill-fragments/` in private bundles is the overlay seam; public bundles keep
  provider-specific text as references in the owning skill.
- **With principle 4 (installed as a platform).** Rendered skills cannot import from the hub
  checkout. Resolution: copies at render time are acceptable only because they are generated
  and verified; a copy without markers is a defect.
- **With principle 6 (harness engineering).** Sharing sensors could couple bundles.
  Resolution: the shared part is the test API (`t`, `tc`, `tr`, `g`, the stubs, the shim
  runner); each bundle's rows still run against core plus itself alone.
- **With principle 8 (user-level by design).** A shared component yields per id and domain;
  sharing must not widen what a repository's `[owns]` lifts. Resolution: shared blocks hold
  mechanics (`hrepo_owns`), never decisions; the yield line stays in each section.
- **With principle 9 (deterministic by construction).** Copying by hand is exactly the
  variation principle 9 forbids. Resolution: the two reinforce each other; a shared block is
  the reproducible output of `sync_inline.py`.

## Examples

Compliant:

- Adding `.harness.toml` support once in `harness_repo.sh` and `harness_repo.py`, inlining
  the `hrepo` block into the guard engine and the skill scripts, and letting
  `sync_inline.py --check` prove they match.
- `create-ticket` on a github.com clone using `gh` from the `github` bundle and stopping with
  "add the `github` bundle" when it is absent.

Non-compliant:

- A new bundle's preflight pasting the Jira permission query from `jira-facts.sh` instead of
  calling a `jira` subcommand or a shared block.
- A public bundle adding `skill-fragments/work-ticket/references/ci.md` so the text appears
  only when that bundle is active.

## Open questions

- Whether facts gathering becomes CLI subcommands (`jira facts PROJECT`, and the GitHub
  equivalent in the `github` bundle) or core blocks. Subcommands keep the logic testable in
  the owning bundle's suite (proposed default).
- Whether `sync_inline.py` should move under `lib/harness/` as `harness sync-inline` so the
  check appears in `harness lint`, or stay a core bundle tool (default: stay; it is bundle
  code, not engine code).
- The scaffolder for `bundles/*/tests/run.sh` (`tests-boilerplate`): a template file in
  `bundles/core/tests/` or generated by `harness` (the roadmap decides).
