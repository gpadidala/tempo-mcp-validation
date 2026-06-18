"""Security posture of the native MCP server.

Two things are asserted here:

1. DATA EGRESS FLAG. Enabling the MCP server means raw trace payloads — span
   names, attribute values, etc. — are returned over the MCP path and therefore
   to whatever LLM/LLM-provider is driving it. We prove this concretely: a
   sensitive seeded attribute value comes back in plaintext. This test PASSING
   is the warning: treat trace contents as exposed to the LLM boundary.

2. AUTH / TENANCY ENFORCEMENT. With multi-tenancy enabled there is no anonymous
   read path — a request with no X-Scope-OrgID is rejected outright, and a
   different tenant cannot read the seeded tenant's data (isolation *is* the
   authorization boundary on the MCP transport, which always sends a header).
"""

from __future__ import annotations

import os

import httpx

from client import shapes
from client.mcp_client import TempoMCPClient

API_URL = os.environ.get("TEMPO_API_URL", "http://localhost:3200")


async def test_trace_payload_egresses_to_mcp_path(mcp, expected, window):
    """FLAG: sensitive trace data is exposed in plaintext through the MCP tools."""
    start, end = window
    uniq = expected["tenant_a"]["unique_attr"]
    async with mcp() as c:
        r = await c.call_tool(
            "traceql-search",
            {"query": f'{{ span.{uniq["key"]} = "{uniq["value"]}" }}', "start": start, "end": end},
        )
        ids = shapes.search_trace_ids(shapes.mcp_json(r))
        values = shapes.tag_values(shapes.mcp_json(
            await c.call_tool("get-attribute-values", {"name": f"span.{uniq['key']}"})))
    # Retrievable by the value AND readable back in plaintext == data egress.
    assert uniq["trace_id"] in ids
    assert uniq["value"] in values, "sensitive attribute value is readable over MCP (data egress)"


def test_direct_api_rejects_missing_org_id():
    """No anonymous read: the API path the MCP server shares requires a tenant."""
    r = httpx.get(f"{API_URL}/api/search", params={"q": "{ }"}, timeout=10)
    assert r.status_code != 200, "request without X-Scope-OrgID must be rejected"
    assert "org id" in r.text.lower() or r.status_code in (401, 403)


async def test_foreign_tenant_cannot_read_seeded_data(expected, window):
    """A client presenting an unknown tenant sees none of tenant-a's traces —
    the tenant header is the authorization boundary, not a formality."""
    start, end = window
    async with TempoMCPClient(tenant="intruder-tenant") as c:
        r = await c.call_tool(
            "traceql-search",
            {"query": '{ resource.service.name = "checkout" }', "start": start, "end": end},
        )
    assert not shapes.is_error(r)
    assert shapes.search_trace_ids(shapes.mcp_json(r)) == set(), "foreign tenant must see nothing"
