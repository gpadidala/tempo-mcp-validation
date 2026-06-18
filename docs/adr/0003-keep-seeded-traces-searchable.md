# 0003 — Keep seeded traces searchable for the whole session

## Status
Accepted.

## Context
Two Tempo behaviors broke a naive seed→validate loop:
1. **Search indexing lags ingest by ~20–30s.** Traces are fetchable by ID almost
   immediately, but TraceQL search/tag discovery only sees them after indexing.
2. **Flushed traces can disappear from search.** With a short
   `ingester.complete_block_timeout`, completed blocks leave the ingester before
   the backend blocklist poll (default 5m) picks them up — a window where seeded
   data is neither in the ingester nor in the searchable blocklist.

The first cut of `tempo.yaml` used `complete_block_timeout: 10s`, which made
seeded traces vanish a few minutes after seeding and produced flaky failures.

## Decision
- `seed/generate_traces.py` blocks until a known seeded trace is search-indexed
  (polls `/api/search`) before returning, so `make seed && make validate` is
  reliable.
- `tempo.yaml` keeps completed blocks resident (`complete_block_timeout: 1h`,
  `max_block_duration: 30m`) and polls the blocklist every `1m`, so seeded data
  stays searchable for the entire dev session.

## Consequences
- Slightly higher ingester memory use — negligible for the tiny seed set.
- Deterministic, non-flaky validation runs on a fresh clone.
