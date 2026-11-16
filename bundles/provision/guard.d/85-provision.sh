# shellcheck shell=bash

# Section 85 (bundle provision): provisioning tools — Proxmox VE, Talos, NixOS, libvirt and QEMU.
# Reads the definitions of the linux bundle's 82-linux.sh (provision depends on linux): the clause
# lexer (linux_scan with this section's own word list), linux_words / linux_cmd0 (wrappers sudo,
# env, timeout, xargs …; sh -c, eval and $(…) unwrapped), linux_pos, linux_is_dev, linux_target
# and linux_pve_ro (the Proxmox VE read forms, shared with the ssh remote allow-list). `ssh HOST
# qm …` is judged by 83-linux-rules (ask unless a read form). Rendering, validating and planning
# with `prov` never applies anything; every apply step is the human's. Asks are deferred (the
# first reason wins, a later deny still wins); denies exit. Reasons carry host=<target> [PROD]
# when a node, endpoint, context, --target-host or libvirt URI matches LINUX_PROD_RE, name the
# Proxmox VE node from PROVISION_PVE_HOST and the hosts repository from PROVISION_INFRA_ROOT.
# rule: prov … -> pass : renders, validates and plans only (never applies); use it first
# rule: proxmox-auto-install-assistant … | nix build|eval|flake check|flake show|path-info -> pass : write local files or read; use them to prepare and check artefacts
# rule: prov plan … | sh|bash | eval|source|sh -c "$(prov plan …)" -> ask : runs the printed apply steps; hand them to the user instead
# rule: qm|pct list|config|status|showcmd|pending|listsnapshot|help | pvesh get|ls|usage | pvecm status|nodes | pvesm status|list|path | pveum … list | ha-manager status|config -> pass : Proxmox VE reads; use them before planning a change
# rule: qm|pct create|destroy|clone|set|start|stop|shutdown|reboot|template|importdisk|disk import|migrate|rollback|snapshot|delsnapshot|resize|unlock|… | pvesh set|create|delete | pvecm|pveum|pvesm|pvenode|ha-manager changes -> ask : changes Proxmox VE guests, storage, users or the cluster; read with 'qm list' / 'pvesh get' instead, and hand the command to the user
# rule: talosctl gen …|validate|machineconfig …|get|version|health|dmesg|logs (no -f)|config info|contexts|images|services|disks|mounts|… | talosctl apply-config --dry-run -> pass : local generation, validation and node reads; use them first
# rule: talosctl apply-config (incl. --mode=try)|reset|upgrade|upgrade-k8s|bootstrap|reboot|shutdown|edit|patch|rotate-ca|wipe|restart|… (anything off the read list) -> ask : changes a live node or cluster; check with 'talosctl apply-config --dry-run' / 'talosctl validate' instead, and hand the command to the user
# rule: talosctl get machineconfig|*secrets -o yaml|json | --namespace secrets -o … -> ask : prints Talos key material; read with the default table output instead, or hand it to the user
# rule: talosctl kubeconfig | talosctl config merge|add|remove|context|endpoint|node|new -> deny : writes the human-managed kubeconfig or talosconfig; hand the command to the user instead
# rule: nixos-rebuild build|dry-build|build-vm|build-vm-with-bootloader|dry-run|list-generations (no --target-host/--build-host) -> pass : builds without activating; use it to check a configuration
# rule: nixos-rebuild switch|boot|test|dry-activate|… | nixos-rebuild … --target-host|--build-host -> ask : activates a configuration or runs on a remote host; build locally with 'nixos-rebuild build' instead, and hand the command to the user
# rule: nixos-anywhere … (no --vm-test) | nix run …#nixos-anywhere … -> ask : installs over ssh and wipes the target's disks; test with 'nixos-anywhere --vm-test' instead, and hand the install to the user
# rule: nixos-anywhere --vm-test … -> pass : a local VM test; use it before the real install
# rule: disko|disko-install (any --mode, no --dry-run) | nix run …#disko … -> ask : partitions, formats or mounts disks; check with 'disko --dry-run' or a VM test instead, and hand the command to the user
# rule: virsh list|dominfo|domstate|dumpxml|domblklist|domiflist|net-list|net-info|pool-list|pool-info|vol-list|capabilities|nodeinfo|version|… -> pass : libvirt reads; use them first
# rule: virsh destroy|undefine|define|create|start|shutdown|reboot|reset|vol-delete|vol-create*|pool-destroy|pool-delete|net-destroy|net-undefine|snapshot-revert|snapshot-delete|attach-*|detach-*|setmem|setvcpus|edit|console|… (anything off the read list) | bare virsh -> ask : changes a libvirt domain, volume, pool or network; read with 'virsh list --all' instead, and hand the command to the user
# rule: virt-install … (unless both --dry-run and --print-xml) -> ask : creates a VM; check with 'virt-install --dry-run --print-xml …' instead, and hand the command to the user
# rule: qemu-system-* -drive file=/dev/X | -hda|-hdb|-sd|-pflash /dev/X | a bare /dev/X operand | qemu-img convert|dd|create|resize|commit|rebase|… onto /dev/X -> ask : writes a block device; use an image file (disk.qcow2) instead, or hand the command to the user
# never-yields: the developer's Talos client credential (principle 8 exemption; runs even when the repository owns infrastructure)
# rule: <reader> ~/.talos/* | $TALOSCONFIG -> deny : the talosconfig holds the Talos client key; run 'talosctl config info' instead
# rule: talosctl kubeconfig - (written to stdout) -> deny : prints cluster credentials; hand 'talosctl kubeconfig' to the user instead
local pv_i pv_k pv_t pv_c pv_n
PROV_PRE_RE='(^|[^[:alnum:]_.-])(qm|pct|pvesh|pvecm|pveum|pvesm|pvenode|ha-manager|talosctl|nixos-rebuild(-ng)?|nixos-anywhere|disko(-install)?|virsh|virt-install|qemu-system-[[:alnum:]_]+|qemu-img|prov|nix|nix-shell)([^[:alnum:]_-]|$)'
PROV_TALOS_RE="(${HOME_RE:-~}/\\.talos(/|[[:space:]\"')]|\$)|\\\$\\{?TALOSCONFIG\\}?)"
# talosctl flags that take a value (so their value is never read as a subcommand)
PROV_TALOS_VF='-n|--nodes|-e|--endpoints|--context|--cluster|--talosconfig|-f|--file|-p|--patch|--config-patch|--config-patch-control-plane|--config-patch-worker|-m|--mode|-o|--output|-i|--image|--tail|--namespace|--timeout|--wait-timeout|--with-secrets|--output-dir|--output-types|-t|--output-types|--kubernetes-version|--talos-version|--install-disk|--install-image|--additional-sans|--dns-domain|--registry-mirror|--version-contract|--to|--from|--stage|--reboot-mode'
PROV_PVE_HINT=${PROVISION_PVE_HOST:+ (on the Proxmox VE node: ssh $PROVISION_PVE_HOST …)}
PROV_INFRA_HINT=${PROVISION_INFRA_ROOT:+; the host definitions live in $PROVISION_INFRA_ROOT and change through an MR}
PROV_SCANNED=false
prov_tgt() {  # VALUE… (comma lists, user@host, URIs) -> PROV_TGT = " (host=a,b [PROD])", or "" for no value
  local v h list="" prod=false
  local -a parts
  for v in "$@"; do
    [ -n "$v" ] || continue
    IFS=, read -ra parts <<<"$v"
    for h in "${parts[@]}"; do
      [ -n "$h" ] || continue
      linux_target "$h"
      h=${LINUX_TGT#host=}
      case "$h" in *' [PROD]') prod=true; h=${h% \[PROD\]} ;; esac
      list="${list:+$list,}$h"
    done
  done
  PROV_TGT=""
  [ -n "$list" ] || return 0
  if $prod; then PROV_TGT=" (host=$list [PROD])"; else PROV_TGT=" (host=$list)"; fi
  return 0
}
prov_talos_tgt() {  # talosctl WORDS… -> PROV_TGT from -n/--nodes, -e/--endpoints and --context values
  local w next=false
  local -a vals=()
  for w in "$@"; do
    if $next; then vals+=("$w"); next=false; continue; fi
    case "$w" in
      -n|--nodes|-e|--endpoints|--context) next=true ;;
      --nodes=*|--endpoints=*|--context=*) vals+=("${w#*=}") ;;
    esac
  done
  prov_tgt "${vals[@]}"
}
if [ -n "${READER_RE:-}" ] && printf '%s' "$flat" | grep -qE '\.talos|TALOSCONFIG'; then
  while IFS= read -r pv_c; do
    [ -n "$pv_c" ] || continue
    pv_c=$(printf '%s' "$pv_c" | sed 's/[[:space:]]/& /g')   # as core 20: \s+ cannot swallow the boundary
    printf '%s' "$pv_c" | grep -qE "${READER_RE}${PROV_TALOS_RE}" \
      && deny "reading the talosconfig (~/.talos/*, \$TALOSCONFIG) exposes the Talos client key — run 'talosctl config info' or 'talosctl config contexts' instead"
  done <<EOF
