#!/usr/bin/env python3
"""
tools/check_translations_cron.py
---------------------------------
Cronjob-Script: Prüft alle 10 Minuten ob Species mit
translations_valid = FALSE existieren und startet für jede davon
den enrich_species_texts.py Job (alle Sprachen, alle Felder).

Aufruf via cron (alle 10 Minuten):
    */10 * * * * /usr/home/openzk/api/venv/bin/python \
        /usr/home/openzk/api/openZooData/source/tools/check_translations_cron.py \
        >> /usr/home/openzk/api/openZooData/logs/translations_cron.log 2>&1

Oder manuell:
    python3 source/tools/check_translations_cron.py
    python3 source/tools/check_translations_cron.py --dry-run
"""

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)


def load_env():
    env = {}
    for path in [Path(__file__).parent.parent.parent / ".env",
                 Path.home() / ".env"]:
        if path.exists():
            for line in path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
            break
    return env


env = load_env()

PG_CONFIG = {
    "host":     env.get("PG_HOST"),
    "user":     env.get("PG_USER"),
    "password": env.get("PG_PASSWORD"),
    "dbname":   env.get("PG_NAME", "zooguide"),
    "port":     int(env.get("PG_PORT", "5432")),
    "options":  "-c search_path=zoo,public",
}

ENRICH_SCRIPT = Path(__file__).parent / "enrich_species_texts.py"
PYTHON        = sys.executable


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Nur anzeigen, nichts ausführen")
    args = parser.parse_args()

    try:
        pg = psycopg2.connect(**PG_CONFIG)
    except Exception as e:
        logging.error(f"DB-Verbindung fehlgeschlagen: {e}")
        sys.exit(1)

    with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT s.id, s.german_name, s.wikidata_id,
                   count(st.id) AS text_rows
            FROM zoo.species s
            LEFT JOIN zoo.species_texts st ON st.species_id = s.id
            WHERE s.translations_valid = FALSE
              AND s.id_valid = TRUE
            GROUP BY s.id, s.german_name, s.wikidata_id
            ORDER BY s.german_name
        """)
        pending = cur.fetchall()

    pg.close()

    if not pending:
        logging.info("Alle Species translations_valid — nichts zu tun")
        return

    logging.info(f"{len(pending)} Species mit translations_valid = FALSE:")
    for s in pending:
        logging.info(f"  id={s['id']}: {s['german_name']} "
                     f"({s['wikidata_id']}) — {s['text_rows']} Textzeilen vorhanden")

    if args.dry_run:
        logging.info("Dry-run — kein enrich_species_texts.py gestartet")
        return

    if not ENRICH_SCRIPT.exists():
        logging.error(f"Script nicht gefunden: {ENRICH_SCRIPT}")
        sys.exit(1)

    # Pro Species enrich_species_texts.py aufrufen (alle Sprachen, alle Felder)
    for s in pending:
        logging.info(f"Starte Enrichment für species_id={s['id']} ({s['german_name']})...")
        try:
            result = subprocess.run(
                [PYTHON, str(ENRICH_SCRIPT), "--species", str(s["id"])],
                capture_output=True,
                text=True,
                timeout=600  # max 10 Minuten pro Species
            )
            if result.returncode == 0:
                logging.info(f"  ✓ {s['german_name']} fertig")
            else:
                logging.error(
                    f"  ✗ {s['german_name']} fehlgeschlagen "
                    f"(exit {result.returncode}): {result.stderr[:200]}"
                )
        except subprocess.TimeoutExpired:
            logging.error(f"  ✗ {s['german_name']} Timeout nach 10 Minuten")
        except Exception as e:
            logging.error(f"  ✗ {s['german_name']} Fehler: {e}")


if __name__ == "__main__":
    main()
