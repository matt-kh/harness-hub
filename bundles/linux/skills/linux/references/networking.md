# Networking runbook

`lx net HOST` first: links with kind (bond, VLAN, bridge, member), addresses, routes, the renderer
in use, firewall services and resolvers. Everything below is read-only unless marked **for the
human**. Raw `ssh HOST …` reads must keep every clause on the guard's allow-list (`ip` show forms,
`ss`, `networkctl status|list`, `resolvectl status|query`, `nmcli` show forms, `netplan get|status`,
`nft list`, `iptables -L|-S`, `ufw status`).

## 1. Which renderer owns the configuration

The fix belongs in the source that renders the interface, never in a live `ip` command (lost on
reboot) or a hand edit on the host (drifts from the infra repo).

| `lx net` renderer | Source of truth on the host | Read it | Change it (infra repo) |
|---|---|---|---|
| `netplan -> systemd-networkd` (Ubuntu server, cloud-init) | `/etc/netplan/*.yaml` → `/run/systemd/network/` | `ssh HOST netplan get`, `ssh HOST networkctl status` | the netplan template / cloud-init `network-config` |
| `netplan -> NetworkManager` (Ubuntu desktop) | `/etc/netplan/*.yaml` → NM keyfiles in `/run` | `ssh HOST nmcli connection show` | same netplan template |
| `NetworkManager` (RHEL 8+, Fedora) | `/etc/NetworkManager/system-connections/*.nmconnection` | `ssh HOST nmcli -f NAME,TYPE,DEVICE connection show` | the role that renders keyfiles (e.g. a `network_connections` role) |
| `network-scripts (ifcfg-*)` (RHEL 7, legacy) | `/etc/sysconfig/network-scripts/ifcfg-*` | `ssh HOST cat /etc/sysconfig/network-scripts/ifcfg-eth0` | migrate to keyfiles; until then the ifcfg template |
| `systemd-networkd` (Debian, Arch, appliances) | `/etc/systemd/network/*.network|.netdev` | `ssh HOST networkctl status`, `ssh HOST cat /etc/systemd/network/10-uplink.network` | the role / module that writes them |
| `ifupdown` (Debian, Proxmox VE) | `/etc/network/interfaces(.d)` | `ssh HOST cat /etc/network/interfaces` | the template; on Proxmox the node's network config (web UI writes the same file) |
| `nixos` | `networking.*` / `systemd.network.*` in the host's configuration | read the flake / configuration in the repo | the NixOS module, then a rebuild by the human |

netplan files can hold Wi-Fi passphrases: pipe their content through `| lx redact` if you must read
them, or prefer `netplan get` piped the same way.

## 2. Links

- `NO-CARRIER` on an admin-up physical port: cable, switch port, transceiver or the peer is down.
  `ssh HOST ip -s link show eth1` (errors, drops) — the physical fix is the human's.
- A bond member down (`lx net` shows `bond_slave` with state DOWN): redundancy lost even though the
  bond is up. `ssh HOST cat /proc/net/bonding/bond0` shows `MII Status`, `Link Failure Count` and,
  for 802.3ad, the partner's aggregator id — mismatched aggregator ids mean the switch side is not in
  one LACP group.
- VLAN sub-interfaces (`bond0.100@bond0`, kind `vlan id 100`) inherit the parent's state; a tagged
  VLAN missing on the switch trunk gives carrier but no traffic.
- MTU mismatches (jumbo frames on one side) show as stalls on large transfers only:
  `ssh HOST ip -d link show bond0` and compare with the peer.

## 3. Routes

- No default route: `lx net` warns. On DHCP check the lease (`ssh HOST networkctl status eth0` or
  `ssh HOST nmcli device show eth0`); on static configs the gateway line in the renderer's source.
- Asymmetric routing on multi-homed hosts (replies leave through the wrong interface) is solved
  with policy routing in the renderer's source (`routing-policy` in netplan, `[RoutingPolicyRule]`
  in networkd, `ipv4.routing-rules` in NM), not with live `ip rule add`.
- `ssh HOST ip route get 192.0.2.50` shows which route and source address a destination uses.

## 4. Firewall

| Service active | Read (non-root usually fails — then it is the human's) | Source of truth |
|---|---|---|
| `nftables` | `sudo nft list ruleset` (**for the human**) | `/etc/nftables.conf` or `/etc/sysconfig/nftables.conf` |
| `firewalld` (RHEL family) | `lx net` reads `firewall-cmd --state` (works unprivileged on many hosts; raw `ssh HOST firewall-cmd` asks); zones and rules: `sudo firewall-cmd --list-all-zones` (**for the human**) | `/etc/firewalld/` (zones, services) |
| `ufw` (Ubuntu) | `sudo ufw status verbose` (**for the human**) | `/etc/ufw/` rules files |
| none | Docker / Kubernetes may still own iptables chains | the container runtime's settings |

Diagnose "service unreachable from outside" in order: is it listening on the right address
(`lx audit` listening table, `ssh HOST ss -tlnp`), does the host firewall allow it (above), does
something upstream (security group, switch ACL) allow it. Fixes are rule files in the infra repo.

## 5. DNS

- `/etc/resolv.conf` pointing at `127.0.0.53` means systemd-resolved: the real upstreams are in
  `resolvectl dns` (`lx net` shows them as `resolved:` lines) and
  `ssh HOST resolvectl status`.
- `ssh HOST resolvectl query host.example.com` tests resolution through resolved; `getent hosts` is
  not on the allow-list (asks).
- NetworkManager hosts without resolved write upstreams straight into `/etc/resolv.conf`.
- Search domains matter for short names; a missing `search` line explains "works with FQDN only".

## 6. Remediations (for the human)

```bash
# hook: ask — NEVER run; hand to the user
ssh -t web1 sudo netplan try          # applies with automatic rollback after 120 s
ssh -t db-prod-1 sudo nmcli connection up ens192
```

`netplan apply`, `nmcli … modify`, `ip … add|del`, `nft`/`ufw` changes on a remote host can cut the
session that runs them: the human uses an out-of-band console or `netplan try`, and the permanent
change goes through the infra repo.
