# Validation matrix

> Generated from the live MCP server by `usecases/runner.py --matrix`. Do not hand-edit.

Server: `tempo 0.1.0` · protocol `2025-06-18` · 7 tool(s) discovered.

## Tools → Tempo HTTP API (parity map)

| Tool | Wraps | Required args |
|------|-------|---------------|
| `docs-traceql` | `(static docs — no data API)` | name |
| `get-attribute-names` | `GET /api/v2/search/tags` | — |
| `get-attribute-values` | `GET /api/v2/search/tag/{name}/values` | name |
| `get-trace` | `GET /api/v2/traces/{id}` | trace_id |
| `traceql-metrics-instant` | `GET /api/metrics/query` | query |
| `traceql-metrics-range` | `GET /api/metrics/query_range` | query |
| `traceql-search` | `GET /api/search` | query |

## Coverage per tool × dimension

| Tool | Schema | Happy | Parity | Negative | Multi-tenancy | Security |
|------|--------|-------|--------|----------|---------------|----------|
| `docs-traceql` | test_tools_contract.py | test_protocol.py | n/a (static) | test_negative.py | n/a | n/a |
| `get-attribute-names` | test_tools_contract.py | uc discover-queryable | test_parity.py::tags | test_negative.py::bad_scope | test_multitenancy.py | test_security.py |
| `get-attribute-values` | test_tools_contract.py | uc discover-queryable | test_parity.py::tag_values | test_negative.py | test_multitenancy.py | test_security.py |
| `get-trace` | test_tools_contract.py | uc trace-by-id | test_parity.py::trace | test_negative.py::missing_id | test_multitenancy.py | test_security.py |
| `traceql-metrics-instant` | test_tools_contract.py | uc traceql-metrics | test_parity.py::metrics | test_negative.py | test_multitenancy.py | test_security.py |
| `traceql-metrics-range` | test_tools_contract.py | test_traceql_metrics.py | test_parity.py::metrics_range | test_negative.py | test_multitenancy.py | test_security.py |
| `traceql-search` | test_tools_contract.py | uc find-slow / find-errors | test_parity.py::search | test_negative.py / uc bad-input | test_multitenancy.py / uc tenant-isolation | test_security.py |

