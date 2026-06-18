"""Fetch traces by ID and confirm the span tree comes back intact."""

from __future__ import annotations

from client import shapes


async def test_slow_trace_full_tree(mcp, expected):
    tid = expected["tenant_a"]["slow_trace_ids"][0]
    async with mcp() as c:
        r = await c.call_tool("get-trace", {"trace_id": tid})
    assert not shapes.is_error(r), shapes.mcp_text(r)
    payload = shapes.mcp_json(r)
    assert payload["trace"]["traceId"] == tid
    assert shapes.mcp_trace_span_count(payload) == 2  # root + db child


async def test_error_trace_single_span(mcp, expected):
    tid = expected["tenant_a"]["error_trace_ids"][0]
    async with mcp() as c:
        r = await c.call_tool("get-trace", {"trace_id": tid})
    assert not shapes.is_error(r), shapes.mcp_text(r)
    payload = shapes.mcp_json(r)
    assert payload["trace"]["traceId"] == tid
    assert shapes.mcp_trace_span_count(payload) == 1


async def test_multiservice_trace_spans_services(mcp, expected):
    tid = expected["tenant_a"]["multiservice_trace_id"]
    async with mcp() as c:
        r = await c.call_tool("get-trace", {"trace_id": tid})
    assert not shapes.is_error(r), shapes.mcp_text(r)
    payload = shapes.mcp_json(r)
    services = {s["serviceName"] for s in payload["trace"]["services"]}
    assert {"frontend", "cart", "payment"} <= services
