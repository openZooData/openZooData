#!/usr/bin/env bash
# start_local.sh — Lokaler Entwicklungsserver (Mac)
# Verwendung: ./start_local.sh [port]

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${1:-5001}"

# Prüfen ob venv existiert
if [[ ! -f "$ROOT_DIR/venv/bin/python3" ]]; then
    echo "ERROR: venv nicht gefunden. Bitte zuerst anlegen:"
    echo "  /opt/homebrew/bin/python3.11 -m venv venv"
    echo "  source venv/bin/activate"
    echo "  pip install -r source/requirements.txt"
    exit 1
fi

# Prüfen ob .env existiert
if [[ ! -f "$ROOT_DIR/.env" ]]; then
    echo "ERROR: .env nicht gefunden unter $ROOT_DIR/.env"
    exit 1
fi

echo "========================================"
echo "  openZooData — Lokaler Dev-Server"
echo "  Port: $PORT"
echo "  DB:   TrueNAS ($(grep PG_HOST "$ROOT_DIR/.env" | cut -d= -f2))"
echo "========================================"

export FLASK_HOST=0.0.0.0
exec "$ROOT_DIR/venv/bin/python3" "$ROOT_DIR/source/app.py"
