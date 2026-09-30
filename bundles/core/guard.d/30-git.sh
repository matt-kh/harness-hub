# shellcheck shell=bash

# Section 30 (bundle core): git.
# rule: git push <dst matching WORK_TICKET_BASE_BRANCH_RE> (explicit refspec or current branch) -> deny : MR/PR-based workflow
# rule: git push to a default branch in a repo matching WORK_TICKET_ALLOW_DEFAULT_PUSH_RE -> ask : personal repos
# rule: git push --force|-f|+refspec -> ask : force-push
# rule: git reset --hard | git clean -f/-d/-x -> ask : destructive working-tree command
# rule: git push of a -sub- branch from (or via cd into) a sub worktree -> ask : only the main thread pushes stacked branches
# rule: git push --all|--mirror -> ask : would publish every local branch
# ---- Git ------------------------------------------------------------------------
# Default-branch push: MR-based workflow → deny (ask where WORK_TICKET_ALLOW_DEFAULT_PUSH_RE
# matches the repo top level). Destination = each refspec's dst (after ':', refs/heads/
# stripped); HEAD or no refspec → the current branch of cwd (or of `git -C DIR`). $VAR
# refspecs are not resolvable and fall through (work-ticket pushes "$BR" feature branches).
GUARD_GIT="${GUARD_GIT:-git}"
push_default_decide() {  # $1 = branch, $2 = repo dir
  local top; top=$(hn_timeout 5 "$GUARD_GIT" -C "$2" rev-parse --show-toplevel 2>/dev/null) || top="$2"
  if [ -n "$ALLOW_DEFAULT_PUSH_RE" ] && printf '%s' "$top" | grep -qE "$ALLOW_DEFAULT_PUSH_RE"; then
    ask "git push to default branch '$1' in $top (allowed here by WORK_TICKET_ALLOW_DEFAULT_PUSH_RE)"
  fi
  deny "git push to default branch '$1' — MR-based workflow — push a feature branch and open an MR"
}
if printf '%s' "$flat" | grep -qE '\bgit(\s+-C\s+\S+)?\s+push\b'; then
  while IFS= read -r clause; do
    [ -n "$clause" ] || continue
    gdir="$cwd"
    if printf '%s' "$clause" | grep -qE '^git\s+-C\s'; then
      gdir=$(printf '%s' "$clause" | awk '{print $3}' | tr -d "\"'")
      case "$gdir" in /*|'~'*|'$'*) ;; *) gdir="${cwd:-.}/$gdir" ;; esac
      gdir="${gdir/#\~/$HOME}"; gdir="${gdir/#\$HOME/$HOME}"
    fi
    printf '%s' "$clause" | grep -qE '\s--(all|mirror|tags)\b' && continue   # handled below / tags only
    pos=(); skip=0
    for tok in $(printf '%s' "$clause" | sed -E 's/^git([[:space:]]+-C[[:space:]]+[^[:space:]]+)?[[:space:]]+push//'); do
      if [ $skip -eq 1 ]; then skip=0; continue; fi
      case "$tok" in
        -o|--push-option|--repo|--receive-pack|--exec) skip=1 ;;
        -*) ;;
        *) pos+=("$(printf '%s' "$tok" | tr -d "\"'")") ;;
      esac
    done
    need_cur=false
    if [ "${#pos[@]}" -le 1 ]; then
      need_cur=true
    else
      for rs in "${pos[@]:1}"; do
        dst="${rs#+}"; dst="${dst##*:}"; dst="${dst#refs/heads/}"
        case "$dst" in *'$'*) continue ;; HEAD|'') need_cur=true; continue ;; esac
        printf '%s' "$dst" | grep -qE "$BASE_BRANCH_RE" && push_default_decide "$dst" "$gdir"
      done
    fi
    if $need_cur && [ -n "$gdir" ]; then
      cur=$(hn_timeout 5 "$GUARD_GIT" -C "$gdir" rev-parse --abbrev-ref HEAD 2>/dev/null) || cur=""
      [ -n "$cur" ] && printf '%s' "$cur" | grep -qE "$BASE_BRANCH_RE" && push_default_decide "$cur" "$gdir"
    fi
  done <<EOF
$(printf '%s' "$flat" | grep -oE '\bgit(\s+-C\s+\S+)?\s+push\b[^;&|]*')
EOF
fi
printf '%s' "$flat" | grep -qE '\bgit\s+push\b.*(\s--force(-with-lease)?|\s-f\b|\s\+[A-Za-z0-9_/-]+)' && ask "git force-push"
printf '%s' "$flat" | grep -qE '\bgit\s+(reset\s+--hard|clean\s+-[a-zA-Z]*[fdx])' && ask "destructive git working-tree command"
# work-ticket stacked delivery: sub branches are pushed by the MAIN thread from the main checkout.
# Ask when the push comes from inside a sub worktree (subagents live there) or cd's into one.
if printf '%s' "$flat" | grep -qE '\bgit\s+push\b.*-sub-'; then
  $in_sub_worktree && ask "git push of a -sub- branch from inside a sub worktree ($cwd_base) — subagents never push; the main thread pushes from the main checkout"
  printf '%s' "$flat" | grep -qE '\bcd\s+[^;&|]*_[^ ;&|]*-sub-[^;&|]*(&&|;)[^;&|]*\bgit\s+push\b' && ask "git push of a -sub- branch via cd into a sub worktree"
fi
printf '%s' "$flat" | grep -qE '\bgit\s+push\b.*\s--(all|mirror)\b' && ask "git push --all/--mirror would publish every local branch (incl. -sub- branches)"
