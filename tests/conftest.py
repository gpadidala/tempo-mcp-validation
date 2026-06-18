"""Shared pytest fixtures.

The suite runs against a live stack: `make up && make seed` must have happened
first (seed blocks until traces are search-indexed). Fixtures load the ground
truth, the live tool snapshot, and provide connected MCP / direct-API clients.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx
import pytest
import pytest_asyncio
from dotenv import load_dotenv

from client.mcp_client import TempoMCPClient
from client.tempo_api import TempoAPIClient

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
EXPECTED_PATH = ROOT / "seed" / "expected.json"
SNAPSHOT_PATH = ROOT / "tools_snapshot.json"


def _tempo_ready() -> bool:
    try:
        return httpx.get("http://localhost:3200/ready", timeout=5).status_code == 200
    except httpx.HTTPError:
        return False


@pytest.fixture(scope="session", autouse=True)
def require_stack() -> None:
    """Fail fast with a clear message if the stack isn't up / seeded."""
    if not _tempo_ready():
        pytest.exit("Tempo is not ready at :3200 — run `make up && make seed` first.", returncode=2)
    if not EXPECTED_PATH.exists():
        pytest.exit("seed/expected.json missing — run `make seed` first.", returncode=2)


@pytest.fixture(scope="session")
def expected() -> dict[str, Any]:
    return json.loads(EXPECTED_PATH.read_text())


@pytest.fixture(scope="session")
def window(expected: dict[str, Any]) -> tuple[int, int]:
    seeded_s = expected["seeded_at_unix_ns"] // 1_000_000_000
    return seeded_s - 3600, int(time.time()) + 60


@pytest.fixture(scope="session")
def snapshot() -> dict[str, Any]:
    if not SNAPSHOT_PATH.exists():
        pytest.exit("tools_snapshot.json missing — run `make discover` first.", returncode=2)
    return json.loads(SNAPSHOT_PATH.read_text())


@pytest.fixture(scope="session")
def tool_names(snapshot: dict[str, Any]) -> set[str]:
    return {t["name"] for t in snapshot["tools"]}


@pytest.fixture(scope="session")
def tools(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    return snapshot["tools"]


# NOTE: MCP clients are provided as *factories*, not pre-connected fixtures.
# The streamable-HTTP transport holds an anyio task group; an async-generator
# fixture would enter it during setup and exit it during teardown — different
# tasks — which anyio rejects ("cancel scope in a different task"). Each test
# instead opens the client in its own task via `async with mcp() as c:`.

@pytest.fixture
def mcp(expected: dict[str, Any]):
    """Factory for a primary-tenant MCP client: `async with mcp() as c:`."""
    def _make() -> TempoMCPClient:
        return TempoMCPClient(tenant=expected["tenant_a"]["tenant"])
    return _make


@pytest.fixture
def mcp_b(expected: dict[str, Any]):
    """Factory for a secondary-tenant MCP client (isolation tests)."""
    def _make() -> TempoMCPClient:
        return TempoMCPClient(tenant=expected["tenant_b"]["tenant"])
    return _make


@pytest.fixture
def api(expected: dict[str, Any]) -> TempoAPIClient:
    return TempoAPIClient(tenant=expected["tenant_a"]["tenant"])


def require_tool(tool_names: set[str], name: str) -> None:
    if name not in tool_names:
        pytest.skip(f"tool '{name}' not exposed by this Tempo version")
