import logging
import psycopg2.extras
from flask import Blueprint, jsonify, request
from db import get_pg_connection
from extensions import limiter
from helpers.coordinates import is_valid_slug, round_coordinates
from helpers.authz import require_zoo_access

locations_bp = Blueprint("locations_bp", __name__)

@locations_bp.route("/api/v1/zoos/<zoo>/locations", methods=["GET"])
@limiter.limit("60 per minute")
def get_locations(zoo):
    """Alle Infrastruktur-POIs eines Zoos (Toilette, Restaurant, Spielplatz, …)."""
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "read")
    if err: return err

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT l.id, l.name, l.name_display, l.description,
                       l.location_type, l.location_type_id, l.sort_order, l.domain_id,
                       l.url, l.description_long,
                       d.name AS domain_name,
                       lt.name AS location_type_name, lt.icon AS location_type_icon,
                       gp.latitude, gp.longitude,
                       mi.storage_path || mi.filename AS icon_path,
                       mimg.storage_path || mimg.filename AS image_path
                FROM zoo.locations l
                JOIN zoo.zoos z ON z.id = l.zoo_id
                LEFT JOIN zoo.domains d ON d.id = l.domain_id
                LEFT JOIN zoo.location_types lt ON lt.id = l.location_type_id
                LEFT JOIN zoo.geo_points gp ON gp.entity_type = 'location' AND gp.entity_id = l.id
                LEFT JOIN zoo.media mi ON mi.id = l.icon_media_id
                LEFT JOIN zoo.media mimg ON mimg.id = l.image_media_id
                WHERE z.slug = %s
                ORDER BY l.sort_order, l.name
            """, (zoo,))
            results = cur.fetchall()
        return jsonify([dict(r) for r in results]), 200
    except Exception:
        logging.exception(f"Exception in GET /api/v1/zoos/{zoo}/locations")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@locations_bp.route("/api/v1/zoos/<zoo>/locations/<int:location_id>", methods=["GET"])
@limiter.limit("60 per minute")
def get_location(zoo, location_id):
    """Einzelner Infrastruktur-POI inkl. Öffnungszeiten."""
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "read")
    if err: return err

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT l.id, l.name, l.name_display, l.description,
                       l.location_type, l.location_type_id, l.sort_order, l.domain_id,
                       l.url, l.description_long,
                       lt.name AS location_type_name, lt.icon AS location_type_icon,
                       gp.latitude, gp.longitude,
                       mi.storage_path || mi.filename AS icon_path,
                       mimg.storage_path || mimg.filename AS image_path
                FROM zoo.locations l
                JOIN zoo.zoos z ON z.id = l.zoo_id
                LEFT JOIN zoo.location_types lt ON lt.id = l.location_type_id
                LEFT JOIN zoo.geo_points gp ON gp.entity_type = 'location' AND gp.entity_id = l.id
                LEFT JOIN zoo.media mi ON mi.id = l.icon_media_id
                LEFT JOIN zoo.media mimg ON mimg.id = l.image_media_id
                WHERE l.id = %s AND z.slug = %s
            """, (location_id, zoo))
            loc = cur.fetchone()
            if not loc:
                return jsonify({"error": "Location not found"}), 404
            loc = dict(loc)

            # Öffnungszeiten
            cur.execute("""
                SELECT day_of_week, open_time::TEXT, close_time::TEXT,
                       valid_from, valid_until, label
                FROM zoo.opening_hours
                WHERE location_id = %s
                ORDER BY day_of_week
            """, (location_id,))
            loc["opening_hours"] = [dict(r) for r in cur.fetchall()]

        return jsonify(loc), 200
    except Exception:
        logging.exception(f"Exception in GET /api/v1/zoos/{zoo}/locations/{location_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@locations_bp.route("/api/v1/zoos/<zoo>/locations", methods=["POST"])
@limiter.limit("30 per minute")
def create_location(zoo):
    """
    Infrastruktur-POI anlegen.
    Body: { name, name_display, description, location_type, sort_order,
            domain_id, url, description_long }
    """
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "write")
    if err: return err

    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    latitude    = data.get("latitude")
    longitude   = data.get("longitude")

    if not name:
        return jsonify({"error": "name required"}), 400
    if len(name) > 200:
        return jsonify({"error": "name must be at most 200 characters"}), 400

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT id FROM zoo.zoos WHERE slug = %s", (zoo,))
            zoo_row = cur.fetchone()
            if not zoo_row:
                return jsonify({"error": "Zoo not found"}), 404

            cur.execute("""
                INSERT INTO zoo.locations
                    (zoo_id, name, name_display, description, location_type,
                     location_type_id, sort_order, domain_id, url, description_long)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                zoo_row["id"], name,
                data.get("name_display") or None,
                data.get("description") or None,
                data.get("location_type") or None,
                data.get("location_type_id") or None,
                data.get("sort_order", 0),
                data.get("domain_id") or None,
                data.get("url") or None,
                data.get("description_long") or None,
            ))
            location_id = cur.fetchone()["id"]

            if latitude is not None and longitude is not None:
                lat, lon = round_coordinates(latitude, longitude)
                cur.execute("""
                    INSERT INTO zoo.geo_points (entity_type, entity_id, latitude, longitude)
                    VALUES ('location', %s, %s, %s)
                    ON CONFLICT DO NOTHING
                """, (location_id, lat, lon))

            # Media-Eintrag für Icon anlegen und icon_media_id direkt verknüpfen.
            # Dateiname kommt aus location_type.icon (falls location_type_id gesetzt).
            location_type_id = data.get("location_type_id")
            if location_type_id:
                cur.execute("""
                    SELECT icon FROM zoo.location_types WHERE id = %s
                """, (location_type_id,))
                lt_row = cur.fetchone()
                if lt_row and lt_row["icon"]:
                    filename = f"{lt_row['icon']}.png"
                    cur.execute("""
                        INSERT INTO zoo.media
                            (entity_type, entity_id, zoo_id, storage_path,
                             filename, mime_type, label)
                        VALUES ('location', %s, %s, %s, %s, 'image/png', 'icon')
                        RETURNING id
                    """, (
                        location_id, zoo_row["id"],
                        f"zoo/{zoo}/locations/",
                        filename
                    ))
                    media_id = cur.fetchone()["id"]
                    cur.execute("""
                        UPDATE zoo.locations SET icon_media_id = %s WHERE id = %s
                    """, (media_id, location_id))
        pg.commit()
        return jsonify({"id": location_id, "message": "Created"}), 201
    except Exception:
        logging.exception(f"Exception in POST /api/v1/zoos/{zoo}/locations")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@locations_bp.route("/api/v1/zoos/<zoo>/locations/<int:location_id>", methods=["PUT"])
@limiter.limit("30 per minute")
def update_location(zoo, location_id):
    """Infrastruktur-POI bearbeiten."""
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "write")
    if err: return err

    data = request.get_json(silent=True) or {}
    ALLOWED = {"name", "name_display", "description", "location_type",
               "location_type_id", "sort_order", "domain_id", "url", "description_long",
               "latitude", "longitude"}
    unknown = set(data.keys()) - ALLOWED
    if unknown:
        return jsonify({"error": f"Unknown fields: {', '.join(sorted(unknown))}"}), 400
    if not data:
        return jsonify({"error": "No fields to update"}), 400
    if "name" in data:
        if not str(data["name"]).strip():
            return jsonify({"error": "name must not be empty"}), 400

    # latitude/longitude go to geo_points, not locations table
    latitude  = data.pop("latitude", None)
    longitude = data.pop("longitude", None)

    set_clauses = ", ".join(f"{k} = %s" for k in data)
    values = list(data.values()) + [location_id, zoo]

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor() as cur:
            cur.execute(f"""
                UPDATE zoo.locations SET {set_clauses}
                WHERE id = %s
                  AND zoo_id = (SELECT id FROM zoo.zoos WHERE slug = %s)
                RETURNING id
            """, values)
            if not cur.fetchone():
                return jsonify({"error": "Location not found"}), 404

            if latitude is not None and longitude is not None:
                lat, lon = round_coordinates(latitude, longitude)
                cur.execute("""
                    INSERT INTO zoo.geo_points (entity_type, entity_id, latitude, longitude)
                    VALUES ('location', %s, %s, %s)
                    ON CONFLICT (entity_type, entity_id) DO UPDATE
                        SET latitude = EXCLUDED.latitude,
                            longitude = EXCLUDED.longitude
                """, (location_id, lat, lon))
        pg.commit()
        return jsonify({"message": "Updated"}), 200
    except Exception:
        logging.exception(f"Exception in PUT /api/v1/zoos/{zoo}/locations/{location_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@locations_bp.route("/api/v1/zoos/<zoo>/locations/<int:location_id>", methods=["DELETE"])
@limiter.limit("10 per minute")
def delete_location(zoo, location_id):
    """Infrastruktur-POI löschen (inkl. Öffnungszeiten via CASCADE)."""
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "write")
    if err: return err

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor() as cur:
            # Media-Eintrag mitlöschen (Datei bleibt auf Disk)
            cur.execute("""
                DELETE FROM zoo.media
                WHERE entity_type = 'location' AND entity_id = %s
            """, (location_id,))

            cur.execute("""
                DELETE FROM zoo.locations
                WHERE id = %s
                  AND zoo_id = (SELECT id FROM zoo.zoos WHERE slug = %s)
            """, (location_id, zoo))
            if cur.rowcount == 0:
                return jsonify({"error": "Location not found"}), 404
        pg.commit()
        return jsonify({"message": "Deleted"}), 200
    except Exception:
        logging.exception(f"Exception in DELETE /api/v1/zoos/{zoo}/locations/{location_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()
