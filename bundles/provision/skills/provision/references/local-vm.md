# Local VM tests

Every rendered install is tested in a throw-away VM before the MR. The VM's disk is always an
**image file** (`disk.qcow2`); QEMU or `qemu-img` on a `/dev/…` block device asks.

## KVM first

```bash
# hook: pass
test -w /dev/kvm && echo kvm ok
```

Without a writable `/dev/kvm` QEMU falls back to TCG emulation: an Ubuntu install takes an hour
instead of minutes. Fixes (the human's): join the `kvm` group (`sudo usermod -aG kvm $USER`, log
in again); in BIOS enable VT-x/AMD-V.

**WSL2:** nested virtualisation must be on. In `%UserProfile%\.wslconfig`:

```ini
[wsl2]
nestedVirtualization=true
```

then `wsl --shutdown` from Windows. `/dev/kvm` should appear; the doctor check `kvm` tells. WSL2
networking is NAT: user-mode networking works, **PXE, bridged networking and DHCP from the VM to
your LAN do not** — test those on a Proxmox VE node or real hardware.

## Ubuntu autoinstall in QEMU (UEFI)

```bash
# hook: pass (image files only)
qemu-img create -f qcow2 disk.qcow2 20G
cloud-localds seed.iso hosts/web1/rendered/user-data hosts/web1/rendered/meta-data
cp /usr/share/OVMF/OVMF_VARS_4M.fd vars.fd
qemu-system-x86_64 -enable-kvm -m 4096 -smp 2 -cpu host \
  -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd \
  -drive if=pflash,format=raw,file=vars.fd \
  -drive file=disk.qcow2,if=virtio,format=qcow2 \
  -cdrom ubuntu-24.04-live-server-amd64.iso \
  -drive file=seed.iso,media=cdrom,format=raw \
  -nic user,model=virtio,hostfwd=tcp::2222-:22 \
  -nographic
```

OVMF paths vary by distribution (`/usr/share/OVMF/`, `/usr/share/edk2/ovmf/`, `/usr/share/qemu/`);
`firmware = "bios"` hosts drop the two pflash drives. Add `autoinstall` to the kernel command line
at the GRUB prompt if the installer asks for confirmation (see `kernel-cmdline`). After the
reboot, remove `-cdrom`/seed and check the guest with read-only commands such as
`ssh -p 2222 -o StrictHostKeyChecking=accept-new ops@127.0.0.1 cat /etc/os-release` (never
`StrictHostKeyChecking=no`; an interactive login is the human's).

The static addresses in `host.toml` will not match QEMU's user-mode network (its own private DHCP range): for the test,
either accept that the network check fails, or render a test variant with `dhcp4 = true`.

## libvirt

```bash
# hook: pass
virt-install --dry-run --print-xml --name web1-test --memory 4096 --vcpus 2 \
  --disk path=disk.qcow2,format=qcow2 --cdrom ubuntu-24.04-live-server-amd64.iso \
  --disk path=seed.iso,device=cdrom --os-variant ubuntu24.04 --boot uefi
virsh list --all
```

Creating, starting and destroying the domain (`virt-install` without `--dry-run --print-xml`,
`virsh define|start|destroy|undefine`) asks: hand them over, or use plain QEMU above.

## NixOS and Talos

- NixOS: `nixos-rebuild build-vm --flake .#web1` then `./result/bin/run-web1-vm`, or
  `nixos-anywhere --vm-test --flake .#web1` for the full disko install (`nixos.md`).
- Talos: boot the Talos ISO in QEMU with a qcow2 disk; the node waits in maintenance mode on the
  user network. Applying the config to it (`talosctl apply-config --insecure`) still asks — for a
  local test VM the human approves it; `talosctl cluster create` (Docker/QEMU clusters) asks too.

## Clean up

Delete `disk.qcow2`, `vars.fd` and `seed.iso` after the test; they are not artefacts for the MR.
