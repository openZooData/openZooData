"""
routes/species.py — Globale Species-Endpoints

GET    /api/v1/species              → alle validen Species
GET    /api/v1/species/<id>         → Species Details
POST   /api/v1/species              → anlegen (zoo_admin, editor)
PUT    /api/v1/species/<id>         → bearbeiten (super_admin only)
DELETE /api/v1/species/<id>         → löschen (super_admin, nur ohne enclosure_species)
"""

import logging
import psycopg2.extras
from flask import Blueprint, jsonify, request
from db import get_pg_connection
from extensions import limiter
from helpers.authz import require_authenticated, require_super_admin, require_zoo_access, require_any_write_access
from helpers.audit import log_action
from helpers.wikidata import fetch_species_data, build_species_filename

species_bp = Blueprint("species", __name__)


@species_bp.route("/api/v1/species", methods=["GET"])
@limiter.limit("60 per minute")
def list_species():
    """
    Alle validen Species (id_valid=TRUE).
    Query-Parameter:
      ?search=<str>  — Suche in deutschem oder lateinischem Namen
      ?limit=<int>   — max. Anzahl (default 500)
      ?offset=<int>  — Pagination
    """
    user_id, err = require_authenticated()
    if err: return err

    search = request.args.get("search", "").strip()
    try:
        limit  = min(int(request.args.get("limit", 500)), 1000)
        offset = int(request.args.get("offset", 0))
    except ValueError:
        return jsonify({"error": "limit and offset must be integers"}), 400

    conditions = ["s.id_valid = TRUE"]
    params     = []

    if search:
        conditions.append("(s.german_name ILIKE %s OR s.latin_name ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])

    where = " AND ".join(conditions)
    params.extend([limit, offset])

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(f"""
                SELECT
                    s.id, s.wikidata_id, s.german_name, s.latin_name,
                    s.iucn_status_id, s.iucn_id, s.gbif_taxon_key,
                    s.iucn_population_trend_id, s.id_valid,
                    m.storage_path || m.filename AS icon_path
                FROM zoo.species s
                LEFT JOIN zoo.media m ON m.id = s.icon_media_id
                WHERE {where}
                ORDER BY s.german_name
                LIMIT %s OFFSET %s
            """, params)
            results = cur.fetchall()
        return jsonify([dict(r) for r in results]), 200
    except Exception:
        logging.exception("Exception in GET /api/v1/species")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@species_bp.route("/api/v1/species/<int:species_id>", methods=["GET"])
@limiter.limit("60 per minute")
def get_species(species_id):
    """Species Details inkl. Taxonomie."""
    user_id, err = require_authenticated()
    if err: return err

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    s.id, s.wikidata_id, s.german_name, s.latin_name,
                    s.iucn_status_id, s.iucn_id, s.gbif_taxon_key,
                    s.iucn_population_trend_id, s.id_valid,
                    s.tax_kingdom_id, s.tax_phylum_id, s.tax_class_id,
                    s.tax_order_id, s.tax_family_id, s.tax_genus_id,
                    s.wiki_fetched_at, s.iucn_fetched_at,
                    m.storage_path || m.filename AS icon_path
                FROM zoo.species s
                LEFT JOIN zoo.media m ON m.id = s.icon_media_id
                WHERE s.id = %s
            """, (species_id,))
            row = cur.fetchone()
            if not row:
                return jsonify({"error": "Species not found"}), 404
        return jsonify(dict(row)), 200
    except Exception:
        logging.exception(f"Exception in GET /api/v1/species/{species_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@species_bp.route("/api/v1/species", methods=["POST"])
@limiter.limit("30 per minute")
def create_species():
    """
    Neue Species anlegen.
    Auth: JWT mit zoo_admin oder editor Rolle auf irgendeinem Zoo.
    Body: { german_name, latin_name, wikidata_id }
    """
    user_id, err = require_any_write_access()
    if err: return err

    data        = request.get_json(silent=True) or {}
    german_name = data.get("german_name", "").strip()
    latin_name  = data.get("latin_name", "").strip() or None
    wikidata_id = data.get("wikidata_id", "").strip() or None

    if not german_name:
        return jsonify({"error": "german_name required"}), 400

    # Wikidata-Anreicherung (blocking) — vor DB-Write, damit latin_name
    # für den Dateinamen bekannt ist.
    wiki_data = {}
    if wikidata_id:
        wiki_data = fetch_species_data(wikidata_id)
        if wiki_data.get("latin_name") and not latin_name:
            latin_name = wiki_data["latin_name"]

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                INSERT INTO zoo.species (german_name, latin_name, wikidata_id, id_valid,
                    tax_kingdom_id, tax_phylum_id, tax_class_id, tax_order_id,
                    tax_family_id, tax_genus_id, iucn_status_id,
                    iucn_population_trend_id, iucn_id, gbif_taxon_key)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, german_name, latin_name, wikidata_id, id_valid
            """, (
                german_name, latin_name, wikidata_id, bool(wikidata_id),
                wiki_data.get("tax_kingdom_id"),
                wiki_data.get("tax_phylum_id"),
                wiki_data.get("tax_class_id"),
                wiki_data.get("tax_order_id"),
                wiki_data.get("tax_family_id"),
                wiki_data.get("tax_genus_id"),
                wiki_data.get("iucn_status_id"),
                wiki_data.get("iucn_population_trend_id"),
                wiki_data.get("iucn_id"),
                wiki_data.get("gbif_taxon_key"),
            ))
            new_species = dict(cur.fetchone())
            species_id  = new_species["id"]

            # Leeren translations-Eintrag anlegen
            cur.execute("""
                INSERT INTO zoo.translations (entity_type, entity_id, de)
                VALUES ('species', %s, %s)
                ON CONFLICT DO NOTHING
            """, (species_id, german_name))

            # Leere species_texts-Zeilen für alle 5 Felder anlegen.
            # Werden später durch enrich_species_texts.py (Cronjob) befüllt.
            # translations_valid bleibt FALSE bis alle Felder + Sprachen gefüllt sind.
            for field in ("description", "habitat", "food", "family_life", "fun_fact"):
                cur.execute("""
                    INSERT INTO zoo.species_texts (species_id, field)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                """, (species_id, field))

            # Media-Eintrag für Icon anlegen und icon_media_id direkt verknüpfen
            if wikidata_id:
                filename = build_species_filename(
                    wikidata_id, new_species.get("latin_name"))
                cur.execute("""
                    INSERT INTO zoo.media
                        (entity_type, entity_id, storage_path, filename,
                         mime_type, label)
                    VALUES ('species', %s, 'species/', %s, 'image/png', 'icon')
                    RETURNING id
                """, (species_id, filename))
                media_id = cur.fetchone()["id"]
                cur.execute("""
                    UPDATE zoo.species SET icon_media_id = %s WHERE id = %s
                """, (media_id, species_id))
                new_species["icon_media_id"] = media_id
                new_species["icon_filename"]  = filename

        pg.commit()
        log_action("species_created", actor_user_id=user_id,
                   target_type="species", target_id=new_species["id"],
                   details={"german_name": german_name, "wikidata_id": wikidata_id})
        return jsonify({
            **new_species,
            "message": f"Tier '{german_name}' erfolgreich angelegt"
        }), 201
    except Exception as e:
        if pg: pg.rollback()
        if "unique" in str(e).lower() or "idx_species_wikidata" in str(e).lower():
            return jsonify({
                "error": "Tier mit dieser Wikidata-ID bereits vorhanden",
                "code": "duplicate_wikidata_id"
            }), 409
        logging.exception("Exception in POST /api/v1/species")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@species_bp.route("/api/v1/species/<int:species_id>", methods=["PUT"])
