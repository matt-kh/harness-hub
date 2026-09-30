# Reference: config schema

Every key `local/harness.toml` accepts, with its type, default, description, the bundles that
need it and deprecation status. Generated from `schema/harness-config.schema.json` compiled with
every bundle's `[requires.config]`; do not edit inside the generated region.

Layering and precedence: [concepts](../concepts.md#config-the-single-source-of-truth). Explain one
key on your machine, including which layer set it: `harness config explain <key>`.

<!-- generated:begin source=schema/harness-config.schema.json -->
<!-- generated:end -->
