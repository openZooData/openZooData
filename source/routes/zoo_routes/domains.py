import logging
import psycopg2.extras
from flask import Blueprint, jsonify, request
from db import get_pg_connection
from extensions import limiter
from helpers.coordinates import is_valid_slug
from helpers.authz import require_zoo_access

domains_bp = Blueprint("domains_bp", __name__)

@domains_bp.route("/api/v1/zoos/<zoo>/domains", methods=["GET"])
@limiter.limit("60 per minute")
def get_domains(zoo):
    """Alle Domains eines Zoos (zoo-spezifisch + global)."""
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "read")
    if err: return err

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT d.id, d.name, d.is_infrastructure, d.sort_order,
                       d.color_red, d.color_green, d.color_blue, d.color_alpha,
                       d.zoo_id
                FROM zoo.domains d
                LEFT JOIN zoo.zoos z ON z.id = d.zoo_id
                WHERE d.zoo_id IS NULL OR z.slug = %s
                ORDER BY d.is_infrastructure DESC, d.sort_order, d.name
            """, (zoo,))
            results = cur.fetchall()
        return jsonify([dict(r) for r in results]), 200
    except Exception:
        logging.exception(f"Exception in GET /api/v1/zoos/{zoo}/domains")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@domains_bp.route("/api/v1/zoos/<zoo>/domains/<int:domain_id>", methods=["GET"])
@limiter.limit("60 per minute")
def get_domain(zoo, domain_id):
    """Einzelne Domain."""
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "read")
    if err: return err

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT d.id, d.name, d.is_infrastructure, d.sort_order,
                       d.color_red, d.color_green, d.color_blue, d.color_alpha,
                       d.zoo_id
                FROM zoo.domains d
                LEFT JOIN zoo.zoos z ON z.id = d.zoo_id
                WHERE d.id = %s
                  AND (d.zoo_id IS NULL OR z.slug = %s)
            """, (domain_id, zoo))
            row = cur.fetchone()
            if not row:
                return jsonify({"error": "Domain not found"}), 404
        return jsonify(dict(row)), 200
    except Exception:
        logging.exception(f"Exception in GET /api/v1/zoos/{zoo}/domains/{domain_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@domains_bp.route("/api/v1/zoos/<zoo>/domains", methods=["POST"])
@limiter.limit("30 per minute")
def create_domain(zoo):
    """Domain anlegen. Body: { name, is_infrastructure, sort_order, color_red, color_green, color_blue, color_alpha }"""
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "write")
    if err: return err

    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400
    if len(name) > 200:
        return jsonify({"error": "name must be at most 200 characters"}), 400

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT id FROM zoo.zoos WHERE slug = %s", (zoo,))
            zoo_row = cur.fetchone()
            if not zoo_row:
                return jsonify({"error": "Zoo not found"}), 404

            cur.execute("""
                INSERT INTO zoo.domains
                    (zoo_id, name, is_infrastructure, sort_order,
                     color_red, color_green, color_blue, color_alpha)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                zoo_row["id"], name,
                data.get("is_infrastructure", False),
                data.get("sort_order", 0),
                data.get("color_red", 128),
                data.get("color_green", 128),
                data.get("color_blue", 128),
                data.get("color_alpha", 1.0),
            ))
            domain_id = cur.fetchone()["id"]
        pg.commit()
        return jsonify({"id": domain_id, "message": "Created"}), 201
    except Exception:
        logging.exception(f"Exception in POST /api/v1/zoos/{zoo}/domains")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@domains_bp.route("/api/v1/zoos/<zoo>/domains/<int:domain_id>", methods=["PUT"])
@limiter.limit("30 per minute")
def update_domain(zoo, domain_id):
    """Domain bearbeiten."""
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "write")
    if err: return err

    data = request.get_json(silent=True) or {}
    ALLOWED = {"name", "is_infrastructure", "sort_order",
               "color_red", "color_green", "color_blue", "color_alpha"}
    unknown = set(data.keys()) - ALLOWED
    if unknown:
        return jsonify({"error": f"Unknown fields: {', '.join(sorted(unknown))}"}), 400
    if not data:
        return jsonify({"error": "No fields to update"}), 400
    if "name" in data:
        if not str(data["name"]).strip():
            return jsonify({"error": "name must not be empty"}), 400
        if len(str(data["name"])) > 200:
            return jsonify({"error": "name must be at most 200 characters"}), 400

    set_clauses = ", ".join(f"{k} = %s" for k in data)
    values = list(data.values()) + [domain_id, zoo]

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor() as cur:
            cur.execute(f"""
                UPDATE zoo.domains SET {set_clauses}
                WHERE id = %s
                  AND zoo_id = (SELECT id FROM zoo.zoos WHERE slug = %s)
                RETURNING id
            """, values)
            if not cur.fetchone():
                return jsonify({"error": "Domain not found"}), 404
        pg.commit()
        return jsonify({"message": "Updated"}), 200
    except Exception:
        logging.exception(f"Exception in PUT /api/v1/zoos/{zoo}/domains/{domain_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@domains_bp.route("/api/v1/zoos/<zoo>/domains/<int:domain_id>", methods=["DELETE"])
@limiter.limit("10 per minute")
def delete_domain(zoo, domain_id):
    """Domain löschen."""
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "write")
    if err: return err

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor() as cur:
            cur.execute("""
                DELETE FROM zoo.domains
                WHERE id = %s
                  AND zoo_id = (SELECT id FROM zoo.zoos WHERE slug = %s)
            """, (domain_id, zoo))
            if cur.rowcount == 0:
                return jsonify({"error": "Domain not found"}), 404
        pg.commit()
        return jsonify({"message": "Deleted"}), 200
    except Exception:
        logging.exception(f"Exception in DELETE /api/v1/zoos/{zoo}/domains/{domain_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()
