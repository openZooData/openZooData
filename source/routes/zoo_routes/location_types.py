import logging
import psycopg2.extras
from flask import Blueprint, jsonify, request
from db import get_pg_connection
from extensions import limiter
from helpers.coordinates import is_valid_slug
from helpers.authz import require_authenticated, require_super_admin

location_types_bp = Blueprint("location_types_bp", __name__)

@location_types_bp.route("/api/v1/location-types", methods=["GET"])
@limiter.limit("60 per minute")
def get_location_types():
    """Alle Location-Typen — lesbar für alle JWT-User."""
    from helpers.authz import require_authenticated
    user_id, err = require_authenticated()
    if err: return err

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id, slug, name, icon, sort_order
                FROM zoo.location_types
                ORDER BY sort_order, name
            """)
            results = cur.fetchall()
        return jsonify([dict(r) for r in results]), 200
    except Exception:
        logging.exception("Exception in GET /api/v1/location-types")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@location_types_bp.route("/api/v1/location-types/<int:type_id>", methods=["GET"])
@limiter.limit("60 per minute")
def get_location_type(type_id):
    """Einzelner Location-Typ."""
    from helpers.authz import require_authenticated
    user_id, err = require_authenticated()
    if err: return err

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id, slug, name, icon, sort_order
                FROM zoo.location_types
                WHERE id = %s
            """, (type_id,))
            row = cur.fetchone()
            if not row:
                return jsonify({"error": "Location type not found"}), 404
        return jsonify(dict(row)), 200
    except Exception:
        logging.exception(f"Exception in GET /api/v1/location-types/{type_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@location_types_bp.route("/api/v1/location-types", methods=["POST"])
@limiter.limit("30 per minute")
def create_location_type():
    """Location-Typ anlegen — nur super_admin."""
    from helpers.authz import require_super_admin
    actor_id, err = require_super_admin()
    if err: return err

    data = request.get_json(silent=True) or {}
    slug = data.get("slug", "").strip()
    name = data.get("name", "").strip()

    if not slug:
        return jsonify({"error": "slug required"}), 400
    if not name:
        return jsonify({"error": "name required"}), 400
    if len(slug) > 50:
        return jsonify({"error": "slug must be at most 50 characters"}), 400
    if len(name) > 100:
        return jsonify({"error": "name must be at most 100 characters"}), 400

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                INSERT INTO zoo.location_types (slug, name, icon, sort_order)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            """, (
                slug, name,
                data.get("icon") or None,
                data.get("sort_order", 0),
            ))
            type_id = cur.fetchone()["id"]
        pg.commit()
        return jsonify({"id": type_id, "message": "Created"}), 201
    except Exception as e:
        if "unique" in str(e).lower():
            return jsonify({"error": f"Slug '{slug}' already exists"}), 409
        logging.exception("Exception in POST /api/v1/location-types")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@location_types_bp.route("/api/v1/location-types/<int:type_id>", methods=["PUT"])
@limiter.limit("30 per minute")
def update_location_type(type_id):
    """Location-Typ bearbeiten — nur super_admin."""
    from helpers.authz import require_super_admin
    actor_id, err = require_super_admin()
    if err: return err

    data = request.get_json(silent=True) or {}
    ALLOWED = {"slug", "name", "icon", "sort_order"}
    unknown = set(data.keys()) - ALLOWED
    if unknown:
        return jsonify({"error": f"Unknown fields: {', '.join(sorted(unknown))}"}), 400
    if not data:
        return jsonify({"error": "No fields to update"}), 400
    if "slug" in data:
        if not str(data["slug"]).strip():
            return jsonify({"error": "slug must not be empty"}), 400
        if len(str(data["slug"])) > 50:
            return jsonify({"error": "slug must be at most 50 characters"}), 400
    if "name" in data:
        if not str(data["name"]).strip():
            return jsonify({"error": "name must not be empty"}), 400
        if len(str(data["name"])) > 100:
            return jsonify({"error": "name must be at most 100 characters"}), 400

    set_clauses = ", ".join(f"{k} = %s" for k in data)
    values = list(data.values()) + [type_id]

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor() as cur:
            cur.execute(f"""
                UPDATE zoo.location_types SET {set_clauses}
                WHERE id = %s
                RETURNING id
            """, values)
            if not cur.fetchone():
                return jsonify({"error": "Location type not found"}), 404
        pg.commit()
        return jsonify({"message": "Updated"}), 200
    except Exception as e:
        if "unique" in str(e).lower():
            return jsonify({"error": "Slug already exists"}), 409
        logging.exception(f"Exception in PUT /api/v1/location-types/{type_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@location_types_bp.route("/api/v1/location-types/<int:type_id>", methods=["DELETE"])
@limiter.limit("10 per minute")
def delete_location_type(type_id):
    """
    Location-Typ löschen — nur super_admin.
    Schlägt fehl wenn noch Locations diesen Typ verwenden.
    """
    from helpers.authz import require_super_admin
    actor_id, err = require_super_admin()
    if err: return err

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor() as cur:
            # Prüfen ob noch Locations diesen Typ verwenden
            cur.execute("""
                SELECT COUNT(*) FROM zoo.locations
                WHERE location_type_id = %s
            """, (type_id,))
            count = cur.fetchone()[0]
            if count > 0:
                return jsonify({
                    "error": f"Cannot delete: {count} location(s) use this type"
                }), 409

            cur.execute("""
                DELETE FROM zoo.location_types WHERE id = %s
            """, (type_id,))
            if cur.rowcount == 0:
                return jsonify({"error": "Location type not found"}), 404
        pg.commit()
        return jsonify({"message": "Deleted"}), 200
    except Exception:
        logging.exception(f"Exception in DELETE /api/v1/location-types/{type_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()
