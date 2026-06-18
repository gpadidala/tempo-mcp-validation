"""Happy-path TraceQL search against seeded ground truth."""

from __future__ import annotations

from client import shapes


async def _search(c, query, window):
    start, end = window
    r = await c.call_tool("traceql-search", {"query": query, "start": start, "end": end})
    assert not shapes.is_error(r), shapes.mcp_text(r)
    return shapes.search_trace_ids(shapes.mcp_json(r))


async def test_slow_requests(mcp, expected, window):
    a = expected["tenant_a"]
    async with mcp() as c:
        ids = await _search(c, '{ resource.service.name = "checkout" && duration > 1s }', window)
    assert ids == set(a["slow_trace_ids"])
    assert a["error_trace_ids"][0] not in ids  # the 120ms error trace is faster


async def test_errors(mcp, expected, window):
    a = expected["tenant_a"]
    async with mcp() as c:
        ids = await _search(c, "{ status = error }", window)
    assert ids == set(a["error_trace_ids"])


async def test_service_filter_frontend(mcp, expected, window):
    a = expected["tenant_a"]
    async with mcp() as c:
        ids = await _search(c, '{ resource.service.name = "frontend" }', window)
    assert ids == set(a["frontend_trace_ids"])
    assert len(ids) == a["frontend_trace_count"]


async def test_unique_attribute_span(mcp, expected, window):
    a = expected["tenant_a"]
    uniq = a["unique_attr"]
    async with mcp() as c:
        ids = await _search(c, f'{{ span.{uniq["key"]} = "{uniq["value"]}" }}', window)
    assert ids == {uniq["trace_id"]}


async def test_empty_result_is_clean(mcp, window):
    start, end = window
    async with mcp() as c:
        r = await c.call_tool(
            "traceql-search",
            {"query": '{ resource.service.name = "no-such-service-xyz" }', "start": start, "end": end},
        )
    assert not shapes.is_error(r), "a no-match query must not be an error"
    assert shapes.search_trace_ids(shapes.mcp_json(r)) == set()
