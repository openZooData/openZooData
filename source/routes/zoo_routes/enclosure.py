"""
routes/zoo_routes/enclosure.py — Freigehege (WG) CRUD

Freigehege = offene WG im Freien für mehrere Tierarten (enclosure_species).

GET    /api/v1/zoos/<zoo>/enclosure         → alle Freigehege
GET    /api/v1/zoos/<zoo>/enclosure/<id>    → Freigehege Details + enclosure_species
POST   /api/v1/zoos/<zoo>/enclosure         → Freigehege anlegen
PUT    /api/v1/zoos/<zoo>/enclosure/<id>    → Freigehege bearbeiten
DELETE /api/v1/zoos/<zoo>/enclosure/<id>    → Freigehege löschen
"""

import logging
import psycopg2.extras
from flask import Blueprint, jsonify, request
from db import get_pg_connection
from extensions import limiter
from helpers.authz import require_zoo_access
from helpers.coordinates import is_valid_slug, round_coordinates

enclosure_bp = Blueprint("enclosure", __name__)


@enclosure_bp.route("/api/v1/zoos/<zoo>/enclosure", methods=["GET"])
@limiter.limit("60 per minute")
def get_enclosures(zoo):
    """Alle Freigehege eines Zoos inkl. Anzahl der Tierarten."""
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "read")
    if err: return err

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    e.id, e.name, e.sort_order, e.domain_id,
                    d.name AS domain_name,
                    e.image_media_id,
                    mimg.storage_path || mimg.filename AS image_path,
                    gp.latitude, gp.longitude,
                    COUNT(es.id) AS species_count
                FROM zoo.enclosures e
                JOIN zoo.zoos z ON z.id = e.zoo_id
                LEFT JOIN zoo.domains d ON d.id = e.domain_id
                LEFT JOIN zoo.media mimg ON mimg.id = e.image_media_id
                LEFT JOIN zoo.geo_points gp
                       ON gp.entity_type = 'enclosure' AND gp.entity_id = e.id
                LEFT JOIN zoo.enclosure_species es ON es.enclosure_id = e.id
                WHERE z.slug = %s
                GROUP BY e.id, d.name, mimg.storage_path, mimg.filename,
                         gp.latitude, gp.longitude
                ORDER BY e.sort_order, e.name
            """, (zoo,))
            results = cur.fetchall()
        return jsonify([dict(r) for r in results]), 200
    except Exception:
        logging.exception(f"Exception in GET /api/v1/zoos/{zoo}/enclosure")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@enclosure_bp.route("/api/v1/zoos/<zoo>/enclosure/<int:enclosure_id>", methods=["GET"])
@limiter.limit("60 per minute")
def get_enclosure(zoo, enclosure_id):
    """Freigehege Details inkl. aller enclosure_species."""
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "read")
    if err: return err

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Freigehege
            cur.execute("""
                SELECT
                    e.id, e.name, e.sort_order, e.domain_id,
                    d.name AS domain_name,
                    mimg.storage_path || mimg.filename AS image_path,
                    gp.latitude, gp.longitude
                FROM zoo.enclosures e
                JOIN zoo.zoos z ON z.id = e.zoo_id
                LEFT JOIN zoo.domains d ON d.id = e.domain_id
                LEFT JOIN zoo.media mimg ON mimg.id = e.image_media_id
                LEFT JOIN zoo.geo_points gp
                       ON gp.entity_type = 'enclosure' AND gp.entity_id = e.id
                WHERE e.id = %s AND z.slug = %s
            """, (enclosure_id, zoo))
            enclosure = cur.fetchone()
            if not enclosure:
                return jsonify({"error": "Enclosure not found"}), 404
            enclosure = dict(enclosure)

            # enclosure_species in diesem Freigehege
            cur.execute("""
                SELECT
                    es.id, es.species_id, es.note,
                    es.count_adult, es.count_juvenile,
                    s.german_name, s.latin_name, s.wikidata_id,
                    s.iucn_status_id,
                    gp.latitude, gp.longitude,
                    ms.storage_path || ms.filename AS species_icon_path
                FROM zoo.enclosure_species es
                JOIN zoo.species s ON s.id = es.species_id
                LEFT JOIN zoo.geo_points gp
                       ON gp.entity_type = 'enclosure_species' AND gp.entity_id = es.id
                LEFT JOIN zoo.media ms ON ms.id = s.icon_media_id
                WHERE es.enclosure_id = %s
                ORDER BY s.german_name
            """, (enclosure_id,))
            enclosure["species"] = [dict(r) for r in cur.fetchall()]

        return jsonify(enclosure), 200
    except Exception:
        logging.exception(f"Exception in GET /api/v1/zoos/{zoo}/enclosure/{enclosure_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@enclosure_bp.route("/api/v1/zoos/<zoo>/enclosure", methods=["POST"])
@limiter.limit("30 per minute")
def create_enclosure(zoo):
    """
    Freigehege anlegen.
    Body: { name, domain_id, sort_order, latitude, longitude }
    """
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "write")
    if err: return err

    data      = request.get_json(silent=True) or {}
    name      = data.get("name", "").strip()
    domain_id = data.get("domain_id")
    sort_order = data.get("sort_order", 0)
    latitude  = data.get("latitude")
    longitude = data.get("longitude")

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
                INSERT INTO zoo.enclosures (zoo_id, name, domain_id, sort_order)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            """, (zoo_row["id"], name, domain_id, sort_order))
            enclosure_id = cur.fetchone()["id"]

            if latitude is not None and longitude is not None:
                try:
                    lat, lon = round_coordinates(latitude, longitude)
                except ValueError as e:
                    return jsonify({"error": str(e)}), 400
                cur.execute("""
                    INSERT INTO zoo.geo_points
                        (entity_type, entity_id, latitude, longitude)
                    VALUES ('enclosure', %s, %s, %s)
                    ON CONFLICT (entity_type, entity_id)
                    DO UPDATE SET latitude = EXCLUDED.latitude,
                                  longitude = EXCLUDED.longitude
                """, (enclosure_id, lat, lon))

        pg.commit()
        return jsonify({"id": enclosure_id, "message": "Created"}), 201
    except Exception:
        logging.exception(f"Exception in POST /api/v1/zoos/{zoo}/enclosure")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@enclosure_bp.route("/api/v1/zoos/<zoo>/enclosure/<int:enclosure_id>", methods=["PUT"])
