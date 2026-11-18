# Storage runbook

`lx storage HOST` first: block devices (`lsblk`), real mounts with read-only remounts flagged,
`df`, LVM volumes and groups (thin-pool fill), ZFS pools, md RAID and SMART health. Everything
below is read-only unless marked **for the human**. LVM, SMART and some ZFS reads need root on
most distributions; `lx` then reports `needs root` and the exact command goes to the user.

## 1. Disk full (`kind=disk`) or inodes full (`kind=inodes`)

1. Which mount and how fast: `lx health HOST` twice a few minutes apart; a mount that fills in
   hours is an incident (runaway log, core dumps, a stuck job), slow growth is capacity.
2. What fills it (each clause is on the allow-list):
   - `ssh HOST 'du -xh --max-depth=1 /var | sort -h | tail -15'` — `-x` stays on one filesystem.
   - `ssh HOST journalctl --disk-usage` — the journal; its cap is `SystemMaxUse=` in
     `journald.conf`.
   - `ssh HOST 'ls -la /var/crash /var/lib/systemd/coredump'` — crash dumps.
   - Docker / containerd: `ssh HOST 'du -sh /var/lib/docker/overlay2 /var/lib/containerd'`.
3. Deleted-but-open files keep space allocated (`df` full, `du` small): `lsof +L1` needs root —
   **for the human**: `sudo lsof +L1 | sort -k7 -n | tail`. Restarting the holder frees it.
4. Inodes full with free space: millions of small files (session dirs, mail queues, cache
   shards). `ssh HOST 'du -x --inodes --max-depth=2 /var | sort -n | tail -15'`.

Fixes: log rotation / journald caps / retention in the infra repo; growing a volume (below) is the
human's.

## 2. Read-only remount (`kind=mount`)

A filesystem that should be `rw` but is mounted `ro` was almost always remounted by the kernel after
an error (`errors=remount-ro` on ext4) or shut down by XFS.

1. `lx logs HOST --since 24h --priority err` — look for `EXT4-fs error`, `XFS (dm-…): Corruption`,
   `blk_update_request: I/O error`, `Buffer I/O error on dev`.
2. `ssh HOST dmesg --level=err,warn` (no `-w`, no `-C`).
3. Correlate with SMART (§6) and RAID (§5): a dying disk is the usual root cause.

**For the human**: stop the writers, unmount, `fsck` / `xfs_repair` from a maintenance window,
replace the disk first if SMART or the RAID says so. Never remount `rw` over an error.

## 3. LVM

| Read (needs root on most distros) | What it shows |
|---|---|
| `lvs -o lv_name,vg_name,lv_attr,lv_size,data_percent,metadata_percent,pool_lv` | thin-pool data and metadata fill (`lx` flags data ≥ 90 %) |
| `vgs -o vg_name,vg_size,vg_free` | free extents left for growth |
| `pvs` | which disks (or md arrays) back each group |

- A thin pool at 100 % data **or metadata** freezes every thin volume in it; metadata fill is the
  one people forget — ask the human for `sudo lvs -o +metadata_percent`.
- `lv_attr` first letter: `t` thin pool, `V` thin volume, `-` linear, `r` RAID; fifth `a` active;
  sixth `o` open.

**For the human** (blast radius: online, but a wrong size or name is hard to undo):
`sudo lvextend -r -L +20G vg/lv` (`-r` grows the filesystem too),
`sudo lvextend --poolmetadatasize +1G vg/pool`. Permanent sizing belongs in the provisioning code.

## 4. ZFS

- `lx storage` runs `zpool list -H -o name,size,alloc,free,cap,health` and `zpool status -x`.
  Raw reads: `ssh HOST zpool status -v POOL`, `ssh HOST zfs list -o name,used,avail,refer,mountpoint`,
  `ssh HOST zpool iostat -v 5 1` (bounded: one sample after 5 s).
- Health other than `ONLINE` (`DEGRADED`, `FAULTED`, `SUSPENDED`): `zpool status -v` names the vdev
  and the read / write / checksum error counters.
- Keep pools under 80 % (`lx` warns at 80, crit at 90): copy-on-write fragmentation makes writes slow
  long before the pool is full.
- Last scrub: the `scan:` line of `zpool status`; more than a month old on a data pool is a
  suggestion.
- Proxmox VE: `rpool` holds the OS and often guests; `local-zfs` storage maps to `rpool/data`.

**For the human**: `sudo zpool replace POOL OLD NEW`, `sudo zpool clear POOL` (only after the cause is
fixed), `sudo zpool scrub POOL` (I/O heavy — off-hours).

## 5. md RAID

- `/proc/mdstat` (no root needed): `[UU]` healthy, `[_U]` / `[U_]` degraded (`lx` crit), `(F)` marks
  the failed member, a `recovery =` / `resync =` line shows a rebuild in progress (`lx` info).
- `ssh HOST mdadm --detail /dev/md0` — state, failed / spare devices, event counts (works without
  root on some distros; otherwise **for the human**).
- A degraded array during a rebuild has no redundancy: no other disk work until it finishes.

**For the human**: `sudo mdadm --manage /dev/md0 --remove /dev/sdb1`, physical swap, partition the new
disk like the survivor, `sudo mdadm --manage /dev/md0 --add /dev/sdX1`. Update the alerting
(`mdadm --monitor` mail / `MAILADDR`) in the infra repo if nobody noticed.

## 6. SMART

- `lx storage` reports `PASSED`, `FAILED` (crit) or `needs root` per disk. VMs show `unknown`
  (virtual disks have no SMART); judge the hypervisor's disks instead.
- **For the human**: `sudo smartctl -H /dev/sda` (overall), `sudo smartctl -A /dev/sda` (attributes:
  `Reallocated_Sector_Ct`, `Current_Pending_Sector`, `Offline_Uncorrectable` rising = replace),
  NVMe: `sudo smartctl -a /dev/nvme0` (`Percentage Used`, `Media and Data Integrity Errors`).
- `smartctl -t long` starts a self-test (changes drive state, slows I/O): human only.

## 7. Mount layout and fstab

- `ssh HOST findmnt --verify` checks `/etc/fstab` syntax read-only.
- Network filesystems (`nfs`, `cifs`) that hang make `df` and `lx` time out: `ssh HOST findmnt -t
  nfs,nfs4,cifs` lists them; a hung NFS mount is a server or network problem.
- `nofail` / `x-systemd.automount` on non-root data mounts keeps a missing disk from blocking boot —
  a suggestion for the infra repo's fstab template.
