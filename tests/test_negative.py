"""Negative / edge cases: malformed input must produce clean error envelopes or
empty results, never a crash, and the session must stay usable afterwards."""

from __future__ import annotations

from client import shapes


async def test_malformed_traceql_is_error(mcp):
    async with mcp() as c:
        r = await c.call_tool("traceql-search", {"query": "{ this is not valid"})
        assert shapes.is_error(r), "malformed TraceQL must be an error envelope"
        r2 = await c.call_tool("get-attribute-names", {})  # session stays usable
        assert not shapes.is_error(r2)


async def test_inverted_time_window_does_not_crash(mcp, window):
    start, end = window
    # end before start — must not crash. Tempo returns a clean empty result here.
    async with mcp() as c:
        r = await c.call_tool("traceql-search", {"query": "{ }", "start": end, "end": start})
    if not shapes.is_error(r):
        # parseable, and (observed) empty — the point is no transport crash
        shapes.search_trace_ids(shapes.mcp_json(r))


async def test_get_trace_missing_id(mcp):
    """A well-formed but non-existent trace ID yields an error/empty, not a crash."""
    missing = "a" * 32
    async with mcp() as c:
        r = await c.call_tool("get-trace", {"trace_id": missing})
    if not shapes.is_error(r):
        assert shapes.mcp_trace_span_count(shapes.mcp_json(r)) == 0


async def test_bad_attribute_scope_is_handled(mcp):
    """An unknown scope must not crash the server."""
    async with mcp() as c:
        r = await c.call_tool("get-attribute-names", {"scope": "not-a-real-scope"})
    if not shapes.is_error(r):
        shapes.tag_names_by_scope(shapes.mcp_json(r))  # parses without raising


async def test_session_survives_a_burst_of_bad_calls(mcp):
    async with mcp() as c:
        for _ in range(3):
            await c.call_tool("traceql-search", {"query": "}{ broken"})
        good = await c.call_tool("get-attribute-names", {})
    assert not shapes.is_error(good), "session must recover after repeated bad calls"
