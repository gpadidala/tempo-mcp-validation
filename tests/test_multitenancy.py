"""Multi-tenancy: X-Scope-OrgID isolation. tenant-a must not read tenant-b's
traces and vice versa. This test genuinely fails if tenants are misconfigured.
"""

from __future__ import annotations

from client import shapes


async def _search(c, query, window):
    start, end = window
    r = await c.call_tool("traceql-search", {"query": query, "start": start, "end": end})
    assert not shapes.is_error(r), shapes.mcp_text(r)
    return shapes.search_trace_ids(shapes.mcp_json(r))


async def test_tenant_a_cannot_see_tenant_b(mcp, window):
    async with mcp() as c:  # billing exists only in tenant-b
        ids = await _search(c, '{ resource.service.name = "billing" }', window)
    assert ids == set(), "tenant-a must not see tenant-b's billing traces"


async def test_tenant_b_sees_only_its_own(mcp_b, expected, window):
    b = expected["tenant_b"]
    async with mcp_b() as c:
        ids = await _search(c, '{ resource.service.name = "billing" }', window)
    assert ids == set(b["all_trace_ids"])


async def test_tenant_b_cannot_see_tenant_a(mcp_b, window):
    async with mcp_b() as c:  # checkout exists only in tenant-a
        ids = await _search(c, '{ resource.service.name = "checkout" }', window)
    assert ids == set(), "tenant-b must not see tenant-a's checkout traces"


async def test_tag_values_are_tenant_scoped(mcp, mcp_b):
    async with mcp() as c:
        a_vals = shapes.tag_values(shapes.mcp_json(
            await c.call_tool("get-attribute-values", {"name": "resource.service.name"})))
    async with mcp_b() as c:
        b_vals = shapes.tag_values(shapes.mcp_json(
            await c.call_tool("get-attribute-values", {"name": "resource.service.name"})))
    assert "checkout" in a_vals and "checkout" not in b_vals
    assert "billing" in b_vals and "billing" not in a_vals
