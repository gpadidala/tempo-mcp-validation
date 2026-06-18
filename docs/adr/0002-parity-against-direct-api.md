# 0002 — Validate via semantic parity against the direct Tempo HTTP API

## Status
Accepted.

## Context
We need to prove the MCP server returns *correct* results, not just *some*
results. The MCP tools and the direct Tempo HTTP API return overlapping but
differently-shaped JSON (e.g. `get-attribute-values` returns
`{"tagValues":{"string":[...]}}` over MCP but `[{"type","value"}]` over the API;
`get-trace` returns a service-grouped shape while `/api/v2/traces` returns OTLP).

## Decision
For every data tool we also call the equivalent HTTP endpoint and assert
*semantic* equivalence — equal trace-ID sets, equal tag-value sets, equal span
counts — via normalizing helpers in `client/shapes.py`. Time-sensitive metric
values are compared structurally (same series, non-negative) rather than
bit-identically.

## Consequences
- Parity is the backbone of the suite; a tool that diverges from the API it wraps
  fails immediately.
- The normalization layer (`shapes.py`) is the single place that encodes each
  shape, so new tools only need a small extractor.
