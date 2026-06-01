import os
import logging
from flask import Blueprint, jsonify, request, send_file, Response
from helpers.auth_utils import require_app_token
from helpers.coordinates import is_valid_slug
from db import get_pg_connection
from extensions import limiter

sqlite_bp = Blueprint("sqlite", __name__)

SQLITE_DIR = os.path.join(os.path.expanduser("~"), "sqlite")


@sqlite_bp.route("/db/<zoo>", methods=["GET"])
@limiter.limit("10 per minute")
def get_sqlite(zoo):
    device_id, err = require_app_token()
    if err: return err

    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400

    sqlite_path = os.path.join(SQLITE_DIR, f"{zoo}.sqlite.gz")
    if not os.path.isfile(sqlite_path):
        return jsonify({"error": "Not found"}), 404

    current_version = None
    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor() as cur:
            cur.execute(
                "SELECT data_version FROM zoos WHERE slug = %s",
                (zoo,)
            )
            row = cur.fetchone()
            if row:
                current_version = str(row[0])
    except Exception as e:
        logging.warning(f"data_version konnte nicht geladen werden: {e}")
    finally:
        if pg:
            pg.close()

    if current_version:
        client_etag = request.headers.get("If-None-Match", "").strip('"')
        if client_etag == current_version:
            return Response(status=304)

    response = send_file(
        sqlite_path,
        mimetype="application/octet-stream",
        as_attachment=True,
        download_name=f"{zoo}.sqlite.gz"
    )

    if current_version:
        response.headers["ETag"] = f'"{current_version}"'
        response.headers["Cache-Control"] = "no-cache"

    return response
