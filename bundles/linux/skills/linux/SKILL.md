---
name: linux
description: >-
  Read-only Linux host client over the aliases in ~/.ssh/config via the `lx` CLI and plain
  read-only `ssh HOST <command>`. Use when the user mentions a host, server, VM, bare-metal box,
  Proxmox node, ssh alias, systemd unit, failed service, journald / journalctl logs, load, OOM,
  disk full, inodes, LVM, ZFS, mdadm / RAID, SMART, mounts, netplan, NetworkManager,
  systemd-networkd, bonds / VLANs, nftables / ufw / firewalld, DNS resolvers, sshd settings,
  sudoers, pending updates or reboots, or host hardening, or asks "why is host X slow / down /
  full". Never changes a host, never opens an interactive session or a tunnel, never reads keys.
model: {{ core.model_policy.execute }}
---

# Linux hosts (read-only client)

Generic client for every host the user reaches through a `Host` alias in `~/.ssh/config`.

**Step 0 — repository-level harness (principle 8).** This is a user-level skill. Read the
repository's declaration first:

```bash
harness repo owns linux/skills/linux   # rc 0 = owned (prints why) → stop; rc 1 = carry on
```

If it is owned (by id or by its domain `infrastructure`), or the repository ships its own skill for
the same workflow, this skill yields: say so in one line, name the repository-level skill or
convention, and stop — nothing below runs and nothing is merged. If the repository owns the
*workflow* but not the client, stay available as the plain client underneath it. Never edit
the repository's harness to fit this skill. `harness repo` explains everything the
repository declares and any `.claude/skills|agents` name collisions.
An infrastructure repository's own skills (Ansible roles, NixOS flakes, Terraform / Pulumi,
cloud-init) own the *fix* — this one stays the read-only client that explains what the host is
actually doing.

## Tooling

- **`lx` CLI** (this skill's `scripts/lx.py`, on PATH) — first choice for everything. One fixed,
  read-only script per subcommand, parsed locally, redacted; raw dumps never enter the context.
- **Plain `ssh HOST <read-only command>`** for anything `lx` does not cover — every clause must be
  on the guard's read-only allow-list (`cat`, `journalctl -u X --since …`, `systemctl status`,
  `ip -br a`, `ss -tlnp`, `lsblk`, `zpool status`, `nft list ruleset`, …). Pipe free text that may
  carry credentials through `| lx redact`.
- **Agents** for anything that needs to read a lot: `linux-triage` (incident) and `linux-auditor`
  (posture). Hand them the alias and the symptom; they return a summary, not the dumps.

Run bare `lx` for the full command list. Common:

```bash
# hook: allow
lx hosts                                   # ALWAYS first: aliases, HostName, User, Port, role
lx check web1                              # reachable? key auth works (BatchMode)?
lx facts web1                              # distro, kernel, CPUs, memory, virt, init
lx health web1                             # failed units, load, disk/inodes, memory, reboot, NTP
lx logs web1 --since 1h --limit 200 [--unit nginx.service] [--priority err]
lx net web1                                # links, bonds/VLANs, routes, renderer, firewall, DNS
lx storage web1                            # lsblk, mounts, df, LVM, ZFS, md RAID, SMART
lx audit web1                              # sshd, listening sockets, sudoers shape, updates
lx redact                                  # stdin filter (+ linux.redact_extra_re)
```

Flags after the subcommand: `--json` (default is Markdown), `--timeout 120` (whole call; the
connect timeout is `linux.ssh_timeout`), `--max-items 50`, `--max-bytes N`.

## Contract & rules

- **Exit codes**: `0` clean · `1` findings were reported (not an error — read them) · `2` access
  error (not an alias, unreachable, key auth failed, host key not verified, timeout). On exit 2
  quote the alias and the error line; `lx check HOST` says which.
- **Aliases only.** `lx` refuses anything that is not a `Host` alias in `~/.ssh/config` (or a file it
  `Include`s): no `user@ip`, no wildcards. A missing alias is the user's to add — never write
  `~/.ssh/config` yourself.
- **Banner** on stderr: `host=<alias> os=<ID VERSION_ID> [PROD]`. Quote the alias in every answer.
  `[PROD]` (alias matching `linux.prod_re`) means the remediation you produce is a **suggestion for
  the human**, stated with its blast radius — never something you try to run.
- **Keys are never read.** `lx` shows no `IdentityFile`, opens no key, and the guard denies reading
  `~/.ssh` private keys and copying them anywhere. `ssh-add -l` (exit code) tells whether an agent
  holds a key; auth failures are fixed by the user loading their key.
- **Host-key checking stays on.** A host-key failure is the user's to resolve (compare the
  fingerprint, add the `known_hosts` entry). `StrictHostKeyChecking=no` and
  `UserKnownHostsFile=/dev/null` are denied.
