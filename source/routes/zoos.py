"""
routes/zoos.py — Zoo-, Houses- und Species-Endpoints

Endpoints:
  GET /api/v1/zoos                        — Zoo-Liste (alle aktiven Zoos)
  GET /api/v1/zoos/<zoo>                  — Zoo-Details
  GET /api/v1/zoos/<zoo>/houses           — Tierhäuser eines Zoos
  GET /api/v1/zoos/<zoo>/houses/<id>      — einzelnes Tierhaus mit Gehegen
  POST /api/v1/zoos/<zoo>/houses          — Tierhaus anlegen (write)
  PUT  /api/v1/zoos/<zoo>/houses/<id>     — Tierhaus bearbeiten (write)
  DELETE /api/v1/zoos/<zoo>/houses/<id>   — Tierhaus löschen (write)
  GET /api/v1/zoos/<zoo>/species          — Artenliste eines Zoos
"""

import logging
import psycopg2.extras
from flask import Blueprint, jsonify, request
from helpers.authz import require_zoo_access, require_authenticated
from helpers.coordinates import is_valid_slug
from db import get_pg_connection
from extensions import limiter

zoos_bp = Blueprint("zoos", __name__)


###############################################################################
# ── Zoo-Liste ─────────────────────────────────────────────────────────────────
###############################################################################

@zoos_bp.route("/api/v1/zoos", methods=["GET"])
@limiter.limit("60 per minute")
def list_zoos():
    """
    Alle aktiven Zoos.
    Öffentlich (App-Token oder JWT) — kein Zoo-spezifischer Zugriff nötig.
    Gibt Basisdaten zurück die die App zum Aufbau des Zoo-Verzeichnisses braucht.
    """
    user_id, err = require_authenticated()
    if err: return err

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id, slug, name, city, country,
                       url, description,
                       top_left_latitude,    top_left_longitude,
                       bottom_right_latitude, bottom_right_longitude,
                       map_overlay, data_version,
                       easy_language, number_animals, icon_url,
                       latitude, longitude
                FROM zoo.zoos
                WHERE is_active = TRUE
                  AND archived_at IS NULL
                ORDER BY name
            """)
            results = cur.fetchall()
        return jsonify([dict(r) for r in results]), 200
    except Exception:
        logging.exception("Exception in GET /api/v1/zoos")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


###############################################################################
# ── Zoo-Details ───────────────────────────────────────────────────────────────
###############################################################################

@zoos_bp.route("/api/v1/zoos/<zoo>", methods=["GET"])
@limiter.limit("60 per minute")
def get_zoo(zoo):
    """
    Zoo-Details inkl. Öffnungszeiten.
    Erfordert Lesezugriff auf diesen Zoo.
    """
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400

    user_id, err = require_zoo_access(zoo, "read")
    if err: return err

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT z.id, z.slug, z.name, z.city, z.country,
                       z.url, z.description, z.email,
                       z.top_left_latitude,    z.top_left_longitude,
                       z.bottom_right_latitude, z.bottom_right_longitude,
                       z.map_overlay, z.data_version,
                       z.easy_language, z.number_animals, z.icon_url,
                       z.time_open, z.time_close
                FROM zoo.zoos z
                WHERE z.slug = %s
                  AND z.is_active = TRUE
                  AND z.archived_at IS NULL
            """, (zoo,))
            row = cur.fetchone()
            if not row:
                return jsonify({"error": "Zoo not found"}), 404
            zoo_data = dict(row)

            # Öffnungszeiten (falls vorhanden)
            cur.execute("""
                SELECT day_of_week, open_time, close_time, valid_from, valid_until, label
                FROM zoo.zoo_opening_hours
                WHERE zoo_id = %s
                ORDER BY day_of_week
            """, (zoo_data["id"],))
            zoo_data["opening_hours"] = [dict(r) for r in cur.fetchall()]

        return jsonify(zoo_data), 200
    except Exception:
        logging.exception(f"Exception in GET /api/v1/zoos/{zoo}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


###############################################################################
# ── Houses ────────────────────────────────────────────────────────────────────
###############################################################################

@zoos_bp.route("/api/v1/zoos/<zoo>/houses", methods=["GET"])
@limiter.limit("60 per minute")
def get_houses(zoo):
    """Alle Tierhäuser eines Zoos inkl. Anzahl Gehege."""
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "read")
    if err: return err

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT h.id, h.name, h.description, h.history,
                       h.sponsor, h.notes,
                       COUNT(e.id) AS enclosure_count
                FROM zoo.houses h
                JOIN zoo.zoos z ON z.id = h.zoo_id
                LEFT JOIN zoo.enclosures e ON e.house_id = h.id
                WHERE z.slug = %s
                GROUP BY h.id
                ORDER BY h.name
            """, (zoo,))
            results = cur.fetchall()
        return jsonify([dict(r) for r in results]), 200
    except Exception:
        logging.exception(f"Exception in GET /api/v1/zoos/{zoo}/houses")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@zoos_bp.route("/api/v1/zoos/<zoo>/houses/<int:house_id>", methods=["GET"])
@limiter.limit("60 per minute")
def get_house(zoo, house_id):
    """Einzelnes Tierhaus mit seinen Gehegen."""
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "read")
    if err: return err

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT h.id, h.name, h.description, h.history,
                       h.sponsor, h.notes
                FROM zoo.houses h
                JOIN zoo.zoos z ON z.id = h.zoo_id
                WHERE h.id = %s AND z.slug = %s
            """, (house_id, zoo))
            house = cur.fetchone()
            if not house:
                return jsonify({"error": "House not found"}), 404
            house = dict(house)

            # Gehege dieses Hauses
            cur.execute("""
                SELECT e.id, e.name, e.sort_order, e.domain_id,
                       s.id AS species_id, s.german_name, s.latin_name,
                       s.wikidata_id, s.iucn_status_id
                FROM zoo.enclosures e
                LEFT JOIN zoo.enclosure_species es ON es.enclosure_id = e.id
                LEFT JOIN zoo.species s ON s.id = es.species_id
                WHERE e.house_id = %s
                ORDER BY e.sort_order, e.name
            """, (house_id,))
            house["enclosures"] = [dict(r) for r in cur.fetchall()]

        return jsonify(house), 200
    except Exception:
        logging.exception(f"Exception in GET /api/v1/zoos/{zoo}/houses/{house_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@zoos_bp.route("/api/v1/zoos/<zoo>/houses", methods=["POST"])
@limiter.limit("30 per minute")
def create_house(zoo):
    """Tierhaus anlegen. Body: { name, description, history, sponsor, notes }"""
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "write")
    if err: return err

    data        = request.get_json(silent=True) or {}
    name        = data.get("name", "").strip()
    description = data.get("description", "").strip() or None
    history     = data.get("history", "").strip() or None
    sponsor     = data.get("sponsor", "").strip() or None
    notes       = data.get("notes", "").strip() or None

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
                INSERT INTO zoo.houses (zoo_id, name, description, history, sponsor, notes)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (zoo_row["id"], name, description, history, sponsor, notes))
            house_id = cur.fetchone()["id"]
        pg.commit()
        return jsonify({"id": house_id, "message": "Created"}), 201
    except Exception:
        logging.exception(f"Exception in POST /api/v1/zoos/{zoo}/houses")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@zoos_bp.route("/api/v1/zoos/<zoo>/houses/<int:house_id>", methods=["PUT"])
