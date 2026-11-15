# shellcheck shell=bash

# Section 83 (bundle linux): Linux hosts over SSH, local block devices and host network changes.
# Reads the definitions of 82-linux.sh (lexer, ssh/scp/rsync parsing, remote allow-list, device
# targets). Asks are deferred (the first reason wins, a later deny still wins); denies exit.
# Reasons carry host=<alias> and [PROD] when the alias matches LINUX_PROD_RE.
# rule: ssh … -o StrictHostKeyChecking=no|off|false | UserKnownHostsFile=/dev/null (any spelling: -oX=Y, -o 'X Y', GIT_SSH_COMMAND=, RSYNC_RSH=, rsync -e, scp -o, git -c core.sshCommand, an ssh_config heredoc) -> deny : disables host-key checking; use StrictHostKeyChecking=accept-new, or add the host key to known_hosts after checking its fingerprint, instead
# rule: sshpass … | an embedded 'sshpass -p|-f|-e|-d' -> deny : a password on the command line; use key-based auth through ssh-agent (ssh-add) instead
# rule: ssh HOST (no remote command) | ssh -t|-tt HOST … -> ask : interactive session; run 'lx' or 'ssh HOST <read-only command>' instead, or hand the session to the user
# rule: ssh -L|-R|-D|-W|-w|-N|-f|-A|-X|-Y|-M|-O | -o ProxyCommand|LocalCommand|LocalForward|RemoteForward|DynamicForward|RemoteCommand|Tunnel|ForwardAgent|RequestTTY|ControlMaster -> ask : forwarding, tunnel or local command; hand the command to the user instead, and run read-only checks with 'lx'
# rule: ssh HOST <command> unless every clause (split on ; && || | & newline, also inside quotes) is on the read-only allow-list (cat, head, tail without -f, ls, stat, journalctl without -f, systemctl status|show|is-*|list-*|cat, ip show forms, ss, df, lsblk, zpool status|list, nft list, iptables -L|-S, …); remote sudo, sh|bash -c, eval, $(…), backticks, $VAR, redirections (2>/dev/null and 2>&1 excepted), heredocs -> ask : not read-only on the host; use 'lx' for read-only checks, or hand the command to the user (on [PROD] as a suggestion with its blast radius) instead
# rule: ssh run through xargs without -I (arguments appended from stdin) -> ask : the remote command cannot be checked; run one literal 'ssh HOST <command>' per host instead
# rule: scp|rsync … HOST:path as the destination (an upload) | rsync --rsync-path|--remove-source-files | sftp | ssh-copy-id -> ask : writes to a host; download with 'scp HOST:/path .' instead, or hand the copy to the user (host changes go through the infra repository)
# rule: dd of=/dev/X | > /dev/X | cp|tee … /dev/X (not /dev/null|zero|stdout|stderr|tty) -> ask : writes a block device; run it against an image file (of=disk.img) instead, or hand the command to the user
# rule: wipefs -a|-o, sgdisk, sfdisk, parted, fdisk, gdisk (not their -l/print forms), mkfs[.*], mke2fs, mkswap, blkdiscard, cryptsetup luksFormat|erase on /dev/X (loop, nbd, mapper included), a $VAR target or xargs-appended targets -> ask : destroys a block device; run it on an image file (mkfs.ext4 disk.img) instead, or hand the command to the user
# rule: pvcreate|pvremove|pvmove|vgcreate|vgremove|vgreduce|lvcreate|lvremove|lvreduce|lvresize | zpool create|destroy|labelclear | zfs destroy|rollback | mdadm --create|--zero-superblock -> ask : changes LVM, ZFS or RAID storage; read with lvs, zpool status or mdadm --detail instead, and hand the change to the user
# rule: nft flush|add|delete|insert|replace|create|destroy|reset|-f | ufw enable|disable|allow|deny|reject|limit|delete|reset|insert|route|default|reload | netplan apply|try|generate|set | nmcli mutations | ip <object> add|del|set|change|replace|flush|… | iptables|ip6tables -A|-I|-D|-F|-P|-X|-N|-R|-Z|-E | iptables-restore -> ask : changes the host firewall or network; read with 'nft list ruleset', 'ip -br a' or 'ufw status' instead, and hand the change to the user (it can cut off the session)
# rule: lx … -> pass : the read-only linux CLI (bounded, redacted, reads ~/.ssh/config aliases, never keys); use it first
# never-yields: copies the developer's SSH private key off this machine (principle 8 exemption; runs even when the repository owns infrastructure)
# rule: scp|rsync|sftp <a file under ~/.ssh other than *.pub> as a source | sftp put ~/.ssh/<key> | ssh-copy-id -i <private key> | ssh … < ~/.ssh/<key> -> deny : copies a private key off this machine; copy the public key (~/.ssh/<key>.pub) instead — ssh-copy-id -i ~/.ssh/<key>.pub HOST asks
local lx_i lx_k lx_t lx_j lx_n lx_w lx_last lx_pre lx_sftp=false
local lx_put_re='^[[:space:]]*(put|mput|reput)[[:space:]]+([^[:space:]]+)' lx_put2_re='(put|mput|reput)[[:space:]]+([^[:space:]"'"'"']+)'
local lx_lt_re='<[[:space:]]*["'"'"']?([^[:space:]"'"'"';&|]+)'
LINUX_SCANNED=false; LINUX_IN_DEV=false
linux_key_deny() {  # WHAT -> deny: a private key leaves the machine
  deny "$1 copies an SSH private key off this machine — copy the public key (~/.ssh/<key>.pub) instead; 'ssh-copy-id -i ~/.ssh/<key>.pub HOST' asks"
}
if linux_scan; then
  LINUX_SCANNED=true
  printf '%s' "$flat" | grep -qE '(^|[^[:alnum:]_.-])sftp([^[:alnum:]_-]|$)' && lx_sftp=true
  lx_i=0
  while [ "$lx_i" -lt "${#LQ[@]}" ]; do
    lx_k=${LQ[lx_i]%%"$LINUX_TABC"*}; lx_t=${LQ[lx_i]#*"$LINUX_TABC"}; lx_i=$((lx_i+1))
    case "$lx_k" in
      H|B)  # heredoc data: an sftp batch that puts a private key
        if $lx_sftp && [[ $lx_t =~ $lx_put_re ]]; then
          linux_ssh_key "${BASH_REMATCH[2]}" && linux_key_deny "sftp put ${BASH_REMATCH[2]}"
        fi
        continue ;;
    esac
    linux_words "$lx_t" || continue
    linux_cmd0
    case "$LC" in
      scp|rsync)
        if [ "$LC" = scp ]; then linux_scp_parse $((LI+1)); else linux_rsync_parse $((LI+1)); fi
        lx_n=${#LP[@]}; [ "$lx_n" -ge 2 ] && lx_n=$((lx_n-1))
        lx_j=0
        while [ "$lx_j" -lt "$lx_n" ]; do
          linux_ssh_key "${LP[lx_j]}" && linux_key_deny "$LC ${LP[lx_j]}"
          lx_j=$((lx_j+1))
        done ;;
      sftp)
        lx_j=$((LI+1))
        while [ "$lx_j" -lt "${#LW[@]}" ]; do
          lx_w=${LW[lx_j]}; lx_j=$((lx_j+1))
          case "$lx_w" in -i|-F|-o|-P|-b|-c|-D|-l|-R|-S|-B|-J|-X) lx_j=$((lx_j+1)); continue ;; -*) continue ;; esac
          linux_ssh_key "$lx_w" && linux_key_deny "sftp $lx_w"
        done
        if [[ $lx_t =~ $lx_put2_re ]]; then
          linux_ssh_key "${BASH_REMATCH[2]}" && linux_key_deny "sftp put ${BASH_REMATCH[2]}"
        fi ;;
      ssh-copy-id)
        lx_j=$((LI+1))
        while [ "$lx_j" -lt "${#LW[@]}" ]; do
          lx_w=${LW[lx_j]}; lx_j=$((lx_j+1))
          case "$lx_w" in
            -i) linux_ssh_key "${LW[lx_j]:-}" && linux_key_deny "ssh-copy-id -i ${LW[lx_j]}" ;;
            -i?*) linux_ssh_key "${lx_w#-i}" && linux_key_deny "ssh-copy-id $lx_w" ;;
          esac
        done ;;
      ssh)
        if [[ $lx_t =~ $lx_lt_re ]]; then
          linux_ssh_key "${BASH_REMATCH[1]}" && linux_key_deny "ssh … < ${BASH_REMATCH[1]}"
        fi ;;
    esac
  done
