# Provisioning workflow

The flow every distro follows. Steps marked **human** are never run by an agent: the guard asks,
and the agent hands over the exact command instead.

| # | Step | Who | Done when |
|---|---|---|---|
| 0 | Step 0 check (`harness repo owns provision/skills/provision`) in the cwd and in `provision.infra_root` | agent | not owned, or yield and stop |
| 1 | Choose the root: `$PROVISION_INFRA_ROOT` on a branch, else a scratch root (`mktemp -d`) | agent | root named to the user |
| 2 | `prov init <distro> <host>` (or copy an existing host of the same role) | agent | `hosts/<host>/host.toml` exists |
| 3 | Fill in real values: disks, interfaces (name or MAC), addresses, users and ssh keys | agent + user | no synthetic placeholder left |
| 4 | `prov render <host>`, `prov validate <host>`, `prov diff <host>` | agent | validate exits 0, diff reviewed |
| 5 | Local VM test (`local-vm.md`) | agent | the installer finished and the VM booted, or the failure is reported |
| 6 | Commit `host.toml` + `rendered/`, open the MR in the infrastructure repository | agent | MR open, body has the plan and the VM result |
| 7 | Review and merge | **human** | merged |
| 8 | `prov plan <host>` from the merged state | agent | steps handed to the user, wiped disks named |
| 9 | Write the USB stick / create the VM / boot the installer | **human** | installer done |
| 10 | Add the host's `~/.ssh/config` alias | **human** | `lx hosts` lists it |
| 11 | `lx check`, `lx facts`, `lx audit` against `host.toml` | agent | matches, or a follow-up MR |

## Without `prov`

Say that `prov` is missing and print the `provision.tool_source` hint. Then walk the user through
the same table by hand: which values `host.toml` needs, which artefacts the distro's installer
expects (see the distro reference), how to test them and what the human will run. Do not
hand-write the rendered artefacts as a substitute: an unrendered, unvalidated autoinstall file is
exactly what this flow exists to prevent.

## Without `provision.infra_root`

Work in a scratch root and end the answer with: "This lives in `<scratch>`; move
`hosts/<host>/` into your infrastructure repository and open an MR before installing from it."
Nobody installs from a scratch root.

## The MR

- Title and branch follow the infrastructure repository's conventions (no ticket key in the
  branch at user level).
- Body: what the host is for, `prov validate` result, the VM test (distro, firmware, what booted),
  the full `prov plan` output in a code block, and the disks it wipes.
- Never commit plaintext secrets: no passwords (crypt hashes only, supplied by the user), Talos
  `secrets.yaml` only sops-encrypted, no private keys.

## Handing over the plan

Copy `prov plan` output verbatim. Add, above it: the target (`host=<alias> [PROD]` when it matches
`linux.prod_re`), the disks that will be wiped, and a rollback note (what to do if the install
fails half-way: boot the previous system, restore from the snapshot, re-run the installer). On a
`[PROD]` target the plan is a suggestion; say so.

## Re-installing an existing host

1. `lx facts HOST` and `lx storage HOST` first: which disks hold data that must survive?
2. Make sure `host.toml` `storage.disks` names only the disks meant to be wiped (all of them may be).
3. Same flow from step 4; the plan must say "re-install: data on <disks> is destroyed".
