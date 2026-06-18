# 0004 — MCP clients as factory fixtures, not pre-connected ones

## Status
Accepted.

## Context
The MCP streamable-HTTP transport holds an anyio task group. A conventional
async-generator pytest fixture (`async with ... as c: yield c`) enters that task
group during fixture *setup* and exits it during *teardown* — which pytest-asyncio
runs in different tasks. anyio rejects this with
`RuntimeError: Attempted to exit cancel scope in a different task than it was entered`.
Every test using a pre-connected client fixture errored on teardown.

## Decision
Fixtures (`mcp`, `mcp_b`) return a zero-arg *factory*. Each test opens and closes
the client inside its own task:

```python
async def test_x(mcp):
    async with mcp() as c:
        ...
```

So `__aenter__` and `__aexit__` of the transport run in the same task.

## Consequences
- One connection per test (acceptable; connect is cheap and the suite is fast).
- Test bodies are explicit about the client lifecycle.
- Also documents per-tenant usage cleanly (`async with mcp() as a, mcp_b() as b`).
