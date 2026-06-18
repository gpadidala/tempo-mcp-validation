"""Tag-name and tag-value discovery against seeded ground truth."""

from __future__ import annotations

from client import shapes


async def test_attribute_names_include_service(mcp, expected):
    async with mcp() as c:
        r = await c.call_tool("get-attribute-names", {})
    assert not shapes.is_error(r), shapes.mcp_text(r)
    by_scope = shapes.tag_names_by_scope(shapes.mcp_json(r))
    assert "service.name" in by_scope.get("resource", set())
    span_tags = by_scope.get("span", set())
    assert {"http.status_code", "promo.code"} <= span_tags


async def test_service_name_values_cover_all_services(mcp, expected):
    a = expected["tenant_a"]
    async with mcp() as c:
        r = await c.call_tool("get-attribute-values", {"name": "resource.service.name"})
    assert not shapes.is_error(r), shapes.mcp_text(r)
    values = shapes.tag_values(shapes.mcp_json(r))
    assert set(a["services"]) <= values


async def test_unique_attribute_value_discoverable(mcp, expected):
    uniq = expected["tenant_a"]["unique_attr"]
    async with mcp() as c:
        r = await c.call_tool("get-attribute-values", {"name": f"span.{uniq['key']}"})
    assert not shapes.is_error(r), shapes.mcp_text(r)
    values = shapes.tag_values(shapes.mcp_json(r))
    assert uniq["value"] in values
