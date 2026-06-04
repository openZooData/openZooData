import logging
import psycopg2.extras
from flask import Blueprint, jsonify, request
from helpers.authz import require_authenticated, require_zoo_access, require_super_admin
from db import get_pg_connection
from extensions import limiter

species_bp = Blueprint("species", __name__)


@species_bp.route("/api/v1/species", methods=["GET"])
@limiter.limit("60 per minute")
def search_species():
    """
    Zoo-übergreifende Species-Suche.
    Erfordert nur gültiges JWT — keine Zoo-spezifische Rolle.
    """
    user_id, err = require_authenticated()
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
                FROM zoo.species
                WHERE german_name ILIKE %s OR latin_name ILIKE %s
                ORDER BY german_name
                LIMIT 20
            """, (f"%{query}%", f"%{query}%"))
            results = cur.fetchall()
        return jsonify([dict(r) for r in results]), 200
    except Exception:
        logging.exception("Exception in /api/v1/species GET")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg:
            pg.close()


@species_bp.route("/api/v1/species", methods=["POST"])
@limiter.limit("30 per minute")
def create_species():
    """
    Neue Species anlegen.
    Migration v7: Berechtigt sind zoo_editor und super_admin (nicht mehr zoo_admin pauschal).
    Wikidata-ID ist Pflicht für direktes Anlegen — sonst → Proposal.

    Body: { german_name, latin_name, wikidata_id (Pflicht), zoo_slug }
    zoo_slug: für Berechtigungsprüfung (editor muss Zugriff auf diesen Zoo haben)
    """
    user_id, err = require_authenticated()
    if err: return err

    data        = request.get_json(silent=True) or {}
    german_name = data.get("german_name", "").strip()
    latin_name  = data.get("latin_name", "").strip()
    wikidata_id = (data.get("wikidata_id") or "").strip() or None
    zoo_slug    = data.get("zoo_slug", "").strip()

    if not german_name:
        return jsonify({"error": "german_name required"}), 400

    if not wikidata_id:
        return jsonify({
            "error": "wikidata_id required. Without a validated Wikidata ID, submit a proposal instead."
        }), 400

    # Berechtigungsprüfung: editor/zoo_admin auf einem Zoo ODER super_admin
    # can_access_zoo() ist die einzige autoritative Quelle — kein direkter DB-Zugriff hier.
    from helpers.authz import can_access_zoo, require_super_admin

    # super_admin darf zoo-übergreifend anlegen (kein zoo_slug nötig)
    _sa_id, _sa_err = require_super_admin()
    is_super = _sa_id is not None

    if not is_super:
        if not zoo_slug:
            return jsonify({"error": "zoo_slug required for non-super_admin"}), 400
        if not can_access_zoo(user_id, zoo_slug, "write"):
            return jsonify({"error": "Unauthorized"}), 403

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                INSERT INTO zoo.species (german_name, latin_name, wikidata_id, id_valid)
                VALUES (%s, %s, %s, %s)
                RETURNING id, german_name, latin_name, wikidata_id, id_valid
            """, (german_name, latin_name or None, wikidata_id, bool(wikidata_id)))
            new_species = dict(cur.fetchone())

            cur.execute("""
                INSERT INTO zoo.translations (entity_type, entity_id, de)
                VALUES ('species', %s, %s)
                ON CONFLICT DO NOTHING
            """, (new_species["id"], german_name))

        pg.commit()
        return jsonify(new_species), 201
    except Exception:
        logging.exception("Exception in /api/v1/species POST")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg:
            pg.close()


@species_bp.route("/api/v1/species/<int:species_id>", methods=["DELETE"])
@limiter.limit("10 per minute")
def delete_species(species_id):
    """Nur super_admin darf Species löschen (zoo-übergreifend)."""
    user_id, err = require_super_admin()
    if err: return err

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM zoo.enclosure_species WHERE species_id = %s
            """, (species_id,))
            count = cur.fetchone()[0]
            if count > 0:
                return jsonify({
                    "error": f"Species wird noch in {count} Gehege(n) verwendet"
                }), 409

            cur.execute("DELETE FROM zoo.species WHERE id = %s", (species_id,))
            if cur.rowcount == 0:
                return jsonify({"error": "Not found"}), 404

        pg.commit()
        return jsonify({"message": "Deleted"}), 200
    except Exception:
        logging.exception("Exception in DELETE /api/v1/species")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg:
            pg.close()
