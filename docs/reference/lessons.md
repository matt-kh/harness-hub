# Reference: lessons

`harness lessons` keeps a private library of **lessons**: short, evidence-backed observations
about where a guide or a sensor of the hub fell short. The loop is reflect → update → reuse:
after a task whose signals meet the review criteria, a retro records at most a couple of
candidate lessons with their evidence (`new`); later tasks in the same domain consult
`INDEX.md` and count whether a lesson was used, helped or the situation recurred (`note`); a
human confirms a lesson, or it recurs often enough with guard-journal evidence, and only then
can it become an `agent-drafted` issue carrying a guide edit and its paired sensor
(`propose`). No lesson changes a bundle by itself: the edit lands as a PR a human merges
([principle 6](../../principles/06-harness-engineering.md)). The `/retro` skill that writes
lessons and the hooks that record prompt signals ship with the `lessons` bundle; this page
covers the engine command, which every provider gets.

## Where things live

| What | Path | Override |
|---|---|---|
| Lesson records and `INDEX.md` | `~/.local/state/harness/lessons/` | `lessons.dir` in `harness.toml` |
| Guard journal | `~/.local/state/harness/journal/<YYYY-MM-DD>.log` | `HARNESS_JOURNAL_DIR` |
| Retro pointers (`current`, `last`, `sessions/`) | `~/.local/state/harness/retro/` | `HARNESS_RETRO_DIR` |

`~/.local/state` is `$XDG_STATE_HOME` when that is set. The CLI refuses a `lessons.dir` under
the hub checkout or inside any git checkout and says where to put it instead: lessons never
enter a repository. `harness uninstall` keeps all three directories.

## Record format

One file per lesson, `<lessons.dir>/<domain>-NNN.md` (`base-001`, `delivery-003`; ids are
sequential per domain). `harness lessons` is the only writer: it re-emits the keys in this
order and the sections in this order, so a record round-trips byte for byte; a hand-edited
record that breaks the shape is refused with the line at fault.

```markdown
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
```

| Key | Values |
|---|---|
| `status` | `candidate` → `confirmed` (human) or `recurring` (engine) → `proposed` → `retired` |
| `scope`, `domain` | `invariant` (only with domain `base`: applies everywhere) or `domain`; a [taxonomy](taxonomy.md) domain |
| `guide_ref`, `sensor_ref` | component ids `<bundle>/<kind>/<name>`, as `harness catalog` prints them |
| `source` | `journal`, `retro`, `user` |
| `uses`, `helped`, `recurred` | deferred-probing counters from `note`; `helped` is subjective and never promotes |
| `recurred_objective` | recurrences noted with a `journal:` evidence ref; the only count that promotes |
| `candidate_edit` | `patches/<id>.diff`: a unified diff against the hub root touching `bundles/` only |
| `validation`, `validated_at`, `validated_guard_id` | the last `validate` result, its time and the rendered guard's id |

`new` refuses a record without evidence, an unknown domain, `invariant` outside `base`, a ref
of the wrong shape, a token-shaped string or URL userinfo anywhere in the text, and text over
the caps: situation 300, lesson 400 and every evidence ref (a quoted user correction too)
200 characters; the candidate-edit summary is cut at 600. Evidence refs are `KIND:TEXT`
with `KIND` one of `journal`, `retro`, `user`, `test`, `review`.

## Journal lines and kinds

