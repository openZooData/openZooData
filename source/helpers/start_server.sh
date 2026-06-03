#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV_DIR="$ROOT_DIR/../venv"
LOG_DIR="$ROOT_DIR/logs"
PORT="5001"

mkdir -p "$LOG_DIR"

cd "$ROOT_DIR"

set -a
source "$ROOT_DIR/.env"
set +a

source "$VENV_DIR/bin/activate"

env PYTHONPATH=source gunicorn \
  --bind "127.0.0.1:${PORT}" \
  --workers 2 \
  --timeout 60 \
  --access-logfile "$LOG_DIR/access.log" \
  --error-logfile "$LOG_DIR/error.log" \
  app:app &

PID=$!

echo "Started OpenZooData Gunicorn"
echo "PID:  $PID"
echo "Port: $PORT"

sleep 3

echo
echo "========================================"
echo "OpenZooData Health Check"
echo "========================================"

curl -s \
  -H "X-Health-Key: ${HEALTH_CHECK_KEY}" \
  "http://127.0.0.1:${PORT}/status/details" || true

echo
echo "========================================"
echo

wait "$PID"