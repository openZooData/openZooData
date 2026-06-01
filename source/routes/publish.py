import os
import logging
import subprocess
from flask import Blueprint, jsonify
from helpers.auth_utils import require_jwt_write
from helpers.coordinates import is_valid_slug
from db import get_pg_connection
from extensions import limiter

publish_bp = Blueprint("publish", __name__)


@publish_bp.route("/api/v1/zoos/<zoo>/publish", methods=["POST"])
@limiter.limit("5 per minute")
def publish_zoo(zoo):
    key_data, err = require_jwt_write(zoo)
    if err: return err

    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400

    try:
        script_path = os.path.join(os.path.expanduser("~"), "tools", "export_sqlite.py")
        venv_python = os.path.join(os.path.expanduser("~"), "myapi-env", "bin", "python3")

        subprocess.Popen(
            [venv_python, script_path, "--zoo", zoo],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        new_version = None
        pg = None
        try:
            pg = get_pg_connection()
            with pg.cursor() as cur:
                cur.execute("""
                    UPDATE zoos
                    SET data_version = COALESCE(data_version, 0) + 1
                    WHERE slug = %s
                    RETURNING data_version
                """, (zoo,))
                row = cur.fetchone()
                new_version = row[0] if row else None
            pg.commit()
        except Exception as e:
            logging.warning(f"data_version konnte nicht aktualisiert werden: {e}")
        finally:
            if pg:
                pg.close()

        return jsonify({
            "message":      f"Export für {zoo} gestartet",
            "data_version": new_version
        }), 202

    except Exception as e:
        logging.exception("Exception in publish")
        return jsonify({"error": "Internal server error"}), 500
