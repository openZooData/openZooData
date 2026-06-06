import os
import uuid
import logging
import psycopg2.extras
from mimetypes import guess_type
from flask import Blueprint, jsonify, request, send_file

from helpers.authz import require_zoo_access
from helpers.coordinates import is_valid_slug
from db import get_pg_connection
from extensions import limiter
from storage import storage, STORAGE_DIR

media_bp = Blueprint("media", __name__)

# Fix 3: SVG entfernt — kann <script> enthalten (Stored XSS)
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

# entity_type Whitelist — verhindert beliebige Strings im URL-Parameter.
# Tabellennamen werden nur aus dieser Map bezogen (sicher für f-string).
ENTITY_TABLE_MAP = {
    "zoo":               "zoos",
    "species":           "species",
    "enclosure":         "enclosures",
    "enclosure_species": "enclosure_species",
    "house":             "houses",
    "location":          "locations",
}


@media_bp.route("/api/v1/files/<path:storage_path>", methods=["GET"])
@limiter.limit("120 per minute")
def serve_file(storage_path):
    # Fix 1: Zoo aus Pfad-Segment ableiten — kein ?zoo= Parameter nötig.
    # storage_path hat das Format "<zoo>/<entity_type>/<filename>".
    # Erstes Segment IS der Zoo → für Auth und Traversal-Schutz verwenden.
    first_segment = os.path.normpath(storage_path).split(os.sep, 1)[0]
    if not is_valid_slug(first_segment):
        return jsonify({"error": "Invalid path"}), 400
    user_id, err = require_zoo_access(first_segment, 'read')
    if err: return err

    full_path    = storage.full_path(storage_path)
    real_storage = os.path.realpath(STORAGE_DIR)
    real_full    = os.path.realpath(full_path)
    if os.path.commonpath([real_full, real_storage]) != real_storage:
        return jsonify({"error": "Unauthorized"}), 403
    if not os.path.isfile(real_full):
        return jsonify({"error": "Not found"}), 404
    mimetype, _ = guess_type(real_full)
    return send_file(real_full, mimetype=mimetype or "application/octet-stream")


@media_bp.route("/api/v1/media/<entity_type>/<int:entity_id>", methods=["GET"])
@limiter.limit("60 per minute")
def list_media(entity_type, entity_id):
    if entity_type not in ENTITY_TABLE_MAP:
        return jsonify({"error": "Invalid entity_type"}), 400

    from helpers.authz import require_authenticated
    if entity_type == "species":
        user_id, err = require_authenticated()
        if err: return err
        zoo = ""
    else:
        zoo = request.args.get("zoo", "")
        user_id, err = require_zoo_access(zoo, 'read')
        if err: return err

    conn = None
    try:
        conn = get_pg_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Fix 3: Zoo-Filter für zoo-gebundene Entities.
            # species ist global (kein zoo_id) → kein Filter nötig.
            # Alle anderen Entities sind zoo-spezifisch → an Zoo binden.
            if entity_type == "species":
                cur.execute("""
                    SELECT id, filename, storage_path, mime_type, file_size,
                           sort_order, label, uploaded_at
                    FROM zoo.media
                    WHERE entity_type = %s AND entity_id = %s
                    ORDER BY sort_order, uploaded_at
                """, (entity_type, entity_id))
            else:
                cur.execute("""
                    SELECT m.id, m.filename, m.storage_path, m.mime_type, m.file_size,
                           m.sort_order, m.label, m.uploaded_at
                    FROM zoo.media m
                    JOIN zoo.zoos z ON z.id = m.zoo_id
                    WHERE m.entity_type = %s
                      AND m.entity_id   = %s
                      AND z.slug        = %s
                    ORDER BY m.sort_order, m.uploaded_at
                """, (entity_type, entity_id, zoo))
            rows = cur.fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["url"]         = storage.url(item.pop("storage_path"))
            item["uploaded_at"] = item["uploaded_at"].isoformat() if item["uploaded_at"] else None
            result.append(item)
        return jsonify(result), 200
    except Exception:
        logging.exception("Exception in GET /api/v1/media")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@media_bp.route("/api/v1/media/<entity_type>/<int:entity_id>", methods=["POST"])
