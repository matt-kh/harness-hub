# Bundle: linux

Linux hosts for agents, reached over the aliases in your `~/.ssh/config`: read-only by default,
with guard sections 82 (definitions) and 83 (rules) that judge every `ssh`, `scp`, `rsync` and
`sftp` call and the destructive local storage and network tools, the read-only `lx` CLI, the
[`linux` skill](../../bundles/linux/skills/linux/SKILL.md) with its runbooks, and two read-only
agents.

## The `lx` CLI

[`lx`](../../bundles/linux/skills/linux/scripts/lx.py) is a single-file stdlib python CLI (3.9+),
linked onto `PATH` by `harness apply`. It reaches **only** the `Host` aliases of `~/.ssh/config`
(and the files it `Include`s; no wildcards, no `user@ip`), and every remote call is

```
ssh -o BatchMode=yes -o ConnectTimeout=<linux.ssh_timeout> -o LogLevel=ERROR -T -n -- ALIAS '<fixed script>'
```

— no tty, no password prompts, host-key checking left to your ssh config (never disabled), one
fixed read-only script per subcommand whose every probe tolerates a missing tool. Output is parsed
and passed through the shared redactor locally, so raw dumps never reach a model context. Human
Markdown by default, `--json` for machines; stderr banner `host=<alias> os=<ID VERSION_ID> [PROD]`.
Exit codes: `0` clean, `1` findings (or a usage error), `2` access error (not an alias,
unreachable, key auth failed, host key not verified, timeout).

| Subcommand | What it reads on the host |
|---|---|
| `hosts` | nothing remote: aliases with HostName, User, Port, and role / notes from `linux.inventory`; never `IdentityFile` |
| `check HOST` | `id -un`, `hostname`, `uname -sr`, os-release — reachability and key auth |
| `facts HOST` | os-release, `uname -srm`, `hostname -f`, `/proc/uptime`, `nproc`, `/proc/cpuinfo` model, `/proc/meminfo`, `systemd-detect-virt`, `/proc/1/comm`, timezone, `pveversion`, `nixos-version` |
| `health HOST` | `systemctl list-units --failed`, `/proc/loadavg`, `df -PT` and `df -PTi`, `/proc/meminfo`, `/proc/pressure/memory`, OOM lines in `journalctl -k --since -24h`, `/var/run/reboot-required`, `needs-restarting -r`, NixOS booted vs current kernel, `timedatectl show` |
| `logs HOST [--since 1h] [--limit 200] [--unit U] [--priority P]` | `journalctl --no-pager -q --utc -o short-iso --since … -n …` (never a follow mode; arguments validated), else the tail of `/var/log/messages` or `syslog` |
| `net HOST` | `ip -br addr`, `ip -br link`, `ip route`, `ip -6 route show default`, `ip -o -d link show` (bonds, VLANs, bridges), netplan files and renderer, renderer services, ifupdown / ifcfg presence, firewall services, `nft list tables`, `ufw status`, `firewall-cmd --state`, `/etc/resolv.conf`, `resolvectl dns` |
| `storage HOST` | `lsblk -J` (or `-P`), `findmnt`, `df -PT`, `lvs` / `vgs`, `zpool list` / `zpool status -x`, `/proc/mdstat`, `smartctl -H` per disk |
| `audit HOST` | `sshd -T` (else the sshd config files, approximate), `ss -Htuln`, sudoers mode / readability / counts (never contents), `apt list --upgradable` or `dnf --cacheonly check-update` / `updateinfo`, automatic-update settings and timers, SUID count in `/usr`, world-writable files in `/etc` |
| `redact` | nothing remote: stdin filter (JSON or text) with `linux.redact_extra_re` |

What needs root (SMART, LVM on most distributions, `nft list ruleset`, `sshd -T`, other users'
journal) is reported as `needs root` with the command for you to run; `lx` never uses sudo.

## Skill and agents

- [`linux`](../../bundles/linux/skills/linux/SKILL.md) — when to use which subcommand, the guard
  table, prod behaviour, and the runbooks
  [triage](../../bundles/linux/skills/linux/references/triage.md),
  [networking](../../bundles/linux/skills/linux/references/networking.md),
  [storage](../../bundles/linux/skills/linux/references/storage.md),
  [hardening](../../bundles/linux/skills/linux/references/hardening.md) (severity rubric) and
  [distros](../../bundles/linux/skills/linux/references/distros.md) (Ubuntu/Debian, RHEL family,
  NixOS, Proxmox VE, Talos).
