#!/usr/bin/env python3
"""Cross-platform task runner — a `make`-free way to drive the harness.

Works anywhere Python 3.11+ and Docker are available (macOS / Linux / Windows),
so you don't need GNU make on a locked-down corporate laptop.

    python tasks.py <task> [task ...]

Tasks (same names as the Makefile targets):
    install   create the venv + install deps (uv)
    up        start the stack (Tempo MCP + Prometheus + Grafana), wait for ready
    seed      push deterministic ground-truth traces (blocks until searchable)
    discover  snapshot live MCP tools -> tools_snapshot.json
    drift     fail if the live tool set drifted from the snapshot
    validate  run the pytest suite (-> reports/junit.xml)
    usecases  run the use-case catalog (-> reports/usecases.md + matrix)
    dashboards open the Grafana dashboards URL
    down      stop the stack + remove volumes
    all       up + seed + discover + validate + usecases
    help      show this message

Examples:
    python tasks.py all
    python tasks.py up seed
    uv run python tasks.py validate
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
import urllib.request

ROOT = __file__.rsplit("tasks.py", 1)[0] or "."
READY_URL = "http://localhost:3200/ready"
GRAFANA_DASH = "http://localhost:3000/d/tempo-mcp-server/tempo-mcp-server"


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


# Prefer `uv run` for Python tasks; fall back to the current interpreter if uv
# isn't on PATH (assumes the venv is already active in that case).
def _py(args: list[str]) -> list[str]:
    if _have("uv"):
        return ["uv", "run", "python", *args]
    return [sys.executable, *args]


def _compose() -> list[str]:
    # Prefer the modern `docker compose`; fall back to legacy `docker-compose`.
    if _have("docker"):
        return ["docker", "compose"]
    if _have("docker-compose"):
        return ["docker-compose"]
    sys.exit("ERROR: docker / docker compose not found on PATH.")


def run(cmd: list[str]) -> None:
    print(f"\n$ {' '.join(cmd)}", flush=True)
    proc = subprocess.run(cmd, cwd=ROOT)
    if proc.returncode != 0:
        sys.exit(proc.returncode)


def wait_ready(timeout_s: int = 120) -> None:
    print(f"waiting for Tempo {READY_URL} ...", flush=True)
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(READY_URL, timeout=5) as r:
                if r.status == 200:
                    print("tempo ready")
                    return
        except Exception:  # noqa: BLE001 — not up yet
            pass
        time.sleep(2)
    sys.exit("Tempo did not become ready in time.")


def t_install() -> None:
    if _have("uv"):
        run(["uv", "sync", "--extra", "dev"])
    else:
        run([sys.executable, "-m", "pip", "install", "-e", ".[dev]"])


def t_up() -> None:
    run([*_compose(), "up", "-d"])
    wait_ready()


def t_down() -> None:
    run([*_compose(), "down", "-v"])


def t_seed() -> None:
    run(_py(["-m", "seed.generate_traces"]))


def t_discover() -> None:
    run(_py(["-m", "client.discover"]))


def t_drift() -> None:
    run(_py(["-m", "client.discover", "--check"]))


def t_validate() -> None:
    run(_py(["-m", "pytest", "-q", "--junitxml=reports/junit.xml"]))


def t_usecases() -> None:
    run(_py(["-m", "usecases.runner"]))


def t_dashboards() -> None:
    print(f"Grafana dashboards: {GRAFANA_DASH}")
    print("  (Tempo MCP Server) and /d/tempo-backend/tempo-backend-query-and-ingest")
    try:
        import webbrowser

        webbrowser.open(GRAFANA_DASH)
    except Exception:  # noqa: BLE001
        pass


def t_all() -> None:
    t_up(); t_seed(); t_discover(); t_validate(); t_usecases()


def t_help() -> None:
    print(__doc__)


TASKS = {
    "install": t_install, "up": t_up, "down": t_down, "seed": t_seed,
    "discover": t_discover, "drift": t_drift, "validate": t_validate,
    "usecases": t_usecases, "dashboards": t_dashboards, "all": t_all, "help": t_help,
}


def main(argv: list[str]) -> None:
    if not argv or "help" in argv or "-h" in argv or "--help" in argv:
        t_help()
        return
    unknown = [a for a in argv if a not in TASKS]
    if unknown:
        sys.exit(f"unknown task(s): {', '.join(unknown)}\nrun `python tasks.py help`")
    for name in argv:
        print(f"\n=== {name} ===")
        TASKS[name]()
    print("\ndone.")


if __name__ == "__main__":
    main(sys.argv[1:])
