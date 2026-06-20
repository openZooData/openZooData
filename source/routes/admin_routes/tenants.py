import logging
import psycopg2
import psycopg2.extras
from flask import Blueprint, jsonify, request
from db import get_auth_connection
from extensions import limiter
from helpers.authz import require_super_admin, get_user_id_from_token
from helpers.audit import log_action
from helpers.coordinates import is_valid_slug
from routes.admin_routes.helpers import (_can_manage_tenant, _get_zoo_id_by_slug)

admin_tenants_bp = Blueprint("admin_tenants_bp", __name__)

@admin_tenants_bp.route("/api/v1/admin/tenants", methods=["POST"])
@limiter.limit("30 per minute")
def create_tenant():
    """Tenant anlegen. Nur super_admin. Body: { name, plan }"""
    actor_id, err = require_super_admin()
    if err: return err

    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    plan = data.get("plan", "free").strip()

    if not name:
        return jsonify({"error": "name required"}), 400
    if len(name) > 255:
        return jsonify({"error": "name must be at most 255 characters"}), 400
    if plan not in ("free", "basic", "pro"):
        return jsonify({"error": "plan must be free, basic or pro"}), 400

    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO auth.tenants (name, plan)
                VALUES (%s, %s)
                RETURNING id
            """, (name, plan))
            tenant_id = cur.fetchone()[0]
        conn.commit()

        log_action("tenant_created", actor_user_id=actor_id, tenant_id=tenant_id,
                   details={"name": name, "plan": plan})
        return jsonify({"id": tenant_id, "name": name, "plan": plan,
                        "message": "Tenant created"}), 201

    except Exception:
        if conn: conn.rollback()
        logging.exception("Exception in POST /admin/tenants")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn: conn.close()


@admin_tenants_bp.route("/api/v1/admin/tenants/<int:tenant_id>", methods=["DELETE"])
@limiter.limit("10 per minute")
def deactivate_tenant(tenant_id):
    """Tenant deaktivieren. Nur super_admin."""
    actor_id, err = require_super_admin()
    if err: return err

    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE auth.tenants SET is_active = FALSE
                WHERE id = %s AND is_active = TRUE
                RETURNING name
            """, (tenant_id,))
            if not cur.fetchone():
                return jsonify({"error": "Tenant not found or already inactive"}), 404
        conn.commit()

        log_action("tenant_deactivated", actor_user_id=actor_id, tenant_id=tenant_id)
        return jsonify({"message": f"Tenant {tenant_id} deactivated"}), 200

    except Exception:
        if conn: conn.rollback()
        logging.exception(f"Exception in DELETE /admin/tenants/{tenant_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn: conn.close()


# ── A5: Zoo-Tenant-Zuordnung ─────────────────────────────────────────────────


@admin_tenants_bp.route("/api/v1/admin/tenants", methods=["GET"])
@limiter.limit("60 per minute")
def list_tenants():
    """Alle Tenants. Nur super_admin."""
    actor_id, err = require_super_admin()
    if err: return err

    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT t.id, t.name, t.plan, t.is_active, t.created_at,
                       COUNT(tz.zoo_id) AS zoo_count
                FROM auth.tenants t
                LEFT JOIN auth.tenant_zoos tz ON tz.tenant_id = t.id
                GROUP BY t.id
                ORDER BY t.name
            """)
            return jsonify([dict(r) for r in cur.fetchall()]), 200

    except Exception:
        logging.exception("Exception in GET /admin/tenants")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn: conn.close()


@admin_tenants_bp.route("/api/v1/admin/tenants/<int:tenant_id>", methods=["GET"])
@limiter.limit("60 per minute")
def get_tenant_details(tenant_id):
    """Tenant-Details. super_admin oder tenant_admin dieses Tenants."""
    actor_id = get_user_id_from_token()
    if not actor_id:
        return jsonify({"error": "Unauthorized"}), 403
    if not _can_manage_tenant(actor_id, tenant_id):
        return jsonify({"error": "Unauthorized"}), 403

    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id, name, plan, is_active, created_at
                FROM auth.tenants WHERE id = %s
            """, (tenant_id,))
            tenant = cur.fetchone()
            if not tenant:
                return jsonify({"error": "Tenant not found"}), 404
            tenant = dict(tenant)

            cur.execute("""
                SELECT zoo_id FROM auth.tenant_zoos WHERE tenant_id = %s
            """, (tenant_id,))
            tenant["zoo_ids"] = [r["zoo_id"] for r in cur.fetchall()]

        return jsonify(tenant), 200

    except Exception:
        logging.exception(f"Exception in GET /admin/tenants/{tenant_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn: conn.close()


@admin_tenants_bp.route("/api/v1/admin/tenants/<int:tenant_id>", methods=["PUT"])
@limiter.limit("30 per minute")
def update_tenant(tenant_id):
    """Tenant bearbeiten. Nur super_admin."""
    actor_id, err = require_super_admin()
    if err: return err

    data = request.get_json(silent=True) or {}
    ALLOWED = {"name", "plan", "is_active"}
    unknown = set(data.keys()) - ALLOWED
    if unknown:
        return jsonify({"error": f"Unknown fields: {', '.join(sorted(unknown))}"}), 400
    if "plan" in data and data["plan"] not in ("free", "basic", "pro"):
        return jsonify({"error": "plan must be free, basic or pro"}), 400
    if "is_active" in data and not isinstance(data["is_active"], bool):
        return jsonify({"error": "is_active must be a boolean"}), 400
    if "name" in data and len(str(data["name"])) > 255:
        return jsonify({"error": "name must be at most 255 characters"}), 400
    if not data:
        return jsonify({"error": "No fields to update"}), 400

    set_clauses = ", ".join(f"{k} = %s" for k in data)
    values      = list(data.values()) + [tenant_id]

    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor() as cur:
            cur.execute(f"""
                UPDATE auth.tenants SET {set_clauses}
                WHERE id = %s RETURNING id
            """, values)
            if not cur.fetchone():
                return jsonify({"error": "Tenant not found"}), 404
        conn.commit()

        log_action("tenant_updated", actor_user_id=actor_id, tenant_id=tenant_id,
                   details={"fields": list(data.keys())})
        return jsonify({"message": "Tenant updated"}), 200

    except Exception:
        if conn: conn.rollback()
        logging.exception(f"Exception in PUT /admin/tenants/{tenant_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn: conn.close()


# ── B4 + B5: User-Liste + Details + Bearbeiten ───────────────────────────────


@admin_tenants_bp.route("/api/v1/admin/tenants/<int:tenant_id>/zoos", methods=["POST"])
@limiter.limit("30 per minute")
def assign_zoo_to_tenant(tenant_id):
    """
    Zoo einem Tenant zuordnen. Nur super_admin.
    Body: { zoo_slug }
    """
    actor_id, err = require_super_admin()
    if err: return err

    data     = request.get_json(silent=True) or {}
    zoo_slug = data.get("zoo_slug", "").strip()

    if not zoo_slug or not is_valid_slug(zoo_slug):
        return jsonify({"error": "valid zoo_slug required"}), 400

    try:
        zoo_id = _get_zoo_id_by_slug(zoo_slug)
    except ValueError:
        return jsonify({"error": "Zoo not found"}), 404

    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor() as cur:
            # Tenant aktiv?
            cur.execute("""
                SELECT 1 FROM auth.tenants WHERE id = %s AND is_active = TRUE
            """, (tenant_id,))
            if not cur.fetchone():
                return jsonify({"error": "Tenant not found or inactive"}), 404

            # Fix v2.1 + v3.5: Ein Zoo gehört genau einem Tenant.
            # Idempotent: gleiche Zuordnung → 200, andere Zuordnung → 409.
            cur.execute("""
                SELECT tenant_id FROM auth.tenant_zoos WHERE zoo_id = %s
            """, (zoo_id,))
            existing = cur.fetchone()
            if existing:
                if existing[0] == tenant_id:
                    return jsonify({
                        "message": "Zoo already assigned to this tenant"
                    }), 200
                else:
                    return jsonify({
                        "error": "Zoo is already assigned to another tenant"
                    }), 409

            cur.execute("""
                INSERT INTO auth.tenant_zoos (tenant_id, zoo_id)
                VALUES (%s, %s)
            """, (tenant_id, zoo_id))
        conn.commit()

        log_action("tenant_zoo_assigned", actor_user_id=actor_id,
                   tenant_id=tenant_id, zoo_id=zoo_id,
                   details={"zoo_slug": zoo_slug})
        return jsonify({"message": f"Zoo '{zoo_slug}' assigned to tenant {tenant_id}"}), 201

    except psycopg2.errors.UniqueViolation:
        if conn: conn.rollback()
        # Präzise Meldung: prüfen welchem Tenant der Zoo tatsächlich gehört
        try:
            zoo_id_check = _get_zoo_id_by_slug(zoo_slug)
            check_conn = get_auth_connection()
            with check_conn.cursor() as cur:
                cur.execute(
                    "SELECT tenant_id FROM auth.tenant_zoos WHERE zoo_id = %s",
                    (zoo_id_check,)
                )
                row = cur.fetchone()
            check_conn.close()
            if row and row[0] == tenant_id:
                return jsonify({"message": "Zoo already assigned to this tenant"}), 200
            else:
                return jsonify({"error": "Zoo is already assigned to another tenant"}), 409
        except Exception:
            return jsonify({"error": "Zoo already assigned to a tenant"}), 409
    except Exception:
        if conn: conn.rollback()
        logging.exception(f"Exception in POST /admin/tenants/{tenant_id}/zoos")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn: conn.close()


@limiter.limit("10 per minute")
def remove_zoo_from_tenant(tenant_id, zoo):
    """Zuordnung Zoo ↔ Tenant entfernen. Nur super_admin."""
    actor_id, err = require_super_admin()
    if err: return err

    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400

    try:
        zoo_id = _get_zoo_id_by_slug(zoo)
    except ValueError:
        return jsonify({"error": "Zoo not found"}), 404

    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM auth.tenant_zoos
                WHERE tenant_id = %s AND zoo_id = %s
            """, (tenant_id, zoo_id))
            if cur.rowcount == 0:
                return jsonify({"error": "Assignment not found"}), 404
        conn.commit()

        log_action("tenant_zoo_removed", actor_user_id=actor_id,
                   tenant_id=tenant_id, zoo_id=zoo_id,
                   details={"zoo_slug": zoo})
        return jsonify({"message": "Assignment removed"}), 200

    except Exception:
        if conn: conn.rollback()
        logging.exception(f"Exception in DELETE /admin/tenants/{tenant_id}/zoos/{zoo}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn: conn.close()


# ── A6 + A7: Zoo-Rolle vergeben / entziehen ──────────────────────────────────
