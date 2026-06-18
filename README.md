# tempo-mcp-validation

Validation harness for **Grafana Tempo's native MCP server** — the MCP server
built into Tempo's `query-frontend` (Tempo OSS **≥ 2.9**), served over
streamable HTTP at `http://localhost:3200/api/mcp`.

This repo does four things and nothing more:

1. Runs **Tempo with its native MCP server enabled** (plus Prometheus + Grafana).
2. Connects an **async MCP client** to it.
3. Exercises **real tracing use cases** through the discovered MCP tools.
4. **Validates** every tool: schema contract, happy-path, parity vs the direct
   Tempo HTTP API, negative/edge cases, multi-tenant isolation, and data-egress
   security flagging.

> ⚠️ **Security note.** Enabling the Tempo MCP server *can pass trace data to an
> LLM or LLM provider.* This harness treats that as a thing to test, not a
> footnote. No real trace data is committed — only deterministic seed generators.

The **only** system under test is the native server. No third-party / standalone
Tempo MCP servers are built or used here. Tools are **discovered at runtime**
(`tools/list`) and snapshotted — never hardcoded.

## Quickstart

```bash
cp .env.example .env
make install      # uv venv + deps
make up           # Tempo (MCP on) + Prometheus + Grafana, wait for ready
make seed         # push deterministic ground-truth traces (tenant-a + tenant-b)
make discover     # snapshot live MCP tools -> tools_snapshot.json
make validate     # pytest suite
make usecases     # use-case catalog -> reports/usecases.md
```

Or everything at once on a fresh clone:

```bash
make all
```

## What's where

| Path | Purpose |
|------|---------|
| `config/tempo.yaml` | Tempo single-binary config; `query_frontend.mcp_server.enabled: true`, multi-tenancy + metrics-generator on |
| `docker-compose.yml` | Pinned stack: tempo 2.10.7, prometheus 3.5.4, grafana 12.4.4 |
| `seed/generate_traces.py` | Deterministic OTLP traces = ground truth; writes `seed/expected.json` |
| `client/mcp_client.py` | Async MCP client over streamable HTTP (sends `X-Scope-OrgID`) |
| `client/discover.py` | `tools/list` snapshot + drift detection |
| `usecases/` | Use-case catalog + runner → pass/fail report |
| `tests/` | pytest suite (protocol, contract, parity, negative, tenancy, security) |
| `docs/` | Architecture diagram, runbook, validation matrix, ADRs |

## Endpoints (when `make up` is running)

- Tempo MCP: `http://localhost:3200/api/mcp`  (needs `X-Scope-OrgID`)
- Tempo HTTP API: `http://localhost:3200`
- Grafana: `http://localhost:3000`  (anonymous admin, Explore → Tempo)
- Prometheus: `http://localhost:9090`

## Use it from Claude Code / Inspector

```bash
# Claude Code
claude mcp add --transport=http tempo http://localhost:3200/api/mcp

# MCP Inspector (manual poking)
npx @modelcontextprotocol/inspector
```

Multi-tenancy is on, so MCP calls must carry an `X-Scope-OrgID` header
(`tenant-a` is the seeded tenant).

## Status

Phase 0–1 scaffolding: stack + runtime tool discovery. Reference:
<https://grafana.com/docs/tempo/latest/api_docs/mcp-server/>
