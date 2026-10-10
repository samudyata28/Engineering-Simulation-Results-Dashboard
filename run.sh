#!/usr/bin/env bash
# One-command start: installs deps, builds the UI, imports the CSVs, seeds the demo demands, serves everything on :8000.
set -euo pipefail
cd "$(dirname "$0")"
python3 -m pip install -q -r backend/requirements.txt ${PIP_FLAGS:-}
(cd frontend && npm install --silent && npm run build --silent)
cd backend
python3 -m app.cli import || true          # reports bad files but never blocks start-up
python3 -m app.cli seed-demands            # idempotent: one demand per component from its first failing revision
exec python3 -m uvicorn app.main:create_app --factory --host 0.0.0.0 --port "${PORT:-8000}"
