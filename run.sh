#!/usr/bin/env bash
# make-free runner for macOS / Linux. Delegates to the cross-platform tasks.py.
#   ./run.sh all          # up + seed + discover + validate + usecases
#   ./run.sh up seed
set -euo pipefail
cd "$(dirname "$0")"

if command -v uv >/dev/null 2>&1; then
  exec uv run python tasks.py "$@"
else
  exec python3 tasks.py "$@"
fi
