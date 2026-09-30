# Reference: secrets

Where every credential used by an active bundle lives, which tool writes it, the file mode it
should have and how to rotate it. Generated from every bundle's `[requires.secrets]`; do not edit
inside the generated region.

The hub never reads, copies or prints these files, and `harness.toml` must never contain a
secret: validation rejects keys named `*token*`, `*secret*`, `*password*`, `*bearer*` and long
high-entropy values. MCP servers receive tokens by **file reference** (`env_files`), resolved when
the provider starts the server; naming the path in config is not a leak.

<!-- generated:begin source=bundles/*/bundle.toml -->
<!-- generated:end -->
