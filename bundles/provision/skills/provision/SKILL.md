---
name: provision
description: >-
  Provision or reinstall hosts from one reviewed host definition with the external `prov`
  renderer: draft `host.toml`, render and validate the install artefacts (Ubuntu autoinstall /
  cloud-init NoCloud seed today; Proxmox VE answer files, NixOS flakes with disko and Talos
  machine configs follow the same flow), test them in a local VM, land them in the
  infrastructure repository through an MR, print the apply plan, and verify the installed host
  with `lx`. Use when the user wants to provision, install, reinstall or bootstrap Ubuntu,
  Proxmox VE, NixOS or Talos, mentions autoinstall, cloud-init, user-data, an answer file, PXE,
  an install ISO, bare metal, a VM template or nixos-anywhere, or runs /provision. NOT for
  diagnosing a running host (use the linux skill), NOT for cluster workloads (use the k8s
  skill), and NOT for applying anything: every VM create, disk write, talosctl apply and
  nixos-anywhere run is handed to the human.
argument-hint: "<host> [--distro ubuntu|proxmox|nixos|talos] [--target metal|pve|vm]"
model: {{ core.model_policy.execute }}
---

# provision — reviewed host definitions to installed hosts

One versioned `host.toml` per machine is the source of truth. `prov` (the public provision-hub
tool, not part of the hub) renders it into the distro's install artefacts, checks them and prints
the steps that apply them. The agent drafts, renders, validates and tests; the human applies.

**Step 0 — repository-level harness (principle 8).** This is a user-level skill. Read the
repository's declaration first:

```bash
harness repo owns provision/skills/provision   # rc 0 = owned (prints why) → stop; rc 1 = carry on
```

If it is owned (by id or by its domain `infrastructure`), or the repository ships its own skill
for the same workflow (an infrastructure repository's provisioning, NixOS, Talos or Proxmox
skills, a Makefile or task runner that renders hosts), this skill yields: say so in one line,
name the repository-level skill or convention, and stop — nothing below runs and nothing is
written. Never edit the repository's harness to fit this skill. `harness repo` explains
everything the repository declares and any `.claude/skills|agents` name collisions. Run the
check in `provision.infra_root` too when you work there.

## What `prov` renders today

| Distro | Status | Artefacts | Reference |
|---|---|---|---|
| Ubuntu 22.04 / 24.04 | **rendered by prov** | NoCloud seed: autoinstall `user-data`, `meta-data`, `kernel-cmdline`; layouts `lvm`, `zfs`, `mdraid` | `references/ubuntu.md` |
| Proxmox VE | planned in prov | `answer.toml` + `proxmox-auto-install-assistant`; guests from `qm` cloud-init templates | `references/proxmox.md` |
| NixOS | planned in prov | flake + `disko` + `nixos-anywhere` | `references/nixos.md` |
| Talos | planned in prov | machine configs from `talosctl gen config` + patches | `references/talos.md` |

For a planned distro, explain the steps from its reference and keep the artefacts the distro's
own tools produce (`talosctl gen config`, a flake); never write a renderer of your own. Local VM
testing for all of them: `references/local-vm.md`. The whole flow with checkpoints:
`references/workflow.md`.

## Before you start

1. **`prov` present?** `command -v prov`. If it is missing, say so, give the install hint from
   `provision.tool_source` (env `PROVISION_TOOL_SOURCE`, default
   `uv tool install git+https://github.com/matt-kh/provision-hub@<commit-sha>`: the user picks
   and reviews the commit), and still help: explain the steps below and what each artefact will
   contain. Never improvise a renderer or hand-write autoinstall YAML in its place.
2. **Where do host definitions live?** `provision.infra_root` (env `PROVISION_INFRA_ROOT`) is the
   private infrastructure repository; run `prov --root "$PROVISION_INFRA_ROOT" …` there, on a
   branch. When it is unset, work in a scratch root (`mktemp -d`) and say plainly that the result
   must move into the infrastructure repository through an MR before anyone installs from it.
3. **Which target?** Bare metal (USB stick or PXE), a Proxmox VE guest (node:
   `provision.pve_host`, env `PROVISION_PVE_HOST`) or a local VM. Production targets (aliases or
   names matching `linux.prod_re`) get the plan as a suggestion with its blast radius.

## The spine

