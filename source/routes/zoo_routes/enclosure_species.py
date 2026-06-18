"""
routes/zoo_routes/enclosure_species.py — Enclosure-Species-Endpoints

Das Datenmodell:
  enclosure_species = ein Tier (species) an einem Ort im Zoo
    → optional in einem Enclosure (Freigehege/WG)
    → optional in einem House (Tierhaus)
    → GPS-Position via geo_points (entity_type='enclosure_species')
    → Bild via media (entity_type='enclosure_species')

GET  /api/v1/zoos/<zoo>/enclosure_species       → alle enclosure_species des Zoos
POST /api/v1/zoos/<zoo>/enclosure_species       → neue enclosure_species anlegen
PUT  /api/v1/zoos/<zoo>/enclosure_species/<id>  → enclosure_species bearbeiten
DELETE /api/v1/zoos/<zoo>/enclosure_species/<id> → enclosure_species löschen

Enclosures (Freigehege) und Houses (Tierhäuser) sind Container
die optional zugeordnet werden können.
"""

import logging
import psycopg2.extras
from flask import Blueprint, jsonify, request
from helpers.authz import require_zoo_access
from helpers.coordinates import is_valid_slug, round_coordinates
from db import get_pg_connection
from extensions import limiter

enclosure_species_bp = Blueprint("enclosure_species", __name__)


@enclosure_species_bp.route("/api/v1/zoos/<zoo>/enclosure_species", methods=["GET"])
@limiter.limit("60 per minute")
def get_enclosures(zoo):
    """
    Alle enclosure_species eines Zoos.
    Optionale Filter: ?enclosure_id=<id>, ?house_id=<id>, ?domain_id=<id>
    """
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "read")
    if err: return err

    enclosure_id_filter = request.args.get("enclosure_id")
    house_id_filter     = request.args.get("house_id")
    domain_id_filter    = request.args.get("domain_id")

    conditions = ["es.zoo_id = (SELECT id FROM zoo.zoos WHERE slug = %s)"]
    params     = [zoo]

    if enclosure_id_filter:
        conditions.append("es.enclosure_id = %s")
        params.append(int(enclosure_id_filter))
    if house_id_filter:
        conditions.append("es.house_id = %s")
        params.append(int(house_id_filter))
    if domain_id_filter:
        conditions.append("(e.domain_id = %s OR h.domain_id = %s OR es.domain_id = %s)")
        params.extend([int(domain_id_filter), int(domain_id_filter), int(domain_id_filter)])

    where = " AND ".join(conditions)

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(f"""
                SELECT
                    es.id,
                    es.species_id,
                    es.enclosure_id,
                    es.house_id,
                    es.note,
                    es.count_adult,
                    es.count_juvenile,
                    es.counted_at,
                    es.domain_id,
                    s.german_name,
                    s.latin_name,
                    s.wikidata_id,
                    s.iucn_status_id,
                    s.iucn_id,
                    s.gbif_taxon_key,
                    e.name AS enclosure_name,
                    e.sort_order AS enclosure_sort_order,
                    e.domain_id AS enclosure_domain_id,
                    h.name AS house_name,
                    h.domain_id AS house_domain_id,
                    gp.latitude,
                    gp.longitude,
                    ms.storage_path || ms.filename AS species_icon_path,
                    mimg.storage_path || mimg.filename AS image_path,
                    ARRAY_AGG(ft.feeding_time::TEXT ORDER BY ft.feeding_time)
                        FILTER (WHERE ft.feeding_time IS NOT NULL) AS feeding_times
                FROM zoo.enclosure_species es
                JOIN zoo.species s ON s.id = es.species_id
                LEFT JOIN zoo.enclosures e ON e.id = es.enclosure_id
                LEFT JOIN zoo.houses h ON h.id = es.house_id
                LEFT JOIN zoo.zoos z ON z.id = es.zoo_id
                LEFT JOIN zoo.geo_points gp
                       ON gp.entity_type = 'enclosure_species'
                      AND gp.entity_id = es.id
                LEFT JOIN zoo.media ms ON ms.id = s.icon_media_id
                LEFT JOIN zoo.media mimg ON mimg.id = e.image_media_id
                LEFT JOIN zoo.feeding_times ft
                       ON ft.enclosure_species_id = es.id
                WHERE {where}
                GROUP BY
                    es.id, es.species_id, es.enclosure_id, es.house_id,
                    es.note, es.count_adult, es.count_juvenile, es.counted_at, es.domain_id,
                    s.german_name, s.latin_name, s.wikidata_id,
                    s.iucn_status_id, s.iucn_id, s.gbif_taxon_key,
                    e.name, e.sort_order, e.domain_id,
                    h.name, h.domain_id,
                    gp.latitude, gp.longitude,
                    ms.storage_path, ms.filename,
                    mimg.storage_path, mimg.filename
                ORDER BY s.german_name
            """, params)
            results = cur.fetchall()
        return jsonify([dict(r) for r in results]), 200
    except Exception:
        logging.exception(f"Exception in GET /api/v1/zoos/{zoo}/enclosures")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@enclosure_species_bp.route("/api/v1/zoos/<zoo>/enclosure_species", methods=["POST"])
