import logging
import psycopg2
import psycopg2.extras
from flask import Blueprint, jsonify, request
from db import get_pg_connection, get_auth_connection
from extensions import limiter
from helpers.authz import require_super_admin
from helpers.coordinates import is_valid_slug
from routes.admin_routes.helpers import (_would_remove_last_super_admin,
    _is_super_admin)

admin_users_bp = Blueprint("admin_users_bp", __name__)

@admin_users_bp.route("/api/v1/admin/users", methods=["GET"])
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


@admin_users_bp.route("/api/v1/admin/users/<int:user_id>", methods=["GET"])
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


@admin_users_bp.route("/api/v1/admin/users/<int:user_id>", methods=["PUT"])
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


@admin_users_bp.route("/api/v1/admin/users/<int:user_id>", methods=["DELETE"])
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


@admin_users_bp.route("/api/v1/auth/password-reset/request", methods=["POST"])
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


@admin_users_bp.route("/api/v1/auth/password-reset/confirm", methods=["POST"])
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