@limiter.limit("30 per minute")
def update_species(species_id):
    """
    Species bearbeiten — nur super_admin.
    Alle Felder erlaubt: german_name, latin_name, wikidata_id, id_valid
    """
    actor_id, err = require_super_admin()
    if err: return err

    data = request.get_json(silent=True) or {}
    ALLOWED = {"german_name", "latin_name", "wikidata_id", "id_valid"}
    unknown = set(data.keys()) - ALLOWED
    if unknown:
        return jsonify({"error": f"Unknown fields: {', '.join(sorted(unknown))}"}), 400
    if not data:
        return jsonify({"error": "No fields to update"}), 400

    # Validierung
    if "german_name" in data and not str(data["german_name"]).strip():
        return jsonify({"error": "german_name must not be empty"}), 400

    set_clauses = ", ".join(f"{k} = %s" for k in data)
    values = list(data.values()) + [species_id]

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor() as cur:
            cur.execute(f"""
                UPDATE zoo.species SET {set_clauses}
                WHERE id = %s
                RETURNING id
            """, values)
            if not cur.fetchone():
                return jsonify({"error": "Species not found"}), 404
        pg.commit()
        return jsonify({"message": "Updated"}), 200
    except Exception as e:
        if pg: pg.rollback()
        if "unique" in str(e).lower():
            return jsonify({"error": "Wikidata-ID bereits vorhanden"}), 409
        logging.exception(f"Exception in PUT /api/v1/species/{species_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@species_bp.route("/api/v1/species/<int:species_id>", methods=["DELETE"])
@limiter.limit("10 per minute")
def delete_species(species_id):
    """
    Species löschen — nur super_admin.
    Schlägt fehl wenn noch enclosure_species ODER births verknüpft sind.
    (births.species_id hat keine ON DELETE-Klausel — ohne diese Prüfung
    würde der DELETE an der FK-Constraint crashen statt sauber 409 zu geben.)
    """
    actor_id, err = require_super_admin()
    if err: return err

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor() as cur:
            # Prüfen ob noch enclosure_species vorhanden
            cur.execute("""
                SELECT COUNT(*) FROM zoo.enclosure_species
                WHERE species_id = %s
            """, (species_id,))
            count = cur.fetchone()[0]
            if count > 0:
                return jsonify({
                    "error": f"Cannot delete: {count} enclosure_species verknüpft"
                }), 409

            # Prüfen ob noch births vorhanden — births_species_id_fkey hat
            # kein ON DELETE, würde sonst als FK-Violation einen 500 auslösen
            cur.execute("""
                SELECT COUNT(*) FROM zoo.births
                WHERE species_id = %s
            """, (species_id,))
            births_count = cur.fetchone()[0]
            if births_count > 0:
                return jsonify({
                    "error": f"Cannot delete: {births_count} births verknüpft"
                }), 409

            cur.execute("DELETE FROM zoo.species WHERE id = %s", (species_id,))
            if cur.rowcount == 0:
                return jsonify({"error": "Species not found"}), 404

            # Media-Eintrag mitlöschen (Datei bleibt auf Disk,
            # nur der DB-Eintrag wird entfernt).
            cur.execute("""
                DELETE FROM zoo.media
                WHERE entity_type = 'species' AND entity_id = %s
            """, (species_id,))

        pg.commit()
        log_action("species_deleted", actor_user_id=actor_id,
                   target_type="species", target_id=species_id,
                   details={"species_id": species_id})
        return jsonify({"message": "Deleted"}), 200
    except Exception:
        logging.exception(f"Exception in DELETE /api/v1/species/{species_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()
