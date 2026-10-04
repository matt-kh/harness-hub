# shellcheck shell=bash

# Section 75 (bundle ticket-workflow): key-free branches and subjects, sub worktree paths, squash delivery.
# rule: git switch -c|checkout -b|branch|worktree add -b NAME with a ticket key or #N in NAME -> ask : keys live on the MR/PR, not the branch; use a <short-name> branch instead (repos opt in with WORK_TICKET_KEY_IN_BRANCH=1)
# rule: git commit whose first -m/--message starts with a ticket key -> ask : mention the key in the body or MR instead (WORK_TICKET_KEY_IN_BRANCH=1 passes)
# rule: git worktree add PATH -b <-sub- branch> with basename(PATH) != <repo>_<branch> -> ask : subagent worktrees follow ../<repo>_<branch>; use that path instead
# rule: git merge [--no-ff|--ff|--ff-only] <-sub- branch> without --squash -> ask : single delivery squash-merges parts; use git merge --squash instead
# ---- Ticket workflow (work-ticket conventions) ---------------------------------------
# All decisions are deferred asks, so a later deny in the same command still wins. $VAR names,
# messages and paths are not resolvable and fall through. WORK_TICKET_KEY_IN_BRANCH=1 switches
# off the two key rules (repos whose own convention puts keys in branches and subjects).
GUARD_GIT="${GUARD_GIT:-git}"
TW_GIT_RE='\bgit((\s+-[Cc]\s+\S+)|(\s+--[A-Za-z-]+(=\S+)?))*\s+(switch|checkout|branch|worktree|commit|merge)\b'

# tw_words CLAUSE -> one word per line; quotes removed. Falls back to deleting every quote and
# backslash when the clause has unbalanced quotes (a clause cut out of `sh -c "…"`).
tw_words() {
  local w
  if w=$(shell_words "$1" 2>/dev/null); then printf '%s\n' "$w"; return 0; fi
  set -f
  # shellcheck disable=SC2046  # word splitting is the point; globbing is off
  for w in $(printf '%s' "$1" | tr -d "\"'\\\\"); do printf '%s\n' "$w"; done
  set +f
}
# tw_has_key NAME -> rc 0 when a branch name carries a ticket key (KEY_RE) or an issue ref (#N)
tw_has_key() { printf '%s' "$1" | grep -qE "$KEY_RE|#[0-9]+"; }
tw_branch_check() {  # VERB NAME
  case "$2" in ''|*'$'*) return 0 ;; esac
  [ -z "$KEY_IN_BRANCH" ] || return 0
  tw_has_key "$2" && defer "git $1 creates branch '$2' carrying a ticket key — keys live on the MR/PR, not the branch; use a <short-name> branch instead (repos opt in with WORK_TICKET_KEY_IN_BRANCH=1)"
  return 0
}

if printf '%s' "$flat" | grep -qE "$TW_GIT_RE"; then
  while IFS= read -r clause; do
    [ -n "$clause" ] || continue
    tw=(); while IFS= read -r _w; do tw+=("$_w"); done <<EOF
