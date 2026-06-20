"""
helpers/env_loader.py — Zentrale .env-Ladelogik für openZooData

Alle Dateien im Projekt (app.py, extensions.py, tools/*) verwenden
diese Funktion statt eigener load_dotenv()-Aufrufe.

Suchreihenfolge:
  1. openZooData/.env           (lokale Entwicklung Mac + Standard)
  2. ~/api/openZooData/.env     (Hetzner-Server)
  3. ~/.env                     (Fallback legacy)

Die erste gefundene Datei gewinnt. Keine Datei → RuntimeError.
"""

from pathlib import Path
from dotenv import load_dotenv


def load_env() -> Path:
    """
    Lädt die .env-Datei aus dem ersten gefundenen Pfad.
    Gibt den tatsächlich geladenen Pfad zurück.
    Wirft RuntimeError wenn keine .env gefunden wurde.
    """
    candidates = [
        # 1. Zwei Ebenen über diesem File: openZooData/.env
        Path(__file__).resolve().parents[2] / ".env",
        # 2. Hetzner-Server: ~/api/openZooData/.env
        Path.home() / "api" / "openZooData" / ".env",
        # 3. Legacy-Fallback
        Path.home() / ".env",
    ]

    for path in candidates:
        if path.exists():
            load_dotenv(dotenv_path=path)
            return path

    raise RuntimeError(
        "Keine .env-Datei gefunden. Gesucht in:\n"
        + "\n".join(f"  {p}" for p in candidates)
    )
