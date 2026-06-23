"""
routes/zoo_routes/opening_hours.py — Öffnungszeiten-Endpoints

Eigenständige CRUD-Endpoints für alle drei Öffnungszeiten-Tabellen.
Jede Zeile entspricht einem Wochentag (oder täglich wenn day_of_week=null).
Mehrere Einträge pro Wochentag sind erlaubt (z.B. Sommer- vs. Winterzeit
über valid_from/valid_until unterschieden).

Zoo-Öffnungszeiten:
  GET    /api/v1/zoos/<zoo>/opening_hours            → Liste
  GET    /api/v1/zoos/<zoo>/opening_hours/<id>       → einzeln
  POST   /api/v1/zoos/<zoo>/opening_hours            → anlegen
  PUT    /api/v1/zoos/<zoo>/opening_hours/<id>       → bearbeiten
  DELETE /api/v1/zoos/<zoo>/opening_hours/<id>       → löschen

Location-Öffnungszeiten:
  GET    /api/v1/zoos/<zoo>/locations/<loc_id>/opening_hours            → Liste
  GET    /api/v1/zoos/<zoo>/locations/<loc_id>/opening_hours/<id>       → einzeln
  POST   /api/v1/zoos/<zoo>/locations/<loc_id>/opening_hours            → anlegen
  PUT    /api/v1/zoos/<zoo>/locations/<loc_id>/opening_hours/<id>       → bearbeiten
  DELETE /api/v1/zoos/<zoo>/locations/<loc_id>/opening_hours/<id>       → löschen

House-Öffnungszeiten:
  GET    /api/v1/zoos/<zoo>/houses/<house_id>/opening_hours            → Liste
  GET    /api/v1/zoos/<zoo>/houses/<house_id>/opening_hours/<id>       → einzeln
  POST   /api/v1/zoos/<zoo>/houses/<house_id>/opening_hours            → anlegen
  PUT    /api/v1/zoos/<zoo>/houses/<house_id>/opening_hours/<id>       → bearbeiten
  DELETE /api/v1/zoos/<zoo>/houses/<house_id>/opening_hours/<id>       → löschen

day_of_week-Werte: 'monday', 'tuesday', 'wednesday', 'thursday', 'friday',
  'saturday', 'sunday' — oder null für täglich gültig.
open_time / close_time: "HH:MM" (Sekunden werden beim Lesen ergänzt).
valid_from / valid_until: "YYYY-MM-DD" oder null (= immer gültig).
"""

import logging
import psycopg2.extras
from flask import Blueprint, jsonify, request
from db import get_pg_connection
from extensions import limiter
from helpers.authz import require_zoo_access
from helpers.coordinates import is_valid_slug

opening_hours_bp = Blueprint("opening_hours", __name__)

VALID_DAYS = {
    "monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "sunday"
}

ALLOWED_FIELDS = {"day_of_week", "open_time", "close_time",
                  "valid_from", "valid_until", "label"}


# ─────────────────────────────────────────────────────────────────────────────
# Hilfsfunktionen
# ─────────────────────────────────────────────────────────────────────────────

def _validate_oh_body(data, require_day=True):
    """Validiert POST/PUT-Body. Gibt (bereinigtes dict, fehler-str) zurück."""
    unknown = set(data.keys()) - ALLOWED_FIELDS
    if unknown:
        return None, f"Unknown fields: {', '.join(sorted(unknown))}"
    if not data:
        return None, "No fields to update"
    day = data.get("day_of_week")
    if day is not None and day not in VALID_DAYS:
        return None, (f"Invalid day_of_week '{day}'. "
                      f"Allowed: {', '.join(sorted(VALID_DAYS))} or null")
    if require_day and "day_of_week" not in data:
        return None, "day_of_week required"
    return data, None


def _get_zoo_id(cur, zoo):
    cur.execute("SELECT id FROM zoo.zoos WHERE slug = %s", (zoo,))
    row = cur.fetchone()
    return row["id"] if row else None


def _get_location_or_404(cur, zoo, loc_id):
    cur.execute("""
        SELECT l.id FROM zoo.locations l
        JOIN zoo.zoos z ON z.id = l.zoo_id
        WHERE l.id = %s AND z.slug = %s
    """, (loc_id, zoo))
    return cur.fetchone()


