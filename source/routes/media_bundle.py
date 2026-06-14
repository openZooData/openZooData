"""
routes/media_bundle.py — Media-Bundle-Endpoint

GET /media-bundle/<zoo>
  → Liefert alle Bilder eines Zoos als gzip-komprimiertes ZIP-Archiv.
  → Enthält: Locations, Houses, Enclosures + Species die in diesem Zoo vorkommen.
  → Versionierung via zoo.zoos.media_version (ETag + 304 Not Modified).
  → Auth: App-Token oder JWT.

Bundle-Struktur:
  zoo_berlin_media/
    species/
      <filename>.jpg
    enclosure/
      <filename>.jpg
    house/
      <filename>.jpg
    location/
      <filename>.jpg
    zoo/
      <filename>.jpg
"""

import io
import logging
import os
import zipfile

import psycopg2.extras
from flask import Blueprint, jsonify, request, send_file
from db import get_pg_connection
from extensions import limiter
from helpers.authz import require_authenticated
from helpers.coordinates import is_valid_slug
from storage import FilesystemBackend

media_bundle_bp = Blueprint("media_bundle", __name__)

storage = FilesystemBackend()


@media_bundle_bp.route("/media-bundle/<zoo>", methods=["GET"])
@limiter.limit("10 per minute")
def get_media_bundle(zoo):
    """
    Media-Bundle für einen Zoo — alle Bilder als ZIP.
    Versionierung: ETag = media_version, 304 wenn unverändert.
    Auth: App-Token oder JWT.
    """
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400

    user_id, err = require_authenticated()
    if err:
        return err

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Zoo-Metadaten + media_version
            cur.execute("""
                SELECT id, slug, media_version
                FROM zoo.zoos
                WHERE slug = %s AND is_active = TRUE
            """, (zoo,))
            zoo_row = cur.fetchone()
            if not zoo_row:
                return jsonify({"error": "Zoo not found"}), 404

            media_version = zoo_row["media_version"]
            etag = f'"{media_version}"'

            # 304 Not Modified
            if_none_match = request.headers.get("If-None-Match", "")
            if if_none_match == etag:
                return "", 304

            zoo_id = zoo_row["id"]

            # 1. Zoo-spezifische Media-Einträge (Locations, Houses, Enclosures, etc.)
            cur.execute("""
                SELECT storage_path, entity_type, filename
                FROM zoo.media
                WHERE zoo_id = %s
                ORDER BY entity_type, filename
            """, (zoo_id,))
            zoo_media_rows = cur.fetchall()

            # 2. Species-Bilder die in diesem Zoo vorkommen
            cur.execute("""
                SELECT DISTINCT m.storage_path, m.entity_type, m.filename
                FROM zoo.media m
                JOIN zoo.species s ON s.id = m.entity_id
                    AND m.entity_type = 'species'
                JOIN zoo.enclosure_species es ON es.species_id = s.id
                LEFT JOIN zoo.enclosures e ON e.id = es.enclosure_id
                LEFT JOIN zoo.houses h ON h.id = es.house_id
                LEFT JOIN zoo.zoos z1 ON z1.id = e.zoo_id
                LEFT JOIN zoo.zoos z2 ON z2.id = h.zoo_id
                WHERE (z1.slug = %s OR z2.slug = %s)
                ORDER BY m.filename
            """, (zoo, zoo))
            species_media_rows = cur.fetchall()

            media_rows = list(zoo_media_rows) + list(species_media_rows)

        if not media_rows:
            return jsonify({"error": "No media found"}), 404

        # ZIP im Speicher aufbauen
        buf = io.BytesIO()
        prefix = f"{zoo}_media"
        added = set()  # Duplikate vermeiden

        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for row in media_rows:
                storage_path = row["storage_path"]
                entity_type  = row["entity_type"]
                filename     = row["filename"]

                arcname = f"{prefix}/{entity_type}/{filename}"
                if arcname in added:
                    continue
                added.add(arcname)

                full_path = storage.full_path(os.path.join(storage_path, filename))
                if not os.path.isfile(full_path):
                    logging.warning(f"Media file not found: {full_path}")
                    continue

                zf.write(full_path, arcname=arcname)

        buf.seek(0)
        bundle_filename = f"{zoo}_media_v{media_version}.zip"

        response = send_file(
            buf,
            mimetype="application/zip",
            as_attachment=True,
            download_name=bundle_filename
        )
        response.headers["ETag"]             = etag
        response.headers["Cache-Control"]    = "public, max-age=3600"
        response.headers["X-Media-Version"]  = str(media_version)
        return response

    except Exception:
        logging.exception(f"Exception in GET /media-bundle/{zoo}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg:
            pg.close()
