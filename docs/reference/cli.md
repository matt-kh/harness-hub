# Reference: CLI

Every `harness` command and flag, generated from the CLI's own help (`bin/harness --help` and
`bin/harness <command> --help`); do not edit inside the generated region.

Global flags: `--config PATH`, `--home DIR`, `--json`, `--offline`, `--yes`, `--dry-run`.
Environment: `HARNESS_HOME` (hub checkout; `bin/harness` always sets it to its own checkout),
`HARNESS_CONFIG` (config path), `HARNESS_OFFLINE=1`, `NO_COLOR`. `./bootstrap` is `bin/harness bootstrap`.

<!-- generated:begin source=lib/harness/cli.py -->
### harness

```text
usage: harness [-h] [--config PATH] [--home DIR] [--json] [--offline] [--yes] [--dry-run]
               [--version]
               command ...

harness-hub: render one declarative config into every agent provider you use.

positional arguments:
  command
    bootstrap    first run: init -> resolve -> plan -> apply -> doctor -> manual steps
    init         write local/harness.toml from the template (optionally from an org overlay)
    bundles      list bundles or show one
    catalog      list every component with its id, kind, domain, function and posture
    config       validate | get | set | explain | migrate the configuration
    plan         render to memory and show what apply would change
    apply        execute the plan (backups, atomic writes, state)
    sync         classify managed files clean|drifted|missing|foreign; adopt edits back
    render       render the provider trees into a directory (no live files read)
    doctor       PASS/WARN/FAIL checks with the manual step that fixes each failure
    status       active bundles/providers, drift summary, capability matrix
    install      install a pinned, sha256-verified tool into ~/.local/bin
    upgrade      move the hub to the newest release tag (or --to TAG|BRANCH), print migration
                 notes, re-plan, apply, doctor
    pack         write the hub as a release artifact: git bundle + SHA256SUMS + INSTALL.txt (+
                 tools, + .run)
    verify       check a hub bundle or .run file: git bundle verify or sh FILE.run --check,
                 SHA256SUMS beside it
    release      maintainers: check a release tag (preflight) | write its release notes
    uninstall    remove what the harness wrote (state-listed paths only)
    test         run the engine, guard, bundle, skill and provider test suites
    lint         validate manifests, cross-references, templates, private identifiers
    docs         generate | check the generated regions under docs/
    repo         show what the current repository's .harness.toml declares and which user-level
                 components yield here
    steps        list manual steps (--pending: only those whose verify fails)
    version      print hub, applied and runtime versions

options:
  -h, --help     show this help message and exit
  --config PATH  config file (default: $HARNESS_CONFIG or <hub>/local/harness.toml)
  --home DIR     hub directory (HARNESS_HOME)
  --json         machine-readable output
  --offline      skip network checks (HARNESS_OFFLINE=1)
  --yes, -y      assume yes; never prompt
  --dry-run      show what would happen, write nothing
  --version      show program's version number and exit

Run `harness <command> --help` for command flags. Docs: docs/reference/cli.md
```

### harness bootstrap

```text
usage: harness bootstrap [-h] [--config PATH] [--home DIR] [--json] [--offline] [--yes]
                         [--dry-run] [--bundles A,B] [--providers X,Y] [--profile PROFILE]
                         [--email EMAIL] [--no-install-tools] [--adopt PATH] [--from FILE.bundle]
                         [--dest DIR] [--origin URL]

first run: init -> resolve -> plan -> apply -> doctor -> manual steps

options:
  -h, --help            show this help message and exit
  --config PATH         config file (default: $HARNESS_CONFIG or <hub>/local/harness.toml)
  --home DIR            hub directory (HARNESS_HOME)
  --json                machine-readable output
  --offline             skip network checks (HARNESS_OFFLINE=1)
  --yes, -y             assume yes; never prompt
  --dry-run             show what would happen, write nothing
  --bundles A,B, --bundle A,B
                        override [hub].bundles
  --providers X,Y, --provider X,Y
                        override [hub].providers
  --profile PROFILE     profile name from profiles/
  --email EMAIL         identity.email for a new config
  --no-install-tools    do not run `harness install` for missing binaries
  --adopt PATH          take over this foreign path (backed up)
  --from FILE.bundle    clone the hub from this bundle file into --dest, then run the clone's
                        bootstrap with the other flags
  --dest DIR            with --from: where to clone (default ~/harness-hub; must not exist or be
                        empty)
  --origin URL          with --from: set the clone's origin remote (default: the bundle file)
```

