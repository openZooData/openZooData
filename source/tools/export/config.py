"""
export/config.py
----------------
Konfiguration: PostgreSQL-Verbindung und Ausgabepfad.
"""

import os
import sys
from pathlib import Path

# source/ auf sys.path damit helpers.env_loader importierbar ist
# (export/config.py liegt in source/tools/export/ -> 2 Ebenen hoch = source/)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from helpers.env_loader import load_env

# Zentrale .env-Ladung -> os.environ. Idempotent (siehe generate_species_icons.py).
try:
    load_env()
except RuntimeError:
    pass  # Variablen evtl. schon vom Eltern-Prozess vererbt

PG_CONFIG = {
    "host":     os.environ.get("PG_HOST"),
    "user":     os.environ.get("PG_USER"),
    "password": os.environ.get("PG_PASSWORD"),
    "dbname":   os.environ.get("PG_NAME"),
    "port":     int(os.environ.get("PG_PORT", "5432")),
    "options":  "-c search_path=zoo,public",
}

OUTPUT_DIR  = Path.home() / "sqlite"
STORAGE_DIR = os.environ.get("STORAGE_DIR",
                       str(Path(__file__).resolve().parent.parent.parent.parent / "media"))
