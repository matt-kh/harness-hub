---
name: provision
description: >-
  Provision or reinstall hosts from one reviewed spec with the external `prov` renderer: draft
  `<kind>/<name>/spec.toml`, render and validate its backend's artefacts (Ubuntu autoinstall
  NoCloud seeds, NixOS flakes with disko and an offline USB installer; Proxmox VE and Talos
  follow the same flow), test them in a local VM, land them in the infrastructure repository
  through an MR, print the apply plan with its render digest, and verify with `lx` and
  `prov status`. Use when the user wants to provision, install, reinstall or bootstrap Ubuntu,
  NixOS, Proxmox VE or Talos, mentions `spec.toml`, `prov`, autoinstall, cloud-init, disko, an
  install ISO or USB installer, an answer file, PXE, bare metal, a VM template or
  nixos-anywhere, or runs /provision. NOT for diagnosing a running host (linux skill), NOT for
  cluster workloads (k8s skill), and NOT for applying anything: every VM create, disk or USB
  write, talosctl apply and nixos-anywhere run is handed to the human.
argument-hint: "<kind>/<name> [--backend ubuntu-autoinstall|nixos-disko|…] [--target metal|pve|vm]"
model: {{ core.model_policy.execute }}
---

# provision — reviewed specs to installed hosts

One versioned `spec.toml` per item is the source of truth: `<root>/<kind>/<name>/spec.toml`,
where the **kind** (e.g. `os-install`) fixes what the item is and the **backend** (e.g.
`ubuntu-autoinstall`, `nixos-disko`) renders it. `prov` (the public provision-hub tool, not
part of the hub) renders the spec into `<kind>/<name>/rendered/`, checks it, prints the steps
that apply it, and reports observed state. The agent drafts, renders, validates and tests; the
human applies.

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
check in `provision.infra_root` too when you work there, and follow that repository's own
`CLAUDE.md` / README (its roots, its validate script, how its prov pin moves).

## What `prov` renders today

`prov kinds` and `prov backends` are authoritative; this table may lag behind them.

| Kind | Backend | Status | Artefacts | Reference |
|---|---|---|---|---|
| `os-install` | `ubuntu-autoinstall` (22.04, 24.04) | **rendered by prov** | NoCloud seed: autoinstall `user-data`, `meta-data`, `kernel-cmdline`; layouts `lvm`, `zfs`, `mdraid` | `references/ubuntu.md` |
| `os-install` | `nixos-disko` | **rendered by prov** | pinned flake: `flake.nix`, `configuration.nix`, `disko.nix`, `installer.nix` (offline USB installer ISO); layouts `ext4`, `ext4-luks`; networkd or NetworkManager, optional GNOME | `references/nixos.md` |
| `os-install` | Proxmox VE | candidate backend | `answer.toml` + `proxmox-auto-install-assistant`; guests from `qm` cloud-init templates | `references/proxmox.md` |
| `os-install` | Talos | candidate backend | machine configs from `talosctl gen config` + patches | `references/talos.md` |

prov's checks are static: a rendered layout is consistent and passes the backend's `validate`,
which does not prove an install works. Never call an artefact working before a VM test or an
install says so. For a candidate backend, explain the steps from its reference and keep the
artefacts the target's own tools produce (`talosctl gen config`,
`proxmox-auto-install-assistant`); never write a renderer of your own. Local VM testing:
`references/local-vm.md`. The whole flow with checkpoints: `references/workflow.md`.

## Before you start

1. **Which `prov`?** In the infrastructure repository, a `pyproject.toml` that depends on
   `provision-hub` pins it: run `uv run prov …` there (the pin wins over any global `prov`; it
   moves only in its own PR). Otherwise `command -v prov`. If neither works, say so, give the
   install hint from `provision.tool_source` (env `PROVISION_TOOL_SOURCE`, default
   `uv tool install git+https://github.com/matt-kh/provision-hub@<commit-sha>`: the user picks
   and reviews the commit), and still help: explain the steps below and what each artefact will
   contain. Never improvise a renderer or hand-write autoinstall YAML or a flake in its place.
   Below, `prov` means whichever form applies.