@limiter.limit("30 per minute")
def create_enclosure(zoo):
    """
    Neue enclosure_species anlegen.
    Body: {
        species_id,          ← Pflicht
        enclosure_id,        ← optional (Freigehege)
        house_id,            ← optional (Tierhaus)
        note,                ← optional
        count_adult,         ← optional
        count_juvenile,      ← optional
        latitude,            ← optional
        longitude,           ← optional
        feeding_times        ← optional ["14:00", "16:00"]
    }
    """
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "write")
    if err: return err

    data           = request.get_json(silent=True) or {}
    species_id     = data.get("species_id")
    enclosure_id   = data.get("enclosure_id")
    house_id       = data.get("house_id")
    note           = data.get("note", "").strip() or None
    count_adult    = data.get("count_adult")
    count_juvenile = data.get("count_juvenile")
    latitude       = data.get("latitude")
    longitude      = data.get("longitude")
    domain_id      = data.get("domain_id")
    feeding_times  = data.get("feeding_times", [])

    if not species_id:
        return jsonify({"error": "species_id required"}), 400

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:

            # Zoo-ID ermitteln
            cur.execute("SELECT id FROM zoo.zoos WHERE slug = %s", (zoo,))
            zoo_row = cur.fetchone()
            if not zoo_row:
                return jsonify({"error": "Zoo not found"}), 404
            zoo_id = zoo_row["id"]

            # Species prüfen
            cur.execute("SELECT id FROM zoo.species WHERE id = %s", (species_id,))
            if not cur.fetchone():
                return jsonify({"error": "Invalid species_id"}), 400

            # Enclosure prüfen (muss zum Zoo gehören)
            if enclosure_id is not None:
                cur.execute("""
                    SELECT id FROM zoo.enclosures
                    WHERE id = %s AND zoo_id = %s
                """, (enclosure_id, zoo_id))
                if not cur.fetchone():
                    return jsonify({"error": "Invalid enclosure_id"}), 400

            # House prüfen (muss zum Zoo gehören)
            if house_id is not None:
                cur.execute("""
                    SELECT id FROM zoo.houses
                    WHERE id = %s AND zoo_id = %s
                """, (house_id, zoo_id))
                if not cur.fetchone():
                    return jsonify({"error": "Invalid house_id"}), 400

            # enclosure_species anlegen
            cur.execute("""
                INSERT INTO zoo.enclosure_species
                    (species_id, enclosure_id, house_id, note,
                    count_adult, count_juvenile, zoo_id, domain_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """, (species_id, enclosure_id, house_id, note,
                    count_adult, count_juvenile, zoo_id, domain_id))
            es_id = cur.fetchone()["id"]

            # GPS-Position
            if latitude is not None and longitude is not None:
                try:
                    latitude, longitude = round_coordinates(latitude, longitude)
                except ValueError as e:
                    return jsonify({"error": str(e)}), 400
                cur.execute("""
                    INSERT INTO zoo.geo_points
                        (entity_type, entity_id, latitude, longitude)
                    VALUES ('enclosure_species', %s, %s, %s)
                    ON CONFLICT (entity_type, entity_id)
                    DO UPDATE SET latitude = EXCLUDED.latitude,
                                  longitude = EXCLUDED.longitude
                """, (es_id, latitude, longitude))

            # Fütterungszeiten
            for t in feeding_times:
                cur.execute("""
                    INSERT INTO zoo.feeding_times
                        (enclosure_species_id, feeding_time)
                    VALUES (%s, %s)
                """, (es_id, t))

        pg.commit()
        return jsonify({"id": es_id, "message": "Created"}), 201
    except Exception:
        logging.exception(f"Exception in POST /api/v1/zoos/{zoo}/enclosures")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@enclosure_species_bp.route("/api/v1/zoos/<zoo>/enclosure_species/<int:es_id>", methods=["PUT"])
