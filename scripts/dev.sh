#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
if [ ! -x .venv/bin/python ] || [ ! -d frontend/node_modules ]; then
  echo 'Install dependencies first; see README.md.'
  exit 1
fi
.venv/bin/python -m uvicorn backend.app:app --reload --reload-dir backend --host 127.0.0.1 --port 8000 &
backend_pid=$!
trap 'kill "$backend_pid" 2>/dev/null || true' EXIT INT TERM
echo 'Charal: http://127.0.0.1:3000 — API: http://127.0.0.1:8000/docs'
npm --prefix frontend run dev

