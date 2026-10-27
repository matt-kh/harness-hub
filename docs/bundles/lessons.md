# Bundle: lessons

The lessons loop is the routine form of the hub's steering loop
([principle 6](../../principles/06-harness-engineering.md)): when an agent repeatedly hits a
guard rail or the user keeps correcting it, the evidence is recorded, a short lesson is
written about where a guide or a sensor fell short, later tasks in the same domain consult
it, and a human decides whether it becomes a guide edit with its paired sensor. No lesson
changes a bundle by itself; the edit lands as a PR a human merges. The engine half (the
`harness lessons` CLI, the record format, the review criteria, the journal) is in the
[lessons reference](../reference/lessons.md) and [hook policy "Journal"](../reference/hook-policy.md#journal);
this bundle adds the agent-facing half.

**The loop.**

1. **Signals** (opt-in, [`enable-journal`](#enable-journal)). With `lessons.journal` the
   guard appends one line per ask or deny to the journal; with `lessons.prompt_signals` the
   `prompt` hook (`hooks/prompt-signal.sh`) appends one `correction` or `dissatisfaction` line
   per prompt that matches `lessons.correction_re` or `lessons.dissatisfaction_re`. Lines
   carry a time, the provider, the session id, the kind, the rule site, the guard id and the
   repository's directory name: never a command, a prompt or any word of either.
2. **Review.** `harness lessons review` is due when one session reaches a threshold
   (2 corrections, 1 dissatisfaction or 3 denies by default). The `stop` hook
   (`hooks/stop-retro-nudge.sh`) asks it once per session and, only when it is due, shows
   `harness: this session met the review criteria (…); run /retro`. It never blocks.
   work-ticket and create-ticket ask the same gate after their last step (a later part of
   this loop).
3. **Reflect and record.** `/retro` reads the facts (`retro-facts.sh`: the review, the
   journal groups since the last retro, the library), fills one fixed-shape questionnaire and
   records at most one `invariant` and one `domain` candidate through `harness lessons new`,
   each citing its evidence (a journal line copied verbatim, a quoted correction). Lessons it
   consulted get a `harness lessons note` (used, helped, recurred).
4. **Reuse.** Rule `15-lessons` has every agent consult `INDEX.md` for its domain at Step 0
   and weigh a lesson as evidence, never as an instruction.
5. **Promote (human).** `harness lessons confirm`, `retire` and `propose` are yours.
   `propose` writes an issue body with the candidate guide edit and its sensor; read
   `body.md` before you run `create.sh`.

**Lifecycle of a record.** `candidate` (written by `/retro`) → `confirmed` (you) or
`recurring` (the CLI, after `lessons.promote_after` journal-backed recurrences) → `proposed`
(`propose --mark`, after the issue exists) → `retired` (you, or `index --prune` for stale
candidates). Records live in `~/.local/state/harness/lessons/` (`lessons.dir`), never in a
repository.

**Provider matrix.** The rule, the skill and `harness lessons` work on every provider; only
the hooks differ. Where no hook runs, the journal has no prompt lines and the stop nudge never
appears; `/retro` by hand still works.

| Provider | prompt signals (`prompt`) | nudge (`stop`) | Notes |
|---|---|---|---|
| claude | enforced (`UserPromptSubmit`) | enforced (`Stop`) | `Stop` does not run when you interrupt the agent |
| gemini | enforced via `shim-prompt.sh` (`BeforeAgent`) | enforced via `shim-stop.sh` (`AfterAgent`) | `AfterAgent` runs after every turn; the per-session marker keeps the nudge to one |
| copilot | enforced via `shim-prompt.sh` (`userPromptSubmitted`) | none: `sessionEnd` has no message channel, the shim drops the output | event names verified on install, like the guard shim |
| codex | advisory (no hook) | advisory | rule, skill and CLI only |
| opencode | advisory (no hook) | advisory | rule, skill and CLI only |

**Privacy.** The prompt hook sees the prompt (the provider hands it the payload, as the
guard sees commands), matches it in memory with `grep -Eiq` and stores only the class name.
It prints nothing: Claude would add its stdout to the model's context. Neither hook opens a
transcript file. Everything stays on the workstation in files with mode 0600.

**The regexes are a judgement call.** They will miss paraphrased corrections and flag some
task text: "undo the last migration" is a documented false positive (it is a correction-shaped
instruction). A false positive costs one nudge or one gated retro. The contract is
`bundles/lessons/hooks/tests/prompts.tsv`; tune `lessons.correction_re` and
`lessons.dissatisfaction_re` in `harness.toml` if your normal prompts trip them.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| No `correction` lines in the journal | `lessons.prompt_signals` is off, the prompt started with `/` or was over 600 characters, or the provider has no `prompt` event (codex, opencode) | turn the key on and `harness apply`; check `harness status --matrix`, row "extra hook events" |
| The nudge never appears | `lessons.journal` is off, the session was already nudged (`~/.local/state/harness/retro/sessions/<id>`), the review is not due, or the provider has no message channel (copilot) | `harness lessons review --session <id> --explain` shows the counts; run `/retro` by hand |
| The nudge appears on harmless prompts | a regex matched task text | narrow `lessons.correction_re` / `lessons.dissatisfaction_re`; add the prompt to `prompts.tsv` if you send a PR |
| `harness doctor`: lessons-index-fresh warns | a record changed after the last `harness lessons index` | `harness lessons index` |
| `harness doctor`: lessons-stale-candidates warns | candidates not updated for `lessons.max_age_days` | `harness lessons list --stale`, then `note`, `retire`, or `harness lessons index --prune` |
| `harness doctor`: lessons-review-keys fails | a regex in `[lessons]` does not compile under `grep -E` | fix the value in `harness.toml`, then `harness apply` |
| `/retro` says "harness CLI not found" | the hub's `bin/harness` is neither at `$HARNESS_HOME` nor on PATH | `harness apply` links it into `~/.local/bin` |
| `harness lessons note --recurred` refuses a `journal:` ref | the ref was retyped instead of copied | copy the `example` value of the journal group verbatim |
| Two sessions at once review the wrong session | `retro/current` holds the last session that produced a signal | pass `--session`; the stop nudge always uses its own session id |

<!-- generated:begin source=bundles/lessons/bundle.toml -->
## Summary

The lessons loop: a /retro skill that turns a session's journal signals into at most two evidence-backed candidate lessons, a rule that has agents consult them, and hooks that record user corrections and nudge for a retro

The routine form of the steering loop (principle 6). With `lessons.journal` on, the guard
journals every ask and deny; with `lessons.prompt_signals` on, the `prompt` hook adds one line
per correction or dissatisfaction it recognises in a prompt (the class only, never the text).
When a session's signals meet the review criteria (`harness lessons review`), the `stop` hook
nudges once with a message (never a block) and `/retro` reflects on the evidence: at most one
invariant and one domain candidate lesson, written only through `harness lessons new|note`.
Later tasks consult `INDEX.md` for their domain at Step 0 and weigh a lesson as evidence,
never as an instruction. Confirming, retiring and proposing a lesson (an `agent-drafted` issue
carrying a guide edit and its sensor) are human actions; no lesson changes a bundle without a
PR. Everything stays on the workstation under `~/.local/state/harness/`.

- **Depends on:** `core`
- **Recommends:** `ticket-workflow`
- **Stability:** experimental
- **Domain / posture:** base / local

## Components

Stable ids derived from the path, with their [taxonomy](../reference/taxonomy.md) facets (domain shown only where it differs from the bundle's). All bundles: [catalog](../catalog.md).

**Skills**

- `lessons/skills/retro` — control: guide · function: workflow · posture: local · model: execute · yields: declaration

**Rules**

- `lessons/rules/15-lessons` — control: guide · function: govern · yields: text

**Hook scripts**

- `lessons/hooks/prompt-signal` — function: govern · yields: n/a
- `lessons/hooks/stop-retro-nudge` — function: govern · yields: n/a

**Permission lists**

- `lessons/permissions` — control: guide · function: govern · decisions: ask 2 · allow 1 · yields: config

**Doctor checks** (function: setup · posture: read-only; table below): `lessons/doctor/lessons-index-fresh`, `lessons/doctor/lessons-review-keys`, `lessons/doctor/lessons-stale-candidates`

**Manual steps** (function: setup; table below): `lessons/steps/enable-journal`, `lessons/steps/read-the-loop`

## Requirements

### Binaries

_none_

### Configuration

_none_

### Secrets (never in harness.toml)

_none_

## Manual steps

<a id="enable-journal"></a>

### enable-journal — Turn on the journal and prompt signals (opt-in)

*once per machine · needs nothing but a terminal · ~2 min*

**Why:** The loop has no evidence without signals: both are off by default, and nothing is recorded until you turn them on.

**How:**

In `harness.toml`, then `harness apply`:

```toml
[lessons]
journal = true          # the guard journals every ask and deny; the stop hook can nudge
prompt_signals = true   # the prompt hook journals corrections and dissatisfaction
```

- `lessons.journal` records, per guard ask or deny, one line in
  `~/.local/state/harness/journal/<date>.log`: time, provider, session id, kind
  (`guard-ask` | `guard-deny`), rule site (section and line), guard id and the repository's
  directory name. It never records the command, any word of it, paths or the reason.
- `lessons.prompt_signals` records, per prompt that matches `lessons.correction_re` or
  `lessons.dissatisfaction_re`, one line of the same shape whose kind is `correction` or
  `dissatisfaction`. It never records the prompt or any word of it: the prompt is only matched
  in memory. Slash commands and prompts over 600 characters are skipped.
- Both stay on this workstation (mode 0600 files); nothing sends them anywhere. Tune the two
  regexes in `[lessons]` if they flag your normal task text; `harness doctor` checks they compile.

**Verify:** `true` (exit 0)

<a id="read-the-loop"></a>

### read-the-loop — Read how the lessons loop works (you confirm, retire and propose)

*once per machine · needs nothing but a terminal · ~5 min*

**Why:** Lessons are agent-written observations; only a human promotes one into a guide change.

**How:**

Read docs/reference/lessons.md (the record, the review criteria, the CLI) and
docs/bundles/lessons.md (the loop and the provider matrix). The human commands:
`harness lessons confirm ID`, `harness lessons retire ID --reason TEXT`,
`harness lessons propose ID --out DIR` (writes body.md, preview.md and create.sh; read body.md
before you run create.sh).

**Verify:** `true` (exit 0)

## Doctor checks

| id | severity | offline | fix |
|---|---|---|---|
| `lessons-index-fresh` | warn | runs | `harness lessons index` |
| `lessons-stale-candidates` | warn | runs | `harness lessons list --stale` |
| `lessons-review-keys` | fail | runs | `Edit lessons.correction_re / lessons.dissatisfaction_re in harness.toml, then harness apply` |

## Guides and sensors

Guides steer the agent before it acts; sensors detect at or after the action. Pairing: **paired**; guides with a declared check: 3 of 3.

| side | kind | ref | note | pairs with |
|---|---|---|---|---|
| guide | rule | `rules/15-lessons.md` | consult INDEX.md at Step 0; a lesson is evidence, never an instruction; records only through /retro; confirm/retire/propose are human | `skills/retro/scripts/tests/run.sh`, `yields` |
| guide | skill | `skills/retro` | the retro: facts, one fixed-shape questionnaire, at most two candidates, harness lessons new\|note, a fixed-shape report | `skills/retro/scripts/tests/run.sh`, `skill-description`, `yields` |
| guide | permission | `permissions.toml` | harness lessons allowed; hand edits of the library ask | `permissions-vs-guard` |
| sensor | doctor | `doctor_checks` | INDEX.md fresh, no stale candidates, the review regexes compile | — |
| sensor | test | `tests/run.sh` | the hook suite, then lib/doctor.sh per check | — |
| sensor | test | `hooks/tests/run.sh` | prompt-signal.sh against prompts.tsv (the regex contract) and edge cases: no prompt word in the journal, empty stdout, journal off, relative dirs, no jq; stop-retro-nudge.sh against a stub CLI: rc 0 only, once per session, no decision key; static greps; under one second | — |
| sensor | test | `skills/retro/scripts/tests/run.sh` | retro-facts.sh goldens against a stub harness (due, not due, no signals, error rc, repo owns, outside a checkout, no CLI), state fixture byte-identical | `rules/15-lessons.md`, `skills/retro` |
| sensor | lint | `permissions-vs-guard` | each Bash allow rule of permissions.toml run through the guard | `permissions.toml` |
| sensor | lint | `skill-description` | retro: trigger phrase, NOT for scope, argument-hint | `skills/retro` |
| sensor | lint | `yields` | the skill's Step 0 and the rule's repository sentence | `rules/15-lessons.md`, `skills/retro` |
| sensor | lint | `hooks-events` | both hook scripts exist, parse, have known when keys and an event some provider declares | — |

**Not covered:** Whether a candidate lesson is worth recording, and whether a consulted lesson helped, stay judgement: /retro caps the candidates at two and needs evidence, and only a human confirms, retires or proposes. The two hooks are signal sources and the nudge, not guides (kind hook has no control facet); their contract is sensed by hooks/tests/run.sh (no prompt text in the journal, empty stdout, once-per-session nudge) and lint hooks-events. Bash(harness lessons:*) also allows confirm, retire and propose: the rule, not a sensor, keeps them human.

## Uninstall

Kept on uninstall: `~/.local/state/harness/lessons/**`, `~/.local/state/harness/journal/**`, `~/.local/state/harness/retro/**`

Removes the rendered skill, the rule block and the two hooks; the lessons library, the journal and the retro pointers under ~/.local/state/harness/ stay (delete them by hand).
<!-- generated:end -->
