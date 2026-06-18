# 0005 — Real multi-tenancy + legacy-flat per-tenant overrides

## Status
Accepted.

## Context
Tenant isolation must be a genuine test, not theatre, so `multitenancy_enabled:
true` is set and every request (ingest, query, and the MCP endpoint) carries
`X-Scope-OrgID`. Two configuration gotchas surfaced:

1. **`overrides.defaults` replaces built-in defaults wholesale.** Providing a
   `defaults` block zeroed Tempo's default ingestion limits, so OTLP pushes were
   rejected with `429 (limit 0 bytes/s)` until the limits were restated.
2. **The per-tenant runtime override file uses the LEGACY FLAT key format**
   (`ingestion_rate_limit_bytes`, `metrics_generator_processors`), not the nested
   structure used by `overrides.defaults`. Nested keys there fail to parse.

## Decision
- `config/tempo.yaml` restates ingestion limits explicitly under
  `overrides.defaults`.
- `config/overrides.yaml` uses legacy flat keys, and each per-tenant entry
  restates its ingestion limits (a per-tenant entry replaces, not merges).
- Tenants `tenant-a` (seeded scenarios) and `tenant-b` (disjoint, isolation only)
  diverge on metrics-generator processors to show per-tenant config is honored.

## Consequences
- `tests/test_multitenancy.py` fails for real if tenants are misconfigured.
- The two override formats are documented in-file to prevent regressions.
