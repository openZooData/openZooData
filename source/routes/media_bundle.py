"""
routes/media_bundle.py — Media-Bundle-Endpoint

GET /media-bundle/<zoo>
  → Liefert das vorbereitete Media-Bundle als ZIP.
  → Das Bundle wird beim Publish-Schritt (export_zoo) vorab generiert
    und unter ~/sqlite/<slug>_media_v<version>.zip abgelegt.
  → Versionierung via zoo.zoos.media_version (ETag + 304 Not Modified).
  → Auth: App-Token oder JWT.

Bundle-Struktur (generiert von tools/export/writer.py):
  <slug>_media/
    species/   <filename>.png
    location/  <filename>.png
    house/     <filename>.png
    enclosure/ <filename>.png
    zoo/       <filename>.png
"""

import os
import logging
import psycopg2.extras
from flask import Blueprint, jsonify, request, send_file
from db import get_pg_connection
from extensions import limiter
from helpers.auth_utils import require_app_token
from helpers.coordinates import is_valid_slug

media_bundle_bp = Blueprint("media_bundle", __name__)

SQLITE_DIR = os.path.join(os.path.expanduser("~"), "sqlite")


@media_bundle_bp.route("/media-bundle/<zoo>", methods=["GET"])
@limiter.limit("10 per minute")
def get_media_bundle(zoo):
    """
    Liefert das vorbereitete Media-Bundle für einen Zoo.
    Muss nach einem Publish verfügbar sein — 404 wenn noch kein Bundle existiert.
    """
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400

    user_id, err = require_app_token()
    if err:
        return err

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT media_version FROM zoo.zoos
                WHERE slug = %s AND is_active = TRUE
            """, (zoo,))
            row = cur.fetchone()
            if not row:
                return jsonify({"error": "Zoo not found"}), 404
            media_version = row["media_version"]
    except Exception:
        logging.exception(f"Exception in GET /media-bundle/{zoo}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg:
            pg.close()

    etag = f'"{media_version}"'

    # 304 Not Modified
    if request.headers.get("If-None-Match", "") == etag:
        return "", 304

    bundle_path = os.path.join(SQLITE_DIR, f"{zoo}_media_v{media_version}.zip")
    if not os.path.isfile(bundle_path):
        return jsonify({
            "error": "Media-Bundle noch nicht generiert — bitte erst publishen"
        }), 404

    response = send_file(
        bundle_path,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{zoo}_media_v{media_version}.zip"
    )
    response.headers["ETag"]            = etag
    response.headers["Cache-Control"]   = "public, max-age=3600"
    response.headers["X-Media-Version"] = str(media_version)
    return response
