import logging
import psycopg2
import psycopg2.extras
from flask import Blueprint, jsonify, request
from db import get_pg_connection, get_auth_connection
from extensions import limiter
from helpers.authz import require_super_admin
from helpers.audit import log_action
from helpers.coordinates import is_valid_slug

admin_fixtures_bp = Blueprint("admin_fixtures_bp", __name__)

@admin_fixtures_bp.route("/api/v1/admin/test-fixtures/rbac", methods=["DELETE"])
@limiter.limit("10 per minute")
def cleanup_rbac_fixtures():
    """
    Löscht alle RBAC-Testdaten vollständig und hart aus der DB.
    Nur super_admin. Idempotent — kein Fehler wenn nichts zu löschen.

    Entfernt:
      - auth.tenant_zoos für alle RBAC-Tenants
      - auth.user_zoo_roles für alle @rbac.test User
      - auth.user_tenant_roles für alle @rbac.test User
      - auth.refresh_tokens für alle @rbac.test User
      - auth.users WHERE email LIKE '%@rbac.test'
      - auth.tenants WHERE name LIKE '%RBAC%'
      - zoo.zoos WHERE slug IN ('rbac_zoo_a', 'rbac_zoo_b') → is_active=FALSE

    Bewusste Entscheidung: Harter DELETE statt Soft-Delete damit
    wiederholte Testläufe nicht durch UniqueViolation blockiert werden.
    """
    actor_id, err = require_super_admin()
    if err: return err

    auth_conn = None
    zoo_conn  = None
    deleted   = {}

    try:
        # Schritt 1: Zoo-IDs aus Zoo-DB ermitteln (brauchen wir für tenant_zoos)
        zoo_conn = get_pg_connection()
        rbac_zoo_ids = []
        try:
            with zoo_conn.cursor() as cur:
                cur.execute("""
                    SELECT id FROM zoo.zoos
                    WHERE slug IN ('rbac_zoo_a', 'rbac_zoo_b')
                """)
                rbac_zoo_ids = [r[0] for r in cur.fetchall()]
                cur.execute("""
                    UPDATE zoo.zoos SET is_active = FALSE, archived_at = NOW()
                    WHERE slug IN ('rbac_zoo_a', 'rbac_zoo_b')
                """)
                deleted["zoos_deactivated"] = cur.rowcount
            zoo_conn.commit()
        finally:
            zoo_conn.close()
            zoo_conn = None

        # Schritt 2: Auth-DB aufräumen
        auth_conn = get_auth_connection()
        with auth_conn.cursor() as cur:

            # tenant_zoos nach Zoo-ID löschen (sicherste Methode)
            if rbac_zoo_ids:
                cur.execute("""
                    DELETE FROM auth.tenant_zoos
                    WHERE zoo_id = ANY(%s)
                """, (rbac_zoo_ids,))
                deleted["tenant_zoos_by_zoo"] = cur.rowcount
            else:
                deleted["tenant_zoos_by_zoo"] = 0

            # tenant_zoos nach Tenant-ID löschen (Fallback)
            cur.execute("""
                DELETE FROM auth.tenant_zoos tz
                USING auth.tenants t
                WHERE tz.tenant_id = t.id AND t.name LIKE '%RBAC%'
            """)
            deleted["tenant_zoos_by_tenant"] = cur.rowcount

            # user_zoo_roles aufräumen
            cur.execute("""
                DELETE FROM auth.user_zoo_roles
                WHERE user_id IN (
                    SELECT id FROM auth.users WHERE email LIKE '%@rbac.test'
                )
            """)
            deleted["user_zoo_roles"] = cur.rowcount

            # user_tenant_roles aufräumen
            cur.execute("""
                DELETE FROM auth.user_tenant_roles
                WHERE user_id IN (
                    SELECT id FROM auth.users WHERE email LIKE '%@rbac.test'
                )
            """)
            deleted["user_tenant_roles"] = cur.rowcount

            # refresh_tokens aufräumen
            cur.execute("""
                DELETE FROM auth.refresh_tokens
                WHERE user_id IN (
                    SELECT id FROM auth.users WHERE email LIKE '%@rbac.test'
                )
            """)
            deleted["refresh_tokens"] = cur.rowcount

            # invites aufräumen
            cur.execute("""
                DELETE FROM auth.invites
                WHERE user_id IN (
                    SELECT id FROM auth.users WHERE email LIKE '%@rbac.test'
                )
            """)
            deleted["invites"] = cur.rowcount

            # User hart löschen
            cur.execute("""
                DELETE FROM auth.users WHERE email LIKE '%@rbac.test'
            """)
            deleted["users"] = cur.rowcount

            # Tenants hart löschen
            cur.execute("""
                DELETE FROM auth.tenants WHERE name LIKE '%RBAC%'
            """)
            deleted["tenants"] = cur.rowcount

        auth_conn.commit()

        log_action("test_fixtures_rbac_cleanup", actor_user_id=actor_id,
                   details=deleted)

        return jsonify({
            "message": "RBAC test fixtures cleaned up",
            "deleted": deleted
        }), 200

    except Exception:
        if auth_conn: auth_conn.rollback()
        if zoo_conn and not zoo_conn.closed: zoo_conn.rollback()
        logging.exception("Exception in DELETE /admin/test-fixtures/rbac")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if auth_conn: auth_conn.close()
        if zoo_conn:  zoo_conn.close()
