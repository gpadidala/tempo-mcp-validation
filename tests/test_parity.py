"""Parity: each MCP tool's result is semantically equivalent to the direct
Tempo HTTP API result for the same query. This is the backbone of the suite —
it proves the MCP server faithfully wraps the API rather than diverging.
"""

from __future__ import annotations

from client import shapes
from tests.conftest import require_tool


async def test_search_parity(mcp, api, window):
    start, end = window
    query = '{ resource.service.name = "checkout" }'
    async with mcp() as c:
        mcp_r = await c.call_tool("traceql-search", {"query": query, "start": start, "end": end})
    mcp_ids = shapes.search_trace_ids(shapes.mcp_json(mcp_r))
    api_ids = shapes.search_trace_ids(await api.search(query, start, end))
    assert mcp_ids == api_ids, f"MCP {sorted(mcp_ids)} != API {sorted(api_ids)}"
    assert mcp_ids, "expected a non-empty result for this parity check"


async def test_trace_parity(mcp, api, expected):
    tid = expected["tenant_a"]["slow_trace_ids"][0]
    async with mcp() as c:
        mcp_payload = shapes.mcp_json(await c.call_tool("get-trace", {"trace_id": tid}))
    api_payload = await api.trace_by_id(tid)
    assert mcp_payload["trace"]["traceId"] == tid
    assert shapes.mcp_trace_span_count(mcp_payload) == shapes.otlp_trace_span_count(api_payload)


async def test_tag_names_parity(mcp, api):
    async with mcp() as c:
        mcp_map = shapes.tag_names_by_scope(
            shapes.mcp_json(await c.call_tool("get-attribute-names", {})))
    api_map = shapes.tag_names_by_scope(await api.tag_names())
    for scope in ("resource", "span"):
        assert mcp_map.get(scope, set()) == api_map.get(scope, set()), f"scope {scope} differs"


async def test_tag_values_parity(mcp, api):
    name = "resource.service.name"
    async with mcp() as c:
        mcp_vals = shapes.tag_values(
            shapes.mcp_json(await c.call_tool("get-attribute-values", {"name": name})))
    api_vals = shapes.tag_values(await api.tag_values(name))
    assert mcp_vals == api_vals, f"MCP {sorted(mcp_vals)} != API {sorted(api_vals)}"


async def test_metrics_instant_parity(mcp, api, tool_names):
    require_tool(tool_names, "traceql-metrics-instant")
    query = "{} | rate()"
    async with mcp() as c:
        mcp_json = shapes.mcp_json(await c.call_tool("traceql-metrics-instant", {"query": query}))
    api_json = await api.metrics_instant(query)
    mcp_vals = shapes.metric_series_values(mcp_json)
    api_vals = shapes.metric_series_values(api_json)
    # Same query, same shape: equal series count; values are time-sensitive so
    # assert both are present and non-negative rather than bit-identical.
    assert len(mcp_vals) == len(api_vals) >= 1
    assert all(v >= 0 for v in mcp_vals + api_vals)
