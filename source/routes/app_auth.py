"""
routes/app_auth.py
------------------
Anonyme App-Client-Authentifizierung für die ZooGuide iOS App.

Ein App-Token authentifiziert eine App-Installation (device_id), nicht
einen Nutzer. Er berechtigt zu: SQLite-Download, Analytics, Feedback.
Kein Schreibzugriff auf Zoo-Daten.

Endpoints:
    POST /api/v1/auth/app_register  — Erster Start oder Token abgelaufen
    POST /api/v1/auth/app_refresh   — Token verlängern (< 30 Tage bis Ablauf)
"""

import re
import hashlib
import logging
import secrets
from datetime import datetime, timezone, timedelta

from flask import Blueprint, jsonify, request
from db import get_auth_connection
from extensions import limiter

app_auth_bp = Blueprint("app_auth", __name__)

APP_TOKEN_EXPIRY_DAYS  = 90
APP_TOKEN_REFRESH_DAYS = 30   # Verlängern wenn weniger als 30 Tage verbleiben

# UUID v4 Format: xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx (case-insensitive)
_UUID_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE
)


def _is_valid_uuid(value: str) -> bool:
    return bool(_UUID_RE.match(value))


def _issue_token(conn, device_id: str) -> dict:
    """Erstellt einen neuen App-Token und speichert ihn in der DB."""
    token      = secrets.token_hex(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(days=APP_TOKEN_EXPIRY_DAYS)

    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO app_tokens (device_id, token_hash, expires_at)
            VALUES (%s, %s, %s)
        """, (device_id, token_hash, expires_at))

    return {
        "app_token":  token,
        "expires_at": expires_at.isoformat(),
    }


@app_auth_bp.route("/api/v1/auth/app_register", methods=["POST"])
@limiter.limit("10 per minute")
def app_register():
    """
    Registriert eine App-Installation und gibt einen App-Token zurück.

    Request:
        { "device_id": "<uuid>" }

    Response:
        { "app_token": "<hex64>", "expires_at": "<iso8601>" }

    Idempotent: Gleiche device_id kann mehrfach registriert werden
    (z.B. nach Token-Ablauf). Alte Tokens werden deaktiviert.
    """
    data      = request.get_json(silent=True) or {}
    device_id = data.get("device_id", "").strip()

    if not device_id:
        return jsonify({"error": "device_id required"}), 400
    if not _is_valid_uuid(device_id):
        return jsonify({"error": "device_id must be a valid UUID"}), 400

    conn = None
    try:
        conn = get_auth_connection()

        # Alte aktive Tokens für diese device_id deaktivieren
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE app_tokens
                SET is_active = FALSE
                WHERE device_id = %s AND is_active = TRUE
            """, (device_id,))

        result = _issue_token(conn, device_id)
        conn.commit()
        return jsonify(result), 201

    except Exception:
        logging.exception("Exception in /auth/app_register")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


@app_auth_bp.route("/api/v1/auth/app_refresh", methods=["POST"])
@limiter.limit("30 per minute")
def app_refresh():
    """
    Verlängert einen App-Token wenn er in weniger als 30 Tagen abläuft.

    Request:
        { "app_token": "<hex64>", "device_id": "<uuid>" }

    Response (Token verlängert):
        { "app_token": "<hex64>", "expires_at": "<iso8601>", "refreshed": true }

    Response (Token noch gültig, kein Refresh nötig):
        { "app_token": "<aktueller token>", "expires_at": "<iso8601>", "refreshed": false }

    Response (Token abgelaufen oder ungültig):
        HTTP 403 → App soll app_register aufrufen
    """
    data      = request.get_json(silent=True) or {}
    app_token = data.get("app_token", "").strip()
    device_id = data.get("device_id", "").strip()

    if not app_token or not device_id:
        return jsonify({"error": "app_token and device_id required"}), 400
    if not _is_valid_uuid(device_id):
        return jsonify({"error": "device_id must be a valid UUID"}), 400

    token_hash = hashlib.sha256(app_token.encode()).hexdigest()

    conn = None
    try:
        conn = get_auth_connection()

        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, device_id, expires_at
                FROM app_tokens
                WHERE token_hash = %s
                  AND is_active = TRUE
                  AND expires_at > NOW()
            """, (token_hash,))
            row = cur.fetchone()

        if not row:
            return jsonify({"error": "Token invalid or expired — re-register"}), 403

        token_id, db_device_id, expires_at = row

        # device_id muss übereinstimmen
        if db_device_id != device_id:
            return jsonify({"error": "Unauthorized"}), 403

        # Noch mehr als 30 Tage gültig — kein Refresh nötig
        remaining = expires_at - datetime.now(timezone.utc)
        if remaining.days > APP_TOKEN_REFRESH_DAYS:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE app_tokens SET last_used_at = NOW() WHERE id = %s",
                    (token_id,)
                )
            conn.commit()
            return jsonify({
                "app_token":  app_token,
                "expires_at": expires_at.isoformat(),
                "refreshed":  False,
            }), 200

        # Alten Token deaktivieren und neuen ausstellen
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE app_tokens SET is_active = FALSE WHERE id = %s",
                (token_id,)
            )

        result = _issue_token(conn, device_id)
        conn.commit()
        result["refreshed"] = True
        return jsonify(result), 200

    except Exception:
        logging.exception("Exception in /auth/app_refresh")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()