def _get_house_or_404(cur, zoo, house_id):
    cur.execute("""
        SELECT h.id FROM zoo.houses h
        JOIN zoo.zoos z ON z.id = h.zoo_id
        WHERE h.id = %s AND z.slug = %s
    """, (house_id, zoo))
    return cur.fetchone()


def _row(r):
    return {
        "id":          r["id"],
        "day_of_week": r["day_of_week"],
        "open_time":   r["open_time"],
        "close_time":  r["close_time"],
        "valid_from":  str(r["valid_from"]) if r["valid_from"] else None,
        "valid_until": str(r["valid_until"]) if r["valid_until"] else None,
        "label":       r["label"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Zoo-Öffnungszeiten  (zoo.zoo_opening_hours)
# ─────────────────────────────────────────────────────────────────────────────

@opening_hours_bp.route(
    "/api/v1/zoos/<zoo>/opening_hours", methods=["GET"])
@limiter.limit("60 per minute")
def list_zoo_opening_hours(zoo):
    """Alle Öffnungszeiten eines Zoos."""
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "read")
    if err: return err
    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            zoo_id = _get_zoo_id(cur, zoo)
            if not zoo_id:
                return jsonify({"error": "Zoo not found"}), 404
            cur.execute("""
                SELECT id, day_of_week, open_time::TEXT, close_time::TEXT,
                       valid_from, valid_until, label
                FROM zoo.zoo_opening_hours
                WHERE zoo_id = %s ORDER BY day_of_week, open_time
            """, (zoo_id,))
            return jsonify([_row(r) for r in cur.fetchall()]), 200
    except Exception:
        logging.exception(f"Exception in GET /api/v1/zoos/{zoo}/opening_hours")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@opening_hours_bp.route(
    "/api/v1/zoos/<zoo>/opening_hours/<int:oh_id>", methods=["GET"])
@limiter.limit("60 per minute")
def get_zoo_opening_hour(zoo, oh_id):
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "read")
    if err: return err
    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            zoo_id = _get_zoo_id(cur, zoo)
            if not zoo_id:
                return jsonify({"error": "Zoo not found"}), 404
            cur.execute("""
                SELECT id, day_of_week, open_time::TEXT, close_time::TEXT,
                       valid_from, valid_until, label
                FROM zoo.zoo_opening_hours
                WHERE id = %s AND zoo_id = %s
            """, (oh_id, zoo_id))
            row = cur.fetchone()
        if not row:
            return jsonify({"error": "Not found"}), 404
        return jsonify(_row(row)), 200
    except Exception:
        logging.exception(f"Exception in GET /api/v1/zoos/{zoo}/opening_hours/{oh_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@opening_hours_bp.route(
    "/api/v1/zoos/<zoo>/opening_hours", methods=["POST"])