- [`linux-triage`](../../bundles/linux/agents/linux-triage.md) — incident → root cause plus
  remediation commands for you, with their blast radius and the infrastructure-repository change.
- [`linux-auditor`](../../bundles/linux/agents/linux-auditor.md) — Critical / Warnings /
  Suggestions posture review; every fix is a file and value in the infrastructure repository.

## Guard


- Reads are free, production included. `ssh HOST <command>` passes when **every** clause of the
  remote command (split on `;`, `&&`, `||`, `|`, `&` and newlines, inside quotes too) is on the
  read-only allow-list: `cat`, `head`, `tail` (no `-f`), `ls`, `stat`, `uname`, `uptime`, `df`,
  `du`, `free`, `lsblk`, `findmnt`, `ps`, `grep`, `journalctl` (no `-f`, no vacuum), `systemctl
  status|show|is-*|list-*|cat`, `dmesg` (no `-C`/`-w`), the `ip` show forms, `ss`, `nft list`,
  `iptables -L|-S`, `ufw status`, `resolvectl status|query`, `networkctl status|list`, `netplan
  get|status`, `nmcli` show forms, `zpool status|list|get|iostat`, `zfs list|get`, `lvs`/`vgs`/
  `pvs`, `mdadm --detail|--examine`, `smartctl -a|-H|-i`, `sshd -T`, `apt list`, `dpkg -l`,
  `rpm -q`, `top -b -n1` and a few more.
- Everything else on a host **asks**, with `host=<alias>` and `[PROD]` (alias matching
  `linux.prod_re`) in the reason: a clause off the allow-list, remote `sudo`, `sh -c`, `eval`,
  `$(…)`, backticks, `$VAR`, redirections (except `2>/dev/null`, `2>&1`), heredocs and
  `cat script | ssh HOST bash`; interactive `ssh HOST` and `-t`; tunnels and forwarding (`-L -R
  -D -W -N -f -A -X`, `ProxyCommand`, `RemoteCommand`); uploads (`scp`/`rsync` to `HOST:`),
  `rsync --rsync-path`, `sftp` and `ssh-copy-id`. Downloads (`scp HOST:/path .`) pass. On prod,
  the agent hands you remediations as suggestions with their blast radius.
- **Denied:** `StrictHostKeyChecking=no|off` and `UserKnownHostsFile=/dev/null` in any spelling
  (`-o X=Y`, `-oX=Y`, `-o 'X Y'`, `GIT_SSH_COMMAND`, `RSYNC_RSH`, `rsync -e`, `git -c
  core.sshCommand`, an ssh_config written through a heredoc) — use `accept-new` or a checked
  `known_hosts` entry; `sshpass` — use keys through `ssh-agent`. Copying anything but `*.pub`
  out of `~/.ssh` (`scp`, `rsync`, `sftp put`, `ssh-copy-id -i <private>`, `ssh … < key`) is
  denied and **never yields**, even when a repository owns the `infrastructure` domain.
- Locally, `dd of=/dev/…`, a redirection, `cp` or `tee` into `/dev/…`, `wipefs -a`, `sgdisk`,
  `sfdisk`, `parted`, `fdisk`, `gdisk`, `mkfs*`, `mkswap`, `blkdiscard`, `cryptsetup
  luksFormat|erase` on a device (loop, nbd and mapper devices included; a `$VAR` target or
  operands appended by `xargs` count as unknown) **ask**; on image files they pass (`mkfs.ext4
  disk.img`, `dd if=/dev/zero of=test.img`), as do the listing forms (`fdisk -l`, `sfdisk -l`,
  `sgdisk -p`, `parted -l`, bare `wipefs`). LVM create/remove, `zpool create|destroy|labelclear`,
  `zfs destroy|rollback` and `mdadm --create|--zero-superblock` always ask.
- Firewall and network changes ask: `nft flush|add|delete|insert|replace|-f`, `ufw
  enable|disable|allow|deny|…`, `netplan apply|try|generate|set`, `nmcli` mutations, `ip <object>
  add|del|set|change|replace|flush`, `iptables -A|-I|-D|-F|-P|-X|-N` and `iptables-restore`.
- Wrappers do not hide a command: `sudo`, `env`, `timeout`, `nohup`, `xargs`, `cd x && …`,
  `;`-chains, `sh -c "…"`, `eval` and `$(…)` are unwrapped before the rules run.
