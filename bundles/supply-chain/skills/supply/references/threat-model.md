# Supply-chain threat model

What can go wrong between a developer's intent and the code that runs, and which check covers
it. "Not covered" rows are judgement or other bundles; say so in a report.

| Threat | Example | Covered by |
|---|---|---|
| A moved tag or branch runs new code | `uses: org/action@v4` re-pointed after a compromise | `GHA001`/`GHA002`, `DKR*`, `CI006`, `CI008` (`supply pins`) |
| Unpinned dependency resolution | `flask>=2.0`, `^4.17.21`, a git branch | `PIP*`, `NPM*`, `CGO001`, `GO001` |
| Downloaded code runs unreviewed | `curl … \| sh`, a tarball without a checksum | `SH001`, `SH002`; core guard band 35 asks on a download piped into an interpreter |
| Verification switched off | `--trusted-host`, `strict-ssl false`, `GOINSECURE`, `cosign --insecure-*` | guard section 38 (deny) |
| Installs into the machine | `pip install` outside a venv, `npm i -g` | guard section 38 (ask) |
| CI token and secret abuse | `pull_request_target` checkout, `${{ github.event.issue.title }}` in `run:` | `CI003`, `CI004`, `CI005`, `CI001`, `CI002` |
| Security checks that cannot fail | `continue-on-error: true` on the scan | `CI007` |
| Known-vulnerable dependency | a CVE in a locked version | `OSV001`, `VUL001` (`supply audit`) |
| Tampered or impostor artefact | an image re-pushed under the same tag | `VER*` (`supply verify`), digests (`DKR*`) |
| Unknown contents | no SBOM, or one without versions | `SBM*` (`supply sbom lint`) |
| Untrusted registry | an image from an unreviewed host | `REG001` (`supply_chain.registries_re`) |
| Typosquatting, a malicious new release, maintainer takeover | `reqeusts`, a compromised patch release | not covered: review new dependencies by hand; pins limit the blast radius |
| Leaked credentials in the repository | a token in a workflow | the `secrets` bundle (planned), never this one |
| Image vulnerabilities and hardening | root user, outdated base | the `containers` bundle (planned) |
| Publishing and release signing | `npm publish`, `cosign sign` | the `release` bundle (planned); a human step |

Trust boundaries: the checkout (reviewed in MRs), the package registries and their mirrors,
the CI runners and their tokens, the container registries, the signing identities (Fulcio,
Rekor, GitHub). Every check above is read-only; every fix lands as a repository change.