@limiter.limit("30 per minute")
def create_zoo_opening_hour(zoo):
    """
    Öffnungszeit für einen Zoo anlegen.
    Body: { day_of_week (Pflicht), open_time, close_time, valid_from,
            valid_until, label }
    """
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "write")
    if err: return err
    data, verr = _validate_oh_body(request.get_json(silent=True) or {},
                                   require_day=True)
    if verr:
        return jsonify({"error": verr}), 400
    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            zoo_id = _get_zoo_id(cur, zoo)
            if not zoo_id:
                return jsonify({"error": "Zoo not found"}), 404
            cur.execute("""
                INSERT INTO zoo.zoo_opening_hours
                    (zoo_id, day_of_week, open_time, close_time,
                     valid_from, valid_until, label)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (zoo_id,
                  data.get("day_of_week"),
                  data.get("open_time") or None,
                  data.get("close_time") or None,
                  data.get("valid_from") or None,
                  data.get("valid_until") or None,
                  data.get("label") or None))
            oh_id = cur.fetchone()["id"]
        pg.commit()
        return jsonify({"id": oh_id, "message": "Created"}), 201
    except Exception:
        logging.exception(f"Exception in POST /api/v1/zoos/{zoo}/opening_hours")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@opening_hours_bp.route(
    "/api/v1/zoos/<zoo>/opening_hours/<int:oh_id>", methods=["PUT"])
@limiter.limit("30 per minute")
def update_zoo_opening_hour(zoo, oh_id):
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "write")
    if err: return err
    data, verr = _validate_oh_body(request.get_json(silent=True) or {},
                                   require_day=False)
    if verr:
        return jsonify({"error": verr}), 400
    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            zoo_id = _get_zoo_id(cur, zoo)
            if not zoo_id:
                return jsonify({"error": "Zoo not found"}), 404
            set_clauses = ", ".join(f"{k} = %s" for k in data)
            values = list(data.values()) + [oh_id, zoo_id]
            cur.execute(f"""
                UPDATE zoo.zoo_opening_hours SET {set_clauses}
                WHERE id = %s AND zoo_id = %s
            """, values)
            if cur.rowcount == 0:
                return jsonify({"error": "Not found"}), 404
        pg.commit()
        return jsonify({"message": "Updated"}), 200
    except Exception:
        logging.exception(f"Exception in PUT /api/v1/zoos/{zoo}/opening_hours/{oh_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@opening_hours_bp.route(
    "/api/v1/zoos/<zoo>/opening_hours/<int:oh_id>", methods=["DELETE"])
@limiter.limit("10 per minute")
def delete_zoo_opening_hour(zoo, oh_id):
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "write")
    if err: return err
    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            zoo_id = _get_zoo_id(cur, zoo)
            if not zoo_id:
                return jsonify({"error": "Zoo not found"}), 404
            cur.execute("""
                DELETE FROM zoo.zoo_opening_hours
                WHERE id = %s AND zoo_id = %s
            """, (oh_id, zoo_id))
            if cur.rowcount == 0:
                return jsonify({"error": "Not found"}), 404
        pg.commit()
        return jsonify({"message": "Deleted"}), 200
    except Exception:
        logging.exception(f"Exception in DELETE /api/v1/zoos/{zoo}/opening_hours/{oh_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


# ─────────────────────────────────────────────────────────────────────────────
# Location-Öffnungszeiten  (zoo.opening_hours)
# ─────────────────────────────────────────────────────────────────────────────

@opening_hours_bp.route(
    "/api/v1/zoos/<zoo>/locations/<int:loc_id>/opening_hours",
    methods=["GET"])
@limiter.limit("60 per minute")
def list_location_opening_hours(zoo, loc_id):
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "read")
    if err: return err
    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if not _get_location_or_404(cur, zoo, loc_id):
                return jsonify({"error": "Location not found"}), 404
            cur.execute("""
                SELECT id, day_of_week, open_time::TEXT, close_time::TEXT,
                       valid_from, valid_until, label
                FROM zoo.opening_hours
                WHERE location_id = %s ORDER BY day_of_week, open_time
            """, (loc_id,))
            return jsonify([_row(r) for r in cur.fetchall()]), 200
    except Exception:
        logging.exception(f"Exception in GET .../locations/{loc_id}/opening_hours")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@opening_hours_bp.route(
    "/api/v1/zoos/<zoo>/locations/<int:loc_id>/opening_hours/<int:oh_id>",
    methods=["GET"])
@limiter.limit("60 per minute")
def get_location_opening_hour(zoo, loc_id, oh_id):
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "read")
    if err: return err
    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if not _get_location_or_404(cur, zoo, loc_id):
                return jsonify({"error": "Location not found"}), 404
            cur.execute("""
                SELECT id, day_of_week, open_time::TEXT, close_time::TEXT,
                       valid_from, valid_until, label
                FROM zoo.opening_hours
                WHERE id = %s AND location_id = %s
            """, (oh_id, loc_id))
            row = cur.fetchone()
        if not row:
            return jsonify({"error": "Not found"}), 404
        return jsonify(_row(row)), 200
    except Exception:
        logging.exception(f"Exception in GET .../locations/{loc_id}/opening_hours/{oh_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@opening_hours_bp.route(
    "/api/v1/zoos/<zoo>/locations/<int:loc_id>/opening_hours",
    methods=["POST"])
@limiter.limit("30 per minute")
def create_location_opening_hour(zoo, loc_id):
    """
    Öffnungszeit für einen Location-POI anlegen.
    Body: { day_of_week (Pflicht), open_time, close_time, valid_from,
            valid_until, label }
    """
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "write")
    if err: return err
    data, verr = _validate_oh_body(request.get_json(silent=True) or {},
                                   require_day=True)
    if verr:
        return jsonify({"error": verr}), 400
    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if not _get_location_or_404(cur, zoo, loc_id):
                return jsonify({"error": "Location not found"}), 404
            cur.execute("""
                INSERT INTO zoo.opening_hours
                    (location_id, day_of_week, open_time, close_time,
                     valid_from, valid_until, label)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (loc_id,
                  data.get("day_of_week"),
                  data.get("open_time") or None,
                  data.get("close_time") or None,
                  data.get("valid_from") or None,
                  data.get("valid_until") or None,
                  data.get("label") or None))
            oh_id = cur.fetchone()["id"]
        pg.commit()
        return jsonify({"id": oh_id, "message": "Created"}), 201
    except Exception:
        logging.exception(f"Exception in POST .../locations/{loc_id}/opening_hours")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@opening_hours_bp.route(
    "/api/v1/zoos/<zoo>/locations/<int:loc_id>/opening_hours/<int:oh_id>",
    methods=["PUT"])
