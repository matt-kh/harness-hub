# Talos Linux (planned in prov)

Talos has no ssh and no shell: a node is configured entirely by its **machine config**, pushed
over the Talos API. `prov` does not render Talos yet; `talosctl gen config` plus patches in the
infrastructure repository are the source of truth.

## Secrets, once per cluster

```bash
# hook: pass (writes a local file)
talosctl gen secrets -o secrets.yaml
```

`secrets.yaml` holds the cluster CAs and tokens. **Encrypt it before it is committed**
(`sops --encrypt --in-place secrets.yaml` with the repository's `.sops.yaml` recipients) and never
print it. Regenerating it later means a new cluster identity.

## Machine configs

```bash
# hook: pass
talosctl gen config demo https://192.0.2.10:6443 \
  --with-secrets secrets.yaml \
  --config-patch @patches/all.yaml \
  --config-patch-control-plane @patches/controlplane.yaml \
  --config-patch-worker @patches/worker.yaml \
  --output-dir rendered/ --output-types controlplane,worker
talosctl machineconfig patch rendered/controlplane.yaml --patch @hosts/cp1.yaml -o rendered/cp1.yaml
talosctl validate --config rendered/cp1.yaml --mode metal
```

`gen config` also writes a `talosconfig` with a client key: keep it out of git (or encrypted) and
let the human merge it (`talosctl config merge`, denied for agents). Per-host patches carry the
install disk, hostname and addresses (`192.0.2.11/24` etc.).

## The install image (network call — the human's)

Extensions (iscsi-tools, qemu-guest-agent, …) come from an **Image Factory schematic**: posting the
schematic YAML to the factory returns a schematic id, which names the ISO and the installer image
(`factory.talos.dev/installer/<schematic-id>:v1.x.y`). The agent writes the schematic file into the
repository; the human registers it and downloads the ISO.

## Apply and bootstrap (the human's)

```bash
# hook: ask — NEVER run; hand to the user
talosctl apply-config --insecure -n 192.0.2.11 --file rendered/cp1.yaml   # node in maintenance mode
talosctl --talosconfig ./talosconfig -n 192.0.2.11 -e 192.0.2.11 bootstrap   # once, on ONE control-plane node
talosctl -n 192.0.2.11 upgrade --image factory.talos.dev/installer/<schematic-id>:v1.x.y
```

What the agent may run before handing over:

```bash
# hook: pass
talosctl -n 192.0.2.11 apply-config --dry-run --file rendered/cp1.yaml   # diff against the running config
talosctl -n 192.0.2.11 version
talosctl -n 192.0.2.11 get members
talosctl -n 192.0.2.11 health
talosctl -n 192.0.2.11 logs kubelet --tail 200
```

The guard asks on `apply-config` (also `--mode=try`: it still changes the live node until the
timeout), `reset`, `upgrade`, `upgrade-k8s`, `bootstrap`, `reboot`, `shutdown`, `edit`, `patch`,
`rotate-ca`, `wipe`; denies `talosctl kubeconfig` (the kubeconfig is human-managed, see the k8s
bundle) and every `talosctl config merge|add|context|endpoint|node`; denies reading
`~/.talos/config`. `talosctl get machineconfig -o yaml` asks: it prints key material.

## After bootstrap

Kubernetes access is the human's `talosctl kubeconfig`; from then on the `k8s` skill reads the
cluster. Node reads stay `talosctl` (`lx` does not apply to Talos).
