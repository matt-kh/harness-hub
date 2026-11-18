# Host triage — symptom decision tree

Start every investigation with `lx check HOST`, `lx facts HOST` and `lx health HOST`. Walk the
branch that matches the first crit/warn finding; the others are often consequences of it (a full
disk fails units, a memory leak triggers OOM kills and swap storms).

Every command here is read-only. Commands marked **for the human** need root or change the host:
write them into the report with their blast radius; never run them.

## 0. Cannot reach the host (`lx check` exit 2)

| Error line | Meaning | Next step |
|---|---|---|
| `unreachable: … Connection timed out` / `No route to host` | network path, host down, firewall | `lx check` another host behind the same bastion; ask whether the host is up (hypervisor / BMC console is the human's) |
| `unreachable: … Connection refused` | host up, sshd not listening on that port | sshd crashed or the port changed — console access is the human's |
| `unreachable: … Could not resolve hostname` | the alias's HostName does not resolve | `lx hosts` shows the HostName; DNS or a typo in the user's ssh config |
| `key auth failed` | no agent key / key not authorised | user: `ssh-add -l`, load the key; never fall back to passwords |
| `host key not verified` | new host or the key changed | user compares the fingerprint (rebuilt host or spoofing) and fixes `known_hosts` |
| `timed out after Ns (whole call)` | host is reachable but a probe hangs (stuck NFS mount, D-state I/O) | that *is* a finding: suspect storage (`§4`); retry `lx check` (no heavy probes) |

## 1. Failed systemd units (`kind=unit`)

1. `lx logs HOST --unit <unit> --since 2h --limit 200` — the last lines before `Failed with result`
   name the cause (`exit-code`, `signal`, `timeout`, `oom-kill`, `start-limit-hit`).
2. `ssh HOST systemctl status <unit> --no-pager` and `ssh HOST systemctl cat <unit>` — exit status,
   `ExecStart`, drop-ins.
3. Typical causes and where the fix lives:

| Result | Usual cause | Fix (infra repo) |
|---|---|---|
| `exit-code` right after start | config error, missing file or secret, port in use | the role / module that renders the config |
| `oom-kill` | `MemoryMax=` too low or a leak | unit drop-in `MemoryMax=` or the app's memory settings |
| `timeout` | slow start (DB recovery, big migration) | `TimeoutStartSec=` drop-in |
| `start-limit-hit` | crash loop | fix the crash first; `StartLimitIntervalSec=` only after |
| timer unit failed | the job's service failed | same tree for the `.service` |

**For the human**: `sudo systemctl restart <unit>` (blast radius: the service is down for the
restart; dependants restart with it), `sudo systemctl reset-failed <unit>` after the fix.

## 2. Load / slowness (`kind=load`, PSI)

- Load per CPU > 2 with low CPU use means tasks waiting on I/O (D state), not CPU.
  `ssh HOST top -b -n1 | head -30` (read-only) and `ssh HOST 'ps -eo state,pid,comm | grep "^D"'`.
- `lx health` reports `psi_some_avg10` for memory: ≥ 10 % means tasks stall for memory → §3.
- `ssh HOST cat /proc/pressure/io` and `/proc/pressure/cpu` complete the picture.
- A steal-heavy VM (`top` `st` column > 10 %) is a hypervisor / noisy-neighbour problem: the fix is
  placement or sizing, not the guest.

## 3. Memory (`kind=memory|swap|oom`)

1. `lx health` → `available%`, `swap_used%`, `oom_kills_24h`.
2. `lx logs HOST --since 24h --priority warning` and look for `Out of memory: Killed process` — it
   names the victim and its RSS.
3. `ssh HOST 'ps -eo rss,pid,comm --sort=-rss | head -15'` — the top consumers.
4. Containers: the kill may come from a cgroup limit (`memory.max`), not the host — the log line says
   `oom-kill:constraint=CONSTRAINT_MEMCG`.

Fix: the service's memory limits or sizing in the infra repo; adding swap is a mitigation, not a fix.

## 4. Disk / inodes full (`kind=disk|inodes|mount`)

Go to `storage.md` §1. Quick reads (every clause is on the guard's allow-list, so they pass):
`ssh HOST 'du -xh --max-depth=1 /var | sort -h | tail -15'` and
`ssh HOST journalctl --disk-usage`.

A filesystem mounted `ro` that should be `rw` almost always means the kernel remounted it after an
I/O or metadata error: `lx logs HOST --since 24h --priority err` and look for `EXT4-fs error`,
`XFS … Corruption`, `I/O error, dev …`. That is a storage incident, not a cleanup.

## 5. Pending reboot (`kind=reboot`)

- Debian/Ubuntu: `/var/run/reboot-required(.pkgs)` lists what needs it (kernel, libc, systemd).
- RHEL family: `needs-restarting -r` exit 1.
- NixOS: the booted kernel differs from the current generation's.

**For the human**: schedule the reboot in a window; on a cluster member drain first (Kubernetes:
`kubectl drain`; Proxmox: migrate guests; databases: fail over the primary).

## 6. Time not synchronised (`kind=time`)

`lx health` reads `timedatectl show -p NTPSynchronized -p NTP`. `timedatectl` and `chronyc` are
not on the guard's remote allow-list (raw `ssh HOST chronyc tracking` asks), so the deeper reads
are the human's: `chronyc tracking` / `chronyc sources` (chrony: RHEL, newer Ubuntu) or
`timedatectl timesync-status` (systemd-timesyncd). `lx logs HOST --unit chronyd --since 24h`
(`chrony` on Debian/Ubuntu, `systemd-timesyncd` elsewhere) usually shows why. Causes: NTP blocked by a firewall (udp
123), no reachable server configured, a VM with paused clock. TLS, Kerberos and distributed
databases fail first.

## 7. Network symptoms

Go to `networking.md`: no carrier, no default route, bond with one member, DNS failures, a firewall
that blocks the service.

## 8. Stop rule

After three unresolved hypotheses, stop and report what was checked, what was not verified
(`needs root` items, unreachable hosts), and the confidence of the best hypothesis.
