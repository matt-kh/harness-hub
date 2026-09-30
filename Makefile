# harness-hub developer loop. Every target delegates to bin/harness or tools/gate.
.PHONY: all test lint gate docs docs-generate render-check install

HARNESS    ?= bin/harness
CI_CONFIG  ?= tests/fixtures/harness.ci.toml
RENDER_TMP ?= $(or $(TMPDIR),/tmp)/harness-render-check

all: lint test gate docs

test:
	@$(HARNESS) test

lint:
	@$(HARNESS) lint
	@tools/gate/check-links.sh

gate:
	@tools/gate/private-ids.sh
	@tools/gate/tests/selftest.sh

docs:
	@$(HARNESS) docs check

docs-generate:
	@$(HARNESS) docs generate

render-check:
	@rm -rf $(RENDER_TMP) && mkdir -p $(RENDER_TMP)/h1 $(RENDER_TMP)/h2
	@HOME=$(RENDER_TMP)/h1 $(HARNESS) render --config $(CI_CONFIG) --out $(RENDER_TMP)/r1
	@HOME=$(RENDER_TMP)/h2 $(HARNESS) render --config $(CI_CONFIG) --out $(RENDER_TMP)/r2
	@diff -r $(RENDER_TMP)/r1 $(RENDER_TMP)/r2 && echo "render-check: deterministic"

install:
	@pre-commit install --hook-type pre-commit --hook-type commit-msg --hook-type pre-push
