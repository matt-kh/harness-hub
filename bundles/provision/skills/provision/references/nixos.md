# NixOS (`os-install` / `nixos-disko`, rendered by prov)

A NixOS host is a build product of a **flake**. `prov` renders that flake from an `os-install`
item whose backend is `nixos-disko`: the target system, a **disko** layout for its one disk, and
an **offline USB installer** ISO that carries the target's closure. A human builds the ISO,
writes the stick, boots the machine from it and runs one confirmed install command. prov never
builds, writes or installs anything. The backend's own documentation (provision-hub
`docs/backends/nixos-disko.md`) is authoritative; this page is the agent's summary.

prov's checks are static: provision-hub's example flakes have been locked and `nix eval`-ed,
never built or installed on hardware. Never call a layout working before a VM test or an install
says so.

## The item

```text
<root>/os-install/web1/spec.toml
<root>/os-install/web1/hardware-configuration.nix   # optional, human-provided; never touched by prov
<root>/os-install/web1/local.nix                    # hand-written when local_module = true; never touched by prov
<root>/os-install/web1/rendered/flake.nix
<root>/os-install/web1/rendered/configuration.nix
<root>/os-install/web1/rendered/disko.nix
<root>/os-install/web1/rendered/installer.nix
<root>/os-install/web1/rendered/flake.lock          # created by `nix flake lock`, kept by render (PRESERVE)
```

Nix sees only **git-tracked** files of a flake: the rendered files, `flake.lock`, the hardware
file and `local.nix` must all be `git add`ed before anything is built.

## Example spec.toml (documentation values)

```toml
api_version = "prov/v1alpha1"
kind = "os-install"
backend = "nixos-disko"
hostname = "web1"
domain = "example.com"
arch = "amd64"
firmware = "uefi"
timezone = "Etc/UTC"
locale = "en_US.UTF-8"
keyboard = "us"

[[users]]
name = "ops"
sudo = true
ssh_authorized_keys = [
  "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEXAMPLEEXAMPLEEXAMPLEEXAMPLEEXAMPLEEXAMPLE ops@example.com",
]

[network.dns]
nameservers = ["192.0.2.53"]
search = ["example.com"]

[[network.interfaces]]
name = "lan0"
macaddress = "02:00:00:00:00:01"
addresses = ["192.0.2.22/24"]
gateway4 = "192.0.2.1"

[storage]
disks = ["/dev/disk/by-id/nvme-EXAMPLE_SSD_SERIAL_0000000000"]   # exactly one; it is wiped

[nixos-disko]
release = "nixos-26.05"      # nixpkgs branch the flake follows
state_version = "26.05"      # the release first installed; never change it afterwards
layout = "ext4"              # ext4 | ext4-luks (LVM on LUKS: root_size, extra volumes)
swap_size = "8G"
packages = ["git", "vim"]
networking = "networkd"      # networkd (needs [network]) | networkmanager (no [network])
desktop = "none"             # none | gnome (needs networkmanager)
```

The authoritative keys are `prov schema os-install --backend nixos-disko`; prefer `prov init
os-install/<name> --backend nixos-disko` or a copy of an existing item. What the spec cannot
express (proprietary packages, services, `programs.*`, fonts) goes into `local.nix` with
`local_module = true`; extra flakes for it go into `[nixos-disko.inputs]`, pinned to a tag or a
commit. `local.nix` and the hardware file are copied onto the stick on their own, so they must
be self-contained (no relative imports).

## What the agent runs (local, nothing activated)

```bash
# hook: pass
prov --root "$ROOT" render os-install/web1
prov --root "$ROOT" validate os-install/web1       # nix-instantiate --parse when nix is installed, else skipped
prov --root "$ROOT" plan os-install/web1           # the USB walkthrough below, with the render digest
cd "$ROOT/os-install/web1/rendered"
nix flake check                                    # after the human-owned lock step, in a git checkout
nix eval .#nixosConfigurations.web1.config.networking.hostName
nixos-rebuild build --flake .#web1                 # builds the system closure, activates nothing
nixos-rebuild build-vm --flake .#web1              # ./result/bin/run-web1-vm boots it in QEMU
```

`build-vm` needs KVM for reasonable speed (`local-vm.md`). Building the installer ISO is a local
build too (it writes only to the Nix store and the out-link), but it is large: agree with the
user before you start it.

## What the human runs (from `prov plan`)

1. Optional: capture the hardware file on the target, booted from the stock NixOS minimal ISO
   (`nixos-generate-config --no-filesystems --show-hardware-config`), and put it **next to
   `spec.toml`**, not into `rendered/`.
2. `git add` the rendered files, `nix flake lock`, commit `flake.lock` (in the infrastructure
   repository, through the MR).
3. `nix build …#nixosConfigurations.<hostname>-installer.config.system.build.isoImage` with an
   out-link (from WSL2: build in the Linux file system, copy the ISO to Windows).
4. Write the ISO to a USB stick (`dd` to `/dev/disk/by-id/usb-…`, or a GUI writer) — the guard
   asks on `dd of=/dev/…`; this wipes the stick.
5. Boot the target from the stick (UEFI, Secure Boot off) and run `sudo install-<hostname>` on
   its console: it checks the disk, asks for the last characters of its serial, then runs
   `disko-install` offline and **wipes the spec disk**. This script exists only on the stick;
   the guard cannot recognise it, so never run it and never suggest running it anywhere else.
6. Reboot into the installed system; post-install checks over ssh.

Hand these steps over exactly as `prov plan` prints them, with the disk it wipes named.

## Changing an installed host

No new ISO: edit `spec.toml` or `local.nix`, `prov render`, open the MR. After the merge the human
runs, on the host in a git checkout of the repository, from `rendered/`: `git pull &&
nixos-rebuild switch --flake .#<hostname> --sudo`. The guard asks on `nixos-rebuild
switch|boot|test|dry-activate` and on any `--target-host` / `--build-host`. Never `nix profile
install` or `nix-env -i` on the host: every change goes through the spec.

## nixos-anywhere (not rendered by prov)

Installing over ssh with **nixos-anywhere** is not a prov backend today; when a repository uses
it with its own flake, keep that flake as the source of truth and follow the same split: the
agent runs `nixos-anywhere --vm-test --flake .#<host>` (pass) and `disko --dry-run …` (pass);
`nixos-anywhere` without `--vm-test` (also through `nix run`) and `disko` without `--dry-run`
ask and are the human's. They wipe the disks disko names.

## After install

`lx check web1`, `lx facts web1` (`nixos-version`), `lx health web1` (booted vs current
kernel), and `prov status --state-dir "${PROVISION_STATE_DIR/#\~/$HOME}"` when state records
exist. Drift
is fixed in the spec and deployed by the human.

## Pitfalls

- `/dev/sda` in `storage.disks` is fragile; use `/dev/disk/by-id/…` from `lx storage` or the
  installer's `lsblk`. `nixos-disko` installs to exactly one disk.
- An untracked `flake.lock`, hardware file or `local.nix` is invisible to Nix: the ISO build
  fails or silently uses the broad initrd module set.
- `state_version` records the first installed release; never bump it when changing `release`.
- Secrets (sops-nix / agenix) are decrypted on the host: plan the host key with the human
  first.
