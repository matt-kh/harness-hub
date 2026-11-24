# Reference: hook policy

Every guard rule — bundle, command pattern, decision (`allow`, `ask`, `deny`) and reason — plus
the **repo overrides** a repository may set in `.harness.toml` `[overrides]` or a provider `env`
(which wins per key). Both tables are generated, from the `# rule:` and `# repo-override:`
comments in `bundles/*/guard.d/*.sh`; do not edit inside the regions.

Decisions are evaluated section by section in numeric order (`10` k8s … `32` obs, `38` supply chain, `40`/`41` closing keywords … `60` github, `65` stack,
`70` jira … `90+` private); a deny anywhere wins over an earlier ask, and an allow never overrides a pending ask. On providers without
an ask prompt, `ask` is mapped by `[providers.<name>].ask_as`. Model and rationale:
[governance](../governance.md). The `yields` column says whether a repository's
`.harness.toml` can lift the rule ([repository-level harnesses](../repo-level.md)): `never`
marks the developer's own credentials and the ask on writing `.harness.toml`.

<!-- generated:begin source=bundles/*/guard.d -->
| section | bundle | pattern | decision | reason | yields |
|---|---|---|---|---|---|
| 15-lessons.sh | lessons | ``harness lessons confirm\|retire\|propose (also …/bin/harness, python3 -m harness, global flags before `lessons`)`` | ask | a human decision on a lesson; run it yourself, or ask the user (/retro never runs it) | owns base |
| 20-credentials.sh | core | `<reader> ~/.kube/* \| $KUBECONFIG` | deny | kubeconfig holds cluster credentials; use 'kubectl config get-contexts' or 'k8s contexts' instead | never |
| 20-credentials.sh | core | `<reader> tool credential files (~/.config/{jira,glab-cli,gdoc,gh}, agent credential json)` | deny | use the tool's own auth status command | never |
| 20-credentials.sh | core | `<reader> .env / .env.*` | deny | secrets; ask the user for the variable names | never |
| 20-credentials.sh | core | `<reader> ~/.aws/* \| ~/.ssh/* (except *.pub)` | deny | private keys / cloud credentials; use 'ssh-add -l', the *.pub file or 'aws sts get-caller-identity' instead | never |
| 20-credentials.sh | core | `<reader> path matching HARNESS_CRED_EXTRA_RE` | deny | org-specific credential paths; run the tool's own auth status command instead | never |
| 20-credentials.sh | core | `env \| printenv (no command)` | deny | dumps the whole environment; print named non-secret variables instead | never |
| 20-credentials.sh | core | `printenv NAME \| echo $NAME (NAME looks secret)` | deny | prints a secret; test presence with [ -n "${VAR:+x}" ] instead | never |
| 25-k8s-rules.sh | k8s | `kubectl config use-context\|set-*\|delete-*\|rename-context` | deny | kubeconfig is human-managed; pass --context on every command instead (see the k8s rule) | owns kubernetes |
| 25-k8s-rules.sh | k8s | `aws eks update-kubeconfig \| eksctl utils write-kubeconfig` | deny | kubeconfig is human-managed; pass --context on every command instead (see the k8s rule) | owns kubernetes |
| 25-k8s-rules.sh | k8s | `kubectl get secret(s) -o yaml\|json\|jsonpath\|template \| get --raw .../secrets` | deny | Secret values are never printed; use 'k8s secret-keys NS NAME' or pipe through 'k8s redact' instead | owns kubernetes |
| 25-k8s-rules.sh | k8s | `kubectl create token` | ask | mints a ServiceAccount credential; ask the user, or use read-only k8s commands instead | owns kubernetes |
| 25-k8s-rules.sh | k8s | `kubectl exec\|attach\|cp\|debug\|port-forward\|proxy` | ask | exec-class; use 'k8s pod' or 'kubectl logs' for read-only triage instead | owns kubernetes |
| 25-k8s-rules.sh | k8s | `kubectl apply\|delete\|edit\|patch\|scale\|rollout restart\|... (no --dry-run=client\|server)` | ask | cluster mutation; use --dry-run=server, or hand the command to the user instead | owns kubernetes |
| 25-k8s-rules.sh | k8s | `helm get values\|all\|manifest` | ask | may print credentials; pipe every clause through 'k8s redact' instead (then allowed) | owns kubernetes |
| 25-k8s-rules.sh | k8s | `helm install\|upgrade\|uninstall\|rollback\|test\|push\|registry login` | ask | release mutation; use 'helm template' read-only, or hand the command to the user instead | owns kubernetes |
| 25-k8s-rules.sh | k8s | `argocd app(set) sync\|delete\|set\|... \| flux reconcile\|... \| eksctl create\|...` | ask | GitOps / cluster mutation; change the GitOps repo instead, or hand the command to the user | owns kubernetes |
| 25-k8s-rules.sh | k8s | `pulumi up\|destroy\|refresh\|import \| terraform apply\|destroy\|import` | ask | IaC state mutation; run a preview / plan instead, or hand the command to the user | owns kubernetes |
| 25-k8s-rules.sh | k8s | `kubectl config view --raw` | deny | prints credentials; use plain 'kubectl config view' (redacted) instead | never |
| 30-git.sh | core | `git push <dst matching WORK_TICKET_BASE_BRANCH_RE> (explicit refspec or current branch)` | deny | MR/PR-based workflow; push a branch and open an MR/PR instead | owns scm |
| 30-git.sh | core | `git push to a default branch in a repo matching WORK_TICKET_ALLOW_DEFAULT_PUSH_RE` | ask | personal repos; ask the user to confirm, or push a branch instead | owns scm |
| 30-git.sh | core | `git [-C DIR] push --force-with-lease[=…] <remote> <refs> as the whole command, every ref (src and dst) a -sub-NN- branch and none matching WORK_TICKET_BASE_BRANCH_RE` | allow | agent-owned sub branches, lease-protected (stk sync, work-ticket §6c); every other force-push asks | owns scm |
| 30-git.sh | core | `git push --force\|-f\|+refspec, or a lease push of a non-sub ref, a $VAR ref, no ref, or inside a compound command` | ask | force-push rewrites shared history; ask the user first, or push a new branch instead | owns scm |
| 30-git.sh | core | `git reset --hard \| git clean -f/-d/-x` | ask | destructive working-tree command; use git stash, or ask the user first | owns scm |
| 30-git.sh | core | `git push of a -sub- branch from (or via cd into) a sub worktree` | ask | only the main thread pushes stacked branches; run the push from the main checkout instead | owns scm |
| 30-git.sh | core | `git push --all\|--mirror` | ask | would publish every local branch; push the named branch instead | owns scm |
| 30-git.sh | core | `shell write to .harness.toml (> >> tee cp mv install ln dd of= sed -i perl -i, harness repo init --write)` | ask | the repository declaration lifts user-level rules; ask the user to review and commit it instead | never |
| 32-obs.sh | obs | `<reader> ~/.config/obs/*` | deny | API key files; run 'obs backends' to see auth status instead | never |
| 32-obs.sh | obs | `[/path/]curl\|wget\|http\|xh ... -H 'Authorization\|SIGNOZ-API-KEY\|X-API-Key: <literal>' \| ?api_key=<literal>` | deny | API key on the command line; use the obs CLI instead (it reads the key file) | owns operations |
| 32-obs.sh | obs | `[/path/]curl\|wget\|http\|xh <host matching OBS_HOSTS_RE>` | ask | raw backend access; use the obs CLI (bounded, redacted, read-only) instead | owns operations |
| 32-obs.sh | obs | `amtool silence add\|expire\|import \| amtool alert add` | ask | changes alert state; hand the command to the user, or change the alert rule in the repo instead | owns operations |
| 32-obs.sh | obs | `logcli query --tail\|-f` | ask | never returns; pass --since and --limit instead | owns operations |
| 32-obs.sh | obs | `grafana-cli admin\|plugins install\|remove` | ask | Grafana admin mutation; hand the command to the user, or change the chart values instead | owns operations |
| 35-shell-hygiene.sh | core | `curl\|wget\|fetch\|http\|xh … \| [wrapper] sh\|bash\|zsh\|ksh\|dash\|ash\|mksh\|fish\|python[3]\|perl\|node\|ruby reading its program from stdin (no -c/-e/-m/-n, script operand or stdin redirect; sh -s, bash -, python3 -, /dev/stdin count; sudo -s\|-i, su, source\|. /dev/stdin too; through { } ( ) if/for/while bodies, a continued line and tee >(sh)) \| sh\|bash\|source\|. <(curl …) \| sh\|bash -c "$(curl …)" \| python\|perl\|ruby\|node -c\|-e "$(curl …)" \| eval "$(curl …)" \| an interpreter's <<< or heredoc expanding $(curl …)` | ask | runs downloaded code unreviewed; download to a file, check its sha256, read it, then run it instead | owns base |
| 38-supply-chain.sh | supply-chain | `<reader> ~/.sigstore/**/*.key (any .sigstore/**/*.key, so cd ~ is no bypass) as a file operand (a grep\|rg pattern is not)` | deny | the developer's signing key; pass --key and let cosign read it, or leave keyless signing to the human release step, instead | never |
| 38-supply-chain.sh | supply-chain | `pip\|uv --trusted-host (or a unique prefix such as --trusted) \| uv --allow-insecure-host \| pip\|uv -i\|--index[-url]\|--extra-index[-url]\|--default-index http:// \| pip config set <section>.trusted-host \| pip config set <section>.[extra-]index-url http:// \| PIP_TRUSTED_HOST= \| PIP_[EXTRA_]INDEX_URL=http:// \| UV_INSECURE_HOST= \| UV_[DEFAULT_\|EXTRA_]INDEX[_URL]=http://` | deny | disables TLS verification; use the HTTPS index with PIP_CERT or REQUESTS_CA_BUNDLE (uv: SSL_CERT_FILE) pointing at your CA bundle instead, or ask the user | owns security |
| 38-supply-chain.sh | supply-chain | `npm\|pnpm\|yarn [config] set strict-ssl false \| --strict-ssl=false \| --no-strict-ssl \| NPM_CONFIG_STRICT_SSL=false \| [config] set registry http:// \| --registry (or --reg) http:// \| yarn config set enableStrictSsl false\|npmRegistryServer http://\|unsafeHttpWhitelist \| YARN_ENABLE_STRICT_SSL=false \| NODE_TLS_REJECT_UNAUTHORIZED=0` | deny | disables TLS verification; use cafile or NODE_EXTRA_CA_CERTS with the HTTPS registry instead, or ask the user | owns security |
| 38-supply-chain.sh | supply-chain | `git -c\|--config http[.<url>].sslVerify=false\|no\|off\|0\|<empty> \| git config ... http.sslVerify false \| --config-env=http.sslVerify=… \| GIT_CONFIG_KEY_<n>=http.sslVerify \| GIT_SSL_NO_VERIFY=` | deny | disables TLS verification; set http.sslCAInfo to your CA bundle instead, or ask the user | owns security |
| 38-supply-chain.sh | supply-chain | `GOINSECURE=<value> \| GOFLAGS=...-insecure \| go get -insecure \| go env -w GONOSUMDB\|GONOSUMCHECK=<value>` | deny | disables module verification; use GOPRIVATE=<prefix> and keep go.sum verification instead | owns security |
| 38-supply-chain.sh | supply-chain | `GOSUMDB=off \| go env -w GOSUMDB=off` | deny | switches the checksum database off for every module; use GOPRIVATE=<prefix> or a one-shot GONOSUMDB=<prefix> for private modules instead | owns security |
| 38-supply-chain.sh | supply-chain | `cosign verify* --insecure-ignore-tlog\|--insecure-ignore-sct\|--insecure-skip-verify\|--allow-insecure-registry\|--allow-http-registry\|--private-infrastructure[=true\|t\|1]` | deny | skips a verification check; run supply verify or cosign verify without the flag and report exit 2 as a finding instead | owns security |
| 38-supply-chain.sh | supply-chain | `<reader> cosign.key as a file operand (a grep\|rg pattern is not)` | deny | a signing key; use keyless signing (a human release step) or pass --key and let cosign read it instead | owns security |
| 38-supply-chain.sh | supply-chain | `pip install outside a venv (no venv marker in the environment, no earlier activate clause, no runner, no venv pip as the command word; conda base is no venv) \| --target\|--prefix outside the checkout \| --user \| --break-system-packages \| uv pip install --system \| UV_SYSTEM_PYTHON=1 \| sudo pip` | ask | installs into the machine; run it inside the project (uv sync, uv pip install, .venv/bin/pip install) instead; supply_chain.allow_global_re allow-lists tools | owns security |
| 38-supply-chain.sh | supply-chain | `npm\|pnpm install\|i\|add -g\|--global\|--location=global\|-<flags with g> \| yarn global add` | ask | installs into the machine; add it to the project (npm i -D, npx) instead; supply_chain.allow_global_re allow-lists tools | owns security |
| 38-supply-chain.sh | supply-chain | `cargo install ... without both --locked and --version` | ask | an unpinned machine install; use cargo run or cargo build in the checkout, or pass --locked --version V, instead; supply_chain.allow_global_re allow-lists tools | owns security |
| 38-supply-chain.sh | supply-chain | `go install ...@latest\|@master\|@main\|@HEAD` | ask | unpinned; pin a version (m@v1.2.3) instead | owns security |
| 38-supply-chain.sh | supply-chain | `pip install git+URL without @<sha> (or @main\|master\|develop\|HEAD\|latest) \| pip install https://...whl\|.tar.gz\|.zip without --hash \| npm\|pnpm\|yarn install\|add github:O/R\|O/R\|git+URL\|git:// without #<40-hex sha> \| npm\|pnpm\|yarn install\|add https://...tgz (a fragment is no pin) \| cargo install\|add --git with --branch, or with neither --rev nor --tag` | ask | unpinned dependency; pin a commit or a released version instead; run supply pins to list every unpinned reference | owns security |
| 38-supply-chain.sh | supply-chain | `GONOSUMDB=<value>\|GONOSUMCHECK=<value> one-shot env prefix` | ask | skips go.sum verification; use GOPRIVATE=<prefix> instead | owns security |
| 38-supply-chain.sh | supply-chain | `cosign sign\|sign-blob\|attest\|attest-blob\|attach signature\|sbom\|attestation\|upload\|copy\|clean\|generate-key-pair\|import-key-pair` | ask | a human release step (registry writes, keys); hand the command to the user (supply verify and cosign verify stay available) | owns security |
| 38-supply-chain.sh | supply-chain | `curl -k\|--insecure ... -o\|-O\|--output\|--remote-name\|--output-dir FILE (not - or /dev/null) \| > FILE \| ... piped into tar\|unzip\|tee\|dd\|cpio \| wget --no-check-certificate (not to stdout)` | ask | an unverified file; use the HTTPS URL with --cacert (wget --ca-certificate) instead | owns security |
| 40-gitlab-closing.sh | gitlab | `(close\|fix\|resolve\|implement) KEY-123 in git commit \| glab [-R g/p] mr [-R g/p] create\|new\|update \| glab [-R g/p] api (also quoted or $VAR command words)` | deny | a closing keyword would change the ticket's state as a side effect; mention the key instead (KEY-123 fix parser) | owns tracker |
| 41-github-closing.sh | github | `(close\|fix\|resolve) #N \| owner/repo#N \| issue URL in git commit \| gh [-R o/r] pr [-R o/r] create\|new\|edit\|merge \| gh api (also quoted or $VAR command words, and a keyword or ref written with quotes or escapes)` | deny | a closing keyword would change the issue's state as a side effect; mention #N instead (see #N, refs #N), or use the PR-to-default-branch form below in a github-issues repository | owns tracker |
| 41-github-closing.sh | github | `(close\|fix\|resolve) #N only in the -b/-t text of a top-level literal gh [-R o/r] pr [-R o/r] create\|new -B <default branch> (head not -sub-, not a fork) or gh pr edit N of a PR targeting the default branch, in the cwd checkout's own github.com repository, every #N agent-worked, the repository's tracker github-issues (.harness.toml [repo] tracker > first matching ticket_workflow.trackers entry > github.com host), github.close_issue_on_merge true` | allow | GitHub closes the worked issue when the human merges the PR; 60-github still decides the create/edit. Set github.close_issue_on_merge = false to deny it again and mention #N instead | owns tracker |
| 41-github-closing.sh | github | `closing keyword in gh pr create\|new\|edit without a literal -B, with a base that is not the repository's default branch, a -sub- or fork head, a non-agent-worked or unreadable #N, more than 10 refs, a multi-line command, cd/pushd/popd, GH_REPO/GH_HOST, sh -c/eval/xargs/$(…)/backticks, a repeated -B/-H/-R/-t/-b/-F, an unknown flag, --, a -R other than the checkout's origin, no canonical github.com/<owner>/<repo> origin, a tracker that resolves to anything but github-issues (a declared one wins: jira declared on github.com denies; a match naming another tracker in guard.env's list or the environment's denies), a .harness.toml tracker the guard cannot read, a malformed ticket_workflow.trackers or one with an invalid match ERE` | deny | run gh pr create\|edit as its own one-line command from the ticket branch's checkout with -B <default branch> and the body in -b (or -F file); label the issue agent-worked; or mention #N instead | owns tracker |
| 50-gitlab.sh | gitlab | `glab api -X non-GET (any case, quoted, attached, $VAR) \| payload flag (-f/-F/--field/--raw-field/--form/--input)` | ask | API write; ask the user, or use the matching glab subcommand | owns scm |
| 50-gitlab.sh | gitlab | `glab api write (as above) from a subagent` | deny | a raw API write can merge or change state; hand the command back to the main thread | owns scm |
| 50-gitlab.sh | gitlab | `glab mr merge\|accept\|approve\|revoke\|unapprove\|delete, glab issue close\|reopen\|open\|delete` | ask | merging, approving, deleting and issue state are human decisions; run it only on the user's explicit request (they confirm it), or ask the user instead | owns scm |
| 50-gitlab.sh | gitlab | `glab mr merge\|accept\|approve\|revoke\|unapprove\|delete, glab issue close\|reopen\|open\|delete from a subagent` | deny | a subagent never merges, approves, deletes or changes issue state; hand the command back to the main thread | owns scm |
| 50-gitlab.sh | gitlab | `glab quick action (/merge /approve /close /reopen /ready /draft …) in a note, description or title` | ask | it carries out a human decision; drop it from the text, or run the matching glab command on the user's explicit request | owns scm |
| 50-gitlab.sh | gitlab | `glab quick action, or note/description text the guard cannot read, from a subagent` | deny | a subagent never merges or changes state; pass the text inline and hand state changes back to the main thread | owns scm |
| 50-gitlab.sh | gitlab | `glab with quoted/escaped command words or a $VAR/$(…) subcommand` | ask | the subcommand cannot be checked; write it literally and unquoted instead (a subagent is denied) | owns scm |
| 50-gitlab.sh | gitlab | `glab issue create, release/repo/label mutations` | ask | team-visible; ask the user instead | owns scm |
| 50-gitlab.sh | gitlab | `glab label create -n agent-*` | allow | governance label; other labels ask | owns scm |
| 50-gitlab.sh | gitlab | `glab mr create\|new` | allow | creates are ungated (a -sub- source without target / with a base target -> deny) | owns scm |
| 50-gitlab.sh | gitlab | `glab mr create -f\|--fill` | ask | generated text may carry a closing keyword or a key-less title; pass --title and --description-file instead | owns scm |
| 50-gitlab.sh | gitlab | `glab mr create --related-issue` | ask | links (and may close) a GitLab issue; mention the key in the description instead | owns scm |
| 50-gitlab.sh | gitlab | `glab mr create -t TITLE not matching HARNESS_GITLAB_MR_TITLE_RE` | ask | MR titles start with the ticket key; use a title like 'PROJ-123 fix parser' instead, or set gitlab.mr_title_re (empty disables) | owns scm |
| 50-gitlab.sh | gitlab | `glab mr create -t with $VAR or backticks` | ask | the title cannot be checked; use a literal title instead | owns scm |
| 50-gitlab.sh | gitlab | `glab mr update\|note\|comment\|close\|reopen\|open\|rebase REF on an agent-labelled MR` | allow | human MRs ask (label it first: glab mr update REF --label agent-worked); -sub- retarget to base -> deny, retarget to the ticket branch instead; no/$VAR ref -> ask, pass a literal number | owns scm |
| 50-gitlab.sh | gitlab | `glab mr close\|reopen\|open, glab mr update --ready\|--draft\|--wip\|-r on a human MR` | ask | MR state is a human decision; run it only on the user's explicit request (they confirm it), or ask the user instead | owns scm |
| 50-gitlab.sh | gitlab | `glab mr close\|reopen\|open, glab mr update --ready\|--draft\|--wip\|-r from a subagent` | deny | a subagent never changes MR state; hand the command back to the main thread | owns scm |
| 60-github.sh | github | `gh api -X non-GET \| --input \| fields without a method \| graphql mutation` | ask | API write; ask the user, or use the matching gh subcommand | owns scm |
| 60-github.sh | github | `gh api write (as above) from a subagent` | deny | a raw API write can merge or change state; hand the command back to the main thread | owns scm |
| 60-github.sh | github | `gh pr merge\|review, gh issue delete\|transfer` | ask | merging, reviewing and deleting/transferring issues are human decisions; run it only on the user's explicit request (they confirm it), or ask the user instead | owns scm |
| 60-github.sh | github | `gh pr merge\|review, gh issue delete\|transfer from a subagent` | deny | a subagent never merges, reviews or deletes; hand the command back to the main thread | owns scm |
| 60-github.sh | github | `gh with quoted/escaped command words or a $VAR/$(…) subcommand` | ask | the subcommand cannot be checked; write it literally and unquoted instead (a subagent is denied) | owns scm |
| 60-github.sh | github | `gh release/repo/workflow/secret/auth/gist/... mutations` | ask | team-visible; ask the user (releases are human-only) | owns scm |
| 60-github.sh | github | `gh label create agent-*` | allow | governance label; other labels ask | owns scm |
| 60-github.sh | github | `gh pr create` | allow | creates are ungated (same -sub- stacked rules as glab; the gh pr new alias too) | owns scm |
| 60-github.sh | github | `gh pr create -f\|--fill\|--fill-first\|--fill-verbose` | ask | generated text may contain a closing keyword; pass -t and -F body-file instead | owns scm |
| 60-github.sh | github | `gh pr create -t TITLE matching HARNESS_GITHUB_PR_TITLE_FORBID_RE` | ask | issue refs belong in the PR body (mention #N there), not the title; set github.pr_title_forbid_re to change the convention (empty disables) | owns scm |
| 60-github.sh | github | `gh pr create -t with $VAR or backticks` | ask | the title cannot be checked; use a literal title instead | owns scm |
| 60-github.sh | github | `gh issue create\|new without -l agent-drafted\|agent-created` | deny | provenance label required; use -l agent-drafted (or agent-created) instead | owns scm |
| 60-github.sh | github | `gh pr edit\|comment\|close\|reopen\|ready\|update-branch, gh issue edit\|comment\|close\|reopen on an agent-labelled ref` | allow | human refs ask (label it first, or ask the user); fork PRs ask | owns scm |
| 60-github.sh | github | `gh pr close\|reopen\|ready, gh issue close\|reopen on a human ref` | ask | PR/issue state is a human decision; run it only on the user's explicit request (they confirm it), or ask the user instead | owns scm |
| 60-github.sh | github | `gh pr close\|reopen\|ready, gh issue close\|reopen from a subagent` | deny | a subagent never changes PR/issue state; hand the command back to the main thread | owns scm |
| 60-github.sh | github | `gh stack merge [N] [-y\|--yes] [--squash\|--merge\|--rebase\|--merge-method M] as the only command on the line (optionally after GH_STACK_NO_UPDATE_NOTIFIER=1), main thread, whose range (stack N whole, else the stack holding PR N up to N, else the current branch's stack whole; read via the stacks REST API) has a non-default base and only open non-fork agent-labelled <base>-sub-* PRs` | allow | the user asked for the merge in the main thread and every part is agent-owned; honours WORK_TICKET_LABELED_DECISION | owns scm |
| 60-github.sh | github | `gh stack merge otherwise (a human, fork or non -sub- PR, a default-branch base, a failed or empty lookup, more than 10 open PRs, an unknown argument, a compound or wrapped line, quotes, gs / gh-stack / gh extension exec / -R spellings)` | ask | merging a stack is a human decision; run it only on the user's explicit request (they confirm it), type gh stack merge [N] as a plain one-line command for agent-labelled -sub- parts, or ask the user to merge the parts bottom-up | owns scm |
| 60-github.sh | github | `gh stack merge from a subagent` | deny | a subagent never merges; hand the command back to the main thread | owns scm |
| 60-github.sh | github | `gh stack view\|help\|feedback\|completion, navigation (up\|down\|top\|bottom\|trunk\|switch\|checkout)` | pass | reads and local navigation; nothing is pushed or linked | owns scm |
| 60-github.sh | github | `gh stack link --base TICKET-BRANCH with literal numbers of agent-labelled -sub- PRs of that ticket branch` | allow | links existing PRs only (no push, no PR create); honours WORK_TICKET_LABELED_DECISION | owns scm |
| 60-github.sh | github | `gh stack link without --base, with --base matching WORK_TICKET_BASE_BRANCH_RE (also origin/…, refs/heads/…) or a -sub- branch` | deny | the stack would sit on the default branch or a part; pass --base <ticket branch> | owns scm |
| 60-github.sh | github | `gh stack link with a branch-name argument` | deny | it would push the branch and create an unlabelled PR; create the PR with gh pr create -l agent-worked, then use its number instead | owns scm |
| 60-github.sh | github | `gh stack link with a PR that is not a -sub- PR of --base (the main PR, another ticket's part)` | deny | the main PR stays outside the stack; pass only the ticket's -sub- PR numbers instead | owns scm |
| 60-github.sh | github | `gh stack link with an unlabelled or fork PR, a URL, a $VAR, --remote, GH_REPO=/GH_HOST=, a gh-level -R, a preceding cd/pushd, an unknown flag or a failed lookup` | ask | the PRs cannot be label-checked; label them (gh pr edit N --add-label agent-worked) and pass literal PR numbers from the repository's own checkout | owns scm |
| 60-github.sh | github | `gh stack VERB --open` | ask | marks PRs ready for review, a human decision; run gh pr ready N on the user's explicit request instead | owns scm |
| 60-github.sh | github | `gh stack VERB --open from a subagent` | deny | a subagent never changes PR state; hand the command back to the main thread | owns scm |
| 60-github.sh | github | `gh stack push\|submit\|sync\|rebase\|modify\|unstack\|delete\|init\|add with the default branch involved (cwd branch, an earlier git checkout\|switch to it or gh stack trunk\|bottom on the line, --base, a branch argument, init without --base, the trunk or a layer of gh stack view --json)` | deny | stacks never sit on the default branch; run it on the ticket branch's stack, or use stk sync --stack BR | owns scm |
| 60-github.sh | github | `gh stack push\|submit\|sync\|rebase\|modify\|unstack\|delete\|init\|add otherwise` | ask | use stk sync --stack BR (retarget, rebase, lease push), git push --force-with-lease of the -sub- branches, or gh stack link --base BR N… by PR numbers instead | owns scm |
| 60-github.sh | github | `gh stack alias, an unknown gh stack verb, a flag before the verb, a $VAR verb, gh extension exec of another extension` | ask | the guard cannot see what runs; type gh stack VERB with the verb first (or the extension's own gh command) instead | owns scm |
| 60-github.sh | github | `gh stack alias, an unknown verb, a flag before the verb, gh extension exec of another extension, from a subagent` | deny | what runs cannot be checked and may merge; hand the command back to the main thread | owns scm |
| 60-github.sh | github | `gh auth token \| gh auth status --show-token \| gh config get oauth_token` | deny | prints the token; run plain 'gh auth status' instead | never |
| 65-stack.sh | stack | `stk sync … --include-human (also …/stk, stk.py)` | ask | writes to MRs/PRs without an agent-* label; label them first (glab mr update N --label agent-worked / gh pr edit N --add-label agent-worked) or ask the user | owns scm |
| 65-stack.sh | stack | `stk sync` | allow | writes only to agent-labelled MRs/PRs (retarget, cascade rebase, lease push of -sub- branches, one leaf refresh); stk plan\|status\|check are reads and pass | owns scm |
| 67-repo-bootstrap.sh | repo-bootstrap | `repoboot apply, or any verb that is not a literal questions\|answer\|plan\|render\|check\|help ($VAR, $(…), xargs, an alias variable)` | ask | creates the repository, makes the first push into an empty remote and changes its settings, protection and labels; show the user `repoboot plan` first, then ask (type the verb literally) | owns scm |
| 67-repo-bootstrap.sh | repo-bootstrap | `repoboot questions\|answer\|plan\|render\|check\|help` | pass | intake, read-only plans and checks, local renders (render refuses the default branch of an existing repository); the permission rules allow them | owns scm |
| 70-jira.sh | jira | `jira set KEY issuelinks \| create --field issuelinks=` | deny | use the governed link commands | owns tracker |
| 70-jira.sh | jira | `jira link A TYPE B (both agent-labelled, type in HARNESS_JIRA_LINK_TYPES_RE)` | allow | otherwise deny | owns tracker |
| 70-jira.sh | jira | `jira create without a provenance label (agent-drafted\|agent-created)` | deny | every agent-created ticket is labelled; use labels agent-drafted (or agent-created) instead | owns tracker |
| 70-jira.sh | jira | `jira create with more than one --field labels` | deny | the last one wins in Jira; pass a single --field labels='["agent-drafted"]' instead | owns tracker |
| 70-jira.sh | jira | `jira create with a provenance label` | allow | creates are promptless | owns tracker |
| 70-jira.sh | jira | `jira label KEY add agent-*` | allow | governance labelling is free | owns tracker |
| 70-jira.sh | jira | `jira set\|comment\|upload\|label KEY on agent-labelled tickets` | allow | promptless (so is a state change, on the main thread) | owns tracker |
| 70-jira.sh | jira | `jira transition KEY, jira set KEY status\|resolution on a human ticket` | ask | ticket state is a human decision; run it only on the user's explicit request (they confirm it), or ask the user to transition it in Jira instead | owns tracker |
| 70-jira.sh | jira | `jira transition, jira set KEY status\|resolution from a subagent` | deny | a subagent never changes ticket state, on human and agent-labelled tickets alike; hand the command back to the main thread | owns tracker |
| 70-jira.sh | jira | `jira state change without a literal key ($VAR, xargs, LBL-1/../X, none) or whose labels cannot be read` | deny | the ticket cannot be checked; type the key literally (e.g. PROJ-123), or ask the user to transition it | owns tracker |
| 70-jira.sh | jira | `jira write whose key is not a literal PROJ-123 word` | ask | the ticket cannot be checked; use a literal key instead | owns tracker |
| 70-jira.sh | jira | `jira hidden from the guard (quoted/escaped/ANSI-C/globbed or case-changed command words, a $VAR/$(…) subcommand, jira fed by xargs, alias, a variable or $(which jira), or a jira call written anywhere outside a known data position)` | ask | the subcommand cannot be checked; write it literally and unquoted instead (a subagent is denied unless it is a known non-state write) | owns tracker |
| 70-jira.sh | jira | `jira guard scanner failure (python3 missing, broken or timed out)` | ask | the command cannot be checked; ask the user to run it, or fix python3 (a subagent is denied) | owns tracker |
| 70-jira.sh | jira | `jira writes to human tickets` | ask | need an explicit user request; ask the user, or label the ticket agent-worked first | owns tracker |
| 75-ticket-workflow.sh | ticket-workflow | `git switch -c\|checkout -b\|branch\|worktree add -b NAME with a ticket key or #N in NAME` | ask | keys live on the MR/PR, not the branch; use a <short-name> branch instead (repos opt in with WORK_TICKET_KEY_IN_BRANCH=1) | owns delivery |
| 75-ticket-workflow.sh | ticket-workflow | `git commit whose first -m/--message starts with a ticket key` | ask | mention the key in the body or MR instead (WORK_TICKET_KEY_IN_BRANCH=1 passes) | owns delivery |
| 75-ticket-workflow.sh | ticket-workflow | `git worktree add PATH -b <-sub- branch> with basename(PATH) != <repo>_<branch>` | ask | subagent worktrees follow ../<repo>_<branch>; use that path instead | owns delivery |
| 75-ticket-workflow.sh | ticket-workflow | `git merge [--no-ff\|--ff\|--ff-only] <-sub- branch> without --squash` | ask | single delivery squash-merges parts; use git merge --squash instead | owns delivery |
| 80-gdoc.sh | gdoc | `gdoc api -X\|--method\|-d\|--data` | deny | api is GET-only; use the create/append/replace/sheet subcommands instead | owns workspace |
| 80-gdoc.sh | gdoc | `gdoc mark ID` | ask | adopts a human file; ask the user before marking it | owns workspace |
| 80-gdoc.sh | gdoc | `gdoc import\|append\|replace\|sheet append\|update on an agent-marked file` | allow | human files / lookup failure ask | owns workspace |
| 80-gdoc.sh | gdoc | `gdoc create \| gdoc mail draft` | allow | create stamps provenance; nothing is sent | owns workspace |
| 80-gdoc.sh | gdoc | `gdoc mail send` | ask | outward and irreversible; use a mail draft instead and let the user send it | owns workspace |
| 83-linux-rules.sh | linux | `ssh … -o StrictHostKeyChecking=no\|off\|false \| UserKnownHostsFile=/dev/null (any spelling: -oX=Y, -o 'X Y', GIT_SSH_COMMAND=, RSYNC_RSH=, rsync -e, scp -o, git -c core.sshCommand, an ssh_config heredoc)` | deny | disables host-key checking; use StrictHostKeyChecking=accept-new, or add the host key to known_hosts after checking its fingerprint, instead | owns infrastructure |
| 83-linux-rules.sh | linux | `sshpass … \| an embedded 'sshpass -p\|-f\|-e\|-d'` | deny | a password on the command line; use key-based auth through ssh-agent (ssh-add) instead | owns infrastructure |
| 83-linux-rules.sh | linux | `ssh HOST (no remote command) \| ssh -t\|-tt HOST …` | ask | interactive session; run 'lx' or 'ssh HOST <read-only command>' instead, or hand the session to the user | owns infrastructure |
| 83-linux-rules.sh | linux | `ssh -L\|-R\|-D\|-W\|-w\|-N\|-f\|-A\|-X\|-Y\|-M\|-O \| -o ProxyCommand\|LocalCommand\|LocalForward\|RemoteForward\|DynamicForward\|RemoteCommand\|Tunnel\|ForwardAgent\|RequestTTY\|ControlMaster` | ask | forwarding, tunnel or local command; hand the command to the user instead, and run read-only checks with 'lx' | owns infrastructure |
| 83-linux-rules.sh | linux | `ssh HOST <command> unless every clause (split on ; && \|\| \| & newline, also inside quotes) is on the read-only allow-list (cat, head, tail without -f, ls, stat, journalctl without -f, systemctl status\|show\|is-*\|list-*\|cat, ip show forms, ss, df, lsblk, zpool status\|list, nft list, iptables -L\|-S, qm\|pct list\|config\|status, pvesh get, pveversion, …); remote sudo, sh\|bash -c, eval, $(…), backticks, $VAR, redirections (2>/dev/null and 2>&1 excepted), heredocs` | ask | not read-only on the host; use 'lx' for read-only checks, or hand the command to the user (on [PROD] as a suggestion with its blast radius) instead | owns infrastructure |
| 83-linux-rules.sh | linux | `ssh run through xargs without -I (arguments appended from stdin)` | ask | the remote command cannot be checked; run one literal 'ssh HOST <command>' per host instead | owns infrastructure |
| 83-linux-rules.sh | linux | `scp\|rsync … HOST:path as the destination (an upload) \| rsync --rsync-path\|--remove-source-files \| sftp \| ssh-copy-id` | ask | writes to a host; download with 'scp HOST:/path .' instead, or hand the copy to the user (host changes go through the infra repository) | owns infrastructure |
| 83-linux-rules.sh | linux | `dd of=/dev/X \| > /dev/X \| cp\|tee … /dev/X (not /dev/null\|zero\|stdout\|stderr\|tty)` | ask | writes a block device; run it against an image file (of=disk.img) instead, or hand the command to the user | owns infrastructure |
| 83-linux-rules.sh | linux | `wipefs -a\|-o, sgdisk, sfdisk, parted, fdisk, gdisk (not their -l/print forms), mkfs[.*], mke2fs, mkswap, blkdiscard, cryptsetup luksFormat\|erase on /dev/X (loop, nbd, mapper included), a $VAR target or xargs-appended targets` | ask | destroys a block device; run it on an image file (mkfs.ext4 disk.img) instead, or hand the command to the user | owns infrastructure |
| 83-linux-rules.sh | linux | `pvcreate\|pvremove\|pvmove\|vgcreate\|vgremove\|vgreduce\|lvcreate\|lvremove\|lvreduce\|lvresize \| zpool create\|destroy\|labelclear \| zfs destroy\|rollback \| mdadm --create\|--zero-superblock` | ask | changes LVM, ZFS or RAID storage; read with lvs, zpool status or mdadm --detail instead, and hand the change to the user | owns infrastructure |
| 83-linux-rules.sh | linux | `nft flush\|add\|delete\|insert\|replace\|create\|destroy\|reset\|-f \| ufw enable\|disable\|allow\|deny\|reject\|limit\|delete\|reset\|insert\|route\|default\|reload \| netplan apply\|try\|generate\|set \| nmcli mutations \| ip <object> add\|del\|set\|change\|replace\|flush\|… \| iptables\|ip6tables -A\|-I\|-D\|-F\|-P\|-X\|-N\|-R\|-Z\|-E \| iptables-restore` | ask | changes the host firewall or network; read with 'nft list ruleset', 'ip -br a' or 'ufw status' instead, and hand the change to the user (it can cut off the session) | owns infrastructure |
| 83-linux-rules.sh | linux | `lx …` | pass | the read-only linux CLI (bounded, redacted, reads ~/.ssh/config aliases, never keys); use it first | owns infrastructure |
| 83-linux-rules.sh | linux | `scp\|rsync\|sftp <a file under ~/.ssh other than *.pub> as a source \| sftp put ~/.ssh/<key> \| ssh-copy-id -i <private key> \| ssh … < ~/.ssh/<key>` | deny | copies a private key off this machine; copy the public key (~/.ssh/<key>.pub) instead — ssh-copy-id -i ~/.ssh/<key>.pub HOST asks | never |
| 85-provision.sh | provision | `prov … \| uv run [opts] prov … \| uv tool run\|uvx [opts] prov …` | pass | renders, validates and plans only (never applies); use it first | owns infrastructure |
| 85-provision.sh | provision | `proxmox-auto-install-assistant … \| nix build\|eval\|flake check\|flake show\|path-info` | pass | write local files or read; use them to prepare and check artefacts | owns infrastructure |
| 85-provision.sh | provision | `[uv run\|uv tool run\|uvx [opts]] prov plan … \| sh\|bash \| eval\|source\|sh -c "$([uv run] prov plan …)"` | ask | runs the printed apply steps; hand them to the user instead | owns infrastructure |
| 85-provision.sh | provision | `qm\|pct list\|config\|status\|showcmd\|pending\|listsnapshot\|help \| pvesh get\|ls\|usage \| pvecm status\|nodes \| pvesm status\|list\|path \| pveum … list \| ha-manager status\|config` | pass | Proxmox VE reads; use them before planning a change | owns infrastructure |
| 85-provision.sh | provision | `qm\|pct create\|destroy\|clone\|set\|start\|stop\|shutdown\|reboot\|template\|importdisk\|disk import\|migrate\|rollback\|snapshot\|delsnapshot\|resize\|unlock\|… \| pvesh set\|create\|delete \| pvecm\|pveum\|pvesm\|pvenode\|ha-manager changes` | ask | changes Proxmox VE guests, storage, users or the cluster; read with 'qm list' / 'pvesh get' instead, and hand the command to the user | owns infrastructure |
| 85-provision.sh | provision | `talosctl gen …\|validate\|machineconfig …\|get\|version\|health\|dmesg\|logs (no -f)\|config info\|contexts\|images\|services\|disks\|mounts\|… \| talosctl apply-config --dry-run` | pass | local generation, validation and node reads; use them first | owns infrastructure |
| 85-provision.sh | provision | `talosctl apply-config (incl. --mode=try)\|reset\|upgrade\|upgrade-k8s\|bootstrap\|reboot\|shutdown\|edit\|patch\|rotate-ca\|wipe\|restart\|… (anything off the read list)` | ask | changes a live node or cluster; check with 'talosctl apply-config --dry-run' / 'talosctl validate' instead, and hand the command to the user | owns infrastructure |
| 85-provision.sh | provision | `talosctl get machineconfig\|*secrets -o yaml\|json \| --namespace secrets -o …` | ask | prints Talos key material; read with the default table output instead, or hand it to the user | owns infrastructure |
| 85-provision.sh | provision | `talosctl kubeconfig \| talosctl config merge\|add\|remove\|context\|endpoint\|node\|new` | deny | writes the human-managed kubeconfig or talosconfig; hand the command to the user instead | owns infrastructure |
| 85-provision.sh | provision | `nixos-rebuild build\|dry-build\|build-vm\|build-vm-with-bootloader\|dry-run\|list-generations (no --target-host/--build-host)` | pass | builds without activating; use it to check a configuration | owns infrastructure |
| 85-provision.sh | provision | `nixos-rebuild switch\|boot\|test\|dry-activate\|… \| nixos-rebuild … --target-host\|--build-host` | ask | activates a configuration or runs on a remote host; build locally with 'nixos-rebuild build' instead, and hand the command to the user | owns infrastructure |
| 85-provision.sh | provision | `nixos-anywhere … (no --vm-test) \| nix run …#nixos-anywhere …` | ask | installs over ssh and wipes the target's disks; test with 'nixos-anywhere --vm-test' instead, and hand the install to the user | owns infrastructure |
| 85-provision.sh | provision | `nixos-anywhere --vm-test …` | pass | a local VM test; use it before the real install | owns infrastructure |
| 85-provision.sh | provision | `disko\|disko-install (any --mode, no --dry-run) \| nix run …#disko …` | ask | partitions, formats or mounts disks; check with 'disko --dry-run' or a VM test instead, and hand the command to the user | owns infrastructure |
| 85-provision.sh | provision | `virsh list\|dominfo\|domstate\|dumpxml\|domblklist\|domiflist\|net-list\|net-info\|pool-list\|pool-info\|vol-list\|capabilities\|nodeinfo\|version\|…` | pass | libvirt reads; use them first | owns infrastructure |
| 85-provision.sh | provision | `virsh destroy\|undefine\|define\|create\|start\|shutdown\|reboot\|reset\|vol-delete\|vol-create*\|pool-destroy\|pool-delete\|net-destroy\|net-undefine\|snapshot-revert\|snapshot-delete\|attach-*\|detach-*\|setmem\|setvcpus\|edit\|console\|… (anything off the read list) \| bare virsh` | ask | changes a libvirt domain, volume, pool or network; read with 'virsh list --all' instead, and hand the command to the user | owns infrastructure |
| 85-provision.sh | provision | `virt-install … (unless both --dry-run and --print-xml)` | ask | creates a VM; check with 'virt-install --dry-run --print-xml …' instead, and hand the command to the user | owns infrastructure |
| 85-provision.sh | provision | `qemu-system-* -drive file=/dev/X \| -hda\|-hdb\|-sd\|-pflash /dev/X \| a bare /dev/X operand \| qemu-img convert\|dd\|create\|resize\|commit\|rebase\|… onto /dev/X` | ask | writes a block device; use an image file (disk.qcow2) instead, or hand the command to the user | owns infrastructure |
| 85-provision.sh | provision | `<reader> ~/.talos/* \| $TALOSCONFIG` | deny | the talosconfig holds the Talos client key; run 'talosctl config info' instead | never |
| 85-provision.sh | provision | `talosctl kubeconfig - (written to stdout)` | deny | prints cluster credentials; hand 'talosctl kubeconfig' to the user instead | never |

`yields`: `owns <domain>` = the rule is skipped in a repository whose `.harness.toml` owns that domain or the section's id; `never` = no repository lifts it: the developer's own credentials (credential files, commands that print stored credentials) and the ask on shell writes to `.harness.toml` (a `# never-yields:` prelude above the section's `repo_owns` line).
<!-- generated:end -->

## Repo overrides

Allow-listed names a repository may set ([principle 8](../../principles/08-user-level-by-design.md),
[repository-level harnesses](../repo-level.md)): only `WORK_TICKET_*` names declared by a
`# repo-override:` comment; the engine, the schema and `harness lint` refuse every other
prefix. Every other variable the guard reads from `guard.env` is a developer-environment
setting rendered from `harness.toml` ([config reference](config-schema.md)), not a repository
override. "Honoured by" names the sections that read the value; owning one of those sections
(or its domain) skips the section and the override with it — owning `scm` also lifts the
GitHub issue-state and merge asks, owning `tracker` the Jira transition deny and the
closing-keyword denies ([what owning a domain lifts](../repo-level.md#what-owning-a-domain-lifts)).

<!-- generated:begin source=bundles/*/guard.d#repo-overrides -->
| name | default | effect | honoured by | set from |
|---|---|---|---|---|
| `WORK_TICKET_ALLOW_DEFAULT_PUSH_RE` | (empty) | regex on the repo top level; there a default-branch push asks instead of denying (personal repos) | `core/guard.d/30-git` | `.harness.toml` `[overrides]` · provider env (wins) · `guard.env` ← `gitlab.personal_repo_re` |
| `WORK_TICKET_ALLOW_TRANSITION` | (empty) | deprecated, no effect since #67: a state change on a human ticket or issue asks on the main thread (and is denied in a subagent) with or without it; remove it | `github/guard.d/60-github`, `jira/guard.d/70-jira` | `.harness.toml` `[overrides]` · provider env (wins) |
| `WORK_TICKET_BASE_BRANCH_RE` | `^(master\|main)$` | default/base branches: pushes to them deny, sub MRs/PRs never target them | `core/guard.d/30-git`, `gitlab/guard.d/50-gitlab`, `github/guard.d/60-github` | `.harness.toml` `[overrides]` · provider env (wins) · `guard.env` ← `core.default_branch_re` |
| `WORK_TICKET_KEY_IN_BRANCH` | (empty) | =1: the repository puts ticket keys in branch names and commit subjects; key-named branches and key-prefixed subjects pass instead of asking | `ticket-workflow/guard.d/75-ticket-workflow` | `.harness.toml` `[overrides]` · provider env (wins) |
| `WORK_TICKET_LABELED_DECISION` | `allow` | allow\|ask: the decision for writes to agent-labelled tickets, issues, MRs and PRs | `gitlab/guard.d/50-gitlab`, `github/guard.d/60-github`, `jira/guard.d/70-jira` | `.harness.toml` `[overrides]` · provider env (wins) |

Precedence per name: environment > `.harness.toml` `[overrides]` > `guard.env` > default. Never settable from `.harness.toml` (only from the developer's own environment): `HARNESS_GUARD_ENV`, `HARNESS_CRED_EXTRA_RE`, `GUARD_GIT`, `GUARD_KUBECTL`, `WORK_TICKET_JIRA_PY`, `WORK_TICKET_GLAB`, `WORK_TICKET_GH`, `WORK_TICKET_GDOC_PY`.
<!-- generated:end -->

## Journal

Opt-in (`lessons.journal = true` in `harness.toml`, rendered as `HARNESS_LESSONS_JOURNAL` into
`guard.env`; off by default, and anything but exactly `true` is off). With it on, every guard
**ask** and **deny** appends one line to
`${XDG_STATE_HOME:-~/.local/state}/harness/journal/<YYYY-MM-DD>.log` (UTC date;
`HARNESS_JOURNAL_DIR` overrides the directory). Allows and passes write nothing, and the allow
path starts no extra process. The two denies the engine prints before any section runs —
malformed hook input and `jq` missing (both fail closed) — are not journaled. A directory that
is empty or relative (no `HOME`, a relative `XDG_STATE_HOME` or `HARNESS_JOURNAL_DIR`) disables
the journal for that call: nothing is ever written under the hook's working directory. A line
is seven tab-separated fields:

| # | field | value |
|---|---|---|
| 1 | `ts` | `date -u +%Y-%m-%dT%H:%M:%SZ` |
| 2 | `provider` | the provider the guard was rendered for (`HARNESS_PROVIDER`), else `-` |
| 3 | `session` | the hook input's `session_id` when it matches `[A-Za-z0-9._-]{1,64}`, else `-` (the gemini and copilot shims pass it through when the provider sends one) |
| 4 | `kind` | `guard-ask`, `guard-deny`; `correction`, `dissatisfaction` are written by the `lessons` bundle's prompt hook (`lessons.prompt_signals`, a later part) |
| 5 | `site` | `<guard_section_*>:<line in that section's file>` of the deciding call; a flushed deferred ask is credited to the rule that deferred it; `-` for prompt kinds |
| 6 | `guard_id` | `HARNESS_GUARD_ID`: the first 12 hex characters of the sha256 of the rendered `guard-bash.sh` |
| 7 | `repo` | directory name of the main checkout of the repository found from the hook's cwd (for a linked worktree, the checkout its `.git` file points at, never the `<repo>_<branch>` worktree name), sanitised to `[A-Za-z0-9._-]`; else `-` |

Example (fields separated by tabs):

```
2026-10-26T09:12:03Z	claude	s1	guard-deny	guard_section_core_30_git:65	3f9c1a7e02bd	shop
```

**Privacy.** The journal never records the command, any word of it, paths, prompt text or the
decision's reason: fields 1–6 come from the clock, a fixed vocabulary, the rendered config and
the sanitised session id, and field 7 is the main checkout's directory name, sanitised
(`bundles/core/guard.d/tests.sh` asserts that no word of a tested command, nor of its cwd
outside that name, longer than three characters reaches the file). It is a local file under your state directory,
written with mode `0600`; nothing sends it anywhere ([governance](../governance.md#10-the-guard-journal-stays-on-your-workstation)).

**`retro/current`.** Each journal line also writes its session id (not `-`) to
`${XDG_STATE_HOME:-~/.local/state}/harness/retro/current` (`HARNESS_RETRO_DIR` overrides the
directory): the last session that produced a signal, which `harness lessons review` reads when
no `--session` is given. Concurrent sessions overwrite each other's pointer.

**Stale lines.** `HARNESS_GUARD_ID` changes whenever the rendered guard changes (an upgrade, an
edited section, another bundle set). Lines whose `guard_id` differs from the current one are
**stale**: their `site` line numbers refer to an older guard, so they are counted but never
attributed to a rule of the current one.

Failures never change a decision: an unwritable directory, a full disk or a missing `date`
leave the decision as it was and write nothing. `HARNESS_LESSONS_JOURNAL`,
`HARNESS_JOURNAL_DIR`, `HARNESS_RETRO_DIR` and `HARNESS_GUARD_ID` carry the `HARNESS_` prefix,
so a repository's `.harness.toml` `[overrides]` can never set them; only your own environment
or `guard.env` does.