@limiter.limit("30 per minute")
def update_enclosure(zoo, enclosure_id):
    """Freigehege bearbeiten."""
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "write")
    if err: return err

    data = request.get_json(silent=True) or {}
    ALLOWED = {"name", "domain_id", "sort_order", "latitude", "longitude"}
    unknown = set(data.keys()) - ALLOWED
    if unknown:
        return jsonify({"error": f"Unknown fields: {', '.join(sorted(unknown))}"}), 400
    if not data:
        return jsonify({"error": "No fields to update"}), 400
    if "name" in data and not str(data["name"]).strip():
        return jsonify({"error": "name must not be empty"}), 400

    latitude  = data.pop("latitude", None)
    longitude = data.pop("longitude", None)

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor() as cur:
            if data:
                set_clauses = ", ".join(f"{k} = %s" for k in data)
                values = list(data.values()) + [enclosure_id, zoo]
                cur.execute(f"""
                    UPDATE zoo.enclosures SET {set_clauses}
                    WHERE id = %s
                    AND zoo_id = (SELECT id FROM zoo.zoos WHERE slug = %s)
                    RETURNING id
                """, values)
                if not cur.fetchone():
                    return jsonify({"error": "Enclosure not found"}), 404

            if latitude is not None and longitude is not None:
                try:
                    lat, lon = round_coordinates(latitude, longitude)
                except ValueError as e:
                    return jsonify({"error": str(e)}), 400
                cur.execute("""
                    INSERT INTO zoo.geo_points
                        (entity_type, entity_id, latitude, longitude)
                    VALUES ('enclosure', %s, %s, %s)
                    ON CONFLICT (entity_type, entity_id)
                    DO UPDATE SET latitude = EXCLUDED.latitude,
                                  longitude = EXCLUDED.longitude
                """, (enclosure_id, lat, lon))

        pg.commit()
        return jsonify({"message": "Updated"}), 200
    except Exception:
        logging.exception(f"Exception in PUT /api/v1/zoos/{zoo}/enclosure/{enclosure_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@enclosure_bp.route("/api/v1/zoos/<zoo>/enclosure/<int:enclosure_id>", methods=["DELETE"])
@limiter.limit("10 per minute")
def delete_enclosure(zoo, enclosure_id):
    """
    Freigehege löschen.
    Schlägt fehl wenn noch enclosure_species zugeordnet sind.
    """
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "write")
    if err: return err

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor() as cur:
            # Prüfen ob noch enclosure_species vorhanden
            cur.execute("""
                SELECT COUNT(*) FROM zoo.enclosure_species
                WHERE enclosure_id = %s
            """, (enclosure_id,))
            count = cur.fetchone()[0]
            if count > 0:
                return jsonify({
                    "error": f"Cannot delete: {count} Tierarten in diesem Gehege"
                }), 409

            cur.execute("""
                DELETE FROM zoo.enclosures
                WHERE id = %s
                AND zoo_id = (SELECT id FROM zoo.zoos WHERE slug = %s)
            """, (enclosure_id, zoo))
            if cur.rowcount == 0:
                return jsonify({"error": "Enclosure not found"}), 404

        pg.commit()
        return jsonify({"message": "Deleted"}), 200
    except Exception:
        logging.exception(f"Exception in DELETE /api/v1/zoos/{zoo}/enclosure/{enclosure_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()