### harness init

```text
usage: harness init [-h] [--config PATH] [--home DIR] [--json] [--offline] [--yes] [--dry-run]
                    [--bundles A,B] [--providers X,Y] [--profile PROFILE] [--from PATH|URL]
                    [--email EMAIL] [--force] [--git]

write local/harness.toml from the template (optionally from an org overlay)

options:
  -h, --help            show this help message and exit
  --config PATH         config file (default: $HARNESS_CONFIG or <hub>/local/harness.toml)
  --home DIR            hub directory (HARNESS_HOME)
  --json                machine-readable output
  --offline             skip network checks (HARNESS_OFFLINE=1)
  --yes, -y             assume yes; never prompt
  --dry-run             show what would happen, write nothing
  --bundles A,B, --bundle A,B
                        override [hub].bundles
  --providers X,Y, --provider X,Y
                        override [hub].providers
  --profile PROFILE     profile name from profiles/
  --from PATH|URL       org overlay file or git URL -> local/harness.org.toml
  --email EMAIL         identity.email
  --force               overwrite an existing config
  --git                 git init local/ as a private repository
```

### harness bundles

```text
usage: harness bundles [-h] [--config PATH] [--home DIR] [--json] [--offline] [--yes] [--dry-run]
                       [{list,show}] [name]

list bundles or show one

positional arguments:
  {list,show}
  name

options:
  -h, --help     show this help message and exit
  --config PATH  config file (default: $HARNESS_CONFIG or <hub>/local/harness.toml)
  --home DIR     hub directory (HARNESS_HOME)
  --json         machine-readable output
  --offline      skip network checks (HARNESS_OFFLINE=1)
  --yes, -y      assume yes; never prompt
  --dry-run      show what would happen, write nothing
```

### harness catalog

```text
usage: harness catalog [-h] [--config PATH] [--home DIR] [--json] [--offline] [--yes] [--dry-run]
                       [--kind {bundle,skill,agent,rule,guard,permission,mcp,bin,installer,doctor,step,provider,profile}]
                       [--bundle NAME] [--domain {base,scm,tracker,delivery,kubernetes,workspace}]

list every component with its id, kind, domain, function and posture

options:
  -h, --help            show this help message and exit
  --config PATH         config file (default: $HARNESS_CONFIG or <hub>/local/harness.toml)
  --home DIR            hub directory (HARNESS_HOME)
  --json                machine-readable output
  --offline             skip network checks (HARNESS_OFFLINE=1)
  --yes, -y             assume yes; never prompt
  --dry-run             show what would happen, write nothing
  --kind {bundle,skill,agent,rule,guard,permission,mcp,bin,installer,doctor,step,provider,profile}
                        only this kind of component
  --bundle NAME         only this bundle's components (and the bundle itself)
  --domain {base,scm,tracker,delivery,kubernetes,workspace}
                        only this domain
```

### harness config

```text
usage: harness config [-h] [--config PATH] [--home DIR] [--json] [--offline] [--yes] [--dry-run]
                      action ...

validate | get | set | explain | migrate the configuration

positional arguments:
  action
    validate     schema + secret-shape check of the merged config
    get          print one merged value
    set          set a scalar/simple array in the config file (comments kept)
    explain      type, default, source layer and users of a key
    migrate      rename deprecated keys in the config file

options:
  -h, --help     show this help message and exit
  --config PATH  config file (default: $HARNESS_CONFIG or <hub>/local/harness.toml)
  --home DIR     hub directory (HARNESS_HOME)
  --json         machine-readable output
  --offline      skip network checks (HARNESS_OFFLINE=1)
  --yes, -y      assume yes; never prompt
  --dry-run      show what would happen, write nothing
```

