# Editing Google Docs with `gdoc` — strategy and API caveats

## Pick the strategy before you touch the document

| Change | Do this | Why |
|---|---|---|
| Rewrite, restructure, add sections, tables, lists, any Markdown | **Round trip**: `gdoc export <ID> --md work.md` → edit `work.md` locally → `gdoc import <ID> work.md` | The Docs API has no "set the body to this Markdown" request; Drive's Markdown→Doc conversion is the only thing that produces real headings, tables and lists |
| Add a paragraph or a section at the end | `gdoc append <ID> "text" --heading "Section"` | One batchUpdate, nothing else in the doc is touched |
| Fix a word, a name, a date, a version string | `gdoc replace <ID> <FIND> <REPL> [--match-case]` | Idempotent, prints `occurrencesChanged` so you can verify |
| Create a document from scratch | `gdoc create "<TITLE>" --from body.md` | Same Markdown conversion, and it stamps `agent_provenance=agent-created` |

**`import` replaces the whole document.** It keeps the file id, URL, sharing and Drive revision
history, and it loses:

- every comment and every suggestion (open *and* resolved),
- every tab except the one the Markdown becomes (a multi-tab doc collapses to one tab),
- anything Markdown cannot express (see the fidelity table).

Because of that, `import` refuses to run when the doc has unresolved comments unless you pass
`--force`. When comments matter, use `append`/`replace` instead, or export, edit, and give the
user the new Markdown to review before importing.

Always read back: `gdoc get <ID>` (outline) or `gdoc export <ID> --md -` after a write.

## Index arithmetic: UTF-16, not characters

Docs API `startIndex`/`endIndex` count **UTF-16 code units**. ASCII and most Latin text: one unit
per character. Emoji and astral-plane characters: **two**. `gdoc.py` uses `utf16len()` for every
range it computes; if you ever build a batchUpdate by hand through some other route, do the same —
off-by-one styling on a doc containing an emoji is the classic symptom.

Other index facts:

- Index 0 is not writable. A body's first insertable index is 1.
- The last element of `body.content` ends with the document's final newline, so the append point
  is `content[-1].endIndex - 1` (inserting at `endIndex` is rejected).
- Indexes shift as soon as a request in the same batch inserts text. `gdoc append` orders its
  requests insert-first, then styles the ranges it just created, which is why it is safe.
- A paragraph's range for `updateParagraphStyle` must include the paragraph's trailing newline.

## Tabs

- Every Doc has tabs now; `gdoc get` lists them (`== tab t.0 "Title"`). Pass `--tab <TABID>` to
  `get` and `append` to work on one.
- `documents.get` only returns tab bodies with `includeTabsContent=true` (gdoc always sends it).
- **`replaceAllText` defaults to *all* tabs**; `--tab` narrows it via `tabsCriteria`.
- Every other request defaults to the **first** tab unless the `Location`/`Range` carries a
  `tabId`. `gdoc append` sets `tabId` whenever the document reports one.
- `gdoc append` with no `--tab` writes to the first tab, not the one the user is looking at. If the
  doc has several tabs, ask which one, or name it from `gdoc get`.

## `append` is plain text

`append` inserts literal characters. `## Heading`, `- bullet`, `**bold**` arrive as those exact
characters — no Markdown is interpreted. `--heading H` is the only formatting it does: it styles
the first inserted paragraph `HEADING_2` and the body `NORMAL_TEXT`. For anything richer, round
trip through `import`.

Heading styles available in the API: `TITLE`, `SUBTITLE`, `HEADING_1` … `HEADING_6`,
`NORMAL_TEXT`. Markdown import maps `#` → `HEADING_1`, `##` → `HEADING_2`, and so on; it does not
produce `TITLE` (the document title is file metadata, not body content — change it in the browser,
`gdoc` has no rename verb).

## Markdown fidelity on a round trip

`export --md` → `import` is not guaranteed to be lossless. **Unverified — fill in after the first
real round-trip** (`gdoc export <ID> --md a.md && gdoc import <ID> a.md && gdoc export <ID> --md
b.md && diff a.md b.md`), then replace the `?` cells:

| Feature | Export → Markdown | Markdown → Doc (import) | Notes |
|---|---|---|---|
| Headings H1–H6 | ? | ? | expected lossless |
| Bold / italic / strikethrough | ? | ? | expected lossless |
| Inline + fenced code | ? | ? | |
| Bullet / numbered lists, nesting | ? | ? | deep nesting is the usual casualty |
| Tables | ? | ? | merged cells and cell formatting are the risk |
| Links | ? | ? | |
| Images | ? | ? | Markdown has no image store; expect loss |
| Footnotes | ? | ? | no Markdown equivalent; expect loss |
| Table of contents | ? | ? | generated element; expect loss |
| Page breaks, headers/footers | ? | ? | not expressible in Markdown |
| Text colour, highlight, font choices | ? | ? | expect loss |
| Comments and suggestions | n/a | n/a | **always lost** by `import` |
| Multiple tabs | ? | n/a | **collapses to one tab** |
| Checkboxes / smart chips / equations | ? | ? | |

Until this table is filled in, treat `import` on a human-authored document as destructive: read
the doc first (`gdoc get`, `gdoc comments`), warn the user what the round trip would drop, and
prefer `append`/`replace`.

Fallback if Drive's Markdown re-conversion on `files.update` ever stops working: a batchUpdate of
`deleteContentRange` over `1 .. endIndex-1` followed by `insertText` of the plain text — which
loses all formatting, so `gdoc` does not do it silently.

## Sheets

- `gdoc sheet get <ID>` with no range lists sheet titles, sheet ids and grid sizes — get the exact
  sheet name from there before writing; a wrong name is a 400, not a silent no-op.
- `sheet append` uses `USER_ENTERED` + `INSERT_ROWS`: values are parsed the way typing them would
  be (`=SUM(A1:A2)` becomes a formula, `2026-09-18` a date). Quote anything that must stay literal.
- `sheet append`'s range is a table anchor (`'Sheet1!A:C'`), not the destination — the API finds
  the first empty row after the existing data. Check the printed `updatedRange`.
- `sheet update` overwrites exactly the range you give it and does not shift anything. Rows come as
  JSON (`'[["a","b"]]'`) or `@rows.json`.
