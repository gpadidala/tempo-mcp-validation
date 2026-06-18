"""Use-case runner — executes the catalog against the live MCP server and the
seeded ground truth, then writes a pass/fail report (Markdown + JSON).

    python -m usecases.runner            # run use cases -> reports/usecases.{md,json}
    python -m usecases.runner --matrix   # (re)generate docs/validation-matrix.md

Exit code is non-zero if any use case fails, so `make`/CI catches regressions.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from client import shapes
from client.mcp_client import TempoMCPClient
from client.tempo_api import TempoAPIClient

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
EXPECTED_PATH = ROOT / "seed" / "expected.json"
CATALOG_PATH = ROOT / "usecases" / "usecases.yaml"
SNAPSHOT_PATH = ROOT / "tools_snapshot.json"
REPORTS_DIR = ROOT / "reports"
MATRIX_PATH = ROOT / "docs" / "validation-matrix.md"


@dataclass
class Result:
    id: str
    goal: str
    tools: list[str]
    expected: str
    actual: str = ""
    passed: bool = False
    skipped: bool = False
    notes: list[str] = field(default_factory=list)


def _expected() -> dict[str, Any]:
    return json.loads(EXPECTED_PATH.read_text())


def _catalog() -> dict[str, dict[str, Any]]:
    cat = yaml.safe_load(CATALOG_PATH.read_text())
    return {uc["id"]: uc for uc in cat["usecases"]}


def _window(exp: dict[str, Any]) -> tuple[int, int]:
    """A generous unix-second window that brackets the seeded data."""
    seeded_s = exp["seeded_at_unix_ns"] // 1_000_000_000
    start = seeded_s - 3600
    end = int(time.time()) + 60
    return start, end


def _available_tools() -> set[str]:
    if not SNAPSHOT_PATH.exists():
        return set()
    snap = json.loads(SNAPSHOT_PATH.read_text())
    return {t["name"] for t in snap["tools"]}


# --- individual use-case implementations ----------------------------------

async def uc_find_slow(c: TempoMCPClient, exp: dict, uc: dict, start: int, end: int) -> Result:
    a = exp["tenant_a"]
    r = await c.call_tool("traceql-search", {"query": uc["query"], "start": start, "end": end})
    ids = shapes.search_trace_ids(shapes.mcp_json(r))
    expected_ids = set(a["slow_trace_ids"])
    error_id = a["error_trace_ids"][0]
    passed = ids == expected_ids and error_id not in ids
    return Result(uc["id"], uc["goal"], uc["tools"], uc["expected"],
                  actual=f"matched {sorted(ids)} (expected {sorted(expected_ids)}; fast/error excluded={error_id not in ids})",
                  passed=passed)


async def uc_find_errors(c: TempoMCPClient, exp: dict, uc: dict, start: int, end: int) -> Result:
    a = exp["tenant_a"]
    r = await c.call_tool("traceql-search", {"query": uc["query"], "start": start, "end": end})
    ids = shapes.search_trace_ids(shapes.mcp_json(r))
    expected_ids = set(a["error_trace_ids"])
    passed = ids == expected_ids
    return Result(uc["id"], uc["goal"], uc["tools"], uc["expected"],
                  actual=f"matched {sorted(ids)} (expected {sorted(expected_ids)})", passed=passed)


async def uc_trace_by_id(c: TempoMCPClient, exp: dict, uc: dict, start: int, end: int) -> Result:
    tid = exp["tenant_a"]["slow_trace_ids"][0]
    r = await c.call_tool("get-trace", {"trace_id": tid})
    payload = shapes.mcp_json(r)
    span_count = shapes.mcp_trace_span_count(payload)
    got_id = payload.get("trace", {}).get("traceId")
    passed = got_id == tid and span_count == 2
    return Result(uc["id"], uc["goal"], uc["tools"], uc["expected"],
                  actual=f"trace {got_id} with {span_count} spans", passed=passed)


async def uc_discover_queryable(c: TempoMCPClient, exp: dict, uc: dict, start: int, end: int) -> Result:
    a = exp["tenant_a"]
    names = shapes.mcp_json(await c.call_tool("get-attribute-names", {}))
    by_scope = shapes.tag_names_by_scope(names)
    has_service_tag = "service.name" in by_scope.get("resource", set())
    vals = shapes.tag_values(shapes.mcp_json(
        await c.call_tool("get-attribute-values", {"name": "resource.service.name"})))
    missing = set(a["services"]) - vals
    passed = has_service_tag and not missing
    return Result(uc["id"], uc["goal"], uc["tools"], uc["expected"],
                  actual=f"service.name tag present={has_service_tag}; values={sorted(vals)}; missing={sorted(missing)}",
                  passed=passed)


async def uc_service_filter(c: TempoMCPClient, exp: dict, uc: dict, start: int, end: int) -> Result:
    a = exp["tenant_a"]
    r = await c.call_tool("traceql-search", {"query": uc["query"], "start": start, "end": end})
    ids = shapes.search_trace_ids(shapes.mcp_json(r))
    passed = ids == set(a["frontend_trace_ids"])
    return Result(uc["id"], uc["goal"], uc["tools"], uc["expected"],
                  actual=f"{len(ids)} frontend traces (expected {a['frontend_trace_count']})", passed=passed)


async def uc_traceql_metrics(c: TempoMCPClient, exp: dict, uc: dict, start: int, end: int) -> Result:
    r = await c.call_tool("traceql-metrics-instant", {"query": uc["query"]})
    vals = shapes.metric_series_values(shapes.mcp_json(r))
    passed = len(vals) > 0 and all(v >= 0 for v in vals)
    return Result(uc["id"], uc["goal"], uc["tools"], uc["expected"],
                  actual=f"series values={vals}", passed=passed)


async def uc_empty_result(c: TempoMCPClient, exp: dict, uc: dict, start: int, end: int) -> Result:
    r = await c.call_tool("traceql-search", {"query": uc["query"], "start": start, "end": end})
    ids = shapes.search_trace_ids(shapes.mcp_json(r))
    passed = len(ids) == 0 and not shapes.is_error(r)
    return Result(uc["id"], uc["goal"], uc["tools"], uc["expected"],
                  actual=f"{len(ids)} traces, isError={shapes.is_error(r)}", passed=passed)


async def uc_tenant_isolation(c: TempoMCPClient, exp: dict, uc: dict, start: int, end: int) -> Result:
    # tenant-a (the connected client) must NOT see billing; tenant-b must.
    ra = await c.call_tool("traceql-search", {"query": uc["query"], "start": start, "end": end})
    a_ids = shapes.search_trace_ids(shapes.mcp_json(ra))
    async with TempoMCPClient(tenant=exp["tenant_b"]["tenant"]) as cb:
        rb = await cb.call_tool("traceql-search", {"query": uc["query"], "start": start, "end": end})
        b_ids = shapes.search_trace_ids(shapes.mcp_json(rb))
    passed = len(a_ids) == 0 and b_ids == set(exp["tenant_b"]["all_trace_ids"])
    return Result(uc["id"], uc["goal"], uc["tools"], uc["expected"],
                  actual=f"tenant-a billing={len(a_ids)} (want 0); tenant-b billing={len(b_ids)} (want {exp['tenant_b']['trace_count']})",
                  passed=passed)


async def uc_bad_input(c: TempoMCPClient, exp: dict, uc: dict, start: int, end: int) -> Result:
    r = await c.call_tool("traceql-search", {"query": uc["query"]})
    err = shapes.is_error(r)
    # session must remain usable afterwards
    r2 = await c.call_tool("get-attribute-names", {})
    still_works = not shapes.is_error(r2)
    passed = err and still_works
    return Result(uc["id"], uc["goal"], uc["tools"], uc["expected"],
                  actual=f"isError={err}; session-usable-after={still_works}", passed=passed)


REGISTRY = {
    "find-slow": uc_find_slow,
    "find-errors": uc_find_errors,
    "trace-by-id": uc_trace_by_id,
    "discover-queryable": uc_discover_queryable,
    "service-filter": uc_service_filter,
    "traceql-metrics": uc_traceql_metrics,
    "empty-result": uc_empty_result,
    "tenant-isolation": uc_tenant_isolation,
    "bad-input": uc_bad_input,
}

# Which discovered tool gates each use case (skip cleanly if not exposed).
TOOL_GATE = {
    "traceql-metrics": "traceql-metrics-instant",
}


async def run_all() -> list[Result]:
    exp = _expected()
    catalog = _catalog()
    start, end = _window(exp)
    available = _available_tools()
    results: list[Result] = []
    async with TempoMCPClient(tenant=exp["tenant_a"]["tenant"]) as c:
        for uc_id, fn in REGISTRY.items():
            uc = catalog[uc_id]
            gate = TOOL_GATE.get(uc_id)
            if gate and available and gate not in available:
                results.append(Result(uc_id, uc["goal"], uc["tools"], uc["expected"],
                                      actual=f"tool '{gate}' not exposed by this Tempo version",
                                      skipped=True))
                continue
            try:
                results.append(await fn(c, exp, uc, start, end))
            except Exception as e:  # noqa: BLE001 — report, don't crash the suite
                results.append(Result(uc_id, uc["goal"], uc["tools"], uc["expected"],
                                      actual=f"EXCEPTION: {type(e).__name__}: {e}", passed=False))
    return results


def write_reports(results: list[Result]) -> tuple[int, int, int]:
    REPORTS_DIR.mkdir(exist_ok=True)
    passed = sum(r.passed for r in results)
    skipped = sum(r.skipped for r in results)
    failed = sum(1 for r in results if not r.passed and not r.skipped)

    lines = ["# Use-case acceptance report", ""]
    lines.append(f"**{passed} passed · {failed} failed · {skipped} skipped** "
                 f"of {len(results)} use cases.")
    lines.append("")
    lines.append("| # | Use case | Tool(s) | Result | Detail |")
    lines.append("|---|----------|---------|--------|--------|")
    for i, r in enumerate(results, 1):
        status = "⏭️ SKIP" if r.skipped else ("✅ PASS" if r.passed else "❌ FAIL")
        tools = ", ".join(f"`{t}`" for t in r.tools)
        detail = r.actual.replace("|", "\\|")
        lines.append(f"| {i} | {r.goal} | {tools} | {status} | {detail} |")
    lines.append("")
    (REPORTS_DIR / "usecases.md").write_text("\n".join(lines) + "\n")

    (REPORTS_DIR / "usecases.json").write_text(json.dumps(
        {"summary": {"passed": passed, "failed": failed, "skipped": skipped, "total": len(results)},
         "results": [r.__dict__ for r in results]}, indent=2) + "\n")
    return passed, failed, skipped


# --- validation matrix (generated from the live tool snapshot) ------------

# Maps each discovered tool to the Tempo HTTP API it wraps, for the parity column.
TOOL_TO_API = {
    "traceql-search": "GET /api/search",
    "get-trace": "GET /api/v2/traces/{id}",
    "get-attribute-names": "GET /api/v2/search/tags",
    "get-attribute-values": "GET /api/v2/search/tag/{name}/values",
    "traceql-metrics-instant": "GET /api/metrics/query",
    "traceql-metrics-range": "GET /api/metrics/query_range",
    "docs-traceql": "(static docs — no data API)",
}

# Which test module/use case exercises each dimension per tool.
DIMENSION_COVERAGE = {
    "traceql-search": {
        "schema": "test_tools_contract.py", "happy": "uc find-slow / find-errors",
        "parity": "test_parity.py::search", "negative": "test_negative.py / uc bad-input",
        "tenancy": "test_multitenancy.py / uc tenant-isolation", "security": "test_security.py",
    },
    "get-trace": {
        "schema": "test_tools_contract.py", "happy": "uc trace-by-id",
        "parity": "test_parity.py::trace", "negative": "test_negative.py::missing_id",
        "tenancy": "test_multitenancy.py", "security": "test_security.py",
    },
    "get-attribute-names": {
        "schema": "test_tools_contract.py", "happy": "uc discover-queryable",
        "parity": "test_parity.py::tags", "negative": "test_negative.py::bad_scope",
        "tenancy": "test_multitenancy.py", "security": "test_security.py",
    },
    "get-attribute-values": {
        "schema": "test_tools_contract.py", "happy": "uc discover-queryable",
        "parity": "test_parity.py::tag_values", "negative": "test_negative.py",
        "tenancy": "test_multitenancy.py", "security": "test_security.py",
    },
    "traceql-metrics-instant": {
        "schema": "test_tools_contract.py", "happy": "uc traceql-metrics",
        "parity": "test_parity.py::metrics", "negative": "test_negative.py",
        "tenancy": "test_multitenancy.py", "security": "test_security.py",
    },
    "traceql-metrics-range": {
        "schema": "test_tools_contract.py", "happy": "test_traceql_metrics.py",
        "parity": "test_parity.py::metrics_range", "negative": "test_negative.py",
        "tenancy": "test_multitenancy.py", "security": "test_security.py",
    },
    "docs-traceql": {
        "schema": "test_tools_contract.py", "happy": "test_protocol.py",
        "parity": "n/a (static)", "negative": "test_negative.py",
        "tenancy": "n/a", "security": "n/a",
    },
}


def generate_matrix() -> None:
    snap = json.loads(SNAPSHOT_PATH.read_text())
    srv = snap["server"]
    tools = snap["tools"]
    lines = ["# Validation matrix", "",
             "> Generated from the live MCP server by `usecases/runner.py --matrix`. "
             "Do not hand-edit.", "",
             f"Server: `{srv['name']} {srv['version']}` · protocol `{snap['protocolVersion']}` · "
             f"{len(tools)} tool(s) discovered.", "",
             "## Tools → Tempo HTTP API (parity map)", "",
             "| Tool | Wraps | Required args |",
             "|------|-------|---------------|"]
    for t in tools:
        req = t["inputSchema"].get("required", []) if isinstance(t["inputSchema"], dict) else []
        api = TOOL_TO_API.get(t["name"], "⚠️ UNMAPPED — document the gap")
        lines.append(f"| `{t['name']}` | `{api}` | {', '.join(req) or '—'} |")

    lines += ["", "## Coverage per tool × dimension", "",
              "| Tool | Schema | Happy | Parity | Negative | Multi-tenancy | Security |",
              "|------|--------|-------|--------|----------|---------------|----------|"]
    for t in tools:
        cov = DIMENSION_COVERAGE.get(t["name"])
        if not cov:
            lines.append(f"| `{t['name']}` | ⚠️ no coverage mapped — NEW TOOL, add tests | | | | | |")
            continue
        lines.append(
            f"| `{t['name']}` | {cov['schema']} | {cov['happy']} | {cov['parity']} | "
            f"{cov['negative']} | {cov['tenancy']} | {cov['security']} |")

    # Honesty: flag any discovered tool we have no mapping for.
    unmapped = [t["name"] for t in tools if t["name"] not in DIMENSION_COVERAGE]
    if unmapped:
        lines += ["", "> ⚠️ **Coverage gap:** these discovered tools have no test mapping yet: "
                  + ", ".join(f"`{u}`" for u in unmapped) + "."]
    lines.append("")
    MATRIX_PATH.parent.mkdir(parents=True, exist_ok=True)
    MATRIX_PATH.write_text("\n".join(lines) + "\n")
    print(f"wrote {MATRIX_PATH}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--matrix", action="store_true", help="regenerate the validation matrix and exit")
    args = ap.parse_args()

    if args.matrix:
        generate_matrix()
        return 0

    results = asyncio.run(run_all())
    passed, failed, skipped = write_reports(results)
    for r in results:
        status = "SKIP" if r.skipped else ("PASS" if r.passed else "FAIL")
        print(f"[{status}] {r.id}: {r.actual}")
    print(f"\n{passed} passed, {failed} failed, {skipped} skipped -> reports/usecases.md")
    generate_matrix()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
