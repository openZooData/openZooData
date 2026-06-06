#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

if pkill -f "gunicorn.*app:app"; then
    echo "OpenZooData Gunicorn stopped."
    rm -f "$ROOT_DIR/logs/gunicorn.pid"
else
    echo "No Gunicorn process found."
fi