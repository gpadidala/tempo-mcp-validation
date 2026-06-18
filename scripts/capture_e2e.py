"""Drive the live MCP Inspector (and Grafana) with Playwright and capture the
end-to-end walkthrough screenshots used in docs/e2e-walkthrough.md.

Prereqs: stack up + seeded, and MCP Inspector running on :6274.
    make up && make seed
    DANGEROUSLY_OMIT_AUTH=true npx @modelcontextprotocol/inspector   # in another shell
    uv run python scripts/capture_e2e.py
"""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "docs" / "screenshots"
SHOTS.mkdir(parents=True, exist_ok=True)

INSPECTOR = "http://localhost:6274"
MCP_URL = "http://localhost:3200/api/mcp"
EXPECTED = json.loads((ROOT / "seed" / "expected.json").read_text())
SLOW_ID = EXPECTED["tenant_a"]["slow_trace_ids"][0]
BILLING_ID = EXPECTED["tenant_b"]["all_trace_ids"][0]


def shot(pg: Page, name: str) -> None:
    pg.screenshot(path=str(SHOTS / name))
    print(f"  saved {name}")


def connect(pg: Page, tenant: str) -> None:
    """Configure Streamable HTTP + X-Scope-OrgID header and connect."""
    pg.goto(INSPECTOR, wait_until="networkidle", timeout=20000)
    pg.wait_for_timeout(1200)
    pg.get_by_role("combobox").first.click()
    pg.wait_for_timeout(400)
    pg.get_by_role("option", name="Streamable HTTP").click()
    pg.wait_for_timeout(400)
    pg.get_by_placeholder("URL").fill(MCP_URL)
    pg.get_by_test_id("auth-button").click()
    pg.wait_for_timeout(400)
    pg.get_by_placeholder("Header Name").fill("X-Scope-OrgID")
    pg.get_by_placeholder("Header Value").fill(tenant)
    pg.query_selector("[role=switch]").click()  # enable the header (off by default)
    pg.wait_for_timeout(300)
    pg.get_by_test_id("auth-button").click()  # collapse to tidy the panel
    pg.wait_for_timeout(300)
    pg.get_by_role("button", name="Connect").click()
    pg.wait_for_timeout(4000)
    assert "Connected" in pg.inner_text("body"), f"failed to connect as {tenant}"


def list_tools(pg: Page) -> None:
    pg.get_by_role("tab", name="Tools").click()
    pg.wait_for_timeout(500)
    pg.get_by_role("button", name="List Tools").click()
    pg.wait_for_timeout(1200)


def run_tool(pg: Page, tool: str, fields: dict[str, str], anchor: str | None = None) -> None:
    # Click the tool in the (already-listed) left panel; .first picks the list
    # item rather than any later occurrence in the result/history panes.
    pg.get_by_text(tool, exact=True).first.click()
    pg.wait_for_timeout(800)
    for name, value in fields.items():
        pg.locator(f"textarea[name='{name}'], input[name='{name}']").first.fill(value)
    pg.get_by_role("button", name="Run Tool").click()
    pg.wait_for_timeout(2000)
    # Scroll the result content into view. Prefer a text anchor unique to the
    # result body (e.g. a returned traceID) so the screenshot shows real data;
    # fall back to the "Tool Result" heading.
    target = None
    if anchor and pg.get_by_text(anchor, exact=False).count():
        target = pg.get_by_text(anchor, exact=False).first
    elif "Tool Result" in pg.inner_text("body"):
        target = pg.get_by_text("Tool Result").first
    if target:
        target.scroll_into_view_if_needed()
        pg.wait_for_timeout(500)


def capture_grafana(p) -> None:
    """Grafana Explore: run a TraceQL search and open the trace waterfall."""
    import urllib.parse

    panes = {"t1": {"datasource": "tempo", "queries": [{
        "refId": "A", "datasource": {"type": "tempo", "uid": "tempo"},
        "queryType": "traceql", "query": "{ duration > 1s }", "limit": 20,
        "tableType": "traces"}], "range": {"from": "now-1h", "to": "now"}}}
    url = ("http://localhost:3000/explore?schemaVersion=1&orgId=1&panes="
           + urllib.parse.quote(json.dumps(panes)))
    browser = p.chromium.launch()
    pg = browser.new_page(viewport={"width": 1500, "height": 1000})
    pg.goto(url, wait_until="networkidle", timeout=30000)
    pg.wait_for_timeout(5000)
    shot(pg, "06_grafana_explore_search.png")
    pg.get_by_text(SLOW_ID[:9], exact=False).first.click()
    pg.wait_for_timeout(4500)
    shot(pg, "07_grafana_trace_waterfall.png")
    browser.close()


def main() -> None:
    vp = {"width": 1400, "height": 1000}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page(viewport=vp)

        print("tenant-a: connect + list tools")
        connect(pg, "tenant-a")
        list_tools(pg)
        shot(pg, "01_connected_tools.png")

        print("tenant-a: traceql-search { duration > 1s }")
        run_tool(pg, "traceql-search", {"query": "{ duration > 1s }"}, anchor=SLOW_ID[:12])
        shot(pg, "02_traceql_search_slow.png")

        print("tenant-a: get-trace by id")
        run_tool(pg, "get-trace", {"trace_id": SLOW_ID}, anchor="SELECT orders")
        shot(pg, "03_get_trace.png")

        print("tenant-a: get-attribute-values resource.service.name")
        run_tool(pg, "get-attribute-values", {"name": "resource.service.name"}, anchor="checkout")
        shot(pg, "04_tag_values.png")

        print("tenant-a: search billing (isolation — expect empty)")
        run_tool(pg, "traceql-search", {"query": '{ resource.service.name = "billing" }'},
                 anchor="inspectedBytes")
        shot(pg, "05a_isolation_tenant_a_empty.png")
        browser.close()

        # New session as tenant-b: same billing query now returns data.
        browser = p.chromium.launch()
        pg = browser.new_page(viewport=vp)
        print("tenant-b: search billing (isolation — expect 2 traces)")
        connect(pg, "tenant-b")
        list_tools(pg)
        run_tool(pg, "traceql-search", {"query": '{ resource.service.name = "billing" }'},
                 anchor=BILLING_ID[:12])
        shot(pg, "05b_isolation_tenant_b_data.png")
        browser.close()

        print("grafana: explore search + trace waterfall")
        capture_grafana(p)

    print("done")


if __name__ == "__main__":
    main()
