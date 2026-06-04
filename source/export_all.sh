#!/bin/bash
echo "Starte SQLite Export..."
source ~/myapi-env/bin/activate
python3 ~/tools/export_sqlite.py --all
echo "Fertig."
