"""
routes/admin.py — Admin-Endpoints für openZooData (v6)

Änderungen gegenüber v1 (adminEndpointReview.md):
  Fix 1  (kritisch): grant_zoo_role() — Tenant-Isolation korrigiert.
                     Prüfung läuft jetzt über Zoo-Tenant-Zuordnung,
                     nicht über Tenant des Zielbenutzers.
  Fix 2  (kritisch): Fixture-Cleanup — create_zoo() reaktiviert bei
                     gleichem Slug (ON CONFLICT ... DO UPDATE).
  Fix 3  (mittel):   Tenant-Admin-Rechte vollständig implementiert
                     für get_zoo_details(), update_zoo(), revoke_zoo_role().
  Fix v2.1 (Blocker): assign_zoo_to_tenant() verhindert Mehrfach-Zuordnung
                     eines Zoos zu verschiedenen Tenants.
  Fix v2.2 (Blocker): _can_*() Helfer prüfen jetzt actor is_active explizit
                     (get_user_id_from_token() macht keine DB-Prüfung).
  Fix v2.3 (hoch):   create_zoo() überschreibt keine aktiven Zoos mehr —
                     ON CONFLICT nur bei is_active=FALSE möglich.
  Fix v2.4 (hoch):   confirm_password_reset() setzt nur bei aktiven Usern.
  Fix v2.5 (hoch):   Audit-Log-Filter validieren Integer und ISO-Datumsformat.
  Fix v3.1 (Blocker): require_super_admin() prüft jetzt is_active (authz.py).
  Fix v3.2 (Blocker): DB-Constraint für Zoo-Tenant-Eindeutigkeit (SQL-Migration).
  Fix v3.3 (hoch):    is_active aus update_zoo() für tenant_admin gesperrt.
  Fix v3.4 (hoch):    list_users() tenant_id-Filter validiert.
  Fix v3.5 (hoch):    assign_zoo_to_tenant() idempotent.
  Fix v3.6 (mittel):  _would_remove_last_super_admin() zentralisiert.
  Fix v3.7 (mittel):  update_user() schützt letzten super_admin.
  Fix v3.8 (mittel):  deactivate_user() schützt letzten super_admin.
  Fix v3.9 (mittel):  grant_zoo_role() direkte Rollenprüfung durch _is_super_admin().
  Fix v3.10 (niedrig): PASSWORD_RESET_PATH konfigurierbar.
  Fix 4  (hoch):     Zentrale Permission-Funktionen statt direkter
                     Rollenprüfung in Endpoints.
  Fix 5  (hoch):     _get_zoo_id_by_slug() loggt DB-Fehler und gibt
                     Exception weiter statt None zurückzugeben.
  Fix 6  (hoch):     Password-Reset invalidiert alte offene Tokens
                     vor dem Anlegen eines neuen.
  Fix 7  (hoch):     Password-Reset Token-Verbrauch atomar via
                     UPDATE ... FOR UPDATE.
  Fix 8  (hoch):     Audit-Log: Settings-Wert wird nicht mehr geloggt.
  Fix 9  (mittel/h): get_audit_log() validiert limit-Parameter.
  Fix 10 (mittel):   Inaktive User/Tenants/Zoos werden bei Aktionen
                     konsequent geprüft.
  Fix 11 (mittel):   revoke_global_role() schützt letzten super_admin.
  Fix 12 (mittel):   PUT-Feldvalidierung: Koordinaten, E-Mail, URL,
                     Bool, Zeitformat.
  Fix 13 (mittel):   auth_py_addition imports explizit.
  Fix 14 (niedrig):  Password-Reset-Routen bleiben im Admin-Blueprint,
                     aber sind klar als auth-zugehörig dokumentiert.
  Entscheidung:      Tenant-Admin-Rechte direkt implementiert (nicht
                     aufgeschoben) — protokolliert in Konzept v3.

Architektur:
  Zentrale Permission-Helfer _can_*() — Endpoints prüfen Berechtigungen
  nie direkt auf Rollennamen, sondern über diese Helfer.
"""

