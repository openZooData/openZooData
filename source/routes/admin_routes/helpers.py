"""admin_routes/helpers.py — Shared helper functions for admin blueprints."""
import re
import logging
import psycopg2
import psycopg2.extras
from flask import jsonify
from db import get_pg_connection, get_auth_connection
from helpers.authz import require_super_admin, get_user_id_from_token
from helpers.coordinates import is_valid_slug



def _can_manage_zoo(actor_id: int, zoo_id: int) -> bool:
    """
    True wenn actor super_admin ist ODER tenant_admin des Tenants
    dem dieser Zoo zugeordnet ist.

    ARCHITEKTUR-ENTSCHEIDUNG (Option A, Juni 2026):
    Admin-Management prüft bewusst NICHT zoo.is_active / archived_at.
    Begründung: Ein neuer Zoo startet immer als inaktiv, wird durch den
    Admin befüllt (Daten, Gehege, Medien) und erst danach live geschaltet
    (is_active = TRUE). Auch reaktivieren, archivieren und Fehlerkorrektur
    erfordern Zugriff auf inaktive Zoos.

    Abgrenzung zu can_access_zoo() in authz.py:
      can_access_zoo()    → App-Seite: darf App-User Zoo-Daten sehen/schreiben?
                            Blockiert bei is_active=FALSE / archived_at IS NOT NULL.
      _can_manage_zoo()   → Admin-Seite: darf Admin das Zoo-Objekt verwalten?
                            Prüft bewusst keinen Zoo-Aktivstatus.

    Fix v2.2: Actor is_active wird explizit geprüft.
    get_user_id_from_token() liest nur JWT-Payload ohne DB-Prüfung —
    deaktivierte User müssen hier abgefangen werden.
    """
    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor() as cur:
            # Actor aktiv? (JWT enthält keine is_active-Info)
            cur.execute("""
                SELECT 1 FROM auth.users WHERE id = %s AND is_active = TRUE
            """, (actor_id,))
            if not cur.fetchone():
                return False

            # super_admin?
            cur.execute("""
                SELECT 1 FROM auth.user_global_roles
                WHERE user_id = %s AND role = 'super_admin'
            """, (actor_id,))
            if cur.fetchone():
                return True

            # tenant_admin des Tenants dem dieser Zoo gehört?
            cur.execute("""
                SELECT tz.tenant_id
                FROM auth.tenant_zoos tz
                JOIN auth.user_tenant_roles utr
                  ON utr.tenant_id = tz.tenant_id
                WHERE tz.zoo_id = %s
                  AND utr.user_id = %s
                  AND utr.role = 'tenant_admin'
                  AND utr.is_active = TRUE
            """, (zoo_id, actor_id))
            return cur.fetchone() is not None
    except Exception:
        logging.exception("_can_manage_zoo: DB-Fehler")
        return False
    finally:
        if conn:
            conn.close()


def _can_manage_tenant(actor_id: int, tenant_id: int) -> bool:
    """
    True wenn actor super_admin oder tenant_admin dieses Tenants.
    Fix v2.2: Actor is_active wird explizit geprüft.
    """
    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor() as cur:
            # Actor aktiv?
            cur.execute("""
                SELECT 1 FROM auth.users WHERE id = %s AND is_active = TRUE
            """, (actor_id,))
            if not cur.fetchone():
                return False

            cur.execute("""
                SELECT 1 FROM auth.user_global_roles
                WHERE user_id = %s AND role = 'super_admin'
            """, (actor_id,))
            if cur.fetchone():
                return True
            cur.execute("""
                SELECT 1 FROM auth.user_tenant_roles
                WHERE user_id = %s AND tenant_id = %s
                  AND role = 'tenant_admin' AND is_active = TRUE
            """, (actor_id, tenant_id))
            return cur.fetchone() is not None
    except Exception:
        logging.exception("_can_manage_tenant: DB-Fehler")
        return False
    finally:
        if conn:
            conn.close()


def _can_review_proposals(actor_id: int) -> bool:
    """
    True wenn actor super_admin oder moderator.
    Fix v2.2: Actor is_active wird explizit geprüft.
    """
    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 1 FROM auth.users WHERE id = %s AND is_active = TRUE
            """, (actor_id,))
            if not cur.fetchone():
                return False

            cur.execute("""
                SELECT 1 FROM auth.user_global_roles
                WHERE user_id = %s AND role IN ('super_admin', 'moderator')
            """, (actor_id,))
            return cur.fetchone() is not None
    except Exception:
        logging.exception("_can_review_proposals: DB-Fehler")
        return False
    finally:
        if conn:
            conn.close()


def _is_super_admin(actor_id: int) -> bool:
    """
    True wenn actor aktiver super_admin ist.
    Fix v3.9: zentrale Hilfsfunktion für direkte Rollenprüfungen.
    """
    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 1
                FROM auth.user_global_roles ugr
                JOIN auth.users u ON u.id = ugr.user_id
                WHERE ugr.user_id = %s
                  AND ugr.role = 'super_admin'
                  AND u.is_active = TRUE
            """, (actor_id,))
            return cur.fetchone() is not None
    except Exception:
        logging.exception("_is_super_admin: DB-Fehler")
        return False
    finally:
        if conn:
            conn.close()


