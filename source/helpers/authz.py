import logging
import psycopg2.extras

# helpers/authz.py — Zentrale Autorisierung (Migration v7)
#
# can_access_zoo() ist die EINZIGE autoritative Quelle für Zoo-Berechtigungen.
# Direkte Rollenprüfungen in einzelnen Endpunkten sind nicht zulässig.
#
# Auth-DB und Zoo-DB bleiben getrennt. Deshalb gibt es keine Cross-DB-JOINs
# und keine Cross-DB-Foreign-Keys. Zoo-IDs werden in der Zoo-DB ermittelt und
# anschließend als Integer in der Auth-DB geprüft.

VALID_ACTIONS = {"read", "write", "publish", "admin"}


def _get_zoo_by_slug(zoo_slug: str) -> dict | None:
    from db import get_pg_connection
    conn = None
    try:
        conn = get_pg_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id, is_active, archived_at
                FROM zoo.zoos
                WHERE slug = %s
            """, (zoo_slug,))
            zoo = cur.fetchone()
            if not zoo:
                return None
            return dict(zoo)
    finally:
        if conn:
            conn.close()


def can_access_zoo(user_id: int, zoo_slug: str, action: str) -> bool:
    if action not in VALID_ACTIONS:
        logging.warning(f"can_access_zoo: ungültige action '{action}'")
        return False

    from db import get_auth_connection
    conn = None
    try:
        # 1. Zoo existiert und ist aktiv? (Zoo-DB)
        zoo = _get_zoo_by_slug(zoo_slug)
        if not zoo or not zoo["is_active"] or zoo["archived_at"] is not None:
            return False
        zoo_id = zoo["id"]

        # 2. Auth-/Rollenprüfung (Auth-DB)
        conn = get_auth_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT u.id, u.is_active, u.tenant_id,
                       t.is_active AS tenant_active
                FROM auth.users u
                LEFT JOIN auth.tenants t ON t.id = u.tenant_id
                WHERE u.id = %s
            """, (user_id,))
            user = cur.fetchone()
            if not user or not user["is_active"]:
                return False
            if user["tenant_id"] is not None and not user["tenant_active"]:
                return False

            # 3. super_admin?
            cur.execute("""
                SELECT 1 FROM auth.user_global_roles
                WHERE user_id = %s AND role = 'super_admin'
            """, (user_id,))
            if cur.fetchone():
                return True

            # 4. Zoo gehört zum Tenant?
            if user["tenant_id"] is not None:
                cur.execute("""
                    SELECT 1 FROM auth.tenant_zoos
                    WHERE tenant_id = %s AND zoo_id = %s
                """, (user["tenant_id"], zoo_id))
                if not cur.fetchone():
                    return False

            # 5. tenant_admin?
            # tenant_admin darf innerhalb seines Tenants alle Rechte besitzen:
            # read, write, publish, admin
            if user["tenant_id"] is not None:
                cur.execute("""
                    SELECT 1 FROM auth.user_tenant_roles
                    WHERE user_id = %s AND tenant_id = %s
                      AND role = 'tenant_admin' AND is_active = TRUE
                """, (user_id, user["tenant_id"]))
                if cur.fetchone():
                    return True

            # 6. Zoo-Rolle
            cur.execute("""
                SELECT role FROM auth.user_zoo_roles
                WHERE user_id = %s AND zoo_id = %s AND is_active = TRUE
            """, (user_id, zoo_id))
            row = cur.fetchone()
            if not row:
                return False

            role = row["role"]
            if role == "zoo_admin":
                return action in ("read", "write", "publish")
            if role == "editor":
                return action in ("read", "write")
            if role == "viewer":
                return action == "read"
            return False

    except Exception:
        logging.exception("can_access_zoo: DB-Fehler — fail-closed")
        return False
    finally:
        if conn:
            conn.close()


def get_user_id_from_token() -> int | None:
    from helpers.auth_utils import verify_access_token
    payload = verify_access_token()
    if not payload:
        return None
    try:
        return int(payload["sub"])
    except (KeyError, ValueError, TypeError):
        return None