fi
repo_owns linux/guard.d/83-linux-rules infrastructure && return 0   # principle 8: the repository's .harness.toml owns this section or domain infrastructure
$LINUX_SCANNED || return 0
# relative operands name devices when the command (or the hook's cwd) is inside /dev
case "${cwd:-}" in /dev|/dev/*) LINUX_IN_DEV=true ;; esac
printf '%s' "$flat" | grep -qE '(^|[;&|({[:space:]])(cd|pushd)[[:space:]]+["'"'"']?/dev(/|["'"'"'[:space:];&|)]|$)' && LINUX_IN_DEV=true
lx_i=0
while [ "$lx_i" -lt "${#LQ[@]}" ]; do
  lx_k=${LQ[lx_i]%%"$LINUX_TABC"*}; lx_t=${LQ[lx_i]#*"$LINUX_TABC"}; lx_i=$((lx_i+1))
  # ---- host-key checking off / sshpass: deny (text tools that only print or search are exempt) --
  if printf '%s' "$lx_t" | grep -qiE "$LINUX_HKC_RE|$LINUX_UKH_RE|$LINUX_SSHPASS_RE"; then
    if [ "$lx_k" = H ]; then
      deny "an ssh_config written with StrictHostKeyChecking no / UserKnownHostsFile /dev/null disables host-key checking — use StrictHostKeyChecking accept-new, or add the host key to known_hosts after checking its fingerprint, instead"
    fi
  fi
  case "$lx_k" in T|P) ;; *) continue ;; esac
  if ! linux_words "$lx_t"; then
    printf '%s' "$lx_t" | grep -qE '(^|[^[:alnum:]_.-])(ssh|scp|sftp|rsync|ssh-copy-id)([^[:alnum:]_-]|$)' \
      && defer "could not parse an ssh/scp/rsync command line (unbalanced quotes) — pass balanced literal arguments instead"
    continue
  fi
  linux_cmd0
  if printf '%s' "$lx_t" | grep -qiE "$LINUX_HKC_RE|$LINUX_UKH_RE|$LINUX_SSHPASS_RE"; then
    lx_pre=""; [ "$LI" -gt 0 ] && lx_pre="${LW[*]:0:$LI}"
    lx_w=false
    if ! printf '%s' "$lx_pre" | grep -qiE "$LINUX_HKC_RE|$LINUX_UKH_RE|$LINUX_SSHPASS_RE"; then
      case "$LC" in
        grep|egrep|fgrep|zgrep|rg|ag|man) lx_w=true ;;
        echo|printf) [ "$lx_k" = T ] && ! printf '%s' "$lx_t" | grep -qE '>' && lx_w=true ;;
        git) linux_pos '-c|-C|--git-dir|--work-tree|--namespace' "${LW[@]:$((LI+1))}"
             case "${LP[0]:-}" in commit|log|show|diff|grep) lx_w=true ;; esac ;;
      esac
    fi
    if ! $lx_w; then
      printf '%s' "$lx_t" | grep -qiE "$LINUX_SSHPASS_RE" && ! printf '%s' "$lx_t" | grep -qiE "$LINUX_HKC_RE|$LINUX_UKH_RE" \
        && deny "sshpass puts a password on the command line — use key-based auth through ssh-agent (ssh-add) instead"
      deny "disables SSH host-key checking (StrictHostKeyChecking=no / UserKnownHostsFile=/dev/null) — use StrictHostKeyChecking=accept-new, or add the host key to known_hosts after checking its fingerprint, instead"
    fi
  fi
  [ -n "$LC" ] || continue
  [ "$LC" = sshpass ] && deny "sshpass puts a password on the command line — use key-based auth through ssh-agent (ssh-add) instead"
  # ---- writes into a device by redirection: ask --------------------------------------------
  if printf '%s' "$lx_t" | grep -qE "$LINUX_REDIR_DEV_RE"; then
    while IFS= read -r lx_w; do
      lx_w=${lx_w#*/dev/}; lx_w="/dev/$lx_w"
      linux_is_dev "$lx_w" && { defer "writes the device $lx_w by redirection — write to an image file instead, or hand the command to the user"; break; }
    done <<EOF