#### harness config validate

```text
usage: harness config validate [-h] [--config PATH] [--home DIR] [--json] [--offline] [--yes]
                               [--dry-run] [--strict]

options:
  -h, --help     show this help message and exit
  --config PATH  config file (default: $HARNESS_CONFIG or <hub>/local/harness.toml)
  --home DIR     hub directory (HARNESS_HOME)
  --json         machine-readable output
  --offline      skip network checks (HARNESS_OFFLINE=1)
  --yes, -y      assume yes; never prompt
  --dry-run      show what would happen, write nothing
  --strict       deprecations are errors
```

#### harness config get

```text
usage: harness config get [-h] [--config PATH] [--home DIR] [--json] [--offline] [--yes]
                          [--dry-run]
                          key

positional arguments:
  key

options:
  -h, --help     show this help message and exit
  --config PATH  config file (default: $HARNESS_CONFIG or <hub>/local/harness.toml)
  --home DIR     hub directory (HARNESS_HOME)
  --json         machine-readable output
  --offline      skip network checks (HARNESS_OFFLINE=1)
  --yes, -y      assume yes; never prompt
  --dry-run      show what would happen, write nothing
```

#### harness config set

```text
usage: harness config set [-h] [--config PATH] [--home DIR] [--json] [--offline] [--yes]
                          [--dry-run]
                          key value

positional arguments:
  key
  value          TOML/JSON literal or bare string

options:
  -h, --help     show this help message and exit
  --config PATH  config file (default: $HARNESS_CONFIG or <hub>/local/harness.toml)
  --home DIR     hub directory (HARNESS_HOME)
  --json         machine-readable output
  --offline      skip network checks (HARNESS_OFFLINE=1)
  --yes, -y      assume yes; never prompt
  --dry-run      show what would happen, write nothing
```

#### harness config explain

```text
usage: harness config explain [-h] [--config PATH] [--home DIR] [--json] [--offline] [--yes]
                              [--dry-run]
                              key

positional arguments:
  key

options:
  -h, --help     show this help message and exit
  --config PATH  config file (default: $HARNESS_CONFIG or <hub>/local/harness.toml)
  --home DIR     hub directory (HARNESS_HOME)
  --json         machine-readable output
  --offline      skip network checks (HARNESS_OFFLINE=1)
  --yes, -y      assume yes; never prompt
  --dry-run      show what would happen, write nothing
```

#### harness config migrate

```text
usage: harness config migrate [-h] [--config PATH] [--home DIR] [--json] [--offline] [--yes]
                              [--dry-run] [--write]

options:
  -h, --help     show this help message and exit
  --config PATH  config file (default: $HARNESS_CONFIG or <hub>/local/harness.toml)
  --home DIR     hub directory (HARNESS_HOME)
  --json         machine-readable output
  --offline      skip network checks (HARNESS_OFFLINE=1)
  --yes, -y      assume yes; never prompt
  --dry-run      show what would happen, write nothing
  --write        write the result (default: show it)
```

### harness plan

```text
usage: harness plan [-h] [--config PATH] [--home DIR] [--json] [--offline] [--yes] [--dry-run]
                    [--bundles A,B] [--providers X,Y] [--diff] [--adopt PATH] [-v]

render to memory and show what apply would change

options:
  -h, --help            show this help message and exit
  --config PATH         config file (default: $HARNESS_CONFIG or <hub>/local/harness.toml)
  --home DIR            hub directory (HARNESS_HOME)
  --json                machine-readable output
  --offline             skip network checks (HARNESS_OFFLINE=1)
  --yes, -y             assume yes; never prompt
  --dry-run             show what would happen, write nothing
  --bundles A,B, --bundle A,B
                        override [hub].bundles
  --providers X,Y, --provider X,Y
                        override [hub].providers
  --diff                show unified diffs
  --adopt PATH          preview taking over PATH
  -v, --verbose         also list unchanged paths
```

