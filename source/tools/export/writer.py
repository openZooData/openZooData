"""
export/writer.py
----------------
SQLite-Schreiblogik: _do_export, export_zoo, _increment_data_version.

media_version wird NUR hochgezählt, wenn sich der Inhalt der Media-Dateien
tatsächlich geändert hat (Content-Hash-Vergleich gegen zoo.zoos.media_hash).
Voraussetzung: Spalte zoo.zoos.media_hash TEXT (Migration siehe unten).
"""

import gzip
import hashlib
import logging
import os
import shutil
import sqlite3
import tempfile
import zipfile
from pathlib import Path

from .config import PG_CONFIG, OUTPUT_DIR, STORAGE_DIR
from .schema import SCHEMA
from .fetch import (    fetch_zoo, fetch_zoo_opening_hours, fetch_domains, fetch_location_types,
    fetch_taxonomy, fetch_iucn_status, fetch_iucn_trend, fetch_houses,
    fetch_house_opening_hours, fetch_enclosures, fetch_locations,
    fetch_location_species, fetch_opening_hours, fetch_species,
    fetch_species_texts, fetch_enclosure_species, fetch_feeding_times,
    fetch_births, fetch_geo_points, fetch_translations, fetch_media,
)
from helpers.taxonomy_sync import sync_missing_taxonomy

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
        db.executemany("INSERT OR REPLACE INTO species VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", species)
        db.executemany("INSERT OR REPLACE INTO species_texts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", species_texts)
        db.executemany("INSERT OR REPLACE INTO enclosure_species VALUES (?,?,?,?,?,?,?,?,?,?,?)", enc_species)
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