$(printf '%s' "$flat" | tr ';&|' '\n\n\n')
EOF
fi
if linux_scan "$PROV_PRE_RE"; then
  PROV_SCANNED=true
  pv_i=0
  while [ "$pv_i" -lt "${#LQ[@]}" ]; do
    pv_k=${LQ[pv_i]%%"$LINUX_TABC"*}; pv_t=${LQ[pv_i]#*"$LINUX_TABC"}; pv_i=$((pv_i+1))
    case "$pv_k" in T|P) ;; *) continue ;; esac
    linux_words "$pv_t" || continue
    linux_cmd0
    [ "$LC" = talosctl ] || continue
    linux_pos "$PROV_TALOS_VF" "${LW[@]:$((LI+1))}"
    pv_n=${#LP[@]}
    if [ "${LP[0]:-}" = kubeconfig ] && [ "$pv_n" -ge 2 ] && [ "${LP[1]}" = - ]; then
      deny "talosctl kubeconfig - prints the cluster's admin credentials — hand 'talosctl kubeconfig' to the user instead (the kubeconfig is human-managed)"
    fi
  done
fi
repo_owns provision/guard.d/85-provision infrastructure && return 0   # principle 8: the repository's .harness.toml owns this section or domain infrastructure
$PROV_SCANNED || return 0
local pv_m pv_ok
prov_judge() {  # CMD WORDS… -> defer or deny for one provisioning command (CMD = its basename); LXA from linux_cmd0
  local c=$1 a b w i n prev part v act remote mode dev
  local -a args parts
  shift
  case "$c" in
    # ---- prov: the renderer never applies -------------------------------------------------------
    prov) ;;
    # ---- Proxmox VE ------------------------------------------------------------------------------
    qm|pct|pvesh|pvecm|pvesm|pveum|pvenode|ha-manager)
      if $LXA && [ $# -eq 0 ]; then
        defer "$c run through xargs takes its action from stdin, so it cannot be checked — run one literal '$c …' per guest instead, or hand it to the user$PROV_PVE_HINT"
        return 0
      fi
      linux_pve_ro "$c" "$@" \
        || defer "$LR_WHY — read with 'qm list', 'qm config VMID' or 'pvesh get PATH' instead, and hand the command to the user$PROV_PVE_HINT" ;;
    # ---- Talos -----------------------------------------------------------------------------------
    talosctl)
      linux_pos "$PROV_TALOS_VF" "$@"
      a=${LP[0]:-}; b=${LP[1]:-}
      prov_talos_tgt "$@"
      if [ -z "$a" ]; then
        $LXA && defer "talosctl run through xargs takes its subcommand from stdin — run one literal 'talosctl <read verb>' instead, or hand it to the user"
        return 0
      fi
      case "$a" in
        kubeconfig)
          deny "talosctl kubeconfig writes or prints a kubeconfig with cluster credentials (human-managed, see the k8s rule)$PROV_TGT — hand the command to the user instead" ;;
        config)
          case "$b" in
            ''|info|contexts|help) ;;
            merge|add|remove|context|endpoint|endpoints|node|nodes|new)
              deny "talosctl config $b writes the talosconfig (~/.talos/config, human-managed) — hand the command to the user instead, and pass -n / -e / --talosconfig per command" ;;
            *) defer "talosctl config $b is not on the read list — run 'talosctl config info' instead, or hand the command to the user" ;;
          esac ;;
        gen|validate|version|health|machineconfig|mc|completion|docs|help|images|containers|c|processes|ps|memory|mounts|disks|netstat|stats|time|usage|du|list|ls|inspect) ;;
        get|g)
          pv_m=""; pv_ok=false
          i=0; args=("$@"); n=${#args[@]}
          while [ "$i" -lt "$n" ]; do
            w=${args[i]}; i=$((i+1))
            case "$w" in
              -o|--output) pv_m=${args[i]:-}; i=$((i+1)) ;;
              -o?*) pv_m=${w#-o} ;;
              --output=*) pv_m=${w#--output=} ;;
              --namespace=secrets) pv_ok=true ;;
              --namespace) [ "${args[i]:-}" = secrets ] && pv_ok=true; i=$((i+1)) ;;
            esac
          done
          printf '%s' "$b" | grep -qiE '^(mc|machineconfigs?|[[:alnum:]]*secrets?)$' && pv_ok=true
          if $pv_ok; then
            case "$pv_m" in yaml|json|jsonpath*|go-template*)
              defer "talosctl get $b -o $pv_m prints Talos key material$PROV_TGT — read with the default table output instead, or hand it to the user" ;;
            esac
          fi ;;
        logs|dmesg)
          for w in "$@"; do
            case "$w" in
              --follow|--follow=true) defer "talosctl $a --follow never returns — pass --tail N instead"; break ;;
              --*) ;;
              -*) linux_sflag f "$w" && { defer "talosctl $a -f never returns — pass --tail N instead"; break; } ;;
            esac
          done ;;
        service|services)
          case "${LP[2]:-}" in ''|status) ;; *) defer "talosctl service $b ${LP[2]} changes a service on a live node$PROV_TGT — read with 'talosctl services' instead, and hand the command to the user" ;; esac ;;
        image)
          case "$b" in ''|list|ls|default|cache-create|help) ;; *) defer "talosctl image $b changes the node's image cache$PROV_TGT — read with 'talosctl image list' instead, and hand the command to the user" ;; esac ;;
        etcd)
          case "$b:${LP[2]:-}" in members:*|status:*|alarm:list|help:*|:) ;;
            *) defer "talosctl etcd $b is not a read (snapshots hold every Secret, the rest change the cluster)$PROV_TGT — read with 'talosctl etcd members' / 'talosctl etcd status' instead, and hand the command to the user" ;;
          esac ;;
        apply-config|apply)
          for w in "$@"; do [ "$w" = --dry-run ] && return 0; done
          mode=""
          for w in "$@"; do case "$w" in --mode=*) mode=" --mode=${w#--mode=}" ;; esac; done
          defer "talosctl $a$mode changes a live node$PROV_TGT (--mode=try still applies it until the timeout) — check with 'talosctl apply-config --dry-run' or 'talosctl validate' instead, and hand the command to the user$PROV_INFRA_HINT" ;;
        reset|upgrade|upgrade-k8s|bootstrap|reboot|shutdown|edit|patch|rotate-ca|wipe|restart|meta|cluster)
          defer "talosctl $a changes a live node or cluster$PROV_TGT — check with 'talosctl validate' / 'talosctl health' instead, and hand the command to the user$PROV_INFRA_HINT" ;;
        *) defer "talosctl $a is not on the read list$PROV_TGT — use 'talosctl get|logs --tail|services|version' instead, or hand the command to the user" ;;
      esac ;;
    # ---- NixOS -----------------------------------------------------------------------------------
    nixos-rebuild|nixos-rebuild-ng)
      act=""; remote=""; i=0; args=("$@"); n=${#args[@]}
      local -a hosts=()
      while [ "$i" -lt "$n" ]; do
        w=${args[i]}; i=$((i+1))
        case "$w" in
          --target-host|--build-host) remote="${remote:+$remote, }$w"; hosts+=("${args[i]:-}"); i=$((i+1)) ;;
          --target-host=*|--build-host=*) remote="${remote:+$remote, }${w%%=*}"; hosts+=("${w#*=}") ;;
          --option) i=$((i+2)) ;;
          --flake|-I|--include|--profile-name|-p|--specialisation|-c|--max-jobs|-j|--cores|--file|-f|--attr|-A|--builders|--store|--eval-store) i=$((i+1)) ;;
          -*) ;;
          *) [ -n "$act" ] || act=$w ;;
        esac
      done
      prov_tgt "${hosts[@]}"
      if [ -n "$remote" ]; then
        defer "nixos-rebuild ${act:+$act }with $remote runs on a remote host$PROV_TGT — build locally with 'nixos-rebuild build --flake …' instead, and hand the command to the user$PROV_INFRA_HINT"
        return 0
      fi
      case "$act" in
        '') $LXA && defer "nixos-rebuild run through xargs takes its action from stdin — run 'nixos-rebuild build' literally instead, or hand it to the user" ;;
        build|dry-build|build-vm|build-vm-with-bootloader|dry-run|list-generations|repl) ;;
        switch|boot|test|dry-activate)
          defer "nixos-rebuild $act activates a system configuration on this machine — build it with 'nixos-rebuild build' or 'build-vm' instead, and hand the command to the user$PROV_INFRA_HINT" ;;
        *) defer "nixos-rebuild $act is not a build — use 'nixos-rebuild build' or 'build-vm' instead, or hand the command to the user" ;;
      esac ;;
    nixos-anywhere)
      local -a hosts=()
      for w in "$@"; do
        case "$w" in --vm-test|--help|-h|--version) return 0 ;; -*) ;; *@*) hosts=("$w") ;; esac
      done
      [ "${#hosts[@]}" -gt 0 ] || { [ $# -gt 0 ] && case "${*: -1}" in -*) ;; *) hosts=("${*: -1}") ;; esac; }
      prov_tgt "${hosts[@]}"
      defer "nixos-anywhere installs over ssh and wipes the target's disks$PROV_TGT — test with 'nixos-anywhere --vm-test --flake …' instead, and hand the install to the user$PROV_INFRA_HINT" ;;
    disko|disko-install)
      mode=""; i=0; args=("$@"); n=${#args[@]}
      while [ "$i" -lt "$n" ]; do
        w=${args[i]}; i=$((i+1))
        case "$w" in
          --dry-run|--help|-h) return 0 ;;
          -m|--mode) mode=${args[i]:-}; i=$((i+1)) ;;
          --mode=*) mode=${w#--mode=} ;;
        esac
      done
      defer "$c${mode:+ --mode $mode} partitions, formats or mounts disks — check with '$c --dry-run' or a VM test ('nixos-anywhere --vm-test') instead, and hand the command to the user$PROV_INFRA_HINT" ;;
    nix)
      # nix run <tool> -- ARGS | nix shell|develop … --command|-c CMD ARGS: judge the tool it runs
      linux_pos '' "$@"
      case "${LP[0]:-}" in
        run)
          i=0; args=("$@"); n=${#args[@]}; v=""
          while [ "$i" -lt "$n" ] && [ "${args[i]}" != run ]; do i=$((i+1)); done
          i=$((i+1))
          while [ "$i" -lt "$n" ]; do
            w=${args[i]}; i=$((i+1))
            case "$w" in
              --option|--override-input|--arg|--argstr) i=$((i+2)); continue ;;
              -I|--include|--inputs-from|-f|--file|--expr|--profile|--store|--eval-store) i=$((i+1)); continue ;;
              -*) continue ;;
            esac
            v=$w; break
          done
          [ -n "$v" ] || return 0
          case "$v" in
            *'#nixos-anywhere'|*nixos-anywhere|*nixos-anywhere/*) b=nixos-anywhere ;;
            *'#disko-install') b=disko-install ;;
            *'#disko'|*nix-community/disko|*nix-community/disko/*) b=disko ;;
            *'#nixos-rebuild'|*'#nixos-rebuild-ng') b=nixos-rebuild ;;
            *) return 0 ;;
          esac
          args=("${args[@]:$i}")
          [ "${args[0]:-}" = -- ] && args=("${args[@]:1}")
          prov_judge "$b" "${args[@]}" ;;
        shell|develop)
          i=0; args=("$@"); n=${#args[@]}
          while [ "$i" -lt "$n" ]; do
            w=${args[i]}; i=$((i+1))
            case "$w" in -c|--command) [ "$i" -lt "$n" ] && prov_judge "${args[i]##*/}" "${args[@]:$((i+1))}"; return 0 ;; esac
          done ;;
      esac ;;
    nix-shell)
      i=0; args=("$@"); n=${#args[@]}
      while [ "$i" -lt "$n" ]; do
        w=${args[i]}; i=$((i+1))
        case "$w" in --run|--command) [ "$i" -lt "$n" ] && linux_lex_into "${args[i]}"; i=$((i+1)) ;; esac
      done ;;
    # ---- libvirt ---------------------------------------------------------------------------------
    virsh)
      i=0; args=("$@"); n=${#args[@]}; a=""
      local -a hosts=()
      while [ "$i" -lt "$n" ]; do
        w=${args[i]}; i=$((i+1))
        case "$w" in
          -c|--connect) hosts+=("${args[i]:-}"); i=$((i+1)) ;;
          --connect=*) hosts+=("${w#--connect=}") ;;
          -l|--log|-k|--keepalive-interval|-K|--keepalive-count|-e|--escape|-d|--debug) i=$((i+1)) ;;
          -*) ;;
          *) a=$w; break ;;
        esac
      done
      prov_tgt "${hosts[@]}"
      case "$a" in
        '') if $LXA; then defer "virsh run through xargs takes its command from stdin — run one literal 'virsh <read command>' instead, or hand it to the user"
            else defer "bare virsh opens an interactive shell$PROV_TGT — run one 'virsh list --all' / 'virsh dominfo DOMAIN' instead, or hand the session to the user"; fi ;;
        list|dominfo|domstate|dumpxml|domblklist|domiflist|domblkinfo|domblkstat|domifaddr|domstats|dommemstat|vcpuinfo|vcpucount|domuuid|domname|domid|domhostname|net-list|net-info|net-dumpxml|pool-list|pool-info|pool-dumpxml|vol-list|vol-info|vol-dumpxml|vol-path|capabilities|domcapabilities|nodeinfo|nodememstats|nodecpustats|sysinfo|version|uri|hostname|help|snapshot-list|snapshot-info|snapshot-dumpxml|snapshot-current|iface-list|nwfilter-list|nodedev-list|secret-list) ;;
        *) defer "virsh $a changes a libvirt domain, volume, pool or network, or is off the read list$PROV_TGT — read with 'virsh list --all' / 'virsh dominfo DOMAIN' instead, and hand the command to the user" ;;
      esac ;;
    virt-install)
      v=""; local -a hosts=()
      i=0; args=("$@"); n=${#args[@]}
      while [ "$i" -lt "$n" ]; do
        w=${args[i]}; i=$((i+1))
        case "$w" in
          --dry-run) v="$v d" ;;
          --print-xml|--print-xml=*) v="$v x" ;;
          --help|-h|--version) return 0 ;;
          --connect) hosts+=("${args[i]:-}"); i=$((i+1)) ;;
          --connect=*) hosts+=("${w#--connect=}") ;;
        esac
      done
      case "$v" in *d*x*|*x*d*) return 0 ;; esac
      prov_tgt "${hosts[@]}"
      defer "virt-install creates a VM$PROV_TGT — check with 'virt-install --dry-run --print-xml …' instead, and hand the command to the user" ;;
    # ---- QEMU ------------------------------------------------------------------------------------
    qemu-system-*)
      prev=""; dev=""
      for w in "$@"; do
        if [ "$prev" != -cdrom ]; then
          case "$w" in /dev/*) linux_is_dev "$w" && dev=$w ;; esac
          IFS=, read -ra parts <<<"$w"
          for part in "${parts[@]}"; do
            case "$part" in file=*|filename=*) v=${part#*=}; linux_is_dev "$v" && dev=$v ;; esac
          done
        fi
        [ -n "$dev" ] && break
        prev=$w
      done
      [ -n "$dev" ] && defer "$c uses the block device $dev as a VM disk (the guest writes it) — use an image file (-drive file=disk.qcow2) instead, or hand the command to the user" ;;
    qemu-img)
      linux_pos '-f|-F|-O|-o|-b|-B|-l|-s|-t|-T|-S|-m|-r|-c|-a|-d|--object' "$@"
      a=${LP[0]:-}; dev=""
      case "$a" in
        convert) n=${#LP[@]}; [ "$n" -ge 3 ] && linux_is_dev "${LP[n-1]}" && dev=$LD_WHAT ;;
        dd) for w in "$@"; do case "$w" in of=*) linux_is_dev "${w#of=}" && dev=$LD_WHAT ;; esac; done ;;
        create|resize|amend|commit|rebase|snapshot|bitmap)
          for w in "${LP[@]:1}"; do linux_is_dev "$w" && { dev=$LD_WHAT; break; }; done ;;
      esac
      [ -n "$dev" ] && defer "qemu-img $a writes the block device $dev — write to an image file (disk.qcow2) instead, or hand the command to the user" ;;
  esac
  return 0
}
pv_i=0
while [ "$pv_i" -lt "${#LQ[@]}" ]; do   # nix-shell --run appends clauses: the bound is re-read each pass
  pv_k=${LQ[pv_i]%%"$LINUX_TABC"*}; pv_t=${LQ[pv_i]#*"$LINUX_TABC"}; pv_i=$((pv_i+1))
  case "$pv_k" in T|P) ;; *) continue ;; esac
  linux_words "$pv_t" || continue
  linux_cmd0
  [ -n "$LC" ] || continue
  # prov plan … | sh: the printed apply steps would run
  if [ "$LC" = prov ] && [ "$pv_k" = P ]; then
    linux_pos '--root' "${LW[@]:$((LI+1))}"
    if [ "${LP[0]:-}" = plan ] && [ "$pv_i" -lt "${#LQ[@]}" ]; then
      pv_c=${LQ[pv_i]#*"$LINUX_TABC"}
      if linux_words "$pv_c"; then
        linux_cmd0
        case "$LC" in sh|bash|zsh|dash|ksh|ash|mksh|source|.)
          defer "prov plan piped into a shell runs the printed apply steps — hand the plan to the user to run step by step instead" ;;
        esac
      fi
      continue
    fi
  fi
  prov_judge "$LC" "${LW[@]:$((LI+1))}"
done
printf '%s' "$flat" | grep -qE '(^|[;&|(`[:space:]])(eval|source|\.|(ba|z|da|k|mk)?sh)[[:space:]]+([^;&|]*[[:space:]])?["'"'"']?(\$\(|<\(|`)[[:space:]]*prov[[:space:]]([^)`]*[[:space:]])?plan([[:space:])`]|$)' \
  && defer "running the output of prov plan executes the printed apply steps — hand the plan to the user to run step by step instead"
return 0
