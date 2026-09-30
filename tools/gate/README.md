# Private-identifier gate

harness-hub is public; the organisations that use it are not. This gate keeps organisation- and
person-specific values (hostnames, project keys, cluster names, account ids, internal IPs, work
emails) out of every tracked file, file name, commit message and commit author address.

| File | Purpose |
|---|---|
| `private-ids.sh` | the gate (bash 3.2, `grep -E`, no `grep -P`) |
| `patterns.public.txt` | generic shapes, safe to publish: home directories, 12-digit ids, non-documentation IPv4, non-example emails, Jira `customfield_1xxxx`, selected country-code hosts, AWS ARNs/keys, Slack/GitHub/GitLab token prefixes <!-- gate-allow: names the pattern --> |
| `allowlist.txt` | reviewed exceptions for public hits, `path-ERE<TAB>line-ERE<TAB>reason` |
| `check-links.sh` | relative Markdown link and anchor checker (CI `lint` job) |
| `tests/selftest.sh` | builds a throw-away repo with planted hits and asserts every mode |

## The private denylist

Your own identifiers are, by definition, not publishable, so they live outside the repo:

1. `$GATE_PRIVATE_DENYLIST` — the list's *contents* (multi-line). CI passes a repository secret.
2. else `${HARNESS_GATE_PRIVATE:-$HARNESS_HOME/local/gate-denylist.txt}` — `local/` is gitignored.

One case-insensitive POSIX ERE per line, `#` comments allowed. Example (fictional org):

```text
# local/gate-denylist.txt
acme
acmecorp\.internal
jira\.acme
SHOP-[0-9]+
```

If neither source is present the gate says `private list unavailable — public patterns only`
and still runs the public patterns. That is what happens on pull requests from forks, where
GitHub does not expose repository secrets.

## Running it

```sh
tools/gate/private-ids.sh                       # every tracked + untracked-not-ignored file
tools/gate/private-ids.sh --staged              # only what is staged
tools/gate/private-ids.sh --files a.md b.sh     # pre-commit passes file names this way
tools/gate/private-ids.sh --commit-msg-file .git/COMMIT_EDITMSG   # commit-msg hook
tools/gate/private-ids.sh --no-tree --range origin/main..HEAD     # messages + author emails
tools/gate/private-ids.sh --ci --range "$BASE..HEAD"              # what CI runs
tools/gate/tests/selftest.sh -v                 # prove the gate still catches what it should
make gate                                       # same as the first line
```

Output, one hit per line; exit status 1 if there is any hit, 2 on a setup error:

```text
docs/example.md:12: public:ipv4: 10.20.30.40
docs/example.md:14: private#3: <matched text>         (local runs only)
docs/example.md:14: private#3                         (--ci: never the pattern or the text)
file name #4:0: private#1                             (--ci: the path itself would leak)
commit:1a2b3c4:author-email: not a users.noreply.github.com address
```

`--ci` exists because CI logs of a public repository are public: a private hit is reported by
its line number in the denylist, never by the pattern or the matched text, and non-noreply
addresses are not echoed.

## Commit identities

Every commit author and committer address must end in `users.noreply.github.com` (GitHub's
per-account noreply address, *Settings → Emails → Keep my email addresses private*) or match
an `^@email$` row of `allowlist.txt` (`noreply@github.com` is pre-approved for web merges).
Set it once per clone:

```sh
git config user.email "<id>+<login>@users.noreply.github.com"
```

## Suppressing a public hit

Public patterns flag *shapes*, and sometimes a shape is fine. In order of preference:

1. Replace the value with a documentation value: `/home/u`, `/Users/u`, `192.0.2.x`,
   `198.51.100.x`, `203.0.113.x`, `you@example.com`, `111122223333`, `customfield_2xxxx`.
2. Mark the line: `# gate-allow: <reason>` in code, `<!-- gate-allow: <reason> -->` in Markdown.
3. Add an `allowlist.txt` row for a whole class of lines (fixtures, goldens).

**Private hits cannot be suppressed.** An allowlist row or inline marker would have to sit next
to the private text in a public file. Rename the value instead; see
[migrate-existing-harness](../../docs/runbooks/migrate-existing-harness.md).

## Where it runs

| Where | How |
|---|---|
| pre-commit | `private-ids` hook, stages `pre-commit` (staged file names) and `commit-msg` |
| CI | `gate` job: `--ci` with the `GATE_PRIVATE_DENYLIST` secret and the push/PR commit range |
| by hand | `make gate` |

Adding a public pattern: add `# id:` (and optionally `# except:`) lines above it in
`patterns.public.txt`, add a planted case to `tests/selftest.sh`, run it. Patterns must be
portable ERE: no `\b`, `\d` or lookarounds (BSD grep on macOS).
