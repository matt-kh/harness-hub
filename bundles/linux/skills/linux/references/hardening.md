# Hardening review and severity rubric

`lx audit HOST` gathers the evidence: sshd settings (`sshd -T` when the login can run it, else the
config files — approximate), listening sockets, the sudoers shape (mode, readability and counts,
never contents), automatic updates, pending updates, SUID files in `/usr` and world-writable files
in `/etc`. `lx net` adds firewall state, `lx health` the reboot flag. Use the rubric below
verbatim; on a `[PROD]` alias escalate every severity by one level and say so.

## 1. Severity rubric

| Finding | Severity | Fix in the infra repo |
|---|---|---|
| `PermitRootLogin yes` | Critical | sshd drop-in `PermitRootLogin no` (or `prohibit-password` for break-glass with a forced command) |
| `PermitEmptyPasswords yes` | Critical | `PermitEmptyPasswords no` |
| `PasswordAuthentication yes` on an internet-facing host | Critical (else Warning) | `PasswordAuthentication no`, keys or certificates only |
| `KbdInteractiveAuthentication yes` without MFA intent | Warning | `KbdInteractiveAuthentication no` |
| Database / cache / admin API on `0.0.0.0` or `[::]` (redis 6379, memcached 11211, mongodb 27017, elasticsearch 9200, docker 2375, rpcbind 111, telnet 23, ftp 21) | Warning (Critical without a host firewall) | bind to a private address or loopback in the service config; firewall rule |
| No active host firewall | Warning | an nftables / firewalld / ufw profile from the infra repo |
| Security updates pending | Warning (Critical when > 30 days or a known-exploited CVE) | enable automatic security updates; patch window |
| Automatic security updates off | Warning | `unattended-upgrades` / `dnf-automatic` / `system.autoUpgrade` |
| Reboot pending for a kernel or libc update | Warning | maintenance window; consider livepatch where offered |
| World-writable file in `/etc` | Warning | owner and mode in the config-management resource |
| `/etc/sudoers` readable by a non-root login | Warning | `0440 root:root` via the sudo role |
| `NOPASSWD` rules | Suggestion (Warning for `ALL`) | scope them to commands; review who holds them |
| `X11Forwarding yes` on a server | Suggestion | `X11Forwarding no` |
| `MaxAuthTries` above 6 | Suggestion | default 6 or lower |
| `PermitRootLogin prohibit-password` | Suggestion | `no`, unless documented break-glass |
| SUID count far above a same-release baseline | Suggestion (Warning with unknown binaries) | remove the package or the bit through config management |
| Agents log in as root (`lx` warns) | Warning | an unprivileged alias for agents |

## 2. sshd

- `sshd -T` prints the *effective* configuration (after `Include` and defaults) but needs root on
  most distributions because it loads the host keys; `lx` then falls back to grepping
  `/etc/ssh/sshd_config.d/*.conf` and `/etc/ssh/sshd_config` (first value wins, `Match` blocks
  ignored) and says so in `source`. For the exact answer, **for the human**: `sudo sshd -T`, and for
  one user `sudo sshd -T -C user=deploy,host=client.example.com,addr=192.0.2.5`.
- Ubuntu 22.04+ and Debian 12 ship `Include /etc/ssh/sshd_config.d/*.conf` as the first line, so a
  drop-in overrides the main file; cloud images often add `50-cloud-init.conf` with
  `PasswordAuthentication yes`. RHEL 9 does the same with `50-redhat.conf`.
- Algorithms: `ssh -Q kex` and friends are local; for the server side ask for `sudo sshd -T | grep -E
  '^(kexalgorithms|ciphers|macs|hostkeyalgorithms) '`.

## 3. Exposure

- `lx audit` lists listening sockets with scope `all`, `address` or `loopback`; process names need
  root (`ss -p`): **for the human** `sudo ss -tulpn`.
- Compare with what the host is for (`role` in the inventory). Every `all` socket that is not the
  host's service or sshd is a question for the owner.
- Containers publish ports through iptables/nftables NAT that `ss` may not show as the container's
  process; check `docker ps` with the human.

## 4. Privilege

- `lx` never reads sudoers rules. It reports the mode, whether this login can read the files, the
  number of `/etc/sudoers.d` entries and — only when readable — how many lines contain `NOPASSWD`.
- Group membership of the login (`sudo`, `wheel`, `admin`) shows whether the agent alias itself can
  escalate; it should not.
- Rule review is the human's: `sudo visudo -c` (syntax) and `sudo cat /etc/sudoers.d/*`.

## 5. Updates

| Family | Pending (lx) | Automatic updates (lx) | For the human |
|---|---|---|---|
| Debian / Ubuntu | `apt list --upgradable` (cache only; stale until `apt update` runs) | `APT::Periodic::Unattended-Upgrade "1"` in `20auto-upgrades`, `apt-daily-upgrade.timer` | `sudo unattended-upgrade --dry-run -d`, `sudo apt update` |
| RHEL family | `dnf --cacheonly check-update` / `updateinfo list --security` (the login's cache; may be empty) | `dnf-automatic(-install).timer`, `apply_updates` in `automatic.conf` | `sudo dnf check-update`, `sudo dnf updateinfo list --security` |
| NixOS | — (generations, not packages) | `nixos-upgrade.timer` (`system.autoUpgrade`) | review `nix flake update` in the repo |
| Proxmox VE | Debian under the hood; enterprise vs no-subscription repository decides what arrives | same as Debian | `pveversion -v`, the node's Updates panel |

## 6. File modes

- World-writable files in `/etc` (`lx` lists up to 50): any user can change configuration that
  root reads — fix owner and mode in the config-management resource that creates the file.
- SUID count in `/usr`: compare against a freshly installed host of the same release; the absolute
  number varies (20–40 is common). Unknown binaries are a Warning — **for the human**
  `sudo find /usr -xdev -perm -4000 -type f -newer /etc/os-release`.

## 7. Report shape

**Scope** (alias, `[PROD]`, distro, what was read) · **Critical** · **Warnings** · **Suggestions** ·
**Not verified** (every `needs root` item and the exact command that closes it). Each finding:
setting · evidence (`lx audit HOST` field) · fix as a file and value in the infra repo.
