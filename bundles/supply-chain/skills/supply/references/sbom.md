# SBOMs (`supply sbom`, `supply sbom lint`)

An SBOM lists what an artefact contains so a vulnerability feed can be matched against it
later. Generate it from the built artefact (an image) or a checkout with lockfiles; a
manifest with version ranges produces an SBOM without versions.

- `supply sbom DIR|IMAGE [--format spdx-json|cyclonedx-json] [--out F] [--force]` runs
  `syft scan dir:DIR|registry:IMAGE -o FORMAT -q` with `SYFT_CHECK_FOR_APP_UPDATE=false` (never
  the docker daemon, never syft's update check), lints the
  document and writes it with sorted keys to `--out`. The written SBOM gets **token-shape**
  redaction only — AWS keys, JWTs, PEM private keys, URL credentials (`://***:***@`) and
  `supply_chain.redact_extra_re` — so CPEs, authors, suppliers and licence texts stay intact;
  the summary printed without `--out` is redacted in full (key names too). `--out` creates the
  file exclusively (an existing file or symlink exits 1 unless `--force`, which replaces it
  atomically and keeps its mode); a missing parent directory exits 2 before syft runs. `syft`
  missing → exit 2 with `harness install syft`.
- Package counts, the summary and SBM006-SBM008 leave out what the SBOM describes rather than
  contains: SPDX packages whose SPDXID starts `SPDXRef-DocumentRoot-` (syft's scanned directory or
  image) and CycloneDX components of `"type": "file"` (the manifests syft read, by absolute path).
- `supply sbom lint FILE` checks an SPDX or CycloneDX JSON document offline; a file that is not
  JSON exits 3 (tag-value and XML are out of scope).
- `supply audit DIR --sbom F` audits an SBOM with osv-scanner; it must be named
  `*.spdx.json`, `*.cdx.json` or `bom.json`.

| Rule | Severity | Matches | Fix |
|---|---|---|---|
| SBM001 | crit | JSON with neither `spdxVersion` nor `bomFormat: CycloneDX` | generate the SBOM with a real tool |
| SBM002 | warn | missing required top-level fields — SPDX: `spdxVersion`, `dataLicense`, `SPDXID`, `name`, `documentNamespace`, `creationInfo`, `packages`; CycloneDX: `bomFormat`, `specVersion`, `version`, `metadata`, `components` | regenerate |
| SBM003 | info | spec version other than `SPDX-2.2`/`SPDX-2.3` or CycloneDX `1.4`–`1.7` | regenerate with SPDX 2.3 or CycloneDX 1.5-1.7 |
| SBM004 | warn | no creation timestamp (`creationInfo.created`, `metadata.timestamp`) | regenerate |
| SBM005 | warn | no generating tool (`Tool:` creator, `metadata.tools`) | regenerate with a tool that records itself |
| SBM006 | warn | zero packages or components | check the scan target |
| SBM007 | info | packages without a version (count) | generate from lockfiles or the built artefact |
| SBM008 | info | packages without a purl (count) | regenerate with purls |
| SBM009 | info | no `DESCRIBES` relationship / `documentDescribes` (SPDX) or `metadata.component` (CycloneDX) | record what the SBOM describes |

Publishing or uploading an SBOM, licence policy and SBOM diffing are not part of this bundle.
