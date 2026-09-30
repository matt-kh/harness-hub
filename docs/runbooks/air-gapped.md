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

## Fully offline

On a connected machine, download the asset named in the lock file for the target OS/arch and
check it:

```sh
jq -r '.assets["linux/amd64"] | .url, .sha256' tools/gh.lock.json
curl -fLO <url>
shasum -a 256 <file>              # must equal the lock's sha256
```

Carry the file and a clone (or `git bundle`) of the hub across, then on the offline machine:

```sh
git clone /media/usb/harness-hub.bundle ~/harness-hub
~/harness-hub/bootstrap --offline --no-install-tools
harness install gh --from /media/usb/gh_<version>_linux_amd64.tar.gz
harness doctor --offline
```

`--offline` (or `HARNESS_OFFLINE=1`) skips every check that needs the network; they show as
`SKIP`, not `FAIL`.

## Upgrading offline

`git bundle create harness-hub.bundle --all` on a connected machine, then
`git -C ~/harness-hub fetch /media/usb/harness-hub.bundle 'refs/tags/*:refs/tags/*'` and
`harness upgrade --to <tag>` (the fetch step finds nothing new and continues).

## MCP servers

The Jira MCP server starts through `uvx`, which downloads from PyPI on first use. Offline,
either pre-populate the uv cache on a connected machine with the same uv version, point uv at
an internal index (`UV_INDEX_URL`), or disable it (`jira.mcp.enabled = false`) and use the
`jira` CLI.
