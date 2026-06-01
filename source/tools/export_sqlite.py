#!/usr/bin/env python3
"""
export_sqlite.py
----------------
Exportiert Zoo-Daten aus PostgreSQL in SQLite-Dateien.
Die SQLite-Dateien spiegeln das komplette Schema — direkt
nutzbar von der iOS-App via GRDB.

Aufruf:
    python3 export_sqlite.py --all                    # alle aktiven Zoos
    python3 export_sqlite.py --zoo zoo_berlin         # einzelner Zoo
    python3 export_sqlite.py --zoo zoo_berlin --zoo zoo_muenster  # mehrere

Output:
    ~/sqlite/<slug>.sqlite.gz (komprimiert, für API-Auslieferung)
"""

import sys
import logging
import psycopg2

from export import PG_CONFIG, OUTPUT_DIR, get_zoo_ids, export_zoo
from export.cli import parse_args

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def main():
    args = parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Zoo Guide — SQLite Export")
    print("=" * 50)

    print("\nVerbinde mit PostgreSQL...")
    try:
        pg = psycopg2.connect(**PG_CONFIG)
        print("   Verbunden")
    except Exception as e:
        print(f"   Fehler: {e}")
        sys.exit(1)

    slugs    = args.zoos or []
    zoo_list = get_zoo_ids(pg, slugs)

    if not zoo_list:
        print("Keine Zoos gefunden")
        sys.exit(1)

    print(f"\n{len(zoo_list)} Zoo(s): {[z[1] for z in zoo_list]}")

    errors = []
    for zoo_id, slug in zoo_list:
        print(f"\n--- {slug} ---")
        try:
            export_zoo(pg, zoo_id, slug, OUTPUT_DIR)
        except Exception as e:
            errors.append((slug, str(e)))

    pg.close()

    if errors:
        print(f"\nFehler bei {len(errors)} Zoo(s):")
        for slug, msg in errors:
            print(f"  {slug}: {msg}")
        sys.exit(1)
    else:
        print(f"\nFertig. Dateien in: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
