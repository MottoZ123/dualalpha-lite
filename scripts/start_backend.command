#!/bin/sh
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(dirname "$SCRIPT_DIR")
cd "$PROJECT_DIR"
if [ -x ".venv/bin/python" ]; then
  exec .venv/bin/python -m uvicorn research_api:app --host 127.0.0.1 --port 8910
fi
exec python3 -m uvicorn research_api:app --host 127.0.0.1 --port 8910
