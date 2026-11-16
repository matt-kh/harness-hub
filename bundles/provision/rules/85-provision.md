## Provisioning
- **Render, validate and plan freely; never apply.** Use the `prov` renderer (skill `provision`):
  `prov init|render|validate|diff|plan` write only below `<root>/hosts/<host>/rendered/` and
  print the apply steps. Never pipe `prov plan` into a shell and never improvise a renderer when
  `prov` is missing.
- **Every apply step is the human's** — creating, changing or destroying a VM (`qm`, `pct`,
  `pvesh create|set|delete`, `virsh`, `virt-install`), writing a disk or USB stick (`dd`, `disko`,
  QEMU on `/dev/…`), `talosctl apply-config` (also `--mode=try`), `reset`, `upgrade`,
  `bootstrap`, `nixos-anywhere` and `nixos-rebuild switch|boot|test` or any `--target-host`. The
  guard asks; agents hand the exact command (Proxmox VE: over `ssh $PROVISION_PVE_HOST`) to the
  user. Local checks pass: `talosctl gen|validate`, `apply-config --dry-run`, `nixos-rebuild
  build|build-vm`, `nixos-anywhere --vm-test`, `virt-install --dry-run --print-xml`.
- Prod targets (node, endpoint, context or host matching `LINUX_PROD_RE`) carry `[PROD]`: there the
  plan is a **suggestion for the human**, stated with its blast radius (which disks are wiped).
- **Denied:** `talosctl kubeconfig` and `talosctl config merge|context|…` (kubeconfig and
  talosconfig are human-managed) and reading `~/.talos/*`; reading the talosconfig and
  `talosctl kubeconfig -` (prints credentials) stay denied even when a repository owns this domain.
- Host definitions (`host.toml`, machine configs, flakes, answer files) change only in the
  infrastructure repository (`provision.infra_root`) through an MR; Talos `secrets.yaml` is
  sops-encrypted before it is committed. Verify installed hosts with `lx check|facts|audit`.

A repository's own instructions for the same action replace this block.
