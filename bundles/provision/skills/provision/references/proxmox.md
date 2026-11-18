# Proxmox VE (planned in prov)

Two different jobs: installing **a Proxmox VE node** itself (bare metal), and creating **guests on
a node** (VM templates and clones). `prov` does not render either yet; explain the steps and keep
the artefacts (`answer.toml`, the template script) in the infrastructure repository.

Every write to a node — `qm`, `pct`, `pvesh create|set|delete`, `pvesm`, `pvecm` changes — is the
human's. Agents read (`qm list`, `qm config VMID`, `pvesh get /nodes`, `pvesm status`, locally or
as `ssh $PROVISION_PVE_HOST qm list`; most need root on the node) and hand writes over, typically
as `ssh <pve-node> qm …` with the node from `provision.pve_host`.

## 1. Installing a node: automated installation

Proxmox VE 8.2+ installs unattended from an **answer file** (`answer.toml`) baked into, or fetched
by, a prepared ISO.

```toml
# answer.toml (documentation values)
[global]
keyboard = "en-us"
country = "us"
fqdn = "pve1.example.com"
mailto = "ops@example.com"
timezone = "Etc/UTC"
root_password_hashed = "<crypt hash supplied by the user>"
root_ssh_keys = ["ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEXAMPLEEXAMPLEEXAMPLEEXAMPLEEXAMPLEEXAMPLE ops@example.com"]

[network]
source = "from-answer"
cidr = "192.0.2.10/24"
gateway = "192.0.2.1"
dns = "192.0.2.53"
filter.ID_NET_NAME_MAC = "*5254001234*"

[disk-setup]
filesystem = "zfs"
zfs.raid = "raid1"
disk_list = ["sda", "sdb"]
```

Check the key names against the Proxmox documentation for the PVE release you install; they
change between releases.

```bash
# hook: pass (local files only)
proxmox-auto-install-assistant device-info                 # on the target (live ISO shell): disk and NIC names
proxmox-auto-install-assistant validate-answer answer.toml
proxmox-auto-install-assistant prepare-iso proxmox-ve_8.4-1.iso --fetch-from iso --answer-file answer.toml
```

`--fetch-from http` (answer served by an HTTP endpoint keyed on the MAC) or `partition` (a
USB partition labelled `proxmox-ais`) are the alternatives; the plan names which.

**Human:** write the prepared ISO to a stick (`dd … of=/dev/sdX`, the guard asks) or mount it in
an IPMI/BMC virtual media slot, boot, wait. Then add the `~/.ssh/config` alias and verify with
`lx check pve1`, `lx facts pve1` (reports `pveversion`), `lx storage pve1` (ZFS `rpool`, mirror
healthy), `lx net pve1` (bridge `vmbr0`).

The answer file holds a password hash and keys: commit it only without plaintext secrets.

## 2. Guests: a cloud-init VM template

A template is a VM with a cloud image as disk and a cloud-init drive; clones get their identity
from `qm set --ipconfig0 --sshkeys`. The agent writes the script into the infrastructure
repository; **the human runs it on the node**:

```bash
# hook: ask — NEVER run; hand to the user (ssh <pve-node> …)
qm create 9000 --name noble-tmpl --memory 2048 --cores 2 --net0 virtio,bridge=vmbr0 \
  --scsihw virtio-scsi-single --ostype l26 --agent enabled=1
qm disk import 9000 noble-server-cloudimg-amd64.img local-lvm
qm set 9000 --scsi0 local-lvm:vm-9000-disk-0 --boot order=scsi0 \
  --ide2 local-lvm:cloudinit --serial0 socket --vga serial0
qm template 9000
qm clone 9000 121 --name web1 --full
qm set 121 --ipconfig0 ip=192.0.2.21/24,gw=192.0.2.1 --nameserver 192.0.2.53 \
  --sshkeys /root/keys/ops.pub
qm start 121
```

Read-only checks the agent may run first (root on the node, or the human runs them):

```bash
# hook: pass
ssh pve1 qm list
ssh pve1 qm config 9000
ssh pve1 pvesm status
ssh pve1 qm cloudinit dump 121 user
```

A Ubuntu autoinstall can also run in a PVE guest: upload the live-server ISO and `prov`'s
`seed.iso` to the ISO storage and attach both (`--ide2`, `--ide3`) — again the human's `qm set`.

## Pitfalls

- `local-lvm` vs `local-zfs` vs a directory storage: the disk reference format differs; read
  `pvesm status` and the storage config first.
- Thin-pool fill: a full `pve/data` thin pool freezes every guest on it (`lx storage`).
- Clustered nodes: VMIDs are cluster-wide; `pvesh get /cluster/nextid` gives a free one.
- Never restart `pve-cluster` or `corosync` without the human: it can fence the node.
