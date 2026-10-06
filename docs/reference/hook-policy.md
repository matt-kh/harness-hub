# Reference: hook policy

Every guard rule — bundle, command pattern, decision (`allow`, `ask`, `deny`) and reason — plus
the **repo overrides** a repository may set in `.harness.toml` `[overrides]` or a provider `env`
(which wins per key). Both tables are generated, from the `# rule:` and `# repo-override:`
comments in `bundles/*/guard.d/*.sh`; do not edit inside the regions.

Decisions are evaluated section by section in numeric order (`10` k8s … `90+` private); a deny
anywhere wins over an earlier ask, and an allow never overrides a pending ask. On providers without
an ask prompt, `ask` is mapped by `[providers.<name>].ask_as`. Model and rationale:
[governance](../governance.md). The `yields` column says whether a repository's
`.harness.toml` can lift the rule ([repository-level harnesses](../repo-level.md)): `never`
marks the developer's own credentials and the ask on writing `.harness.toml`.

<!-- generated:begin source=bundles/*/guard.d -->
| section | bundle | pattern | decision | reason | yields |
|---|---|---|---|---|---|
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
| 30-git.sh | core | `git push --force\|-f\|+refspec` | ask | force-push rewrites shared history; ask the user first, or push a new branch instead | owns scm |
| 30-git.sh | core | `git reset --hard \| git clean -f/-d/-x` | ask | destructive working-tree command; use git stash, or ask the user first | owns scm |
| 30-git.sh | core | `git push of a -sub- branch from (or via cd into) a sub worktree` | ask | only the main thread pushes stacked branches; run the push from the main checkout instead | owns scm |
| 30-git.sh | core | `git push --all\|--mirror` | ask | would publish every local branch; push the named branch instead | owns scm |
| 30-git.sh | core | `shell write to .harness.toml (> >> tee cp mv install ln dd of= sed -i perl -i, harness repo init --write)` | ask | the repository declaration lifts user-level rules; ask the user to review and commit it instead | never |
| 40-gitlab-closing.sh | gitlab | `(close\|fix\|resolve\|implement) KEY-123 in git commit \| glab mr create\|update \| glab api` | deny | ticket state is human-only; mention the key instead (KEY-123 fix parser) | owns tracker |
| 41-github-closing.sh | github | `(close\|fix\|resolve) #N \| owner/repo#N \| issue URL in git commit \| gh pr create\|edit\|merge \| gh api` | deny | issue state is human-only; mention #N instead (see #N, refs #N) | owns tracker |
| 50-gitlab.sh | gitlab | `glab api -X POST\|PUT\|PATCH\|DELETE \| payload flag` | ask | API write; ask the user, or use the matching glab subcommand | owns scm |
| 50-gitlab.sh | gitlab | `glab mr merge\|approve\|revoke\|delete, issue/release/repo/label mutations` | ask | team-visible, humans merge; ask the user instead of merging or approving | owns scm |
| 50-gitlab.sh | gitlab | `glab label create -n agent-*` | allow | governance label; other labels ask | owns scm |
| 50-gitlab.sh | gitlab | `glab mr create` | allow | creates are ungated (a -sub- source without target / with a base target -> deny) | owns scm |
| 50-gitlab.sh | gitlab | `glab mr update\|note\|close REF on an agent-labelled MR` | allow | human MRs ask; -sub- retarget to base -> deny | owns scm |
| 60-github.sh | github | `gh api -X non-GET \| --input \| fields without a method \| graphql mutation` | ask | API write; ask the user, or use the matching gh subcommand | owns scm |
| 60-github.sh | github | `gh pr merge\|review, release/repo/workflow/secret/auth/gist/... mutations` | ask | team-visible; ask the user (merges, reviews and releases are human-only) | owns scm |
| 60-github.sh | github | `gh label create agent-*` | allow | governance label; other labels ask | owns scm |
| 60-github.sh | github | `gh pr create` | allow | creates are ungated (same -sub- stacked rules as glab) | owns scm |
| 60-github.sh | github | `gh issue create without -l agent-drafted\|agent-created` | deny | provenance label required; use -l agent-drafted (or agent-created) instead | owns scm |
| 60-github.sh | github | `gh pr\|issue edit\|comment\|close\|reopen on an agent-labelled ref` | allow | human refs ask; human issue close\|reopen -> deny; fork PRs ask | owns scm |
| 60-github.sh | github | `gh auth token \| gh auth status --show-token \| gh config get oauth_token` | deny | prints the token; run plain 'gh auth status' instead | never |
| 70-jira.sh | jira | `jira set KEY issuelinks \| create --field issuelinks=` | deny | use the governed link commands | owns tracker |
| 70-jira.sh | jira | `jira link A TYPE B (both agent-labelled, type in HARNESS_JIRA_LINK_TYPES_RE)` | allow | otherwise deny | owns tracker |
| 70-jira.sh | jira | `jira create without a provenance label (agent-drafted\|agent-created)` | deny | every agent-created ticket is labelled; use labels agent-drafted (or agent-created) instead | owns tracker |
| 70-jira.sh | jira | `jira create with a provenance label` | allow | creates are promptless | owns tracker |
| 70-jira.sh | jira | `jira label KEY add agent-*` | allow | governance labelling is free | owns tracker |
| 70-jira.sh | jira | `jira set\|comment\|upload\|label\|transition KEY on agent-labelled tickets` | allow | promptless | owns tracker |
| 70-jira.sh | jira | `jira transition KEY on a human ticket` | deny | ticket state is human-only (ask under WORK_TICKET_ALLOW_TRANSITION=1) | owns tracker |
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
| `WORK_TICKET_ALLOW_TRANSITION` | (empty) | =1: a state change (transition, close, reopen) on a purely human ticket or issue asks instead of denying | `github/guard.d/60-github`, `jira/guard.d/70-jira` | `.harness.toml` `[overrides]` · provider env (wins) |
| `WORK_TICKET_BASE_BRANCH_RE` | `^(master\|main)$` | default/base branches: pushes to them deny, sub MRs/PRs never target them | `core/guard.d/30-git`, `gitlab/guard.d/50-gitlab`, `github/guard.d/60-github` | `.harness.toml` `[overrides]` · provider env (wins) · `guard.env` ← `core.default_branch_re` |
| `WORK_TICKET_KEY_IN_BRANCH` | (empty) | =1: the repository puts ticket keys in branch names and commit subjects; key-named branches and key-prefixed subjects pass instead of asking | `ticket-workflow/guard.d/75-ticket-workflow` | `.harness.toml` `[overrides]` · provider env (wins) |
| `WORK_TICKET_LABELED_DECISION` | `allow` | allow\|ask: the decision for writes to agent-labelled tickets, issues, MRs and PRs | `gitlab/guard.d/50-gitlab`, `github/guard.d/60-github`, `jira/guard.d/70-jira` | `.harness.toml` `[overrides]` · provider env (wins) |

Precedence per name: environment > `.harness.toml` `[overrides]` > `guard.env` > default. Never settable from `.harness.toml` (only from the developer's own environment): `HARNESS_GUARD_ENV`, `HARNESS_CRED_EXTRA_RE`, `GUARD_GIT`, `GUARD_KUBECTL`, `WORK_TICKET_JIRA_PY`, `WORK_TICKET_GLAB`, `WORK_TICKET_GH`, `WORK_TICKET_GDOC_PY`.
<!-- generated:end -->
