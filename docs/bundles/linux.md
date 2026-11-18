# Bundle: linux

Linux hosts for agents, reached over the aliases in your `~/.ssh/config`: read-only by default,
with guard sections 82 (definitions) and 83 (rules) that judge every `ssh`, `scp`, `rsync` and
`sftp` call and the destructive local storage and network tools. The `lx` CLI (subcommands
`hosts`, `check`, `facts`, `health`, `logs`, `net`, `storage`, `audit`, `redact`), its skill and
the `linux-triage` / `linux-auditor` agents complete the bundle; the guard already lets `lx` pass.

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
`linux.ssh_timeout` (connect timeout in seconds for the bundle's own SSH calls). Your keys stay
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
| `sudo` on a host asks every time | remote privilege escalation is never read-only | hand the command to the user, or read files your login can read |

<!-- generated:begin source=bundles/linux/bundle.toml -->
## Summary

Linux hosts over SSH: read-only by default, guards on remote mutations, interactive sessions, tunnels, uploads, disabled host-key checking, copied private keys and local disk / network changes

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
pass. Host fixes go into the infrastructure repository through a merge request.

- **Depends on:** `core`
- **Stability:** experimental
- **Domain / posture:** infrastructure / read-only

## Components

Stable ids derived from the path, with their [taxonomy](../reference/taxonomy.md) facets (domain shown only where it differs from the bundle's). All bundles: [catalog](../catalog.md).

**Rules**

- `linux/rules/82-linux` — control: guide · function: govern · yields: text

**Guard sections**

- `linux/guard.d/82-linux` — control: sensor · function: govern · decisions: helper (no rules) · yields: n/a
- `linux/guard.d/83-linux-rules` — control: sensor · function: govern · decisions: deny 3 · ask 9 · yields: declaration

**Permission lists**

- `linux/permissions` — control: guide · function: govern · decisions: deny 5 · ask 21 · allow 8 · yields: config

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
| `linux.ssh_timeout` | integer | no | `10` | Connect timeout in seconds for every SSH call the bundle's tooling makes (ConnectTimeout). LINUX_SSH_TIMEOUT. |

### Secrets (never in harness.toml)

| id | where | written by | mode | rotate |
|---|---|---|---|---|
| `ssh_keys` | `~/.ssh/* (except *.pub)` | human (ssh-keygen) | 0600 | ssh-keygen -t ed25519 a new key, install its .pub on each host yourself (ssh-copy-id -i KEY.pub HOST), then remove the old line from each host's authorized_keys |

## Manual steps

_none_

## Doctor checks

_none_

## Guides and sensors

Guides steer the agent before it acts; sensors detect at or after the action. Pairing: **paired**; guides with a declared check: 2 of 2.

| side | kind | ref | note | pairs with |
|---|---|---|---|---|
| guide | rule | `rules/82-linux.md` | read-only over ssh aliases, prod remediations are suggestions, host fixes through the infra repository | `guard.d/83-linux-rules.sh` |
| guide | permission | `permissions.toml` | local host reads allowed, storage and network changes ask, sshpass and disabled host-key checking denied | `permissions-vs-guard`, `guard.d/83-linux-rules.sh` |
| sensor | guard | `guard.d/82-linux.sh` | clause lexer, ssh/scp/rsync parsing, remote allow-list and device targets shared by the rules section | — |
| sensor | guard | `guard.d/83-linux-rules.sh` | remote mutations, sessions, tunnels, uploads, host-key checking, sshpass, private keys, local disk and network changes | `rules/82-linux.md`, `permissions.toml` |
| sensor | test | `guard.d/tests.sh` | guard rows incl. bypasses, the guard.env prod regex and the infrastructure yield | — |
| sensor | test | `tests/run.sh` | this bundle's rows against core + linux only | — |
| sensor | lint | `permissions-vs-guard` | each Bash allow/deny rule of permissions.toml run through the guard: no allowed command the guard denies or asks, no denied one it allows | `permissions.toml` |

**Not covered:** The linux-rules guard section enforces rule text that lives in rules/82-linux.md. The remote allow-list judges the command text ssh sends; what an aliased host's ~/.ssh/config adds (ProxyCommand, RemoteCommand, StrictHostKeyChecking) and commands run through other tools (ansible, pssh, mosh) are not sensed. Device targets are judged by path: a relative path is a device only when the command or cwd is in /dev.

## Uninstall

Kept on uninstall: `~/.ssh/**`

Your SSH keys, config and known_hosts are yours; uninstall removes only the rendered rule, permissions and guard sections.
<!-- generated:end -->
