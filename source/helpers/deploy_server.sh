#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=”$(cd “$(dirname “${BASH_SOURCE[0]}”)/../..” && pwd)”

cd “$ROOT_DIR”

echo “========================================”
echo “Pull from git”
echo “========================================”

git pull

echo
echo “========================================”
echo “Install requirements”
echo “========================================”

source ../venv/bin/activate
pip install -r source/requirements.txt

echo
echo “========================================”
echo “Stop server”
echo “========================================”

“$ROOT_DIR/source/helpers/stop_server.sh”

echo
echo “========================================”
echo “Start server”
echo “========================================”

“$ROOT_DIR/source/helpers/start_server.sh”

echo
echo “Deploy finished.”