def require_zoo_access(zoo_slug: str, action: str):
    """Gibt (user_id, None) oder (None, error_response) zurück."""
    from flask import jsonify
    user_id = get_user_id_from_token()
    if not user_id:
        return None, (jsonify({"error": "Unauthorized"}), 403)
    if not can_access_zoo(user_id, zoo_slug, action):
        return None, (jsonify({"error": "Unauthorized"}), 403)
    return user_id, None


def require_super_admin():
    from flask import jsonify
    from db import get_auth_connection
    user_id = get_user_id_from_token()
    if not user_id:
        return None, (jsonify({"error": "Unauthorized"}), 403)
    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor() as cur:
            # Prüft is_active UND super_admin-Rolle in einem Query.
            # Deaktivierte User werden auch mit altem gültigem JWT abgewiesen.
            cur.execute("""
                SELECT 1
                FROM auth.user_global_roles ugr
                JOIN auth.users u ON u.id = ugr.user_id
                WHERE ugr.user_id = %s
                  AND ugr.role = 'super_admin'
                  AND u.is_active = TRUE
            """, (user_id,))
            if cur.fetchone():
                return user_id, None
        return None, (jsonify({"error": "Unauthorized"}), 403)
    except Exception:
        logging.exception("require_super_admin: DB-Fehler")
        return None, (jsonify({"error": "Internal server error"}), 500)
    finally:
        if conn:
            conn.close()


def require_authenticated():
    """
    Prüft nur ob ein gültiges JWT vorhanden ist.
    HINWEIS: Keine DB-Prüfung — prüft nicht ob User/Tenant aktiv ist.
    Für Admin-Endpoints immer require_super_admin() oder _can_*() verwenden.
    require_authenticated() ist nur für Endpoints geeignet, bei denen
    nachgelagert can_access_zoo() oder eine andere Rechteprüfung erfolgt.
    """
    from flask import jsonify
    user_id = get_user_id_from_token()
    if not user_id:
        return None, (jsonify({"error": "Unauthorized"}), 403)
    return user_id, None


def require_any_write_access():
    """
    Für globale (zoo-übergreifende) Schreib-Endpoints wie das Anlegen einer
    neuen Species — es gibt keinen einzelnen zoo_slug, gegen den man prüfen
    könnte. Erlaubt, wer mindestens irgendwo write-Rechte hat:
    super_admin, tenant_admin (eines beliebigen Tenants), oder zoo_admin/
    editor auf mindestens einem Zoo. viewer-only User werden abgelehnt.
    """
    from flask import jsonify
    from db import get_auth_connection
    user_id = get_user_id_from_token()
    if not user_id:
        return None, (jsonify({"error": "Unauthorized"}), 403)

    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT u.is_active, t.is_active
                FROM auth.users u
                LEFT JOIN auth.tenants t ON t.id = u.tenant_id
                WHERE u.id = %s
            """, (user_id,))
            row = cur.fetchone()
            if not row or not row[0]:
                return None, (jsonify({"error": "Unauthorized"}), 403)
            if row[1] is False:
                return None, (jsonify({"error": "Unauthorized"}), 403)

            cur.execute("""
                SELECT 1 FROM auth.user_global_roles
                WHERE user_id = %s AND role = 'super_admin'
            """, (user_id,))
            if cur.fetchone():
                return user_id, None

            cur.execute("""
                SELECT 1 FROM auth.user_tenant_roles
                WHERE user_id = %s AND role = 'tenant_admin' AND is_active = TRUE
            """, (user_id,))
            if cur.fetchone():
                return user_id, None

            cur.execute("""
                SELECT 1 FROM auth.user_zoo_roles
                WHERE user_id = %s AND role IN ('zoo_admin', 'editor')
                  AND is_active = TRUE
            """, (user_id,))
            if cur.fetchone():
                return user_id, None

        return None, (jsonify({"error": "Unauthorized"}), 403)
    except Exception:
        logging.exception("require_any_write_access: DB-Fehler — fail-closed")
        return None, (jsonify({"error": "Internal server error"}), 500)
    finally:
        if conn:
            conn.close()
