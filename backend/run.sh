#!/usr/bin/env bash
# One-command backend start (macOS / Linux / Git Bash).
#   Usage:  ./run.sh
set -e
cd "$(dirname "$0")"

PY=.venv/bin/python
[ -x "$PY" ] || PY=.venv/Scripts/python.exe   # Git Bash on Windows

if [ ! -x "$PY" ]; then
  echo "No venv found. Creating one and installing requirements..."
  python -m venv .venv
  $PY -m pip install --upgrade pip
  $PY -m pip install -r requirements.txt
fi

echo "Seeding SYNTHETIC demo data..."
$PY seed.py

echo "Starting API on http://0.0.0.0:8000 ..."
$PY -m uvicorn main:app --host 0.0.0.0 --port 8000
