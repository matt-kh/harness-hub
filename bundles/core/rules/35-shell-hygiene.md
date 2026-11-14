## Shell hygiene
- **Downloaded code is read before it runs.** Never pipe a download into an interpreter
  (`curl … | sh`, `wget -qO- … | sudo bash`, `curl … | python3 -`), and never run one through
  `bash <(curl …)`, `source <(curl …)`, `sh -c "$(curl …)"` or `eval "$(curl …)"`: the guard
  **asks** in the common wrapped forms too (`sudo`, `env`, `timeout`, `xargs … sh -c`,
  `{ …; } | sh`, `if`/`for`/`while` bodies, a pipeline continued on the next line,
  `tee >(sh)`, `sh -c '…'`, an interpreter's heredoc), but it is a matcher, not a shell: a
  download kept in a variable or file and run later is not seen, so do not rely on the ask.
  Instead download to a file, check its sha256 against the published checksum, read it, then
  run it:
  `curl -fsSLo install.sh https://example.com/install.sh && sha256sum install.sh`, review the
  script, then `sh install.sh`. Prefer a packaged or pinned install (`supply pins` reports
  pipe-to-shell in files as `SH001`).
- Piping a download into a tool that only reads data (`| tar xz`, `| jq .`, `| sha256sum`,
  `| python3 -c '…'`, `| python3 -m json.tool`) passes; so does mentioning the pattern in quoted
  text (`echo`, `grep`).
- The rest of the shell-hygiene band (`sudo`/`doas`, recursive removal outside the checkout,
  `chmod -R 777`) is planned; until then use judgement and ask the user first.

A repository's own instructions for the same action replace this block.