def build_media_bundle(pg, zoo_id: int, slug: str, output_dir: Path) -> Path:
    """
    Baut das Media-Bundle als ZIP und entscheidet selbstständig, ob die
    media_version hochgezählt wird.

    Ablauf:
      1) ZIP in temp schreiben, dabei SHA256-Content-Hash bilden
         (über arcname + Inhaltslänge + Inhaltsbytes, sortiert nach arcname).
      2) Aktuelle media_version + media_hash aus zoo.zoos lesen.
      3) Hash unverändert UND aktuelles Bundle existiert auf Disk
         -> nichts tun, bestehendes Bundle zurückgeben (KEIN Bump,
            kein Client-Re-Download).
      4) Sonst (Inhalt geändert oder Bundle fehlt):
         -> media_version + 1, ZIP als <slug>_media_v<neu>.zip ablegen,
            DB (media_version, media_hash) aktualisieren, alte Bundles löschen.

    ZIP-Struktur: <slug>_media/<entity_type>/<filename>
    """
    prefix      = f"{slug}_media"
    storage_dir = Path(STORAGE_DIR)
    tmp_path    = output_dir / f".tmp_bundle_{slug}_{os.getpid()}.zip"

    try:
        with pg.cursor() as cur:
            # 1) Zoo-spezifische Media-Einträge
            cur.execute("""
                SELECT storage_path, entity_type, filename
                FROM zoo.media
                WHERE zoo_id = %s
                ORDER BY entity_type, filename
            """, (zoo_id,))
            zoo_media = cur.fetchall()

            # 2) Species-Bilder die in diesem Zoo vorkommen
            cur.execute("""
                SELECT DISTINCT m.storage_path, m.entity_type, m.filename
                FROM zoo.media m
                JOIN zoo.species s ON s.id = m.entity_id
                    AND m.entity_type = 'species'
                JOIN zoo.enclosure_species es ON es.species_id = s.id
                WHERE es.zoo_id = %s
                ORDER BY m.filename
            """, (zoo_id,))
            species_media = cur.fetchall()

        media_rows = list(zoo_media) + list(species_media)

        # Eindeutige Einträge, deterministisch nach arcname sortiert
        # -> stabiler Hash, unabhängig von Query-Reihenfolge.
        entries = []  # (arcname, full_path)
        seen = set()
        for storage_path, entity_type, filename in media_rows:
            arcname = f"{prefix}/{entity_type}/{filename}"
            if arcname in seen:
                continue
            seen.add(arcname)
            entries.append((arcname, storage_dir / storage_path / filename))
        entries.sort(key=lambda e: e[0])

        hasher  = hashlib.sha256()
        added   = 0
        missing = 0

        with zipfile.ZipFile(str(tmp_path), mode="w",
                             compression=zipfile.ZIP_DEFLATED) as zf:
            for arcname, full_path in entries:
                if not full_path.is_file():
                    logging.warning(f"Media bundle: Datei nicht gefunden: {full_path}")
                    missing += 1
                    continue
                data = full_path.read_bytes()
                # Hash über Pfad + Länge + Inhalt
                # -> erkennt Inhalt, Umbenennung, Add/Remove
                hasher.update(arcname.encode("utf-8"))
                hasher.update(len(data).to_bytes(8, "big"))
                hasher.update(data)
                zf.writestr(arcname, data)
                added += 1

        if not tmp_path.is_file() or tmp_path.stat().st_size < 22:
            raise RuntimeError("Media-Bundle leer oder fehlgeschlagen")

        content_hash = hasher.hexdigest()

        # Aktuellen Stand lesen
        with pg.cursor() as cur:
            cur.execute("""
                SELECT media_version, media_hash
                FROM zoo.zoos WHERE id = %s
            """, (zoo_id,))
            row = cur.fetchone()
            cur_version = row[0] if row and row[0] is not None else 0
            cur_hash    = row[1] if row else None

        current_bundle = output_dir / f"{slug}_media_v{cur_version}.zip"

        # Unverändert UND aktuelles Bundle existiert -> nichts tun
        if content_hash == cur_hash and current_bundle.is_file():
            tmp_path.unlink()
            logging.info(f"Media-Bundle {slug} unverändert (v{cur_version}, "
                         f"{added} Dateien) — kein Bump")
            return current_bundle

        # Inhalt geändert (oder Bundle fehlt) -> Version hochzählen
        new_version = cur_version + 1
        final_path  = output_dir / f"{slug}_media_v{new_version}.zip"
        os.replace(tmp_path, final_path)

        with pg.cursor() as cur:
            cur.execute("""
                UPDATE zoo.zoos
                SET media_version = %s, media_hash = %s
                WHERE id = %s
            """, (new_version, content_hash, zoo_id))
        pg.commit()

        # Alte Bundle-Versionen desselben Zoos aufräumen
        for old in output_dir.glob(f"{slug}_media_v*.zip"):
            if old != final_path:
                try:
                    old.unlink()
                    logging.info(f"Altes Bundle gelöscht: {old.name}")
                except OSError:
                    pass

        logging.info(f"Media-Bundle {slug} NEU: v{new_version} "
                     f"({added} Dateien, {missing} fehlend, "
                     f"{final_path.stat().st_size / 1024:.1f} KB)")
        return final_path

    except Exception as e:
        if tmp_path.exists():
            tmp_path.unlink()
        logging.error(f"Media-Bundle {slug} fehlgeschlagen: {e}")
        raise


def export_zoo(pg, zoo_id: int, slug: str, output_dir: Path) -> Path:
    final_path = output_dir / f"{slug}.sqlite.gz"

    # Taxonomy-Sync: nur fehlende QIDs bei Wikidata abfragen
    # Schlägt fehl → Warnung, Export läuft trotzdem weiter
    sync_missing_taxonomy(pg)

    with tempfile.NamedTemporaryFile(
        dir=output_dir,
        prefix=f".tmp_{slug}_",
        suffix=".sqlite.gz",
        delete=False
    ) as tmp_file:
        tmp_path = Path(tmp_file.name)

    try:
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

    # Media-Bundle nach erfolgreichem SQLite-Export bauen.
    # build_media_bundle entscheidet selbst, ob media_version hochgezählt wird
    # (nur bei tatsächlicher Änderung der Media-Dateien).
    try:
        build_media_bundle(pg, zoo_id, slug, output_dir)
    except Exception:
        # Media-Bundle-Fehler darf den SQLite-Export nicht rückgängig machen
        logging.exception(f"Media-Bundle {slug} fehlgeschlagen (SQLite-Export bleibt)")

    return final_path
