#!/usr/bin/env python3
"""
feedback_aggregate.py — Täglicher Cron-Job: Typ 9/10 aggregieren + löschen
===========================================================================
Aggregiert text_helpful (9) und text_excellent (10) Rohdaten in Zählspalten
auf enrichment_texts, löscht danach die Rohdaten (DSGVO-konform).

Cron-Eintrag (täglich 03:00):
    0 3 * * * /usr/home/gkgwsr/myapi-env/bin/python3 /usr/home/gkgwsr/tools/feedback_aggregate.py

Ausführen:
    source ~/myapi-env/bin/activate
    python3 tools/feedback_aggregate.py
    python3 tools/feedback_aggregate.py --dry-run   # nur anzeigen, nichts löschen
"""

import os
import sys
import argparse
import logging
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.expanduser("~"), "tools", ".env"))

import psycopg2
import psycopg2.extras

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

PG_CONFIG = {
    "host":    os.getenv("PG_HOST"),
    "user":    os.getenv("PG_USER"),
    "password":os.getenv("PG_PASSWORD"),
    "dbname":  os.getenv("PG_DATABASE", "zooguide"),
    "port":    int(os.getenv("PG_PORT", "5432")),
    "options": "-c search_path=zoo,public"
}

# Typ-IDs für text_helpful und text_excellent
TYPE_HELPFUL   = 9
TYPE_EXCELLENT = 10


def aggregate_and_cleanup(dry_run=False):
    pg = psycopg2.connect(**PG_CONFIG)

    try:
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:

            # ------------------------------------------------------------------
            # 1. Neue Bewertungen zählen (seit letztem Lauf)
            # ------------------------------------------------------------------
            cur.execute("""
                SELECT
                    value_enrichment_text_id                          AS text_id,
                    COUNT(*) FILTER (WHERE feedback_type_id = %s)     AS new_helpful,
                    COUNT(*) FILTER (WHERE feedback_type_id = %s)     AS new_excellent
                FROM feedback
                WHERE feedback_type_id IN (%s, %s)
                GROUP BY value_enrichment_text_id
            """, (TYPE_HELPFUL, TYPE_EXCELLENT, TYPE_HELPFUL, TYPE_EXCELLENT))
            counts = cur.fetchall()

            if not counts:
                log.info("Keine neuen Bewertungen — nichts zu tun.")
                return

            log.info(f"Texte mit neuen Bewertungen: {len(counts)}")

            # ------------------------------------------------------------------
            # 2. Zählspalten auf enrichment_texts aktualisieren
            # ------------------------------------------------------------------
            for row in counts:
                log.info(
                    f"  enrichment_text {row['text_id']}: "
                    f"+{row['new_helpful']} helpful, +{row['new_excellent']} excellent"
                )
                if not dry_run:
                    cur.execute("""
                        UPDATE enrichment_texts SET
                            helpful_count   = helpful_count   + %s,
                            excellent_count = excellent_count + %s
                        WHERE id = %s
                    """, (row["new_helpful"], row["new_excellent"], row["text_id"]))

            # ------------------------------------------------------------------
            # 3. Rohdaten löschen (DSGVO: contributor_id nicht länger als nötig)
            # ------------------------------------------------------------------
            cur.execute("""
                SELECT COUNT(*) AS total FROM feedback
                WHERE feedback_type_id IN (%s, %s)
            """, (TYPE_HELPFUL, TYPE_EXCELLENT))
            total_rows = cur.fetchone()["total"]
            log.info(f"Rohdaten zum Löschen: {total_rows} Zeilen")

            if not dry_run:
                cur.execute("""
                    DELETE FROM feedback
                    WHERE feedback_type_id IN (%s, %s)
                """, (TYPE_HELPFUL, TYPE_EXCELLENT))
                deleted = cur.rowcount
                log.info(f"Gelöscht: {deleted} Zeilen")

        if not dry_run:
            pg.commit()
            log.info("Commit erfolgreich.")
        else:
            pg.rollback()
            log.info("Dry-run — kein Commit.")

    except Exception as e:
        pg.rollback()
        log.error(f"Fehler: {e}")
        raise
    finally:
        pg.close()


def main():
    parser = argparse.ArgumentParser(description="Feedback Typ 9/10 aggregieren + löschen")
    parser.add_argument("--dry-run", action="store_true",
                        help="Nur anzeigen, nichts schreiben oder löschen")
    args = parser.parse_args()

    if args.dry_run:
        log.info("=== DRY RUN — keine Änderungen ===")

    aggregate_and_cleanup(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
