"""
routes/zoo_routes/feeding_times.py — Fütterungszeiten-Endpoints

Eigenständige CRUD-Endpoints für feeding_times, immer mit Bezug auf die
übergeordnete enclosure_species (kommt aus der URL, wird nie vom Client
mitgeschickt). Ergänzt — ersetzt nicht — das bestehende verschachtelte
feeding_times-Array auf enclosure_species (GET/POST/PUT dort funktioniert
unverändert weiter, z.B. für Clients die lieber alles in einem Call lesen
oder schreiben).

GET    /api/v1/zoos/<zoo>/feeding_times                                → alle im Zoo
GET    /api/v1/zoos/<zoo>/enclosure_species/<es_id>/feeding_times      → Liste
GET    /api/v1/zoos/<zoo>/enclosure_species/<es_id>/feeding_times/<id> → einzeln
POST   /api/v1/zoos/<zoo>/enclosure_species/<es_id>/feeding_times      → anlegen
PUT    /api/v1/zoos/<zoo>/enclosure_species/<es_id>/feeding_times/<id> → bearbeiten
DELETE /api/v1/zoos/<zoo>/enclosure_species/<es_id>/feeding_times/<id> → löschen
"""

import logging
import psycopg2.extras
from flask import Blueprint, jsonify, request
from helpers.authz import require_zoo_access
from helpers.audit import log_action
from helpers.coordinates import is_valid_slug
from db import get_pg_connection
from extensions import limiter

feeding_times_bp = Blueprint("feeding_times", __name__)


def _get_enclosure_species_or_404(cur, zoo, es_id):
    """
    Prüft dass die enclosure_species existiert und zum angegebenen Zoo
    gehört. Gibt die Zeile zurück, oder None (→ Aufrufer gibt 404 zurück).
    """
    cur.execute("""
        SELECT es.id FROM zoo.enclosure_species es
        JOIN zoo.zoos z ON z.id = es.zoo_id
        WHERE es.id = %s AND z.slug = %s
    """, (es_id, zoo))
    return cur.fetchone()


@feeding_times_bp.route(
    "/api/v1/zoos/<zoo>/feeding_times",
    methods=["GET"])
@limiter.limit("60 per minute")
def list_feeding_times_for_zoo(zoo):
    """
    Alle Fütterungszeiten eines kompletten Zoos, zoo-/artenübergreifend
    (nicht auf eine einzelne enclosure_species beschränkt).
    Optionaler Filter: ?species_id=<id>
    """
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "read")
    if err: return err

    species_id_filter = request.args.get("species_id")
    conditions = ["es.zoo_id = (SELECT id FROM zoo.zoos WHERE slug = %s)"]
    params     = [zoo]
    if species_id_filter:
        conditions.append("es.species_id = %s")
        params.append(int(species_id_filter))
    where = " AND ".join(conditions)

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(f"""
                SELECT
                    ft.id, ft.enclosure_species_id, ft.feeding_time::TEXT,
                    ft.day_of_week, ft.note, ft.is_public,
                    es.species_id, s.german_name, s.latin_name,
                    e.name AS enclosure_name, h.name AS house_name
                FROM zoo.feeding_times ft
                JOIN zoo.enclosure_species es ON es.id = ft.enclosure_species_id
                JOIN zoo.species s ON s.id = es.species_id
                LEFT JOIN zoo.enclosures e ON e.id = es.enclosure_id
                LEFT JOIN zoo.houses h ON h.id = es.house_id
                WHERE {where}
                ORDER BY s.german_name, ft.feeding_time
            """, params)
            rows = cur.fetchall()
        return jsonify([dict(r) for r in rows]), 200
    except Exception:
        logging.exception(f"Exception in GET /api/v1/zoos/{zoo}/feeding_times")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@feeding_times_bp.route(
    "/api/v1/zoos/<zoo>/enclosure_species/<int:es_id>/feeding_times",
    methods=["GET"])
@limiter.limit("60 per minute")
def list_feeding_times(zoo, es_id):
    """Alle Fütterungszeiten einer enclosure_species."""
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
                SELECT id, enclosure_species_id, feeding_time::TEXT,
                       day_of_week, note, is_public
                FROM zoo.feeding_times
                WHERE enclosure_species_id = %s
                ORDER BY feeding_time
            """, (es_id,))
            rows = cur.fetchall()
        return jsonify([dict(r) for r in rows]), 200
    except Exception:
        logging.exception(
            f"Exception in GET .../enclosure_species/{es_id}/feeding_times")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@feeding_times_bp.route(
    "/api/v1/zoos/<zoo>/enclosure_species/<int:es_id>/feeding_times/<int:ft_id>",
    methods=["GET"])
@limiter.limit("60 per minute")
def get_feeding_time(zoo, es_id, ft_id):
    """Einzelne Fütterungszeit."""
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
                SELECT id, enclosure_species_id, feeding_time::TEXT,
                       day_of_week, note, is_public
                FROM zoo.feeding_times
                WHERE id = %s AND enclosure_species_id = %s
            """, (ft_id, es_id))
            row = cur.fetchone()
        if not row:
            return jsonify({"error": "Not found"}), 404
        return jsonify(dict(row)), 200
    except Exception:
        logging.exception(
            f"Exception in GET .../feeding_times/{ft_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@feeding_times_bp.route(
    "/api/v1/zoos/<zoo>/enclosure_species/<int:es_id>/feeding_times",
    methods=["POST"])
