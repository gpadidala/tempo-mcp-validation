"""Shape helpers — normalize MCP tool results and direct Tempo API responses to
the same semantic values so parity tests can compare apples to apples.

The MCP tools and the direct HTTP API return overlapping-but-different JSON:
  - traceql-search / /api/search        -> identical {"traces":[{traceID}...]}
  - get-trace        -> {"trace":{"services":[{scopes:[{spans:[{spanId}]}]}]}}
    /api/v2/traces   -> {"trace":{"resourceSpans":[{scopeSpans:[{spans}]}]}}
  - get-attribute-names / .../search/tags -> identical {"scopes":[{name,tags}]}
  - get-attribute-values -> {"tagValues":{"string":[...]}}
    /api/.../tag/.../values -> {"tagValues":[{"type","value"}]}
These helpers paper over those differences and return plain Python sets/ints.
"""

from __future__ import annotations

import json
from typing import Any


# --- MCP CallToolResult helpers -------------------------------------------

def mcp_text(result: Any) -> str:
    """Concatenate the text content blocks of an MCP CallToolResult."""
    return "".join(getattr(b, "text", "") for b in result.content)


def mcp_json(result: Any) -> Any:
    """Parse an MCP tool result's text payload as JSON."""
    return json.loads(mcp_text(result))


def is_error(result: Any) -> bool:
    return bool(getattr(result, "isError", False))


# --- Semantic extractors (work on either MCP or direct-API JSON) ----------

def search_trace_ids(payload: dict[str, Any]) -> set[str]:
    """traceql-search and /api/search share this shape."""
    return {t["traceID"] for t in payload.get("traces", [])}


def tag_names_by_scope(payload: dict[str, Any]) -> dict[str, set[str]]:
    """get-attribute-names and /api/v2/search/tags share this shape."""
    return {s["name"]: set(s.get("tags", [])) for s in payload.get("scopes", [])}


def tag_values(payload: dict[str, Any]) -> set[str]:
    """Normalize both tag-value shapes to a flat set of string values."""
    tv = payload.get("tagValues")
    if isinstance(tv, dict):  # MCP: {"string": [...], "int": [...]}
        out: set[str] = set()
        for v in tv.values():
            out.update(str(x) for x in v)
        return out
    if isinstance(tv, list):  # direct API: [{"type","value"}]
        return {str(x["value"]) for x in tv}
    return set()


def mcp_trace_span_count(payload: dict[str, Any]) -> int:
    """Span count from the MCP get-trace shape."""
    n = 0
    for svc in payload.get("trace", {}).get("services", []):
        for scope in svc.get("scopes", []):
            n += len(scope.get("spans", []))
    return n


def otlp_trace_span_count(payload: dict[str, Any]) -> int:
    """Span count from the direct /api/v2/traces OTLP shape."""
    n = 0
    for rs in payload.get("trace", {}).get("resourceSpans", []):
        for ss in rs.get("scopeSpans", []):
            n += len(ss.get("spans", []))
    return n


def metric_series_values(payload: dict[str, Any]) -> list[float]:
    """Instant value(s) from a metrics result."""
    return [s["value"] for s in payload.get("series", []) if "value" in s]


def metric_range_sample_count(payload: dict[str, Any]) -> int:
    """Total samples across all series in a range metrics result."""
    return sum(len(s.get("samples", [])) for s in payload.get("series", []))