@limiter.limit("30 per minute")
def update_enclosure(zoo, es_id):
    """
    enclosure_species bearbeiten.
    Erlaubte Felder: enclosure_id, house_id, note, count_adult,
                     count_juvenile, latitude, longitude, feeding_times
    """
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "write")
    if err: return err

    data = request.get_json(silent=True) or {}

    ALLOWED = {"enclosure_id", "house_id", "domain_id", "note", "count_adult",
               "count_juvenile", "latitude", "longitude", "feeding_times"}
    unknown = set(data.keys()) - ALLOWED
    if unknown:
        return jsonify({"error": f"Unknown fields: {', '.join(sorted(unknown))}"}), 400
    if not data:
        return jsonify({"error": "No fields to update"}), 400

    latitude      = data.pop("latitude", None)
    longitude     = data.pop("longitude", None)
    feeding_times = data.pop("feeding_times", None)

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor() as cur:

            # Prüfen ob enclosure_species zum Zoo gehört
            cur.execute("""
                SELECT es.id FROM zoo.enclosure_species es
                LEFT JOIN zoo.enclosures e ON e.id = es.enclosure_id
                LEFT JOIN zoo.houses h ON h.id = es.house_id
                LEFT JOIN zoo.zoos z ON z.id = es.zoo_id
                WHERE es.id = %s AND z.slug = %s
            """, (es_id, zoo))
            if not cur.fetchone():
                return jsonify({"error": "Not found"}), 404

            # Felder updaten
            if data:
                set_clauses = ", ".join(f"{k} = %s" for k in data)
                values = list(data.values()) + [es_id]
                cur.execute(f"""
                    UPDATE zoo.enclosure_species SET {set_clauses}
                    WHERE id = %s
                """, values)

            # GPS-Position
            if latitude is not None and longitude is not None:
                try:
                    latitude, longitude = round_coordinates(latitude, longitude)
                except ValueError as e:
                    return jsonify({"error": str(e)}), 400
                cur.execute("""
                    INSERT INTO zoo.geo_points
                        (entity_type, entity_id, latitude, longitude)
                    VALUES ('enclosure_species', %s, %s, %s)
                    ON CONFLICT (entity_type, entity_id)
                    DO UPDATE SET latitude = EXCLUDED.latitude,
                                  longitude = EXCLUDED.longitude
                """, (es_id, latitude, longitude))

            # Fütterungszeiten
            if feeding_times is not None:
                cur.execute("""
                    DELETE FROM zoo.feeding_times
                    WHERE enclosure_species_id = %s
                """, (es_id,))
                for t in feeding_times:
                    cur.execute("""
                        INSERT INTO zoo.feeding_times
                            (enclosure_species_id, feeding_time)
                        VALUES (%s, %s)
                    """, (es_id, t))

        pg.commit()
        return jsonify({"message": "Updated"}), 200
    except Exception:
        logging.exception(f"Exception in PUT /api/v1/zoos/{zoo}/enclosures/{es_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@enclosure_species_bp.route("/api/v1/zoos/<zoo>/enclosure_species/<int:es_id>", methods=["DELETE"])
@limiter.limit("10 per minute")
def delete_enclosure(zoo, es_id):
    """enclosure_species löschen."""
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "write")
    if err: return err

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor() as cur:
            cur.execute("""
                DELETE FROM zoo.enclosure_species es
                USING zoo.enclosures e, zoo.zoos z
                WHERE es.id = %s
                AND e.id = es.enclosure_id
                AND z.id = e.zoo_id
                AND z.slug = %s
            """, (es_id, zoo))
            if cur.rowcount == 0:
                # Auch ohne Enclosure löschen (nur house_id oder ohne Zuordnung)
                cur.execute("""
                    DELETE FROM zoo.enclosure_species
                    WHERE id = %s
                """, (es_id,))
                if cur.rowcount == 0:
                    return jsonify({"error": "Not found"}), 404
        pg.commit()
        return jsonify({"message": "Deleted"}), 200
    except Exception:
        logging.exception(f"Exception in DELETE /api/v1/zoos/{zoo}/enclosures/{es_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()
