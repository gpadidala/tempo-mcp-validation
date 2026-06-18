"""TraceQL metrics — only runs if the running Tempo version exposes the tools."""

from __future__ import annotations

from client import shapes
from tests.conftest import require_tool


async def test_metrics_instant_nonempty(mcp, tool_names):
    require_tool(tool_names, "traceql-metrics-instant")
    async with mcp() as c:
        r = await c.call_tool("traceql-metrics-instant", {"query": "{} | rate()"})
    assert not shapes.is_error(r), shapes.mcp_text(r)
    values = shapes.metric_series_values(shapes.mcp_json(r))
    assert len(values) >= 1
    assert all(v >= 0 for v in values)


async def test_metrics_range_has_samples(mcp, tool_names, window):
    require_tool(tool_names, "traceql-metrics-range")
    start, end = window
    async with mcp() as c:
        r = await c.call_tool(
            "traceql-metrics-range", {"query": "{} | rate()", "start": start, "end": end}
        )
    assert not shapes.is_error(r), shapes.mcp_text(r)
    assert shapes.metric_range_sample_count(shapes.mcp_json(r)) > 0
