# Running the harness — `make` and `make`-free options

`make` is convenient but not always available (locked-down corporate laptops,
Windows). Every target has an equivalent that needs only **Python + Docker**.
Pick whichever row fits your machine — they all do the same thing.

## Option A — Make (macOS / Linux with GNU make)

```bash
make install && make up && make seed && make validate && make usecases
make all          # all of the above in one shot
```

## Option B — Python task runner (cross-platform, no make)

Works anywhere Python 3.11+ and Docker exist — macOS, Linux, **Windows**.

```bash
python tasks.py all                 # up + seed + discover + validate + usecases
python tasks.py up seed             # run several in order
uv run python tasks.py validate     # if you use uv
python tasks.py help                # list tasks
```

## Option C — Shell / PowerShell wrappers

```bash
# macOS / Linux
./run.sh all
./run.sh up seed

# Windows PowerShell
.\run.ps1 all
.\run.ps1 up seed
```

## Option D — Raw commands (no make, no scripts)

If you'd rather run things directly. Replace `uv run` with nothing if your venv
is already activated.

| Step | Command |
|------|---------|
| Install deps | `uv sync --extra dev`  (or `pip install -e ".[dev]"`) |
| Create `.env` | `cp .env.example .env`  (Windows: `copy .env.example .env`) |
| Start stack | `docker compose up -d` |
| Wait for Tempo | open <http://localhost:3200/ready> until it returns `ready` |
| Seed traces | `uv run python -m seed.generate_traces` |
| Discover tools | `uv run python -m client.discover` |
| Drift check | `uv run python -m client.discover --check` |
| Validate (pytest) | `uv run pytest -q --junitxml=reports/junit.xml` |
| Use cases | `uv run python -m usecases.runner` |
| Stop stack | `docker compose down -v` |

## Task ↔ command reference

| make target | `tasks.py` | raw command |
|-------------|-----------|-------------|
| `make install` | `python tasks.py install` | `uv sync --extra dev` |
| `make up` | `python tasks.py up` | `docker compose up -d` |
| `make seed` | `python tasks.py seed` | `uv run python -m seed.generate_traces` |
| `make discover` | `python tasks.py discover` | `uv run python -m client.discover` |
| `make drift` | `python tasks.py drift` | `uv run python -m client.discover --check` |
| `make validate` | `python tasks.py validate` | `uv run pytest -q` |
| `make usecases` | `python tasks.py usecases` | `uv run python -m usecases.runner` |
| `make down` | `python tasks.py down` | `docker compose down -v` |
| `make all` | `python tasks.py all` | (the five steps above, in order) |

## Notes for corporate / Windows machines

- **No `make`?** Use Option B/C/D. `tasks.py` only uses the Python standard
  library, so it runs before `uv sync` too.
- **No `uv`?** `tasks.py` falls back to the active interpreter; install deps with
  `pip install -e ".[dev]"`.
- **Docker Desktop alternative?** Any engine exposing `docker compose` works;
  `tasks.py` also falls back to legacy `docker-compose`.
- **Distroless Tempo image** means the container shows as `unhealthy` in some UIs —
  that's expected; readiness is gated on <http://localhost:3200/ready>.