- **No sudo.** `lx` runs as the alias's login. What needs root (SMART, LVM on most distros, `nft
  list ruleset`, `sshd -T`, other users' journal) is reported as `needs root` — hand the exact
  `sudo …` command to the user instead of trying it.
- **Bounded logs.** Always `--since` and `-n`/`--limit`; never `journalctl -f` or `tail -f`.
- Guard decisions (the guard wins over `permissions.allow`):

  | Command | Decision | Rationale |
  |---|---|---|
  | `lx <any subcommand>` | allow | read-only by construction |
  | `ssh HOST <cmd>` where every clause is read-only | pass | reads |
  | `ssh HOST` with `sudo`, `sh -c`, `$(…)`, redirections, restarts, package or config changes | **ask** (`host=… [PROD]`) | not read-only — hand it to the user |
  | interactive `ssh HOST`, `ssh -t`, tunnels / forwarding, `scp`/`rsync` uploads, `sftp`, `ssh-copy-id` | **ask** | session, tunnel or upload |
  | `StrictHostKeyChecking=no`, `UserKnownHostsFile=/dev/null`, `sshpass` | **deny** | spoofed hosts, passwords on the command line |
  | copying anything but `*.pub` out of `~/.ssh` | **deny** (never yields) | private keys never leave the machine |
  | local `mkfs`, `wipefs`, `dd of=/dev/…`, partitioning, LVM / ZFS / RAID changes, `nft`/`ufw`/`netplan apply`/`nmcli`/`ip … add` | **ask** | destructive local storage or network change |

## Procedure

**Step 1 — Orient.** Never assume which host.

```bash
# hook: allow
lx hosts
lx check db-prod-1
```

Resolve the user's words to an alias (`role` and `notes` come from `linux.inventory`). If none
matches, ask; do not guess a HostName.

**Step 2 — Sweep.** Always before drilling in.

```bash
# hook: allow
lx facts db-prod-1
lx health db-prod-1
```

**Step 3 — Drill into the symptom** with `references/triage.md`, a decision tree keyed on these
outputs; then the topic runbook: `references/networking.md`, `references/storage.md`,
`references/hardening.md`. `references/distros.md` maps each step to Ubuntu/Debian, the RHEL
family, NixOS, Proxmox VE and Talos.

```bash
# hook: allow
lx logs db-prod-1 --since 2h --priority err
lx logs db-prod-1 --since 30m --unit postgresql.service --limit 100
lx storage db-prod-1
lx net db-prod-1
```

```bash
# hook: pass
ssh db-prod-1 systemctl status postgresql --no-pager
ssh db-prod-1 'journalctl -u postgresql --since -1h -n 200 --no-pager' | lx redact
```

**Step 4 — Report.** Alias (and `[PROD]`) · what is broken · the evidence (command + the line that
proves it) · root cause with a confidence · **remediation for the human**, numbered, each with its
blast radius and the infrastructure-repository change that makes it permanent (role / module /
`configuration.nix` / cloud-init file and the value) · what was not verified (`needs root` items
included). Stop after three unresolved hypotheses and say so.

Remediations are written out for the user to run, never executed:

```bash
# hook: ask — NEVER run; hand to the user
ssh -t db-prod-1 sudo systemctl restart postgresql
ssh -t web1 sudo apt-get install --only-upgrade openssl
```

## Deliberately not implemented

Not gaps — decisions. Do not work around them with raw `ssh`: the guard asks or denies, and routing
around a prompt is the one thing that is never acceptable. Tell the user what to run instead.

- **Every host change**: restarts, package installs or upgrades, config edits, firewall or network
  changes, reboots, user and key management. Host fixes go into the infrastructure repository
  through an MR; a live edit drifts from the source of truth and is reverted by the next run.
- **Remote sudo**, interactive sessions, `-t`, tunnels, port forwarding, agent forwarding, uploads.
- **Follow modes** (`journalctl -f`, `tail -f`, `watch`).
- **Host-key bypasses and password auth** (`StrictHostKeyChecking=no`, `sshpass`).
- **Reading or copying private keys**, or editing `~/.ssh/config` / `known_hosts`.
- **Talos nodes** — no ssh by design; use `talosctl` read verbs (see `references/distros.md`).

## References

`references/triage.md` (symptom decision tree) · `references/networking.md` (renderers, bonds,
routes, firewall, DNS) · `references/storage.md` (disk full, LVM, ZFS, md RAID, SMART, read-only
remounts) · `references/hardening.md` (sshd, exposure, sudo, updates, file modes; severity rubric) ·
`references/distros.md` (Ubuntu/Debian, RHEL family, NixOS, Proxmox VE, Talos).