2. **Which root?** `provision.infra_root` (env `PROVISION_INFRA_ROOT`) is the private
   infrastructure *repository*; it may hold several prov roots (for example one per site or
   category), each with `<kind>/<name>/` items. Take the roots from its `CLAUDE.md` / README;
   otherwise find the directories holding `*/*/spec.toml` and confirm with `prov --root <dir>
   list`. Always pass `--root` (or `PROV_ROOT`) and work on a branch. When `infra_root` is
   unset, work in a scratch root (`mktemp -d`) and say plainly that the result must move into
   the infrastructure repository through an MR before anyone installs from it.
3. **Which target?** Bare metal (USB stick or PXE), a Proxmox VE guest (node:
   `provision.pve_host`, env `PROVISION_PVE_HOST`) or a local VM. Production targets (aliases or
   names matching `linux.prod_re`) get the plan as a suggestion with its blast radius.

## The spine

```bash
# hook: pass
prov kinds                                                       # kinds and their api versions
prov backends --kind os-install                                  # backends that render them
prov --root "$ROOT" list                                         # items under the root (ref, backend)
prov --root "$ROOT" init os-install/web1 --backend ubuntu-autoinstall   # starter spec.toml (synthetic values)
prov --root "$ROOT" schema os-install --backend ubuntu-autoinstall      # the authoritative keys
#   edit os-install/web1/spec.toml: hostname, users + ssh keys, network, disks, the backend table
prov --root "$ROOT" render os-install/web1                       # rendered/ holds exactly the artefacts
prov --root "$ROOT" validate os-install/web1                     # envelope, schema, semantics, rendered files, staleness (exit 1 = findings; --json)
prov --root "$ROOT" diff os-install/web1                         # rendered/ vs a fresh render (review before the MR)
```

1. **Draft** `spec.toml` with the user's real values, never invented ones: ask for what is open
   (disk by-id path, interface name or MAC, addresses, the ssh public key). Copy an existing
   item of the same role when there is one. Secrets are never inline: ssh public keys only, a
   password at most as a crypt hash the user supplies.
2. **Render, validate, diff** until `prov validate` exits 0. Read each finding; fix `spec.toml`,
   never the files in `rendered/`. Host-owned files live **next to** `spec.toml`, not in
   `rendered/` (nixos-disko: `hardware-configuration.nix`, `local.nix`); files a backend
   preserves across renders (nixos-disko: `rendered/flake.lock`) are committed, not deleted.
3. **Test in a local VM** (`references/local-vm.md`): QEMU with an image file, never a
   `/dev/…` disk. Report what booted and what failed; say so when no VM test was possible.
4. **MR in the infrastructure repository** with `spec.toml`, the host-owned files and
   `rendered/`; run the repository's own checks first (for example a validate-all script). The
   MR body carries the `prov plan` output and the VM-test result. Talos `secrets.yaml` is
   sops-encrypted first.
5. **Plan for the human:**

   ```bash
   # hook: pass
   prov --root "$ROOT" plan os-install/web1                      # prints the steps; runs nothing
   ```

   Hand the steps over as they are, with the disks they wipe named and the `render digest:
   sha256:…` line from the plan header, which the human records with what they applied. Never
   pipe the plan into a shell (the guard asks, also through `uv run` and `uvx`) and never run
   its steps yourself.
6. **The human applies** (writes the USB stick, creates the VM, boots the installer; for an
   installed NixOS host, `nixos-rebuild switch --flake` after the spec MR merged).
