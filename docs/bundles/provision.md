# Bundle: provision

Installing hosts from reviewed definitions, with the agent drafting, rendering, validating and
testing, and the human applying. The bundle is deliberately thin: governance (guard section 85,
a rule, permissions) and workflow knowledge (the
[`provision` skill](../../bundles/provision/skills/provision/SKILL.md) and the
[`provision-planner`](../../bundles/provision/agents/provision-planner.md) agent). It depends on
the [linux](linux.md) bundle, whose guard definitions it reuses and whose `lx` CLI verifies an
installed host.

## The renderer lives outside the hub

`prov` is a separate public tool, [provision-hub](https://github.com/matt-kh/provision-hub)
(Python 3.10+, uv). It turns one versioned `spec.toml` per item, `<root>/<kind>/<name>/`, into
the artefacts its backend produces, checks them, prints the steps a human runs to apply them and
reports observed state; it never applies anything (no disk writes outside `rendered/`, no ssh,
no VM creation, no network calls). A **kind** fixes what an item is (`os-install`: one machine's
operating-system install); a **backend** renders it. Both are plugins.

| Command | Does |
|---|---|
| `prov kinds` / `prov backends [--kind K]` | the installed kinds and their api versions / the registered backends |
| `prov list` | every item under the root (ref, backend) |
| `prov schema <kind> [--backend B]` | the JSON Schema of a kind for its backends |
| `prov init <kind>/<name> --backend B` | starter `<kind>/<name>/spec.toml` with synthetic values |
| `prov render <ref>` | `<kind>/<name>/rendered/` holds exactly the rendered files |
| `prov validate <ref>` | envelope, schema, semantic and rendered-file checks, staleness (exit 1 = findings) |
| `prov diff <ref>` | `rendered/` vs a fresh render |
| `prov plan <ref>` | prints the apply steps for a human, headed by the render digest; runs nothing |
| `prov digest <ref>` | the sha256 digest of `rendered/` |
| `prov status [ref…] [--state-dir D]` | lifecycle and sync from the specs, `rendered/` and state records (files only) |
| `prov conformance <backend>` | renders the kind's fixtures through a backend; static checks only |

`kinds`, `backends`, `schema`, `validate`, `plan` and `status` take `--json`. Root: `--root DIR`,
else `$PROV_ROOT`, else the current directory. Install it either pinned in your infrastructure
repository (`provision-hub` as a git dependency at a reviewed commit in its `pyproject.toml`; the
skill then runs `uv run --frozen prov` there and the guard judges that form like a bare `prov`) or as an
isolated, pinned uv tool (`provision.tool_source`, default
`uv tool install git+https://github.com/matt-kh/provision-hub@<commit-sha>`: pick and review the
commit). Without `prov` the skill says so, prints that hint and explains the steps, but never
improvises a renderer.

| Kind / backend | In prov | Reference |
|---|---|---|
| `os-install` / `ubuntu-autoinstall` (22.04, 24.04) | **rendered today**: autoinstall NoCloud seed (`user-data`, `meta-data`, `kernel-cmdline`); layouts `lvm`, `zfs`, `mdraid` | [ubuntu.md](../../bundles/provision/skills/provision/references/ubuntu.md) |
| `os-install` / `nixos-disko` | **rendered today**: pinned flake (`flake.nix`, `configuration.nix`, `disko.nix`, `installer.nix`) with an offline USB installer ISO; layouts `ext4`, `ext4-luks`; host-owned `local.nix` | [nixos.md](../../bundles/provision/skills/provision/references/nixos.md) |
| Proxmox VE | candidate backend (`answer.toml` + `proxmox-auto-install-assistant`; guests via `qm` cloud-init templates) | [proxmox.md](../../bundles/provision/skills/provision/references/proxmox.md) |
| Talos | candidate backend (`talosctl gen config` + patches) | [talos.md](../../bundles/provision/skills/provision/references/talos.md) |

Specs live in your private infrastructure repository (`provision.infra_root`): the repository
itself or its subdirectories are prov roots, named in its `CLAUDE.md` or README. It may own
provisioning itself: declare `domains = ["infrastructure"]` in its `.harness.toml` and the skill,
agent, rule and guard section yield there (principle 8).

Observed state is optional: point `provision.state_dir` at a checkout of the state records that
host agents write (`<kind>/<name>.json`); the skill then reads `prov status --state-dir` after an
install (`planned`, `active`, `stale`, `decommissioned`; `in-sync`, `pending`, `drifted`,
`unknown`). Neither prov nor the
agent writes a record.

## Workflow

[workflow.md](../../bundles/provision/skills/provision/references/workflow.md):
`prov backends` → `prov init <kind>/<name> --backend B` → edit `spec.toml` → `prov render` →
`prov validate` → local VM test
([local-vm.md](../../bundles/provision/skills/provision/references/local-vm.md): KVM, WSL2 nested
virtualisation, QEMU + qcow2 + seed ISO + OVMF) → MR in the infrastructure repository →
`prov plan` (with its render digest) → **the human** runs the apply steps → verify with
`lx check|facts|audit` and `prov status`. Without `provision.infra_root` the agent works in a
scratch root and says the result must move into the infrastructure repository through an MR.

## Guard

Section 85 runs after the linux sections `82`/`83` and reads their definitions (clause lexer,
wrapper unwrapping, block-device targets, the Proxmox VE read forms, `[PROD]` from
`linux.prod_re`).

- **Pass:** `prov …`, also as `uv run [opts] prov …`, `uv tool run prov …` and `uvx prov …`; `proxmox-auto-install-assistant`; `qm`/`pct list|config|status|showcmd|
  pending|listsnapshot`, `pvesh get|ls|usage`, `pvecm status`, `pvesm status|list`, `pveum … list`,
  `ha-manager status`; `talosctl gen|validate|machineconfig|get|version|health|services|disks|
  mounts|logs --tail|dmesg|config info|contexts|images` and `apply-config --dry-run`;
  `nixos-rebuild build|dry-build|build-vm|dry-run` without a remote host; `nixos-anywhere
  --vm-test`; `disko --dry-run`; `nix build|eval|flake check|flake show|path-info`; `virsh` reads;
  `virt-install --dry-run --print-xml`; QEMU and `qemu-img` on image files.
- **Ask** (reasons carry `host=<target> [PROD]` from talosctl `-n`/`-e`/`--context`,
  `--target-host`, the nixos-anywhere target or a libvirt URI; the Proxmox VE node from
  `provision.pve_host`; the infrastructure repository from `provision.infra_root`): every other
  `qm`/`pct`/`pvesh`/`pvecm`/`pvesm`/`pveum`/`pvenode`/`ha-manager` form; `talosctl apply-config`
  (also `--mode=try`), `reset`, `upgrade`, `upgrade-k8s`, `bootstrap`, `reboot`, `shutdown`,
  `edit`, `patch`, `rotate-ca`, `wipe`, `logs -f`, `etcd snapshot`, anything off the read list,
  and `talosctl get machineconfig|…secrets -o yaml|json`; `nixos-rebuild switch|boot|test|
  dry-activate` and any `--target-host`/`--build-host`; `nixos-anywhere` and `disko` (also
  through `nix run`, `nix shell -c` and `nix-shell --run`); `virsh` changes, bare `virsh` and
  `virsh console`; `virt-install`; QEMU with a `/dev/…` disk and `qemu-img convert|dd|create`
  onto one; `prov plan … | sh` and `eval "$(prov plan …)"`, also when prov runs through
  `uv run`, `uv tool run` or `uvx`. `ssh <pve-node> qm …` asks in section
  83 unless it is a read form; `dd if=… of=/dev/…` (writing a USB stick) asks there too.
- **Deny:** `talosctl kubeconfig` and `talosctl config merge|add|remove|context|endpoint|node|new`
  (the kubeconfig and talosconfig are human-managed). Reading `~/.talos/*` or `$TALOSCONFIG` and
  `talosctl kubeconfig -` (prints credentials) are denied in a never-yields prelude: they stay
  denied when a repository owns `infrastructure`.
- Wrappers do not hide a command: `sudo`, `env`, `timeout`, `xargs`, `cd x && …`, `sh -c`, `eval`
  and `$(…)` are unwrapped first, and `uv run`, `uv tool run` and `uvx` before prov.

Config: `provision.infra_root` (env `PROVISION_INFRA_ROOT`), `provision.pve_host`
(`PROVISION_PVE_HOST`), `provision.state_dir` (`PROVISION_STATE_DIR`), `provision.tool_source`
(`PROVISION_TOOL_SOURCE`); prod targets come from
`linux.prod_re`.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| The skill says `prov` is missing | provision-hub is neither on PATH nor pinned in `provision.infra_root` | pin it in the infrastructure repository and `uv sync --frozen` there, or run the `provision.tool_source` command (manual step `install-prov`), then `prov kinds` |
| Doctor warns `prov-cli` although the infrastructure repository pins prov | its `.venv` has no `prov` yet (the check only reads `<infra_root>/.venv/bin/prov`) | `uv sync --frozen` in that repository |
| Doctor warns `infra-root` | `provision.infra_root` empty or not a git checkout | clone the infrastructure repository and set `[provision] infra_root` in `local/harness.toml`, then `harness apply` |
| Doctor warns `kvm` | no writable `/dev/kvm`: VM tests fall back to slow TCG | join the `kvm` group; on WSL2 set `nestedVirtualization=true` in `.wslconfig` and `wsl --shutdown` |
| A PXE or bridged VM test never gets an address | WSL2 networking is NAT | test PXE and bridging on a Proxmox VE node or real hardware |
| `qm list` over ssh fails with a permission error | `qm` needs root on the node | use the node's root login for reads, or hand the read to the human |
| `ssh pve qm create …` asks | every `qm` write is the human's | hand the command over; the guard reason names the node |
| `talosctl apply-config --mode=try` asks | try mode still applies the config to the live node | `talosctl apply-config --dry-run` shows the diff; the human applies |
| `talosctl kubeconfig` is denied | the kubeconfig is human-managed (see the k8s bundle) | the human runs it and merges the context |
| `nix run github:nix-community/nixos-anywhere -- …` asks | it installs and wipes disks | `--vm-test` passes; the real install is the human's |
| `qemu-system-x86_64 -drive file=$IMG` asks | a `$VAR` target cannot be checked | pass a literal image path |
| `prov plan … \| sh` or `uv run prov plan … \| sh` asks | it would run the apply steps | hand the plan to the human step by step |
| `prov status` shows every item `planned` | no state directory (`provision.state_dir` empty) or no host agent reports yet | set `[provision] state_dir` to the records checkout, then `harness apply` |
| Prod targets not flagged `[PROD]` | node or host names do not match `linux.prod_re` | adjust `[linux] prod_re`, then `harness apply` |

<!-- generated:begin source=bundles/provision/bundle.toml -->
## Summary

Provisioning Ubuntu, NixOS, Proxmox VE and Talos hosts with the external prov renderer (kind/backend specs): workflow skill, design-only planner agent, and guards that hand every apply step (VM create, disk or USB write, talosctl apply, nixos-anywhere) to the human

A thin governance and workflow bundle for installing hosts. The renderer is not part of the hub:
`prov` (the public provision-hub tool) turns one versioned `spec.toml` per item
(`<root>/<kind>/<name>/`, a kind such as `os-install` rendered by a backend) into artefacts:
today Ubuntu autoinstall NoCloud seeds (`ubuntu-autoinstall`) and NixOS flakes with disko and an
offline USB installer (`nixos-disko`); Proxmox VE and Talos are candidate backends. It validates
them, prints the apply steps for a human with the render digest, and reports observed state
(`prov status`); it never applies anything. Real specs live in a private infrastructure
repository (`provision.infra_root`, one or more prov roots, often with prov pinned in its
`pyproject.toml` and run as `uv run prov`), which may own provisioning (principle 8). Guard
section 85 (after the linux sections it builds on): `prov` passes, also through `uv run`,
`uv tool run` and `uvx`; the read forms of `qm`, `pct`, `pvesh`, `pvecm`, `pvesm`, `pveum`,
`ha-manager`, `talosctl` (gen, validate, get, logs without -f, apply-config --dry-run),
`nixos-rebuild build|build-vm`, `nixos-anywhere --vm-test`, `virsh` reads and `virt-install
--dry-run --print-xml` pass; every apply step asks (Proxmox VE guest and cluster changes,
`talosctl apply-config` incl. `--mode=try`, reset, upgrade, bootstrap, `nixos-rebuild switch` or
any `--target-host`, `nixos-anywhere`, `disko`, `virsh` and `virt-install` changes, QEMU on block
devices, `prov plan | sh` however prov is launched), with `host=<target> [PROD]` from
`linux.prod_re`; `talosctl kubeconfig` and talosconfig edits deny; reading the talosconfig and
printing a kubeconfig deny and never yield. Ships the `provision` workflow skill with backend
references and the design-only `provision-planner` agent.

- **Depends on:** `core`, `linux`
- **Recommends:** `k8s`
- **Stability:** experimental
- **Domain / posture:** infrastructure / local

## Components

Stable ids derived from the path, with their [taxonomy](../reference/taxonomy.md) facets (domain shown only where it differs from the bundle's). All bundles: [catalog](../catalog.md).

**Skills**

- `provision/skills/provision` — control: guide · function: workflow · posture: local · model: execute · yields: declaration

**Agents**

- `provision/agents/provision-planner` — control: guide · function: plan · posture: read-only · model: plan · yields: name

**Rules**

- `provision/rules/85-provision` — control: guide · function: govern · yields: text

**Guard sections**

- `provision/guard.d/85-provision` — control: sensor · function: govern · decisions: deny 3 · ask 10 · yields: declaration

**Permission lists**

- `provision/permissions` — control: guide · function: govern · decisions: deny 2 · ask 15 · allow 12 · yields: config

**Doctor checks** (function: setup · posture: read-only; table below): `provision/doctor/infra-root`, `provision/doctor/kvm`, `provision/doctor/nix`, `provision/doctor/prov-cli`, `provision/doctor/pve-assistant`, `provision/doctor/qemu`, `provision/doctor/seed-iso`, `provision/doctor/talosctl`, `provision/doctor/virsh`

**Manual steps** (function: setup; table below): `provision/steps/infra-root`, `provision/steps/install-prov`

## Requirements

### Binaries

| binary | min version | install | optional | why |
|---|---|---|---|---|
| `python3` | 3.10 |  | no | prov (the external renderer) needs Python 3.10+ (uv runs it, globally or pinned in the infrastructure repository); everything else in this bundle is optional. |

### Configuration

| key | type | required | default | description |
|---|---|---|---|---|
| `provision.infra_root` | string | no | `""` | Path of your private infrastructure repository: the repository itself or its subdirectories are prov roots holding <kind>/<name>/spec.toml (its CLAUDE.md or README names them), and a pyproject.toml that pins provision-hub makes the skill run `uv run --frozen prov` there. Empty = the skill works in a scratch root and says the result must move into that repository through an MR. PROVISION_INFRA_ROOT. |
| `provision.pve_host` | string | no | `""` | ~/.ssh/config alias of a Proxmox VE node, used in printed plans and guard reasons (`ssh <alias> qm …`, every qm write the human's). Empty = plans use <pve-node>. PROVISION_PVE_HOST. |
| `provision.state_dir` | string | no | `""` | Optional checkout of the directory of prov state records (<kind>/<name>.json, written by host agents, never by prov or the agent); an absolute path, or ~/… (the skill expands it). Set = the skill runs `prov status --state-dir` to report lifecycle and sync (planned, active, stale, decommissioned; in-sync, pending, drifted, unknown) after an install; empty = every item is reported planned. PROVISION_STATE_DIR. |
| `provision.tool_source` | string | no | `"uv tool install git+https://github.com/matt-kh/provision-hub@<commit-sha>"` | How to install the prov renderer globally, shown by the skill and the prov-cli doctor check when prov is missing and the infrastructure repository does not pin it. Pin a commit or tag you reviewed. PROVISION_TOOL_SOURCE. |

### Secrets (never in harness.toml)

| id | where | written by | mode | rotate |
|---|---|---|---|---|
| `talos_secrets_bundle` | `<provision.infra_root>/…/secrets.yaml (from talosctl gen secrets), sops-encrypted before commit` | human (talosctl gen secrets once per cluster, then sops --encrypt) | 0600 | talosctl rotate-ca (the human's, per the Talos docs), then regenerate and re-encrypt the bundle |
| `talosconfig` | `~/.talos/config (or $TALOSCONFIG)` | human (talosctl gen config, then talosctl config merge) | 0600 | talosctl config new on a control-plane node with a fresh role, merge it yourself, then remove the old context |

## Manual steps

<a id="install-prov"></a>

### install-prov — Install the prov renderer (optional)

*once per machine · needs nothing but a terminal · ~3 min*

**Why:** The skill renders and validates install artefacts with prov; without it the agent explains the steps but never improvises a renderer.

**How:**

Either pin provision-hub in your infrastructure repository (preferred: the pin moves through a
reviewed PR, and the skill runs `uv run prov` there):
```
# <provision.infra_root>/pyproject.toml
[project]
name = "infra"
version = "0"
requires-python = ">=3.10"
dependencies = ["provision-hub"]

[tool.uv]
package = false

[tool.uv.sources]
provision-hub = { git = "https://github.com/matt-kh/provision-hub", rev = "<commit-sha>" }
```
then `uv sync --frozen` and `uv run --frozen prov kinds` in that repository. Or install it as an isolated uv tool,
pinned to a commit you reviewed:
```
{{ provision.tool_source }}
prov kinds
```
`prov` never applies anything; it writes only below `<root>/<kind>/<name>/rendered/`.

**Verify:** `{ command -v prov >/dev/null && prov kinds >/dev/null; } || { r=$(jq -r '.provision.infra_root // ""' "$HARNESS_CONFIG_JSON"); r=${r/#\~/$HOME}; [ -n "$r" ] && grep -q '"provision-hub' "$r/pyproject.toml" 2>/dev/null && [ -x "$r/.venv/bin/prov" ] && "$r/.venv/bin/prov" kinds >/dev/null; }` (exit 0)

<a id="infra-root"></a>

### infra-root — Point provision.infra_root at your infrastructure repository

*once per machine · needs nothing but a terminal · ~2 min*

**Why:** Specs belong in a reviewed repository; with infra_root set, prov runs with --root on its roots there and changes go through an MR.

**How:**

Clone your infrastructure repository (the one holding `<kind>/<name>/spec.toml` items in one or
more prov roots), then set
`[provision] infra_root = "~/dev/infra"` in `local/harness.toml` and run `harness apply`. If that
repository has its own provisioning skills, declare `domains = ["infrastructure"]` in its
`.harness.toml` and this bundle yields there.

**Verify:** `r=$(jq -r '.provision.infra_root // ""' "$HARNESS_CONFIG_JSON"); [ -n "$r" ] && git -C "${r/#\~/$HOME}" rev-parse --git-dir >/dev/null 2>&1` (exit 0)

## Doctor checks

| id | severity | offline | fix |
|---|---|---|---|
| `prov-cli` | warn | runs | [install-prov](#install-prov) |
| `infra-root` | warn | runs | [infra-root](#infra-root) |
| `kvm` | warn | runs | `add yourself to the kvm group (sudo usermod -aG kvm $USER, then log in again); on WSL2 set nestedVirtualization=true under [wsl2] in %UserProfile%\.wslconfig and run wsl --shutdown` |
| `talosctl` | warn | runs | `install talosctl from the Talos release page (verify its checksum) or your package manager; needed only for Talos hosts` |
| `nix` | warn | runs | `install Nix with your distribution's package or the official installer (download it, check it, then run it); prov renders NixOS items without it, Nix is needed to lock their flake and build the installer ISO` |
| `qemu` | warn | runs | `install qemu-system-x86 (Debian/Ubuntu), qemu-kvm (RHEL family) or qemu (Homebrew)` |
| `virsh` | warn | runs | `install libvirt-clients (Debian/Ubuntu) or libvirt-client (RHEL family); plain QEMU works without it` |
| `seed-iso` | warn | runs | `install xorriso, or cloud-image-utils (cloud-localds)` |
| `pve-assistant` | warn | runs | `install proxmox-auto-install-assistant from the Proxmox repository (on a Debian-based machine or a PVE node); needed only for Proxmox VE hosts` |

## Guides and sensors

Guides steer the agent before it acts; sensors detect at or after the action. Pairing: **paired**; guides with a declared check: 4 of 4.

| side | kind | ref | note | pairs with |
|---|---|---|---|---|
| guide | rule | `rules/85-provision.md` | render, validate and plan freely; every apply step is the human's; host definitions change in the infra repo through an MR | `guard.d/85-provision.sh` |
| guide | skill | `skills/provision` | the prov spine: kinds/backends, init <kind>/<name> --backend, render, validate, local VM test, MR, plan with its render digest, the human applies, lx and prov status verify; backend references | `guard.d/tests.sh`, `doctor_checks` |
| guide | permission | `permissions.toml` | prov, uv run --frozen prov and the read forms allowed, apply steps ask, kubeconfig and talosconfig edits denied | `permissions-vs-guard`, `guard.d/85-provision.sh` |
| guide | agent | `agents/provision-planner.md` | design only: spec.toml drafts and the plan steps, never applies | `guard.d/85-provision.sh`, `agent-tools` |
| sensor | guard | `guard.d/85-provision.sh` | Proxmox VE, Talos, NixOS, libvirt and QEMU apply steps ask; kubeconfig and talosconfig writes deny; credential prints never yield | `rules/85-provision.md`, `permissions.toml`, `agents/provision-planner.md` |
| sensor | test | `guard.d/tests.sh` | guard rows incl. wrappers, nix run, uv run / uvx, ssh to a PVE node, the guard.env PROVISION_* keys and prod regex, and the infrastructure yield | `skills/provision` |
| sensor | doctor | `doctor_checks` | prov (on PATH or pinned in infra_root), infra_root, /dev/kvm and the optional distro tools (warn only) | `skills/provision` |
| sensor | test | `tests/run.sh` | this bundle's rows against core + linux + provision only | — |
| sensor | lint | `permissions-vs-guard` | each Bash allow/deny rule of permissions.toml run through the guard: no allowed command the guard denies or asks, no denied one it allows | `permissions.toml` |
| sensor | lint | `agent-tools` | the planner sets no permissionMode, lists no write tools and names the plan model | `agents/provision-planner.md` |

**Not covered:** The renderer (prov) is an external tool with its own test suite; this bundle senses only the shell commands around it (prov run directly or through uv run, uv tool run and uvx, wrappers after uv included). The guard judges command text: an apply step run through another tool (ansible, a Proxmox API client, terraform providers, a script file written first and run later), a plan saved to a file and executed later, the nixos-disko `install-<hostname>` command on the installer stick (a host-specific name, run on the target's console), and what ~/.ssh/config adds to an alias are not sensed. The provision-rules guard section enforces rule text that lives in rules/85-provision.md; ssh HOST qm … is judged by the linux sections.

## Uninstall

Kept on uninstall: `~/.talos/**`

Your talosconfig, the infrastructure repository, the state records and the prov tool are yours; uninstall removes only the rendered skill, agent, rule, permissions and guard section.
<!-- generated:end -->
