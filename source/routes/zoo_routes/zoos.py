import logging
import psycopg2.extras
from flask import Blueprint, jsonify, request
from db import get_pg_connection
from extensions import limiter
from helpers.coordinates import is_valid_slug
from helpers.authz import require_zoo_access, require_authenticated

zoos_bp = Blueprint("zoos_bp", __name__)

@zoos_bp.route("/api/v1/zoos", methods=["GET"])
@limiter.limit("60 per minute")
def list_zoos():
    """
    Alle aktiven Zoos.
    Öffentlich (App-Token oder JWT) — kein Zoo-spezifischer Zugriff nötig.
    Gibt Basisdaten zurück die die App zum Aufbau des Zoo-Verzeichnisses braucht.
    """
    user_id, err = require_authenticated()
    if err: return err

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id, slug, name, city, country,
                       url, description,
                       top_left_latitude,    top_left_longitude,
                       bottom_right_latitude, bottom_right_longitude,
                       map_overlay, data_version,
                       easy_language, number_animals, icon_url,
                       latitude, longitude
                FROM zoo.zoos
                WHERE is_active = TRUE
                  AND archived_at IS NULL
                ORDER BY name
            """)
            results = cur.fetchall()
        return jsonify([dict(r) for r in results]), 200
    except Exception:
        logging.exception("Exception in GET /api/v1/zoos")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@zoos_bp.route("/api/v1/zoos/<zoo>", methods=["GET"])
@limiter.limit("60 per minute")
def get_zoo(zoo):
    """
    Zoo-Details inkl. Öffnungszeiten.
    Erfordert Lesezugriff auf diesen Zoo.
    """
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400

    user_id, err = require_zoo_access(zoo, "read")
    if err: return err

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT z.id, z.slug, z.name, z.city, z.country,
                       z.url, z.description, z.email,
                       z.top_left_latitude,    z.top_left_longitude,
                       z.bottom_right_latitude, z.bottom_right_longitude,
                       z.map_overlay, z.data_version,
                       z.easy_language, z.number_animals, z.icon_url,
                       z.time_open::TEXT, z.time_close::TEXT,
                       im.storage_path || im.filename AS icon_media_path,
                       mo1.storage_path || mo1.filename AS map_overlay_1_path,
                       mo2.storage_path || mo2.filename AS map_overlay_2_path,
                       mo3.storage_path || mo3.filename AS map_overlay_3_path,
                       mo4.storage_path || mo4.filename AS map_overlay_4_path,
                       mo5.storage_path || mo5.filename AS map_overlay_5_path
                FROM zoo.zoos z
                LEFT JOIN zoo.media im  ON im.id  = z.icon_media_id
                LEFT JOIN zoo.media mo1 ON mo1.id = z.map_overlay_1_id
                LEFT JOIN zoo.media mo2 ON mo2.id = z.map_overlay_2_id
                LEFT JOIN zoo.media mo3 ON mo3.id = z.map_overlay_3_id
                LEFT JOIN zoo.media mo4 ON mo4.id = z.map_overlay_4_id
                LEFT JOIN zoo.media mo5 ON mo5.id = z.map_overlay_5_id
                WHERE z.slug = %s
                  AND z.is_active = TRUE
                  AND z.archived_at IS NULL
            """, (zoo,))
            row = cur.fetchone()
            if not row:
                return jsonify({"error": "Zoo not found"}), 404
            zoo_data = dict(row)

            # Öffnungszeiten (falls vorhanden)
            cur.execute("""
                SELECT day_of_week, open_time::TEXT, close_time::TEXT,
                       valid_from, valid_until, label
                FROM zoo.zoo_opening_hours
                WHERE zoo_id = %s
                ORDER BY day_of_week
            """, (zoo_data["id"],))
            zoo_data["opening_hours"] = [dict(r) for r in cur.fetchall()]

        return jsonify(zoo_data), 200
    except Exception:
        logging.exception(f"Exception in GET /api/v1/zoos/{zoo}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()