import hashlib
import logging
import os
import re
import secrets as secrets_module
import smtplib
from datetime import datetime, timezone
from email.mime.text import MIMEText

import bcrypt
import psycopg2.errors
import psycopg2.extras
from flask import Blueprint, jsonify, request

from db import get_auth_connection, get_pg_connection
from extensions import limiter
from helpers.audit import log_action
from helpers.authz import get_user_id_from_token, require_super_admin
from helpers.coordinates import is_valid_slug

admin_bp = Blueprint("admin", __name__)

VALID_ZOO_ROLES    = {"viewer", "editor", "zoo_admin"}
VALID_GLOBAL_ROLES = {"super_admin", "moderator"}


###############################################################################
# ── Zentrale Permission-Funktionen ──────────────────────────────────────────
# Alle Endpoints prüfen Berechtigungen ausschließlich über diese Helfer.
# Endpoints enthalten keine Rollenlogik direkt —
# Rollenlogik ist in zentralen Permission-Helfern gekapselt.
#
# Zwei Autorisierungsebenen (bewusste Trennung, Option A, Juni 2026):
#
#   App-Ebene:   can_access_zoo() in authz.py
#                → für normale Zoo-Daten-Endpoints (Enclosures, Species, ...)
#                → blockiert bei inaktivem/archiviertem Zoo
#
#   Admin-Ebene: _can_manage_zoo() / _can_manage_tenant() hier
#                → für Admin-Verwaltungs-Endpoints
#                → erlaubt auch inaktive/archivierte Zoos (Lifecycle-Management)
###############################################################################

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


###############################################################################
# ── Zoo-ID Hilfsfunktion ────────────────────────────────────────────────────
###############################################################################

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


###############################################################################
# ── Feldvalidierung für PUT-Endpoints ───────────────────────────────────────
###############################################################################

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


###############################################################################
# ══ GRUPPE A — RBAC-Fixtures ═════════════════════════════════════════════════
###############################################################################

# ── A1 + A2: Zoo anlegen / deaktivieren ─────────────────────────────────────

@admin_bp.route("/api/v1/admin/zoos", methods=["POST"])
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


@admin_bp.route("/api/v1/admin/zoos/<zoo>", methods=["DELETE"])
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

@admin_bp.route("/api/v1/admin/tenants", methods=["POST"])
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


@admin_bp.route("/api/v1/admin/tenants/<int:tenant_id>", methods=["DELETE"])
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

@admin_bp.route("/api/v1/admin/tenants/<int:tenant_id>/zoos", methods=["POST"])
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


@admin_bp.route("/api/v1/admin/tenants/<int:tenant_id>/zoos/<zoo>",
                methods=["DELETE"])
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

@admin_bp.route("/api/v1/admin/users/<int:user_id>/roles/zoo", methods=["POST"])
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


@admin_bp.route("/api/v1/admin/users/<int:user_id>/roles/zoo/<zoo>/<role>",
                methods=["DELETE"])
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

@admin_bp.route("/api/v1/admin/users/<int:user_id>/roles/tenant",
                methods=["POST"])
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


@admin_bp.route("/api/v1/admin/users/<int:user_id>/roles/tenant/<int:tenant_id>",
                methods=["DELETE"])
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