def _would_remove_last_super_admin(user_id: int,
                                    deactivate: bool = False) -> bool:
    """
    Fix v3.6: Prüft ob eine Aktion den letzten aktiven super_admin entfernen würde.

    deactivate=True: User wird deaktiviert (is_active=FALSE)
    deactivate=False: super_admin-Rolle wird entzogen

    Gibt True zurück wenn die Aktion blockiert werden sollte.
    Verwendet in: revoke_global_role(), update_user(), deactivate_user()
    """
    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor() as cur:
            # Ist dieser User überhaupt super_admin?
            cur.execute("""
                SELECT 1 FROM auth.user_global_roles
                WHERE user_id = %s AND role = 'super_admin'
            """, (user_id,))
            if not cur.fetchone():
                return False  # Kein super_admin → kein Risiko

            # Wie viele aktive super_admins gibt es?
            cur.execute("""
                SELECT COUNT(*)
                FROM auth.user_global_roles ugr
                JOIN auth.users u ON u.id = ugr.user_id
                WHERE ugr.role = 'super_admin' AND u.is_active = TRUE
            """)
            count = cur.fetchone()[0]
            return count <= 1
    except Exception:
        logging.exception("_would_remove_last_super_admin: DB-Fehler")
        return True  # fail-safe: im Zweifel blockieren
    finally:
        if conn:
            conn.close()


def _require_can_manage_zoo(zoo_id: int):
    """Gibt (actor_id, None) oder (None, error_response) zurück."""
    actor_id = get_user_id_from_token()
    if not actor_id:
        return None, (jsonify({"error": "Unauthorized"}), 401)
    if not _can_manage_zoo(actor_id, zoo_id):
        return None, (jsonify({"error": "Unauthorized"}), 403)
    return actor_id, None


def _get_zoo_id_by_slug(slug: str) -> int:
    """
    Zoo-ID aus zoo.zoos. Wirft ValueError wenn nicht gefunden.
    Fix 5: Keine stillschweigende None-Rückgabe bei DB-Fehlern.
    """
    conn = None
    try:
        conn = get_pg_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM zoo.zoos WHERE slug = %s", (slug,))
            row = cur.fetchone()
            if not row:
                raise ValueError(f"Zoo '{slug}' not found")
            return row[0]
    finally:
        if conn:
            conn.close()


def _validate_zoo_fields(data: dict) -> str | None:
    """
    Validiert Felder für PUT /admin/zoos/<zoo>.
    Gibt Fehlermeldung zurück oder None wenn alles ok.
    Fix 12: Koordinaten, E-Mail, URL, Bool, Zeitformat.
    """
    email = data.get("email")
    if email is not None and email != "":
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", str(email)):
            return "Invalid email format"

    url = data.get("url")
    if url is not None and url != "":
        if not str(url).startswith(("http://", "https://")):
            return "url must start with http:// or https://"

    for coord_field in ("latitude", "longitude",
                        "top_left_latitude", "top_left_longitude",
                        "bottom_right_latitude", "bottom_right_longitude"):
        val = data.get(coord_field)
        if val is not None:
            try:
                f = float(val)
            except (ValueError, TypeError):
                return f"{coord_field} must be a number"
            if "latitude" in coord_field and not (-90 <= f <= 90):
                return f"{coord_field} must be between -90 and 90"
            if "longitude" in coord_field and not (-180 <= f <= 180):
                return f"{coord_field} must be between -180 and 180"

    time_pattern = re.compile(r"^\d{2}:\d{2}(:\d{2})?$")
    for tf in ("time_open", "time_close"):
        val = data.get(tf)
        if val is not None and not time_pattern.match(str(val)):
            return f"{tf} must be in HH:MM or HH:MM:SS format"

    is_active = data.get("is_active")
    if is_active is not None and not isinstance(is_active, bool):
        return "is_active must be a boolean"

    for str_field, max_len in [("name", 100), ("map_overlay", 100),
                                ("description", 2000), ("url", 255),
                                ("email", 255)]:
        val = data.get(str_field)
        if val is not None and len(str(val)) > max_len:
            return f"{str_field} must be at most {max_len} characters"

    return None