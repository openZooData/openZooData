import os
import hashlib
import logging
import uuid
import jwt
import psycopg2.extras
from datetime import datetime, timezone, timedelta
from flask import request, jsonify

JWT_SECRET          = os.getenv("JWT_SECRET")
JWT_ALGORITHM       = "HS256"
JWT_EXPIRY_MINUTES  = 480
REFRESH_EXPIRY_DAYS = 30

# Migration v7: JWT enthält KEINE Rollen mehr.
# Claims: sub, email, tenant_id, jti, iat, exp
# Rollen werden frisch aus DB geladen via helpers/authz.py


def require_app_token():
    """App-Token für ZooGuide-App-Besucher — UNVERÄNDERT."""
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
                SELECT device_id FROM auth.app_tokens
                WHERE token_hash = %s AND is_active = TRUE AND expires_at > NOW()
            """, (token_hash,))
            row = cur.fetchone()
            if row:
                cur.execute("UPDATE auth.app_tokens SET last_used_at = NOW() WHERE token_hash = %s", (token_hash,))
                conn.commit()
                return row["device_id"], None
        return None, (jsonify({"error": "Unauthorized"}), 403)
    except Exception:
        logging.exception("App-Token check failed")
        return None, (jsonify({"error": "Unauthorized"}), 403)
    finally:
        if conn:
            conn.close()


def create_access_token(user_id: int, email: str, tenant_id) -> str:
    expiry_minutes = _get_setting_int("admin_access_token_minutes", JWT_EXPIRY_MINUTES)
    payload = {
        "sub":       str(user_id),
        "email":     email,
        "tenant_id": tenant_id,
        "jti":       str(uuid.uuid4()),
        "exp":       datetime.now(timezone.utc) + timedelta(minutes=expiry_minutes),
        "iat":       datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_access_token() -> dict | None:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    token = auth_header.removeprefix("Bearer ").strip()
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None

    # Migration v7: revoked_tokens ist jetzt aktiv.
    # Fail-closed: Bei DB-Fehler wird der Token abgelehnt.
    jti = payload.get("jti")
    if not jti:
        return None

    from db import get_auth_connection
    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 1 FROM auth.revoked_tokens
                WHERE jti = %s AND expires_at > NOW()
            """, (jti,))
            if cur.fetchone():
                return None
    except Exception:
        logging.exception("JWT revocation check failed")
        return None
    finally:
        if conn:
            conn.close()

    return payload


def _get_setting_int(key: str, default: int) -> int:
    from db import get_auth_connection
    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT value FROM auth.system_settings WHERE key = %s AND value_type = 'int'", (key,))
            row = cur.fetchone()
            if row:
                return int(row[0])
    except Exception:
        pass
    finally:
        if conn:
            conn.close()
    return default
