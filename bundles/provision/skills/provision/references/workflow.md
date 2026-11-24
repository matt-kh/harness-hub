# Provisioning workflow

The flow every backend follows. Steps marked **human** are never run by an agent: the guard asks,
and the agent hands over the exact command instead. `prov` below is `uv run prov` where the
infrastructure repository pins provision-hub.

| # | Step | Who | Done when |
|---|---|---|---|
| 0 | Step 0 check (`harness repo owns provision/skills/provision`) in the cwd and in `provision.infra_root`; read that repository's `CLAUDE.md` / README | agent | not owned, or yield and stop |
| 1 | Choose the prov command (pinned `uv run prov`, else `prov`) and the root: one of the roots in `$PROVISION_INFRA_ROOT`, on a branch, else a scratch root (`mktemp -d`) | agent | command and root named to the user |
| 2 | `prov backends --kind <kind>`, then `prov init <kind>/<name> --backend <backend>` (or copy an existing item of the same role) | agent | `<kind>/<name>/spec.toml` exists |
| 3 | Fill in real values: disks (by-id), interfaces (name or MAC), addresses, users and ssh keys, the backend table; host-owned files next to `spec.toml` | agent + user | no synthetic placeholder left |
| 4 | `prov render <ref>`, `prov validate <ref>`, `prov diff <ref>` | agent | validate exits 0, diff reviewed |
| 5 | Local VM test (`local-vm.md`) | agent | the installer finished and the VM booted, or the failure (or why no test was possible) is reported |
| 6 | Commit `spec.toml`, host-owned files and `rendered/`; run the repository's own checks; open the MR in the infrastructure repository | agent | MR open, body has the plan and the VM result |
| 7 | Review and merge | **human** | merged |
| 8 | `prov plan <ref>` from the merged state | agent | steps handed to the user with the render digest and the wiped disks named |
| 9 | Write the USB stick / create the VM / boot the installer / `nixos-rebuild switch` | **human** | installer done; digest recorded with what was applied |
| 10 | Add the host's `~/.ssh/config` alias | **human** | `lx hosts` lists it |
| 11 | `lx check`, `lx facts`, `lx audit` against `spec.toml`; `prov status --state-dir "$PROVISION_STATE_DIR" <ref>` when state records exist | agent | matches (`in-sync`), or a follow-up MR |

## Without `prov`

Say that `prov` is missing and print the `provision.tool_source` hint (or, for a repository that
pins provision-hub in its `pyproject.toml`, `uv sync` there). Then walk the user through the same
table by hand: which values `spec.toml` needs (`prov schema` once it is installed), which
artefacts the backend produces (see its reference), how to test them and what the human will
run. Do not hand-write the rendered artefacts as a substitute: an unrendered, unvalidated
autoinstall file or flake is exactly what this flow exists to prevent.

## Without `provision.infra_root`

Work in a scratch root and end the answer with: "This lives in `<scratch>`; move
`<kind>/<name>/` into a root of your infrastructure repository and open an MR before installing
from it." Nobody installs from a scratch root.

## The MR

- Title and branch follow the infrastructure repository's conventions (no ticket key in the
  branch at user level). The prov pin (`pyproject.toml` / `uv.lock`) moves only in its own MR.
- Body: what the host is for, `prov validate` result, the VM test (backend, firmware, what
  booted), the full `prov plan` output in a code block (its header carries the render digest),
  and the disks it wipes.
- Never commit plaintext secrets: no passwords (crypt hashes only, supplied by the user), Talos
  `secrets.yaml` only sops-encrypted, no private keys, no LUKS passphrases.

## Handing over the plan

Copy `prov plan` output verbatim, including its `render digest: sha256:…` header line: the human
records it with what they applied, and a host agent later reports it back, which is how
`prov status` tells `pending` from `in-sync`. Add, above it: the target (`host=<alias> [PROD]`
when it matches `linux.prod_re`), the disks that will be wiped, and a rollback note (what to do
if the install fails half-way: boot the previous system, restore from the snapshot, re-run the
installer; for NixOS, the previous generation in the boot menu). On a `[PROD]` target the plan is
a suggestion; say so.

## Observed state

`prov status` reads the specs, `rendered/` and the state records in `provision.state_dir`
(`<kind>/<name>.json`, written by host agents, never by prov or the agent); `prov digest <ref>`
prints the digest of `rendered/`. Without a state directory every item is `planned`.

| Lifecycle / sync | Meaning | What the agent does |
|---|---|---|
| `planned` | no record yet | nothing: not installed, or no agent reports |
| `active` / `stale` | the host reported within `--stale-after` (72h) / stopped reporting | `stale`: check the host with `lx check` |
| `pending` | the host applied an older render | hand the newest `prov plan` to the human |
| `drifted` | the host changed outside the spec | adopt the change through a spec MR, or let the human discard it; never overwrite |
| `invalid` | a spec or record is invalid | fix the spec through an MR; report a broken record |

## Re-installing an existing host

1. `lx facts HOST` and `lx storage HOST` first: which disks hold data that must survive?
2. Make sure `spec.toml` `storage.disks` names only the disks meant to be wiped (all of them may
   be).
3. Same flow from step 4; the plan must say "re-install: data on <disks> is destroyed".
