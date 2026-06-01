import os
import hashlib
import logging
import jwt
import psycopg2.extras
from datetime import datetime, timezone, timedelta
from flask import request, jsonify

JWT_SECRET          = os.getenv("JWT_SECRET")
JWT_ALGORITHM       = "HS256"
JWT_EXPIRY_HOURS    = 24
REFRESH_EXPIRY_DAYS = 30


# ---------------------------------------------------------------------------
# App-Token — iOS App Client (anonym, kein Zoo-Bezug)
# ---------------------------------------------------------------------------

def require_app_token():
    """
    Prüft einen App-Token (iOS-App-Client).
    Berechtigt zu: SQLite-Download, Analytics, Feedback.
    Kein Schreibzugriff auf Zoo-Daten.
    Gibt device_id zurück oder None bei ungültigem Token.
    """
    from db import get_auth_connection
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None, (jsonify({"error": "Unauthorized"}), 403)
    token      = auth_header.removeprefix("Bearer ").strip()
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT device_id
                FROM app_tokens
                WHERE token_hash = %s
                  AND is_active = TRUE
                  AND expires_at > NOW()
            """, (token_hash,))
            row = cur.fetchone()
            if row:
                cur.execute(
                    "UPDATE app_tokens SET last_used_at = NOW() WHERE token_hash = %s",
                    (token_hash,)
                )
                conn.commit()
                return row["device_id"], None
        return None, (jsonify({"error": "Unauthorized"}), 403)
    except Exception as e:
        logging.warning(f"App-Token check failed: {e}")
        return None, (jsonify({"error": "Unauthorized"}), 403)
    finally:
        if conn:
            conn.close()


# ---------------------------------------------------------------------------
# JWT — Zoo-Admin (ZooCreator)
# ---------------------------------------------------------------------------

def create_access_token(user_id, email, role, zoo_dir):
    payload = {
        "sub":     str(user_id),
        "email":   email,
        "role":    role,
        "zoo_dir": zoo_dir,
        "exp":     datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
        "iat":     datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_access_token():
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    token = auth_header.removeprefix("Bearer ").strip()
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def require_jwt_write(zoo):
    """JWT + zoo_dir + write-fähige Rolle (zoo_admin, super_admin)."""
    payload = verify_access_token()
    if not payload:
        return None, (jsonify({"error": "Unauthorized"}), 403)
    role    = payload.get("role")
    zoo_dir = payload.get("zoo_dir")
    if role == "super_admin":
        return payload, None
    if role == "zoo_admin" and zoo_dir == zoo:
        return payload, None
    return None, (jsonify({"error": "Unauthorized"}), 403)


def require_jwt_read(zoo):
    """JWT + zoo_dir für lesenden Zugriff (alle Rollen)."""
    payload = verify_access_token()
    if not payload:
        return None, (jsonify({"error": "Unauthorized"}), 403)
    role    = payload.get("role")
    zoo_dir = payload.get("zoo_dir")
    if role == "super_admin":
        return payload, None
    if role in ("zoo_admin", "zoo_viewer") and zoo_dir == zoo:
        return payload, None
    return None, (jsonify({"error": "Unauthorized"}), 403)
