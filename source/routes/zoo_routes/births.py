"""
routes/zoo_routes/births.py — Geburten-Endpoints

Eigenständige CRUD-Endpoints für births, immer mit Bezug auf die
übergeordnete enclosure_species (kommt aus der URL). species_id und
zoo_id werden serverseitig aus der enclosure_species abgeleitet und nie
vom Client mitgeschickt. Ergänzt — ersetzt nicht — das bestehende
verschachtelte births-Array auf enclosure_species (GET/POST/PUT dort
funktioniert unverändert weiter).

Hinweis zur Löschsemantik: wird die übergeordnete enclosure_species selbst
gelöscht, bleiben births als historisches Faktum erhalten
(enclosure_species_id → NULL, siehe enclosure_species.py). Das DELETE hier
ist ein direkter, vollständiger Löschvorgang für einen einzelnen
Geburten-Eintrag (z.B. zur Korrektur einer Fehleingabe) — das sind zwei
unterschiedliche, beide gewollte Vorgänge.

GET    /api/v1/zoos/<zoo>/births                                → alle im Zoo
GET    /api/v1/zoos/<zoo>/enclosure_species/<es_id>/births       → Liste
GET    /api/v1/zoos/<zoo>/enclosure_species/<es_id>/births/<id>  → einzeln
POST   /api/v1/zoos/<zoo>/enclosure_species/<es_id>/births       → anlegen
PUT    /api/v1/zoos/<zoo>/enclosure_species/<es_id>/births/<id>  → bearbeiten
DELETE /api/v1/zoos/<zoo>/enclosure_species/<es_id>/births/<id>  → löschen
"""

import logging
import psycopg2.extras
from flask import Blueprint, jsonify, request
from helpers.authz import require_zoo_access
from helpers.coordinates import is_valid_slug
from db import get_pg_connection
from extensions import limiter

births_bp = Blueprint("births", __name__)


def _get_enclosure_species_or_404(cur, zoo, es_id):
    """
    Prüft dass die enclosure_species existiert und zum angegebenen Zoo
    gehört. Gibt (es_id, species_id, zoo_id) zurück, oder None.
    """
    cur.execute("""
        SELECT es.id, es.species_id, es.zoo_id
        FROM zoo.enclosure_species es
        JOIN zoo.zoos z ON z.id = es.zoo_id
        WHERE es.id = %s AND z.slug = %s
    """, (es_id, zoo))
    return cur.fetchone()


@births_bp.route(
    "/api/v1/zoos/<zoo>/births",
    methods=["GET"])
@limiter.limit("60 per minute")
def list_births_for_zoo(zoo):
    """
    Alle Geburten eines kompletten Zoos, zoo-/artenübergreifend (nicht auf
    eine einzelne enclosure_species beschränkt). births hat eine eigene
    zoo_id-Spalte — kein Join über enclosure_species nötig, funktioniert
    daher auch für births deren enclosure_species inzwischen gelöscht
    wurde (enclosure_species_id ist dann NULL, taucht hier trotzdem auf).
    Optionale Filter: ?species_id=<id>
    """
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "read")
    if err: return err

    species_id_filter = request.args.get("species_id")
    conditions = ["b.zoo_id = (SELECT id FROM zoo.zoos WHERE slug = %s)"]
    params     = [zoo]
    if species_id_filter:
        conditions.append("b.species_id = %s")
        params.append(int(species_id_filter))
    where = " AND ".join(conditions)

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(f"""
                SELECT
                    b.id, b.enclosure_species_id, b.species_id, b.zoo_id,
                    b.birth_date::TEXT, b.count, b.note, b.is_public,
                    s.german_name, s.latin_name,
                    e.name AS enclosure_name, h.name AS house_name
                FROM zoo.births b
                JOIN zoo.species s ON s.id = b.species_id
                LEFT JOIN zoo.enclosure_species es ON es.id = b.enclosure_species_id
                LEFT JOIN zoo.enclosures e ON e.id = es.enclosure_id
                LEFT JOIN zoo.houses h ON h.id = es.house_id
                WHERE {where}
                ORDER BY b.birth_date DESC
            """, params)
            rows = cur.fetchall()
        return jsonify([dict(r) for r in rows]), 200
    except Exception:
        logging.exception(f"Exception in GET /api/v1/zoos/{zoo}/births")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@births_bp.route(
    "/api/v1/zoos/<zoo>/enclosure_species/<int:es_id>/births",
    methods=["GET"])
@limiter.limit("60 per minute")
def list_births(zoo, es_id):
    """Alle Geburten einer enclosure_species."""
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "read")
    if err: return err

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if not _get_enclosure_species_or_404(cur, zoo, es_id):
                return jsonify({"error": "enclosure_species not found"}), 404

            cur.execute("""
                SELECT id, enclosure_species_id, species_id, zoo_id,
                       birth_date::TEXT, count, note, is_public
                FROM zoo.births
                WHERE enclosure_species_id = %s
                ORDER BY birth_date DESC
            """, (es_id,))
            rows = cur.fetchall()
        return jsonify([dict(r) for r in rows]), 200
    except Exception:
        logging.exception(
            f"Exception in GET .../enclosure_species/{es_id}/births")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@births_bp.route(
    "/api/v1/zoos/<zoo>/enclosure_species/<int:es_id>/births/<int:birth_id>",
    methods=["GET"])
