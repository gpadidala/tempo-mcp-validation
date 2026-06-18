"""Runtime tool discovery + drift detection for the Tempo MCP server.

GUARDRAIL: tools are discovered at runtime, never hardcoded. This calls MCP
`tools/list`, snapshots the tools + JSON schemas to tools_snapshot.json, and
diffs against any prior snapshot so CI goes red on tool regression.

    python -m client.discover            # write/update snapshot, print summary
    python -m client.discover --check    # fail (exit 1) if live set drifts from snapshot
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from client.mcp_client import TempoMCPClient

load_dotenv()

SNAPSHOT_PATH = Path(__file__).resolve().parent.parent / "tools_snapshot.json"


def _tool_to_dict(tool: Any) -> dict[str, Any]:
    return {
        "name": tool.name,
        "description": (tool.description or "").strip(),
        "inputSchema": tool.inputSchema,
    }


async def fetch_snapshot(tenant: str | None = None) -> dict[str, Any]:
    async with TempoMCPClient(tenant=tenant) as client:
        info = client.init_result.serverInfo
        tools = await client.list_tools()
        return {
            "server": {"name": info.name, "version": info.version},
            "protocolVersion": client.init_result.protocolVersion,
            "tools": sorted((_tool_to_dict(t) for t in tools), key=lambda t: t["name"]),
        }


def _tool_names(snap: dict[str, Any]) -> set[str]:
    return {t["name"] for t in snap["tools"]}


def write_snapshot(snap: dict[str, Any]) -> None:
    SNAPSHOT_PATH.write_text(json.dumps(snap, indent=2, sort_keys=True) + "\n")


def load_snapshot() -> dict[str, Any] | None:
    if not SNAPSHOT_PATH.exists():
        return None
    return json.loads(SNAPSHOT_PATH.read_text())


def diff_snapshots(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    old_names, new_names = _tool_names(old), _tool_names(new)
    changed_schema = []
    old_by_name = {t["name"]: t for t in old["tools"]}
    for t in new["tools"]:
        prev = old_by_name.get(t["name"])
        if prev and prev["inputSchema"] != t["inputSchema"]:
            changed_schema.append(t["name"])
    return {
        "added": sorted(new_names - old_names),
        "removed": sorted(old_names - new_names),
        "schema_changed": sorted(changed_schema),
    }


def _print_summary(snap: dict[str, Any]) -> None:
    srv = snap["server"]
    print(f"server: {srv['name']} {srv['version']}  (protocol {snap['protocolVersion']})")
    print(f"discovered {len(snap['tools'])} tool(s):\n")
    for t in snap["tools"]:
        required = t["inputSchema"].get("required", []) if isinstance(t["inputSchema"], dict) else []
        props = list(t["inputSchema"].get("properties", {})) if isinstance(t["inputSchema"], dict) else []
        print(f"  • {t['name']}")
        print(f"      {t['description'][:100]}")
        print(f"      args: {props or '—'}   required: {required or '—'}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Discover Tempo MCP tools at runtime.")
    ap.add_argument("--check", action="store_true", help="fail if live set drifts from snapshot")
    args = ap.parse_args()

    live = asyncio.run(fetch_snapshot())

    if args.check:
        prior = load_snapshot()
        if prior is None:
            print("no tools_snapshot.json to check against; run without --check first", file=sys.stderr)
            return 2
        delta = diff_snapshots(prior, live)
        if any(delta.values()):
            print("TOOL DRIFT DETECTED:", json.dumps(delta, indent=2), file=sys.stderr)
            return 1
        print(f"no drift: {len(live['tools'])} tool(s) match snapshot.")
        return 0

    prior = load_snapshot()
    write_snapshot(live)
    _print_summary(live)
    if prior is not None:
        delta = diff_snapshots(prior, live)
        if any(delta.values()):
            print("\n(snapshot updated; drift vs previous):", json.dumps(delta))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