@limiter.limit("30 per minute")
def update_house(zoo, house_id):
    """Tierhaus bearbeiten."""
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "write")
    if err: return err

    data = request.get_json(silent=True) or {}
    ALLOWED = {"name", "description", "history", "sponsor", "notes"}
    unknown = set(data.keys()) - ALLOWED
    if unknown:
        return jsonify({"error": f"Unknown fields: {', '.join(sorted(unknown))}"}), 400
    if not data:
        return jsonify({"error": "No fields to update"}), 400
    if "name" in data:
        if not data["name"] or not str(data["name"]).strip():
            return jsonify({"error": "name must not be empty"}), 400
        if len(str(data["name"])) > 200:
            return jsonify({"error": "name must be at most 200 characters"}), 400

    set_clauses = ", ".join(f"{k} = %s" for k in data)
    values      = list(data.values()) + [house_id, zoo]

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor() as cur:
            cur.execute(f"""
                UPDATE zoo.houses SET {set_clauses}
                WHERE id = %s
                  AND zoo_id = (SELECT id FROM zoo.zoos WHERE slug = %s)
                RETURNING id
            """, values)
            if not cur.fetchone():
                return jsonify({"error": "House not found"}), 404
        pg.commit()
        return jsonify({"message": "Updated"}), 200
    except Exception:
        logging.exception(f"Exception in PUT /api/v1/zoos/{zoo}/houses/{house_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@zoos_bp.route("/api/v1/zoos/<zoo>/houses/<int:house_id>", methods=["DELETE"])
@limiter.limit("10 per minute")
def delete_house(zoo, house_id):
    """Tierhaus löschen (inkl. aller Gehege via CASCADE)."""
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "write")
    if err: return err

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor() as cur:
            cur.execute("""
                DELETE FROM zoo.houses
                WHERE id = %s
                  AND zoo_id = (SELECT id FROM zoo.zoos WHERE slug = %s)
            """, (house_id, zoo))
            if cur.rowcount == 0:
                return jsonify({"error": "House not found"}), 404
        pg.commit()
        return jsonify({"message": "Deleted"}), 200
    except Exception:
        logging.exception(f"Exception in DELETE /api/v1/zoos/{zoo}/houses/{house_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


###############################################################################
# ── Artenliste pro Zoo ────────────────────────────────────────────────────────
###############################################################################

@zoos_bp.route("/api/v1/zoos/<zoo>/species", methods=["GET"])
@limiter.limit("60 per minute")
def get_zoo_species(zoo):
    """
    Alle Tierarten die in diesem Zoo gehalten werden.
    Aggregiert aus enclosure_species — jede Art einmal, mit Zoo-Kontext.

    Query-Parameter:
      ?domain_id=<int>   — nur Arten einer Domain
      ?search=<str>      — Suche in deutschem oder lateinischem Namen
    """
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "read")
    if err: return err

    domain_id = request.args.get("domain_id")
    search    = request.args.get("search", "").strip()

    conditions = ["z.slug = %s"]
    params     = [zoo]

    if domain_id:
        try:
            domain_id = int(domain_id)
        except ValueError:
            return jsonify({"error": "domain_id must be an integer"}), 400
        conditions.append("e.domain_id = %s")
        params.append(domain_id)

    if search:
        conditions.append(
            "(s.german_name ILIKE %s OR s.latin_name ILIKE %s)"
        )
        params.extend([f"%{search}%", f"%{search}%"])

    where = " AND ".join(conditions)

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(f"""
                SELECT DISTINCT
                    s.id, s.wikidata_id, s.german_name, s.latin_name,
                    s.iucn_status_id, s.iucn_id, s.gbif_taxon_key,
                    s.iucn_population_trend_id, s.id_valid,
                    COUNT(DISTINCT e.id) AS enclosure_count
                FROM zoo.species s
                JOIN zoo.enclosure_species es ON es.species_id = s.id
                JOIN zoo.enclosures e ON e.id = es.enclosure_id
                JOIN zoo.zoos z ON z.id = e.zoo_id
                WHERE {where}
                GROUP BY s.id
                ORDER BY s.german_name
            """, params)
            results = cur.fetchall()
        return jsonify([dict(r) for r in results]), 200
    except Exception:
        logging.exception(f"Exception in GET /api/v1/zoos/{zoo}/species")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