@limiter.limit("60 per minute")
def get_birth(zoo, es_id, birth_id):
    """Einzelner Geburten-Eintrag."""
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "read")
    if err: return err

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if not _get_enclosure_species_or_404(cur, zoo, es_id):
                return jsonify({"error": "enclosure_species not found"}), 404

            cur.execute("""
                SELECT id, enclosure_species_id, species_id, zoo_id,
                       birth_date::TEXT, count, note, is_public
                FROM zoo.births
                WHERE id = %s AND enclosure_species_id = %s
            """, (birth_id, es_id))
            row = cur.fetchone()
        if not row:
            return jsonify({"error": "Not found"}), 404
        return jsonify(dict(row)), 200
    except Exception:
        logging.exception(f"Exception in GET .../births/{birth_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@births_bp.route(
    "/api/v1/zoos/<zoo>/enclosure_species/<int:es_id>/births",
    methods=["POST"])
@limiter.limit("30 per minute")
def create_birth(zoo, es_id):
    """
    Neue Geburt anlegen.
    Body: { birth_date ← Pflicht ("YYYY-MM-DD"),
            count       ← optional, Default 1,
            note        ← optional,
            is_public   ← optional, Default true }
    species_id/zoo_id kommen aus der enclosure_species, nie vom Client.
    """
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "write")
    if err: return err

    data       = request.get_json(silent=True) or {}
    birth_date = data.get("birth_date")
    count      = data.get("count", 1)
    note       = (data.get("note") or "").strip() or None
    is_public  = data.get("is_public", True)

    if not birth_date:
        return jsonify({"error": "birth_date required"}), 400

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            es_row = _get_enclosure_species_or_404(cur, zoo, es_id)
            if not es_row:
                return jsonify({"error": "enclosure_species not found"}), 404
            species_id, zoo_id = es_row["species_id"], es_row["zoo_id"]

            cur.execute("""
                INSERT INTO zoo.births
                    (enclosure_species_id, species_id, zoo_id,
                     birth_date, count, note, is_public)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (es_id, species_id, zoo_id, birth_date, count, note, is_public))
            birth_id = cur.fetchone()["id"]
        pg.commit()
        return jsonify({"id": birth_id, "message": "Created"}), 201
    except Exception:
        logging.exception(
            f"Exception in POST .../enclosure_species/{es_id}/births")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@births_bp.route(
    "/api/v1/zoos/<zoo>/enclosure_species/<int:es_id>/births/<int:birth_id>",
    methods=["PUT"])
@limiter.limit("30 per minute")
def update_birth(zoo, es_id, birth_id):
    """
    Geburten-Eintrag bearbeiten.
    Erlaubte Felder: birth_date, count, note, is_public
    (species_id/zoo_id/enclosure_species_id sind über diesen Endpoint
    nicht änderbar — 400 bei Versuch.)
    """
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "write")
    if err: return err

    data = request.get_json(silent=True) or {}

    ALLOWED = {"birth_date", "count", "note", "is_public"}
    unknown = set(data.keys()) - ALLOWED
    if unknown:
        return jsonify({"error": f"Unknown fields: {', '.join(sorted(unknown))}"}), 400
    if not data:
        return jsonify({"error": "No fields to update"}), 400

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor() as cur:
            if not _get_enclosure_species_or_404(cur, zoo, es_id):
                return jsonify({"error": "enclosure_species not found"}), 404

            cur.execute("""
                SELECT id FROM zoo.births
                WHERE id = %s AND enclosure_species_id = %s
            """, (birth_id, es_id))
            if not cur.fetchone():
                return jsonify({"error": "Not found"}), 404

            set_clauses = ", ".join(f"{k} = %s" for k in data)
            values = list(data.values()) + [birth_id]
            cur.execute(f"""
                UPDATE zoo.births SET {set_clauses}
                WHERE id = %s
            """, values)
        pg.commit()
        return jsonify({"message": "Updated"}), 200
    except Exception:
        logging.exception(f"Exception in PUT .../births/{birth_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@births_bp.route(
    "/api/v1/zoos/<zoo>/enclosure_species/<int:es_id>/births/<int:birth_id>",
    methods=["DELETE"])
@limiter.limit("10 per minute")
def delete_birth(zoo, es_id, birth_id):
    """
    Geburten-Eintrag direkt löschen (z.B. Korrektur einer Fehleingabe).
    Anders als beim Löschen der enclosure_species selbst (dort: SET NULL,
    historisches Faktum bleibt erhalten) wird hier die Zeile tatsächlich
    entfernt — das ist hier ein bewusster, gezielter Löschvorgang.
    """
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "write")
    if err: return err

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor() as cur:
            if not _get_enclosure_species_or_404(cur, zoo, es_id):
                return jsonify({"error": "enclosure_species not found"}), 404

            cur.execute("""
                DELETE FROM zoo.births
                WHERE id = %s AND enclosure_species_id = %s
            """, (birth_id, es_id))
            if cur.rowcount == 0:
                return jsonify({"error": "Not found"}), 404
        pg.commit()
        return jsonify({"message": "Deleted"}), 200
    except Exception:
        logging.exception(f"Exception in DELETE .../births/{birth_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()