@admin_bp.route("/api/v1/admin/users/<int:user_id>", methods=["DELETE"])
@limiter.limit("10 per minute")
def deactivate_user(user_id):
    """User deaktivieren. Nur super_admin. Kann sich nicht selbst deaktivieren."""
    actor_id, err = require_super_admin()
    if err: return err

    if actor_id == user_id:
        return jsonify({"error": "Cannot deactivate yourself"}), 400

    # Fix v3.8: Letzten aktiven super_admin schützen
    if _would_remove_last_super_admin(user_id, deactivate=True):
        return jsonify({
            "error": "Cannot deactivate the last active super_admin"
        }), 400

    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE auth.users SET is_active = FALSE
                WHERE id = %s AND is_active = TRUE
                RETURNING email
            """, (user_id,))
            if not cur.fetchone():
                return jsonify({"error": "User not found or already inactive"}), 404
        conn.commit()

        log_action("user_deactivated", actor_user_id=actor_id,
                   target_type="user", target_id=user_id)
        return jsonify({"message": f"User {user_id} deactivated"}), 200

    except Exception:
        if conn: conn.rollback()
        logging.exception(f"Exception in DELETE /admin/users/{user_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn: conn.close()


###############################################################################
# ══ GRUPPE B — Admin-UI ══════════════════════════════════════════════════════
###############################################################################

# ── B1 + B2: Zoo-Liste + Details + Bearbeiten ────────────────────────────────

@admin_bp.route("/api/v1/admin/zoos", methods=["GET"])
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


@admin_bp.route("/api/v1/admin/zoos/<zoo>", methods=["GET"])
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


@admin_bp.route("/api/v1/admin/zoos/<zoo>", methods=["PUT"])
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

@admin_bp.route("/api/v1/admin/tenants", methods=["GET"])
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


@admin_bp.route("/api/v1/admin/tenants/<int:tenant_id>", methods=["GET"])
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


@admin_bp.route("/api/v1/admin/tenants/<int:tenant_id>", methods=["PUT"])
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

@admin_bp.route("/api/v1/admin/users", methods=["GET"])
@limiter.limit("60 per minute")
def list_users():
    """User-Liste. Nur super_admin. ?tenant_id= für Filter."""
    actor_id, err = require_super_admin()
    if err: return err

    # Fix v3.4: tenant_id als Integer validieren
    tenant_filter_raw = request.args.get("tenant_id")
    tenant_filter = None
    if tenant_filter_raw is not None:
        try:
            tenant_filter = int(tenant_filter_raw)
        except ValueError:
            return jsonify({"error": "tenant_id must be an integer"}), 400

    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if tenant_filter is not None:
                cur.execute("""
                    SELECT id, email, display_name, tenant_id,
                           is_active, last_login_at, created_at
                    FROM auth.users
                    WHERE tenant_id = %s
                    ORDER BY email
                """, (tenant_filter,))
            else:
                cur.execute("""
                    SELECT id, email, display_name, tenant_id,
                           is_active, last_login_at, created_at
                    FROM auth.users ORDER BY email
                """)
            return jsonify([dict(r) for r in cur.fetchall()]), 200

    except Exception:
        logging.exception("Exception in GET /admin/users")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn: conn.close()


@admin_bp.route("/api/v1/admin/users/<int:user_id>", methods=["GET"])
@limiter.limit("60 per minute")
def get_user_details(user_id):
    """User-Details inkl. aller Rollen. Nur super_admin."""
    actor_id, err = require_super_admin()
    if err: return err

    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id, email, display_name, tenant_id,
                       is_active, must_change_password,
                       last_login_at, created_at
                FROM auth.users WHERE id = %s
            """, (user_id,))
            user = cur.fetchone()
            if not user:
                return jsonify({"error": "User not found"}), 404
            user = dict(user)

            cur.execute("""
                SELECT role FROM auth.user_global_roles WHERE user_id = %s
            """, (user_id,))
            user["global_roles"] = [r["role"] for r in cur.fetchall()]

            cur.execute("""
                SELECT tenant_id, role, is_active
                FROM auth.user_tenant_roles WHERE user_id = %s
            """, (user_id,))
            user["tenant_roles"] = [dict(r) for r in cur.fetchall()]

            cur.execute("""
                SELECT zoo_id, role, is_active
                FROM auth.user_zoo_roles WHERE user_id = %s
            """, (user_id,))
            user["zoo_roles"] = [dict(r) for r in cur.fetchall()]

        return jsonify(user), 200

    except Exception:
        logging.exception(f"Exception in GET /admin/users/{user_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn: conn.close()


@admin_bp.route("/api/v1/admin/users/<int:user_id>", methods=["PUT"])
@limiter.limit("30 per minute")
def update_user(user_id):
    """display_name und is_active bearbeiten. Nur super_admin."""
    actor_id, err = require_super_admin()
    if err: return err

    data = request.get_json(silent=True) or {}
    ALLOWED = {"display_name", "is_active"}
    unknown = set(data.keys()) - ALLOWED
    if unknown:
        return jsonify({"error": f"Unknown fields: {', '.join(sorted(unknown))}"}), 400
    if "is_active" in data and not isinstance(data["is_active"], bool):
        return jsonify({"error": "is_active must be a boolean"}), 400
    if "display_name" in data and len(str(data["display_name"])) > 255:
        return jsonify({"error": "display_name must be at most 255 characters"}), 400
    if not data:
        return jsonify({"error": "No fields to update"}), 400

    # Fix v3.7: Deaktivierung des letzten super_admin verhindern
    if data.get("is_active") is False:
        if _would_remove_last_super_admin(user_id, deactivate=True):
            return jsonify({
                "error": "Cannot deactivate the last active super_admin"
            }), 400

    set_clauses = ", ".join(f"{k} = %s" for k in data)
    values      = list(data.values()) + [user_id]

    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor() as cur:
            cur.execute(f"""
                UPDATE auth.users SET {set_clauses}
                WHERE id = %s RETURNING id
            """, values)
            if not cur.fetchone():
                return jsonify({"error": "User not found"}), 404
        conn.commit()

        log_action("user_updated", actor_user_id=actor_id,
                   target_type="user", target_id=user_id,
                   details={"fields": list(data.keys())})
        return jsonify({"message": "User updated"}), 200

    except Exception:
        if conn: conn.rollback()
        logging.exception(f"Exception in PUT /admin/users/{user_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn: conn.close()


# ── B6: Password-Reset ───────────────────────────────────────────────────────
# Routen liegen im Admin-Blueprint aber unter /api/v1/auth/ —
# strukturell zu auth gehörig, hier platziert bis auth.py refactored wird.

def _send_reset_email(email: str, display_name: str | None,
                      reset_url: str) -> bool:
    """
    Passwort-Reset-Mail versenden.
    Fix 13: os und logging sind hier als Modulimporte vorhanden.
    """
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASSWORD")
    smtp_from = os.getenv("SMTP_FROM", "noreply@zooguide.app")
    smtp_timeout = int(os.getenv("SMTP_TIMEOUT", "10"))

    if not smtp_host or not smtp_user:
        logging.warning("SMTP nicht konfiguriert — Reset-Mail nicht versendet")
        return False

    name = display_name or email
    msg  = MIMEText(
        f"Hallo {name},\n\n"
        f"Du hast einen Passwort-Reset für dein openZooData-Konto angefordert.\n\n"
        f"Link (gültig 60 Minuten):\n{reset_url}\n\n"
        f"Falls du keinen Reset angefordert hast, ignoriere diese E-Mail.\n\n"
        f"openZooData Team"
    )
    msg["Subject"] = "openZooData — Passwort zurücksetzen"
    msg["From"]    = smtp_from
    msg["To"]      = email

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=smtp_timeout) as smtp:
            smtp.starttls()
            smtp.login(smtp_user, smtp_pass)
            smtp.sendmail(smtp_from, [email], msg.as_string())
        return True
    except Exception:
        logging.exception(f"Reset-Mail konnte nicht gesendet werden an {email}")
        return False


@admin_bp.route("/api/v1/auth/password-reset/request", methods=["POST"])
@limiter.limit("5 per minute")
def request_password_reset():
    """
    Passwort-Reset anfordern. Öffentlich, antwortet immer 200.
    Fix 6: Alte offene Tokens werden vor dem neuen invalidiert.
    """
    from helpers.auth_utils import _get_setting_int

    data  = request.get_json(silent=True) or {}
    email = data.get("email", "").strip().lower()
    if not email:
        return jsonify({"error": "email required"}), 400

    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id, display_name FROM auth.users
                WHERE email = %s AND is_active = TRUE
            """, (email,))
            user = cur.fetchone()

            if user:
                # Fix 6: Alte offene Tokens invalidieren
                cur.execute("""
                    UPDATE auth.password_resets SET used_at = NOW()
                    WHERE user_id = %s AND used_at IS NULL
                """, (user["id"],))

                reset_token   = secrets_module.token_urlsafe(32)
                reset_hash    = hashlib.sha256(reset_token.encode()).hexdigest()
                reset_minutes = _get_setting_int("admin_password_reset_minutes", 60)
                public_base   = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")

                cur.execute("""
                    INSERT INTO auth.password_resets
                        (user_id, reset_token_hash, reset_expires)
                    VALUES (%s, %s, NOW() + (%s * INTERVAL '1 minute'))
                """, (user["id"], reset_hash, reset_minutes))
                conn.commit()

                if public_base:
                    # Fix v3.10: Pfad konfigurierbar via PASSWORD_RESET_PATH
                    reset_path = os.getenv("PASSWORD_RESET_PATH", "/admin/reset")
                    reset_url  = f"{public_base}{reset_path}/{reset_token}"
                    _send_reset_email(email, user.get("display_name"), reset_url)

                log_action("password_reset_req", actor_email=email,
                           target_type="user", target_id=user["id"])

        return jsonify({"message": "If the email exists, a reset link was sent"}), 200

    except Exception:
        if conn: conn.rollback()
        logging.exception("Exception in /auth/password-reset/request")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn: conn.close()


@admin_bp.route("/api/v1/auth/password-reset/confirm", methods=["POST"])
@limiter.limit("10 per minute")
def confirm_password_reset():
    """
    Passwort-Reset bestätigen.
    Fix 7: Token-Verbrauch atomar via UPDATE ... RETURNING.
    """
    data         = request.get_json(silent=True) or {}
    token        = data.get("token", "").strip()
    new_password = data.get("new_password", "")

    if not token or not new_password:
        return jsonify({"error": "token and new_password required"}), 400
    if len(new_password) < 12:
        return jsonify({"error": "new_password must be at least 12 characters"}), 400

    token_hash = hashlib.sha256(token.encode()).hexdigest()

    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Fix 7: Atomar markieren und prüfen in einem Statement
            cur.execute("""
                UPDATE auth.password_resets
                SET used_at = NOW()
                WHERE reset_token_hash = %s
                  AND used_at IS NULL
                  AND reset_expires > NOW()
                RETURNING id, user_id
            """, (token_hash,))
            reset = cur.fetchone()
            if not reset:
                return jsonify({"error": "Invalid or expired token"}), 403

            pw_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()

            # Fix v2.4: Nur aktive User dürfen ihr Passwort zurücksetzen.
            cur.execute("""
                UPDATE auth.users
                SET password_hash = %s,
                    must_change_password = FALSE,
                    failed_login_count = 0,
                    locked_until = NULL
                WHERE id = %s AND is_active = TRUE
                RETURNING id
            """, (pw_hash, reset["user_id"]))
            if not cur.fetchone():
                return jsonify({"error": "User is inactive"}), 403

            cur.execute("""
                UPDATE auth.refresh_tokens SET is_active = FALSE
                WHERE user_id = %s
            """, (reset["user_id"],))

        conn.commit()
        log_action("password_reset_done", target_type="user",
                   target_id=reset["user_id"])
        return jsonify({"message": "Password reset successful"}), 200

    except Exception:
        if conn: conn.rollback()
        logging.exception("Exception in /auth/password-reset/confirm")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn: conn.close()


# ── B7: Globale Rollen ────────────────────────────────────────────────────────

@admin_bp.route("/api/v1/admin/users/<int:user_id>/roles/global",
                methods=["POST"])
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


@admin_bp.route("/api/v1/admin/users/<int:user_id>/roles/global/<role>",
                methods=["DELETE"])
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

@admin_bp.route("/api/v1/admin/settings", methods=["GET"])
@limiter.limit("60 per minute")
def get_settings():
    """System-Settings lesen. Nur super_admin."""
    actor_id, err = require_super_admin()
    if err: return err

    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT key, value, value_type, updated_at
                FROM auth.system_settings ORDER BY key
            """)
            return jsonify([dict(r) for r in cur.fetchall()]), 200

    except Exception:
        logging.exception("Exception in GET /admin/settings")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn: conn.close()


