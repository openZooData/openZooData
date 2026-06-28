import logging
import os
import subprocess
import sys
import psycopg2.extras
from flask import Blueprint, jsonify, request
from db import get_pg_connection
from extensions import limiter
from helpers.coordinates import is_valid_slug
from helpers.authz import require_zoo_access, require_super_admin
from helpers.audit import log_action

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

    where_extra = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    
    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(f"""
                SELECT
                    s.id, s.wikidata_id, s.german_name, s.latin_name,
                    s.iucn_status_id, s.iucn_id, s.gbif_taxon_key,
                    s.iucn_population_trend_id, s.id_valid,
                    COUNT(DISTINCT e.id) AS enclosure_count,
                    m.storage_path || m.filename AS icon_path
                FROM zoo.species s
                LEFT JOIN zoo.enclosure_species es ON es.species_id = s.id
                LEFT JOIN zoo.enclosures e ON e.id = es.enclosure_id
                    AND e.zoo_id = (SELECT id FROM zoo.zoos WHERE slug = %s)
                LEFT JOIN zoo.media m ON m.id = s.icon_media_id
                {where_extra}
                GROUP BY s.id, m.storage_path, m.filename
                ORDER BY s.german_name
            """, params)
            results = cur.fetchall()
        return jsonify([dict(r) for r in results]), 200
    except Exception:
        logging.exception(f"Exception in GET /api/v1/zoos/{zoo}/species")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@zoo_species_bp.route("/api/v1/species/<int:species_id>/icon/generate", methods=["POST"])
@limiter.limit("5 per minute")
def generate_species_icon(species_id):
    """
    Stößt die Icon-Generierung für eine Species via OpenAI Images API an.
    Läuft asynchron (Fire-and-forget) — Antwort kommt sofort (202).
    Nur super_admin.
    """
    user_id, err = require_super_admin()
    if err: return err

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id, german_name, latin_name FROM zoo.species WHERE id = %s
            """, (species_id,))
            row = cur.fetchone()
        if not row:
            return jsonify({"error": "Species not found"}), 404
    except Exception:
        logging.exception(f"Exception in POST /api/v1/species/{species_id}/icon/generate (DB)")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg:
            pg.close()

    try:
        script_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "tools", "generate_species_icons.py"
        )
        subprocess.Popen(
            [sys.executable, script_path, "--species", str(species_id), "--force"],
            close_fds=True,
        )
        logging.info(
            f"Icon-Generierung gestartet: species_id={species_id} "
            f"({row['german_name']})"
        )
        log_action("species_icon_generate_triggered", actor_user_id=user_id,
                   target_type="species", target_id=species_id,
                   details={"german_name": row["german_name"], "latin_name": row["latin_name"]})
    except Exception:
        logging.exception(f"Exception beim Starten der Icon-Generierung für species_id={species_id}")
        return jsonify({"error": "Icon-Generierung konnte nicht gestartet werden"}), 500

    return jsonify({
        "message": "Icon-Generierung gestartet",
        "species_id": species_id,
        "german_name": row["german_name"],
        "latin_name": row["latin_name"],
    }), 202