### harness apply

```text
usage: harness apply [-h] [--config PATH] [--home DIR] [--json] [--offline] [--yes] [--dry-run]
                     [--bundles A,B] [--providers X,Y] [--diff] [--adopt PATH] [-v]

execute the plan (backups, atomic writes, state)

options:
  -h, --help            show this help message and exit
  --config PATH         config file (default: $HARNESS_CONFIG or <hub>/local/harness.toml)
  --home DIR            hub directory (HARNESS_HOME)
  --json                machine-readable output
  --offline             skip network checks (HARNESS_OFFLINE=1)
  --yes, -y             assume yes; never prompt
  --dry-run             show what would happen, write nothing
  --bundles A,B, --bundle A,B
                        override [hub].bundles
  --providers X,Y, --provider X,Y
                        override [hub].providers
  --diff                show unified diffs
  --adopt PATH          back up and take over PATH (foreign or edited)
  -v, --verbose
```

### harness sync

```text
usage: harness sync [-h] [--config PATH] [--home DIR] [--json] [--offline] [--yes] [--dry-run]
                    [--providers X,Y] [--adopt [PATH ...]]

classify managed files clean|drifted|missing|foreign; adopt edits back

options:
  -h, --help            show this help message and exit
  --config PATH         config file (default: $HARNESS_CONFIG or <hub>/local/harness.toml)
  --home DIR            hub directory (HARNESS_HOME)
  --json                machine-readable output
  --offline             skip network checks (HARNESS_OFFLINE=1)
  --yes, -y             assume yes; never prompt
  --dry-run             show what would happen, write nothing
  --providers X,Y, --provider X,Y
                        override [hub].providers
  --adopt [PATH ...]    copy drifted untemplated files back into their bundle (all, or PATHs)
```

### harness render

```text
usage: harness render [-h] [--config PATH] [--home DIR] [--json] [--offline] [--yes] [--dry-run]
                      [--bundles A,B] [--providers X,Y] --out DIR

render the provider trees into a directory (no live files read)

options:
  -h, --help            show this help message and exit
  --config PATH         config file (default: $HARNESS_CONFIG or <hub>/local/harness.toml)
  --home DIR            hub directory (HARNESS_HOME)
  --json                machine-readable output
  --offline             skip network checks (HARNESS_OFFLINE=1)
  --yes, -y             assume yes; never prompt
  --dry-run             show what would happen, write nothing
  --bundles A,B, --bundle A,B
                        override [hub].bundles
  --providers X,Y, --provider X,Y
                        override [hub].providers
  --out DIR             directory standing in for $HOME
```

### harness doctor

```text
usage: harness doctor [-h] [--config PATH] [--home DIR] [--json] [--offline] [--yes] [--dry-run]
                      [--bundle NAME] [--provider NAME]

PASS/WARN/FAIL checks with the manual step that fixes each failure

options:
  -h, --help       show this help message and exit
  --config PATH    config file (default: $HARNESS_CONFIG or <hub>/local/harness.toml)
  --home DIR       hub directory (HARNESS_HOME)
  --json           machine-readable output
  --offline        skip network checks (HARNESS_OFFLINE=1)
  --yes, -y        assume yes; never prompt
  --dry-run        show what would happen, write nothing
  --bundle NAME
  --provider NAME
```

### harness status

```text
usage: harness status [-h] [--config PATH] [--home DIR] [--json] [--offline] [--yes] [--dry-run]
                      [--matrix]

active bundles/providers, drift summary, capability matrix

options:
  -h, --help     show this help message and exit
  --config PATH  config file (default: $HARNESS_CONFIG or <hub>/local/harness.toml)
  --home DIR     hub directory (HARNESS_HOME)
  --json         machine-readable output
  --offline      skip network checks (HARNESS_OFFLINE=1)
  --yes, -y      assume yes; never prompt
  --dry-run      show what would happen, write nothing
  --matrix       capability matrix of every provider
```

