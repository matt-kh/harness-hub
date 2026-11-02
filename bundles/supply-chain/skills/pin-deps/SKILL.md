---
name: pin-deps
description: >-
  Pin the moving references in a checkout as a diff for review: GitHub Actions by tag to their
  commit sha, images by tag to their digest, git dependencies by tag to their commit, GitLab
  includes and `go install …@latest` to a fixed ref. Finds them with `supply pins`, resolves
  each value read-only (`git ls-remote`, `gh api` GET, a registry digest read), applies them
  with `supply pins --apply` and re-runs `supply pins` as the check. Use when the user says pin
  the actions, pin dependencies, pin images by digest, "supply pins found …", harden the
  workflows' `uses:`, or runs /pin-deps. NOT for upgrading versions or fixing vulnerabilities
  (use /audit-deps), NOT for editing lockfiles by hand, and NOT for a posture review (use the
  supply-auditor agent). Never guesses a sha, digest or checksum; never commits or pushes.
argument-hint: "[DIR] [--actions|--images|--deps] [--no-apply]"
model: {{ core.model_policy.execute }}
---

# pin-deps — pin moving references, as a reviewed diff

A tag, a branch or `latest` is a pointer someone else can move; a commit sha or a digest is the
value you reviewed. This skill turns the `supply pins` findings that `--apply` can rewrite into
pinned values, writes them with the CLI's exact-token rewrite, and proves the result with
`supply pins` again. The rubric is `{{ provider.skills_dir }}/supply/references/pinning.md`.

**Step 0 — repository-level harness (principle 8).** This is a user-level skill. Read the
repository's declaration first:

```bash
harness repo owns supply-chain/skills/pin-deps   # rc 0 = owned (prints why) → stop; rc 1 = carry on
```

If it is owned (by id or by its domain `security`), or the repository ships its own skill for
the same workflow, this skill yields: say so in one line, name the repository-level skill or
convention, and stop — nothing below runs and nothing is written. Never edit the
repository's harness to fit this skill. `harness repo` explains everything the
repository declares and any `.claude/skills|agents` name collisions.

A pinning bot is a repository convention too: if `renovate.json*`, `.github/renovate.json*` or
`.renovaterc*` extends `helpers:pinGitHubActionDigests` or sets `pinDigests: true`, or
`.github/dependabot.yml` covers the ecosystem, say that the bot owns pinning there and ask
before pinning those classes yourself; never edit the bot's configuration.

## Arguments

- `DIR` — the checkout (default `.`). Paths in the apply file are relative to it.
- `--actions` / `--images` / `--deps` — only that class: actions = `GHA001`, `GHA002`;
  images = `GHA003`, `CI006`, `DKR001`–`DKR003`; deps = `PIP002`, `NPM002`, `CI008`, `GO002`.
  Default: all of them.
- `--no-apply` — resolve and show the apply file and the unresolved list; write nothing.

## Step 1 — findings

```bash
supply pins DIR --json > "$SCRATCH/pins-before.json"; echo "rc=$?"
```

rc 0 → nothing to pin: say so and stop. rc 2 → report the error line and stop. rc 1 → keep the
findings of the selected classes. Findings of other rules (`PIP001`, `PIP003`, `PIP004`,
`NPM001`, `GO001`, `GO003`, `CGO*`, `SH*`, `REG001`, `CI009`, URL archives and tarballs) are not
rewritten by `--apply`: list them for the human with the finding's `fix`. `SUP001`/`SUP002`
mean the scan is incomplete: report them.

## Step 2 — resolve each value, read-only

Every value comes from a command you ran in this session. **Never guess, shorten, recall or
compute a sha, digest or checksum**; an unresolved finding stays unresolved.

A **tag** (`GHA001` `@v4`, a `PIP002`/`NPM002` git tag, a `CI008` `ref:` tag, an image tag)
is resolved to the value it points at today — the pin keeps today's behaviour. A **branch,
`latest` or no ref at all** (`GHA002`, `CI006`/`DKR002`/`DKR003` crit, `CI008` with no or a
branch `ref`, a `@~latest` component, `GO002`) means choosing a version: resolve the latest
release as a **suggestion** and list it for the human; do not apply it unless the user says so.

