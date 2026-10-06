# Runbook: air-gapped and proxied networks

The hub needs the network only for tool downloads, `upgrade`, and the online doctor checks
([SECURITY.md](../../SECURITY.md#outbound-network-calls)). Everything else works offline.

## Behind a proxy

Downloads use curl or python's urllib and honour the standard variables:

```sh
export HTTPS_PROXY=http://proxy.example.com:3128
export NO_PROXY=localhost,127.0.0.1,.example.com
```

For an internal CA, point python and curl at your bundle:
`export SSL_CERT_FILE=/etc/ssl/certs/ca-bundle.pem CURL_CA_BUNDLE=$SSL_CERT_FILE`.

## Through an artifact mirror

Every pinned tool is described in `tools/<tool>.lock.json` (version, per-OS/arch URL, sha256).
Point the hub at a mirror that serves the same file names:

```sh
export HARNESS_TOOLS_MIRROR=https://artifacts.example.com/github-releases
harness install gh
```

The base URL is rewritten; the sha256 check is unchanged, so a mirror cannot substitute a
different binary.

## Fully offline: the release bundle

The supported path is the release artifact described in [distribution](../distribution.md):
one `git bundle` file with the whole hub, optional tool archives, `SHA256SUMS` and
`INSTALL.txt`.

On a connected machine with a clean clone (upstream or your org instance):

```sh
harness pack --out /media/usb/rel --tag X.Y.Z --tools linux/amd64,darwin/arm64
harness verify /media/usb/rel/harness-hub-X.Y.Z.bundle
```

- `--tools` downloads the `tools/*.lock.json` assets for those platforms with the same
  sha256 check as `harness install`; leave it out if the offline side has its own mirror.
- `pack` refuses a dirty tree and never includes `local/`. Carry your `local/harness.toml`
  separately if you need it (it holds no secrets).

On the offline machine:

```sh
cd /media/usb/rel && shasum -a 256 -c SHA256SUMS
git clone harness-hub-X.Y.Z.bundle ~/harness-hub
~/harness-hub/bootstrap --offline --no-install-tools
harness install gh --from /media/usb/rel/tools/gh_<version>_linux_amd64.tar.gz
harness doctor --offline
```

`--offline` (or `HARNESS_OFFLINE=1`) skips every check that needs the network; they show as
`SKIP`, not `FAIL`.

### One file: the `.run` envelope

`harness pack ... --self-extract` (and every published release) adds
`harness-hub-X.Y.Z.run`: a POSIX sh header plus a tar of the directory above, so one file
crosses the gap. On the connected side, check it before carrying it (and, for a published
release, its provenance: `gh attestation verify harness-hub-X.Y.Z.run -R matt-kh/harness-hub`):

```sh
sh harness-hub-X.Y.Z.run --check         # payload size + sha256, every SHA256SUMS line
```

On the offline side (needs sh, tar, git, bash, python3, jq):

```sh
sh harness-hub-X.Y.Z.run --check
sh harness-hub-X.Y.Z.run --offline --no-install-tools       # --dest DIR, default ~/harness-hub
harness install gh --from ~/.local/share/harness/releases/X.Y.Z/tools/gh_<version>_linux_amd64.tar.gz
harness doctor --offline
```

- The release files stay in `~/.local/share/harness/releases/X.Y.Z/` (`--release-dir DIR`
  to change it); the clone's `origin` is the bundle there.
- To unpack only and follow `INSTALL.txt` by hand: `sh harness-hub-X.Y.Z.run --extract DIR`.

### Without `harness pack`

Plain git and a checksum tool do the same job, for example from an older checkout:

```sh
git bundle create harness-hub.bundle --all
jq -r '.assets["linux/amd64"] | .url, .sha256' tools/gh.lock.json   # then curl -fLO <url>
shasum -a 256 <file>                                                 # must equal the lock's sha256
```

## Upgrading offline

`harness upgrade --to TAG` runs `git fetch --tags` from the clone's `origin`, so point
`origin` at the new bundle file and upgrade:

```sh
git -C ~/harness-hub remote set-url origin /media/usb/rel/harness-hub-X.Y.Z.bundle
harness upgrade --to X.Y.Z
```

- A clone made from a bundle file already has that file as `origin`; replacing the file at the
  same path is enough.
- With a `.run`: run the newer one with the same `--dest`. It fetches its tags into the
  clone, points `origin` at its bundle and runs `harness upgrade --to X.Y.Z`; pass
  `--yes --offline` (and `--config FILE` if your config is not in `local/`):

  ```sh
  sh harness-hub-X.Y.Z.run --check && sh harness-hub-X.Y.Z.run --yes --offline
  ```
- Migration notes, config validation and the plan run as usual ([upgrade runbook](upgrade.md)).

## MCP servers

The Jira MCP server starts through `uvx`, which downloads from PyPI on first use. Offline,
either pre-populate the uv cache on a connected machine with the same uv version, point uv at
an internal index (`UV_INDEX_URL`), or disable it (`jira.mcp.enabled = false`) and use the
`jira` CLI.