@limiter.limit("30 per minute")
def update_location_opening_hour(zoo, loc_id, oh_id):
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "write")
    if err: return err
    data, verr = _validate_oh_body(request.get_json(silent=True) or {},
                                   require_day=False)
    if verr:
        return jsonify({"error": verr}), 400
    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if not _get_location_or_404(cur, zoo, loc_id):
                return jsonify({"error": "Location not found"}), 404
            set_clauses = ", ".join(f"{k} = %s" for k in data)
            values = list(data.values()) + [oh_id, loc_id]
            cur.execute(f"""
                UPDATE zoo.opening_hours SET {set_clauses}
                WHERE id = %s AND location_id = %s
            """, values)
            if cur.rowcount == 0:
                return jsonify({"error": "Not found"}), 404
        pg.commit()
        return jsonify({"message": "Updated"}), 200
    except Exception:
        logging.exception(f"Exception in PUT .../locations/{loc_id}/opening_hours/{oh_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@opening_hours_bp.route(
    "/api/v1/zoos/<zoo>/locations/<int:loc_id>/opening_hours/<int:oh_id>",
    methods=["DELETE"])
@limiter.limit("10 per minute")
def delete_location_opening_hour(zoo, loc_id, oh_id):
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "write")
    if err: return err
    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if not _get_location_or_404(cur, zoo, loc_id):
                return jsonify({"error": "Location not found"}), 404
            cur.execute("""
                DELETE FROM zoo.opening_hours
                WHERE id = %s AND location_id = %s
            """, (oh_id, loc_id))
            if cur.rowcount == 0:
                return jsonify({"error": "Not found"}), 404
        pg.commit()
        return jsonify({"message": "Deleted"}), 200
    except Exception:
        logging.exception(f"Exception in DELETE .../locations/{loc_id}/opening_hours/{oh_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


# ─────────────────────────────────────────────────────────────────────────────
# House-Öffnungszeiten  (zoo.house_opening_hours)
# ─────────────────────────────────────────────────────────────────────────────

@opening_hours_bp.route(
    "/api/v1/zoos/<zoo>/houses/<int:house_id>/opening_hours",
    methods=["GET"])
@limiter.limit("60 per minute")
def list_house_opening_hours(zoo, house_id):
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "read")
    if err: return err
    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if not _get_house_or_404(cur, zoo, house_id):
                return jsonify({"error": "House not found"}), 404
            cur.execute("""
                SELECT id, day_of_week, open_time::TEXT, close_time::TEXT,
                       valid_from, valid_until, label
                FROM zoo.house_opening_hours
                WHERE house_id = %s ORDER BY day_of_week, open_time
            """, (house_id,))
            return jsonify([_row(r) for r in cur.fetchall()]), 200
    except Exception:
        logging.exception(f"Exception in GET .../houses/{house_id}/opening_hours")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@opening_hours_bp.route(
    "/api/v1/zoos/<zoo>/houses/<int:house_id>/opening_hours/<int:oh_id>",
    methods=["GET"])