The evidence the loop counts is the guard journal: one line of seven tab-separated fields
`ts provider session kind site guard_id repo` per signal, with `kind` one of `guard-ask`,
`guard-deny` (the guard, `lessons.journal`) and `correction`, `dissatisfaction` (the `lessons`
bundle's prompt hook, `lessons.prompt_signals`). The format, the privacy guarantees and the
stale rule are in [hook policy "Journal"](hook-policy.md#journal). A line whose `guard_id`
differs from the current guard's is **stale**: counted, never attributed to a rule of the
current guard.

## Review criteria

`harness lessons review` decides whether a retro is due for one session (`--session S`, else
the session in `retro/current`). It is due when, within that session:

| Criterion | Journal kind | Key (default) |
|---|---|---|
| corrections | `correction` | `lessons.review.corrections` (2) |
| dissatisfaction | `dissatisfaction` | `lessons.review.dissatisfaction` (1) |
| denies | `guard-deny` | `lessons.review.denies` (3) |

A threshold of `0` disables its criterion. Exit status: **0** due, **1** not due, **3** no
journal files, no session known, or no line for the session (the output says which). It prints
`due: yes|no`, the session, the counts and the criterion that fired; `--explain` adds each line
as time, kind and site, never anything else; `--json` prints
`{"due", "session", "counts", "fired"}` (plus `reason` for rc 3).

## Commands

Every subcommand takes the global flags (`--config`, `--json`, ...); full help in
[CLI](cli.md#harness-lessons).

| Command | What it does |
|---|---|
| `list [--status S\|all] [--domain D] [--stale]` | lessons, every status but retired by default |
| `show ID` | the record as written |
| `new --domain D --scope invariant\|domain --situation TEXT --guide-ref R --sensor-ref R --evidence REF... [--bundles B,...] [--source S] [--lesson TEXT] [--edit FILE.diff] [--date D]` | the only way a record is created (status `candidate`); prints the id |
| `note ID [--used] [--helped] [--recurred] [--evidence REF]... [--note TEXT] [--date D]` | bumps counters and appends a History line; `--recurred` with a `journal:` ref also bumps `recurred_objective`, and a candidate becomes `recurring` at `lessons.promote_after` (3); refused on proposed and retired lessons |
| `confirm ID`, `retire ID [--reason TEXT]` | human decisions; confirm only from candidate or recurring |
| `review [--session S] [--explain]` | the review gate above |
| `stats [--domain D] [--since DATE]` | one table: per lesson, before and after its `created` date, sessions and asks, denies and corrections per session in its scope (its guard section when the sensor is one, else the guard sections of its domain), plus its counters |
| `validate [ID] [--quick] [--full] [--now TS]` | `git archive HEAD` of the hub into a temp dir, `git apply` the candidate edit, then `harness lint`, `test guard`, `test <touched bundle>` (skipped with `--quick`; `--full` runs every suite) and `render --out`, isolated from your config and home; records pass or fail, the time and the rendered guard's id. Without a candidate edit: `validation none`, rc 1 |
| `propose ID --out DIR [--repo OWNER/REPO] [--keep-repos] [--mark] [--date D]` | writes `body.md`, `preview.md` and `create.sh` (a `gh issue create -R OWNER/REPO ... -l agent-drafted` line for a GitHub Issues tracker, a `/create-ticket` line for Jira; the tracker comes from the hub's `.harness.toml`, `--repo` overrides). Accepts `confirmed`, or `recurring` with `recurred_objective >= lessons.promote_after`; refuses closing keywords and a `#N` title; replaces repository names from evidence by `<repo>` unless `--keep-repos`. `--mark` sets `proposed` after the issue exists |
| `index [--prune] [--now TS]` | rewrites `INDEX.md`: grouped by domain, settled lessons first, at most `lessons.index_max_candidates` (5) candidates per domain and `lessons.index_max` (40) lines overall, `ready` or `stale` (no update in `lessons.max_age_days`, 90); `--prune` retires stale candidates |
| `journal [--all] [--since TS] [--ack]` | journal lines since `retro/last`, grouped by kind and site; a current-guard site shows its source line, other guard ids show as stale; `--ack` writes `retro/last` and prunes `retro/sessions/*` older than 7 days |

## Privacy

Nothing leaves the workstation. The records, the index, the journal and the retro pointers
are local files under your state directory, written with mode `0600`; no hub component sends
them anywhere and none of them holds a command, a prompt or a secret (`new` refuses token
shapes and URL userinfo). `propose` never creates anything: it writes three files for you to
read, and you decide whether to run `create.sh`. Repository names from evidence are replaced
by `<repo>` in what it writes unless you pass `--keep-repos`
([governance](../governance.md#10-the-guard-journal-stays-on-your-workstation)).
