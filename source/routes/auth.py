import hashlib
import logging
import os
import re
import secrets as secrets_module
import bcrypt
import psycopg2.extras
from datetime import datetime, timezone, timedelta
from flask import Blueprint, jsonify, request
from helpers.auth_utils import (
    verify_access_token, create_access_token,
    JWT_SECRET, REFRESH_EXPIRY_DAYS, _get_setting_int
)
from helpers.audit import log_action
from helpers.authz import require_super_admin
from db import get_auth_connection
from extensions import limiter

auth_bp = Blueprint("auth", __name__)

# Login-Lockout Konstanten (Defaults — überschreibbar via system_settings)
MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES   = 30


@auth_bp.route("/api/v1/auth/login", methods=["POST"])
@limiter.limit("10 per minute")
def login():
    data      = request.get_json(silent=True) or {}
    email     = data.get("email", "").strip().lower()
    password  = data.get("password", "")
    device_id = data.get("device_id")

    if not email or not password:
        return jsonify({"error": "email and password required"}), 400

    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:

            # Schemaqualifiziert — kein Vertrauen auf search_path
            cur.execute("""
                SELECT u.id, u.email, u.password_hash, u.display_name,
                       u.is_active, u.tenant_id,
                       u.failed_login_count, u.locked_until,
                       u.must_change_password,
                       t.is_active AS tenant_active
                FROM auth.users u
                LEFT JOIN auth.tenants t ON t.id = u.tenant_id
                WHERE u.email = %s
            """, (email,))
            user = cur.fetchone()

            # Generische Antwort — verhindert User-Enumeration
            if not user or not user["is_active"]:
                log_action("login_failed", actor_email=email, success=False,
                           error_code="user_not_found_or_inactive")
                return jsonify({"error": "Invalid credentials"}), 403

            # Tenant deaktiviert?
            if user["tenant_id"] is not None and not user["tenant_active"]:
                log_action("login_failed", actor_user_id=user["id"],
                           tenant_id=user["tenant_id"], success=False,
                           error_code="tenant_inactive")
                return jsonify({"error": "Invalid credentials"}), 403

            # Account gesperrt?
            if user["locked_until"] and user["locked_until"] > datetime.now(timezone.utc):
                log_action("login_failed", actor_user_id=user["id"],
                           tenant_id=user["tenant_id"], success=False,
                           error_code="account_locked")
                return jsonify({"error": "Invalid credentials"}), 403

            # Passwort prüfen
            if not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
                new_count = (user["failed_login_count"] or 0) + 1
                if new_count >= MAX_FAILED_LOGINS:
                    cur.execute("""
                        UPDATE auth.users
                        SET failed_login_count = %s,
                            locked_until       = NOW() + (%s * INTERVAL '1 minute')
                        WHERE id = %s
                    """, (new_count, LOCKOUT_MINUTES, user["id"]))
                    conn.commit()
                    log_action("login_failed", actor_user_id=user["id"],
                               tenant_id=user["tenant_id"], success=False,
                               error_code="account_locked_now")
                    return jsonify({"error": "Invalid credentials"}), 403
                else:
                    cur.execute("""
                        UPDATE auth.users SET failed_login_count = %s WHERE id = %s
                    """, (new_count, user["id"]))
                    conn.commit()
                log_action("login_failed", actor_user_id=user["id"],
                           tenant_id=user["tenant_id"], success=False,
                           error_code="wrong_password")
                return jsonify({"error": "Invalid credentials"}), 403

            # Erfolgreicher Login
            cur.execute("""
                UPDATE auth.users
                SET failed_login_count = 0,
                    locked_until       = NULL,
                    last_login_at      = NOW()
                WHERE id = %s
            """, (user["id"],))

            access_token = create_access_token(
                user["id"], user["email"], user["tenant_id"]
            )

            refresh_days       = _get_setting_int("admin_refresh_token_days", REFRESH_EXPIRY_DAYS)
            refresh_token      = secrets_module.token_hex(32)
            refresh_token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
            expires_at         = datetime.now(timezone.utc) + timedelta(days=refresh_days)

            cur.execute("""
                INSERT INTO auth.refresh_tokens (user_id, token_hash, device_id, expires_at)
                VALUES (%s, %s, %s, %s)
            """, (user["id"], refresh_token_hash, device_id, expires_at))

        conn.commit()

        log_action("login_success", actor_user_id=user["id"],
                   tenant_id=user["tenant_id"])

        response = {
            "access_token":       access_token,
            "refresh_token":      refresh_token,
            "display_name":       user["display_name"],
            "must_change_password": user["must_change_password"],
        }
        return jsonify(response), 200

    except Exception:
        logging.exception("Exception in /auth/login")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@auth_bp.route("/api/v1/auth/refresh", methods=["POST"])
