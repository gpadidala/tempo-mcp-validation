"""MCP protocol basics: initialize, capabilities, tools/list, error envelopes."""

from __future__ import annotations

import pytest

from client import shapes


async def test_initialize_reports_server_info(mcp):
    async with mcp() as c:
        info = c.init_result.serverInfo
        assert info.name, "server must report a name"
        assert info.version, "server must report a version"
        assert c.init_result.protocolVersion, "server must report a protocol version"


async def test_capabilities_include_tools(mcp):
    async with mcp() as c:
        assert c.init_result.capabilities.tools is not None, "must advertise tools capability"


async def test_tools_list_nonempty(mcp):
    async with mcp() as c:
        tools = await c.list_tools()
    assert len(tools) >= 1
    for t in tools:
        assert t.name
        assert isinstance(t.inputSchema, dict)


async def test_unknown_tool_is_error(mcp):
    """Calling a tool that doesn't exist yields an error, not a crash."""
    failed = False
    try:
        async with mcp() as c:
            result = await c.call_tool("definitely-not-a-real-tool", {})
        failed = shapes.is_error(result)
    except Exception:  # noqa: BLE001 — SDK may raise instead of returning isError
        failed = True
    assert failed, "unknown tool should produce an error envelope or exception"


async def test_docs_tool_returns_text_if_present(mcp, tool_names):
    if "docs-traceql" not in tool_names:
        pytest.skip("docs-traceql not exposed")
    async with mcp() as c:
        result = await c.call_tool("docs-traceql", {"name": "intro"})
    assert not shapes.is_error(result)
    assert shapes.mcp_text(result).strip(), "docs tool should return non-empty text"
