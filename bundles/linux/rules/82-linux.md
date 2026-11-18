## Linux hosts
- **Read-only by default.** Reach hosts by their `~/.ssh/config` aliases; use the `lx` CLI
  (skill `linux`) first, and plain `ssh HOST <command>` only for read-only commands (`cat`,
  `journalctl -u X --since …`, `systemctl status`, `ip -br a`, `df -h`, `lsblk`, `nft list
  ruleset`, …). Never `tail -f` / `journalctl -f`: pass `--since` or `-n`.
- Prod hosts (alias matching `LINUX_PROD_RE`, default: `prod`/`production` as a whole segment)
  read freely — but there **remediations are suggestions for the human**, stated with their
  blast radius, never executed.
- **Prompts (ask):** a remote command any clause of which is not read-only (remote `sudo`,
  `sh -c`, `$(…)`, redirections, restarts, package or config changes), interactive `ssh HOST`
  and `-t`, tunnels and forwarding (`-L -R -D -W -N -f -A`, `ProxyCommand`), uploads (`scp` /
  `rsync` to `HOST:`), `sftp`, `ssh-copy-id`; locally `dd of=/dev/…`, `mkfs`, `wipefs`,
  partitioning and LVM / ZFS / RAID changes on block devices (image files pass), and firewall
  or network changes (`nft`, `ufw`, `netplan apply`, `nmcli`, `ip … add|del|set`,
  `iptables -A|-D|-F`). Reasons carry `host=<alias> [PROD]`. Agents never run these — they
  hand the command to the user.
- **Denied:** `StrictHostKeyChecking=no` and `UserKnownHostsFile=/dev/null` (use `accept-new`
  or a checked `known_hosts` entry), `sshpass` (use keys through `ssh-agent`), and copying
  anything but `*.pub` out of `~/.ssh` — the last even when a repository owns this domain.
- Host fixes go into the infrastructure repository through an MR, never as live edits.

A repository's own instructions for the same action replace this block.