@admin_bp.route("/api/v1/admin/settings/<key>", methods=["PUT"])
@limiter.limit("30 per minute")
def update_setting(key):
    """
    System-Setting aktualisieren. Nur super_admin.
    Fix 8: Wert wird nicht ins Audit-Log geschrieben.
    """
    actor_id, err = require_super_admin()
    if err: return err

    data  = request.get_json(silent=True) or {}
    value = data.get("value")
    if value is None:
        return jsonify({"error": "value required"}), 400

    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE auth.system_settings
                SET value = %s, updated_by = %s, updated_at = NOW()
                WHERE key = %s RETURNING key
            """, (str(value), actor_id, key))
            if not cur.fetchone():
                return jsonify({"error": "Setting not found"}), 404
        conn.commit()

        # Fix 8: Wert NICHT loggen — könnte sensitiv sein
        log_action("system_setting_updated", actor_user_id=actor_id,
                   details={"key": key, "changed": True})
        return jsonify({"message": f"Setting '{key}' updated"}), 200

    except Exception:
        if conn: conn.rollback()
        logging.exception(f"Exception in PUT /admin/settings/{key}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn: conn.close()


# ── B9: Audit-Log ─────────────────────────────────────────────────────────────

@admin_bp.route("/api/v1/admin/audit", methods=["GET"])
@limiter.limit("30 per minute")
def get_audit_log():
    """
    Audit-Log lesen. Nur super_admin.
    Fix 9: limit-Parameter wird validiert.
    """
    actor_id, err = require_super_admin()
    if err: return err

    # Fix 9: saubere Validierung
    try:
        limit = int(request.args.get("limit", 100))
    except ValueError:
        return jsonify({"error": "limit must be an integer"}), 400
    limit = max(1, min(limit, 200))

    action    = request.args.get("action")
    from_dt   = request.args.get("from")
    to_dt     = request.args.get("to")

    # Fix v2.5: Integer- und Datum-Filter validieren
    def _int_param(name):
        val = request.args.get(name)
        if val is None:
            return None, None
        try:
            return int(val), None
        except ValueError:
            return None, f"{name} must be an integer"

    user_id,   user_err   = _int_param("user_id")
    zoo_id,    zoo_err    = _int_param("zoo_id")
    tenant_id, tenant_err = _int_param("tenant_id")
    for err_msg in (user_err, zoo_err, tenant_err):
        if err_msg:
            return jsonify({"error": err_msg}), 400

    from datetime import datetime as _dt
    for dt_val, dt_name in ((from_dt, "from"), (to_dt, "to")):
        if dt_val:
            try:
                _dt.fromisoformat(dt_val.replace("Z", "+00:00"))
            except ValueError:
                return jsonify({"error": f"{dt_name} must be ISO 8601 datetime"}), 400

    conditions, params = [], []
    if action:
        conditions.append("action = %s");        params.append(action)
    if user_id is not None:
        conditions.append("actor_user_id = %s"); params.append(user_id)
    if zoo_id is not None:
        conditions.append("zoo_id = %s");        params.append(zoo_id)
    if tenant_id is not None:
        conditions.append("tenant_id = %s");     params.append(tenant_id)
    if from_dt:
        conditions.append("created_at >= %s");   params.append(from_dt)
    if to_dt:
        conditions.append("created_at <= %s");   params.append(to_dt)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)

    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(f"""
                SELECT id, action, success, error_code,
                       actor_user_id, actor_email,
                       tenant_id, zoo_id,
                       target_type, target_id,
                       details, created_at
                FROM auth.audit_log
                {where}
                ORDER BY created_at DESC
                LIMIT %s
            """, params)
            return jsonify([dict(r) for r in cur.fetchall()]), 200

    except Exception:
        logging.exception("Exception in GET /admin/audit")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn: conn.close()


# ── B10: Species-Proposals ────────────────────────────────────────────────────

@admin_bp.route("/api/v1/admin/proposals", methods=["GET"])
@limiter.limit("60 per minute")
def list_proposals():
    """Species-Proposals. super_admin oder moderator.
    Hinweis: Moderator ist aktuell global — keine Zoo-/Tenant-Einschränkung.
    Zoo-spezifische Moderation kommt in einer späteren Version."""
    actor_id = get_user_id_from_token()
    if not actor_id:
        return jsonify({"error": "Unauthorized"}), 401
    if not _can_review_proposals(actor_id):
        return jsonify({"error": "Unauthorized"}), 403

    status_filter  = request.args.get("status", "pending")
    valid_statuses = {"pending", "approved", "rejected",
                      "needs_more_info", "external_check_failed"}
    if status_filter not in valid_statuses:
        return jsonify({"error": "Invalid status"}), 400

    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id, status, wikidata_id, latin_name, german_name,
                       created_by_user_id, created_for_zoo_id,
                       created_at, reviewed_at, review_comment
                FROM auth.species_proposals
                WHERE status = %s
                ORDER BY created_at DESC
                LIMIT 100
            """, (status_filter,))
            return jsonify([dict(r) for r in cur.fetchall()]), 200

    except Exception:
        logging.exception("Exception in GET /admin/proposals")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn: conn.close()


