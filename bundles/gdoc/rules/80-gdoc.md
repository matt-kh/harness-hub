## Google Workspace ({{ google.domain }})
- One corporate account. Use the `gdoc` CLI (user-level skill) for Docs, Drive, Sheets and
  Gmail; reads are free.
- `create` stamps the Drive property `agent_provenance=agent-created` and runs promptless, as
  does `mail draft`. `import/append/replace/sheet append|update` run promptless only on files
  carrying an `agent-*` provenance marker; on human files (or an unreadable one, or a `$VAR`
  id) they prompt. `mark` always prompts once — it adopts a human file. `gdoc api` is GET-only.
- Gmail: search/read/draft only (drafts may address anyone). **Sending mail is not implemented**
  — the agent leaves the draft in Gmail and the user sends it; never route around this.
- Not implemented on purpose: sharing/permissions, delete/trash, Calendar, writing doc
  comments. Do not work around this via `gdoc api`.
- Editing: rich changes are a round trip (`export --md` → edit → `import`) that replaces the
  **whole** doc — comments, suggestions and extra tabs are lost, `import` refuses while
  comments are open unless `--force`, Drive revision history survives. Surgical changes go
  through `append`/`replace`. Read back after every write.
- Secrets: `~/.config/gdoc/{client_secret,token}.json` hold the OAuth client and tokens —
  never read or print them; check auth with `gdoc auth status`.

A repository's own instructions for the same action replace this block.
