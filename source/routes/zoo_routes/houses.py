import logging
import psycopg2.extras
from flask import Blueprint, jsonify, request
from db import get_pg_connection
from extensions import limiter
from helpers.coordinates import is_valid_slug, round_coordinates
from helpers.authz import require_zoo_access

houses_bp = Blueprint("houses_bp", __name__)

@houses_bp.route("/api/v1/zoos/<zoo>/houses", methods=["GET"])
@limiter.limit("60 per minute")
def get_houses(zoo):
    """Alle Tierhäuser eines Zoos inkl. Anzahl Gehege."""
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "read")
    if err: return err

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT h.id, h.name, h.description, h.history,
                       h.sponsor, h.notes, h.domain_id,
                       d.name AS domain_name,
                       COUNT(e.id) AS enclosure_count,
                       gp.latitude, gp.longitude,
                       mimg.storage_path || mimg.filename AS image_path
                FROM zoo.houses h
                JOIN zoo.zoos z ON z.id = h.zoo_id
                LEFT JOIN zoo.domains d ON d.id = h.domain_id
                LEFT JOIN zoo.enclosures e ON e.house_id = h.id
                LEFT JOIN zoo.geo_points gp ON gp.entity_type = 'house' AND gp.entity_id = h.id
                LEFT JOIN zoo.media mimg ON mimg.id = h.image_media_id
                WHERE z.slug = %s
                GROUP BY h.id, d.name, gp.latitude, gp.longitude, mimg.storage_path, mimg.filename
                ORDER BY h.name
            """, (zoo,))
            results = cur.fetchall()
        return jsonify([dict(r) for r in results]), 200
    except Exception:
        logging.exception(f"Exception in GET /api/v1/zoos/{zoo}/houses")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@houses_bp.route("/api/v1/zoos/<zoo>/houses/<int:house_id>", methods=["GET"])
@limiter.limit("60 per minute")
def get_house(zoo, house_id):
    """Einzelnes Tierhaus mit seinen Gehegen."""
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "read")
    if err: return err

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT h.id, h.name, h.description, h.history,
                       h.sponsor, h.notes, h.domain_id,
                       d.name AS domain_name,
                       gp.latitude, gp.longitude,
                       mimg.storage_path || mimg.filename AS image_path
                FROM zoo.houses h
                JOIN zoo.zoos z ON z.id = h.zoo_id
                LEFT JOIN zoo.domains d ON d.id = h.domain_id
                LEFT JOIN zoo.geo_points gp ON gp.entity_type = 'house' AND gp.entity_id = h.id
                LEFT JOIN zoo.media mimg ON mimg.id = h.image_media_id
                WHERE h.id = %s AND z.slug = %s
            """, (house_id, zoo))
            house = cur.fetchone()
            if not house:
                return jsonify({"error": "House not found"}), 404
            house = dict(house)

            # Gehege dieses Hauses
            cur.execute("""
                SELECT e.id, e.name, e.sort_order, e.domain_id,
                       s.id AS species_id, s.german_name, s.latin_name,
                       s.wikidata_id, s.iucn_status_id
                FROM zoo.enclosures e
                LEFT JOIN zoo.enclosure_species es ON es.enclosure_id = e.id
                LEFT JOIN zoo.species s ON s.id = es.species_id
                WHERE e.house_id = %s
                ORDER BY e.sort_order, e.name
            """, (house_id,))
            house["enclosures"] = [dict(r) for r in cur.fetchall()]

            # Tiere direkt im Haus (ohne Gehege)
            cur.execute("""
                SELECT es.id, es.species_id, es.house_id, es.enclosure_id,
                       es.note, es.count_adult, es.count_juvenile,
                       s.german_name, s.latin_name, s.wikidata_id, s.iucn_status_id
                FROM zoo.enclosure_species es
                JOIN zoo.species s ON s.id = es.species_id
                WHERE es.house_id = %s
                ORDER BY s.german_name
            """, (house_id,))
            house["species"] = [dict(r) for r in cur.fetchall()]

        return jsonify(house), 200
    except Exception:
        logging.exception(f"Exception in GET /api/v1/zoos/{zoo}/houses/{house_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@houses_bp.route("/api/v1/zoos/<zoo>/houses", methods=["POST"])
@limiter.limit("30 per minute")
def create_house(zoo):
    """Tierhaus anlegen. Body: { name, description, history, sponsor, notes }"""
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "write")
    if err: return err

    data        = request.get_json(silent=True) or {}
    name        = data.get("name", "").strip()
    description = data.get("description", "").strip() or None
    history     = data.get("history", "").strip() or None
    sponsor     = data.get("sponsor", "").strip() or None
    notes       = data.get("notes", "").strip() or None
    domain_id   = data.get("domain_id") or None
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
                INSERT INTO zoo.houses (zoo_id, name, description, history, sponsor, notes, domain_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (zoo_row["id"], name, description, history, sponsor, notes, domain_id))
            house_id = cur.fetchone()["id"]

            if latitude is not None and longitude is not None:
                lat, lon = round_coordinates(latitude, longitude)
                cur.execute("""
                    INSERT INTO zoo.geo_points (entity_type, entity_id, latitude, longitude)
                    VALUES ('house', %s, %s, %s)
                    ON CONFLICT DO NOTHING
                """, (house_id, lat, lon))
        pg.commit()
        return jsonify({"id": house_id, "message": "Created"}), 201
    except Exception:
        logging.exception(f"Exception in POST /api/v1/zoos/{zoo}/houses")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@houses_bp.route("/api/v1/zoos/<zoo>/houses/<int:house_id>", methods=["PUT"])
