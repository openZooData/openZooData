#!/usr/bin/env bash

set -euo pipefail

PID_FILE="logs/gunicorn.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "PID file not found."
    exit 1
fi

PID=$(cat "$PID_FILE")

if kill "$PID" 2>/dev/null; then
    rm -f "$PID_FILE"
    echo "Killed OpenZooData server process (PID $PID)."
else
    echo "Process $PID is not running."
    rm -f "$PID_FILE"
fi