| Finding | Read-only resolution | `new` |
|---|---|---|
| `GHA001` `O/R@TAG` | `git ls-remote https://github.com/O/R 'refs/tags/TAG' 'refs/tags/TAG^{}'` — take the `^{}` line when present (annotated tag), else the plain line; or `gh api repos/O/R/commits/TAG --jq .sha` (also for a short sha) | `O/R@<40-hex>` |
| `GHA002` `O/R@BRANCH` | suggestion: `gh api repos/O/R/releases/latest --jq .tag_name`, then resolve that tag as above | `O/R@<40-hex>` (only when the user accepts) |
| `GHA003`, `CI006`, `DKR001`–`DKR003` `IMAGE:TAG` | `crane digest IMAGE:TAG`, or `docker buildx imagetools inspect IMAGE:TAG` (the index `Digest:` line) — only when the tool is already installed; never `docker pull` | `IMAGE:TAG@sha256:<64-hex>` |
| `PIP002` `git+URL@TAG` | `git ls-remote URL 'refs/tags/TAG' 'refs/tags/TAG^{}'` (URL without `git+`) | `git+URL@<40-hex>[#egg=…]` |
| `NPM002` `github:O/R#TAG` (or `O/R#TAG`) | `git ls-remote https://github.com/O/R 'refs/tags/TAG' 'refs/tags/TAG^{}'` | the same spec, `…#<40-hex>` |
| `CI008` project include `ref: TAG` | `glab api "projects/<url-encoded path>/repository/tags/TAG" --jq .commit.id` (GET) | the 40-hex sha |
| `CI008` component `…@~latest` | suggestion: the latest released version from the component's project tags | `NAME@X.Y.Z` (only when the user accepts) |
| `GO002` `M@latest` | suggestion: `(cd "$SCRATCH" && GOTOOLCHAIN=local go list -m -json M@latest)` → `.Version` | `M@vX.Y.Z` (only when the user accepts) |

An empty answer, an error, an access denial or a tool that is not installed → unresolved, with
the reason. A private repository you cannot read is unresolved; never ask for a token.

## Step 3 — the apply file

Write `$SCRATCH/pins.json`, the format `supply pins --apply` takes:

```json
[
  {"file": ".github/workflows/build.yml", "line": 8, "old": "actions/checkout@v4",
   "new": "actions/checkout@0123456789abcdef0123456789abcdef01234567"}
]
```

`file` and `line` are the finding's; `old` is its `ref`, copied exactly; `new` pins it without
renaming it. With `--no-apply`, show this file and the unresolved list, and stop.

## Step 4 — apply

```bash
supply pins DIR --apply "$SCRATCH/pins.json"; echo "rc=$?"
```

Writes are all-or-nothing. rc 2 lists one reason per refused entry (an `old` that is not a
current finding's `ref` on that line, not a whole token, a `new` that renames, a symlink, a
`.git` path): fix those entries or drop them, and rerun; never edit the files by hand instead.
With `supply_chain.pin_actions = false`, action pins are skipped and listed in `data.skipped`:
report them and leave them.

For an action rewritten from a tag, the rubric's form keeps the tag as a comment
(`uses: O/R@<sha> # v4`), which Renovate and Dependabot read to keep the pin current: when the
rewritten line has no comment, append ` # TAG` to it, touching nothing else on the line.

## Step 5 — sensor

```bash
supply pins DIR --json > "$SCRATCH/pins-after.json"; echo "rc=$?"
git -C DIR diff --stat
```

Every applied finding must be gone from `pins-after.json`; one that remains is a failure to
report, not to hide. rc 1 is expected while other classes or unresolved findings remain.

## Report

- **Pinned** — `file:line · rule id · old → new` (and the tag kept as a comment).
- **Suggested, not applied** — branch, `latest` and no-ref findings with the release you
  resolved, for the human to accept.
- **Unresolved** — finding and reason (no access, tool missing, empty answer).
- **Not for --apply** — the other rule ids with their `fix`, for the human.
- **Sensor** — `supply pins` before and after (counts per rule id) and `git diff --stat`.
- **Not verified** — anything skipped. Never leave this out.

## Never

- Never guess a sha, digest or checksum, or take one from memory, a comment or an issue.
- Never edit a lockfile or a pinned file by hand to pin a value; `supply pins --apply` is the
  writer (the trailing `# TAG` comment is the one exception).
- Never pull an image, install a tool or run a dependency to resolve a pin.
- Never commit, push or open a merge request: the diff is the user's to review.
- Never pass `--trusted-host`, `strict-ssl false`, `http.sslVerify=false` or
  `GIT_SSL_NO_VERIFY` to make a resolution work.
