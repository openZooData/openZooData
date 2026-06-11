import logging
import psycopg2
import psycopg2.extras
from flask import Blueprint, jsonify, request
from db import get_pg_connection, get_auth_connection
from extensions import limiter
from helpers.authz import require_super_admin
from helpers.coordinates import is_valid_slug
from routes.admin_routes.helpers import (_can_manage_zoo, _require_can_manage_zoo,
    _get_zoo_id_by_slug, _validate_zoo_fields, _is_super_admin)

admin_zoos_bp = Blueprint("admin_zoos_bp", __name__)

@admin_zoos_bp.route("/api/v1/admin/zoos", methods=["POST"])
@limiter.limit("30 per minute")
def create_zoo():
    """
    Zoo in zoo.zoos anlegen. Nur super_admin.
    Body: { slug, name, is_active (default true) }

    Fix 2: ON CONFLICT (slug) reaktiviert deaktivierten Zoo
    statt 409 zurückzugeben — ermöglicht wiederholbare Test-Fixtures.
    """
    actor_id, err = require_super_admin()
    if err: return err

    data      = request.get_json(silent=True) or {}
    slug      = data.get("slug", "").strip().lower()
    name      = data.get("name", "").strip()
    is_active = data.get("is_active", True)

    if not slug or not name:
        return jsonify({"error": "slug and name required"}), 400
    if not is_valid_slug(slug):
        return jsonify({"error": "slug must only contain a-z, 0-9, _ and -"}), 400
    if not isinstance(is_active, bool):
        return jsonify({"error": "is_active must be a boolean"}), 400

    conn = None
    try:
        conn = get_pg_connection()
        with conn.cursor() as cur:
            # Fix v2.3: Aktive Zoos dürfen nicht überschrieben werden.
            # Reaktivierung ist erlaubt (für RBAC-Fixtures), aber nur wenn
            # der bestehende Zoo inaktiv ist.
            cur.execute("""
                INSERT INTO zoo.zoos (slug, name, is_active)
                VALUES (%s, %s, %s)
                ON CONFLICT (slug) DO UPDATE SET
                    name        = EXCLUDED.name,
                    is_active   = EXCLUDED.is_active,
                    archived_at = NULL
                WHERE zoo.zoos.is_active = FALSE
                RETURNING id, (xmax = 0) AS inserted
            """, (slug, name, is_active))
            row = cur.fetchone()
            if row is None:
                # Kein RETURNING-Ergebnis: Zoo existiert und ist aktiv → 409
                return jsonify({
                    "error": "Zoo slug already exists and is active. "
                             "Deactivate it first if you want to recreate it."
                }), 409
            zoo_id   = row[0]
            inserted = row[1]
        conn.commit()

        action = "zoo_created" if inserted else "zoo_reactivated"
        log_action(action, actor_user_id=actor_id,
                   target_type="zoo", target_id=zoo_id,
                   details={"slug": slug, "name": name})
        status = 201 if inserted else 200
        return jsonify({"id": zoo_id, "slug": slug,
                        "message": "Zoo created" if inserted else "Zoo reactivated"}), status

    except Exception:
        if conn: conn.rollback()
        logging.exception("Exception in POST /admin/zoos")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn: conn.close()


@admin_zoos_bp.route("/api/v1/admin/zoos/<zoo>", methods=["DELETE"])
@limiter.limit("10 per minute")
def deactivate_zoo(zoo):
    """Zoo deaktivieren (is_active = FALSE). Nur super_admin."""
    actor_id, err = require_super_admin()
    if err: return err

    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400

    conn = None
    try:
        conn = get_pg_connection()
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE zoo.zoos SET is_active = FALSE
                WHERE slug = %s AND is_active = TRUE
                RETURNING id
            """, (zoo,))
            row = cur.fetchone()
            if not row:
                return jsonify({"error": "Zoo not found or already inactive"}), 404
            zoo_id = row[0]
        conn.commit()

        log_action("zoo_deactivated", actor_user_id=actor_id,
                   target_type="zoo", target_id=zoo_id,
                   details={"slug": zoo})
        return jsonify({"message": f"Zoo '{zoo}' deactivated"}), 200

    except Exception:
        if conn: conn.rollback()
        logging.exception(f"Exception in DELETE /admin/zoos/{zoo}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn: conn.close()


# ── A3 + A4: Tenant anlegen / deaktivieren ──────────────────────────────────


@admin_zoos_bp.route("/api/v1/admin/zoos", methods=["GET"])
@limiter.limit("60 per minute")
def list_zoos():
    """Alle Zoos. Nur super_admin."""
    actor_id, err = require_super_admin()
    if err: return err

    conn = None
    try:
        conn = get_pg_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id, slug, name, is_active, data_version,
                       latitude, longitude, archived_at
                FROM zoo.zoos
                ORDER BY name
            """)
            return jsonify([dict(r) for r in cur.fetchall()]), 200

    except Exception:
        logging.exception("Exception in GET /admin/zoos")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn: conn.close()


