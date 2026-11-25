## Provisioning
- **Render, validate and plan freely; never apply.** Use the `prov` renderer (skill `provision`),
  also when it runs as `uv run --frozen prov` from an infrastructure repository that pins it:
  `prov init|render|validate|diff|plan|list|status|digest|conformance` write at most below
  `<root>/<kind>/<name>/rendered/` and print the apply steps. Never pipe `prov plan` into a
  shell, however prov is launched, and never improvise a renderer when `prov` is missing.
- **Every apply step is the human's** — creating, changing or destroying a VM (`qm`, `pct`,
  `pvesh create|set|delete`, `virsh`, `virt-install`), writing a disk or USB stick (`dd`, `disko`,
  QEMU on `/dev/…`), `talosctl apply-config` (also `--mode=try`), `reset`, `upgrade`,
  `bootstrap`, `nixos-anywhere` and `nixos-rebuild switch|boot|test` or any `--target-host`. The
  guard asks; agents hand the exact command (Proxmox VE: over `ssh $PROVISION_PVE_HOST`) to the
  user, with the render digest from the plan header so the human records what they applied.
  Local checks pass: `talosctl gen|validate`, `apply-config --dry-run`, `nixos-rebuild
  build|build-vm`, `nixos-anywhere --vm-test`, `virt-install --dry-run --print-xml`.
- Prod targets (node, endpoint, context or host matching `LINUX_PROD_RE`) carry `[PROD]`: there the
  plan is a **suggestion for the human**, stated with its blast radius (which disks are wiped).
- **Denied:** `talosctl kubeconfig` and `talosctl config merge|context|…` (kubeconfig and
  talosconfig are human-managed) and reading `~/.talos/*`; reading the talosconfig and
  `talosctl kubeconfig -` (prints credentials) stay denied even when a repository owns this domain.
- Specs (`<kind>/<name>/spec.toml`, the host-owned files beside them, machine configs, answer
  files) change only in the infrastructure repository (`provision.infra_root`) through an MR;
  `rendered/` is regenerated with `prov render`, never hand-edited; Talos `secrets.yaml` is
  sops-encrypted before it is committed. Verify installed hosts with `lx check|facts|audit` and,
  where state records exist (`provision.state_dir`), `prov status`.

A repository's own instructions for the same action replace this block.
