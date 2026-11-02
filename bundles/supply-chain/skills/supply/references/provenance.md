# Provenance and signatures (`supply verify`)

A signature says *who* published an artefact; a provenance attestation says *how* it was built
(source repository, commit, workflow, builder). Verify both against an identity you chose in
advance — never against whatever the artefact claims.

## What `supply verify` runs

| Target | Mode | Command (read-only) |
|---|---|---|
| image (`oci://REF` or a reference not on disk) | keyless | `cosign verify --output json --certificate-identity-regexp RE --certificate-oidc-issuer URL [--trusted-root F] [--offline] IMAGE` |
| image | key | `cosign verify --output json --key F IMAGE` |
| image | attestation | `cosign verify-attestation --output json [--type T] … IMAGE` |
| file (blob) | keyless or key | `cosign verify-blob --bundle B … FILE` (a Sigstore bundle is required: cosign v3 verifies blobs from bundles) |
| image or file | GitHub | `gh attestation verify FILE\|oci://IMAGE (-R OWNER/REPO \| -o OWNER) --format json [--predicate-type URI] [--custom-trusted-root F]` |

The identity comes from `--identity NAME` (a `[[supply_chain.identities]]` entry: `name`,
`identity_re`, `issuer`, optional `match_re`), from `--identity RE --issuer URL`, or — without
`--identity` — from the first entry whose `match_re` matches the target. With none, the
command exits 2 and names the fix. Keyless GitHub Actions signatures use the issuer
`https://token.actions.githubusercontent.com` and an identity such as
`^https://github\.com/OWNER/REPO/\.github/workflows/release\.yml@refs/tags/v.*$`: anchor it,
name the workflow file, and restrict the ref.

| Rule | Severity | Matches | Fix |
|---|---|---|---|
| VER000 | info | the signature or attestation verified; `data.signatures` / `data.attestations` list subject, digest, issuer, identity, predicate type and builder | none |
| VER001 | warn | the verified signature or attestation names another repository than the target | verify the image you will run, by digest, against its own signature |

Exit 2 `unverifiable: <first stderr line>` is a finding: no matching signature, a wrong
identity or issuer, no attestation, a registry that refused the read. Report it; never retry
with `--insecure-ignore-tlog`, `--insecure-ignore-sct`, `--allow-insecure-registry` or a looser
regexp (the guard denies the flags). `--offline` needs `--trusted-root` (exit 3 otherwise).

## SLSA in one table

| Level | Build provenance | What it proves | How to get there |
|---|---|---|---|
| L1 | exists | the build is documented | any provenance generator |
| L2 | signed by a hosted builder | provenance cannot be forged after the fact | GitHub artifact attestations, `actions/attest-build-provenance` |
| L3 | hardened, isolated builder | the build itself resisted tampering | reusable workflows on hosted runners with isolated signing |

Signing and attesting are release steps a human (or the release pipeline) runs:
`cosign sign`, `cosign attest`, `gh attestation` creation. The agent proposes them in a
release workflow change; it never runs them (the guard asks).