@limiter.limit("60 per minute")
def get_house_opening_hour(zoo, house_id, oh_id):
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "read")
    if err: return err
    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if not _get_house_or_404(cur, zoo, house_id):
                return jsonify({"error": "House not found"}), 404
            cur.execute("""
                SELECT id, day_of_week, open_time::TEXT, close_time::TEXT,
                       valid_from, valid_until, label
                FROM zoo.house_opening_hours
                WHERE id = %s AND house_id = %s
            """, (oh_id, house_id))
            row = cur.fetchone()
        if not row:
            return jsonify({"error": "Not found"}), 404
        return jsonify(_row(row)), 200
    except Exception:
        logging.exception(f"Exception in GET .../houses/{house_id}/opening_hours/{oh_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@opening_hours_bp.route(
    "/api/v1/zoos/<zoo>/houses/<int:house_id>/opening_hours",
    methods=["POST"])
@limiter.limit("30 per minute")
def create_house_opening_hour(zoo, house_id):
    """
    Öffnungszeit für ein Tierhaus anlegen.
    Body: { day_of_week (Pflicht), open_time, close_time, valid_from,
            valid_until, label }
    """
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "write")
    if err: return err
    data, verr = _validate_oh_body(request.get_json(silent=True) or {},
                                   require_day=True)
    if verr:
        return jsonify({"error": verr}), 400
    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if not _get_house_or_404(cur, zoo, house_id):
                return jsonify({"error": "House not found"}), 404
            cur.execute("""
                INSERT INTO zoo.house_opening_hours
                    (house_id, day_of_week, open_time, close_time,
                     valid_from, valid_until, label)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (house_id,
                  data.get("day_of_week"),
                  data.get("open_time") or None,
                  data.get("close_time") or None,
                  data.get("valid_from") or None,
                  data.get("valid_until") or None,
                  data.get("label") or None))
            oh_id = cur.fetchone()["id"]
        pg.commit()
        return jsonify({"id": oh_id, "message": "Created"}), 201
    except Exception:
        logging.exception(f"Exception in POST .../houses/{house_id}/opening_hours")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@opening_hours_bp.route(
    "/api/v1/zoos/<zoo>/houses/<int:house_id>/opening_hours/<int:oh_id>",
    methods=["PUT"])
@limiter.limit("30 per minute")
def update_house_opening_hour(zoo, house_id, oh_id):
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "write")
    if err: return err
    data, verr = _validate_oh_body(request.get_json(silent=True) or {},
                                   require_day=False)
    if verr:
        return jsonify({"error": verr}), 400
    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if not _get_house_or_404(cur, zoo, house_id):
                return jsonify({"error": "House not found"}), 404
            set_clauses = ", ".join(f"{k} = %s" for k in data)
            values = list(data.values()) + [oh_id, house_id]
            cur.execute(f"""
                UPDATE zoo.house_opening_hours SET {set_clauses}
                WHERE id = %s AND house_id = %s
            """, values)
            if cur.rowcount == 0:
                return jsonify({"error": "Not found"}), 404
        pg.commit()
        return jsonify({"message": "Updated"}), 200
    except Exception:
        logging.exception(f"Exception in PUT .../houses/{house_id}/opening_hours/{oh_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@opening_hours_bp.route(
    "/api/v1/zoos/<zoo>/houses/<int:house_id>/opening_hours/<int:oh_id>",
    methods=["DELETE"])
@limiter.limit("10 per minute")
def delete_house_opening_hour(zoo, house_id, oh_id):
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "write")
    if err: return err
    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if not _get_house_or_404(cur, zoo, house_id):
                return jsonify({"error": "House not found"}), 404
            cur.execute("""
                DELETE FROM zoo.house_opening_hours
                WHERE id = %s AND house_id = %s
            """, (oh_id, house_id))
            if cur.rowcount == 0:
                return jsonify({"error": "Not found"}), 404
        pg.commit()
        return jsonify({"message": "Deleted"}), 200
    except Exception:
        logging.exception(f"Exception in DELETE .../houses/{house_id}/opening_hours/{oh_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()
