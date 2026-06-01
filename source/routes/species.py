import logging
import psycopg2.extras
from flask import Blueprint, jsonify, request
from helpers.auth_utils import require_jwt_read, require_jwt_write, verify_access_token
from db import get_pg_connection
from extensions import limiter

species_bp = Blueprint("species", __name__)


@species_bp.route("/api/v1/species", methods=["GET"])
@limiter.limit("60 per minute")
def search_species():
    payload, err = require_jwt_read(None)
    if err: return err

    query = request.args.get("search", "").strip()
    if not query:
        return jsonify({"error": "search parameter required"}), 400

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id, wikidata_id, latin_name, german_name,
                       iucn_status_id, gbif_taxon_key, id_valid
                FROM species
                WHERE german_name ILIKE %s OR latin_name ILIKE %s
                ORDER BY german_name
                LIMIT 20
            """, (f"%{query}%", f"%{query}%"))
            results = cur.fetchall()
        return jsonify([dict(r) for r in results]), 200
    except Exception as e:
        logging.exception("Exception in /api/v1/species GET")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg:
            pg.close()


@species_bp.route("/api/v1/species", methods=["POST"])
@limiter.limit("30 per minute")
def create_species():
    payload, err = require_jwt_write(None)
    if err: return err
    if payload.get("role") not in ("zoo_admin", "super_admin"):
        return jsonify({"error": "Unauthorized"}), 403

    data        = request.get_json(silent=True) or {}
    german_name = data.get("german_name", "").strip()
    latin_name  = data.get("latin_name", "").strip()
    wikidata_id = (data.get("wikidata_id") or "").strip() or None

    if not german_name:
        return jsonify({"error": "german_name required"}), 400

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                INSERT INTO species (german_name, latin_name, wikidata_id, id_valid)
                VALUES (%s, %s, %s, %s)
                RETURNING id, german_name, latin_name, wikidata_id, id_valid
            """, (german_name, latin_name or None, wikidata_id, bool(wikidata_id)))
            new_species = dict(cur.fetchone())

            cur.execute("""
                INSERT INTO translations (entity_type, entity_id, de)
                VALUES ('species', %s, %s)
                ON CONFLICT DO NOTHING
            """, (new_species["id"], german_name))

        pg.commit()
        return jsonify(new_species), 201
    except Exception as e:
        logging.exception("Exception in /api/v1/species POST")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg:
            pg.close()


@species_bp.route("/api/v1/species/<int:species_id>", methods=["DELETE"])
@limiter.limit("10 per minute")
def delete_species(species_id):
    payload, err = require_jwt_write(None)
    if err: return err
    # Fix 4: Species sind zoo-übergreifend — nur super_admin darf löschen
    if payload.get("role") != "super_admin":
        return jsonify({"error": "Unauthorized"}), 403

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM enclosure_species WHERE species_id = %s
            """, (species_id,))
            count = cur.fetchone()[0]
            if count > 0:
                return jsonify({
                    "error": f"Species wird noch in {count} Gehege(n) verwendet"
                }), 409

            cur.execute("DELETE FROM species WHERE id = %s", (species_id,))
            if cur.rowcount == 0:
                return jsonify({"error": "Not found"}), 404

        pg.commit()
        return jsonify({"message": "Deleted"}), 200
    except Exception as e:
        logging.exception("Exception in DELETE /api/v1/species")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg:
            pg.close()