@admin_bp.route("/api/v1/admin/proposals/<int:proposal_id>/approve",
                methods=["PUT"])
@limiter.limit("30 per minute")
def approve_proposal(proposal_id):
    """Proposal genehmigen. super_admin oder moderator."""
    actor_id = get_user_id_from_token()
    if not actor_id:
        return jsonify({"error": "Unauthorized"}), 401
    if not _can_review_proposals(actor_id):
        return jsonify({"error": "Unauthorized"}), 403

    comment = (request.get_json(silent=True) or {}).get("comment", "")

    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE auth.species_proposals
                SET status = 'approved',
                    reviewed_by_user_id = %s,
                    reviewed_at = NOW(),
                    review_comment = %s
                WHERE id = %s AND status = 'pending'
                RETURNING id
            """, (actor_id, comment or None, proposal_id))
            if not cur.fetchone():
                return jsonify({"error": "Proposal not found or not pending"}), 404
        conn.commit()

        log_action("species_confirmed", actor_user_id=actor_id,
                   target_type="species", target_id=proposal_id)
        return jsonify({"message": "Proposal approved"}), 200

    except Exception:
        if conn: conn.rollback()
        logging.exception(f"Exception in PUT /admin/proposals/{proposal_id}/approve")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn: conn.close()


@admin_bp.route("/api/v1/admin/proposals/<int:proposal_id>/reject",
                methods=["PUT"])
@limiter.limit("30 per minute")
def reject_proposal(proposal_id):
    """Proposal ablehnen. super_admin oder moderator."""
    actor_id = get_user_id_from_token()
    if not actor_id:
        return jsonify({"error": "Unauthorized"}), 401
    if not _can_review_proposals(actor_id):
        return jsonify({"error": "Unauthorized"}), 403

    comment = (request.get_json(silent=True) or {}).get("comment", "")

    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE auth.species_proposals
                SET status = 'rejected',
                    reviewed_by_user_id = %s,
                    reviewed_at = NOW(),
                    review_comment = %s
                WHERE id = %s AND status = 'pending'
                RETURNING id
            """, (actor_id, comment or None, proposal_id))
            if not cur.fetchone():
                return jsonify({"error": "Proposal not found or not pending"}), 404
        conn.commit()

        log_action("species_rejected", actor_user_id=actor_id,
                   target_type="species", target_id=proposal_id)
        return jsonify({"message": "Proposal rejected"}), 200

    except Exception:
        if conn: conn.rollback()
        logging.exception(f"Exception in PUT /admin/proposals/{proposal_id}/reject")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn: conn.close()

