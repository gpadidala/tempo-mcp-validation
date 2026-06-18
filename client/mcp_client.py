"""Async MCP client for Tempo's native MCP server over streamable HTTP.

Thin, reusable wrapper around the official `mcp` Python SDK. Every call carries
the X-Scope-OrgID header because the stack runs with multi-tenancy enabled and
the MCP endpoint honors the same tenancy as the rest of the Tempo API.

Usage:
    async with TempoMCPClient(tenant="tenant-a") as c:
        tools = await c.list_tools()
        result = await c.call_tool("traceql-search", {"query": '{ }'})
"""

from __future__ import annotations

import os
from contextlib import AsyncExitStack
from typing import Any

import structlog
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

log = structlog.get_logger()

DEFAULT_MCP_URL = os.environ.get("TEMPO_MCP_URL", "http://localhost:3200/api/mcp")


class TempoMCPClient:
    """Connect, initialize, and drive the Tempo MCP server for one tenant."""

    def __init__(self, url: str | None = None, tenant: str | None = None) -> None:
        self.url = url or DEFAULT_MCP_URL
        self.tenant = tenant or os.environ.get("TENANT_PRIMARY", "tenant-a")
        self._stack: AsyncExitStack | None = None
        self.session: ClientSession | None = None
        self.init_result: Any = None

    @property
    def headers(self) -> dict[str, str]:
        # X-Scope-OrgID selects the Tempo tenant for this MCP session.
        return {"X-Scope-OrgID": self.tenant}

    async def __aenter__(self) -> "TempoMCPClient":
        self._stack = AsyncExitStack()
        read, write, _ = await self._stack.enter_async_context(
            streamablehttp_client(self.url, headers=self.headers)
        )
        self.session = await self._stack.enter_async_context(ClientSession(read, write))
        self.init_result = await self.session.initialize()
        log.info(
            "mcp.initialized",
            tenant=self.tenant,
            server=getattr(self.init_result.serverInfo, "name", None),
            version=getattr(self.init_result.serverInfo, "version", None),
        )
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._stack is not None:
            await self._stack.aclose()
        self.session = None

    async def list_tools(self) -> list[Any]:
        assert self.session is not None, "client not entered"
        result = await self.session.list_tools()
        return list(result.tools)

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        assert self.session is not None, "client not entered"
        log.info("mcp.call_tool", tenant=self.tenant, tool=name, arguments=arguments)
        return await self.session.call_tool(name, arguments)