- Host fixes go into your infrastructure repository through a merge request, never as live
  edits.

Config: `linux.prod_re` (case-insensitive ERE on host aliases; same default as `k8s.prod_re`),
`linux.inventory` (optional file of hosts: alias, role, notes; empty = `~/.ssh/config` only),
`linux.ssh_timeout` (connect timeout in seconds for the bundle's own SSH calls),
`linux.redact_extra_re` (extra Python regex masked by `lx redact` and `lx logs`). Your keys stay
in `~/.ssh`; the bundle never reads them.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| The agent asks before a read-only `ssh HOST …` | one clause of the remote command is off the allow-list, or uses `$VAR`, `$(…)` or a redirection | read the reason (it names the clause); drop the redirection, pass literal arguments, or use `lx` |
| `journalctl -f` / `tail -f` asks | a follow mode never returns | pass `--since 1h` or `-n 200` |
| `ssh -o StrictHostKeyChecking=no` is denied | host-key checking protects against a spoofed host | `ssh -o StrictHostKeyChecking=accept-new HOST …` for a first contact, or add the key with `ssh-keyscan HOST` after comparing the fingerprint |
| Host-key prompt on a new host makes the command hang | no `known_hosts` entry and no tty | add the entry yourself (see above); never disable the check |
| `scp ~/.ssh/id_… HOST:` is denied, even in a repository that owns `infrastructure` | private keys never leave the machine (never yields) | copy the `.pub` file, or install it with `ssh-copy-id -i ~/.ssh/<key>.pub HOST` (asks) |
| `mkfs` / `wipefs` / `dd` on an image asks | the target is a `$VAR`, comes from `xargs`, or the command `cd`s into `/dev` | pass a literal image path |
| Prod hosts not flagged | your aliases do not match `linux.prod_re` | adjust the regex in `local/harness.toml` and run `harness apply` |
| An aliased host still runs a `ProxyCommand` or `RemoteCommand` | the guard sees the command line, not `~/.ssh/config` | keep such settings out of the aliases agents use |
| `lx` exits 2 with `not a Host alias` | the host is not a `Host` block in `~/.ssh/config` (or is a wildcard / `user@ip`) | add a `Host <alias>` block yourself; `lx hosts` lists what it sees |
| `lx check` says `key auth failed` | `BatchMode=yes` never prompts: no key in the agent, or the key is not authorised | `ssh-add`, then `lx check <alias>`; doctor check `ssh-agent` |
| `lx` shows `needs root` | the read requires root (SMART, LVM, `nft list ruleset`, `sshd -T`) | run the printed `sudo …` command yourself; `lx` never uses sudo |
| `lx logs` hints that other users' messages are hidden | the login is not in the `adm` / `systemd-journal` group | add the agent's login to that group in the infrastructure repo, or read as yourself |
| `lx` times out on one host | a probe hangs (stuck NFS mount, D-state I/O) | a finding in itself; `lx check` first, then raise `--timeout` |
| `sudo` on a host asks every time | remote privilege escalation is never read-only | hand the command to the user, or read files your login can read |

<!-- generated:begin source=bundles/linux/bundle.toml -->
## Summary

Linux hosts over SSH aliases: read-only lx CLI, skill and triage / audit agents; guards on remote mutations, interactive sessions, tunnels, uploads, disabled host-key checking, copied private keys and local disk / network changes

Governs Linux hosts reached over SSH aliases, and the destructive local storage and network
tools. Guard sections 82 (definitions: clause lexer, ssh / scp / rsync parsing, the remote
read-only allow-list, block-device targets) and 83 (rules): `ssh HOST <command>` passes when every
clause of the remote command is on a read-only allow-list and asks otherwise (remote sudo,
`sh -c`, substitutions and redirections included), with `host=<alias> [PROD]` in the reason;
interactive sessions, `-t`, tunnels and forwarding, uploads, `sftp` and `ssh-copy-id` ask;
`StrictHostKeyChecking=no`, `UserKnownHostsFile=/dev/null` and `sshpass` deny; copying a private
key out of `~/.ssh` denies and never yields. Locally, `dd of=/dev/…`, `mkfs`, `wipefs`, partition,
LVM, ZFS and RAID changes on block devices, and firewall / network changes (`nft`, `ufw`,
`netplan`, `nmcli`, `ip … add|del|set`, `iptables -A|-D|-F`) ask; the same tools on image files
pass. Ships the stdlib `lx` CLI (hosts, check, facts, health, logs, net, storage, audit, redact —
every remote call `ssh -o BatchMode=yes -o ConnectTimeout=… -T` to a `~/.ssh/config` alias with one
fixed read-only script, output parsed and redacted locally), its skill and runbooks, and the
read-only linux-triage / linux-auditor agents. Host fixes go into the infrastructure repository
through a merge request.

- **Depends on:** `core`
- **Stability:** experimental
- **Domain / posture:** infrastructure / read-only

## Components

Stable ids derived from the path, with their [taxonomy](../reference/taxonomy.md) facets (domain shown only where it differs from the bundle's). All bundles: [catalog](../catalog.md).

**Skills**

- `linux/skills/linux` — control: guide · function: client · posture: read-only · model: execute · yields: declaration

**Agents**

- `linux/agents/linux-auditor` — control: guide · function: review · posture: read-only · model: execute · yields: name
- `linux/agents/linux-triage` — control: guide · function: investigate · posture: read-only · model: execute · yields: name

**Rules**

- `linux/rules/82-linux` — control: guide · function: govern · yields: text

**Guard sections**

- `linux/guard.d/82-linux` — control: sensor · function: govern · decisions: helper (no rules) · yields: n/a
- `linux/guard.d/83-linux-rules` — control: sensor · function: govern · decisions: deny 3 · ask 9 · yields: declaration

**Permission lists**

- `linux/permissions` — control: guide · function: govern · decisions: deny 5 · ask 21 · allow 8 · yields: config

**CLIs**

- `linux/bin/lx` — function: client · posture: read-only · yields: n/a

**Doctor checks** (function: setup · posture: read-only; table below): `linux/doctor/lx-cli`, `linux/doctor/ssh-agent`, `linux/doctor/ssh-aliases`, `linux/doctor/ssh-binary`

**Manual steps** (function: setup; table below): `linux/steps/ssh-agent-key`, `linux/steps/ssh-aliases`

## Requirements

### Binaries

| binary | min version | install | optional | why |
|---|---|---|---|---|
| `python3` | 3.9 |  | no | The bundle's tooling is stdlib python. |
| `ssh` |  |  | no | Hosts are reached through the OpenSSH client and the aliases in ~/.ssh/config. |

### Configuration

| key | type | required | default | description |
|---|---|---|---|---|
| `linux.inventory` | string | no | `""` | Optional path to a host inventory file (one host per line: alias, role, notes); aliases themselves come from ~/.ssh/config. Empty = ~/.ssh/config only. LINUX_INVENTORY. |
| `linux.prod_re` | string | no | `"(^\|[-_./:])(prod\|production)([-_./:]\|$)"` | Case-insensitive POSIX ERE on host aliases marking production ([PROD] in guard reasons; remediations become suggestions only). LINUX_PROD_RE. |
| `linux.redact_extra_re` | string | no | `""` | Extra Python regex of token shapes masked on top of the built-in list, applied by `lx redact` and `lx logs`. LINUX_REDACT_EXTRA_RE. |
| `linux.ssh_timeout` | integer | no | `10` | Connect timeout in seconds for every SSH call the bundle's tooling makes (ConnectTimeout). LINUX_SSH_TIMEOUT. |

### Secrets (never in harness.toml)

| id | where | written by | mode | rotate |
|---|---|---|---|---|
| `ssh_keys` | `~/.ssh/* (except *.pub)` | human (ssh-keygen) | 0600 | ssh-keygen -t ed25519 a new key, install its .pub on each host yourself (ssh-copy-id -i KEY.pub HOST), then remove the old line from each host's authorized_keys |

## Manual steps

<a id="ssh-aliases"></a>

### ssh-aliases — Give every host an alias in ~/.ssh/config

*once per machine · needs nothing but a terminal · ~5 min*

**Why:** lx and the agents reach hosts only through Host aliases (no user@ip, no wildcards), so each machine needs one; the alias also decides [PROD] through linux.prod_re.

**How:**

Add one block per host to `~/.ssh/config` (or a file it `Include`s), for example:
```
Host web1
  HostName 192.0.2.10
  User deploy
```
Name production hosts so they match `linux.prod_re` (default: a `prod`/`production` segment, e.g.
`db-prod-1`). Optionally list role and notes per alias in the file `linux.inventory` points at.
Then connect once yourself to accept and check the host key (`ssh web1 true`); agents never answer
host-key prompts. `lx hosts` shows what was picked up.

**Verify:** `lx hosts --json | grep -q '"alias"'` (exit 0)

<a id="ssh-agent-key"></a>

### ssh-agent-key — Load your SSH key into ssh-agent

*once per machine · needs nothing but a terminal · ~2 min*

**Why:** Every lx call uses BatchMode=yes: no password or passphrase prompts, so the key must already be in an agent (or be passphrase-less, which is not recommended).

**How:**

Start an agent if your desktop does not (`eval "$(ssh-agent)"`), then `ssh-add` your key; `ssh-add -l` lists the loaded fingerprints. `lx check <alias>` confirms auth.

**Verify:** `ssh-add -l >/dev/null 2>&1` (exit 0)

## Doctor checks

| id | severity | offline | fix |
|---|---|---|---|
| `lx-cli` | fail | runs | `harness apply` |
| `ssh-binary` | fail | runs | `install the OpenSSH client with your OS package manager (openssh-client / openssh-clients)` |
| `ssh-aliases` | warn | runs | [ssh-aliases](#ssh-aliases) |
| `ssh-agent` | warn | runs | [ssh-agent-key](#ssh-agent-key) |

## Guides and sensors

Guides steer the agent before it acts; sensors detect at or after the action. Pairing: **paired**; guides with a declared check: 5 of 5.

| side | kind | ref | note | pairs with |
|---|---|---|---|---|
| guide | rule | `rules/82-linux.md` | read-only over ssh aliases, prod remediations are suggestions, host fixes through the infra repository | `guard.d/83-linux-rules.sh` |
| guide | skill | `skills/linux` | the lx CLI: aliases, triage views, bounded logs, redact; distro-aware runbooks | `skills/linux/scripts/tests/run.sh`, `doctor_checks` |
| guide | permission | `permissions.toml` | local host reads allowed, storage and network changes ask, sshpass and disabled host-key checking denied | `permissions-vs-guard`, `guard.d/83-linux-rules.sh` |
| guide | agent | `agents/linux-triage.md` | read-only incident triage that hands remediations to the human | `guard.d/83-linux-rules.sh`, `agent-tools` |
| guide | agent | `agents/linux-auditor.md` | read-only posture review with fixes as infra-repo changes | `guard.d/83-linux-rules.sh`, `agent-tools` |
| sensor | guard | `guard.d/82-linux.sh` | clause lexer, ssh/scp/rsync parsing, remote allow-list and device targets shared by the rules section | — |
| sensor | guard | `guard.d/83-linux-rules.sh` | remote mutations, sessions, tunnels, uploads, host-key checking, sshpass, private keys, local disk and network changes | `rules/82-linux.md`, `permissions.toml`, `agents/linux-triage.md`, `agents/linux-auditor.md` |
| sensor | test | `guard.d/tests.sh` | guard rows incl. bypasses, the guard.env prod regex and the infrastructure yield | — |
| sensor | doctor | `doctor_checks` | the lx CLI, the ssh client, Host aliases and a key in ssh-agent | `skills/linux` |
| sensor | test | `tests/run.sh` | this bundle's rows against core + linux only | — |
| sensor | test | `skills/linux/scripts/tests/run.sh` | the lx CLI against a stub ssh: goldens per subcommand, BatchMode/ConnectTimeout on every call, no tty, no host-key override, bounded logs, redaction | `skills/linux` |
| sensor | lint | `permissions-vs-guard` | each Bash allow/deny rule of permissions.toml run through the guard: no allowed command the guard denies or asks, no denied one it allows | `permissions.toml` |
| sensor | lint | `agent-tools` | read-only agents set no permissionMode and list no write tools | `agents/linux-triage.md`, `agents/linux-auditor.md` |

**Not covered:** The agents' read-only stance is enforced for shell commands by the guard; what lx's fixed remote scripts run is checked by its own test suite (stub ssh), not by the guard. The linux-rules guard section enforces rule text that lives in rules/82-linux.md. The remote allow-list judges the command text ssh sends; what an aliased host's ~/.ssh/config adds (ProxyCommand, RemoteCommand, StrictHostKeyChecking) and commands run through other tools (ansible, pssh, mosh) are not sensed. Device targets are judged by path: a relative path is a device only when the command or cwd is in /dev.

## Uninstall

Kept on uninstall: `~/.ssh/**`

Your SSH keys, config, known_hosts and inventory file are yours; uninstall removes only the rendered skill, agents, lx link, rule, permissions and guard sections.
<!-- generated:end -->
