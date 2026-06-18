# 0001 — Discover MCP tools at runtime, never hardcode them

## Status
Accepted.

## Context
Tempo's MCP server exposes a set of tools (`traceql-search`, `get-trace`,
`get-attribute-names`, `get-attribute-values`, `traceql-metrics-instant`,
`traceql-metrics-range`, `docs-traceql` at the time of writing). The docs do not
exhaustively enumerate them and the set changes across Tempo versions. Hardcoding
the list would make the harness lie when run against a version that exposes more
or fewer tools.

## Decision
The harness calls MCP `tools/list` at runtime, snapshots the tools and their JSON
schemas to `tools_snapshot.json`, and builds its validation matrix and
required-arg contract checks from that live snapshot. `client/discover.py --check`
drift-detects any change (added/removed tools, changed schemas) and fails CI.

## Consequences
- The validation matrix (`docs/validation-matrix.md`) is generated, not written.
- A new Tempo version that adds a tool surfaces as a coverage gap (flagged in the
  matrix) rather than silently passing.
- The committed snapshot is the regression baseline; intentional changes require
  re-running `make discover` and committing the new snapshot.