@limiter.limit("20 per minute")
def upload_media(entity_type, entity_id):
    # entity_type Whitelist
    if entity_type not in ENTITY_TABLE_MAP:
        return jsonify({"error": "Invalid entity_type"}), 400

    zoo = request.form.get("zoo")
    if not zoo:
        return jsonify({"error": "Missing zoo parameter"}), 400

    user_id, err = require_zoo_access(zoo, 'write')
    if err: return err

    if "file" not in request.files or not request.files["file"].filename:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]

    file.seek(0, 2)
    file_size = file.tell()
    file.seek(0)
    if file_size > MAX_FILE_SIZE:
        return jsonify({"error": "File too large (max 10 MB)"}), 413

    # MIME-Prüfung via python-magic (liest echte Datei-Bytes, nicht den Header)
    mime_type = file.mimetype
    try:
        import magic
        header = file.read(2048)
        file.seek(0)
        mime_type = magic.from_buffer(header, mime=True)
    except ImportError:
        # Fix 10: fail-closed — Upload ablehnen wenn libmagic fehlt.
        # Verhindert dass ein Client den Content-Type fälscht.
        logging.error(
            "python-magic nicht verfügbar — Upload abgelehnt. "
            "`pip install python-magic` und `apt install libmagic1` ausführen."
        )
        return jsonify({"error": "Server configuration error — upload temporarily unavailable"}), 500

    if mime_type not in ALLOWED_MIME_TYPES:
        return jsonify({"error": "Invalid file type"}), 400

    ext           = os.path.splitext(file.filename)[1].lower()
    safe_filename = f"{uuid.uuid4().hex}{ext}"
    label         = request.form.get("label")
    sort_order    = int(request.form.get("sort_order", 0) or 0)
    wikidata_id   = request.form.get("wikidata_id")

    conn         = None
    storage_path = None
    try:
        conn = get_pg_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:

            # Zoo-ID ermitteln
            cur.execute("SELECT id FROM zoo.zoos WHERE slug = %s", (zoo,))
            zoo_row = cur.fetchone()
            if not zoo_row:
                return jsonify({"error": "Zoo not found"}), 404
            zoo_id = zoo_row["id"]

            # Fix 4 (erweitert): Entity muss existieren UND zum autorisierten Zoo gehören.
            # species: global → nur Existenz prüfen.
            # enclosure_species: hat keine zoo_id → Zoo via enclosures JOIN prüfen.
            # Alle anderen: haben zoo_id direkt.
            table = ENTITY_TABLE_MAP[entity_type]
            if entity_type == "species":
                cur.execute(f"SELECT id FROM {table} WHERE id = %s", (entity_id,))
            elif entity_type == "enclosure_species":
                cur.execute("""
                    SELECT es.id FROM enclosure_species es
                    JOIN enclosures e ON e.id = es.enclosure_id
                    WHERE es.id = %s AND e.zoo_id = %s
                """, (entity_id, zoo_id))
            else:
                cur.execute(
                    f"SELECT id FROM {table} WHERE id = %s AND zoo_id = %s",
                    (entity_id, zoo_id)
                )
            if not cur.fetchone():
                return jsonify({"error": f"{entity_type} not found or not in this zoo"}), 404

            # Erst jetzt Datei speichern — verhindert verwaiste Dateien bei
            # nicht-existenten Entities
            storage_path = storage.save(zoo, entity_type, safe_filename, file)
            actual_size  = os.path.getsize(storage.full_path(storage_path))

            cur.execute("""
                INSERT INTO zoo.media
                    (entity_type, entity_id, wikidata_id, filename, storage_path,
                     mime_type, file_size, sort_order, label, uploaded_by, zoo_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                entity_type, entity_id, wikidata_id, safe_filename, storage_path,
                mime_type, actual_size, sort_order, label,
                str(user_id), zoo_id
            ))
            new_id = cur.fetchone()["id"]

        conn.commit()
        return jsonify({"id": new_id, "url": storage.url(storage_path), "message": "Uploaded"}), 201

    except Exception:
        logging.exception("Exception in POST /api/v1/media")
        if storage_path:
            storage.delete(storage_path)
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@media_bp.route("/api/v1/media/<int:media_id>", methods=["DELETE"])
@limiter.limit("20 per minute")
def delete_media(media_id):
    zoo = request.args.get("zoo")
    if not zoo:
        return jsonify({"error": "Missing zoo parameter"}), 400

    user_id, err = require_zoo_access(zoo, 'write')
    if err: return err

    conn = None
    try:
        conn = get_pg_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT m.storage_path, z.slug AS zoo_slug
                FROM zoo.media m
                LEFT JOIN zoo.zoos z ON z.id = m.zoo_id
                WHERE m.id = %s
            """, (media_id,))
            row = cur.fetchone()

            if not row:
                return jsonify({"error": "Not found"}), 404
            if row["zoo_slug"] != zoo:
                return jsonify({"error": "Unauthorized"}), 403

            storage.delete(row["storage_path"])
            cur.execute("DELETE FROM zoo.media WHERE id = %s", (media_id,))
        conn.commit()
        return jsonify({"message": "Deleted"}), 200

    except Exception:
        logging.exception("Exception in DELETE /api/v1/media")
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()