@limiter.limit("30 per minute")
def update_house(zoo, house_id):
    """Tierhaus bearbeiten."""
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "write")
    if err: return err

    data = request.get_json(silent=True) or {}
    ALLOWED = {"name", "description", "history", "sponsor", "notes", "domain_id", "latitude", "longitude"}
    unknown = set(data.keys()) - ALLOWED
    if unknown:
        return jsonify({"error": f"Unknown fields: {', '.join(sorted(unknown))}"}), 400
    if "name" in data:
        if not data["name"] or not str(data["name"]).strip():
            return jsonify({"error": "name must not be empty"}), 400
        if len(str(data["name"])) > 200:
            return jsonify({"error": "name must be at most 200 characters"}), 400

    # latitude/longitude go to geo_points, not houses table
    latitude  = data.pop("latitude", None)
    longitude = data.pop("longitude", None)

    if not data and latitude is None and longitude is None:
        return jsonify({"error": "No fields to update"}), 400

    set_clauses = ", ".join(f"{k} = %s" for k in data)
    values      = list(data.values()) + [house_id, zoo]

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor() as cur:
            cur.execute(f"""
                UPDATE zoo.houses SET {set_clauses}
                WHERE id = %s
                  AND zoo_id = (SELECT id FROM zoo.zoos WHERE slug = %s)
                RETURNING id
            """, values)
            if not cur.fetchone():
                return jsonify({"error": "House not found"}), 404

            if latitude is not None and longitude is not None:
                lat, lon = round_coordinates(latitude, longitude)
                cur.execute("""
                    INSERT INTO zoo.geo_points (entity_type, entity_id, latitude, longitude)
                    VALUES ('house', %s, %s, %s)
                    ON CONFLICT (entity_type, entity_id) DO UPDATE
                        SET latitude = EXCLUDED.latitude,
                            longitude = EXCLUDED.longitude
                """, (house_id, lat, lon))
        pg.commit()
        return jsonify({"message": "Updated"}), 200
    except Exception:
        logging.exception(f"Exception in PUT /api/v1/zoos/{zoo}/houses/{house_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@houses_bp.route("/api/v1/zoos/<zoo>/houses/<int:house_id>", methods=["DELETE"])
@limiter.limit("10 per minute")
def delete_house(zoo, house_id):
    """Tierhaus löschen (inkl. aller Gehege via CASCADE)."""
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "write")
    if err: return err

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor() as cur:
            cur.execute("""
                DELETE FROM zoo.houses
                WHERE id = %s
                  AND zoo_id = (SELECT id FROM zoo.zoos WHERE slug = %s)
            """, (house_id, zoo))
            if cur.rowcount == 0:
                return jsonify({"error": "House not found"}), 404
        pg.commit()
        return jsonify({"message": "Deleted"}), 200
    except Exception:
        logging.exception(f"Exception in DELETE /api/v1/zoos/{zoo}/houses/{house_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()
