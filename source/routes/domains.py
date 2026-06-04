import logging
import psycopg2.extras
from flask import Blueprint, jsonify
from helpers.authz import require_zoo_access
from helpers.coordinates import is_valid_slug
from db import get_pg_connection
from extensions import limiter

domains_bp = Blueprint("domains", __name__)


@domains_bp.route("/api/v1/zoos/<zoo>/domains", methods=["GET"])
@limiter.limit("60 per minute")
def get_domains(zoo):
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "read")
    if err: return err

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT d.id, d.name, d.is_infrastructure,
                       d.color_red, d.color_green, d.color_blue, d.color_alpha
                FROM zoo.domains d
                LEFT JOIN zoo.zoos z ON z.id = d.zoo_id
                WHERE d.zoo_id IS NULL OR z.slug = %s
                ORDER BY d.is_infrastructure DESC, d.sort_order, d.name
            """, (zoo,))
            results = cur.fetchall()
        return jsonify([dict(r) for r in results]), 200
    except Exception:
        logging.exception("Exception in GET domains")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg:
            pg.close()
