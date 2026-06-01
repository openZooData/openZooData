import hashlib
import logging
import secrets as secrets_module
import bcrypt
import psycopg2.extras
from datetime import datetime, timezone, timedelta
from flask import Blueprint, jsonify, request
from helpers.auth_utils import (
    verify_access_token, create_access_token,
    JWT_SECRET, REFRESH_EXPIRY_DAYS
)
from db import get_auth_connection
from extensions import limiter

auth_bp = Blueprint("auth", __name__)

# Fix 5: Login-Lockout Konstanten
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

            cur.execute("""
                SELECT u.id, u.email, u.password_hash, u.full_name, u.is_active,
                       u.failed_login_count, u.locked_until,
                       r.role, r.zoo_dir
                FROM users u
                LEFT JOIN user_roles r ON r.user_id = u.id
                WHERE u.email = %s
            """, (email,))
            user = cur.fetchone()

            # Generische Antwort — kein Unterschied zwischen "nicht gefunden" und
            # "falsches Passwort" (verhindert User-Enumeration)
            if not user or not user["is_active"]:
                return jsonify({"error": "Invalid credentials"}), 403

            # Fix 5: Account gesperrt?
            if user["locked_until"] and user["locked_until"] > datetime.now(timezone.utc):
                return jsonify({
                    "error": f"Account temporarily locked. Try again in {LOCKOUT_MINUTES} minutes."
                }), 403

            if not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
                # Fix 5: Fehlversuch zählen
                new_count = (user["failed_login_count"] or 0) + 1
                if new_count >= MAX_FAILED_LOGINS:
                    cur.execute("""
                        UPDATE users
                        SET failed_login_count = %s,
                            locked_until       = NOW() + INTERVAL '%s minutes'
                        WHERE id = %s
                    """, (new_count, LOCKOUT_MINUTES, user["id"]))
                    conn.commit()
                    return jsonify({
                        "error": f"Account locked for {LOCKOUT_MINUTES} minutes "
                                 f"after {MAX_FAILED_LOGINS} failed attempts."
                    }), 403
                else:
                    cur.execute("""
                        UPDATE users SET failed_login_count = %s WHERE id = %s
                    """, (new_count, user["id"]))
                    conn.commit()
                return jsonify({"error": "Invalid credentials"}), 403

            if not user["role"]:
                return jsonify({"error": "No role assigned"}), 403

            # Fix 5: Erfolgreicher Login — Zähler zurücksetzen + last_login aktualisieren
            cur.execute("""
                UPDATE users
                SET failed_login_count = 0,
                    locked_until       = NULL,
                    last_login         = NOW()
                WHERE id = %s
            """, (user["id"],))

            access_token = create_access_token(
                user["id"], user["email"], user["role"], user["zoo_dir"]
            )

            refresh_token      = secrets_module.token_hex(32)
            refresh_token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
            expires_at         = datetime.now(timezone.utc) + timedelta(days=REFRESH_EXPIRY_DAYS)

            cur.execute("""
                INSERT INTO refresh_tokens (user_id, token_hash, device_id, expires_at)
                VALUES (%s, %s, %s, %s)
            """, (user["id"], refresh_token_hash, device_id, expires_at))

        conn.commit()
        return jsonify({
            "access_token":  access_token,
            "refresh_token": refresh_token,
            "role":          user["role"],
            "zoo_dir":       user["zoo_dir"],
            "full_name":     user["full_name"],
        }), 200

    except Exception as e:
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
            # Atomares UPDATE — verhindert Race Condition bei parallelen Requests
            cur.execute("""
                UPDATE refresh_tokens
                SET is_active = FALSE, last_used = NOW()
                WHERE token_hash = %s
                AND is_active = TRUE
                AND expires_at > NOW()
            """, (token_hash,))

            if cur.rowcount != 1:
                return jsonify({"error": "Unauthorized"}), 403

            cur.execute("""
                SELECT rt.user_id, rt.device_id,
                       u.email, u.is_active AS user_active,
                       r.role, r.zoo_dir
                FROM refresh_tokens rt
                JOIN users u ON u.id = rt.user_id
                LEFT JOIN user_roles r ON r.user_id = rt.user_id
                WHERE rt.token_hash = %s
            """, (token_hash,))
            row = cur.fetchone()

            if not row or not row["user_active"]:
                return jsonify({"error": "Unauthorized"}), 403

            new_refresh_token      = secrets_module.token_hex(32)
            new_refresh_token_hash = hashlib.sha256(new_refresh_token.encode()).hexdigest()
            new_expires_at         = datetime.now(timezone.utc) + timedelta(days=REFRESH_EXPIRY_DAYS)

            cur.execute("""
                INSERT INTO refresh_tokens (user_id, token_hash, device_id, expires_at)
                VALUES (%s, %s, %s, %s)
            """, (row["user_id"], new_refresh_token_hash, row["device_id"], new_expires_at))

            access_token = create_access_token(
                row["user_id"], row["email"], row["role"], row["zoo_dir"]
            )

        conn.commit()
        return jsonify({
            "access_token":  access_token,
            "refresh_token": new_refresh_token,
        }), 200

    except Exception as e:
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

    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE refresh_tokens SET is_active = FALSE WHERE token_hash = %s",
                (token_hash,)
            )
        conn.commit()
        return jsonify({"message": "Logged out"}), 200

    except Exception as e:
        logging.exception("Exception in /auth/logout")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@auth_bp.route("/api/v1/auth/register", methods=["POST"])
@limiter.limit("10 per minute")
def register_user():
    payload = verify_access_token()
    if not payload or payload.get("role") != "super_admin":
        return jsonify({"error": "Unauthorized"}), 403

    data      = request.get_json(silent=True) or {}
    email     = data.get("email", "").strip().lower()
    password  = data.get("password", "")
    full_name = data.get("full_name", "").strip()
    role      = data.get("role", "zoo_viewer")
    zoo_dir   = data.get("zoo_dir")

    if not email or not password:
        return jsonify({"error": "email and password required"}), 400
    if role not in ("super_admin", "zoo_admin", "zoo_viewer"):
        return jsonify({"error": "Invalid role"}), 400

    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                INSERT INTO users (email, password_hash, full_name)
                VALUES (%s, %s, %s)
                RETURNING id
            """, (email, pw_hash, full_name or None))
            user_id = cur.fetchone()["id"]

            cur.execute("""
                INSERT INTO user_roles (user_id, zoo_dir, role)
                VALUES (%s, %s, %s)
            """, (user_id, zoo_dir, role))

        conn.commit()
        return jsonify({"id": user_id, "message": "User created"}), 201

    except Exception as e:
        logging.exception("Exception in /auth/register")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()
