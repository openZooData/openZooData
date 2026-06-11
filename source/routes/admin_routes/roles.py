import logging
import psycopg2
import psycopg2.extras
from flask import Blueprint, jsonify, request
from db import get_pg_connection, get_auth_connection
from extensions import limiter
from helpers.authz import require_super_admin
from helpers.coordinates import is_valid_slug
from routes.admin_routes.helpers import (_get_zoo_id_by_slug, _is_super_admin,
    _would_remove_last_super_admin)

admin_roles_bp = Blueprint("admin_roles_bp", __name__)

@admin_roles_bp.route("/api/v1/admin/users/<int:user_id>/roles/zoo", methods=["POST"])
@limiter.limit("30 per minute")
def grant_zoo_role(user_id):
    """
    Zoo-Rolle vergeben.
    super_admin oder tenant_admin des betreffenden Zoos.
    Body: { zoo_slug, role }

    Fix 1: Berechtigungsprüfung über Zoo-Tenant-Zuordnung.
    Ablauf:
      1. zoo_slug → zoo_id (Zoo-DB)
      2. zoo_id → tenant_id (auth.tenant_zoos)
      3. actor ist super_admin ODER tenant_admin dieses Tenants?
      4. Zieluser gehört zu demselben Tenant (oder actor ist super_admin)?
    Fix 10: Zieluser und Zoo müssen aktiv sein.
    """
    actor_id = get_user_id_from_token()
    if not actor_id:
        return jsonify({"error": "Unauthorized"}), 401

    data     = request.get_json(silent=True) or {}
    zoo_slug = data.get("zoo_slug", "").strip()
    role     = data.get("role", "").strip()

    if not zoo_slug or not is_valid_slug(zoo_slug):
        return jsonify({"error": "valid zoo_slug required"}), 400
    if role not in VALID_ZOO_ROLES:
        return jsonify({"error": f"role must be one of: {', '.join(sorted(VALID_ZOO_ROLES))}"}), 400

    try:
        zoo_id = _get_zoo_id_by_slug(zoo_slug)
    except ValueError:
        return jsonify({"error": "Zoo not found"}), 404

    # Fix 1: Berechtigung über Zoo-Tenant-Zuordnung prüfen
    if not _can_manage_zoo(actor_id, zoo_id):
        return jsonify({"error": "Unauthorized"}), 403

    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor() as cur:
            # Fix 10: Zieluser aktiv?
            cur.execute("""
                SELECT id, tenant_id FROM auth.users
                WHERE id = %s AND is_active = TRUE
            """, (user_id,))
            target_user = cur.fetchone()
            if not target_user:
                return jsonify({"error": "User not found or inactive"}), 404

            # Fix 1: Zieluser muss zum selben Tenant des Zoos gehören
            # (außer bei super_admin, der darf immer)
            # Fix v3.9: _is_super_admin() statt direkter Rollenprüfung
            actor_is_super = _is_super_admin(actor_id)

            if not actor_is_super:
                # Tenant des Zoos ermitteln
                cur.execute("""
                    SELECT tenant_id FROM auth.tenant_zoos WHERE zoo_id = %s
                """, (zoo_id,))
                zoo_tenant_row = cur.fetchone()
                if zoo_tenant_row:
                    zoo_tenant_id = zoo_tenant_row[0]
                    target_tenant_id = target_user[1]
                    if target_tenant_id != zoo_tenant_id:
                        return jsonify({
                            "error": "User does not belong to the tenant of this zoo"
                        }), 403

            cur.execute("""
                INSERT INTO auth.user_zoo_roles (user_id, zoo_id, role, is_active)
                VALUES (%s, %s, %s, TRUE)
                ON CONFLICT (user_id, zoo_id, role)
                DO UPDATE SET is_active = TRUE
            """, (user_id, zoo_id, role))
        conn.commit()

        log_action("zoo_role_granted", actor_user_id=actor_id,
                   zoo_id=zoo_id, target_type="user", target_id=user_id,
                   details={"zoo_slug": zoo_slug, "role": role})
        return jsonify({"message": f"Role '{role}' granted for zoo '{zoo_slug}'"}), 201

    except Exception:
        if conn: conn.rollback()
        logging.exception(f"Exception in POST /admin/users/{user_id}/roles/zoo")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn: conn.close()