### harness install

```text
usage: harness install [-h] [--config PATH] [--home DIR] [--json] [--offline] [--yes] [--dry-run]
                       [--from FILE] [--version WANT_VERSION] [--insecure] [--dest DIR]
                       [tool]

install a pinned, sha256-verified tool into ~/.local/bin

positional arguments:
  tool                  tool id (tools/<id>.lock.json or a bundle's install/<id>.sh)

options:
  -h, --help            show this help message and exit
  --config PATH         config file (default: $HARNESS_CONFIG or <hub>/local/harness.toml)
  --home DIR            hub directory (HARNESS_HOME)
  --json                machine-readable output
  --offline             skip network checks (HARNESS_OFFLINE=1)
  --yes, -y             assume yes; never prompt
  --dry-run             show what would happen, write nothing
  --from FILE           use a local archive (air-gapped)
  --version WANT_VERSION
                        must equal the locked version
  --insecure            allow a lock without verified sha256
  --dest DIR            install directory (default ~/.local/bin)
```

### harness upgrade

```text
usage: harness upgrade [-h] [--config PATH] [--home DIR] [--json] [--offline] [--yes] [--dry-run]
                       [--to TARGET] [--no-apply]

move the hub to the newest release tag (or --to TAG|BRANCH), print migration notes, re-plan,
apply, doctor

options:
  -h, --help     show this help message and exit
  --config PATH  config file (default: $HARNESS_CONFIG or <hub>/local/harness.toml)
  --home DIR     hub directory (HARNESS_HOME)
  --json         machine-readable output
  --offline      skip network checks (HARNESS_OFFLINE=1)
  --yes, -y      assume yes; never prompt
  --dry-run      show what would happen, write nothing
  --to TARGET    latest (default: newest release tag, pre-releases skipped) | TAG | BRANCH (fast-
                 forward)
  --no-apply     stop after the plan
```

### harness pack

```text
usage: harness pack [-h] [--config PATH] [--home DIR] [--json] [--offline] [--yes] [--dry-run]
                    [--out DIR] [--tag TAG] [--tools OS/ARCH,...] [--self-extract]

write the hub as a release artifact: git bundle + SHA256SUMS + INSTALL.txt (+ tools, + .run)

options:
  -h, --help           show this help message and exit
  --config PATH        config file (default: $HARNESS_CONFIG or <hub>/local/harness.toml)
  --home DIR           hub directory (HARNESS_HOME)
  --json               machine-readable output
  --offline            skip network checks (HARNESS_OFFLINE=1)
  --yes, -y            assume yes; never prompt
  --dry-run            show what would happen, write nothing
  --out DIR            output directory (default <hub>/build/release)
  --tag TAG            release this existing tag (bundle carries every tag; default: branches +
                       tags + HEAD)
  --tools OS/ARCH,...  also download tools/*.lock.json assets for these platforms (e.g.
                       linux/amd64,darwin/arm64)
  --self-extract       also write harness-hub-<version>.run: a POSIX sh header + tar of the
                       bundle, INSTALL.txt, SHA256SUMS and tools (sh FILE.run --check | --list |
                       --extract DIR, or run it to install)
```

### harness verify

```text
usage: harness verify [-h] [--config PATH] [--home DIR] [--json] [--offline] [--yes] [--dry-run]
                      FILE

check a hub bundle or .run file: git bundle verify or sh FILE.run --check, SHA256SUMS beside it

positional arguments:
  FILE           FILE.bundle or FILE.run (SHA256SUMS beside it is checked too)

options:
  -h, --help     show this help message and exit
  --config PATH  config file (default: $HARNESS_CONFIG or <hub>/local/harness.toml)
  --home DIR     hub directory (HARNESS_HOME)
  --json         machine-readable output
  --offline      skip network checks (HARNESS_OFFLINE=1)
  --yes, -y      assume yes; never prompt
  --dry-run      show what would happen, write nothing
```

