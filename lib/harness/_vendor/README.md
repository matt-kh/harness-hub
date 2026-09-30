# Vendored dependencies

The engine is stdlib-only. The single vendored package is used only when the standard
library lacks it.

| package | version | license | used when | source |
|---|---|---|---|---|
| `tomli/` | 2.2.1 | MIT (`tomli/LICENSE`) | python < 3.11 (no `tomllib`) | https://pypi.org/project/tomli/2.2.1/ (sdist `src/tomli/`, unmodified) |

Update: download the sdist, copy `src/tomli/*.py` and `LICENSE` here unchanged, bump the
table above, run `harness test unit`.
