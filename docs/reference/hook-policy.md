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
| 20-credentials.sh | core | `<reader> ~/.kube/* \| $KUBECONFIG` | deny | kubeconfig holds cluster credentials |
| 20-credentials.sh | core | `<reader> tool credential files (~/.config/{jira,glab-cli,gdoc,gh}, agent credential json)` | deny | use the tool's own auth status command |
| 20-credentials.sh | core | `<reader> .env / .env.*` | deny | secrets; ask the user for the variable names |
| 20-credentials.sh | core | `<reader> ~/.aws/* \| ~/.ssh/* (except *.pub)` | deny | private keys / cloud credentials |
| 20-credentials.sh | core | `<reader> path matching HARNESS_CRED_EXTRA_RE` | deny | org-specific credential paths |
| 20-credentials.sh | core | `env \| printenv (no command)` | deny | dumps the whole environment |
| 20-credentials.sh | core | `printenv NAME \| echo $NAME (NAME looks secret)` | deny | prints a secret |
| 25-k8s-rules.sh | k8s | `kubectl config view --raw` | deny | prints credentials |
| 25-k8s-rules.sh | k8s | `kubectl config use-context\|set-*\|delete-*\|rename-context` | deny | kubeconfig is human-managed |
| 25-k8s-rules.sh | k8s | `aws eks update-kubeconfig \| eksctl utils write-kubeconfig` | deny | kubeconfig is human-managed |
| 25-k8s-rules.sh | k8s | `kubectl get secret(s) -o yaml\|json\|jsonpath\|template \| get --raw .../secrets` | deny | Secret values are never printed (unless piped through k8s redact) |
| 25-k8s-rules.sh | k8s | `kubectl create token` | ask | mints a ServiceAccount credential |
| 25-k8s-rules.sh | k8s | `kubectl exec\|attach\|cp\|debug\|port-forward\|proxy` | ask | exec-class |
| 25-k8s-rules.sh | k8s | `kubectl apply\|delete\|edit\|patch\|scale\|rollout restart\|... (no --dry-run=client\|server)` | ask | cluster mutation |
| 25-k8s-rules.sh | k8s | `helm get values\|all\|manifest` | ask | may print credentials (allow when every clause is piped through k8s redact) |
| 25-k8s-rules.sh | k8s | `helm install\|upgrade\|uninstall\|rollback\|test\|push\|registry login` | ask | release mutation |
| 25-k8s-rules.sh | k8s | `argocd app(set) sync\|delete\|set\|... \| flux reconcile\|... \| eksctl create\|...` | ask | GitOps / cluster mutation |
| 25-k8s-rules.sh | k8s | `pulumi up\|destroy\|refresh\|import \| terraform apply\|destroy\|import` | ask | IaC state mutation |
| 30-git.sh | core | `git push <dst matching WORK_TICKET_BASE_BRANCH_RE> (explicit refspec or current branch)` | deny | MR/PR-based workflow |
| 30-git.sh | core | `git push to a default branch in a repo matching WORK_TICKET_ALLOW_DEFAULT_PUSH_RE` | ask | personal repos |
| 30-git.sh | core | `git push --force\|-f\|+refspec` | ask | force-push |
| 30-git.sh | core | `git reset --hard \| git clean -f/-d/-x` | ask | destructive working-tree command |
| 30-git.sh | core | `git push of a -sub- branch from (or via cd into) a sub worktree` | ask | only the main thread pushes stacked branches |
| 30-git.sh | core | `git push --all\|--mirror` | ask | would publish every local branch |
| 40-gitlab-closing.sh | gitlab | `(close\|fix\|resolve\|implement) KEY-123 in git commit \| glab mr create\|update \| glab api` | deny | ticket state is human-only |
| 41-github-closing.sh | github | `(close\|fix\|resolve) #N \| owner/repo#N \| issue URL in git commit \| gh pr create\|edit\|merge \| gh api` | deny | issue state is human-only |
| 50-gitlab.sh | gitlab | `glab api -X POST\|PUT\|PATCH\|DELETE \| payload flag` | ask | API write |
| 50-gitlab.sh | gitlab | `glab mr merge\|approve\|revoke\|delete, issue/release/repo/label mutations` | ask | team-visible, humans merge |
| 50-gitlab.sh | gitlab | `glab label create -n agent-*` | allow | governance label; other labels ask |
| 50-gitlab.sh | gitlab | `glab mr create` | allow | creates are ungated (a -sub- source without target / with a base target -> deny) |
| 50-gitlab.sh | gitlab | `glab mr update\|note\|close REF on an agent-labelled MR` | allow | human MRs ask; -sub- retarget to base -> deny |
| 60-github.sh | github | `gh auth token \| gh auth status --show-token \| gh config get oauth_token` | deny | prints the token |
| 60-github.sh | github | `gh api -X non-GET \| --input \| fields without a method \| graphql mutation` | ask | API write |
| 60-github.sh | github | `gh pr merge\|review, release/repo/workflow/secret/auth/gist/... mutations` | ask | team-visible |
| 60-github.sh | github | `gh label create agent-*` | allow | governance label; other labels ask |
| 60-github.sh | github | `gh pr create` | allow | creates are ungated (same -sub- stacked rules as glab) |
| 60-github.sh | github | `gh issue create without -l agent-drafted\|agent-created` | deny | provenance label required |
| 60-github.sh | github | `gh pr\|issue edit\|comment\|close\|reopen on an agent-labelled ref` | allow | human refs ask; human issue close\|reopen -> deny; fork PRs ask |
| 70-jira.sh | jira | `jira set KEY issuelinks \| create --field issuelinks=` | deny | use the governed link commands |
| 70-jira.sh | jira | `jira link A TYPE B (both agent-labelled, type in HARNESS_JIRA_LINK_TYPES_RE)` | allow | otherwise deny |
| 70-jira.sh | jira | `jira create without a provenance label (agent-drafted\|agent-created)` | deny | every agent-created ticket is labelled |
| 70-jira.sh | jira | `jira create with a provenance label` | allow | creates are promptless |
| 70-jira.sh | jira | `jira label KEY add agent-*` | allow | governance labelling is free |
| 70-jira.sh | jira | `jira set\|comment\|upload\|label\|transition KEY on agent-labelled tickets` | allow | promptless |
| 70-jira.sh | jira | `jira transition KEY on a human ticket` | deny | ticket state is human-only (ask under WORK_TICKET_ALLOW_TRANSITION=1) |
| 70-jira.sh | jira | `jira writes to human tickets` | ask | need an explicit user request |
| 80-gdoc.sh | gdoc | `gdoc api -X\|--method\|-d\|--data` | deny | api is GET-only |
| 80-gdoc.sh | gdoc | `gdoc mark ID` | ask | adopts a human file |
| 80-gdoc.sh | gdoc | `gdoc import\|append\|replace\|sheet append\|update on an agent-marked file` | allow | human files / lookup failure ask |
| 80-gdoc.sh | gdoc | `gdoc create \| gdoc mail draft` | allow | create stamps provenance; nothing is sent |
| 80-gdoc.sh | gdoc | `gdoc mail send` | ask | outward and irreversible |
<!-- generated:end -->
