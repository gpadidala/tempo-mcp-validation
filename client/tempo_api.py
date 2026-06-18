"""Direct Tempo HTTP API client — the parity reference.

For every MCP tool we also call the equivalent Tempo HTTP endpoint and assert
semantic equivalence. This client wraps those endpoints with the same tenant
header the MCP client uses.

Endpoint map (MCP tool -> HTTP API):
    traceql-search           -> GET /api/search?q=&start=&end=
    get-trace                -> GET /api/v2/traces/{id}
    get-attribute-names      -> GET /api/v2/search/tags?scope=
    get-attribute-values     -> GET /api/v2/search/tag/{name}/values
    traceql-metrics-instant  -> GET /api/metrics/query?q=
    traceql-metrics-range    -> GET /api/metrics/query_range?q=&start=&end=&step=
"""

from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_API_URL = os.environ.get("TEMPO_API_URL", "http://localhost:3200")


class TempoAPIClient:
    def __init__(self, base_url: str | None = None, tenant: str | None = None) -> None:
        self.base_url = (base_url or DEFAULT_API_URL).rstrip("/")
        self.tenant = tenant or os.environ.get("TENANT_PRIMARY", "tenant-a")

    @property
    def _headers(self) -> dict[str, str]:
        return {"X-Scope-OrgID": self.tenant}

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> httpx.Response:
        async with httpx.AsyncClient(timeout=30) as client:
            return await client.get(f"{self.base_url}{path}", params=params, headers=self._headers)

    async def ready(self) -> bool:
        try:
            r = await self._get("/ready")
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    async def search(self, query: str, start: int | None = None, end: int | None = None) -> dict:
        params: dict[str, Any] = {"q": query}
        if start is not None:
            params["start"] = start
        if end is not None:
            params["end"] = end
        r = await self._get("/api/search", params)
        r.raise_for_status()
        return r.json()

    async def trace_by_id(self, trace_id: str) -> dict:
        r = await self._get(f"/api/v2/traces/{trace_id}")
        r.raise_for_status()
        return r.json()

    async def tag_names(self, scope: str | None = None) -> dict:
        params = {"scope": scope} if scope else None
        r = await self._get("/api/v2/search/tags", params)
        r.raise_for_status()
        return r.json()

    async def tag_values(self, name: str) -> dict:
        r = await self._get(f"/api/v2/search/tag/{name}/values")
        r.raise_for_status()
        return r.json()

    async def metrics_instant(self, query: str) -> dict:
        r = await self._get("/api/metrics/query", {"q": query})
        r.raise_for_status()
        return r.json()

    async def metrics_range(
        self, query: str, start: int, end: int, step: str = "60s"
    ) -> dict:
        params = {"q": query, "start": start, "end": end, "step": step}
        r = await self._get("/api/metrics/query_range", params)
        r.raise_for_status()
        return r.json()
