"""
export/config.py
----------------
Konfiguration: PostgreSQL-Verbindung und Ausgabepfad.
"""

from pathlib import Path
from typing import Dict


def load_env() -> Dict[str, str]:
    env = {}
    for path in [Path(".env"), Path.home() / ".env"]:
        if path.exists():
            for line in path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
            break
    return env


env = load_env()

PG_CONFIG = {
    "host":     env.get("PG_HOST"),
    "user":     env.get("PG_USER"),
    "password": env.get("PG_PASSWORD"),
    "dbname":   env.get("PG_NAME"),
    "port":     int(env.get("PG_PORT", "5432")),
    "options":  "-c search_path=zoo,public",
}

OUTPUT_DIR = Path.home() / "sqlite"
