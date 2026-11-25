# Ubuntu (`os-install` / `ubuntu-autoinstall`, rendered by prov)

Ubuntu Server 22.04 and 24.04 install unattended with **autoinstall** (subiquity), read from a
cloud-init **NoCloud** data source. `prov` renders that seed from an `os-install` item whose
backend is `ubuntu-autoinstall`; nothing else in this flow is hand-written.

## What prov renders

`<root>/os-install/<name>/rendered/`:

| File | Purpose |
|---|---|
| `user-data` | `#cloud-config` with the `autoinstall:` section: identity / users and ssh keys, locale, keyboard, timezone, network (netplan v2), storage layout, packages |
| `meta-data` | `instance-id` and `local-hostname` for NoCloud |
| `kernel-cmdline` | the kernel arguments the installer needs: `autoinstall ds=nocloud` |

Storage layouts (`[storage] disks` + `[ubuntu-autoinstall.storage] layout` in `spec.toml`): `lvm`
(LVM over the listed disks), `zfs` (ZFS root, single disk, following curtin's example — the least
exercised layout; test it in a VM), `mdraid` (software RAID across the listed disks). Every disk
in `storage.disks` may be wiped.

`prov validate` checks the envelope (`api_version`, `kind`, `backend`, the item path), the kind
and backend schema, cross-field rules (a user with an ssh key, addresses in CIDR, gateways and
nameservers of the right family), the rendered files and staleness; it runs `cloud-init schema`
when cloud-init is installed and reports `skipped` otherwise. `--json` prints the findings as one
document.

## Example spec.toml (documentation values)

`<root>/os-install/web1/spec.toml`:

```toml
api_version = "prov/v1alpha1"
kind = "os-install"
backend = "ubuntu-autoinstall"
hostname = "web1"
domain = "example.com"
arch = "amd64"
firmware = "uefi"
timezone = "Etc/UTC"
locale = "en_US.UTF-8"
keyboard = "us"

[[users]]
name = "ops"
groups = ["adm", "sudo"]
sudo = true
ssh_authorized_keys = [
  "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEXAMPLEEXAMPLEEXAMPLEEXAMPLEEXAMPLEEXAMPLE ops@example.com",
]

[network.dns]
nameservers = ["192.0.2.53"]
search = ["example.com"]

[[network.interfaces]]
name = "eth0"
addresses = ["192.0.2.21/24"]
gateway4 = "192.0.2.1"

[storage]
disks = ["/dev/vda"]

[ubuntu-autoinstall]
release = "24.04"
packages = ["qemu-guest-agent"]

[ubuntu-autoinstall.storage]
layout = "lvm"
```

The authoritative keys are `prov schema os-install --backend ubuntu-autoinstall`; the keys above
may lag behind it — prefer `prov init os-install/<name> --backend ubuntu-autoinstall` (or a copy
of an existing item of the same role) as the starting point.

## The seed

The NoCloud seed is a small ISO with volume label `CIDATA` holding `user-data` and `meta-data`.
`prov plan` prints the exact command; typically one of:

```bash
# hook: pass (writes a local file)
cloud-localds seed.iso user-data meta-data
xorriso -as genisoimage -output seed.iso -volid cidata -joliet -rock user-data meta-data
```

Boot targets:

- **Local VM**: the Ubuntu live-server ISO as cdrom plus `seed.iso` as a second cdrom
  (`local-vm.md`). The installer finds the CIDATA volume; add `autoinstall ds=nocloud` to the kernel
  command line (`kernel-cmdline`), or accept the installer's confirmation prompt.
- **Bare metal**: write the live-server ISO to a USB stick and the seed to a second stick or a
  CIDATA partition — **human**: `dd if=ubuntu-24.04-live-server-amd64.iso of=/dev/sdX bs=4M
  conv=fsync` (the guard asks; check `/dev/sdX` with `lsblk` first). At the GRUB menu press `e`
  and append `autoinstall ds=nocloud` to the `linux` line (the plan's option B).
- **PXE / HTTP**: serve the seed over HTTP and pass `ds=nocloud;s=http://192.0.2.5/web1/` on the
  kernel command line. Needs a DHCP/TFTP or iPXE setup the human owns; it does not work from WSL2
  NAT (`local-vm.md`).
- **Proxmox VE guest**: upload the ISOs to the node's storage and attach them; every `qm` write is
  the human's (`proxmox.md`).

## After install

`lx check web1`, `lx facts web1` (release, kernel), `lx storage web1` (layout as rendered),
`lx net web1` (addresses), `lx audit web1` (sshd: password auth off, keys only). The installer
log on the host: `ssh web1 cat /var/log/installer/autoinstall-user-data` (read-only; it holds no
secret beyond the password hash if one was set).

Common failures: the installer stops at an interactive screen (a key missing from `autoinstall`,
or the seed was not found — check the CIDATA label and `kernel-cmdline`), storage errors (the
disk path differs on the real machine: use `/dev/disk/by-id/…` in `storage.disks` of `spec.toml`), no network
(interface name differs: match by MAC).