@limiter.limit("30 per minute")
def create_feeding_time(zoo, es_id):
    """
    Neue Fütterungszeit anlegen.
    Body: { feeding_time ← Pflicht ("HH:MM"),
            day_of_week  ← optional (0=Mo … 6=So, leer = täglich),
            note         ← optional,
            is_public    ← optional, Default true }
    """
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "write")
    if err: return err

    data         = request.get_json(silent=True) or {}
    feeding_time = data.get("feeding_time")
    day_of_week  = data.get("day_of_week")
    note         = (data.get("note") or "").strip() or None
    is_public    = data.get("is_public", True)

    if not feeding_time:
        return jsonify({"error": "feeding_time required"}), 400

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if not _get_enclosure_species_or_404(cur, zoo, es_id):
                return jsonify({"error": "enclosure_species not found"}), 404

            cur.execute("""
                INSERT INTO zoo.feeding_times
                    (enclosure_species_id, feeding_time, day_of_week,
                     note, is_public)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """, (es_id, feeding_time, day_of_week, note, is_public))
            ft_id = cur.fetchone()["id"]
        pg.commit()
        with pg.cursor() as _cur:
            _cur.execute("SELECT id FROM zoo.zoos WHERE slug = %s", (zoo,))
            _zr = _cur.fetchone()
            _zoo_id = _zr[0] if _zr else None
        log_action("feeding_time_created", actor_user_id=user_id,
                   zoo_id=_zoo_id, target_type="feeding_time", target_id=ft_id,
                   details={"enclosure_species_id": es_id, "feeding_time": feeding_time,
                             "day_of_week": day_of_week})
        return jsonify({"id": ft_id, "message": "Created"}), 201
    except Exception:
        logging.exception(
            f"Exception in POST .../enclosure_species/{es_id}/feeding_times")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@feeding_times_bp.route(
    "/api/v1/zoos/<zoo>/enclosure_species/<int:es_id>/feeding_times/<int:ft_id>",
    methods=["PUT"])
@limiter.limit("30 per minute")
def update_feeding_time(zoo, es_id, ft_id):
    """
    Fütterungszeit bearbeiten.
    Erlaubte Felder: feeding_time, day_of_week, note, is_public
    """
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "write")
    if err: return err

    data = request.get_json(silent=True) or {}

    ALLOWED = {"feeding_time", "day_of_week", "note", "is_public"}
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
                SELECT id FROM zoo.feeding_times
                WHERE id = %s AND enclosure_species_id = %s
            """, (ft_id, es_id))
            if not cur.fetchone():
                return jsonify({"error": "Not found"}), 404

            set_clauses = ", ".join(f"{k} = %s" for k in data)
            values = list(data.values()) + [ft_id]
            cur.execute(f"""
                UPDATE zoo.feeding_times SET {set_clauses}
                WHERE id = %s
            """, values)
        pg.commit()
        with pg.cursor() as _cur:
            _cur.execute("SELECT id FROM zoo.zoos WHERE slug = %s", (zoo,))
            _zr = _cur.fetchone()
            _zoo_id = _zr[0] if _zr else None
        log_action("feeding_time_updated", actor_user_id=user_id,
                   zoo_id=_zoo_id, target_type="feeding_time", target_id=ft_id,
                   details={"enclosure_species_id": es_id, "fields": list(data.keys())})
        return jsonify({"message": "Updated"}), 200
    except Exception:
        logging.exception(
            f"Exception in PUT .../feeding_times/{ft_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@feeding_times_bp.route(
    "/api/v1/zoos/<zoo>/enclosure_species/<int:es_id>/feeding_times/<int:ft_id>",
    methods=["DELETE"])
@limiter.limit("10 per minute")
def delete_feeding_time(zoo, es_id, ft_id):
    """Fütterungszeit löschen."""
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
                DELETE FROM zoo.feeding_times
                WHERE id = %s AND enclosure_species_id = %s
            """, (ft_id, es_id))
            if cur.rowcount == 0:
                return jsonify({"error": "Not found"}), 404
        pg.commit()
        with pg.cursor() as _cur:
            _cur.execute("SELECT id FROM zoo.zoos WHERE slug = %s", (zoo,))
            _zr = _cur.fetchone()
            _zoo_id = _zr[0] if _zr else None
        log_action("feeding_time_deleted", actor_user_id=user_id,
                   zoo_id=_zoo_id, target_type="feeding_time", target_id=ft_id,
                   details={"enclosure_species_id": es_id})
        return jsonify({"message": "Deleted"}), 200
    except Exception:
        logging.exception(
            f"Exception in DELETE .../feeding_times/{ft_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()
