# Principle 9 — Deterministic by construction

Part of [PRINCIPLES.md](../PRINCIPLES.md). Read this before adding a skill step that writes
something (a ticket body, an MR description, a facts JSON, a rendered file, a release
artifact), or a script that produces one.

## Statement

> Any deterministic process should be built with reliable determinism in mind to prevent
> unnecessary variation introduced by AI's non-determinism.

- Two kinds of output exist. A **reproducible output** is fully determined by structured
  input: a facts JSON, a ticket model, a config, a template plus values. A **judgement
  output** is not: a plan, a classification, the prose of an MR body.
- Reproducible outputs are produced by a script with goldens or unit tests, and the skill
  names that script as the only way. The model gathers the input and makes the judgement
  calls that feed it; it never re-types the artefact.
- Judgement outputs keep a fixed shape (headings, a JSON block, a commit-subject form) that a
  script, a schema or a guard row checks. The shape is the deterministic part.

## Rationale

- A model asked to "write the ticket in house style" produces a different artefact every run;
  a script fed the same input produces the same bytes. Variation that carries no information
  is cost: reviewers re-read it, diffs are noise, and goldens cannot exist.
- Determinism is what makes a check cheap ([principle 6](06-harness-engineering.md):
  computational sensors run on every change). Only a scripted output can have a golden, and
  only a golden turns a review into a diff ([CONTRIBUTING](../CONTRIBUTING.md#guard-tests-and-goldens)).
- The split protects the model's strength. Judgement stays with the model; the mechanics stop
  consuming context and stop being a source of silent errors (a closing keyword, a wrong
  field id, Markdown where Jira wiki was required).
- The engine already works this way (`render`, `pack`, the guard build). This principle
  extends the same rule to what skills emit.

## What it means in this repo

- **The engine renders byte-identically.** `lib/harness/render.py` sorts every collection,
  dumps JSON with sorted keys, writes LF and no timestamps; `tests/smoke/render-determinism.sh`
  renders every provider twice and diffs; `make render-check` does the same locally.
- **Release artifacts are reproducible.** `lib/harness/pack.py` honours `SOURCE_DATE_EPOCH`
  and builds a sorted, fixed-mode tar; `tests/unit/test_pack.py` asserts the self-extract
  payload is deterministic.
- **The guard is built, not written.** `bundles/core/guard/build.sh` concatenates sections in
  basename order; `bundles/core/tests/run.sh` compares two builds with `cmp` and asserts the
  order. The hook-policy page is generated from `# rule:` comments (`lib/harness/docsgen.py`),
  never hand-typed.
- **Ticket bodies come from one script.** `create-ticket` says it in its own words:
  `scripts/render-ticket.py` is "the ONLY way the body and the create command are produced"
  (`bundles/ticket-workflow/skills/create-ticket/SKILL.md`). Goldens per ticket class live in
  `scripts/tests/golden/` and the suite is declared as a sensor in the bundle's `[harness]`
  section ("golden renders of every ticket class"). "Edit a field" re-renders; nobody patches
  the text.
- **Facts are one JSON object, read-only.** `create-facts.sh`, `jira-facts.sh`,
  `issue-facts.sh` and the `preflight.sh` dispatcher each print exactly one JSON object; the
  model reads fields, never parses prose. The `k8s` CLI's goldens
  (`bundles/k8s/skills/k8s/scripts/tests/golden/`) run against stubbed `kubectl` and `helm`.
- **Judgement outputs have a fixed shape.** The decomposition is "one fenced JSON block, saved
  verbatim" (`work-ticket/references/decomposition.md`); commit subjects, branch names and
  sub-branch names follow a form the ticket-workflow guard section 75 checks with test rows;
  MR descriptions are read back and grepped for closing keywords
  (`work-ticket/references/mr-description.md`).
- **Templates take the repository's shape as input.** When preflight finds an MR or PR
  template (`preflight.mr_template`), its headings are the input of the description, never a
  hub house style imposed over them ([principle 8](08-user-level-by-design.md)).
- **Goldens are reviewed as diffs** and regenerated only with `UPDATE=1`
  ([CONTRIBUTING](../CONTRIBUTING.md#guard-tests-and-goldens), PR template checklist).

## What it rules out

- A skill step that says "write the description in the house style" when a renderer exists
  or could; the model composing a Jira or GitHub body, an `INSTALL.txt`, a hook-policy table
  or a "Checks" table by hand.
- A script whose output depends on the wall clock, the locale, `$PWD`, dictionary order or
  environment not passed as input, unless the test normalises it or the value is pinned
  (`SOURCE_DATE_EPOCH`).
- A `*-facts.sh` or `*-preflight.sh` that prints prose, several JSON objects, or JSON mixed
  with log lines on stdout.
- A renderer or facts script under `skills/<s>/scripts/` with no `scripts/tests/run.sh`.
  Today every shipped CLI and facts script has one.
- A judgement output with no declared shape: a free-form plan where `decomposition.md`
  requires the JSON block; a commit subject the section-75 rows would not accept.
- Regenerating goldens to make a test pass without reading the diff.

## How it is checked

| Check | Kind | Where |
|---|---|---|
| Two renders of every provider are byte-identical | smoke | `tests/smoke/render-determinism.sh`, `make render-check` |
| Guard build output identical across two runs, sections in basename order | bundle test | `bundles/core/tests/run.sh` |
| Release payload deterministic; `SOURCE_DATE_EPOCH` honoured | unit test | `tests/unit/test_pack.py` |
| Dependency order deterministic regardless of request order | unit test | `tests/unit/test_manifest.py` |
| Every ticket class renders to its golden; `create-facts.sh` emits one JSON object per fixture (Jira, GitHub, config, unreachable, unauthenticated, not installed) | skill test | `bundles/ticket-workflow/skills/create-ticket/scripts/tests/run.sh` |
| `work-ticket` preflights and facts scripts emit one JSON object under fixture-routed `gh`/`glab`/`jira` stubs; goldens per fixture repository, CI parsed with and without PyYAML; the stub log proves read-only calls | skill test | `bundles/ticket-workflow/skills/work-ticket/scripts/tests/run.sh` |
| `k8s` CLI output matches goldens against stubbed `kubectl` and `helm` | skill test | `bundles/k8s/skills/k8s/scripts/tests/run.sh` |
| `gdoc` CLI output and request shapes match goldens against fixture-routed HTTP; writes under `GDOC_DRY_RUN=1` send only GET requests | skill test | `bundles/gdoc/skills/gdoc/scripts/tests/run.sh`, driver `tests/fakes/http_fixture.py` |
| `jira` CLI output and request shapes match goldens against fixture-routed HTTP (reads, 401/403/404/500/unreachable, upload); writes under `JIRA_DRY_RUN=1` send only GET requests and their bodies are asserted (label `update` verb, transition id, outward link side) | skill test | `bundles/jira/skills/jira/scripts/tests/run.sh`, driver `tests/fakes/http_fixture.py` |
| `stable` bundle skills and CLIs have a `tests/run.sh`; `coverage_note` admits no missing suite | lint warning `stability` | `harness lint` |
| Commit subject, branch name and sub-branch forms | guard rows | `bundles/ticket-workflow/guard.d/75-*.sh`, `guard.d/tests.sh` |
| README facts from manifests and PRINCIPLES.md (bundles, providers, principle count, core binaries) are rendered, never typed | docs | `harness docs check`, `tests/unit/test_docsgen.py` |
| Golden updates reviewed as a diff | review | PR template, CONTRIBUTING "Guard tests and goldens" |
| `beta` bundles also need a suite per skill and CLI (CONTRIBUTING "Stability levels" already says so) | lint warning (follow-up) | `lib/harness/lint.py`, rule `stability` |
| Decomposition JSON validated against its declared shape before sub-tickets are created | script with fixtures (follow-up) | `work-ticket/scripts/` |
| MR/PR description skeleton (headings, "Checks", "Stack", "Agent notes") rendered from preflight, decomposition and stack JSON; the model fills only the prose slots | script with goldens (follow-up) | `work-ticket/scripts/` |

## Tensions and how they are resolved

- **With principle 1 (lightweight).** Every renderer is more code. Resolution: renderers are
  stdlib python or bash, goldens are data, one renderer per artefact, no templating engine.
- **With principle 2 (developer-first).** A developer wants to change a rendered body.
  Resolution: the change goes into the input ("Edit a field" re-renders), never into the
  artefact after rendering; the developer's own text outside managed blocks is never touched.
- **With principle 6 (harness engineering).** Goldens are sensors written by the agent that
  is being sensed. Resolution: goldens are reviewed as diffs and regenerated only with
  `UPDATE=1`; the renderer's fixtures are the specification.
- **With principle 8 (user-level by design).** A repository's own MR template or ticket
  conventions win. Resolution: the renderer takes the repository's template as input and the
  skill yields wholesale when the repository owns the workflow; a script never hardcodes a
  house style over a repository's.
- **With judgement.** Not everything can be scripted (the size rubric, classification,
  prose). Resolution: judgement outputs keep a fixed shape that a script or guard row checks,
  and the bundle's `coverage_note` names the judgement gap (ticket-workflow does).
- **With principle 10 (composable bundles).** One renderer per artefact and one canonical
  source per helper pull the same way: the renderer is the artefact's canonical source, and
  the helpers it needs are inlined marked blocks, not a second renderer.

## Examples

Compliant:

- `create-ticket` previews a body produced by `render-ticket.py` and, on "Edit a field",
  re-runs the renderer with the changed model instead of patching the text.
- A new `k8s` subcommand ships with `golden/<cmd>-md.txt` and `golden/<cmd>-json.txt`,
  produced against the `kubectl` stub.

Non-compliant:

- A skill step reading "write a Jira description in the format shown above" next to a
  renderer that exists.
- A facts script that prints `Project: PROJ` lines for the model to parse, or a preflight
  whose JSON changes key order between runs.

## Open questions

- Whether `harness lint` should require that a skill with a `scripts/render-*.py` names it in
  `SKILL.md` as the only way (a text heuristic like the `yields` rule), or whether `stability`
  extended to `beta` is enough.
- The MR description: how much of it is reproducible once preflight, decomposition and stack
  state are JSON. Proposal: everything but the "Why" and "What" prose.
- Whether judgement shapes get JSON schemas under `schema/`. The engine has `schema_lite.py`,
  but rendered skills cannot import it; an inlined checker would be a principle 10 block.
