# Distribution notes

`lx facts HOST` prints `id`, `id_like` and `version_id` from `/etc/os-release`; pick the column
below from `id` (or `id_like` for derivatives). Reads are read-only; **for the human** marks commands
that need root or change the host.

## 1. Quick map

| Concern | Ubuntu / Debian | RHEL family (RHEL, Rocky, Alma, CentOS Stream, Fedora) | NixOS | Proxmox VE (Debian-based) |
|---|---|---|---|---|
| Packages (read) | `ssh HOST apt list --installed`, `ssh HOST dpkg -l PKG` | `ssh HOST rpm -q PKG`, `ssh HOST rpm -qa` | the system closure in the repo's flake / configuration | as Debian; plus `pveversion -v` (asks — not on the allow-list) |
| Pending updates | `lx audit` (`apt list --upgradable`) | `lx audit` (`dnf --cacheonly …`) | generations: compare the flake lock | as Debian |
| Reboot needed | `/var/run/reboot-required(.pkgs)` (`lx health`) | `needs-restarting -r` (`lx health`; from `dnf-utils` / `yum-utils`) | booted vs current kernel (`lx health`) | as Debian; plus the running kernel vs `proxmox-kernel-*` installed |
| Network renderer | netplan (server), NetworkManager (desktop), ifupdown (Debian) | NetworkManager keyfiles (8+), ifcfg (7) | `networking.*` / `systemd.network` | ifupdown2, `/etc/network/interfaces` |
| Firewall | ufw (front-end to nftables) | firewalld | `networking.firewall` (nftables or iptables) | pve-firewall (cluster / host / VM levels) |
| MAC | AppArmor (`ssh HOST aa-status` asks; **for the human** `sudo aa-status`) | SELinux (`ssh HOST getenforce` asks; **for the human** `sudo ausearch -m avc -ts recent`) | AppArmor optional | AppArmor for containers |
| Logs | journald; `/var/log/syslog` with rsyslog | journald; `/var/log/messages` | journald only | journald; `/var/log/pve/tasks/` |
| Auto updates | unattended-upgrades | dnf-automatic | `system.autoUpgrade` | unattended-upgrades (not default) |
| Where the fix goes | role / cloud-init in the infra repo | role / kickstart in the infra repo | the NixOS module in the flake | the node config in the infra repo (or Proxmox's API via Terraform/Pulumi) |

## 2. Ubuntu / Debian

- Cloud images run cloud-init: `/etc/netplan/50-cloud-init.yaml` and
  `/etc/ssh/sshd_config.d/50-cloud-init.conf` are generated — change the user-data, not the file.
- `apt list --upgradable` reads the local cache; if `apt-daily.timer` is disabled the count is stale.
- Ubuntu Pro / livepatch: `ssh HOST cat /var/lib/ubuntu-advantage/status.json` is large — prefer
  `pro status` (asks; **for the human**).
- Snap mounts (`/snap/*`, squashfs) are always 100 % full by design; `lx` hides them.

## 3. RHEL family

- SELinux denials look like permission errors in the application log; the human confirms with
  `sudo ausearch -m avc -ts recent` and fixes with a policy module or a boolean in the infra repo,
  never with `setenforce 0`.
- `firewall-cmd --state` works for unprivileged users on many hosts; `--list-all` usually needs root.
- Subscription state (RHEL): `subscription-manager status` is the human's.
- Installed kernels: `ssh HOST rpm -q kernel`. Install history (`rpm -qa --last`) currently asks
  (the guard reads `--last` as a package change), as does `dnf history`: hand
  `dnf history list` to the user.

## 4. NixOS

- The host is a build product: the fix is always the configuration in the repo plus a
  `nixos-rebuild switch` (or deploy-rs / colmena) by the human. `nix-env -i` on the host is drift.
- `/run/current-system` is the active generation, `/run/booted-system` what booted; `lx health`
  compares their kernels.
- `nixos-version` (in `lx facts`) gives the release and the configuration revision when built from a
  flake with `system.configurationRevision`.
- Units come from the store: `ssh HOST systemctl cat UNIT` shows the store path of the generated
  unit file.

## 5. Proxmox VE hosts

- The node is Debian plus Proxmox packages; treat it like Debian for the OS, but guest, storage and
  cluster state come from Proxmox tools, all of which need root or the API: `pvecm status`
  (quorum), `pvesm status` (storage), `qm list` / `pct list` (guests), `ha-manager status`,
  `pvesh get …` pass the guard as `ssh NODE …` reads (they fail without a root login — then they are
  **for the human**); every `qm` / `pct` / `pvesh` write asks.
- Read-only for the agent: `lx storage` (ZFS `rpool`, LVM-thin `pve/data` fill — thin-pool fill at
  100 % freezes every guest on it), `lx net` (bridges `vmbr*`, bonds), `lx logs HOST --unit
  pve-cluster --since 1h`, `lx logs HOST --unit corosync --since 1h`.
- Never restart `pve-cluster` or `corosync` on a cluster member without the human: it can fence the
  node and its guests.

## 6. Talos Linux

Talos has **no SSH and no shell** by design; `lx` does not apply. Read-only access is `talosctl`
against the node's API with the user's talosconfig (never read it):

- `talosctl -n NODE version`, `talosctl -n NODE health` (cluster-level),
  `talosctl -n NODE services`, `talosctl -n NODE logs kubelet --tail 200`,
  `talosctl -n NODE dmesg` (no `--follow`), `talosctl -n NODE get members`,
  `talosctl -n NODE disks`, `talosctl -n NODE mounts`.
- Changes (`apply-config`, `upgrade`, `reboot`, `reset`) are the human's, from the machine config
  in the infra repo. Workload issues on Talos nodes go through the `k8s` skill.

## 7. Other systemd distributions

Arch, openSUSE, Alpine (OpenRC, not systemd: `lx health` cannot list failed units and `lx logs`
falls back to `/var/log/messages`), Container-Optimized OS / Flatcar (read-only root, updates by
image swap; the fix is the image or the Ignition config). `lx facts` reports `init` so the gap is
visible.