@limiter.limit("30 per minute")
def refresh_token_endpoint():
    data          = request.get_json(silent=True) or {}
    refresh_token = data.get("refresh_token", "").strip()

    if not refresh_token:
        return jsonify({"error": "refresh_token required"}), 400

    token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()

    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Atomares UPDATE — verhindert Race Condition
            cur.execute("""
                UPDATE auth.refresh_tokens
                SET is_active = FALSE, last_used = NOW()
                WHERE token_hash = %s
                  AND is_active  = TRUE
                  AND expires_at > NOW()
            """, (token_hash,))

            if cur.rowcount != 1:
                return jsonify({"error": "Unauthorized"}), 403

            cur.execute("""
                SELECT rt.user_id, rt.device_id,
                       u.email, u.is_active AS user_active,
                       u.tenant_id,
                       t.is_active AS tenant_active
                FROM auth.refresh_tokens rt
                JOIN auth.users u ON u.id = rt.user_id
                LEFT JOIN auth.tenants t ON t.id = u.tenant_id
                WHERE rt.token_hash = %s
            """, (token_hash,))
            row = cur.fetchone()

            if not row or not row["user_active"]:
                return jsonify({"error": "Unauthorized"}), 403

            if row["tenant_id"] is not None and not row["tenant_active"]:
                return jsonify({"error": "Unauthorized"}), 403

            refresh_days           = _get_setting_int("admin_refresh_token_days", REFRESH_EXPIRY_DAYS)
            new_refresh_token      = secrets_module.token_hex(32)
            new_refresh_token_hash = hashlib.sha256(new_refresh_token.encode()).hexdigest()
            new_expires_at         = datetime.now(timezone.utc) + timedelta(days=refresh_days)

            cur.execute("""
                INSERT INTO auth.refresh_tokens (user_id, token_hash, device_id, expires_at)
                VALUES (%s, %s, %s, %s)
            """, (row["user_id"], new_refresh_token_hash, row["device_id"], new_expires_at))

            access_token = create_access_token(
                row["user_id"], row["email"], row["tenant_id"]
            )

        conn.commit()
        return jsonify({
            "access_token":  access_token,
            "refresh_token": new_refresh_token,
        }), 200

    except Exception:
        logging.exception("Exception in /auth/refresh")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@auth_bp.route("/api/v1/auth/logout", methods=["POST"])
@limiter.limit("30 per minute")
def logout():
    data          = request.get_json(silent=True) or {}
    refresh_token = data.get("refresh_token", "").strip()

    if not refresh_token:
        return jsonify({"error": "refresh_token required"}), 400

    token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()

    # User-ID für Audit aus JWT lesen und Access-JWT widerrufen
    payload = verify_access_token()
    user_id = int(payload["sub"]) if payload else None

    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE auth.refresh_tokens SET is_active = FALSE WHERE token_hash = %s",
                (token_hash,)
            )
            if payload and payload.get("jti") and payload.get("exp"):
                exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
                cur.execute("""
                    INSERT INTO auth.revoked_tokens (jti, reason, expires_at)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (jti) DO NOTHING
                """, (payload["jti"], "logout", exp))
        conn.commit()
        log_action("logout", actor_user_id=user_id)
        return jsonify({"message": "Logged out"}), 200

    except Exception:
        logging.exception("Exception in /auth/logout")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@auth_bp.route("/api/v1/auth/register", methods=["POST"])
@limiter.limit("10 per minute")
def register_user():
    """
    Legt einen neuen Admin-/ZooCreator-User an und erzeugt einen Invite-Link.

    Nur super_admin.
    Body: { email, display_name, tenant_id (optional für super_admin) }

    Wichtig:
    - Kein temporäres Passwort wird an den User gegeben.
    - Der User setzt sein Passwort über /api/v1/auth/invite/<token>.
    - Rollen werden durch separate Admin-/Tenant-/Zoo-Routen vergeben.
    """
    actor_user_id, err = require_super_admin()
    if err:
        return err

    data         = request.get_json(silent=True) or {}
    email        = data.get("email", "").strip().lower()
    display_name = data.get("display_name", "").strip()
    tenant_id    = data.get("tenant_id")

    if not email:
        return jsonify({"error": "email required"}), 400
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return jsonify({"error": "invalid email"}), 400

    # Platzhalter-Passwort — Login bleibt bis Invite-Annahme praktisch unbenutzbar.
    placeholder_pw = secrets_module.token_urlsafe(48)
    pw_hash = bcrypt.hashpw(placeholder_pw.encode(), bcrypt.gensalt()).decode()

    invite_token = secrets_module.token_urlsafe(32)
    invite_hash = hashlib.sha256(invite_token.encode()).hexdigest()
    invite_minutes = _get_setting_int("admin_invite_token_minutes", 1440)
    public_base_url = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    invite_url = f"{public_base_url}/admin/invite/{invite_token}" if public_base_url else None

    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:

            # Tenant-Existenz prüfen wenn angegeben
            if tenant_id is not None:
                cur.execute("SELECT id FROM auth.tenants WHERE id = %s", (tenant_id,))
                if not cur.fetchone():
                    return jsonify({"error": "Invalid tenant_id"}), 400

            cur.execute("""
                INSERT INTO auth.users (email, password_hash, display_name,
                                        tenant_id, must_change_password)
                VALUES (%s, %s, %s, %s, TRUE)
                RETURNING id
            """, (email, pw_hash, display_name or None, tenant_id))
            new_user_id = cur.fetchone()["id"]

            cur.execute("""
                INSERT INTO auth.invites (user_id, invite_token_hash, invite_expires)
                VALUES (%s, %s, NOW() + (%s * INTERVAL '1 minute'))
            """, (new_user_id, invite_hash, invite_minutes))

        conn.commit()

        mail_sent = False
        if invite_url:
            mail_sent = _send_invite_email(email, display_name, invite_url)

        log_action("user_created", actor_user_id=actor_user_id,
                   tenant_id=tenant_id, target_type="user", target_id=new_user_id,
                   details={"email": email, "invite_sent": mail_sent})
        log_action("invite_sent", actor_user_id=actor_user_id,
                   tenant_id=tenant_id, target_type="user", target_id=new_user_id,
                   details={"email": email, "invite_sent": mail_sent})

        response = {
            "id": new_user_id,
            "message": "User created and invite generated",
            "invite_sent": mail_sent,
        }
        # Für Referenz-/Stagingbetrieb ohne SMTP. In Produktion sollte die UI den Link nicht anzeigen.
        if not mail_sent and invite_url:
            response["invite_url"] = invite_url
        return jsonify(response), 201

    except psycopg2.errors.UniqueViolation:
        if conn:
            conn.rollback()
        return jsonify({"error": "User already exists"}), 409
    except Exception:
        if conn:
            conn.rollback()
        logging.exception("Exception in /auth/register")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@auth_bp.route("/api/v1/auth/invite/<token>", methods=["POST"])