###############################################################################
# ── Domains GET ───────────────────────────────────────────────────────────────
###############################################################################

@zoos_bp.route("/api/v1/zoos/<zoo>/domains", methods=["GET"])
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


@zoos_bp.route("/api/v1/zoos/<zoo>/domains/<int:domain_id>", methods=["GET"])
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

###############################################################################
# ── Domains CRUD ──────────────────────────────────────────────────────────────
###############################################################################

@zoos_bp.route("/api/v1/zoos/<zoo>/domains", methods=["POST"])
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


@zoos_bp.route("/api/v1/zoos/<zoo>/domains/<int:domain_id>", methods=["PUT"])
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


@zoos_bp.route("/api/v1/zoos/<zoo>/domains/<int:domain_id>", methods=["DELETE"])
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


###############################################################################
# ── Locations CRUD ────────────────────────────────────────────────────────────
###############################################################################

@zoos_bp.route("/api/v1/zoos/<zoo>/locations", methods=["GET"])
@limiter.limit("60 per minute")
def get_locations(zoo):
    """Alle Infrastruktur-POIs eines Zoos (Toilette, Restaurant, Spielplatz, …)."""
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "read")
    if err: return err

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT l.id, l.name, l.name_display, l.description,
                       l.location_type, l.sort_order, l.domain_id,
                       l.url, l.description_long,
                       d.name AS domain_name
                FROM zoo.locations l
                JOIN zoo.zoos z ON z.id = l.zoo_id
                LEFT JOIN zoo.domains d ON d.id = l.domain_id
                WHERE z.slug = %s
                ORDER BY l.sort_order, l.name
            """, (zoo,))
            results = cur.fetchall()
        return jsonify([dict(r) for r in results]), 200
    except Exception:
        logging.exception(f"Exception in GET /api/v1/zoos/{zoo}/locations")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@zoos_bp.route("/api/v1/zoos/<zoo>/locations/<int:location_id>", methods=["GET"])
@limiter.limit("60 per minute")
def get_location(zoo, location_id):
    """Einzelner Infrastruktur-POI inkl. Öffnungszeiten."""
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "read")
    if err: return err

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT l.id, l.name, l.name_display, l.description,
                       l.location_type, l.sort_order, l.domain_id,
                       l.url, l.description_long
                FROM zoo.locations l
                JOIN zoo.zoos z ON z.id = l.zoo_id
                WHERE l.id = %s AND z.slug = %s
            """, (location_id, zoo))
            loc = cur.fetchone()
            if not loc:
                return jsonify({"error": "Location not found"}), 404
            loc = dict(loc)

            # Öffnungszeiten
            cur.execute("""
                SELECT day_of_week, open_time, close_time, valid_from, valid_until, label
                FROM zoo.opening_hours
                WHERE location_id = %s
                ORDER BY day_of_week
            """, (location_id,))
            loc["opening_hours"] = [dict(r) for r in cur.fetchall()]

        return jsonify(loc), 200
    except Exception:
        logging.exception(f"Exception in GET /api/v1/zoos/{zoo}/locations/{location_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@zoos_bp.route("/api/v1/zoos/<zoo>/locations", methods=["POST"])
@limiter.limit("30 per minute")
def create_location(zoo):
    """
    Infrastruktur-POI anlegen.
    Body: { name, name_display, description, location_type, sort_order,
            domain_id, url, description_long }
    """
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
                INSERT INTO zoo.locations
                    (zoo_id, name, name_display, description, location_type,
                     sort_order, domain_id, url, description_long)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                zoo_row["id"], name,
                data.get("name_display") or None,
                data.get("description") or None,
                data.get("location_type") or None,
                data.get("sort_order", 0),
                data.get("domain_id") or None,
                data.get("url") or None,
                data.get("description_long") or None,
            ))
            location_id = cur.fetchone()["id"]
        pg.commit()
        return jsonify({"id": location_id, "message": "Created"}), 201
    except Exception:
        logging.exception(f"Exception in POST /api/v1/zoos/{zoo}/locations")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@zoos_bp.route("/api/v1/zoos/<zoo>/locations/<int:location_id>", methods=["PUT"])
