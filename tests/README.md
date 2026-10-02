# Engine tests

| path | what | run |
|---|---|---|
| `unit/test_*.py` | engine unit tests (stdlib `unittest`, python 3.9+), each in a throw-away `$HOME` against a copy of `fixtures/bundles` | `bin/harness test unit` or `PYTHONPATH=lib python3 -m unittest discover -s tests/unit` |
| `fixtures/bundles/{core,alpha,beta}` | minimal bundles exercising every manifest feature: depends_on, any_of, conflicts_with, recommends, deprecated `hook_rules`, skill fragments, MCP `env_files`, bin links, a tiny guard engine + sections | used by the unit tests (`HARNESS_BUNDLES_ROOT`) |
| `fixtures/manifests/*.bundle.toml` | the two worked examples from the bundle design, validated against `schema/bundle.schema.json` | `unit/test_schema.py` |
| `fixtures/harness.fixture.toml` | config for the fixture bundles | unit tests |
| `fixtures/harness.ci.toml` | public-placeholder config for CI and the smoke tests | `smoke/*.sh` |
| `fakes/bin/*` | fake `claude gemini copilot codex gh glab kubectl jira` with deterministic `--version` / `auth status` output | put first on `PATH` |
| `smoke/bootstrap.sh` | newcomer first run in a temp `HOME`: bootstrap, settings merge, hook fails closed and denies a credential read, `doctor --offline` rc 0, second apply `0 changes`, nothing written outside managed paths | `bin/harness test smoke` |
| `smoke/render-determinism.sh` | two renders of every provider are byte-identical | `bin/harness test smoke` |
| `smoke/pack.sh` | distribution: snapshot the working tree into a temp repo, `harness pack`, `harness verify` (and a tampered `SHA256SUMS` fails), a dirty tree is refused, `bootstrap --from <bundle>` into a temp HOME, the installed hub's `doctor --offline` rc 0 | `bin/harness test smoke` |
| `unit/test_pack.py`, `unit/test_deps.py`, `unit/test_harness_section.py` | pack/verify/`bootstrap --from`/offline `upgrade --to`; stdlib-only imports and the shell binary scanner; `[harness]` schema, lint pairing and guard-reason checks, generated coverage docs | `bin/harness test unit` |

`bin/harness test` also discovers `bundles/core/guard/tests/run.sh` (with `GUARD_BASH` set to a
guard concatenated from every bundle), `bundles/*/tests/run.sh`,
`bundles/*/skills/*/scripts/tests/run.sh` and `providers/*/tests/run.sh`.
Set `HARNESS_TEST_VERBOSE=1` to see command output inside unit tests. Unit and smoke tests set
`HARNESS_BUILD_DIR` to a temp directory, so a live hub's `build/config.json` is never rewritten.