@admin_zoos_bp.route("/api/v1/admin/zoos/<zoo>", methods=["GET"])
@limiter.limit("60 per minute")
def get_zoo_details(zoo):
    """
    Zoo-Details.
    Fix 3: super_admin oder tenant_admin des Zoos.
    """
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400

    try:
        zoo_id = _get_zoo_id_by_slug(zoo)
    except ValueError:
        return jsonify({"error": "Zoo not found"}), 404

    actor_id, err = _require_can_manage_zoo(zoo_id)
    if err: return err

    conn = None
    try:
        conn = get_pg_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id, slug, name, url, description, email,
                       latitude, longitude,
                       top_left_latitude, top_left_longitude,
                       bottom_right_latitude, bottom_right_longitude,
                       map_overlay, time_open, time_close,
                       data_version, is_active, archived_at
                FROM zoo.zoos WHERE slug = %s
            """, (zoo,))
            row = cur.fetchone()
            if not row:
                return jsonify({"error": "Zoo not found"}), 404
        return jsonify(dict(row)), 200

    except Exception:
        logging.exception(f"Exception in GET /admin/zoos/{zoo}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn: conn.close()


@admin_zoos_bp.route("/api/v1/admin/zoos/<zoo>", methods=["PUT"])
@limiter.limit("30 per minute")
def update_zoo(zoo):
    """
    Zoo bearbeiten.
    Fix 3: super_admin oder tenant_admin des Zoos.
    Fix 12: Feldvalidierung.
    """
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400

    try:
        zoo_id = _get_zoo_id_by_slug(zoo)
    except ValueError:
        return jsonify({"error": "Zoo not found"}), 404

    actor_id, err = _require_can_manage_zoo(zoo_id)
    if err: return err

    data = request.get_json(silent=True) or {}
    for forbidden in ("id", "slug", "data_version", "archived_at"):
        data.pop(forbidden, None)

    if not data:
        return jsonify({"error": "No fields to update"}), 400

    # Fix v3.3: is_active nur für super_admin — tenant_admin darf Betriebsstatus nicht ändern.
    actor_id_sa, _ = require_super_admin()
    is_super = actor_id_sa is not None

    ALLOWED_TENANT = {"name", "url", "description", "email",
                      "latitude", "longitude",
                      "top_left_latitude", "top_left_longitude",
                      "bottom_right_latitude", "bottom_right_longitude",
                      "map_overlay", "time_open", "time_close"}
    ALLOWED_SUPER  = ALLOWED_TENANT | {"is_active"}
    ALLOWED        = ALLOWED_SUPER if is_super else ALLOWED_TENANT

    if not is_super and "is_active" in data:
        return jsonify({"error": "Only super_admin may change is_active"}), 403
    unknown = set(data.keys()) - ALLOWED
    if unknown:
        return jsonify({"error": f"Unknown fields: {', '.join(sorted(unknown))}"}), 400

    # Fix 12: Feldvalidierung
    validation_error = _validate_zoo_fields(data)
    if validation_error:
        return jsonify({"error": validation_error}), 400

    set_clauses = ", ".join(f"{k} = %s" for k in data)
    values      = list(data.values()) + [zoo]

    conn = None
    try:
        conn = get_pg_connection()
        with conn.cursor() as cur:
            cur.execute(f"""
                UPDATE zoo.zoos SET {set_clauses}
                WHERE slug = %s
                RETURNING id
            """, values)
            row = cur.fetchone()
            if not row:
                return jsonify({"error": "Zoo not found"}), 404
        conn.commit()

        log_action("zoo_updated", actor_user_id=actor_id,
                   target_type="zoo", target_id=row[0],
                   details={"slug": zoo, "fields": list(data.keys())})
        return jsonify({"message": "Zoo updated"}), 200

    except Exception:
        if conn: conn.rollback()
        logging.exception(f"Exception in PUT /admin/zoos/{zoo}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn: conn.close()


# ── B3: Tenant-Liste + Details + Bearbeiten ──────────────────────────────────
