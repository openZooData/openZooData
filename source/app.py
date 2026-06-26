import os
import logging
import hmac
from pathlib import Path

# .env laden — muss als allererstes passieren
import sys
sys.path.insert(0, str(Path(__file__).parent))
from helpers.env_loader import load_env
load_env()

# Jetzt erst alle anderen Imports
from flask import Flask, jsonify, request
from extensions import limiter
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.exceptions import HTTPException

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024
limiter.init_app(app)
logging.basicConfig(
    filename="flask-error.log",
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s:%(name)s:%(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET or len(JWT_SECRET) < 32:
    raise RuntimeError("JWT_SECRET fehlt oder ist zu kurz (min. 32 Zeichen)")

HEALTH_CHECK_KEY = os.getenv("HEALTH_CHECK_KEY")
if not HEALTH_CHECK_KEY or len(HEALTH_CHECK_KEY) < 32:
    raise RuntimeError("HEALTH_CHECK_KEY fehlt oder ist zu kurz (min. 32 Zeichen)")

PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
if not PUBLIC_BASE_URL or not PUBLIC_BASE_URL.startswith(("https://", "http://")):
    raise RuntimeError(
        "PUBLIC_BASE_URL fehlt oder ist ungültig. "
        "Beispiel: PUBLIC_BASE_URL=https://api.zooguide.app"
    )

from routes.auth       import auth_bp
from routes.app_auth   import app_auth_bp
from routes.sqlite     import sqlite_bp
from routes.publish    import publish_bp
from routes.media      import media_bp
from routes.feedback   import feedback_bp
from routes.feed       import feed_bp
from routes.zoo_routes import register_zoo_blueprints
from routes.admin_routes import register_admin_blueprints
from routes.media_bundle import media_bundle_bp
from routes.qr           import qr_bp

app.register_blueprint(auth_bp)
app.register_blueprint(app_auth_bp)
app.register_blueprint(sqlite_bp)
app.register_blueprint(publish_bp)
app.register_blueprint(media_bp)
app.register_blueprint(feedback_bp)
app.register_blueprint(feed_bp)
app.register_blueprint(media_bundle_bp)
app.register_blueprint(qr_bp)
register_zoo_blueprints(app)
register_admin_blueprints(app)


@app.route("/")
def root():
    return jsonify({"message": "openZooData API is running.", "status": "ok"}), 200


@app.route("/status")
def status():
    # Zoo-DB und Auth-DB bleiben getrennt; beide müssen erreichbar sein.
    from db import get_pg_connection, get_auth_connection
    try:
        for fn in (get_pg_connection, get_auth_connection):
            c = fn()
            c.cursor().execute("SELECT 1")
            c.close()
        return jsonify({"status": "ok"}), 200
    except Exception:
        return jsonify({"status": "degraded"}), 503


@app.route("/status/details")
@limiter.limit("30 per minute")
def status_details():
    key = request.headers.get("X-Health-Key", "")
    if not key or not hmac.compare_digest(key, HEALTH_CHECK_KEY):
        return jsonify({"error": "Unauthorized"}), 403

    from db import get_pg_connection, get_auth_connection
    checks = {}
    healthy = True

    try:
        c = get_pg_connection()
        c.cursor().execute("SELECT 1")
        c.close()
        checks["db_zoo"] = "ok"
    except Exception:
        logging.exception("Health-Check: Zoo-DB nicht erreichbar")
        checks["db_zoo"] = "error"
        healthy = False

    try:
        c = get_auth_connection()
        c.cursor().execute("SELECT 1")
        c.close()
        checks["db_auth"] = "ok"
    except Exception:
        logging.exception("Health-Check: Auth-DB nicht erreichbar")
        checks["db_auth"] = "error"
        healthy = False

    sqlite_dir = os.path.join(os.path.expanduser("~"), "sqlite")
    checks["sqlite_files"] = len([
        f for f in os.listdir(sqlite_dir) if f.endswith(".sqlite.gz")
    ]) if os.path.isdir(sqlite_dir) else 0

    return jsonify({
        "status": "ok" if healthy else "degraded",
        "checks": checks,
    }), 200 if healthy else 503


@app.after_request
def set_security_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    # Werkzeug-Dev-Server verrät standardmäßig Framework+Python-Version
    # im Server-Header (z.B. "Werkzeug/3.1.6 Python/3.11.15") — überschreiben,
    # damit keine Fingerprinting-Infos nach außen gehen.
    resp.headers["Server"] = "openZooData"
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
    from werkzeug.serving import WSGIRequestHandler

    class _QuietRequestHandler(WSGIRequestHandler):
        """
        Werkzeug schreibt sonst "Werkzeug/x.x Python/x.x.x" in den Server-
        Header (Framework-Fingerprinting). version_string() ist die Stelle,
        an der dieser String tatsächlich erzeugt wird — hier überschreiben
        statt im Nachhinein über response.headers zu versuchen, einen ggf.
        von Werkzeug separat gesetzten Server-Header zu überschreiben.
        """
        def version_string(self):
            return "openZooData"

    host = os.getenv("FLASK_HOST", "127.0.0.1")
    port = int(os.getenv("FLASK_PORT", "5001"))
    app.run(host=host, port=port, debug=False, request_handler=_QuietRequestHandler)
