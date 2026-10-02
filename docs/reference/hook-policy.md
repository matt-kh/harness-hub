# Reference: hook policy

Every guard rule — bundle, command pattern, decision (`allow`, `ask`, `deny`) and reason — plus
the override variables a repository can set. Generated from the `# rule: <pattern> -> <decision> : <reason>`
comments in `bundles/*/guard.d/*.sh`; do not edit inside the generated region.

Decisions are evaluated section by section in numeric order (`10` k8s … `90+` private); a deny
anywhere wins over an earlier ask, and an allow never overrides a pending ask. On providers without
an ask prompt, `ask` is mapped by `[providers.<name>].ask_as`. Model and rationale:
[governance](../governance.md).

<!-- generated:begin source=bundles/*/guard.d -->
| section | bundle | pattern | decision | reason |
|---|---|---|---|---|
| 20-credentials.sh | core | `<reader> ~/.kube/* \| $KUBECONFIG` | deny | kubeconfig holds cluster credentials; use 'kubectl config get-contexts' or 'k8s contexts' instead |
| 20-credentials.sh | core | `<reader> tool credential files (~/.config/{jira,glab-cli,gdoc,gh}, agent credential json)` | deny | use the tool's own auth status command |
| 20-credentials.sh | core | `<reader> .env / .env.*` | deny | secrets; ask the user for the variable names |
| 20-credentials.sh | core | `<reader> ~/.aws/* \| ~/.ssh/* (except *.pub)` | deny | private keys / cloud credentials; use 'ssh-add -l', the *.pub file or 'aws sts get-caller-identity' instead |
| 20-credentials.sh | core | `<reader> path matching HARNESS_CRED_EXTRA_RE` | deny | org-specific credential paths; run the tool's own auth status command instead |
| 20-credentials.sh | core | `env \| printenv (no command)` | deny | dumps the whole environment; print named non-secret variables instead |
| 20-credentials.sh | core | `printenv NAME \| echo $NAME (NAME looks secret)` | deny | prints a secret; test presence with [ -n "${VAR:+x}" ] instead |
| 25-k8s-rules.sh | k8s | `kubectl config view --raw` | deny | prints credentials; use plain 'kubectl config view' (redacted) instead |
| 25-k8s-rules.sh | k8s | `kubectl config use-context\|set-*\|delete-*\|rename-context` | deny | kubeconfig is human-managed; pass --context on every command instead (see the k8s rule) |
| 25-k8s-rules.sh | k8s | `aws eks update-kubeconfig \| eksctl utils write-kubeconfig` | deny | kubeconfig is human-managed; pass --context on every command instead (see the k8s rule) |
| 25-k8s-rules.sh | k8s | `kubectl get secret(s) -o yaml\|json\|jsonpath\|template \| get --raw .../secrets` | deny | Secret values are never printed; use 'k8s secret-keys NS NAME' or pipe through 'k8s redact' instead |
| 25-k8s-rules.sh | k8s | `kubectl create token` | ask | mints a ServiceAccount credential; ask the user, or use read-only k8s commands instead |
| 25-k8s-rules.sh | k8s | `kubectl exec\|attach\|cp\|debug\|port-forward\|proxy` | ask | exec-class; use 'k8s pod' or 'kubectl logs' for read-only triage instead |
| 25-k8s-rules.sh | k8s | `kubectl apply\|delete\|edit\|patch\|scale\|rollout restart\|... (no --dry-run=client\|server)` | ask | cluster mutation; use --dry-run=server, or hand the command to the user instead |
| 25-k8s-rules.sh | k8s | `helm get values\|all\|manifest` | ask | may print credentials; pipe every clause through 'k8s redact' instead (then allowed) |
| 25-k8s-rules.sh | k8s | `helm install\|upgrade\|uninstall\|rollback\|test\|push\|registry login` | ask | release mutation; use 'helm template' read-only, or hand the command to the user instead |
| 25-k8s-rules.sh | k8s | `argocd app(set) sync\|delete\|set\|... \| flux reconcile\|... \| eksctl create\|...` | ask | GitOps / cluster mutation; change the GitOps repo instead, or hand the command to the user |
| 25-k8s-rules.sh | k8s | `pulumi up\|destroy\|refresh\|import \| terraform apply\|destroy\|import` | ask | IaC state mutation; run a preview / plan instead, or hand the command to the user |
| 30-git.sh | core | `git push <dst matching WORK_TICKET_BASE_BRANCH_RE> (explicit refspec or current branch)` | deny | MR/PR-based workflow; push a branch and open an MR/PR instead |
| 30-git.sh | core | `git push to a default branch in a repo matching WORK_TICKET_ALLOW_DEFAULT_PUSH_RE` | ask | personal repos; ask the user to confirm, or push a branch instead |
| 30-git.sh | core | `git push --force\|-f\|+refspec` | ask | force-push rewrites shared history; ask the user first, or push a new branch instead |
| 30-git.sh | core | `git reset --hard \| git clean -f/-d/-x` | ask | destructive working-tree command; use git stash, or ask the user first |
| 30-git.sh | core | `git push of a -sub- branch from (or via cd into) a sub worktree` | ask | only the main thread pushes stacked branches; run the push from the main checkout instead |
| 30-git.sh | core | `git push --all\|--mirror` | ask | would publish every local branch; push the named branch instead |
| 40-gitlab-closing.sh | gitlab | `(close\|fix\|resolve\|implement) KEY-123 in git commit \| glab mr create\|update \| glab api` | deny | ticket state is human-only; mention the key instead (KEY-123 fix parser) |
| 41-github-closing.sh | github | `(close\|fix\|resolve) #N \| owner/repo#N \| issue URL in git commit \| gh pr create\|edit\|merge \| gh api` | deny | issue state is human-only; mention #N instead (see #N, refs #N) |
| 50-gitlab.sh | gitlab | `glab api -X POST\|PUT\|PATCH\|DELETE \| payload flag` | ask | API write; ask the user, or use the matching glab subcommand |
| 50-gitlab.sh | gitlab | `glab mr merge\|approve\|revoke\|delete, issue/release/repo/label mutations` | ask | team-visible, humans merge; ask the user instead of merging or approving |
| 50-gitlab.sh | gitlab | `glab label create -n agent-*` | allow | governance label; other labels ask |
| 50-gitlab.sh | gitlab | `glab mr create` | allow | creates are ungated (a -sub- source without target / with a base target -> deny) |
| 50-gitlab.sh | gitlab | `glab mr update\|note\|close REF on an agent-labelled MR` | allow | human MRs ask; -sub- retarget to base -> deny |
| 60-github.sh | github | `gh auth token \| gh auth status --show-token \| gh config get oauth_token` | deny | prints the token; run plain 'gh auth status' instead |
| 60-github.sh | github | `gh api -X non-GET \| --input \| fields without a method \| graphql mutation` | ask | API write; ask the user, or use the matching gh subcommand |
| 60-github.sh | github | `gh pr merge\|review, release/repo/workflow/secret/auth/gist/... mutations` | ask | team-visible; ask the user (merges, reviews and releases are human-only) |
| 60-github.sh | github | `gh label create agent-*` | allow | governance label; other labels ask |
| 60-github.sh | github | `gh pr create` | allow | creates are ungated (same -sub- stacked rules as glab) |
| 60-github.sh | github | `gh issue create without -l agent-drafted\|agent-created` | deny | provenance label required; use -l agent-drafted (or agent-created) instead |
| 60-github.sh | github | `gh pr\|issue edit\|comment\|close\|reopen on an agent-labelled ref` | allow | human refs ask; human issue close\|reopen -> deny; fork PRs ask |
| 70-jira.sh | jira | `jira set KEY issuelinks \| create --field issuelinks=` | deny | use the governed link commands |
| 70-jira.sh | jira | `jira link A TYPE B (both agent-labelled, type in HARNESS_JIRA_LINK_TYPES_RE)` | allow | otherwise deny |
| 70-jira.sh | jira | `jira create without a provenance label (agent-drafted\|agent-created)` | deny | every agent-created ticket is labelled; use labels agent-drafted (or agent-created) instead |
| 70-jira.sh | jira | `jira create with a provenance label` | allow | creates are promptless |
| 70-jira.sh | jira | `jira label KEY add agent-*` | allow | governance labelling is free |
| 70-jira.sh | jira | `jira set\|comment\|upload\|label\|transition KEY on agent-labelled tickets` | allow | promptless |
| 70-jira.sh | jira | `jira transition KEY on a human ticket` | deny | ticket state is human-only (ask under WORK_TICKET_ALLOW_TRANSITION=1) |
| 70-jira.sh | jira | `jira writes to human tickets` | ask | need an explicit user request; ask the user, or label the ticket agent-worked first |
| 80-gdoc.sh | gdoc | `gdoc api -X\|--method\|-d\|--data` | deny | api is GET-only; use the create/append/replace/sheet subcommands instead |
| 80-gdoc.sh | gdoc | `gdoc mark ID` | ask | adopts a human file; ask the user before marking it |
| 80-gdoc.sh | gdoc | `gdoc import\|append\|replace\|sheet append\|update on an agent-marked file` | allow | human files / lookup failure ask |
| 80-gdoc.sh | gdoc | `gdoc create \| gdoc mail draft` | allow | create stamps provenance; nothing is sent |
| 80-gdoc.sh | gdoc | `gdoc mail send` | ask | outward and irreversible; use a mail draft instead and let the user send it |
<!-- generated:end -->
