import logging
import psycopg2.extras
from flask import Blueprint, jsonify, request
from helpers.auth_utils import require_jwt_read, require_jwt_write
from helpers.coordinates import is_valid_slug, round_coordinates
from db import get_pg_connection
from extensions import limiter

enclosures_bp = Blueprint("enclosures", __name__)


@enclosures_bp.route("/api/v1/zoos/<zoo>/enclosures", methods=["GET"])
@limiter.limit("60 per minute")
def get_enclosures(zoo):
    key_data, err = require_jwt_read(zoo)
    if err: return err
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT e.id, e.name, e.sort_order, e.domain_id,
                       d.name AS domain_name,
                       s.id AS species_id, s.german_name, s.latin_name,
                       s.wikidata_id, s.iucn_status_id,
                       es.count_adult, es.count_juvenile,
                       ARRAY_AGG(ft.feeding_time::TEXT ORDER BY ft.feeding_time)
                           FILTER (WHERE ft.feeding_time IS NOT NULL) AS feeding_times,
                       gp.latitude, gp.longitude
                FROM enclosures e
                JOIN zoos z ON z.id = e.zoo_id
                LEFT JOIN domains d ON d.id = e.domain_id
                LEFT JOIN enclosure_species es ON es.enclosure_id = e.id
                LEFT JOIN species s ON s.id = es.species_id
                LEFT JOIN feeding_times ft
                       ON ft.enclosure_id = e.id
                      AND ft.species_id = es.species_id
                LEFT JOIN geo_points gp
                       ON gp.entity_type = 'enclosure'
                      AND gp.entity_id = e.id
                WHERE z.slug = %s
                GROUP BY e.id, e.name, e.sort_order, e.domain_id,
                         d.name, s.id, s.german_name, s.latin_name,
                         s.wikidata_id, s.iucn_status_id,
                         es.count_adult, es.count_juvenile,
                         gp.latitude, gp.longitude
                ORDER BY e.sort_order, e.name
            """, (zoo,))
            results = cur.fetchall()
        return jsonify([dict(r) for r in results]), 200
    except Exception as e:
        logging.exception("Exception in GET enclosures")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg:
            pg.close()


@enclosures_bp.route("/api/v1/zoos/<zoo>/enclosures", methods=["POST"])
@limiter.limit("30 per minute")
def create_enclosure(zoo):
    key_data, err = require_jwt_write(zoo)
    if err: return err
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400

    data       = request.get_json(silent=True) or {}
    name       = data.get("name", "").strip()
    species_id = data.get("species_id")
    domain_id  = data.get("domain_id")
    latitude   = data.get("latitude")
    longitude  = data.get("longitude")
    feeding_times = data.get("feeding_times", [])

    if not name or not species_id:
        return jsonify({"error": "name and species_id required"}), 400

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT id FROM zoos WHERE slug = %s", (zoo,))
            zoo_row = cur.fetchone()
            if not zoo_row:
                return jsonify({"error": "Zoo not found"}), 404
            zoo_id = zoo_row["id"]

            cur.execute("SELECT id FROM species WHERE id = %s", (species_id,))
            if not cur.fetchone():
                return jsonify({"error": "Invalid species_id"}), 400

            if domain_id is not None:
                cur.execute("""
                    SELECT id FROM domains
                    WHERE id = %s
                    AND (zoo_id IS NULL OR zoo_id = %s)
                """, (domain_id, zoo_id))
                if not cur.fetchone():
                    return jsonify({"error": "Invalid domain_id"}), 400

            cur.execute("""
                INSERT INTO enclosures (zoo_id, name, domain_id)
                VALUES (%s, %s, %s)
                RETURNING id
            """, (zoo_id, name, domain_id))
            enclosure_id = cur.fetchone()["id"]

            cur.execute("""
                INSERT INTO enclosure_species (enclosure_id, species_id)
                VALUES (%s, %s)
            """, (enclosure_id, species_id))

            for t in feeding_times:
                cur.execute("""
                    INSERT INTO feeding_times (enclosure_id, species_id, feeding_time)
                    VALUES (%s, %s, %s)
                """, (enclosure_id, species_id, t))

            if latitude is not None and longitude is not None:
                try:
                    latitude, longitude = round_coordinates(latitude, longitude)
                except ValueError as e:
                    return jsonify({"error": str(e)}), 400
                cur.execute("""
                    INSERT INTO geo_points (entity_type, entity_id, latitude, longitude)
                    VALUES ('enclosure', %s, %s, %s)
                """, (enclosure_id, latitude, longitude))

        pg.commit()
        return jsonify({"id": enclosure_id, "message": "Created"}), 201
    except Exception as e:
        logging.exception("Exception in POST enclosure")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg:
            pg.close()


@enclosures_bp.route("/api/v1/zoos/<zoo>/enclosures/<int:enclosure_id>", methods=["PUT"])
@limiter.limit("30 per minute")
def update_enclosure(zoo, enclosure_id):
    key_data, err = require_jwt_write(zoo)
    if err: return err
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400

    data          = request.get_json(silent=True) or {}
    name          = data.get("name")
    domain_id     = data.get("domain_id")
    feeding_times = data.get("feeding_times")
    latitude      = data.get("latitude")
    longitude     = data.get("longitude")
    species_id    = data.get("species_id")

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor() as cur:

            # Fix 2: Zoo-Zugehörigkeit einmalig prüfen — schützt alle nachfolgenden
            # UPDATE/INSERT-Statements (feeding_times, geo_points) vor Cross-Tenant-Zugriff.
            cur.execute("""
                SELECT 1 FROM enclosures e
                JOIN zoos z ON z.id = e.zoo_id
                WHERE e.id = %s AND z.slug = %s
            """, (enclosure_id, zoo))
            if not cur.fetchone():
                return jsonify({"error": "Not found"}), 404

            if domain_id is not None:
                cur.execute("SELECT id FROM zoos WHERE slug = %s", (zoo,))
                zoo_row = cur.fetchone()
                if zoo_row:
                    cur.execute("""
                        SELECT id FROM domains
                        WHERE id = %s
                        AND (zoo_id IS NULL OR zoo_id = %s)
                    """, (domain_id, zoo_row[0]))
                    if not cur.fetchone():
                        return jsonify({"error": "Invalid domain_id"}), 400

            if name or domain_id is not None:
                cur.execute("""
                    UPDATE enclosures SET
                        name      = COALESCE(%s, name),
                        domain_id = COALESCE(%s, domain_id)
                    WHERE id = %s
                    AND zoo_id = (SELECT id FROM zoos WHERE slug = %s)
                """, (name, domain_id, enclosure_id, zoo))

            if feeding_times is not None:
                sid = species_id
                if not sid:
                    cur.execute("""
                        SELECT species_id FROM enclosure_species
                        WHERE enclosure_id = %s LIMIT 1
                    """, (enclosure_id,))
                    row = cur.fetchone()
                    sid = row[0] if row else None

                if sid:
                    cur.execute("""
                        DELETE FROM feeding_times
                        WHERE enclosure_id = %s AND species_id = %s
                    """, (enclosure_id, sid))
                    for t in feeding_times:
                        cur.execute("""
                            INSERT INTO feeding_times
                                (enclosure_id, species_id, feeding_time)
                            VALUES (%s, %s, %s)
                        """, (enclosure_id, sid, t))

            if latitude is not None and longitude is not None:
                try:
                    latitude, longitude = round_coordinates(latitude, longitude)
                except ValueError as e:
                    return jsonify({"error": str(e)}), 400
                cur.execute("""
                    INSERT INTO geo_points (entity_type, entity_id, latitude, longitude)
                    VALUES ('enclosure', %s, %s, %s)
                    ON CONFLICT DO NOTHING
                """, (enclosure_id, latitude, longitude))

        pg.commit()
        return jsonify({"message": "Updated"}), 200
    except Exception as e:
        logging.exception("Exception in PUT enclosure")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg:
            pg.close()


@enclosures_bp.route("/api/v1/zoos/<zoo>/enclosures/<int:enclosure_id>", methods=["DELETE"])
@limiter.limit("10 per minute")
def delete_enclosure(zoo, enclosure_id):
    key_data, err = require_jwt_write(zoo)
    if err: return err
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor() as cur:
            cur.execute("""
                DELETE FROM enclosures
                WHERE id = %s
                AND zoo_id = (SELECT id FROM zoos WHERE slug = %s)
            """, (enclosure_id, zoo))
        pg.commit()
        return jsonify({"message": "Deleted"}), 200
    except Exception as e:
        logging.exception("Exception in DELETE enclosure")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg:
            pg.close()
