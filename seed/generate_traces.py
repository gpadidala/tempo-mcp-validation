"""Deterministic trace seeder — the ground truth for every assertion.

Pushes a fixed set of labeled traces to Tempo via OTLP/HTTP JSON. Trace and span
IDs are derived by hashing stable names, so the same traces (same IDs) are
produced on every run. Timestamps are relative to seed-time so traces fall
inside "last 15m" query windows.

Two tenants are seeded (via X-Scope-OrgID):
  tenant-a — the rich scenario set the use cases assert against.
  tenant-b — a small, disjoint set, used only to prove tenant isolation.

Writes seed/expected.json: the fixture the test suite + use-case runner read.

    python -m seed.generate_traces
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

OTLP_HTTP_URL = os.environ.get("OTLP_HTTP_URL", "http://localhost:4318")
TENANT_A = os.environ.get("TENANT_PRIMARY", "tenant-a")
TENANT_B = os.environ.get("TENANT_SECONDARY", "tenant-b")

EXPECTED_PATH = Path(__file__).resolve().parent / "expected.json"

MS = 1_000_000  # nanoseconds per millisecond


def _hex(prefix: str, nbytes: int) -> str:
    return hashlib.sha256(prefix.encode()).hexdigest()[: nbytes * 2]


def trace_id(name: str) -> str:
    return _hex(f"trace::{name}", 16)  # 32 hex chars


def span_id(name: str) -> str:
    return _hex(f"span::{name}", 8)  # 16 hex chars


def _attr(key: str, value: object) -> dict:
    if isinstance(value, bool):
        v = {"boolValue": value}
    elif isinstance(value, int):
        v = {"intValue": str(value)}
    elif isinstance(value, float):
        v = {"doubleValue": value}
    else:
        v = {"stringValue": str(value)}
    return {"key": key, "value": v}


def _span(
    name: str,
    *,
    span_key: str,
    start_ns: int,
    duration_ms: int,
    kind: int = 2,
    parent: str = "",
    status_code: int = 1,  # 0 unset, 1 ok, 2 error
    attrs: dict | None = None,
) -> dict:
    span = {
        "traceId": "",  # filled in by caller (lives at resource level)
        "spanId": span_id(span_key),
        "parentSpanId": parent,
        "name": name,
        "kind": kind,
        "startTimeUnixNano": str(start_ns),
        "endTimeUnixNano": str(start_ns + duration_ms * MS),
        "attributes": [_attr(k, v) for k, v in (attrs or {}).items()],
        "status": {"code": status_code},
    }
    return span


def _resource_spans(service: str, trace_hex: str, spans: list[dict]) -> dict:
    for s in spans:
        s["traceId"] = trace_hex
    return {
        "resource": {"attributes": [_attr("service.name", service)]},
        "scopeSpans": [{"scope": {"name": "tempo-mcp-seed"}, "spans": spans}],
    }


def build_tenant_a(now_ns: int) -> tuple[list[dict], dict]:
    """Rich scenario set + the fixture describing it."""
    rs: list[dict] = []

    # 1. Slow checkout request: root 1500ms (> 1s) with a child db span.
    t_slow = trace_id("checkout-slow")
    rs.append(
        _resource_spans(
            "checkout",
            t_slow,
            [
                _span("POST /checkout", span_key="slow-root", start_ns=now_ns - 1500 * MS,
                      duration_ms=1500, attrs={"http.method": "POST", "http.status_code": 200}),
                _span("SELECT orders", span_key="slow-db", start_ns=now_ns - 1400 * MS,
                      duration_ms=1200, kind=3, parent=span_id("slow-root"),
                      attrs={"db.system": "postgresql"}),
            ],
        )
    )

    # 2. Error trace: http 500 + ERROR status in checkout.
    t_err = trace_id("checkout-error")
    rs.append(
        _resource_spans(
            "checkout",
            t_err,
            [
                _span("POST /checkout", span_key="err-root", start_ns=now_ns - 300 * MS,
                      duration_ms=120, status_code=2,
                      attrs={"http.method": "POST", "http.status_code": 500, "error": True}),
            ],
        )
    )

    # 3-5. Three fast frontend traces (< 200ms), no errors.
    frontend_ids = []
    for i in range(3):
        tid = trace_id(f"frontend-{i}")
        frontend_ids.append(tid)
        rs.append(
            _resource_spans(
                "frontend",
                tid,
                [
                    _span(f"GET /page/{i}", span_key=f"fe-root-{i}", start_ns=now_ns - (200 + i) * MS,
                          duration_ms=80 + i * 10, attrs={"http.method": "GET", "http.status_code": 200}),
                ],
            )
        )

    # 6. Multi-service graph: frontend -> cart -> payment in one trace.
    t_graph = trace_id("multiservice-graph")
    rs.append(
        _resource_spans(
            "frontend",
            t_graph,
            [_span("GET /cart/checkout", span_key="graph-fe", start_ns=now_ns - 500 * MS,
                   duration_ms=400, attrs={"http.method": "GET"})],
        )
    )
    rs.append(
        _resource_spans(
            "cart",
            t_graph,
            [_span("cart.assemble", span_key="graph-cart", start_ns=now_ns - 480 * MS,
                   duration_ms=200, kind=3, parent=span_id("graph-fe"))],
        )
    )
    rs.append(
        _resource_spans(
            "payment",
            t_graph,
            [_span("payment.charge", span_key="graph-pay", start_ns=now_ns - 400 * MS,
                   duration_ms=150, kind=3, parent=span_id("graph-cart"),
                   attrs={"payment.provider": "stripe"})],
        )
    )

    # 7. Unique-attribute span (single discoverable tag value).
    t_uniq = trace_id("inventory-unique")
    rs.append(
        _resource_spans(
            "inventory",
            t_uniq,
            [_span("inventory.reserve", span_key="uniq-root", start_ns=now_ns - 600 * MS,
                   duration_ms=90, attrs={"promo.code": "UNIQUE-SEED-XYZ"})],
        )
    )

    fixture = {
        "tenant": TENANT_A,
        "services": sorted(["checkout", "frontend", "cart", "payment", "inventory"]),
        "trace_count": 7,
        "slow_trace_ids": [t_slow],          # duration > 1s in checkout
        "error_trace_ids": [t_err],          # status=error / http 500
        "frontend_trace_ids": sorted(frontend_ids + [t_graph]),  # frontend root spans
        "frontend_trace_count": 4,
        "multiservice_trace_id": t_graph,
        "unique_attr": {"key": "promo.code", "value": "UNIQUE-SEED-XYZ", "trace_id": t_uniq},
        "all_trace_ids": sorted([t_slow, t_err, *frontend_ids, t_graph, t_uniq]),
    }
    return rs, fixture


def build_tenant_b(now_ns: int) -> tuple[list[dict], dict]:
    """Disjoint set, distinct service names, for isolation testing."""
    rs: list[dict] = []
    ids = []
    for i in range(2):
        tid = trace_id(f"billing-{i}")
        ids.append(tid)
        rs.append(
            _resource_spans(
                "billing",
                tid,
                [_span(f"POST /invoice/{i}", span_key=f"bill-root-{i}", start_ns=now_ns - (300 + i) * MS,
                       duration_ms=110, attrs={"http.status_code": 200})],
            )
        )
    fixture = {
        "tenant": TENANT_B,
        "services": ["billing"],
        "trace_count": 2,
        "all_trace_ids": sorted(ids),
    }
    return rs, fixture


def push(tenant: str, resource_spans: list[dict]) -> None:
    # On a cold stack the distributor ring takes a few seconds to register as
    # healthy; until then OTLP pushes are rejected with 429 (global rate
    # strategy divides by 0 healthy distributors). Retry with backoff so a
    # fresh `make up && make seed` is reliable.
    payload = {"resourceSpans": resource_spans}
    headers = {"Content-Type": "application/json", "X-Scope-OrgID": tenant}
    last_exc: Exception | None = None
    for attempt in range(1, 9):
        resp = httpx.post(f"{OTLP_HTTP_URL}/v1/traces", json=payload, headers=headers, timeout=30)
        if resp.status_code == 200:
            print(f"  pushed {len(resource_spans)} resource-span batch(es) for {tenant} -> 200")
            return
        if resp.status_code in (429, 503):
            print(f"  {tenant}: {resp.status_code} (ring warming up), retry {attempt}/8 ...")
            last_exc = httpx.HTTPStatusError(f"{resp.status_code}", request=resp.request, response=resp)
            time.sleep(3)
            continue
        resp.raise_for_status()
    raise RuntimeError(f"ingestion never succeeded for {tenant}") from last_exc


def main() -> int:
    now_ns = time.time_ns()
    print(f"seeding traces to {OTLP_HTTP_URL} (now={now_ns})")

    rs_a, fix_a = build_tenant_a(now_ns)
    rs_b, fix_b = build_tenant_b(now_ns)

    push(TENANT_A, rs_a)
    push(TENANT_B, rs_b)

    expected = {"seeded_at_unix_ns": now_ns, "tenant_a": fix_a, "tenant_b": fix_b}
    EXPECTED_PATH.write_text(json.dumps(expected, indent=2, sort_keys=True) + "\n")
    print(f"\nwrote ground-truth fixture -> {EXPECTED_PATH}")
    print(f"  tenant-a: {fix_a['trace_count']} traces across {len(fix_a['services'])} services")
    print(f"  tenant-b: {fix_b['trace_count']} traces (isolation)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
