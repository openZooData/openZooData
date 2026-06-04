"""
export/writer.py
----------------
SQLite-Schreiblogik: _do_export, export_zoo, _increment_data_version.
"""

import gzip
import logging
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path

from .schema import SCHEMA
from .fetch import (
    fetch_zoo, fetch_zoo_opening_hours, fetch_domains, fetch_location_types,
    fetch_taxonomy, fetch_iucn_status, fetch_iucn_trend, fetch_houses,
    fetch_house_opening_hours, fetch_enclosures, fetch_locations,
    fetch_location_species, fetch_opening_hours, fetch_species,
    fetch_species_texts, fetch_enclosure_species, fetch_feeding_times,
    fetch_births, fetch_geo_points, fetch_translations, fetch_media,
)

STATS_TABLES = [
    'species', 'species_texts', 'enclosures', 'enclosure_species',
    'feeding_times', 'locations', 'opening_hours', 'zoo_opening_hours',
    'house_opening_hours', 'births', 'geo_points', 'translations',
    'media', 'domains',
]


def _increment_data_version(pg, slug: str):
    with pg.cursor() as cur:
        cur.execute("""
            UPDATE zoos SET data_version = data_version + 1
            WHERE slug = %s
        """, (slug,))
    pg.commit()


def _do_export(pg, zoo_id: int, slug: str, output_path: Path):
    """Schreibt komprimierte SQLite nach output_path. output_path ist eine tmp-Datei."""
    tmp_sqlite = output_path.parent / f".tmp_sqlite_{slug}_{os.getpid()}.sqlite"
    try:
        db = sqlite3.connect(str(tmp_sqlite))
        db.executescript(SCHEMA)

        print(f"   Lade Daten aus PostgreSQL...")
        zoo_row           = fetch_zoo(pg, zoo_id)
        zoo_opening_hrs   = fetch_zoo_opening_hours(pg, zoo_id)
        domains           = fetch_domains(pg, zoo_id)
        location_types    = fetch_location_types(pg)
        taxonomy          = fetch_taxonomy(pg)
        iucn_status       = fetch_iucn_status(pg)
        iucn_trend        = fetch_iucn_trend(pg)
        houses            = fetch_houses(pg, zoo_id)
        house_opening_hrs = fetch_house_opening_hours(pg, zoo_id)
        enclosures        = fetch_enclosures(pg, zoo_id)
        locations         = fetch_locations(pg, zoo_id)
        location_species  = fetch_location_species(pg, zoo_id)
        opening_hrs       = fetch_opening_hours(pg, zoo_id)
        species           = fetch_species(pg, zoo_id)
        species_texts     = fetch_species_texts(pg, zoo_id)
        enc_species       = fetch_enclosure_species(pg, zoo_id)
        feeding_times     = fetch_feeding_times(pg, zoo_id)
        births            = fetch_births(pg, zoo_id)
        geo_points        = fetch_geo_points(pg, zoo_id)
        translations      = fetch_translations(pg, zoo_id)
        media             = fetch_media(pg, zoo_id)
        pg.commit()  # read-Transaktion beenden

        print(f"   Schreibe SQLite...")
        db.execute(
            "INSERT OR REPLACE INTO zoos VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            zoo_row
        )
        db.executemany(
            "INSERT OR REPLACE INTO domains VALUES (?,?,?,?,?,?,?,?,?)",
            [(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], float(r[8]) if r[8] else 1.0)
             for r in domains]
        )
        db.executemany("INSERT OR REPLACE INTO location_types VALUES (?,?,?,?,?)", location_types)
        db.executemany("INSERT OR REPLACE INTO taxonomy VALUES (?,?,?,?)", taxonomy)
        db.executemany("INSERT OR REPLACE INTO iucn_status VALUES (?,?,?,?)", iucn_status)
        db.executemany("INSERT OR REPLACE INTO iucn_trend VALUES (?,?,?)", iucn_trend)
        db.executemany("INSERT OR REPLACE INTO houses VALUES (?,?,?,?,?,?,?)", houses)
        db.executemany("INSERT OR REPLACE INTO zoo_opening_hours VALUES (?,?,?,?,?,?,?,?)", zoo_opening_hrs)
        db.executemany("INSERT OR REPLACE INTO house_opening_hours VALUES (?,?,?,?,?,?,?,?)", house_opening_hrs)
        db.executemany("INSERT OR REPLACE INTO enclosures VALUES (?,?,?,?,?,?,?,?,?,?)", enclosures)
        db.executemany("INSERT OR REPLACE INTO locations VALUES (?,?,?,?,?,?,?,?,?,?,?)", locations)
        db.executemany("INSERT OR REPLACE INTO location_species VALUES (?,?,?)", location_species)
        db.executemany("INSERT OR REPLACE INTO opening_hours VALUES (?,?,?,?,?,?,?,?)", opening_hrs)
        db.executemany("INSERT OR REPLACE INTO species VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", species)
        db.executemany("INSERT OR REPLACE INTO species_texts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", species_texts)
        db.executemany("INSERT OR REPLACE INTO enclosure_species VALUES (?,?,?,?,?,?,?)", enc_species)
        db.executemany("INSERT OR REPLACE INTO feeding_times VALUES (?,?,?,?,?,?,?)", feeding_times)
        db.executemany("INSERT OR REPLACE INTO births VALUES (?,?,?,?,?,?,?,?,?)", births)
        db.executemany("INSERT OR REPLACE INTO geo_points VALUES (?,?,?,?,?,?,?)", geo_points)
        db.executemany("INSERT OR REPLACE INTO translations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", translations)
        db.executemany("INSERT OR REPLACE INTO media VALUES (?,?,?,?,?,?,?,?,?)", media)
        db.commit()
        db.close()

        # Statistik
        db = sqlite3.connect(str(tmp_sqlite))
        print(f"   Statistik:")
        for table in STATS_TABLES:
            count = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if count > 0:
                print(f"      {table}: {count}")
        db.close()

        # gzip
        with open(str(tmp_sqlite), 'rb') as f_in:
            with gzip.open(str(output_path), 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)

    finally:
        if tmp_sqlite.exists():
            tmp_sqlite.unlink()


def export_zoo(pg, zoo_id: int, slug: str, output_dir: Path) -> Path:
    final_path = output_dir / f"{slug}.sqlite.gz"

    with tempfile.NamedTemporaryFile(
        dir=output_dir,
        prefix=f".tmp_{slug}_",
        suffix=".sqlite.gz",
        delete=False
    ) as tmp_file:
        tmp_path = Path(tmp_file.name)

    try:
        # Migration v7: data_version wird NICHT mehr hier erhöht.
        # Das Increment erfolgt ausschließlich in routes/publish.py
        # nach erfolgreichem Export — verhindert doppeltes Increment.
        # Funktion _increment_data_version() bleibt als Fallback erhalten
        # aber wird nicht mehr automatisch aufgerufen.
        _do_export(pg, zoo_id, slug, tmp_path)

        if not tmp_path.is_file():
            raise RuntimeError("Export hat keine Datei erzeugt")
        size = tmp_path.stat().st_size
        if size < 1024:
            raise RuntimeError(f"Export zu klein: {size} bytes")

        os.replace(tmp_path, final_path)
        logging.info(f"Export {slug} OK: {final_path} ({size / 1024:.1f} KB)")

    except Exception as e:
        if tmp_path.exists():
            tmp_path.unlink()
        logging.error(f"Export {slug} fehlgeschlagen: {e}")
        raise

    return final_path