@limiter.limit("10 per minute")
def revoke_zoo_role(user_id, zoo, role):
    """
    Zoo-Rolle entziehen.
    Fix 3: super_admin oder tenant_admin des betreffenden Zoos (nicht nur super_admin).
    """
    actor_id = get_user_id_from_token()
    if not actor_id:
        return jsonify({"error": "Unauthorized"}), 401

    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    if role not in VALID_ZOO_ROLES:
        return jsonify({"error": "Invalid role"}), 400

    try:
        zoo_id = _get_zoo_id_by_slug(zoo)
    except ValueError:
        return jsonify({"error": "Zoo not found"}), 404

    if not _can_manage_zoo(actor_id, zoo_id):
        return jsonify({"error": "Unauthorized"}), 403

    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE auth.user_zoo_roles SET is_active = FALSE
                WHERE user_id = %s AND zoo_id = %s AND role = %s
                  AND is_active = TRUE
            """, (user_id, zoo_id, role))
            if cur.rowcount == 0:
                return jsonify({"error": "Role assignment not found or already inactive"}), 404
        conn.commit()

        log_action("zoo_role_revoked", actor_user_id=actor_id,
                   zoo_id=zoo_id, target_type="user", target_id=user_id,
                   details={"zoo_slug": zoo, "role": role})
        return jsonify({"message": f"Role '{role}' revoked for zoo '{zoo}'"}), 200

    except Exception:
        if conn: conn.rollback()
        logging.exception(f"Exception in DELETE /admin/users/{user_id}/roles/zoo")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn: conn.close()


# ── A8 + A9: Tenant-Rolle vergeben / entziehen ───────────────────────────────


@limiter.limit("30 per minute")
def grant_tenant_role(user_id):
    """Tenant-Rolle vergeben. Nur super_admin. Body: { tenant_id, role }"""
    actor_id, err = require_super_admin()
    if err: return err

    data      = request.get_json(silent=True) or {}
    tenant_id = data.get("tenant_id")
    role      = data.get("role", "").strip()

    if not tenant_id:
        return jsonify({"error": "tenant_id required"}), 400
    try:
        tenant_id = int(tenant_id)
    except (TypeError, ValueError):
        return jsonify({"error": "tenant_id must be an integer"}), 400
    if role not in ("tenant_admin",):
        return jsonify({"error": "role must be tenant_admin"}), 400

    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor() as cur:
            # Fix 10: aktive Entitäten prüfen
            cur.execute("SELECT 1 FROM auth.users WHERE id = %s AND is_active = TRUE",
                        (user_id,))
            if not cur.fetchone():
                return jsonify({"error": "User not found or inactive"}), 404
            cur.execute("SELECT 1 FROM auth.tenants WHERE id = %s AND is_active = TRUE",
                        (tenant_id,))
            if not cur.fetchone():
                return jsonify({"error": "Tenant not found or inactive"}), 404

            cur.execute("""
                INSERT INTO auth.user_tenant_roles (user_id, tenant_id, role, is_active)
                VALUES (%s, %s, %s, TRUE)
                ON CONFLICT (user_id, tenant_id, role)
                DO UPDATE SET is_active = TRUE
            """, (user_id, tenant_id, role))
        conn.commit()

        log_action("tenant_role_granted", actor_user_id=actor_id,
                   tenant_id=tenant_id, target_type="user", target_id=user_id,
                   details={"role": role})
        return jsonify({"message": f"Role '{role}' granted for tenant {tenant_id}"}), 201

    except Exception:
        if conn: conn.rollback()
        logging.exception(f"Exception in POST /admin/users/{user_id}/roles/tenant")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn: conn.close()


@limiter.limit("10 per minute")
def revoke_tenant_role(user_id, tenant_id):
    """Tenant-Rolle entziehen. Nur super_admin."""
    actor_id, err = require_super_admin()
    if err: return err

    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE auth.user_tenant_roles SET is_active = FALSE
                WHERE user_id = %s AND tenant_id = %s AND is_active = TRUE
            """, (user_id, tenant_id))
            if cur.rowcount == 0:
                return jsonify({"error": "Role assignment not found or already inactive"}), 404
        conn.commit()

        log_action("tenant_role_revoked", actor_user_id=actor_id,
                   tenant_id=tenant_id, target_type="user", target_id=user_id)
        return jsonify({"message": "Tenant role revoked"}), 200

    except Exception:
        if conn: conn.rollback()
        logging.exception(f"Exception in DELETE /admin/users/{user_id}/roles/tenant/{tenant_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn: conn.close()


# ── A10: User deaktivieren ───────────────────────────────────────────────────


@limiter.limit("10 per minute")
def grant_global_role(user_id):
    """Globale Rolle vergeben. Nur super_admin."""
    actor_id, err = require_super_admin()
    if err: return err

    data = request.get_json(silent=True) or {}
    role = data.get("role", "").strip()
    if role not in VALID_GLOBAL_ROLES:
        return jsonify({"error": f"role must be one of: {', '.join(sorted(VALID_GLOBAL_ROLES))}"}), 400

    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor() as cur:
            # Fix 10: aktiven User prüfen
            cur.execute("SELECT 1 FROM auth.users WHERE id = %s AND is_active = TRUE",
                        (user_id,))
            if not cur.fetchone():
                return jsonify({"error": "User not found or inactive"}), 404

            cur.execute("""
                INSERT INTO auth.user_global_roles (user_id, role)
                VALUES (%s, %s) ON CONFLICT DO NOTHING
            """, (user_id, role))
        conn.commit()

        log_action("global_role_granted", actor_user_id=actor_id,
                   target_type="user", target_id=user_id,
                   details={"role": role})
        return jsonify({"message": f"Global role '{role}' granted"}), 201

    except Exception:
        if conn: conn.rollback()
        logging.exception(f"Exception in POST /admin/users/{user_id}/roles/global")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn: conn.close()


@limiter.limit("10 per minute")
def revoke_global_role(user_id, role):
    """
    Globale Rolle entziehen. Nur super_admin.
    Fix 11: Verhindert das Entfernen des letzten aktiven super_admin.
    """
    actor_id, err = require_super_admin()
    if err: return err

    if role not in VALID_GLOBAL_ROLES:
        return jsonify({"error": "Invalid role"}), 400
    if role == "super_admin" and actor_id == user_id:
        return jsonify({"error": "Cannot revoke your own super_admin role"}), 400

    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor() as cur:
            # Fix 11 + v3.6: zentraler Schutz über _would_remove_last_super_admin()
            if role == "super_admin" and _would_remove_last_super_admin(user_id):
                return jsonify({
                    "error": "Cannot remove the last active super_admin"
                }), 400

            cur.execute("""
                DELETE FROM auth.user_global_roles
                WHERE user_id = %s AND role = %s
            """, (user_id, role))
            if cur.rowcount == 0:
                return jsonify({"error": "Role not found"}), 404
        conn.commit()

        log_action("global_role_revoked", actor_user_id=actor_id,
                   target_type="user", target_id=user_id,
                   details={"role": role})
        return jsonify({"message": f"Global role '{role}' revoked"}), 200

    except Exception:
        if conn: conn.rollback()
        logging.exception(f"Exception in DELETE /admin/users/{user_id}/roles/global/{role}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn: conn.close()


# ── B8: System-Settings ───────────────────────────────────────────────────────
