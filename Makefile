# harness-hub developer loop. Every target delegates to bin/harness or tools/gate.
.PHONY: all test lint gate docs docs-generate render-check install release-check release-build

HARNESS    ?= bin/harness
CI_CONFIG  ?= tests/fixtures/harness.ci.toml
RENDER_TMP ?= $(or $(TMPDIR),/tmp)/harness-render-check
TAG        ?=
TOOLS      ?= linux/amd64,linux/arm64,darwin/amd64,darwin/arm64

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
	@rm -rf $(RENDER_TMP) && mkdir -p $(RENDER_TMP)/home
	@HOME=$(RENDER_TMP)/home $(HARNESS) render --config $(CI_CONFIG) --out $(RENDER_TMP)/r1
	@HOME=$(RENDER_TMP)/home $(HARNESS) render --config $(CI_CONFIG) --out $(RENDER_TMP)/r2
	@diff -r $(RENDER_TMP)/r1 $(RENDER_TMP)/r2 && echo "render-check: deterministic"

install:
	@pre-commit install --hook-type pre-commit --hook-type commit-msg --hook-type pre-push

# Releases (CONTRIBUTING.md "Releases"): after `git tag -a X.Y.Z`, before `git push origin X.Y.Z`.
release-check:
	@test -n "$(TAG)" || { echo "usage: make release-check TAG=X.Y.Z"; exit 2; }
	@$(HARNESS) release check $(TAG)

# The release workflow's build job, locally, into build/release (TOOLS= for an offline rehearsal).
release-build:
	@test -n "$(TAG)" || { echo "usage: make release-build TAG=X.Y.Z [TOOLS=os/arch,...]"; exit 2; }
	@$(HARNESS) pack --out build/release --tag $(TAG) $(if $(TOOLS),--tools $(TOOLS)) --self-extract
	@$(HARNESS) verify build/release/harness-hub-$(TAG).bundle
	@sh build/release/harness-hub-$(TAG).run --check
