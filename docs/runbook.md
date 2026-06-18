# Runbook

Operational guide for the Tempo native MCP server validation harness.

## Prerequisites

- Docker + Docker Compose (the `grafana/tempo` image is distroless — no shell)
- Python 3.11+ and [`uv`](https://docs.astral.sh/uv/)
- `claude` CLI (optional, for the manual E2E path)
- `npx` (optional, for MCP Inspector)

## One-command path

```bash
cp .env.example .env
make install
make all          # up + seed + discover + validate + usecases
```

`make all` brings up Tempo (MCP on) + Prometheus + Grafana, seeds deterministic
traces (blocking until they are search-indexed), snapshots the live tool set,
runs the pytest suite, and runs the use-case catalog.

## Step-by-step

| Step | Command | What it does |
|------|---------|--------------|
| Start stack | `make up` | Compose up; polls `:3200/ready` from the host |
| Seed | `make seed` | Pushes ground-truth traces (tenant-a + tenant-b); waits for searchability |
| Discover | `make discover` | `tools/list` → `tools_snapshot.json` |
| Validate | `make validate` | pytest suite → `reports/junit.xml` |
| Use cases | `make usecases` | Catalog → `reports/usecases.{md,json}` + matrix |
| Drift check | `make drift` | Fails if live tool set ≠ committed snapshot |
| Tear down | `make down` | Compose down + remove volumes |

## Endpoints

| Service | URL | Notes |
|---------|-----|-------|
| Tempo MCP | `http://localhost:3200/api/mcp` | streamable HTTP; needs `X-Scope-OrgID` |
| Tempo API | `http://localhost:3200` | direct HTTP API (parity oracle) |
| Grafana | `http://localhost:3000` | anon admin → Explore → Tempo |
| Prometheus | `http://localhost:9090` | metrics-generator remote-write target |

## Manual E2E with Claude Code

```bash
make up && make seed
claude mcp add --transport=http tempo http://localhost:3200/api/mcp
# Then ask, e.g.: "find traces slower than 1s in checkout"
# Capture the transcript as evidence under docs/ (see ACCEPTANCE in README).
```

Note: with multi-tenancy on, you must supply `X-Scope-OrgID: tenant-a`. If your
client can't set headers, use Grafana Explore (the datasource pins the header).

## MCP Inspector

```bash
npx @modelcontextprotocol/inspector
# transport: streamable HTTP, URL http://localhost:3200/api/mcp
# add header X-Scope-OrgID: tenant-a
```

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `429` on seed | Distributor ring still warming up | The seeder retries with backoff; just wait |
| Empty search results right after seed | Search indexing lags ingest ~20–30s | `make seed` already blocks on searchability |
| Seeded traces vanish minutes later | `complete_block_timeout` too short vs blocklist poll | Fixed in `tempo.yaml` (kept resident + 1m poll) |
| `no org id` from the API | Missing `X-Scope-OrgID` header | Add the tenant header (multi-tenancy is on) |
| Tempo container "unhealthy" | Distroless image can't run an HTTP healthcheck | Expected — readiness is gated host-side on `/ready` |
| Tool drift CI failure | Tempo version changed the tool set | Review the diff; re-run `make discover` and commit if intended |

## Proving the tenant-isolation test bites

Point the secondary tenant at the same data (misconfiguration) and the
isolation tests must fail. For example, temporarily seed `billing` into
`tenant-a` as well, re-run `make validate`, and confirm
`tests/test_multitenancy.py` goes red. Revert afterward.