7. **Verify** the installed host with the linux bundle once its `~/.ssh/config` alias exists:

   ```bash
   # hook: allow
   lx check web1
   lx facts web1
   lx audit web1
   ```

   Compare distro, kernel, disks, addresses and sshd settings with `spec.toml`; a difference is a
   fix to `spec.toml` through the next MR, never a live edit. When `provision.state_dir` (env
   `PROVISION_STATE_DIR`) is set, also read the observed state:

   ```bash
   # hook: pass
   prov --root "$ROOT" status --state-dir "$PROVISION_STATE_DIR" os-install/web1   # lifecycle + sync; reads files only
   prov --root "$ROOT" digest os-install/web1                                       # the digest of rendered/
   ```

   `planned` = no record yet; `active` / `stale` = the host reported recently / stopped
   reporting; sync `pending` = a newer render waits to be applied, `drifted` = the host changed
   outside the spec (adopt it through a spec MR or let the human discard it; never overwrite).
   State records are written by host agents, never by prov or by you.

## Guard decisions (the guard wins over permissions)

| Command | Decision | Instead |
|---|---|---|
| `prov …`, `uv run [opts] prov …`, `uv tool run prov …`, `uvx prov …` | pass | — |
| `prov plan … \| sh`, `eval "$(prov plan …)"` (also through `uv run` / `uvx`) | **ask** | hand the steps to the user |
| `qm`/`pct list\|config\|status`, `pvesh get`, `pvecm status`, `ha-manager status` | pass | — |
| `qm create\|set\|clone\|template\|start\|destroy\|importdisk …`, `pvesh create\|set\|delete` (also `ssh PVE qm …`) | **ask** | the human runs it on the node |
| `talosctl gen\|validate\|get\|logs --tail\|version`, `apply-config --dry-run` | pass | — |
| `talosctl apply-config` (incl. `--mode=try`), `reset`, `upgrade`, `bootstrap`, `reboot` | **ask** (`host=… [PROD]`) | `--dry-run`, then the human |
| `talosctl kubeconfig`, `talosctl config merge\|context\|…`, reading `~/.talos/*` | **deny** | the human manages both configs |
| `nixos-rebuild build\|build-vm`, `nixos-anywhere --vm-test`, `nix build\|eval\|flake check` | pass | — |
| `nixos-rebuild switch\|boot\|test`, any `--target-host`, `nixos-anywhere`, `disko`, `disko-install` (also via `nix run`) | **ask** | build / VM-test, then the human |
| `virsh` reads, `virt-install --dry-run --print-xml` | pass | — |
| `virsh destroy\|define\|start\|…`, `virt-install`, QEMU or `qemu-img` on `/dev/…`, `dd of=/dev/…` | **ask** | image files; the human writes devices |

## Deliberately not implemented

- **Applying anything.** VM lifecycle, disk and USB writes, installs over ssh, config pushes to
  live nodes, cluster bootstrap. They are the human's, from the plan.
- **A renderer in the hub.** Backends and kinds land in provision-hub through its plugin
  contract.
- **Writing state records.** They come from host agents; the skill only reads them with
  `prov status`.
- **Network calls on the user's behalf** that register or fetch artefacts (the Talos Image
  Factory schematic, ISO downloads): the plan names them for the human.
- **Editing `~/.talos/config` or a kubeconfig**, and reading either.

## References

`references/workflow.md` (the flow, checkpoints, MR contents) · `references/ubuntu.md`
(`ubuntu-autoinstall`: NoCloud seed, layouts, a spec example) · `references/nixos.md`
(`nixos-disko`: pinned flake, host-owned module, USB installer, changing an installed host) ·
`references/proxmox.md` (PVE host install with `answer.toml`, VM templates with `qm` cloud-init;
candidate backend) · `references/talos.md` (secrets, machine configs, apply and bootstrap; candidate
backend) · `references/local-vm.md` (KVM, WSL2, QEMU + seed ISO + OVMF). The design-only
`provision-planner` agent turns "N hosts of kind X on target Y" into `spec.toml` drafts and the
plan steps.