$(printf '%s' "$lx_t" | grep -oE "$LINUX_REDIR_DEV_RE")
EOF
  fi
  case "$LC" in
    lx) ;;
    # ---- ssh: interactive, forwarding, remote commands that are not read-only -----------------
    ssh)
      if $LXA; then defer "ssh run through xargs appends arguments from stdin, so the remote command cannot be checked — run one literal 'ssh HOST <command>' per host instead"; continue; fi
      linux_ssh_parse $((LI+1))
      [ -n "$LS_HOST" ] && ! $LS_NOCONN || continue
      linux_target "$LS_HOST"
      if [ -n "$LS_ASK" ]; then
        defer "ssh with $LS_ASK ($LINUX_TGT) — hand the command to the user instead, and run read-only checks with 'lx' or 'ssh HOST <read-only command>'"
      elif ! $LS_HASCMD; then
        defer "interactive ssh session ($LINUX_TGT) — run 'lx' or 'ssh HOST <read-only command>' (e.g. cat /etc/os-release) instead, or hand the session to the user"
      elif ! linux_remote_ro "$LS_CMD"; then
        defer "ssh remote command that is not read-only ($LINUX_TGT: $LR_WHY) — use 'lx' for read-only checks, or hand the command to the user (on [PROD] as a suggestion with its blast radius) instead"
      fi ;;
    scp|rsync)
      if [ "$LC" = scp ]; then linux_scp_parse $((LI+1)); else linux_rsync_parse $((LI+1)); fi
      if $LXA; then defer "$LC run through xargs appends its operands from stdin — run one literal copy per file instead, or hand it to the user"; continue; fi
      lx_n=${#LP[@]}
      if [ "$lx_n" -ge 2 ] && linux_remote_spec "${LP[lx_n-1]}"; then
        linux_target "$LT_HOST"
        defer "$LC upload to a remote host ($LINUX_TGT) — download with '$LC HOST:/path .' instead, or hand the copy to the user (host changes go through the infra repository)"
      elif [ -n "$LS_ASK" ]; then
        defer "$LC with $LS_ASK — hand the command to the user instead, or download with '$LC HOST:/path .'"
      fi ;;
    sftp) defer "sftp is an interactive or batch file transfer that can write to the host — download with 'scp HOST:/path .' instead, or hand uploads to the user" ;;
    ssh-copy-id)
      lx_last=${LW[${#LW[@]}-1]}; linux_target "$lx_last"
      defer "ssh-copy-id installs a key on a host ($LINUX_TGT) — hand the command to the user instead" ;;
    # ---- local block devices: ask ------------------------------------------------------------
    dd)
      lx_j=$((LI+1))
      while [ "$lx_j" -lt "${#LW[@]}" ]; do
        lx_w=${LW[lx_j]}; lx_j=$((lx_j+1))
        case "$lx_w" in of=*) linux_is_dev "${lx_w#of=}" && defer "dd writes the block device $LD_WHAT — run it against an image file (of=disk.img) instead, or hand the command to the user" ;; esac
      done
      $LXA && defer "dd run through xargs takes its operands from stdin — run it with a literal of=FILE instead, or hand the command to the user" ;;
    cp|tee)
      lx_j=$((LI+1)); lx_last=""
      while [ "$lx_j" -lt "${#LW[@]}" ]; do
        lx_w=${LW[lx_j]}; lx_j=$((lx_j+1))
        case "$lx_w" in -*) continue ;; esac
        lx_last=$lx_w
        if [ "$LC" = tee ] && linux_is_dev "$lx_w"; then case "$lx_w" in /dev/*) defer "tee writes the device $LD_WHAT — write to an image file instead, or hand the command to the user" ;; esac; fi
      done
      if [ "$LC" = cp ] && [ -n "$lx_last" ]; then
        case "$lx_last" in /dev/*) linux_is_dev "$lx_last" && defer "cp writes the device $LD_WHAT — write to an image file instead, or hand the command to the user" ;; esac
      fi ;;
    wipefs|sgdisk|sfdisk|parted|fdisk|gdisk|cfdisk|mkfs|mkfs.*|mke2fs|mkswap|blkdiscard|cryptsetup)
      lx_w=false   # true = a read-only form (listing, printing)
      case "$LC" in
        fdisk|gdisk) for lx_j in "${LW[@]:$((LI+1))}"; do case "$lx_j" in --list|--list=*) lx_w=true ;; --*) ;; -*) linux_sflag l "$lx_j" && lx_w=true ;; esac; done ;;
        sfdisk) case "${LW[LI+1]:-}" in -l|--list|-d|--dump|-J|--json|-V|--verify|-F|--list-free|-s|--show-size|-g|--show-geometry) lx_w=true ;; esac ;;
        sgdisk)
          lx_w=true
          for lx_j in "${LW[@]:$((LI+1))}"; do case "$lx_j" in -p|--print|-v|--verify|-O|--print-mbr|-L|--list-types|-i|-i[0-9]*|--info=*|[0-9]*) ;; -*) lx_w=false ;; esac; done ;;
        parted)
          lx_n=""
          for lx_j in "${LW[@]:$((LI+1))}"; do
            case "$lx_j" in -l|--list) lx_w=true ;; -*) ;; *) linux_is_dev "$lx_j" || lx_n="$lx_n $lx_j" ;; esac
          done
          case "$lx_n" in ' print'|' p') lx_w=true ;; esac ;;
        wipefs)
          lx_w=true
          for lx_j in "${LW[@]:$((LI+1))}"; do
            case "$lx_j" in --all|--offset|--offset=*) lx_w=false ;; --*) ;; -*) linux_sflag ao "$lx_j" && lx_w=false ;; esac
          done
          for lx_j in "${LW[@]:$((LI+1))}"; do case "$lx_j" in -n|--no-act) lx_w=true ;; esac; done ;;
        cryptsetup)
          lx_w=true
          for lx_j in "${LW[@]:$((LI+1))}"; do case "$lx_j" in luksFormat|erase|luksErase) lx_w=false ;; esac; done ;;
      esac
      $lx_w && continue
      linux_dev_operands $((LI+1)) \
        && defer "$LC on $LD_WHAT destroys a block device — run it on an image file (mkfs.ext4 disk.img) instead, or hand the command to the user" ;;
    pvcreate|pvremove|pvmove|vgcreate|vgremove|vgreduce|lvcreate|lvremove|lvreduce|lvresize)
      defer "$LC changes LVM storage — read with lvs / vgs / pvs instead, and hand the change to the user" ;;
    zpool|zfs)
      linux_pos '-o|-O|-R|-m|-t' "${LW[@]:$((LI+1))}"
      case "$LC:${LP[0]:-}" in
        zpool:create|zpool:destroy|zpool:labelclear|zfs:destroy|zfs:rollback)
          defer "$LC ${LP[0]} changes ZFS storage — read with 'zpool status' / 'zfs list' instead, and hand the change to the user" ;;
      esac ;;
    mdadm)
      for lx_j in "${LW[@]:$((LI+1))}"; do
        case "$lx_j" in --create|--create=*|-C|--zero-superblock)
          defer "mdadm $lx_j changes RAID storage — read with 'mdadm --detail' or 'cat /proc/mdstat' instead, and hand the change to the user"; break ;;
        esac
      done ;;
    # ---- local firewall / network: ask --------------------------------------------------------
    nft)
      lx_w=""
      for lx_j in "${LW[@]:$((LI+1))}"; do
        case "$lx_j" in --file|--file=*|--interactive) lx_w=$lx_j ;; --*) ;; -*) linux_sflag fi "$lx_j" && lx_w=$lx_j ;; esac
      done
      linux_pos '-I|--includepath|-D|--define|-T|-f|--file' "${LW[@]:$((LI+1))}"
      case "${LP[0]:-}" in flush|add|delete|insert|replace|create|destroy|reset|rename) lx_w=${LP[0]} ;; esac
      [ -n "$lx_w" ] && defer "nft $lx_w changes the host firewall — read with 'nft list ruleset' instead, and hand the change to the user (it can cut off the session)" ;;
    ufw)
      linux_pos '' "${LW[@]:$((LI+1))}"
      case "${LP[0]:-}" in
        enable|disable|allow|deny|reject|limit|delete|reset|insert|prepend|route|default|reload|logging)
          defer "ufw ${LP[0]} changes the host firewall — read with 'ufw status' instead, and hand the change to the user (it can cut off the session)" ;;
      esac ;;
    netplan)
      linux_pos '--root-dir' "${LW[@]:$((LI+1))}"
      case "${LP[0]:-}" in
        apply|try|generate|set) defer "netplan ${LP[0]} changes the host network — read with 'netplan get' / 'netplan status' instead, and hand the change to the user (it can cut off the session)" ;;
      esac ;;
    nmcli)
      linux_nmcli_ro "${LW[@]:$((LI+1))}" \
        || defer "$LR_WHY — read with 'nmcli device status' / 'nmcli connection show' instead, and hand the change to the user (it can cut off the session)" ;;
    ip)
      linux_ip_ro "${LW[@]:$((LI+1))}" \
        || defer "$LR_WHY — read with 'ip -br a' / 'ip route' instead, and hand the change to the user (it can cut off the session)" ;;
    iptables|ip6tables|iptables-legacy|iptables-nft|ip6tables-legacy|ip6tables-nft)
      linux_ipt_action "${LW[@]:$((LI+1))}" \
        && defer "$LC with -A/-I/-D/-F/-P/-X/-N/-R/-Z/-E changes the host firewall — read with '$LC -S' or '$LC -L -n' instead, and hand the change to the user (it can cut off the session)" ;;
    iptables-restore|ip6tables-restore|iptables-legacy-restore|iptables-nft-restore)
      defer "$LC replaces the host firewall — read with 'iptables-save' instead, and hand the change to the user (it can cut off the session)" ;;
  esac
done
return 0
