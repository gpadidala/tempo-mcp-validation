# Tempo MCP validation harness. One command on a fresh clone:
#   make all   ->  up + seed + discover + validate + usecases + report
#
# Python env is managed with uv (https://docs.astral.sh/uv/).
.DEFAULT_GOAL := help
SHELL := /bin/bash

UV ?= uv
RUN := $(UV) run

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

.PHONY: install
install: ## Create venv + install deps (uv)
	$(UV) sync --extra dev || $(UV) pip install -e ".[dev]"

.PHONY: env
env: ## Create .env from example if missing
	@test -f .env || (cp .env.example .env && echo "created .env")

.PHONY: up
up: env ## Start the stack (Tempo MCP-on + Prometheus + Grafana) and wait for ready
	docker compose up -d
	@echo "waiting for Tempo /ready ..."
	@for i in $$(seq 1 60); do \
		curl -sf http://localhost:3200/ready >/dev/null 2>&1 && echo "tempo ready" && break || sleep 2; \
	done
	@curl -sf http://localhost:3200/ready >/dev/null 2>&1 || (echo "tempo did not become ready" && exit 1)

.PHONY: down
down: ## Stop the stack and remove volumes
	docker compose down -v

.PHONY: ps
ps: ## Show stack status
	docker compose ps

.PHONY: logs
logs: ## Tail Tempo logs
	docker compose logs -f tempo

.PHONY: seed
seed: ## Push deterministic ground-truth traces (both tenants)
	$(RUN) python -m seed.generate_traces

.PHONY: discover
discover: ## Snapshot live MCP tools -> tools_snapshot.json
	$(RUN) python -m client.discover

.PHONY: drift
drift: ## Fail if live tool set drifts from the committed snapshot
	$(RUN) python -m client.discover --check

.PHONY: validate
validate: ## Run the pytest suite (protocol, contract, parity, negative, tenancy, security)
	$(RUN) pytest --junitxml=reports/junit.xml

.PHONY: usecases
usecases: ## Run the use-case catalog -> reports/usecases.{md,json}
	$(RUN) python -m usecases.runner

.PHONY: report
report: ## Regenerate docs/validation-matrix.md from the live server
	$(RUN) python -m usecases.runner --matrix

.PHONY: claude-add
claude-add: ## Register the Tempo MCP server with Claude Code
	claude mcp add --transport=http tempo http://localhost:3200/api/mcp

.PHONY: all
all: up seed discover validate usecases ## Full pipeline on a fresh clone

.PHONY: clean
clean: down ## Tear everything down
	rm -rf reports
