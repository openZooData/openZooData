import os
import logging
from flask import Flask, jsonify, request
from dotenv import load_dotenv
from pathlib import Path
from extensions import limiter
from werkzeug.middleware.proxy_fix import ProxyFix
import hmac
from werkzeug.exceptions import HTTPException

load_dotenv(Path(__file__).parent.parent / ".env")

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

# Fix 6: Globales Größenlimit — verhindert Speicher/Disk-DoS durch riesige Bodies.
# Medien-Upload prüft separat 10 MB; 12 MB als globaler Deckel.
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024

limiter.init_app(app)

logging.basicConfig(filename="flask-error.log", level=logging.WARNING)

JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET or len(JWT_SECRET) < 32:
    raise RuntimeError("JWT_SECRET fehlt oder ist zu kurz (min. 32 Zeichen)")

HEALTH_CHECK_KEY = os.getenv("HEALTH_CHECK_KEY")
if not HEALTH_CHECK_KEY or len(HEALTH_CHECK_KEY) < 32:
    raise RuntimeError("HEALTH_CHECK_KEY fehlt oder ist zu kurz (min. 32 Zeichen)")

from routes.auth          import auth_bp
from routes.app_auth      import app_auth_bp
from routes.species       import species_bp
from routes.enclosures    import enclosures_bp
from routes.domains       import domains_bp
from routes.sqlite        import sqlite_bp
from routes.publish       import publish_bp
from routes.media         import media_bp
from routes.feedback      import feedback_bp
from routes.feed          import feed_bp

app.register_blueprint(auth_bp)
app.register_blueprint(app_auth_bp)
app.register_blueprint(species_bp)
app.register_blueprint(enclosures_bp)
app.register_blueprint(domains_bp)
app.register_blueprint(sqlite_bp)
app.register_blueprint(publish_bp)
app.register_blueprint(media_bp)
app.register_blueprint(feedback_bp)
app.register_blueprint(feed_bp)


@app.route("/")
def root():
    return jsonify({"message": "Zooguide API is running.", "status": "ok"}), 200


# ---------------------------------------------------------------------------
# Public Health-Endpoint — für UptimeRobot / Hetzner-Monitoring
# Gibt nur 200 / 503 zurück, keine internen Details.
# ---------------------------------------------------------------------------
@app.route("/status")
def status():
    from db import get_auth_connection, get_pg_connection
    healthy = True
    for get_conn in (get_auth_connection, get_pg_connection):
        try:
            c = get_conn()
            c.cursor().execute("SELECT 1")
            c.close()
        except Exception:
            healthy = False
            break
    return jsonify({"status": "ok" if healthy else "degraded"}), 200 if healthy else 503


# ---------------------------------------------------------------------------
# Detaillierter Health-Endpoint — nur mit HEALTH_CHECK_KEY
# Verrät keine internen Details an unauthentifizierte Clients.
# Header: X-Health-Key: <HEALTH_CHECK_KEY aus .env>
# ---------------------------------------------------------------------------
@app.route("/status/details")
@limiter.limit("30 per minute")
def status_details():
    key = request.headers.get("X-Health-Key", "")
    if not key or not hmac.compare_digest(key, HEALTH_CHECK_KEY):
        return jsonify({"error": "Unauthorized"}), 403

    from db import get_auth_connection, get_pg_connection

    checks  = {}
    healthy = True

    for label, get_conn in (
        ("db_auth", get_auth_connection),
        ("db_zoo",  get_pg_connection),
    ):
        try:
            c = get_conn()
            c.cursor().execute("SELECT 1")
            c.close()
            checks[label] = "ok"
        except Exception:
            logging.exception(f"Health-Check: {label} nicht erreichbar")
            checks[label] = "error"
            healthy = False

    # SQLite-Dateien
    sqlite_dir = os.path.join(os.path.expanduser("~"), "sqlite")
    if os.path.isdir(sqlite_dir):
        checks["sqlite_files"] = len([
            f for f in os.listdir(sqlite_dir) if f.endswith(".sqlite.gz")
        ])
    else:
        checks["sqlite_files"] = 0

    return jsonify({
        "status": "ok" if healthy else "degraded",
        "checks": checks,
    }), 200 if healthy else 503


# Fix 7: Security-Header auf alle Responses
@app.after_request
def set_security_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    return resp


@app.errorhandler(Exception)
def handle_exception(e):
    if isinstance(e, HTTPException):
        return e
    logging.exception("Unhandled exception")
    return jsonify({"error": "Internal server error"}), 500


@app.errorhandler(429)
def ratelimit_handler(e):
    logging.warning(f"Rate Limit überschritten: {request.remote_addr}")
    return jsonify({"error": "Rate limit exceeded. Please slow down."}), 429


if __name__ == "__main__":
    # Fix 8: debug=False — nie im Produktionsmodus aktivieren
    app.run(host="127.0.0.1", port=5001, debug=False)