@limiter.limit("10 per minute")
def accept_invite(token):
    """
    Nimmt einen Invite an und setzt das initiale Passwort.
    Body: { password }
    """
    data = request.get_json(silent=True) or {}
    password = data.get("password", "")

    if len(password) < 12:
        return jsonify({"error": "password must be at least 12 characters"}), 400

    token_hash = hashlib.sha256(token.encode()).hexdigest()
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT i.id AS invite_id, i.user_id, u.email, u.tenant_id, u.is_active
                FROM auth.invites i
                JOIN auth.users u ON u.id = i.user_id
                LEFT JOIN auth.tenants t ON t.id = u.tenant_id
                WHERE i.invite_token_hash = %s
                  AND i.invite_accepted_at IS NULL
                  AND i.invite_expires > NOW()
                  AND u.is_active = TRUE
                  AND (u.tenant_id IS NULL OR t.is_active = TRUE)
            """, (token_hash,))
            invite = cur.fetchone()
            if not invite:
                return jsonify({"error": "Invalid or expired invite"}), 403

            cur.execute("""
                UPDATE auth.users
                SET password_hash = %s,
                    must_change_password = FALSE,
                    failed_login_count = 0,
                    locked_until = NULL
                WHERE id = %s
            """, (pw_hash, invite["user_id"]))

            cur.execute("""
                UPDATE auth.invites
                SET invite_accepted_at = NOW()
                WHERE id = %s
            """, (invite["invite_id"],))

        conn.commit()
        log_action("invite_accepted", actor_user_id=invite["user_id"],
                   tenant_id=invite["tenant_id"], target_type="user",
                   target_id=invite["user_id"])
        return jsonify({"message": "Invite accepted"}), 200

    except Exception:
        if conn:
            conn.rollback()
        logging.exception("Exception in /auth/invite")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


def _send_invite_email(email: str, display_name: str, invite_url: str) -> bool:
    """Sendet Invite-Mail wenn SMTP konfiguriert ist. Gibt False zurück wenn nicht."""
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASSWORD")
    smtp_from = os.getenv("SMTP_FROM", "noreply@zooguide.app")

    if not smtp_host or not smtp_user or not smtp_pass:
        logging.warning("SMTP nicht vollständig konfiguriert — Invite-Link nicht per Mail versendet")
        return False

    try:
        import smtplib
        from email.mime.text import MIMEText

        greeting = f"Hallo {display_name}," if display_name else "Hallo,"
        msg = MIMEText(
            f"{greeting}\n\n"
            "für dich wurde ein openZooData Admin-/ZooCreator-Zugang angelegt.\n\n"
            f"Bitte setze dein Passwort über diesen Link:\n{invite_url}\n\n"
            "Der Link ist zeitlich begrenzt gültig.\n"
        )
        msg["Subject"] = "openZooData Einladung"
        msg["From"] = smtp_from
        msg["To"] = email

        with smtplib.SMTP(smtp_host, smtp_port) as smtp:
            smtp.starttls()
            smtp.login(smtp_user, smtp_pass)
            smtp.sendmail(smtp_from, [email], msg.as_string())
        return True
    except Exception:
        logging.exception("Invite-Mail konnte nicht versendet werden")
        return False