```bash
# hook: pass
prov distros                                   # what this prov renders
prov --root "$ROOT" init ubuntu web1           # starter hosts/web1/host.toml (synthetic values)
#   edit hosts/web1/host.toml: hostname, users + ssh keys, network, storage.disks, [ubuntu]
prov --root "$ROOT" render web1                # hosts/web1/rendered/ holds exactly the artefacts
prov --root "$ROOT" validate web1              # schema, semantics, rendered files, staleness (exit 1 = findings)
prov --root "$ROOT" diff web1                  # rendered/ vs a fresh render (review before the MR)
```

1. **Draft** `host.toml` with the user's real values, never invented ones: ask for what is open
   (disk device, interface name or MAC, addresses, the ssh public key). Secrets are never inline:
   ssh keys only, a password at most as a crypt hash the user supplies.
2. **Render, validate, diff** until `prov validate` exits 0. Read each finding; fix `host.toml`,
   not the rendered files.
3. **Test in a local VM** (`references/local-vm.md`): seed ISO + QEMU with an image file, never a
   `/dev/…` disk. Report what booted and what failed.
4. **MR in the infrastructure repository** with `host.toml` and `rendered/`; the MR body carries
   the `prov plan` output and the VM-test result. Talos `secrets.yaml` is sops-encrypted first.
5. **Plan for the human:**

   ```bash
   # hook: pass
   prov --root "$ROOT" plan web1                # prints the steps; runs nothing
   ```

   Hand the steps over as they are, with the disks they wipe named. Never pipe the plan into a
   shell (the guard asks) and never run its steps yourself.
6. **The human applies** (writes the USB stick, creates the VM, boots the installer).
7. **Verify** the installed host with the linux bundle once its `~/.ssh/config` alias exists:

   ```bash
   # hook: allow
   lx check web1
   lx facts web1
   lx audit web1
   ```

   Compare distro, kernel, disks, addresses and sshd settings with `host.toml`; a difference is a
   fix to `host.toml` through the next MR, never a live edit.

## Guard decisions (the guard wins over permissions)

| Command | Decision | Instead |
|---|---|---|
| `prov …` | pass | — |
| `prov plan … \| sh`, `eval "$(prov plan …)"` | **ask** | hand the steps to the user |
| `qm`/`pct list\|config\|status`, `pvesh get`, `pvecm status`, `ha-manager status` | pass | — |
| `qm create\|set\|clone\|template\|start\|destroy\|importdisk …`, `pvesh create\|set\|delete` (also `ssh PVE qm …`) | **ask** | the human runs it on the node |
| `talosctl gen\|validate\|get\|logs --tail\|version`, `apply-config --dry-run` | pass | — |
| `talosctl apply-config` (incl. `--mode=try`), `reset`, `upgrade`, `bootstrap`, `reboot` | **ask** (`host=… [PROD]`) | `--dry-run`, then the human |
| `talosctl kubeconfig`, `talosctl config merge\|context\|…`, reading `~/.talos/*` | **deny** | the human manages both configs |
| `nixos-rebuild build\|build-vm`, `nixos-anywhere --vm-test`, `nix build\|eval\|flake check` | pass | — |
| `nixos-rebuild switch\|boot\|test`, any `--target-host`, `nixos-anywhere`, `disko` (also via `nix run`) | **ask** | build / VM-test, then the human |
| `virsh` reads, `virt-install --dry-run --print-xml` | pass | — |
| `virsh destroy\|define\|start\|…`, `virt-install`, QEMU or `qemu-img` on `/dev/…`, `dd of=/dev/…` | **ask** | image files; the human writes devices |

## Deliberately not implemented

- **Applying anything.** VM lifecycle, disk and USB writes, installs over ssh, config pushes to
  live nodes, cluster bootstrap. They are the human's, from the plan.
- **A renderer in the hub.** Distro support lands in provision-hub through its plugin contract.
- **Network calls on the user's behalf** that register or fetch artefacts (the Talos Image
  Factory schematic, ISO downloads): the plan names them for the human.
- **Editing `~/.talos/config` or a kubeconfig**, and reading either.

## References

`references/workflow.md` (the flow, checkpoints, MR contents) · `references/ubuntu.md` (autoinstall,
NoCloud seed, what prov renders) · `references/proxmox.md` (PVE host install with `answer.toml`,
VM templates with `qm` cloud-init) · `references/nixos.md` (flake + disko + nixos-anywhere) ·
`references/talos.md` (secrets, machine configs, apply and bootstrap) · `references/local-vm.md`
(KVM, WSL2, QEMU + seed ISO + OVMF). The design-only `provision-planner` agent turns "N hosts of
kind X on target Y" into `host.toml` drafts and the plan steps.
