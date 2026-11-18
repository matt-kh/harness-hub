# NixOS (planned in prov)

A NixOS host is a build product of a **flake**: `nixosConfigurations.<host>` plus a **disko**
layout for the disks, installed over ssh by **nixos-anywhere** onto any Linux the target boots
(the NixOS installer ISO, or an existing distro it kexecs out of). `prov` does not render NixOS
yet; the flake in the infrastructure repository is the source of truth.

## Layout in the infrastructure repository

```text
flake.nix                          # inputs: nixpkgs, disko; nixosConfigurations.web1
hosts/web1/configuration.nix       # networking, users and ssh keys, services
hosts/web1/disko.nix               # disks, partitions, filesystems
hosts/web1/hardware-configuration.nix   # from nixos-anywhere --generate-hardware-config
```

```nix
# hosts/web1/disko.nix (one disk, GPT, ESP + ext4 root)
{
  disko.devices.disk.main = {
    device = "/dev/disk/by-id/<disk-id>";
    type = "disk";
    content.type = "gpt";
    content.partitions = {
      ESP = { size = "512M"; type = "EF00";
              content = { type = "filesystem"; format = "vfat"; mountpoint = "/boot"; }; };
      root = { size = "100%";
               content = { type = "filesystem"; format = "ext4"; mountpoint = "/"; }; };
    };
  };
}
```

Networking with documentation values: `networking.interfaces.eth0.ipv4.addresses = [ { address =
"192.0.2.22"; prefixLength = 24; } ];`, `networking.defaultGateway = "192.0.2.1";`.

## What the agent runs (local, nothing activated)

```bash
# hook: pass
nix flake check
nix flake show
nix eval .#nixosConfigurations.web1.config.networking.hostName
nixos-rebuild build --flake .#web1                 # builds the system closure, activates nothing
nixos-rebuild build-vm --flake .#web1              # ./result/bin/run-web1-vm boots it in QEMU
nixos-anywhere --vm-test --flake .#web1            # the whole install incl. disko, in a VM
disko --dry-run --mode destroy,format,mount hosts/web1/disko.nix   # prints the script path only
```

`--vm-test` and `build-vm` need KVM for reasonable speed (`local-vm.md`).

## What the human runs

```bash
# hook: ask — NEVER run; hand to the user
nix run github:nix-community/nixos-anywhere -- --flake .#web1 \
  --generate-hardware-config nixos-generate-config hosts/web1/hardware-configuration.nix \
  root@192.0.2.22                                  # wipes the disks disko names
nixos-rebuild switch --flake .#web1 --target-host root@web1   # later changes
```

The guard asks on `nixos-anywhere` without `--vm-test` (also through `nix run`), on `disko` without
`--dry-run`, on `nixos-rebuild switch|boot|test|dry-activate` and on any `--target-host` /
`--build-host`; reasons carry `host=<target> [PROD]`.

## After install

`lx check web1`, `lx facts web1` (`nixos-version` with the configuration revision when the flake
sets `system.configurationRevision`), `lx health web1` (booted vs current kernel). Drift is fixed in
the flake and deployed by the human, never with `nix-env -i` on the host.

## Pitfalls

- `device = "/dev/sda"` in disko is fragile; use `/dev/disk/by-id/…` from `lx storage` or the
  installer's `lsblk`.
- nixos-anywhere needs root ssh (or sudo) on the target and enough RAM to kexec (≥ 1.5 GB).
- Secrets (sops-nix / agenix) are decrypted on the host: the host key must be known first; plan
  `--extra-files` for it with the human.
