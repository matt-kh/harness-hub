# Runbook: migrate an existing hand-built harness

For people who already maintain a harness by hand — typically `~/.claude` as a git repository
with a guard hook, skills, agents and a long `CLAUDE.md` — and want to move to harness-hub
without losing anything or leaking their organisation into a public repository.

The end state: the hub (public, or your fork) holds generic bundles; `local/` holds your
config and a **private bundle** with everything organisation-specific; `~/.claude` becomes a
render target again, containing only what `harness apply` writes plus the runtime state
Claude Code keeps there.

Budget an afternoon. Nothing below needs your agent sessions closed until step 7.

## 1. Snapshot the old harness

From a plain terminal:

```sh
mkdir -p ~/backups
git -C ~/.claude status --short          # must be clean: commit anything pending first
git -C ~/.claude bundle create ~/backups/claude-harness-$(date +%F).bundle --all
git bundle verify ~/backups/claude-harness-*.bundle
```

Verify you can restore: `git clone ~/backups/claude-harness-<date>.bundle /tmp/verify` and
check the log. Keep this bundle until you are sure you will not roll back (30 days is plenty).

## 2. Classify every file

List what the old repo tracks and put each file in one of three buckets:

| Bucket | Examples | Goes to |
|---|---|---|
| **Generic** — useful to anyone | guard rules for git/credentials, generic skills | an existing hub bundle (compare first), or a new public bundle |
| **Parameterised** — generic code with your values inside | a Jira CLI with your URL and field ids, docs mentioning your hosts | the hub bundle, with values moved to `harness.toml` keys |
| **Private** — only meaningful to you | cluster inventories with IPs, cross-repo maps, trust text, internal runbooks, plans | `local/bundles/<org>/` (never public) |

Runtime state (`projects/`, `sessions/`, `plans/`, `plugins/`, credentials, memory) is not
migrated at all; it stays where it is and the hub never touches it.

## 3. Write your config and private bundle

```sh
~/harness-hub/bin/harness init --bundles core,github,jira,ticket-workflow   # scaffolds local/
git -C ~/harness-hub/local init && chmod 700 ~/harness-hub/local            # private history, no public remote
```

- Move every literal into `local/harness.toml`: hosts (`gitlab.host`, `jira.url`), your login,
  Jira field ids (`jira fields PROJ` prints them), prod regexes, GitOps paths, the Workspace
  domain, the auto-mode trust text (`[trust]`).
- Put private rules, references and extra guard sections in `local/bundles/<org>/` with a
  `bundle.toml`, and add the bundle to `hub.bundles`.
- Write `local/gate-denylist.txt`: one case-insensitive regex per identifier that must never
  appear publicly — company and product names, hostnames, project keys, cluster names,
  account ids, internal IP prefixes, your name.

`harness config validate` must pass. It will reject any token you forgot to remove.

## 4. Build a rename map for test data

Guard tests and goldens are usually full of real values. Create a private sed script (keep it
in `local/migration/`, never commit it publicly) mapping each real value to a documentation
value: your project key → `PROJ`, your domain → `example.com`, your username → `u`, custom
field ids → `customfield_2xxxx`, account ids → `111122223333`, IPs → `192.0.2.x`
/ `203.0.113.x`. Apply it to the rows you port, regenerate goldens with `UPDATE=1`, and check
the golden diff is a pure token substitution:

```sh
git diff --word-diff-regex='[A-Za-z0-9_./-]+'
```

Row counts must not change. If your old suite had N passing rows, the hub's suite plus your
private bundle's rows must still total N.

## 5. Local gates, before anything leaves the machine

If you contribute generic parts back (a fork or PR), start that tree from **fresh history** —
never copy the old `.git`, it contains every private value you ever committed.

```sh
git config user.email "<id>+<login>@users.noreply.github.com"
make gate                   # public patterns + your denylist over contents, names, messages
make test && make lint && make render-check
git log --format='%ae' | sort -u               # only the noreply address
```

## 6. Regression check: render equals today

```sh
harness render --out /tmp/r
diff <(jq -S .permissions /tmp/r/claude/settings.json) <(jq -S .permissions ~/.claude/settings.json)
diff <(jq -S .autoMode    /tmp/r/claude/settings.json) <(jq -S .autoMode    ~/.claude/settings.json)
diff /tmp/r/claude/hooks/guard-bash.sh ~/.claude/hooks/guard-bash.sh      # expect only structural changes
diff /tmp/r/claude/CLAUDE.md ~/.claude/CLAUDE.md                          # same text plus managed-block markers
harness apply --dry-run                                                   # every path it would touch
```

Confirm in the dry-run that runtime directories (`projects/`, `plans/`, `plugins/`,
credentials, memory) appear nowhere.

## 7. Cut over

Close every agent session first: settings and instructions are rewritten. Then, from a plain
terminal:

```sh
mv ~/.claude/.git ~/.claude.bak-$(date +%F).git        # old history out of the runtime dir
# remove only the files the old repo managed and the hub will now render:
#   old repo-only files (README, Makefile, pre-commit config, secrets baseline, .gitignore)
#   hooks/, agents/, bin/, and the skills the hub now provides (not org-synced or plugin skills)
~/harness-hub/bin/harness apply --provider claude
~/harness-hub/bin/harness doctor
```

`apply` treats anything left in place as foreign and keeps it; if you forgot to remove an old
skill directory the plan shows it, and `--adopt PATH` backs it up and takes it over.

## 8. Restart and verify

Start one session in the hub checkout: `harness test` passes; asking the agent to read a
credential file is denied; your memory/notes still load; the permission list shows your
trust text. Then resume normal work.

## Rollback

Any time before you delete the backups:

```sh
~/harness-hub/bin/harness uninstall --provider claude   # removes only state-listed paths
mv ~/.claude.bak-<date>.git ~/.claude/.git
git -C ~/.claude checkout -- . && git -C ~/.claude status
```

Then re-run whatever install step your old harness had and restart sessions.