### harness release

```text
usage: harness release [-h] [--config PATH] [--home DIR] [--json] [--offline] [--yes] [--dry-run]
                       action ...

maintainers: check a release tag (preflight) | write its release notes

positional arguments:
  action
    check        preflight a release tag: SemVer, annotated, VERSION, CHANGELOG, local/, clean
                 tree, on main
    notes        release notes: the CHANGELOG section, install and verify lines, SHA256SUMS

options:
  -h, --help     show this help message and exit
  --config PATH  config file (default: $HARNESS_CONFIG or <hub>/local/harness.toml)
  --home DIR     hub directory (HARNESS_HOME)
  --json         machine-readable output
  --offline      skip network checks (HARNESS_OFFLINE=1)
  --yes, -y      assume yes; never prompt
  --dry-run      show what would happen, write nothing
```

#### harness release check

```text
usage: harness release check [-h] [--config PATH] [--home DIR] [--json] [--offline] [--yes]
                             [--dry-run] [--remote NAME] [--branch NAME] [--no-remote]
                             [TAG]

positional arguments:
  TAG            X.Y.Z[-pre], bare SemVer, no v prefix (default: the tag on HEAD)

options:
  -h, --help     show this help message and exit
  --config PATH  config file (default: $HARNESS_CONFIG or <hub>/local/harness.toml)
  --home DIR     hub directory (HARNESS_HOME)
  --json         machine-readable output
  --offline      skip network checks (HARNESS_OFFLINE=1)
  --yes, -y      assume yes; never prompt
  --dry-run      show what would happen, write nothing
  --remote NAME  remote holding the release branch (default origin)
  --branch NAME  release branch the tag must be on (default main)
  --no-remote    skip the fetch and the on-branch check (local rehearsal)
```

#### harness release notes

```text
usage: harness release notes [-h] [--config PATH] [--home DIR] [--json] [--offline] [--yes]
                             [--dry-run] [--dir DIR] [--out FILE]
                             TAG

positional arguments:
  TAG            the release tag

options:
  -h, --help     show this help message and exit
  --config PATH  config file (default: $HARNESS_CONFIG or <hub>/local/harness.toml)
  --home DIR     hub directory (HARNESS_HOME)
  --json         machine-readable output
  --offline      skip network checks (HARNESS_OFFLINE=1)
  --yes, -y      assume yes; never prompt
  --dry-run      show what would happen, write nothing
  --dir DIR      release directory whose SHA256SUMS is appended
  --out FILE     write the notes here (default: stdout)
```

### harness uninstall

```text
usage: harness uninstall [-h] [--config PATH] [--home DIR] [--json] [--offline] [--yes]
                         [--dry-run] [--bundle NAME] [--provider NAME] [--all] [--purge-tools]

remove what the harness wrote (state-listed paths only)

options:
  -h, --help       show this help message and exit
  --config PATH    config file (default: $HARNESS_CONFIG or <hub>/local/harness.toml)
  --home DIR       hub directory (HARNESS_HOME)
  --json           machine-readable output
  --offline        skip network checks (HARNESS_OFFLINE=1)
  --yes, -y        assume yes; never prompt
  --dry-run        show what would happen, write nothing
  --bundle NAME    only paths owned by these bundles
  --provider NAME  only these providers
  --all            every provider with a state file
  --purge-tools    also remove tools installed by `harness install`
```

### harness test

```text
usage: harness test [-h] [--config PATH] [--home DIR] [--json] [--offline] [--yes] [--dry-run]
                    [-v]
                    [suite]

run the engine, guard, bundle, skill and provider test suites

positional arguments:
  suite          all | unit | guard | bundles | skills | providers | smoke | <bundle name>

options:
  -h, --help     show this help message and exit
  --config PATH  config file (default: $HARNESS_CONFIG or <hub>/local/harness.toml)
  --home DIR     hub directory (HARNESS_HOME)
  --json         machine-readable output
  --offline      skip network checks (HARNESS_OFFLINE=1)
  --yes, -y      assume yes; never prompt
  --dry-run      show what would happen, write nothing
  -v, --verbose
```

