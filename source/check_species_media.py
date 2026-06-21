"""
check_species_media.py

Prüft für alle Species ohne zoo.media Eintrag ob ein Bild
im media/species/ Verzeichnis vorhanden ist.

Ausgabe:
  - Species mit vorhandenem Bild aber fehlendem DB-Eintrag
  - Species ohne Bild (müssen von Wikidata nachgeladen werden)
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from helpers.env_loader import load_env
load_env()

import psycopg2
import psycopg2.extras
from storage import STORAGE_DIR

SPECIES_MEDIA_DIR = os.path.join(STORAGE_DIR, "media", "species")

def get_db_connection():
    import os
    return psycopg2.connect(
        host=os.getenv("PG_HOST"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
        dbname=os.getenv("PG_NAME", "ozd_zoo"),
        port=int(os.getenv("PG_PORT", "5432")),
        options="-c search_path=zoo,public"
    )

def main():
    conn = get_db_connection()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT s.id, s.german_name, s.latin_name, s.wikidata_id
            FROM zoo.species s
            WHERE s.id_valid = TRUE
            AND NOT EXISTS (
                SELECT 1 FROM zoo.media m
                WHERE m.entity_type = 'species'
                AND m.entity_id = s.id
            )
            ORDER BY s.german_name
        """)
        species_list = cur.fetchall()

    print(f"Species ohne Media-Eintrag: {len(species_list)}\n")

    # Dateien im media/species/ Verzeichnis lesen
    if os.path.isdir(SPECIES_MEDIA_DIR):
        existing_files = os.listdir(SPECIES_MEDIA_DIR)
    else:
        print(f"ERROR: Verzeichnis nicht gefunden: {SPECIES_MEDIA_DIR}")
        return

    found     = []
    not_found = []

    for s in species_list:
        wikidata_id = s["wikidata_id"]
        if not wikidata_id:
            not_found.append((s, None))
            continue

        # Datei suchen: Q<id>_*.png oder Q<id>_*.jpg
        matches = [f for f in existing_files if f.startswith(f"{wikidata_id}_")]
        if matches:
            found.append((s, matches[0]))
        else:
            not_found.append((s, None))

    print(f"✅ Bild vorhanden aber kein DB-Eintrag: {len(found)}")
    for s, filename in found:
        print(f"   {s['wikidata_id']:15} {s['german_name']:40} → {filename}")

    print(f"\n❌ Kein Bild vorhanden (Wikidata-Download nötig): {len(not_found)}")
    for s, _ in not_found:
        wid = s['wikidata_id'] or 'KEIN WIKIDATA'
        print(f"   {wid:15} {s['german_name']:40} {s['latin_name'] or ''}")

    conn.close()

    # SQL für fehlende DB-Einträge generieren
    if found:
        print(f"\n-- SQL zum Eintragen der vorhandenen Bilder:")
        print(f"-- Ausführen in Postico auf der Zoo-DB\n")
        for s, filename in found:
            print(f"""INSERT INTO zoo.media (entity_type, entity_id, filename, storage_path, mime_type, label, zoo_id)
VALUES ('species', {s['id']}, '{filename}', 'species/', 'image/png', 'icon', NULL)
ON CONFLICT DO NOTHING;""")

if __name__ == "__main__":
    main()
