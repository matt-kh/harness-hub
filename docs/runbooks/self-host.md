# Runbook: self-host an org platform instance

Goal: your organisation runs its own copy of harness-hub on its own git host, with org
bundles and org defaults, and every developer installs from it. Background:
[distribution](../distribution.md), [principle 3](../../principles/03-platform-for-everyone.md),
[principle 4](../../principles/04-install-as-a-platform.md).

Roles: a **platform maintainer** does steps 1–7 once; **developers** do step 8.

## 1. Create the instance

Pick one, on your git host (GitLab, Gitea, a bare repo on a share):

```sh
# a) mirror upstream into a new, PRIVATE project
git clone --origin upstream https://github.com/matt-kh/harness-hub.git harness-hub
cd harness-hub
git remote add origin git@git.example.com:platform/harness-hub.git
git push origin --all && git push origin --tags

# b) no internet on the build host: start from a release bundle
harness verify harness-hub-X.Y.Z.bundle             # or: git bundle verify FILE
git clone --origin upstream harness-hub-X.Y.Z.bundle harness-hub
cd harness-hub && git remote add origin git@git.example.com:platform/harness-hub.git
git push origin --all && git push origin --tags
```

- Keep the project **private** once it contains org bundles.
- Protect the default branch on the git host; changes arrive as MRs/PRs like any other repo.

## 2. Track upstream

```sh
git fetch upstream --tags
git merge X.Y.Z                     # a release tag; or upstream/main if you follow main
git push origin HEAD:<branch> && git push origin --tags      # then open an MR into your default branch
```

- Prefer merging release tags. Read the CHANGELOG **Migration** paragraphs for every version
  you cross before merging.
- Keep org changes in new files (org bundles, overlay) rather than edits to upstream files, so
  merges stay conflict-free.
- Air-gapped: point the remote at a release bundle instead
  (`git remote set-url upstream /path/harness-hub-X.Y.Z.bundle`), then fetch as above.

## 3. Add org bundles in-repo

```sh
mkdir -p bundles/acme-platform
# same layout as any bundle: bundle.toml, rules/, skills/, guard.d/, doctor/, …
bin/harness lint
bin/harness docs generate
```

- Name them with an org prefix (`bundles/<org>-<topic>/`) so they never collide with upstream
  bundle names. A separate directory also works: list it in `[hub].bundle_paths` or
  `HARNESS_BUNDLE_PATH`.
- Follow the add-a-bundle checklist in [CONTRIBUTING](../../CONTRIBUTING.md#adding-a-bundle),
  including the `[harness]` guides and sensors.
- Org guard sections use prefixes `90+`.

## 4. Configure the gate for the instance

The private-identifier gate still runs in your instance; it now protects what must never
leave even the org (customer names, personal data), not your own hostnames.

- Set the instance's CI secret `GATE_PRIVATE_DENYLIST` to that list (one ERE per line).
- Allow the org's own values where they are expected, for example an `allowlist.txt` row for
  `bundles/<org>-.*` paths ([tools/gate](../../tools/gate/README.md#suppressing-a-public-hit)).
- Contributing a generic fix upstream: branch from an upstream tag, cherry-pick the generic
  commit, and run the gate with your org denylist in `local/gate-denylist.txt` before
  opening the upstream PR.

## 5. Publish the org overlay

The overlay holds org-wide config defaults (hosts, regexes, Jira field ids, trust text).

```sh
mkdir -p org && $EDITOR org/harness.org.toml       # same keys as local/harness.toml
git add org/harness.org.toml && git commit -m "org: overlay defaults"
```

- Developers seed it with `harness init --from <path|url>`; it is stored as
  `local/harness.org.toml` and sits between bundle defaults and their own `local/harness.toml`.
- A git URL works too: `init --from` clones the repository and copies its root
  `harness.org.toml`, so the overlay may also live in a small separate repo.
- No secrets: validation rejects secret-looking keys and values.

## 6. Cut org releases

```sh
git tag -a X.Y.Z-acme.1 -m "acme release on upstream X.Y.Z"
git push origin X.Y.Z-acme.1
harness pack --out rel --tag X.Y.Z-acme.1 --tools linux/amd64,darwin/arm64
harness verify rel/harness-hub-*.bundle
```

- Publish `rel/` (bundle, sidecar archives, `SHA256SUMS`, `INSTALL.txt`) wherever your
  developers can reach: an artifact store, a file share, removable media.
- Sidecar archives come from the pinned `tools/*.lock.json`; mirror them instead with
  `HARNESS_TOOLS_MIRROR` if you run an artifact store.

## 7. Write the onboarding one-liner

Connected developers:

```sh
git clone git@git.example.com:platform/harness-hub.git ~/harness-hub \
  && ~/harness-hub/bin/harness init --from ~/harness-hub/org/harness.org.toml \
       --bundles core,acme-platform,gitlab,jira,ticket-workflow --providers claude \
  && ~/harness-hub/bootstrap
```

Offline developers:

```sh
git clone harness-hub-X.Y.Z-acme.1.bundle ~/harness-hub
git -C ~/harness-hub remote set-url origin git@git.example.com:platform/harness-hub.git   # once the host is reachable
~/harness-hub/bin/harness init --from ~/harness-hub/org/harness.org.toml --bundles core,acme-platform,gitlab,jira
~/harness-hub/bootstrap --offline --no-install-tools
```

- `init` needs a selection: `--bundles a,b` or `--profile NAME` (a profile committed under
  `profiles/` works well for org-wide selections). It writes `local/harness.toml` with the
  overlay beside it; `bootstrap` then resolves, plans, applies and runs doctor.
- Put the one-liner and the list of manual steps (`harness steps --pending`) in your internal
  onboarding page.

## 8. Developers upgrade

```sh
harness upgrade --to X.Y.Z-acme.2       # fetches from origin = your instance
```

- `upgrade` prints the Migration notes, re-validates config, shows the plan and applies with
  backups ([upgrade runbook](upgrade.md)).

## 9. Config-key migrations

- Before merging an upstream release, read its Migration paragraphs and update
  `org/harness.org.toml` in the same MR.
- `harness config migrate` performs pure renames in a developer's `local/harness.toml`,
  preserving comments.
- Deprecated keys warn for two minor releases, then error; fix the overlay before that.

## Checklist

- [ ] Instance is private, default branch protected
- [ ] `upstream` remote set; merges by release tag
- [ ] Org bundles under `bundles/<org>-*/`, lint clean, docs generated
- [ ] Gate denylist secret set; org paths allowlisted
- [ ] Overlay committed; onboarding one-liner published
- [ ] Release bundle packed and verified for every platform you support