### harness lint

```text
usage: harness lint [-h] [--config PATH] [--home DIR] [--json] [--offline] [--yes] [--dry-run]

validate manifests, cross-references, templates, private identifiers

options:
  -h, --help     show this help message and exit
  --config PATH  config file (default: $HARNESS_CONFIG or <hub>/local/harness.toml)
  --home DIR     hub directory (HARNESS_HOME)
  --json         machine-readable output
  --offline      skip network checks (HARNESS_OFFLINE=1)
  --yes, -y      assume yes; never prompt
  --dry-run      show what would happen, write nothing
```

### harness docs

```text
usage: harness docs [-h] [--config PATH] [--home DIR] [--json] [--offline] [--yes] [--dry-run]
                    {generate,check}

generate | check the generated regions under docs/

positional arguments:
  {generate,check}

options:
  -h, --help        show this help message and exit
  --config PATH     config file (default: $HARNESS_CONFIG or <hub>/local/harness.toml)
  --home DIR        hub directory (HARNESS_HOME)
  --json            machine-readable output
  --offline         skip network checks (HARNESS_OFFLINE=1)
  --yes, -y         assume yes; never prompt
  --dry-run         show what would happen, write nothing
```

### harness repo

```text
usage: harness repo [-h] [--config PATH] [--home DIR] [--json] [--offline] [--yes] [--dry-run]
                    [--write]
                    [show|owns|init] [ID|DIR ...]

show what the current repository's .harness.toml declares and which user-level components yield
here

positional arguments:
  show|owns|init  show (default): declaration, problems, what yields, collisions, overrides; owns
                  ID: exit 0 when the repository owns ID (prints why), 1 when not, 2 for an
                  unknown id; init: print a commented .harness.toml
  ID|DIR          owns: the component id, then an optional DIR; show/init: the directory to look
                  from (default: the current one)

options:
  -h, --help      show this help message and exit
  --config PATH   config file (default: $HARNESS_CONFIG or <hub>/local/harness.toml)
  --home DIR      hub directory (HARNESS_HOME)
  --json          machine-readable output
  --offline       skip network checks (HARNESS_OFFLINE=1)
  --yes, -y       assume yes; never prompt
  --dry-run       show what would happen, write nothing
  --write         init: create <repo root>/.harness.toml (never overwrites)
```

### harness steps

```text
usage: harness steps [-h] [--config PATH] [--home DIR] [--json] [--offline] [--yes] [--dry-run]
                     [--bundle NAME] [--pending]

list manual steps (--pending: only those whose verify fails)

options:
  -h, --help     show this help message and exit
  --config PATH  config file (default: $HARNESS_CONFIG or <hub>/local/harness.toml)
  --home DIR     hub directory (HARNESS_HOME)
  --json         machine-readable output
  --offline      skip network checks (HARNESS_OFFLINE=1)
  --yes, -y      assume yes; never prompt
  --dry-run      show what would happen, write nothing
  --bundle NAME
  --pending      only steps whose verify command fails
```

### harness version

```text
usage: harness version [-h] [--config PATH] [--home DIR] [--json] [--offline] [--yes] [--dry-run]

print hub, applied and runtime versions

options:
  -h, --help     show this help message and exit
  --config PATH  config file (default: $HARNESS_CONFIG or <hub>/local/harness.toml)
  --home DIR     hub directory (HARNESS_HOME)
  --json         machine-readable output
  --offline      skip network checks (HARNESS_OFFLINE=1)
  --yes, -y      assume yes; never prompt
  --dry-run      show what would happen, write nothing
```
<!-- generated:end -->