@limiter.limit("30 per minute")
def update_location(zoo, location_id):
    """Infrastruktur-POI bearbeiten."""
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "write")
    if err: return err

    data = request.get_json(silent=True) or {}
    ALLOWED = {"name", "name_display", "description", "location_type",
               "sort_order", "domain_id", "url", "description_long"}
    unknown = set(data.keys()) - ALLOWED
    if unknown:
        return jsonify({"error": f"Unknown fields: {', '.join(sorted(unknown))}"}), 400
    if not data:
        return jsonify({"error": "No fields to update"}), 400
    if "name" in data:
        if not str(data["name"]).strip():
            return jsonify({"error": "name must not be empty"}), 400

    set_clauses = ", ".join(f"{k} = %s" for k in data)
    values = list(data.values()) + [location_id, zoo]

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor() as cur:
            cur.execute(f"""
                UPDATE zoo.locations SET {set_clauses}
                WHERE id = %s
                  AND zoo_id = (SELECT id FROM zoo.zoos WHERE slug = %s)
                RETURNING id
            """, values)
            if not cur.fetchone():
                return jsonify({"error": "Location not found"}), 404
        pg.commit()
        return jsonify({"message": "Updated"}), 200
    except Exception:
        logging.exception(f"Exception in PUT /api/v1/zoos/{zoo}/locations/{location_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()


@zoos_bp.route("/api/v1/zoos/<zoo>/locations/<int:location_id>", methods=["DELETE"])
@limiter.limit("10 per minute")
def delete_location(zoo, location_id):
    """Infrastruktur-POI löschen (inkl. Öffnungszeiten via CASCADE)."""
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400
    user_id, err = require_zoo_access(zoo, "write")
    if err: return err

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor() as cur:
            cur.execute("""
                DELETE FROM zoo.locations
                WHERE id = %s
                  AND zoo_id = (SELECT id FROM zoo.zoos WHERE slug = %s)
            """, (location_id, zoo))
            if cur.rowcount == 0:
                return jsonify({"error": "Location not found"}), 404
        pg.commit()
        return jsonify({"message": "Deleted"}), 200
    except Exception:
        logging.exception(f"Exception in DELETE /api/v1/zoos/{zoo}/locations/{location_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg: pg.close()