$(tw_words "$clause")
EOF
    # skip `git` and its global options up to the verb; remember -C DIR
    gdir="$cwd"; i=1; verb=""
    while [ "$i" -lt "${#tw[@]}" ]; do
      tok=${tw[i]}; i=$((i+1))
      case "$tok" in
        -C) gdir=${tw[i]:-}; i=$((i+1))
            case "$gdir" in /*|'$'*|'~'*) ;; *) gdir="${cwd:-.}/$gdir" ;; esac ;;
        -c) i=$((i+1)) ;;
        -*) ;;
        *) verb=$tok; break ;;
      esac
    done
    args=("${tw[@]:i}")
    case "$verb" in
      switch|checkout)
        j=0
        while [ "$j" -lt "${#args[@]}" ]; do
          tok=${args[j]}; j=$((j+1))
          case "$verb:$tok" in
            switch:-c|switch:-C|switch:--create|switch:--force-create|checkout:-b|checkout:-B)
              tw_branch_check "$verb" "${args[j]:-}"; j=$((j+1)) ;;
            switch:--create=*|switch:--force-create=*) tw_branch_check "$verb" "${tok#*=}" ;;
          esac
        done ;;
      branch)
        # create (first positional) or rename/copy (last positional); list/delete modes skip
        mode=create; pos=(); j=0
        while [ "$j" -lt "${#args[@]}" ]; do
          tok=${args[j]}; j=$((j+1))
          case "$tok" in
            -d|-D|--delete|-l|--list|-a|--all|-r|--remotes|-v|-vv|--verbose|--show-current|--unset-upstream|--edit-description|--contains|--no-contains|--merged|--no-merged|--points-at|--format*|--sort*|--column*)
              mode=skip ;;
            -m|-M|--move|-c|-C|--copy) [ "$mode" = skip ] || mode=rename ;;
            -u|--set-upstream-to) j=$((j+1)); mode=skip ;;
            -*) ;;
            *) pos+=("$tok") ;;
          esac
        done
        if [ "${#pos[@]}" -gt 0 ]; then
          case "$mode" in
            create) tw_branch_check branch "${pos[0]}" ;;
            rename) tw_branch_check branch "${pos[${#pos[@]}-1]}" ;;
          esac
        fi ;;
      worktree)
        [ "${args[0]:-}" = add ] || continue
        wpath=""; wbr=""; j=1
        while [ "$j" -lt "${#args[@]}" ]; do
          tok=${args[j]}; j=$((j+1))
          case "$tok" in
            -b|-B) wbr=${args[j]:-}; j=$((j+1)) ;;
            --reason) j=$((j+1)) ;;
            -*) ;;
            *) [ -n "$wpath" ] || wpath=$tok ;;
          esac
        done
        tw_branch_check "worktree add" "$wbr"
        case "$wbr" in *-sub-*) ;; *) continue ;; esac
        case "$wbr$wpath" in *'$'*) continue ;; esac
        [ -n "$wpath" ] || continue
        top=$(hn_timeout 5 "$GUARD_GIT" -C "$gdir" rev-parse --show-toplevel 2>/dev/null) || continue
        [ -n "$top" ] || continue
        repo=${top%/}; repo=${repo##*/}
        wbase=${wpath%/}; wbase=${wbase##*/}
        [ "$wbase" = "${repo}_${wbr}" ] \
          || defer "git worktree add '$wpath' for sub branch '$wbr' — subagent worktrees follow ../<repo>_<branch>; use ../${repo}_${wbr} instead"
        ;;
      commit)
        [ -z "$KEY_IN_BRANCH" ] || continue
        msg=""; found=false; j=0
        while [ "$j" -lt "${#args[@]}" ]; do
          tok=${args[j]}; j=$((j+1))
          case "$tok" in
            -F|--file|-C|-c|--reuse-message|--reedit-message|--fixup|--squash|--author|--date|-t|--template|--cleanup|--trailer) j=$((j+1)) ;;
            --message=*) msg=${tok#*=}; found=true ;;
            --message) msg=${args[j]:-}; found=true ;;
            --*) ;;
            -*m) msg=${args[j]:-}; found=true ;;           # -m, -am, -sm …
            -*m*) msg=${tok#*m}; found=true ;;             # -mMSG, -amMSG
          esac
          $found && break
        done
        $found || continue
        case "$msg" in '$'*) continue ;; esac
        key=$(printf '%s' "$msg" | grep -oE "^$KEY_RE" | head -1)
        [ -z "$key" ] || defer "git commit subject starts with ticket key '$key' — mention the key in the body or MR instead (WORK_TICKET_KEY_IN_BRANCH=1 passes)"
        ;;
      merge)
        squash=false; subs=""; j=0
        while [ "$j" -lt "${#args[@]}" ]; do
          tok=${args[j]}; j=$((j+1))
          case "$tok" in
            --squash) squash=true ;;
            --abort|--continue|--quit) squash=true ;;
            -m|-F|--file|-s|--strategy|-X|--strategy-option|--into-name) j=$((j+1)) ;;
            -*) ;;
            *'$'*) ;;
            *-sub-*) subs="${subs:+$subs }$tok" ;;
          esac
        done
        if ! $squash && [ -n "$subs" ]; then
          defer "git merge of sub branch '$subs' without --squash — single delivery squash-merges parts; use git merge --squash $subs instead"
        fi ;;
    esac
  done <<EOF
$(printf '%s' "$flat" | grep -oE "${TW_GIT_RE}[^;&|]*")
EOF
fi