###############################################################################
# ── Test-Fixtures: RBAC Cleanup ─────────────────────────────────────────────
###############################################################################

@admin_bp.route("/api/v1/admin/test-fixtures/rbac", methods=["DELETE"])
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
        auth_conn = get_auth_connection()
        with auth_conn.cursor() as cur:

            # 1. Alle RBAC-Test-User IDs ermitteln
            cur.execute("""
                SELECT id FROM auth.users WHERE email LIKE '%@rbac.test'
            """)
            rbac_user_ids = [r[0] for r in cur.fetchall()]

            # 2. Alle RBAC-Tenant IDs ermitteln
            cur.execute("""
                SELECT id FROM auth.tenants WHERE name LIKE '%RBAC%'
            """)
            rbac_tenant_ids = [r[0] for r in cur.fetchall()]

            # 3. tenant_zoos aufräumen — nach Tenant-ID UND nach Zoo-ID
            #    Beide Wege nötig: Tenants könnten bereits gelöscht sein
            #    aber tenant_zoos Einträge noch vorhanden (verwaist)
            if rbac_tenant_ids:
                cur.execute("""
                    DELETE FROM auth.tenant_zoos
                    WHERE tenant_id = ANY(%s)
                """, (rbac_tenant_ids,))
            # Zusätzlich: verwaiste Einträge für RBAC-Zoos direkt löschen
            # zoo_ids aus Zoo-DB ermitteln (separate Verbindung nach dem Auth-Block)
            deleted["tenant_zoos_by_tenant"] = cur.rowcount

            # 4. user_zoo_roles aufräumen
            if rbac_user_ids:
                cur.execute("""
                    DELETE FROM auth.user_zoo_roles
                    WHERE user_id = ANY(%s)
                """, (rbac_user_ids,))
                deleted["user_zoo_roles"] = cur.rowcount

            # 5. user_tenant_roles aufräumen
            if rbac_user_ids:
                cur.execute("""
                    DELETE FROM auth.user_tenant_roles
                    WHERE user_id = ANY(%s)
                """, (rbac_user_ids,))
                deleted["user_tenant_roles"] = cur.rowcount

            # 6. refresh_tokens aufräumen
            if rbac_user_ids:
                cur.execute("""
                    DELETE FROM auth.refresh_tokens
                    WHERE user_id = ANY(%s)
                """, (rbac_user_ids,))
                deleted["refresh_tokens"] = cur.rowcount

            # 7. invites aufräumen
            if rbac_user_ids:
                cur.execute("""
                    DELETE FROM auth.invites
                    WHERE user_id = ANY(%s)
                """, (rbac_user_ids,))
                deleted["invites"] = cur.rowcount

            # 8. User hart löschen
            cur.execute("""
                DELETE FROM auth.users WHERE email LIKE '%@rbac.test'
            """)
            deleted["users"] = cur.rowcount

            # 9. Tenants hart löschen
            cur.execute("""
                DELETE FROM auth.tenants WHERE name LIKE '%RBAC%'
            """)
            deleted["tenants"] = cur.rowcount

        auth_conn.commit()

        # 10. Zoos deaktivieren (Zoo-DB) + verwaiste tenant_zoos aufräumen
        zoo_conn = get_pg_connection()
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

        # Verwaiste tenant_zoos nach Zoo-ID löschen (Auth-DB)
        if rbac_zoo_ids:
            auth_conn2 = get_auth_connection()
            try:
                with auth_conn2.cursor() as cur:
                    cur.execute("""
                        DELETE FROM auth.tenant_zoos
                        WHERE zoo_id = ANY(%s)
                    """, (rbac_zoo_ids,))
                    deleted["tenant_zoos_by_zoo"] = cur.rowcount
                auth_conn2.commit()
            finally:
                auth_conn2.close()

        log_action("test_fixtures_rbac_cleanup", actor_user_id=actor_id,
                   details=deleted)

        return jsonify({
            "message": "RBAC test fixtures cleaned up",
            "deleted": deleted
        }), 200

    except Exception:
        if auth_conn: auth_conn.rollback()
        if zoo_conn:  zoo_conn.rollback()
        logging.exception("Exception in DELETE /admin/test-fixtures/rbac")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if auth_conn: auth_conn.close()
        if zoo_conn:  zoo_conn.close()
