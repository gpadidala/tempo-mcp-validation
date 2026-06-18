"""Per-tool schema contract: tools/list advertises valid JSON Schema, and
required arguments are actually enforced by the server."""

from __future__ import annotations

import pytest

from client import shapes

# Minimal call that omits every required arg, per tool, to prove enforcement.
EMPTY_CALL: dict[str, dict] = {
    "traceql-search": {},
    "get-trace": {},
    "get-attribute-values": {},
    "traceql-metrics-instant": {},
    "traceql-metrics-range": {},
    "docs-traceql": {},
}


def test_every_tool_has_valid_schema(tools):
    for t in tools:
        schema = t["inputSchema"]
        assert isinstance(schema, dict), f"{t['name']} schema must be an object"
        assert schema.get("type") == "object", f"{t['name']} schema type must be 'object'"
        props = schema.get("properties", {})
        assert isinstance(props, dict)
        # required (if present) must reference declared properties
        for req in schema.get("required", []):
            assert req in props, f"{t['name']}: required arg '{req}' not in properties"


async def test_required_args_enforced(mcp, tools):
    """For each tool with required args, an empty call must fail (isError/exc)."""
    checked = 0
    async with mcp() as c:
        for t in tools:
            required = t["inputSchema"].get("required", [])
            if not required:
                continue
            checked += 1
            args = EMPTY_CALL.get(t["name"], {})
            failed = False
            try:
                result = await c.call_tool(t["name"], args)
                failed = shapes.is_error(result)
            except Exception:  # noqa: BLE001
                failed = True
            assert failed, f"{t['name']} accepted a call missing required args {required}"
    assert checked > 0, "expected at least one tool with required args"
