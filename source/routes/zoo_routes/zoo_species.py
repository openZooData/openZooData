import logging
import psycopg2.extras
from flask import Blueprint, jsonify, request
from db import get_pg_connection
from extensions import limiter
from helpers.coordinates import is_valid_slug
from helpers.authz import require_zoo_access

zoo_species_bp = Blueprint("zoo_species_bp", __name__)

@zoo_species_bp.route("/api/v1/zoos/<zoo>/species", methods=["GET"])
@limiter.limit("60 per minute")
def get_zoo_species(zoo):
    """
    Alle Tierarten die in diesem Zoo gehalten werden.
    Aggregiert aus enclosure_species — jede Art einmal, mit Zoo-Kontext.

    Query-Parameter:
      ?domain_id=<int>   — nur Arten einer Domain
      ?search=<str>      — Suche in deutschem oder lateinischem Namen
    """
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "read")
    if err: return err

    domain_id = request.args.get("domain_id")
    search    = request.args.get("search", "").strip()

    # Species sind global — alle Species zurückgeben.
    # enclosure_count zeigt wie viele Gehege dieses Zoos die Art halten.
    conditions = []
    params     = [zoo]  # Zoo-Slug für enclosure_count

    if domain_id:
        try:
            domain_id = int(domain_id)
        except ValueError:
            return jsonify({"error": "domain_id must be an integer"}), 400
        conditions.append("e.domain_id = %s")
        params.append(domain_id)

    if search:
        conditions.append(
            "(s.german_name ILIKE %s OR s.latin_name ILIKE %s)"
        )
        params.extend([f"%{search}%", f"%{search}%"])

    where_extra = ("AND " + " AND ".join(conditions)) if conditions else ""

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(f"""
                SELECT
                    s.id, s.wikidata_id, s.german_name, s.latin_name,
                    s.iucn_status_id, s.iucn_id, s.gbif_taxon_key,
                    s.iucn_population_trend_id, s.id_valid,
                    COUNT(DISTINCT e.id) AS enclosure_count
                FROM zoo.species s
                LEFT JOIN zoo.enclosure_species es ON es.species_id = s.id
                LEFT JOIN zoo.enclosures e ON e.id = es.enclosure_id
                    AND e.zoo_id = (SELECT id FROM zoo.zoos WHERE slug = %s)
                {where_extra}
                GROUP BY s.id
                ORDER BY s.german_name
            """, params)
            results = cur.fetchall()
        return jsonify([dict(r) for r in results]), 200
    except Exception:
        logging.exception(f"Exception in GET /api/v1/zoos/{zoo}/species")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()
