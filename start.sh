#!/bin/bash
# Start AIMVA: FastAPI backend on :8000 and Vite dev server on :5173.
cd "$(dirname "$0")"
export PATH="$HOME/.local/node/bin:$PATH"
(cd backend && .venv/bin/uvicorn app.main:app --port 8000 --reload --reload-dir app --timeout-graceful-shutdown 3) &
BACK=$!
trap 'kill $BACK 2>/dev/null' EXIT
cd frontend && npm run dev
